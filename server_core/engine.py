import time
import datetime
import uuid
import threading
import json
from types import SimpleNamespace
import pandas as pd
import ccxt

from . import config
from . import state
from core.pivot_detector import detect_pivots
from core.pattern_scanner import scan_patterns
from core.trade_planner import build_trade_plan
from core.divergence import check_divergence
from .utils import as_float, clamp, timestamp_ms, trade_open_timestamp_ms, history_event_key, write_json_atomic
from .okx_client import (
    okx, sync_exchange_history, fetch_open_positions_snapshot,
    fetch_okx_account_snapshot, fetch_data, resolve_okx_inst_id, okx_timeframe_to_bar,
    capital_snapshot, normalize_position_side, position_is_open, fetch_market_quality
)
from .strategies import (
    strategy_profile, category_profile, category_has_keyword, strategy_category_permission,
    recent_strategy_stats, strategy_performance, auto_tune_strategy_params, apply_rehab_sizing_if_needed,
    get_confidence_score, build_sizing_plan, apply_exit_state_limits, tuned_runner_profile,
    runner_policy_text, fee_safe_stop_price, apply_adaptive_exits, create_mode_direct_setup,
    live_trade_permission, evaluate_mode_gate, infer_exit_reason, performance_block_reason,
    squeeze_hunter_release_ready
)
from .execution import (
    expected_trade_edge, risk_based_leverage_cap, execute_bounded_limit_entry, rebase_plan_to_fill,
    place_exact_fill_protection, emergency_close_unprotected, protective_algo_targets,
    amend_protective_stop, fetch_exchange_max_contracts, protection_retry_delay, okx_order_failed
)

def active_net_key(t):
    inst_id = t.get('instId') or ''
    symbol = t.get('symbol') or ''
    direction = normalize_position_side(t.get('direction'))
    return (inst_id if inst_id else symbol, direction)

def normalize_symbol_key(symbol):
    return str(symbol or '').upper().replace('/', '').replace(':USDT', '').replace('-USDT-SWAP', 'USDT')

def reserve_symbol_for_entry(symbol):
    key = normalize_symbol_key(symbol)
    with state.execution_state_lock:
        if key in state.reserved_symbols:
            return False, 'another strategy is already executing this symbol'
        if any(
            trade.get('status') == 'active' and normalize_symbol_key(trade.get('symbol') or trade.get('instId')) == key
            for trade in state.active_trades
        ):
            return False, 'one net lifecycle per symbol; existing position must close first'
        state.reserved_symbols.add(key)
    return True, key

def release_symbol_reservation(key):
    if not key:
        return
    with state.execution_state_lock:
        state.reserved_symbols.discard(key)

def merge_active_trade(existing, incoming):
    strategies = set(existing.get('strategy_mix') or [])
    if existing.get('strategy'):
        strategies.add(existing.get('strategy'))
    if incoming.get('strategy'):
        strategies.add(incoming.get('strategy'))
    strategies.discard('Mixed')

    existing['add_count'] = int(existing.get('add_count') or 1) + int(incoming.get('add_count') or 1)
    existing['strategy_mix'] = sorted(strategies)
    if len(strategies) > 1:
        existing['strategy'] = 'Mixed'
        existing['mode_reason'] = 'net position combined from multiple strategy entries'
    elif strategies:
        existing['strategy'] = next(iter(strategies))

    protection_ids = set(existing.get('protection_order_ids') or [])
    protection_ids.update(incoming.get('protection_order_ids') or [])
    for row in [existing, incoming]:
        if row.get('protection_order_id'):
            protection_ids.add(str(row['protection_order_id']))
    if protection_ids:
        existing['protection_order_ids'] = sorted(protection_ids)

    strategy_versions = set(existing.get('strategy_versions') or [])
    strategy_versions.update(incoming.get('strategy_versions') or [])
    for row in [existing, incoming]:
        if row.get('strategy_version'):
            strategy_versions.add(str(row['strategy_version']))
    if strategy_versions:
        existing['strategy_versions'] = sorted(strategy_versions)
        existing['strategy_version'] = (
            next(iter(strategy_versions)) if len(strategy_versions) == 1 else 'mixed-version'
        )

    for key in [
        'posId', 'instId', 'entry', 'current', 'sl', 'tp1', 'pnl', 'percentage',
        'leverage', 'initialMargin', 'notional', 'liquidationPrice', 'marginRatio',
        'runner_policy', 'optimizer', 'sizing_plan', 'planned_margin',
        'planned_notional', 'planned_leverage',
    ]:
        val = incoming.get(key)
        if val not in [None, '', 0]:
            existing[key] = val

    existing['status'] = 'active'
    existing['last_signal_id'] = incoming.get('id', existing.get('last_signal_id'))
    return existing

def collapse_active_records(records):
    collapsed = []
    index = {}
    for t in records:
        if t.get('status') != 'active':
            collapsed.append(t)
            continue
        key = active_net_key(t)
        if key in index:
            merge_active_trade(index[key], t)
        else:
            index[key] = dict(t)
            collapsed.append(index[key])
    return collapsed

def live_position_key(pos):
    info = pos.get('info') or {}
    inst_id = str(pos.get('instId') or info.get('instId') or '')
    symbol = normalize_symbol_key(pos.get('symbol'))
    return (inst_id if inst_id else symbol, normalize_position_side(pos.get('direction') or pos.get('side')))

def normalize_okx_position(pos):
    info = pos.get('info') or {}
    raw_symbol = str(pos.get('symbol') or pos.get('instId') or info.get('instId') or '')
    inst_id = str(info.get('instId') or pos.get('instId') or raw_symbol)
    side = normalize_position_side(
        pos.get('side')
        or pos.get('posSide')
        or info.get('posSide')
        or ('long' if as_float(pos.get('pos') or info.get('pos')) >= 0 else 'short')
    )
    contracts = as_float(pos.get('contracts') or pos.get('pos') or info.get('pos'))
    mark_price = as_float(pos.get('markPrice') or pos.get('markPx'))
    entry_price = as_float(pos.get('entryPrice') or pos.get('avgPx') or info.get('avgPx'))
    pnl = as_float(pos.get('unrealizedPnl', pos.get('upl', 0.0)))
    normalized = {
        'id': pos.get('id'),
        'posId': pos.get('id'),
        'instId': inst_id,
        'symbol': normalize_symbol_key(raw_symbol),
        'raw_symbol': raw_symbol,
        'direction': side,
        'status': 'active',
        'source': 'okx_live',
        'entry': entry_price,
        'current': mark_price,
        'pnl': pnl,
        'percentage': as_float(pos.get('percentage', pos.get('uplRatio', 0.0))),
        'leverage': pos.get('leverage') or pos.get('lever'),
        'initialMargin': as_float(pos.get('initialMargin')),
        'notional': as_float(pos.get('notional') or pos.get('notionalUsd')),
        'liquidationPrice': as_float(pos.get('liquidationPrice') or pos.get('liqPx')),
        'marginRatio': as_float(pos.get('marginRatio')),
        'contracts': contracts,
        'availPos': as_float(pos.get('availPos') or info.get('availPos')),
        'marginMode': info.get('mgnMode') or pos.get('marginMode') or pos.get('mgnMode'),
        'info': info or dict(pos),
    }
    if normalized['entry'] == 0:
        normalized['entry'] = as_float(info.get('avgPx') or pos.get('avgPx'))
    return normalized

def fetch_live_okx_positions():
    try:
        return [normalize_okx_position(p) for p in fetch_open_positions_snapshot()]
    except Exception as e:
        print(f"[live_positions ERROR] {e}")
        return []

def overlay_live_position_metadata(live_pos, tracked_trade=None):
    record = dict(live_pos)
    if tracked_trade:
        record['trade_id'] = tracked_trade.get('id')
        for key in [
            'strategy', 'pattern', 'trailing_stage', 'runner_policy',
            'protection_status', 'protection_error', 'protection_order_id',
            'protection_order_ids', 'missing_protection_checks', 'tp_removed',
            'sync_status', 'strategy_version', 'lifecycle_id', 'last_signal_id',
            'block_reason', 'entry_reason', 'mode_reason', 'highest_pnl',
            'highest_r', 'current_r', 'tp1', 'sl',
        ]:
            value = tracked_trade.get(key)
            if value not in [None, '']:
                record[key] = value
        if tracked_trade.get('source'):
            record['trade_source'] = tracked_trade.get('source')
    else:
        record.update({
            'strategy': 'Manual',
            'pattern': 'Manual / Unsynced',
            'trailing_stage': 'waiting',
            'runner_policy': None,
            'protection_status': 'unconfirmed',
            'protection_error': None,
        })
        record.setdefault('entry_reason', 'OKX live position without matching tracked lifecycle')
    record['status'] = 'active'
    return record

def build_live_trade_snapshot(tracked_records=None, live_positions=None, include_potentials=True):
    tracked_records = tracked_records if tracked_records is not None else collapse_active_records(state.active_trades)
    live_positions = live_positions if live_positions is not None else fetch_live_okx_positions()
    tracked_index = {
        active_net_key(t): dict(t)
        for t in tracked_records
        if t.get('status') == 'active'
    }
    merged = []
    for pos in live_positions:
        key = live_position_key(pos)
        tracked = tracked_index.get(key)
        if tracked:
            merged.append(overlay_live_position_metadata(pos, tracked))
        else:
            merged.append(overlay_live_position_metadata(pos, None))
    if include_potentials:
        merged.extend([dict(t) for t in state.potential_signals if t.get('symbol') and t.get('status') != 'active'])
    return merged

def run_strategy(strategy_name, timeframe, tolerance, sl_buffer_pct, trend_tf, target_rr):
    
    print(f"[{strategy_name}] Engine Started. ({timeframe} candles, {trend_tf} trend filter)")
    
    if timeframe.endswith('m'):
        tf_minutes = int(timeframe[:-1])
    elif timeframe.endswith('h'):
        tf_minutes = int(timeframe[:-1]) * 60
    else:
        tf_minutes = 5
    COOLDOWN_SECONDS = 10
    
    while True:
        try:
            symbols = state.global_symbols
            if not symbols:
                time.sleep(5)
                continue
                
            current_potentials = []
            current_radar = []
            
            for symbol in symbols:
                try:
                    # Apply Coin-Specific Profiles based on Dynamic Categories
                    cat = state.global_symbol_categories.get(symbol, 'Uncategorized')
                    
                    # Mode Alignment (Soft Whitelisting)
                    alignment_penalty = 1.0
                    if strategy_name == 'MeanReversion' and ('Squeeze' in cat):
                        alignment_penalty = 0.3
                    elif strategy_name == 'Contrarian' and not ('Oversold' in cat or 'Volatility' in cat):
                        alignment_penalty = 0.6
                    elif strategy_name == 'SqueezeHunter' and not ('Squeeze' in cat):
                        alignment_penalty = 0.4

                    # Fetch MTF Trend Data (1H, 4H, 1D)
                    def get_trend(sym, tf):
                        d = fetch_data(sym, tf, limit=500)
                        if d.empty or len(d) < 202: return 'neutral'
                        closed = d.iloc[:-1]
                        e50 = closed['close'].ewm(span=50, adjust=False).mean().iloc[-1]
                        e200 = closed['close'].ewm(span=200, adjust=False).mean().iloc[-1]
                        current_price = closed['close'].iloc[-1]
                        
                        if current_price > e200 and e50 > e200:
                            return 'bull'
                        elif current_price < e200 and e50 < e200:
                            return 'bear'
                        else:
                            return 'neutral' # Choppy transition phase, do not trade

                    trends_dict = {
                        '15m': get_trend(symbol, '15m'),
                        '1h': get_trend(symbol, '1h'),
                        '4h': get_trend(symbol, '4h'),
                        '1d': get_trend(symbol, '1d')
                    }
                    # MTF Trend Resonance (Triple Screen Logic)
                    # We dynamically select the macro timeframe (Factor of 4-6x higher than intermediate)
                    if timeframe == '5m': macro_tf = '1h'
                    elif timeframe == '15m': macro_tf = '4h'
                    elif timeframe == '1h': macro_tf = '1d'
                    else: macro_tf = '4h'
                    
                    trend_val = trends_dict.get(trend_tf, 'neutral')
                    macro_val = trends_dict.get(macro_tf, 'neutral')
                    
                    if trend_tf == 'none':
                        htf_bull = True
                        htf_bear = True
                    else:
                        # BOTH the strategy's specific trend AND the dynamic macro trend must not contradict
                        htf_bull = (trend_val == 'bull' and macro_val != 'bear')
                        htf_bear = (trend_val == 'bear' and macro_val != 'bull')
                    
                    # Fetch Entry Data
                    df = fetch_data(symbol, timeframe)
                    if df.empty or len(df) < 52:
                        continue
                    live_price = as_float(df['close'].iloc[-1])
                    signal_df = df.iloc[:-1].copy(deep=False)
                    
                    # Profit-first entry filter: require enough profit room to absorb fees/slippage.
                    min_profit = config.PROFIT_FIRST_MIN_ROOM_BY_TIMEFRAME.get(timeframe, 0.0035)
                    
                    # Calculate True ATR % (Average True Range as a percentage of price over last 14 candles)
                    recent_df = signal_df.tail(14)
                    if not recent_df.empty:
                        avg_range = (recent_df['high'] - recent_df['low']).mean()
                        atr_pct = (avg_range / live_price) if live_price > 0 else 0
                    else:
                        atr_pct = 0
                    
                    category_key, cat_prof = category_profile(cat)
                    mode_prof = strategy_profile(strategy_name)
                    active_tolerance = tolerance * cat_prof['tolerance_mult']
                    base_sl_buffer = sl_buffer_pct * cat_prof['sl_mult']
                    active_min_profit = min_profit * cat_prof['profit_mult']
                        
                    # DYNAMIC ATR-BASED STOP LOSS ADAPTATION
                    # Ensure SL is at least 60% of the average candle wick (ATR) so it doesn't get swept by noise
                    active_sl_buffer = max(base_sl_buffer, atr_pct * mode_prof['sl_atr'] * 0.35)

                    # Apply alignment penalty to tolerance (make it stricter for bad regimes)
                    active_tolerance = active_tolerance * alignment_penalty

                    # ML Engine Feedback (Determines position size multiplier)
                    confidence = get_confidence_score(strategy_name, cat) * alignment_penalty
                    confidence = clamp(confidence, 0.2, 2.5)
                    mode_perf = strategy_performance(strategy_name)
                    optimizer = auto_tune_strategy_params(strategy_name, mode_perf)
                    runner_prof = tuned_runner_profile(strategy_name, optimizer)
                    mode_block_reason = performance_block_reason(strategy_name)
                    active_tolerance = active_tolerance * optimizer['tolerance_mult']
                    active_min_profit = active_min_profit * optimizer['min_profit_mult']
                    tuned_target_rr = max(0.05, target_rr * optimizer['target_rr_mult'])

                    # Dynamic pivot depth based on standard Fractal/ZigZag math
                    pivot_depth = 4
                    if timeframe == '5m': pivot_depth = 1
                    elif timeframe == '15m': pivot_depth = 3
                    elif timeframe in ['1h', '4h']: pivot_depth = 4
                    
                    hist_pivots = detect_pivots(signal_df, depth=pivot_depth)
                    
                    # SYNTHESIZE REAL-TIME D-POINT
                    pivots = list(hist_pivots)
                    if len(pivots) >= 4:
                        pivots = pivots[-4:]
                        last_p = pivots[-1]
                        fake_type = "low" if last_p.type == "high" else "high"
                        current_close = signal_df['close'].iloc[-1]
                        current_time = str(signal_df['time'].iloc[-1])
                        current_idx = len(signal_df) - 1
                        
                        from core.pivot_detector import PivotPoint
                        fake_d = PivotPoint(current_idx, current_time, current_close, fake_type)
                        pivots.append(fake_d)
                    
                    patterns = scan_patterns(pivots, tolerance=active_tolerance)
                    direct_setup = create_mode_direct_setup(
                        strategy_name,
                        signal_df,
                        trends_dict,
                        htf_bull,
                        htf_bear,
                    )
                    if direct_setup:
                        patterns.append(direct_setup)
                    
                    display_sym = symbol.replace(':USDT', '').replace('/', '')
                    
                    # Radar Item
                    radar_item = {
                        'symbol': display_sym,
                        'category': state.global_symbol_categories.get(symbol, 'Uncategorized'),
                        'trends': trends_dict,
                        'rsi': round(signal_df['rsi'].iloc[-1], 1) if pd.notna(signal_df['rsi'].iloc[-1]) else 50,
                        'pattern': 'None',
                        'score': 0,
                        'trigger_reason': '掃描型態中 (Scanning)',
                        'strategy': strategy_name,
                        'active_tolerance': round(active_tolerance, 3),
                        'active_sl_buffer': round(active_sl_buffer, 3),
                        'active_min_profit': round(active_min_profit, 3),
                        'confidence': round(confidence, 2),
                        'mode_role': mode_prof['role'],
                        'category_key': category_key,
                        'mode_verdict': mode_perf.get('verdict'),
                        'optimizer': optimizer,
                        'tuned_target_rr': round(tuned_target_rr, 3),
                    }
                    if mode_block_reason:
                        radar_item['trigger_reason'] = mode_block_reason
                    
                    if patterns:
                        best_p = patterns[-1]
                        radar_item['pattern'] = best_p.pattern_name
                        radar_item['setup_source'] = getattr(best_p, 'setup_source', 'harmonic')
                        d_price = best_p.d.price
                        prz_width = best_p.prz_high - best_p.prz_low
                        buffer = max(prz_width * 0.15, abs(d_price) * 0.002, avg_range * 0.35)
                        try:
                            radar_plan = build_trade_plan(best_p.direction, best_p.x.price, best_p.a.price, best_p.c.price, d_price, best_p.pattern_name, min_rr=0.2, sl_buffer_pct=active_sl_buffer)
                            radar_plan['structural_stop'] = getattr(best_p, 'stop_reference', None)
                            radar_plan['structural_target'] = getattr(best_p, 'target_reference', None)
                            radar_plan = apply_adaptive_exits(radar_plan, strategy_name, live_price, best_p.direction, atr_pct, optimizer)
                            est_tp_pct = abs(radar_plan['tp1'] - live_price) / live_price
                            est_sl_pct = abs(live_price - radar_plan['sl']) / live_price
                            safe_lev = risk_based_leverage_cap(config.BASE_MARGIN_USDT, est_sl_pct, symbol=symbol)
                            radar_sizing = build_sizing_plan(strategy_name, cat, confidence, safe_lev, state.account_data.get('usdtAvail'))
                            radar_sizing = apply_rehab_sizing_if_needed(radar_sizing, mode_perf.get('verdict'), safe_lev, optimizer)
                            radar_item.update({
                                'est_tp_pct': round(est_tp_pct * 100, 2),
                                'est_sl_pct': round(est_sl_pct * 100, 2),
                                'est_rr': radar_plan.get('risk_reward'),
                                'planned_margin': radar_sizing['margin_usdt'],
                                'planned_notional': radar_sizing['target_notional'],
                                'planned_leverage': safe_lev,
                                'exit_model': radar_plan.get('exit_model'),
                            })
                        except Exception as radar_err:
                            radar_item['trigger_reason'] = f"radar plan error: {radar_err}"
                        in_prz = (best_p.prz_low - buffer) <= live_price <= (best_p.prz_high + buffer)
                        if in_prz:
                            radar_item['score'] = 100
                            radar_item['trigger_reason'] = 'PRZ 抵達！等待指標共振進場'
                        else:
                            dist = min(abs(live_price - best_p.prz_low), abs(live_price - best_p.prz_high))
                            radar_item['score'] = max(10, int(100 - (dist / live_price) * 1000))
                            direction = "做多" if best_p.direction == 'bullish' else "做空"
                            radar_item['trigger_reason'] = f"等待 D 點{direction}至 {best_p.prz_center:.4g}"
                            
                    current_radar.append(radar_item)
                    if len(current_radar) == 1 or len(current_radar) % 5 == 0:
                        state.market_radar_dict[strategy_name] = list(current_radar)
                    
                    for p in patterns:
                        d_price = p.d.price
                        prz_width = p.prz_high - p.prz_low
                        buffer = max(prz_width * 0.15, abs(d_price) * 0.002, avg_range * 0.35)
                        
                        # CRITICAL ENTRY POSITION OPTIMIZATION:
                        if strategy_name in ['SqueezeHunter', 'Contrarian', 'MeanReversion']:
                            in_prz = (p.prz_low - buffer) <= live_price <= (p.prz_high + buffer)
                        else:
                            # Trend mode waits for a real retest of its closed-bar level.
                            if p.direction == 'bullish':
                                trigger_price = p.prz_center + (prz_width * 0.2)
                                in_prz = live_price <= trigger_price and live_price >= (p.prz_low - buffer)
                            else:
                                trigger_price = p.prz_center - (prz_width * 0.2)
                                in_prz = live_price >= trigger_price and live_price <= (p.prz_high + buffer)
                        
                        # HTF Trend Filter - ENFORCED FOR ALL STRATEGIES (High Win-Rate Training Mode)
                        rsi = signal_df['rsi'].iloc[-1] if pd.notna(signal_df['rsi'].iloc[-1]) else 50
                        trend_ok = (p.direction == 'bullish' and htf_bull) or (p.direction == 'bearish' and htf_bear)
                        
                        # Pass the strategy's specific sl_buffer to the planner
                        plan = build_trade_plan(p.direction, p.x.price, p.a.price, p.c.price, p.d.price, p.pattern_name, min_rr=0.2, sl_buffer_pct=active_sl_buffer)
                        
                        # DYNAMIC TARGET COMPRESSION: Secure profits faster for aggressive/intraday modes
                        if strategy_name in ['MeanReversion', 'Contrarian']:
                            move_ad = abs(p.a.price - p.d.price)
                            if p.direction == 'bullish':
                                plan['tp1'] = p.d.price + move_ad * 0.382
                            else:
                                plan['tp1'] = p.d.price - move_ad * 0.382
                        
                        # CRITICAL WIN-RATE FIX: Calculate TRUE Risk/Reward based on the real-time execution price!
                        current_price = live_price
                        true_risk = abs(current_price - plan['sl'])
                        true_reward = abs(plan['tp1'] - current_price)
                        true_rr = true_reward / true_risk if true_risk > 0 else 0
                        
                        # Override the theoretical RR with the TRUE real-time RR
                        plan["risk_reward"] = round(true_rr, 2)
                        
                        # CHECK: Valid Live Target Prices?
                        sl_valid = (plan['sl'] < current_price) if p.direction == 'bullish' else (plan['sl'] > current_price)
                        tp_valid = (plan['tp1'] > current_price) if p.direction == 'bullish' else (plan['tp1'] < current_price)
                        
                        block_reason = None
                        squeeze_ready = False
                        if strategy_name == 'SqueezeHunter':
                            squeeze_ready = squeeze_hunter_release_ready(signal_df, sample=int(mode_perf.get('sample') or 0))
                        if not sl_valid or not tp_valid:
                            block_reason = "API 參數無效 (止盈止損反向)"
                        elif not trend_ok:
                            t_dir = '空' if htf_bear and not htf_bull else ('多' if htf_bull and not htf_bear else '平')
                            block_reason = f"大趨勢逆風 ({trend_tf} {t_dir})"
                        # Keep entries anchored to the PRZ; SqueezeHunter also needs a confirmed release.
                        is_prz_ok = in_prz
                        if not is_prz_ok:
                            block_reason = "尚未進入 PRZ 區間"
                        else:
                            # PROFITABILITY CHECK (Live Fire Calibration)
                            active_min_profit = max(active_min_profit, config.PROFIT_FIRST_MIN_ROOM_FLOOR)
                            profit_pct = abs(plan["tp1"] - current_price) / current_price
                            if profit_pct < active_min_profit:
                                block_reason = f"利潤空間太小 (<{(active_min_profit*100):.2f}%)"
                            elif true_rr < tuned_target_rr:
                                block_reason = f"真實盈虧比過低 ({round(true_rr, 2)} < {round(tuned_target_rr, 2)})"
                                
                        # Growth engine override
                        div_ok = check_divergence(signal_df, len(signal_df)-1, lookback=30, direction=p.direction)
                        current_candle = signal_df.iloc[-1]
                        sweep_ok = current_candle['low'] <= p.x.price if p.direction == 'bullish' else current_candle['high'] >= p.x.price
                        current_price = live_price
                        plan['structural_stop'] = getattr(p, 'stop_reference', None)
                        plan['structural_target'] = getattr(p, 'target_reference', None)
                        plan = apply_adaptive_exits(plan, strategy_name, current_price, p.direction, atr_pct, optimizer)
                        true_risk = abs(current_price - plan['sl'])
                        true_reward = abs(plan['tp1'] - current_price)
                        true_rr = true_reward / true_risk if true_risk > 0 else 0
                        plan["risk_reward"] = round(true_rr, 2)
                        sl_valid = (plan['sl'] < current_price) if p.direction == 'bullish' else (plan['sl'] > current_price)
                        tp_valid = (plan['tp1'] > current_price) if p.direction == 'bullish' else (plan['tp1'] < current_price)
                        mode_ok, mode_reason = evaluate_mode_gate(
                            strategy_name, p.direction, rsi, trends_dict, in_prz,
                            true_rr, tuned_target_rr, div_ok, sweep_ok,
                            signal_df, optimizer, symbol, cat,
                        )
                        profit_pct = abs(plan["tp1"] - current_price) / current_price
                        mode_paused = mode_perf.get('verdict') == 'pause'
                        rehab_rr_floor = max(tuned_target_rr, mode_prof['min_rr']) * config.REHAB_RR_MULTIPLIER
                        rehab_profit_floor = active_min_profit * config.REHAB_PROFIT_MULTIPLIER
                        rehab_ok = mode_paused and true_rr >= rehab_rr_floor and profit_pct >= rehab_profit_floor
                        if not sl_valid or not tp_valid:
                            block_reason = "invalid live TP/SL direction"
                        elif not mode_ok:
                            block_reason = mode_reason
                        elif mode_paused and not rehab_ok:
                            block_reason = f"training rehab waiting: needs RR >= {round(rehab_rr_floor, 2)} and profit room >= {(rehab_profit_floor*100):.2f}%"
                        elif profit_pct < active_min_profit:
                            block_reason = f"profit room too small (<{(active_min_profit*100):.2f}%)"
                        else:
                            block_reason = None
                            if rehab_ok:
                                mode_reason = "training sample allowed: base setup"

                        live_allowed, live_reason, live_tier = live_trade_permission(strategy_name, optimizer, mode_perf)
                        soft_override_note = None
                        if block_reason and live_allowed and live_tier in ['live_probe', 'live_learning', 'live_calibration']:
                            soft_reason = str(block_reason).lower()
                            soft_block = (
                                soft_reason.startswith('waiting for ')
                                or 'training rehab waiting' in soft_reason
                                or 'learning lane' in soft_reason
                                or 'profit room too small' in soft_reason
                                or soft_reason.startswith('rr ')
                            )
                            if soft_block and true_rr >= max(0.9, tuned_target_rr * 0.85) and profit_pct >= max(active_min_profit * 0.75, config.PROFIT_FIRST_MIN_ROOM_FLOOR):
                                soft_override_note = f"{live_reason}; soft override"
                                block_reason = None
                        display_sym = symbol.replace(':USDT', '').replace('/', '')
                        signal_obj = {
                            "id": state.trade_id_counter,
                            "symbol": display_sym,
                            "direction": "long" if p.direction == "bullish" else "short",
                            "pattern": p.pattern_name,
                            "setup_source": getattr(p, 'setup_source', 'harmonic'),
                            "status": "potential",
                            "entry": plan["entry"],
                            "current": live_price,
                            "signal_close": as_float(p.d.price),
                            "entry_reference": as_float(p.prz_center),
                            "entry_zone_low": as_float(p.prz_low),
                            "entry_zone_high": as_float(p.prz_high),
                            "structural_stop": as_float(getattr(p, 'stop_reference', 0)),
                            "structural_target": as_float(getattr(p, 'target_reference', 0)),
                            "sl": plan["sl"],
                            "tp1": plan["tp1"],
                            "original_tp_dist": abs(plan["tp1"] - current_price),
                            "original_sl_dist": abs(current_price - plan["sl"]),
                            "opened_at": datetime.datetime.now(datetime.UTC).isoformat(),
                            "pnl": 0.0,
                            "rsi_on_entry": round(signal_df['rsi'].iloc[-1], 1) if pd.notna(signal_df['rsi'].iloc[-1]) else 50,
                            "trends": trends_dict,
                            "strategy": strategy_name,
                            "lifecycle_id": uuid.uuid4().hex,
                            "category": cat,
                            "category_key": category_key,
                            "confidence": round(confidence, 2),
                            "mode_role": mode_prof['role'],
                            "mode_reason": mode_reason,
                            "mode_verdict": mode_perf.get('verdict'),
                            "rehab_mode": rehab_ok,
                            "optimizer": optimizer,
                            "tuned_target_rr": round(tuned_target_rr, 3),
                            "active_tolerance": round(active_tolerance, 4),
                            "active_min_profit": round(active_min_profit, 5),
                            "execution_mode": live_tier,
                            "live_permission": live_reason,
                            "exit_model": plan.get("exit_model"),
                            "est_rr": plan.get("risk_reward"),
                            "sl_dist_pct": plan.get("sl_dist_pct"),
                            "tp_dist_pct": plan.get("tp_dist_pct"),
                            "runner_policy": runner_policy_text(runner_prof),
                            "strategy_version": config.STRATEGY_VERSION,
                            "estimated_round_trip_cost_pct": round(config.FEE_SAFE_PROFIT_RATE * 100, 3),
                            "cost_safe_stop": fee_safe_stop_price(
                                current_price,
                                "long" if p.direction == "bullish" else "short",
                            ),
                            "signal_candle": int(signal_df['timestamp'].iloc[-1]),
                            "block_reason": block_reason
                        }

                        if soft_override_note:
                            signal_obj["mode_reason"] = f"{mode_reason}; {soft_override_note}"

                        if not live_allowed and not block_reason:
                            block_reason = live_reason
                            signal_obj["block_reason"] = block_reason
                            signal_obj["mode_reason"] = live_reason
                        
                        on_cooldown = False
                        signal_key = (strategy_name, symbol, p.direction)
                        signal_candle = signal_obj['signal_candle']
                        if state.global_executed_signal_candles.get(signal_key) == signal_candle and not block_reason:
                            block_reason = "same mode/symbol/candle already executed"
                            signal_obj["block_reason"] = block_reason
                        active_cooldown = COOLDOWN_SECONDS * optimizer['cooldown_mult']
                        if rehab_ok:
                            active_cooldown = min(active_cooldown, COOLDOWN_SECONDS * config.REHAB_COOLDOWN_MULTIPLIER)
                        cooldown_key = (strategy_name, symbol)
                        if cooldown_key in state.global_symbol_cooldowns and (time.time() - state.global_symbol_cooldowns[cooldown_key] < active_cooldown):
                            on_cooldown = True
                            if not block_reason:
                                block_reason = "cooldown active"
                                signal_obj["block_reason"] = block_reason
                        
                        # 檢查該幣種是否有反向持倉
                        has_opposite_position = False
                        try:
                            with open('active_trades.json', 'r', encoding='utf-8') as af:
                                active_list = json.load(af)
                            for act_t in active_list:
                                if act_t.get('symbol') == symbol:
                                    existing_dir = str(act_t.get('direction')).lower()
                                    new_dir = 'long' if p.direction == 'bullish' else 'short'
                                    if existing_dir != new_dir:
                                        has_opposite_position = True
                                        break
                        except Exception as e:
                            print(f'Error reading state.active_trades for conflict check: {e}')

                        if has_opposite_position:
                            block_reason = 'conflict: opposite position already exists'
                            signal_obj['block_reason'] = block_reason

                        reservation_key = None
                        if not block_reason:
                            reserved, reservation_result = reserve_symbol_for_entry(display_sym)
                            if reserved:
                                reservation_key = reservation_result
                            else:
                                block_reason = reservation_result
                                signal_obj['block_reason'] = block_reason

                        if not block_reason:
                            # ACTUAL OKX ORDER EXECUTION
                            try:
                                side = 'buy' if p.direction == 'bullish' else 'sell'
                                filled_size = 0.0
                                protection_confirmed = False
                                
                                # Size leverage by planned U loss, including an
                                # order-book-derived allowance for stop slippage.
                                sl_dist_pct = abs(current_price - plan['sl']) / current_price
                                market_quality = fetch_market_quality(symbol)
                                max_safe_leverage = int(0.8 / (sl_dist_pct + 0.002)) if sl_dist_pct > 0 else config.MAX_LEVERAGE_CAP
                                risk_preview = build_sizing_plan(
                                    strategy_name, cat, confidence, 1, state.account_data.get('usdtAvail')
                                )
                                risk_preview = apply_rehab_sizing_if_needed(
                                    risk_preview, mode_perf.get('verdict'), 1, optimizer
                                )
                                risk_leverage = risk_based_leverage_cap(
                                    risk_preview['margin_usdt'],
                                    sl_dist_pct,
                                    market_quality['exit_slippage_pct'],
                                    symbol,
                                )
                                safe_leverage_target = min(config.MAX_LEVERAGE_CAP, max_safe_leverage, risk_leverage)
                                base_leverages = [75, 50, 20, 10, 5, 2, 1]
                                leverages_to_try = [l for l in base_leverages if l <= safe_leverage_target]
                                if not leverages_to_try: leverages_to_try = [1]
                                
                                actual_leverage = None
                                sizing_plan = None
                                margin_usdt = config.BASE_MARGIN_USDT
                                target_notional = 0.0
                                size = 0
                                current_price = live_price
                                contract_size = float(okx.markets[symbol]['contractSize'])
                                for lev in leverages_to_try:
                                    try:
                                        okx.set_leverage(lev, symbol)
                                    except Exception:
                                        continue

                                    candidate_plan = build_sizing_plan(
                                        strategy_name,
                                        cat,
                                        confidence,
                                        lev,
                                        state.account_data.get('usdtAvail'),
                                    )
                                    candidate_plan = apply_rehab_sizing_if_needed(
                                        candidate_plan,
                                        mode_perf.get('verdict'),
                                        lev,
                                        optimizer,
                                    )
                                    candidate_notional = candidate_plan['target_notional']
                                    candidate_size = int(candidate_notional / (current_price * contract_size))
                                    if candidate_size < 1:
                                        continue

                                    max_contracts = fetch_exchange_max_contracts(symbol, side)
                                    if candidate_size > max_contracts:
                                        print(
                                            f"[{strategy_name}] {symbol}: {candidate_size} contracts exceed "
                                            f"OKX max {int(max_contracts)} at {lev}x; trying lower leverage."
                                        )
                                        continue

                                    actual_leverage = lev
                                    sizing_plan = candidate_plan
                                    margin_usdt = candidate_plan['margin_usdt']
                                    target_notional = candidate_notional
                                    size = candidate_size
                                    break

                                if actual_leverage is None or sizing_plan is None or size < 1:
                                    print(f"[{strategy_name}] Skip {symbol}: no leverage fits OKX contract limits.")
                                    continue

                                signal_obj['sizing_plan'] = sizing_plan
                                signal_obj['planned_margin'] = margin_usdt
                                signal_obj['planned_notional'] = target_notional
                                signal_obj['planned_leverage'] = actual_leverage
                                signal_obj['max_planned_loss_usdt'] = config.MAX_PLANNED_LOSS_USDT
                                signal_obj['market_quality'] = market_quality

                                actual_order_notional = size * current_price * contract_size
                                actual_order_margin = actual_order_notional / max(actual_leverage, 1)
                                edge_check = expected_trade_edge(
                                    actual_order_notional,
                                    as_float(plan.get('tp_dist_pct')),
                                    market_quality,
                                )
                                signal_obj['expected_edge'] = edge_check
                                if not edge_check['passes']:
                                    signal_obj['block_reason'] = (
                                        f"target gross {edge_check['gross_target_usdt']:.2f}U cannot cover "
                                        f"estimated cost and {config.MIN_EXPECTED_NET_PROFIT_USDT:.2f}U net edge"
                                    )
                                    current_potentials.append(signal_obj)
                                    continue
                                available_usdt = as_float(state.account_data.get('usdtAvail'))
                                if available_usdt <= 0 or actual_order_margin > available_usdt * 0.95:
                                    print(
                                        f"[{strategy_name}] Skip {symbol}: actual margin {actual_order_margin:.2f}U "
                                        f"exceeds available {available_usdt:.2f}U"
                                    )
                                    continue

                                with state.execution_state_lock:
                                    existing_active = next(
                                        (
                                            t for t in state.active_trades
                                            if t.get('status') == 'active'
                                            and normalize_symbol_key(t.get('symbol') or t.get('instId')) == normalize_symbol_key(display_sym)
                                        ),
                                        None,
                                    )
                                if existing_active:
                                    print(
                                        f"[{strategy_name}] Skip {symbol}: an existing net lifecycle is active; "
                                        "cross-mode add-on disabled."
                                    )
                                    continue
                                
                                # OKX clOrdId must be alphanumeric (1-32 chars)
                                cl_ord_id = f"H{strategy_name}{uuid.uuid4().hex[:8]}"
                                execution = execute_bounded_limit_entry(
                                    symbol,
                                    side,
                                    size,
                                    strategy_name,
                                    cl_ord_id,
                                    atr_pct,
                                )
                                if not execution:
                                    signal_obj['block_reason'] = 'bounded limit not filled; retry on next scan'
                                    signal_obj['execution_mode'] = 'limit_waiting'
                                    current_potentials.append(signal_obj)
                                    print(f"[{strategy_name}] {symbol} bounded limit not filled; no market chase.")
                                    continue

                                filled_size = execution['filled']
                                fill_price = execution['average']
                                direction = signal_obj['direction']
                                plan = rebase_plan_to_fill(plan, current_price, fill_price, direction)
                                sl_valid = plan['sl'] < fill_price if direction == 'long' else plan['sl'] > fill_price
                                tp_valid = plan['tp1'] > fill_price if direction == 'long' else plan['tp1'] < fill_price
                                if not sl_valid or not tp_valid:
                                    raise ValueError(
                                        f"Fill-rebased protection invalid: fill={fill_price}, SL={plan['sl']}, TP={plan['tp1']}"
                                    )

                                try:
                                    protection = place_exact_fill_protection(
                                        symbol,
                                        direction,
                                        filled_size,
                                        plan,
                                        cl_ord_id,
                                    )
                                except Exception as protection_exc:
                                    print(f"[{strategy_name}] Protection placement failed on {symbol}: {protection_exc}")
                                    try:
                                        emergency_close_unprotected(symbol, direction, filled_size)
                                        print(f"[{strategy_name}] Emergency close succeeded after protection exception.")
                                    except Exception as emergency_err:
                                        print(f"[{strategy_name}] URGENT: emergency close failed: {emergency_err}")
                                    continue
                                protection_failed, protection_code, protection_message = okx_order_failed(protection)
                                if protection_failed:
                                    print(
                                        f"[{strategy_name}] Protection rejected on {symbol}: "
                                        f"code={protection_code}, msg={protection_message}"
                                    )
                                    try:
                                        emergency_close_unprotected(symbol, direction, filled_size)
                                        print(f"[{strategy_name}] Emergency close succeeded after protection rejection.")
                                    except Exception as emergency_err:
                                        print(f"[{strategy_name}] URGENT: emergency close failed: {emergency_err}")
                                    continue
                                protection_confirmed = True

                                actual_order_notional = filled_size * fill_price * float(contract_size)
                                signal_obj.update({
                                    'entry': fill_price,
                                    'current': fill_price,
                                    'sl': plan['sl'],
                                    'tp1': plan['tp1'],
                                    'original_tp_dist': abs(plan['tp1'] - fill_price),
                                    'original_sl_dist': abs(fill_price - plan['sl']),
                                    'sl_dist_pct': plan['sl_dist_pct'],
                                    'tp_dist_pct': plan['tp_dist_pct'],
                                    'cost_safe_stop': fee_safe_stop_price(fill_price, direction),
                                    'filled_contracts': filled_size,
                                    'entry_order_type': execution['execution'],
                                    'entry_limit_price': execution['limit_price'],
                                    'entry_max_slippage_pct': round(execution['max_slippage'] * 100, 4),
                                    'entry_spread_pct': round(execution.get('spread_pct', 0.0) * 100, 4),
                                    'protection_order_id': protection.get('id'),
                                    'protection_order_ids': [str(protection.get('id'))] if protection.get('id') else [],
                                    'protection_status': 'confirmed',
                                    'tp_order_type': 'limit',
                                    'sl_order_type': 'market',
                                })
                                print(
                                    f"DEMO LIMIT EXECUTED: {side} {filled_size} contracts of {symbol} "
                                    f"@ {fill_price} ({execution['execution']}, notional ~${int(actual_order_notional)})"
                                )
                                
                                signal_obj["status"] = "active"
                                signal_obj["entry_reason"] = f"觸發 {p.pattern_name} (指標共振/趨勢吻合)"
                                signal_obj["entry_reason"] = (
                                    f"{mode_reason}; {execution['execution']} fill {fill_price}; "
                                    f"{plan.get('exit_model')}; margin {margin_usdt}U at {actual_leverage}x"
                                )
                                with state.execution_state_lock:
                                    state.global_symbol_cooldowns[cooldown_key] = time.time()
                                    state.global_executed_signal_candles[signal_key] = signal_candle
                                    state.active_trades.append(signal_obj)
                                    if len(state.active_trades) > 1000:
                                        state.active_trades = state.active_trades[-1000:]
                                    write_json_atomic(config.TRADE_FILE, state.active_trades)
                                    state.trade_id_counter += 1
                                print(f"SIGNAL GENERATED: {display_sym} {p.direction.upper()} {p.pattern_name} @ {plan['entry']}")

                            except Exception as ex:
                                print(f"Demo Execution Error: {ex}")
                                if filled_size > 0 and not protection_confirmed:
                                    try:
                                        emergency_close_unprotected(
                                            symbol,
                                            signal_obj['direction'],
                                            filled_size,
                                        )
                                        print(f"[{strategy_name}] Emergency close succeeded after execution exception.")
                                    except Exception as emergency_err:
                                        print(f"[{strategy_name}] URGENT: emergency close failed: {emergency_err}")
                            finally:
                                release_symbol_reservation(reservation_key)
                        else:
                            # It's a potential setup waiting for PRZ or Trend alignment
                            current_potentials.append(signal_obj)
                            
                    # Network calls are already serialized and throttled in fetch_data.
                    time.sleep(0.08)
                except Exception as e:
                    print(f"Error scanning {symbol}: {e}")
                    time.sleep(1)
            
            # Merge potentials safely
            state.potential_signals = [s for s in state.potential_signals if s.get('strategy') != strategy_name] + current_potentials
            
            # Merge radar safely into the dict
            state.market_radar_dict[strategy_name] = current_radar

            # Update ML evolution logs dynamically for frontend visibility
            time_str = datetime.datetime.now().strftime('%H:%M:%S')
            log_msg = f"[{time_str}] [{strategy_name}] AI 學習控制台：已掃描全市場 {len(symbols)} 個標的，當前狀態為 {state.market_radar_dict[strategy_name][0].get('trigger_reason', '探測中') if state.market_radar_dict[strategy_name] else '無可用信號'}"
            if not any(strategy_name in item and "AI 學習控制台" in item for item in state.ml_evolution_logs[-8:]):
                state.ml_evolution_logs.append(log_msg)
                if len(state.ml_evolution_logs) > 60:
                    state.ml_evolution_logs = state.ml_evolution_logs[-60:]
            
            # Wait before next full market scan
            time.sleep(60)
        except Exception as e:
            print(f"Error in main bot loop: {e}")
            time.sleep(10)

def background_sync_loop():
    while True:
        try:
            # 1. Sync Account Balance
            new_account_data = fetch_okx_account_snapshot(force=True)
            if new_account_data:
                new_account_data['capital'] = capital_snapshot()
                state.account_data = new_account_data
            elif state.account_data:
                state.account_data['capital'] = capital_snapshot()

            # 2. Sync Active Positions & Clear Closed Trades
            try:
                positions = fetch_open_positions_snapshot(force=True)
                cycle_history = None
                for t in state.active_trades:
                    if t['status'] == 'active':
                        def get_base_ccy(sym):
                            return sym.replace('/', '').replace(':USDT', '').replace('-USDT', '').replace('USDT', '').upper()
                        pos = next((p for p in positions if get_base_ccy(p['symbol']) == get_base_ccy(t['symbol']) and ('long' if p['side'] in ['long', 'buy'] else 'short') == ('long' if t['direction'] in ['long', 'buy'] else 'short')), None)
                        if pos:
                            t['current'] = float(pos['markPrice'])
                            if pos.get('entryPrice'):
                                t['entry'] = float(pos['entryPrice']) # CRITICAL: Use the REAL exchange fill price, not theoretical signal price
                            t['posId'] = pos.get('id')
                            t['instId'] = pos.get('info', {}).get('instId', '')
                            t['pnl'] = float(pos.get('unrealizedPnl', 0.0))
                            t['percentage'] = float(pos.get('percentage', 0.0))
                            t['leverage'] = pos.get('leverage')
                            t['initialMargin'] = pos.get('initialMargin')
                            t['notional'] = pos.get('notional')
                            t['liquidationPrice'] = pos.get('liquidationPrice')
                            t['marginRatio'] = pos.get('marginRatio')
                        else:
                            if cycle_history is None:
                                cycle_history = sync_exchange_history(force=True)
                            pos_id = str(t.get('posId') or '')
                            lifecycle_id = str(t.get('lifecycle_id') or '')
                            actual_close = next(
                                (
                                    h for h in cycle_history
                                    if lifecycle_id and str(h.get('lifecycle_id') or '') == lifecycle_id
                                ),
                                None,
                            )
                            if actual_close is None:
                                actual_close = next(
                                    (h for h in cycle_history if str(h.get('posId') or '') == pos_id),
                                    None,
                                )
                            if actual_close is None:
                                t['sync_status'] = 'awaiting exact OKX close lifecycle'
                                continue
                            if actual_close:
                                t['pnl'] = as_float(actual_close.get('realizedPnl'))
                                t['realized_pnl'] = t['pnl']
                                t['fee'] = as_float(actual_close.get('fee'))
                                t['funding_fee'] = as_float(actual_close.get('fundingFee'))
                                t['close_price'] = actual_close.get('closePrice')
                                t['gross_price_pnl'] = round(
                                    t['realized_pnl'] - t['fee'] - t['funding_fee'],
                                    8,
                                )
                                t['exit_reason'] = infer_exit_reason(t, t['close_price'])
                                t['closed_at'] = actual_close.get('lastUpdateTimestamp') or actual_close.get('timestamp')
                                t['close_event_key'] = actual_close.get('close_event_key') or history_event_key(actual_close)
                                t['pnl_source'] = 'okx_realized'
                                t['accounting_status'] = actual_close.get('accounting_status')
                                t['eligible_for_learning'] = actual_close.get('eligible_for_learning') is True
                                t['accounting_reasons'] = actual_close.get('accounting_reasons') or []
                            t['status'] = 'closed'
                            already_recorded = any(
                                row.get('close_event_key') and row.get('close_event_key') == t.get('close_event_key')
                                for row in state.trade_journal
                            )
                            if not already_recorded:
                                state.trade_journal.append(dict(t))
                            
                # Cleanup and Save
                if any(t['status'] == 'closed' for t in state.active_trades):
                    state.active_trades = [t for t in state.active_trades if t['status'] != 'closed']
                    write_json_atomic(config.JOURNAL_FILE, state.trade_journal)
                            
                for pos in positions:
                    # Normalize symbol formats (e.g. LAB-USDT-SWAP -> LABUSDT) to match active strategy trades
                    def get_base_ccy(s):
                        return s.replace('/', '').replace(':USDT', '').replace('-USDT', '').replace('USDT', '').replace('-SWAP', '').upper()
                    sym = get_base_ccy(pos['symbol']) + "USDT"
                    direction = pos.get('side', 'long')
                    exists = any(get_base_ccy(t['symbol']) == get_base_ccy(sym) and t['direction'] == direction and t['status'] == 'active' for t in state.active_trades)
                    if not exists:
                        state.active_trades.append({
                            "id": state.trade_id_counter, "posId": pos.get('id'), "instId": pos.get('info', {}).get('instId', ''),
                            "symbol": sym, "direction": direction, "pattern": "Manual / Unsynced", "status": "active",
                            "entry": float(pos.get('entryPrice', 0)), "current": float(pos['markPrice']), "sl": 0, "tp1": 0,
                            "pnl": float(pos.get('unrealizedPnl', 0.0)), "percentage": float(pos.get('percentage', 0.0)),
                            "rsi_on_entry": '--', "trends": {}, "strategy": "Manual", "leverage": pos.get('leverage'),
                            "initialMargin": pos.get('initialMargin'), "notional": pos.get('notional'),
                            "liquidationPrice": pos.get('liquidationPrice'), "marginRatio": pos.get('marginRatio')
                        })
                        state.trade_id_counter += 1

                state.active_trades = collapse_active_records(state.active_trades)

                # 3. Sync Algo Orders (TP/SL)
                oco_res = okx.private_get_trade_orders_algo_pending({'instType':'SWAP', 'ordType': 'oco'})
                cond_res = okx.private_get_trade_orders_algo_pending({'instType':'SWAP', 'ordType': 'conditional'})
                all_algos = []
                if oco_res and oco_res.get('code') == '0': all_algos.extend(oco_res.get('data', []))
                if cond_res and cond_res.get('code') == '0': all_algos.extend(cond_res.get('data', []))

                for t in state.active_trades:
                    if t['status'] == 'active':
                        expected_inst_id = t.get('instId') or (normalize_symbol_key(t['symbol']).replace('USDT', '') + "-USDT-SWAP")
                        expected_side = 'sell' if t['direction'] == 'long' else 'buy'
                        tracked_algo_ids = set(str(x) for x in (t.get('protection_order_ids') or []) if x)
                        if t.get('protection_order_id'):
                            tracked_algo_ids.add(str(t['protection_order_id']))
                        candidate_algos = [
                            a for a in all_algos
                            if a.get('instId') == expected_inst_id and a.get('side') == expected_side
                            and (
                                not tracked_algo_ids
                                or str(a.get('algoId') or '') in tracked_algo_ids
                                or str((a.get('linkedAlgoOrd') or {}).get('algoId') or '') in tracked_algo_ids
                            )
                        ]
                        protective_algos = protective_algo_targets(
                            all_algos, expected_inst_id, expected_side, tracked_algo_ids
                        )
                        for a in protective_algos:
                            if as_float(a.get('slTriggerPx')) > 0: t['sl'] = float(a['slTriggerPx'])
                        for a in candidate_algos:
                            if a.get('tpTriggerPx') and float(a['tpTriggerPx']) > 0: t['tp1'] = float(a['tpTriggerPx'])

                        if protective_algos:
                            t['missing_protection_checks'] = 0
                        elif t.get('strategy_version') == config.STRATEGY_VERSION and t.get('strategy') != 'Manual':
                            missing_checks = int(t.get('missing_protection_checks') or 0) + 1
                            t['missing_protection_checks'] = missing_checks
                            t['protection_status'] = 'failed'
                            t['protection_error'] = 'OKX has no matching protective SL order'
                            if missing_checks >= config.PROTECTION_MISSING_CONFIRMATIONS and not t.get('emergency_close_submitted'):
                                open_pos = next(
                                    (
                                        p for p in positions
                                        if str((p.get('info') or {}).get('instId') or '') == expected_inst_id
                                    ),
                                    None,
                                )
                                close_size = as_float((open_pos or {}).get('contracts'))
                                if close_size <= 0:
                                    close_size = as_float(t.get('filled_contracts'))
                                if close_size > 0:
                                    try:
                                        ccxt_sym = f"{normalize_symbol_key(t['symbol']).replace('USDT', '')}/USDT:USDT"
                                        emergency_close_unprotected(ccxt_sym, t['direction'], close_size)
                                        t['emergency_close_submitted'] = True
                                        t['protection_status'] = 'emergency_close_submitted'
                                        print(f"[URGENT] {t['symbol']} had no SL for {missing_checks} checks; emergency close submitted.")
                                    except Exception as emergency_err:
                                        t['protection_error'] = f"missing SL; emergency close failed: {emergency_err}"
                                        print(f"[URGENT] {t['symbol']} emergency close failed: {emergency_err}")
                        
                        # Fix: Fetch real-time price inside background loop to avoid stale t['current'] values
                        try:
                            ccxt_sym = f"{normalize_symbol_key(t['symbol']).replace('USDT', '')}/USDT:USDT"
                            ticker = okx.fetch_ticker(ccxt_sym)
                            t['current'] = float(ticker.get('last', t['current']))
                        except Exception as p_err:
                            print(f"[Warning] Failed to fetch current price for {t['symbol']}: {p_err}")

                        fee_safe_stop = fee_safe_stop_price(
                            as_float(t.get('entry')),
                            t.get('direction'),
                        )
                        stop_is_locked = (
                            (t.get('direction') == 'long' and as_float(t.get('sl')) >= fee_safe_stop)
                            or (t.get('direction') == 'short' and 0 < as_float(t.get('sl')) <= fee_safe_stop)
                        )
                        if stop_is_locked:
                            t['protection_status'] = 'confirmed'
                        
                        # 🏃 DYNAMIC TRAILING STOP MECHANISM (動態追蹤止盈)
                        if t.get('tp1') and t.get('sl') and t.get('entry'):
                            raw_strat = t.get('strategy', 'SqueezeHunter')
                            strat_lookup = 'SqueezeHunter' if raw_strat not in ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'] else raw_strat
                            runtime_optimizer = auto_tune_strategy_params(strat_lookup)
                            runner_prof = tuned_runner_profile(strat_lookup, runtime_optimizer)
                            t['optimizer'] = runtime_optimizer
                            t['runner_policy'] = runner_policy_text(runner_prof)

                            # Original theoretical distance to TP1
                            if 'original_tp_dist' not in t:
                                t['original_tp_dist'] = abs(t['tp1'] - t['entry'])
                            if 'original_sl_dist' not in t or not t.get('original_sl_dist'):
                                t['original_sl_dist'] = abs(t['entry'] - t['sl'])
                            
                            total_dist = t['original_tp_dist']
                            current_dist = abs(t['current'] - t['entry'])
                            is_profitable = (t['direction'] == 'long' and t['current'] > t['entry']) or (t['direction'] == 'short' and t['current'] < t['entry'])
                            risk_dist = float(t.get('original_sl_dist') or abs(t['entry'] - t['sl']) or 0)
                            favorable_move = (t['current'] - t['entry']) if t['direction'] == 'long' else (t['entry'] - t['current'])
                            t['current_r'] = round(favorable_move / risk_dist, 3) if risk_dist > 0 else 0

                            if not is_profitable and as_float(t.get('highest_r')) >= config.MFE_BE_R and not stop_is_locked:
                                t['trailing_stage'] = 'missed_be_lock'
                            
                            if is_profitable and total_dist > 0:
                                progress = current_dist / total_dist
                                
                                # Track High Water Mark (Highest progress reached)
                                highest_progress = t.get('highest_progress', 0.0)
                                if progress > highest_progress:
                                    t['highest_progress'] = progress
                                    highest_progress = progress
                                
                                new_sl = None
                                remove_tp = False
                                desired_stage = t.get('trailing_stage') or 'waiting'
                                
                                be_threshold = runner_prof['be_threshold']
                                lock_threshold = runner_prof['lock_threshold']
                                trail_buffer = runner_prof['trail_buffer']
                                remove_tp_at = runner_prof['remove_tp_at']
                                fee_safe_stop = fee_safe_stop_price(t['entry'], t['direction'])
                                cost_distance = abs(fee_safe_stop - t['entry'])
                                cost_progress = cost_distance / total_dist if total_dist > 0 else 1.0
                                be_threshold = max(be_threshold, cost_progress * 1.20)
                                lock_threshold = max(lock_threshold, be_threshold + 0.10)
                                cost_covered_now = favorable_move > cost_distance + abs(t['current']) * 0.0002
                                r_now = favorable_move / risk_dist if risk_dist > 0 else 0
                                t['current_r'] = round(r_now, 3)
                                highest_r = max(float(t.get('highest_r') or 0), r_now)
                                t['highest_r'] = round(highest_r, 3)
                                t['highest_pnl'] = round(max(float(t.get('highest_pnl') or 0), float(t.get('pnl') or 0)), 4)

                                lock_r = None
                                if highest_r >= config.MFE_RUNNER_R:
                                    lock_r = max(config.MFE_LOCK_FRACTION, highest_r - config.MFE_TRAIL_GIVEBACK_R)
                                    desired_stage = 'mfe_runner_lock'
                                elif highest_r >= config.MFE_LOCK_R:
                                    lock_r = config.MFE_LOCK_FRACTION
                                    desired_stage = 'mfe_profit_lock'
                                elif highest_r >= config.MFE_BE_R:
                                    lock_r = config.MFE_BE_LOCK_R
                                    desired_stage = 'mfe_break_even'

                                if lock_r is not None and risk_dist > 0 and cost_covered_now:
                                    if t['direction'] == 'long':
                                        new_sl = max(new_sl or -float('inf'), t['entry'] + risk_dist * lock_r, fee_safe_stop)
                                    else:
                                        new_sl = min(new_sl or float('inf'), t['entry'] - risk_dist * lock_r, fee_safe_stop)

                                if lock_r is None and cost_covered_now and highest_progress >= be_threshold and highest_progress < lock_threshold:
                                    if t['direction'] == 'long':
                                        new_sl = max(new_sl or -float('inf'), fee_safe_stop)
                                    else:
                                        new_sl = min(new_sl or float('inf'), fee_safe_stop)
                                    desired_stage = 'cost_safe_break_even'
                                     
                                elif cost_covered_now and highest_progress >= lock_threshold:
                                    locked_progress = max(0.0, highest_progress - trail_buffer)
                                     
                                    if t['direction'] == 'long':
                                        new_sl = max(new_sl or -float('inf'), t['entry'] + (total_dist * locked_progress), fee_safe_stop)
                                    else:
                                        new_sl = min(new_sl or float('inf'), t['entry'] - (total_dist * locked_progress), fee_safe_stop)
                                    
                                    desired_stage = 'runner'
                                    remove_tp = highest_progress >= remove_tp_at
                                t['runner_policy'] = runner_policy_text(runner_prof)

                                # APPLY CHANGES TO OKX
                                if new_sl:
                                    trigger_guard = max(abs(t['current']) * 0.0015, 1e-10)
                                    if t['direction'] == 'long' and new_sl >= t['current']:
                                        new_sl = t['current'] - trigger_guard
                                    elif t['direction'] == 'short' and new_sl <= t['current']:
                                        new_sl = t['current'] + trigger_guard

                                    # Only update if the new_sl is strictly BETTER than the current SL
                                    is_better_sl = (t['direction'] == 'long' and new_sl > t['sl']) or (t['direction'] == 'short' and new_sl < t['sl'])
                                    
                                    # Allow 0.05% margin for floating point comparison
                                    sl_diff_pct = abs(t['sl'] - new_sl) / t['entry']
                                    
                                    if is_better_sl and sl_diff_pct > 0.0005:
                                        retry_after = as_float(t.get('protection_retry_after'))
                                        if retry_after > time.time():
                                            continue
                                        for a in protective_algos:
                                            try:
                                                ccxt_sym = f"{normalize_symbol_key(t['symbol']).replace('USDT', '')}/USDT:USDT"
                                                formatted_sl = okx.price_to_precision(ccxt_sym, new_sl)
                                                
                                                # Avoid redundant API calls if string format matches existing OKX order
                                                if formatted_sl == str(a.get('slTriggerPx')):
                                                    t['trailing_stage'] = desired_stage
                                                    t['protection_status'] = 'confirmed'
                                                    t['protection_error'] = None
                                                    break
                                                    
                                                tp_update = None
                                                if remove_tp and not t.get('tp_removed'):
                                                    if t['direction'] == 'long':
                                                        far_tp = t['entry'] + (total_dist * 3.0)
                                                    else:
                                                        far_tp = max(0.0001, t['entry'] - (total_dist * 3.0))
                                                    formatted_far_tp = okx.price_to_precision(ccxt_sym, far_tp)
                                                    if a.get('tp_limit_linked'):
                                                        t['tp_extension_status'] = 'kept_limit_tp_for_linked_oco_safety'
                                                    else:
                                                        tp_update = {
                                                            'newTpTriggerPx': formatted_far_tp,
                                                            'newTpOrdPx': '-1',
                                                        }

                                                res, failed, code, message = amend_protective_stop(
                                                    a, formatted_sl, tp_update
                                                )
                                                # 51119 = Order amend details cannot be same
                                                if failed and str(code) == '51119':
                                                    failed = False
                                                
                                                if not failed:
                                                    print(f"[🛡️ TRAILING STOP] {t['symbol']} SL moved to: {formatted_sl} (Progress: {highest_progress*100:.1f}%)")
                                                    t['sl'] = float(formatted_sl)
                                                    t['trailing_stage'] = desired_stage
                                                    t['protection_status'] = 'confirmed'
                                                    t['protection_error'] = None
                                                    t['protection_retry_count'] = 0
                                                    t['protection_retry_after'] = 0
                                                    if tp_update:
                                                        t['tp_removed'] = True
                                                        print(f"[🚀 INFINITE RUN] {t['symbol']} TP ceiling extended after confirmed amend.")
                                                    break
                                                else:
                                                    failures = int(t.get('protection_retry_count') or 0) + 1
                                                    t['trailing_stage'] = 'protection_failed'
                                                    t['protection_status'] = 'failed'
                                                    t['protection_retry_count'] = failures
                                                    t['protection_retry_after'] = time.time() + protection_retry_delay(failures)
                                                    t['protection_error'] = f"{code}: {message}"
                                                    print(f"[ERROR] Amend failed for {t['symbol']}: code={code}, msg={message}")
                                            except Exception as e:
                                                failures = int(t.get('protection_retry_count') or 0) + 1
                                                t['trailing_stage'] = 'protection_failed'
                                                t['protection_status'] = 'failed'
                                                t['protection_retry_count'] = failures
                                                t['protection_retry_after'] = time.time() + protection_retry_delay(failures)
                                                t['protection_error'] = str(e)
                                                print(f"[ERROR] Failed to trail stop for {t['symbol']}: {e}")
                # Save the persisted state so we don't lose UI metadata on restart
                write_json_atomic(config.TRADE_FILE, state.active_trades)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(3)

