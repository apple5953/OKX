import math
import time
import pandas as pd
from . import config
from . import state
from .utils import as_float, clamp
from types import SimpleNamespace

def strategy_profile(strategy_name):
    return config.STRATEGY_PROFILES.get(strategy_name, config.STRATEGY_PROFILES['SqueezeHunter'])

def category_profile(category):
    for key, profile in config.CATEGORY_PROFILES.items():
        if key != 'Default' and key in str(category):
            return key, profile
    return 'Default', config.CATEGORY_PROFILES['Default']

def category_has_keyword(category, keyword):
    if not category or not keyword:
        return False
    return keyword.lower() in str(category).lower()

def strategy_category_permission(strategy_name, category, perf=None):
    # MeanReversion, Contrarian can trade Squeeze/Oversold/Volatility/Majors.
    # MacroSniper can trade Majors/Alpha/Volatility/Squeeze.
    # SqueezeHunter only trades Squeeze and Alpha.
    cat_lower = str(category or '').lower()
    if strategy_name == 'SqueezeHunter':
        allowed = any(kw in cat_lower for kw in ['squeeze', 'alpha', '費率', '獨立'])
        return allowed, "SqueezeHunter restricted to Squeeze/Alpha categories" if not allowed else (True, '')
    
    if strategy_name == 'MacroSniper':
        allowed = not any(kw in cat_lower for kw in ['oversold', '超跌'])
        return allowed, "MacroSniper restricted from Oversold category" if not allowed else (True, '')
        
    return True, ''

def squeeze_hunter_release_ready(df, sample=0):
    if df.empty or len(df) < 5:
        return False
    # Volatility Squeeze release: bb_width expanding, was squeezed recently
    last = df.iloc[-1]
    prev = df.iloc[-2]
    was_squeezed = any(df.tail(8)['is_squeezed'])
    is_expanding = last['bb_width'] > prev['bb_width']
    return was_squeezed and is_expanding

def version_matches_strategy_scope(row_version):
    if not row_version:
        return True
    return str(row_version) == config.STRATEGY_VERSION

def recent_strategy_stats(strategy_name, category=None, limit=40):
    from .okx_client import sync_exchange_history
    history = sync_exchange_history()
    rows = []
    seen = set()
    for row in reversed(history):
        if row.get('strategy') != strategy_name:
            continue
        if category and row.get('category') != category:
            continue
        if version_matches_strategy_scope(row.get('strategy_version')):
            key = (row.get('posId'), row.get('close_event_key'))
            if key not in seen:
                rows.append(row)
                seen.add(key)
    # Fallback to journal
    if len(rows) < 10:
        for row in reversed(state.trade_journal):
            if row.get('strategy') == strategy_name and row.get('status') == 'closed':
                if category and row.get('category') != category:
                    continue
                if not row.get('strategy_version') or version_matches_strategy_scope(row.get('strategy_version')):
                    key = (row.get('posId'), row.get('close_event_key') or row.get('closed_at'))
                    if key not in seen:
                        rows.append(row)
                        seen.add(key)
    return rows[:limit]

def strategy_performance(strategy_name, limit=120):
    from .okx_client import realized_strategy_rows
    rows = realized_strategy_rows(strategy_name, limit)
    total_trades = len(rows)
    if total_trades == 0:
        return {
            'strategy': strategy_name, 'total_trades': 0, 'win_rate': 0.0,
            'profit_factor': 0.0, 'expectancy': 0.0, 'total_pnl': 0.0,
            'max_drawdown': 0.0, 'tier': 'D (Training/Explore)', 'state': 'explore',
            'net_wins': 0, 'funding_excluded': True, 'win_count': 0, 'loss_count': 0
        }
    
    wins = [as_float(r.get('alphaPnl', r.get('realizedPnl'))) for r in rows if as_float(r.get('alphaPnl', r.get('realizedPnl'))) > 0]
    losses = [as_float(r.get('alphaPnl', r.get('realizedPnl'))) for r in rows if as_float(r.get('alphaPnl', r.get('realizedPnl'))) <= 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0
    
    total_win = sum(wins)
    total_loss = abs(sum(losses))
    profit_factor = total_win / total_loss if total_loss > 0 else (total_win if total_win > 0 else 0.0)
    
    total_pnl = sum(as_float(r.get('alphaPnl', r.get('realizedPnl'))) for r in rows)
    expectancy = total_pnl / total_trades
    
    # Drawdown calculation
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rows:
        cum_pnl += as_float(r.get('alphaPnl', r.get('realizedPnl')))
        if cum_pnl > peak: peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd: max_dd = dd

    # Sizing tier
    pf = profit_factor
    trades = total_trades
    
    if trades >= config.CORE_TRADE_MIN_SAMPLE and pf >= 1.25 and expectancy > 0.5:
        tier = 'S (Confidence Exploit)'
        state_verdict = 'exploit'
    elif trades >= 15 and pf >= 1.08 and expectancy >= 0.0:
        tier = 'A (Steady Accumulate)'
        state_verdict = 'steady'
    elif trades >= 8 and pf >= 0.90:
        tier = 'B (Recovery Phase)'
        state_verdict = 'recover'
    else:
        tier = 'D (Training/Explore)'
        state_verdict = 'explore'
        
    return {
        'strategy': strategy_name, 'total_trades': total_trades, 'win_rate': round(win_rate, 2),
        'profit_factor': round(profit_factor, 3), 'expectancy': round(expectancy, 4),
        'total_pnl': round(total_pnl, 4), 'max_drawdown': round(max_dd, 4),
        'tier': tier, 'state': state_verdict, 'net_wins': win_count - loss_count,
        'funding_excluded': True, 'win_count': win_count, 'loss_count': loss_count
    }

def all_strategy_performance():
    return {name: strategy_performance(name) for name in ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter']}

def auto_tune_strategy_params(strategy_name, perf=None):
    import json, os
    if os.path.exists('global_optimizer.json'):
        try:
            with open('global_optimizer.json', 'r', encoding='utf-8') as gf:
                global_data = json.load(gf)
            if isinstance(global_data, dict) and strategy_name in global_data:
                opt = dict(global_data[strategy_name])
                # Ensure compatibility keys are present
                opt['tolerance_mult'] = opt.get('tolerance_mult', 1.0)
                opt['min_profit_mult'] = opt.get('min_profit_mult', opt.get('profit_mult', 1.0))
                opt['target_rr_mult'] = opt.get('target_rr_mult', opt.get('rr_mult', 1.0))
                return opt
        except Exception:
            pass

    if perf is None:
        perf = strategy_performance(strategy_name)
    
    state_verdict = perf['state']
    pf = perf['profit_factor']
    trades = perf['total_trades']
    
    tuned_sl_atr = None
    
    if state_verdict == 'exploit':
        rr_mult = 1.15
        profit_mult = 1.20
        cooldown_mult = 0.60
    elif state_verdict == 'steady':
        rr_mult = 1.0
        profit_mult = 1.0
        cooldown_mult = 1.0
    elif state_verdict == 'recover':
        rr_mult = 1.0
        profit_mult = config.REHAB_PROFIT_MULTIPLIER
        cooldown_mult = 1.20
        if pf < 0.90 and trades >= 10:
            tuned_sl_atr = strategy_profile(strategy_name)['sl_atr'] * 1.10
    else: # explore / rehab
        rr_mult = config.REHAB_RR_MULTIPLIER
        profit_mult = config.REHAB_PROFIT_MULTIPLIER
        cooldown_mult = 1.50
        if pf < 0.85 and trades >= 6:
            tuned_sl_atr = strategy_profile(strategy_name)['sl_atr'] * 1.20

    return {
        'strategy': strategy_name,
        'state': state_verdict,
        'rr_mult': rr_mult,
        'profit_mult': profit_mult,
        'cooldown_mult': cooldown_mult,
        'tuned_sl_atr': round(tuned_sl_atr, 3) if tuned_sl_atr else None,
        'profit_factor': pf,
        'sample_size': trades,
        'tolerance_mult': 1.0,
        'min_profit_mult': profit_mult,
        'target_rr_mult': rr_mult,
    }

def performance_block_reason(strategy_name):
    perf = strategy_performance(strategy_name)
    if perf['total_trades'] >= config.CORE_TRADE_MIN_SAMPLE:
        if perf['profit_factor'] < config.CORE_TRADE_MIN_PROFIT_FACTOR or perf['expectancy'] < config.CORE_TRADE_MIN_EXPECTANCY:
            return f"blocked: pf={perf['profit_factor']} < {config.CORE_TRADE_MIN_PROFIT_FACTOR} or expectancy={perf['expectancy']} < {config.CORE_TRADE_MIN_EXPECTANCY}"
    return None

def apply_rehab_sizing_if_needed(sizing_plan, mode_verdict, leverage, optimizer=None):
    plan = dict(sizing_plan)
    state_verdict = mode_verdict
    if optimizer and optimizer.get('state'):
        state_verdict = optimizer['state']
        
    if mode_verdict == 'pause':
        plan['margin_usdt'] = 0.0
        plan['target_notional'] = 0.0
        plan['risk_rule'] = 'strategy execution paused by optimizer'
        return plan

    if state_verdict == 'explore':
        plan['margin_usdt'] = config.EXPLORE_MARGIN_USDT
        plan['target_notional'] = round(config.EXPLORE_MARGIN_USDT * leverage, 2)
        plan['risk_rule'] = 'explore mode restricts sizing to base minimum'
    elif state_verdict == 'recover':
        plan['margin_usdt'] = config.REHAB_MARGIN_USDT
        plan['target_notional'] = round(config.REHAB_MARGIN_USDT * leverage, 2)
        plan['risk_rule'] = 'recovery mode restricts sizing to protect equity'
    else:
        plan['risk_rule'] = 'winning/stable mode receives confidence-weighted capital'
        
    if mode_verdict == 'rehab':
        plan['margin_usdt'] = config.REHAB_MARGIN_USDT
        plan['target_notional'] = round(config.REHAB_MARGIN_USDT * leverage, 2)
        plan['risk_rule'] = 'optimizer mandated rehab (rebuilding equity safety)'
        plan['rehab_mode'] = True
    elif mode_verdict == 'firewall':
        plan['margin_usdt'] = config.LOSS_FIREWALL_MARGIN_USDT
        plan['target_notional'] = round(config.LOSS_FIREWALL_MARGIN_USDT * leverage, 2)
        plan['risk_rule'] = 'loss firewall triggered: minimum exposure allowed'
        
    return plan

def get_confidence_score(strategy_name, category):
    perf = strategy_performance(strategy_name)
    pf = perf['profit_factor']
    
    score = 1.0
    if pf > 1.40: score += 0.35
    elif pf > 1.20: score += 0.15
    elif pf < 0.90: score -= 0.25
    
    _, cat_prof = category_profile(category)
    score *= cat_prof['margin_mult']
    return clamp(score, 0.2, 2.5)

def build_sizing_plan(strategy_name, category, confidence, leverage, usdt_available=None):
    confidence_scale = 1.0 + max(0.0, confidence - 1.0) * 0.50
    target_margin = clamp(60.0 * confidence_scale, config.MIN_CONFIDENCE_MARGIN_USDT, config.MAX_CONFIDENCE_MARGIN_USDT)
    if usdt_available is not None:
        target_margin = min(target_margin, max(60.0, as_float(usdt_available) * 0.02))
    return {
        'base_margin': 60.0,
        'confidence': round(confidence, 3),
        'margin_usdt': round(target_margin, 2),
        'target_notional': round(target_margin * leverage, 2),
    }

def apply_exit_state_limits(strategy_name, state, sl_dist, tp_dist, current_price):
    limits = config.EXIT_STATE_LIMITS.get(strategy_name, {}).get(state)
    if not limits or current_price <= 0:
        return sl_dist, tp_dist, None
        
    min_sl_pct = config.MIN_EXIT_DISTANCE_PCT.get(strategy_name, 0.0035)
    sl_cap = limits['sl_cap']
    tp_cap = limits['tp_cap']
    rr_floor = limits['rr_floor']
    
    sl_pct = clamp(sl_dist / current_price, min_sl_pct, sl_cap)
    tp_pct = min(tp_dist / current_price, tp_cap)
    tp_pct = max(tp_pct, sl_pct * rr_floor)
    
    if tp_pct > tp_cap:
        sl_pct = max(min_sl_pct, min(sl_pct, tp_cap / rr_floor))
        tp_pct = tp_cap
        
    note = f"{state} exit clamp: SL {sl_pct*100:.2f}%, TP {tp_pct*100:.2f}%"
    return current_price * sl_pct, current_price * tp_pct, note

def tuned_runner_profile(strategy_name, optimizer=None):
    profile = dict(strategy_profile(strategy_name))
    if not optimizer:
        return profile
        
    profile['be_threshold'] = round(profile['be_threshold'] * optimizer['cooldown_mult'], 4)
    profile['lock_threshold'] = round(profile['lock_threshold'] * optimizer['cooldown_mult'], 4)
    profile['remove_tp_at'] = profile['remove_tp_at'] * optimizer['rr_mult']
    
    state_verdict = optimizer.get('state', 'steady')
    if state_verdict == 'explore':
        profile['remove_tp_at'] *= 1.10
    elif state_verdict == 'recover':
        profile['remove_tp_at'] *= 1.10
    elif state_verdict == 'exploit':
        profile['remove_tp_at'] *= 0.75
        
    profile['remove_tp_at'] = round(clamp(profile['remove_tp_at'], 0.50, 2.50), 4)
    return profile

def runner_policy_text(runner_prof):
    return (
        f"浮盈達 {int(runner_prof['be_threshold']*100)}% 成本保護，"
        f"{int(runner_prof['lock_threshold']*100)}% 鎖利，"
        f"達到 {int(runner_prof['remove_tp_at']*100)}% 獲利目標後，"
        f"撤銷限價單改為移動止損保護。"
    )

def fee_safe_stop_price(entry, direction, extra_rate=0.0):
    rate = config.FEE_SAFE_PROFIT_RATE + extra_rate
    if direction == 'long':
        return entry * (1.0 + rate)
    else:
        return entry * (1.0 - rate)

def apply_adaptive_exits(plan, strategy_name, current_price, direction, atr_pct, optimizer=None):
    profile = strategy_profile(strategy_name)
    effective_atr = clamp(atr_pct if atr_pct else 0.008, 0.005, 0.05)
    atr_abs = current_price * effective_atr
    sl_dist = max(atr_abs * profile['sl_atr'], current_price * 0.003)
    tp_dist = max(atr_abs * profile['tp_atr'], sl_dist * profile['min_rr'])
    structural_stop = as_float(plan.get('structural_stop'))
    stop_is_valid = structural_stop > 0 and (
        structural_stop < current_price if direction == 'bullish'
        else structural_stop > current_price
    )
    state_verdict = (optimizer or {}).get('state', 'steady')
    sl_dist, tp_dist, clamp_note = apply_exit_state_limits(strategy_name, state_verdict, sl_dist, tp_dist, current_price)
    if stop_is_valid:
        structural_sl_dist = clamp(abs(current_price - structural_stop), sl_dist, current_price * 0.025)
        sl_dist = max(sl_dist, structural_sl_dist)

    structural_target = as_float(plan.get('structural_target'))
    target_is_valid = (
        structural_target > current_price if direction == 'bullish'
        else 0 < structural_target < current_price
    )
    if structural_target > 0 and target_is_valid:
        structural_tp_dist = abs(structural_target - current_price)
        tp_dist = min(tp_dist, max(structural_tp_dist, sl_dist * 1.25))
    tp_dist = max(
        tp_dist,
        sl_dist * 1.25,
        current_price * config.MIN_TARGET_DISTANCE_PCT.get(strategy_name, 0.006),
    )

    if direction == 'bullish':
        plan['sl'] = current_price - sl_dist
        plan['tp1'] = current_price + tp_dist
    else:
        plan['sl'] = current_price + sl_dist
        plan['tp1'] = current_price - tp_dist

    risk = abs(current_price - plan['sl'])
    reward = abs(plan['tp1'] - current_price)
    plan['risk_reward'] = round(reward / risk, 2) if risk > 0 else 0
    plan['sl_dist_pct'] = round(risk / current_price, 5)
    plan['tp_dist_pct'] = round(reward / current_price, 5)
    plan['exit_state'] = state_verdict
    structure_label = 'structure + ATR' if structural_stop > 0 else 'ATR'
    plan['exit_model'] = f"{profile['label']}: {structure_label} SL, structure-aware TP, early cost-safe runner"
    if clamp_note:
        plan['exit_model'] = f"{plan['exit_model']}; {clamp_note}"
    return plan

def create_macro_trend_setup(df, trends, htf_bull, htf_bear):
    if df.empty or len(df) < 50:
        return None

    current = as_float(df['close'].iloc[-1])
    previous = df.iloc[-2]
    ema20 = as_float(df['ema50'].iloc[-1]) # EMA50 acts as macro anchor
    avg_range = as_float((df.tail(14)['high'] - df.tail(14)['low']).mean())

    trend_1h = trends.get('1h', 'neutral')
    trend_4h = trends.get('4h', 'neutral')
    
    is_bullish = trend_1h == 'bull' and trend_4h == 'bull' and htf_bull
    is_bearish = trend_1h == 'bear' and trend_4h == 'bear' and htf_bear

    if not is_bullish and not is_bearish:
        return None

    breakout = as_float(df['close'].iloc[-1]) > as_float(df['bb_upper'].iloc[-2]) if is_bullish else as_float(df['close'].iloc[-1]) < as_float(df['bb_lower'].iloc[-2])
    direction = 'bullish' if is_bullish else 'bearish'

    if direction == 'bullish':
        entry_reference = as_float(previous['high']) if breakout else ema20
        stop_reference = min(as_float(signal_low(df)), as_float(df.tail(5)['low'].min())) - avg_range * 0.10
        risk = max(current - stop_reference, avg_range * 0.70)
        target_reference = current + risk * 1.65
        name = 'Macro Trend Long'
    else:
        entry_reference = as_float(previous['low']) if breakout else ema20
        stop_reference = max(as_float(signal_high(df)), as_float(df.tail(5)['high'].max())) + avg_range * 0.10
        risk = max(stop_reference - current, avg_range * 0.70)
        target_reference = current - risk * 1.65
        name = 'Macro Trend Short'

    return build_direct_mode_setup(
        df, direction, name, entry_reference, stop_reference, target_reference,
        'closed breakout retest' if breakout else 'closed EMA50 pullback resume',
    )

def signal_low(df):
    return df['low'].iloc[-1]

def signal_high(df):
    return df['high'].iloc[-1]

def build_direct_mode_setup(
    df, direction, name, entry_reference=None, stop_reference=None,
    target_reference=None, setup_reason=None,
):
    current = as_float(df['close'].iloc[-1])
    recent = df.tail(40)
    last10 = df.tail(10)
    avg_range = as_float((df.tail(14)['high'] - df.tail(14)['low']).mean())
    entry_reference = as_float(entry_reference, current)
    prz_buffer = max(current * 0.0007, avg_range * 0.18)
    idx = len(df) - 1
    now = str(df['time'].iloc[-1])

    if direction == 'bullish':
        x_price = as_float(recent['low'].min())
        a_price = as_float(recent['high'].max())
        c_price = as_float(last10['low'].min())
        stop_reference = as_float(stop_reference, c_price - avg_range * 0.10)
        target_reference = as_float(target_reference, max(current, as_float(df['bb_mid'].iloc[-1])))
    else:
        x_price = as_float(recent['high'].max())
        a_price = as_float(recent['low'].min())
        c_price = as_float(last10['high'].max())
        stop_reference = as_float(stop_reference, c_price + avg_range * 0.10)
        target_reference = as_float(target_reference, min(current, as_float(df['bb_mid'].iloc[-1])))

    def point(price, offset=0):
        return SimpleNamespace(index=idx + offset, time=now, price=price, type='direct')

    return SimpleNamespace(
        pattern_name=name,
        direction=direction,
        x=point(x_price, -3),
        a=point(a_price, -2),
        b=point((x_price + a_price) / 2, -1),
        c=point(c_price),
        d=point(current, 1),
        prz_low=entry_reference - prz_buffer,
        prz_high=entry_reference + prz_buffer,
        prz_center=entry_reference,
        setup_source='mode_direct',
        stop_reference=stop_reference,
        target_reference=target_reference,
        setup_reason=setup_reason or 'closed-candle structure retest',
    )

def create_mode_direct_setup(strategy_name, df, trends, htf_bull, htf_bear):
    if df.empty or len(df) < 50:
        return None

    signal = df.iloc[-1]
    previous = df.iloc[-2]
    rsi = as_float(signal.get('rsi'), 50.0)
    avg_range = as_float((df.tail(14)['high'] - df.tail(14)['low']).mean())
    bull_reversal = signal['close'] > signal['open'] and signal['close'] > previous['close']
    bear_reversal = signal['close'] < signal['open'] and signal['close'] < previous['close']

    if strategy_name == 'MacroSniper':
        return create_macro_trend_setup(df, trends, htf_bull, htf_bear)

    if strategy_name == 'MeanReversion':
        lower_prev = as_float(df['bb_lower'].iloc[-2])
        lower_now = as_float(df['bb_lower'].iloc[-1])
        upper_prev = as_float(df['bb_upper'].iloc[-2])
        upper_now = as_float(df['bb_upper'].iloc[-1])
        long_reentry = previous['low'] <= lower_prev and signal['close'] > lower_now and bull_reversal and rsi < 45
        short_reentry = previous['high'] >= upper_prev and signal['close'] < upper_now and bear_reversal and rsi > 55
        if long_reentry:
            return build_direct_mode_setup(df, 'bullish', 'Mean BB Re-entry Long', lower_now, min(previous['low'], signal['low']) - avg_range * 0.15, df['bb_mid'].iloc[-1])
        elif short_reentry:
            return build_direct_mode_setup(df, 'bearish', 'Mean BB Re-entry Short', upper_now, max(previous['high'], signal['high']) + avg_range * 0.15, df['bb_mid'].iloc[-1])
        
        long_rsi_snap = rsi < 32 and bull_reversal
        short_rsi_snap = rsi > 68 and bear_reversal
        if long_rsi_snap:
            return build_direct_mode_setup(df, 'bullish', 'Mean RSI Snapback Long', (signal['open'] + signal['close'])/2, signal['low'] - avg_range * 0.20, df['bb_mid'].iloc[-1])
        elif short_rsi_snap:
            return build_direct_mode_setup(df, 'bearish', 'Mean RSI Snapback Short', (signal['open'] + signal['close'])/2, signal['high'] + avg_range * 0.20, df['bb_mid'].iloc[-1])

    if strategy_name == 'Contrarian':
        # Exhaustion proof: RSI and candle reversal at extreme levels
        oversold = rsi < 28
        overbought = rsi > 72
        if oversold and bull_reversal:
            return build_direct_mode_setup(df, 'bullish', 'Contrarian Reversal Long', signal['close'], signal['low'] - avg_range * 0.25, df['bb_mid'].iloc[-1])
        elif overbought and bear_reversal:
            return build_direct_mode_setup(df, 'bearish', 'Contrarian Reversal Short', signal['close'], signal['high'] + avg_range * 0.25, df['bb_mid'].iloc[-1])

    if strategy_name == 'SqueezeHunter':
        if squeeze_hunter_release_ready(df):
            # Directional squeeze breakout
            direction = 'bullish' if signal['close'] > previous['high'] and signal['close'] > df['bb_mid'].iloc[-1] else 'bearish'
            if direction == 'bullish' and bull_reversal:
                return build_direct_mode_setup(df, 'bullish', 'Squeeze Expansion Long', signal['close'], df['bb_lower'].iloc[-1], df['bb_upper'].iloc[-1] + avg_range * 1.50)
            elif direction == 'bearish' and bear_reversal:
                return build_direct_mode_setup(df, 'bearish', 'Squeeze Expansion Short', signal['close'], df['bb_upper'].iloc[-1], df['bb_lower'].iloc[-1] - avg_range * 1.50)

    return None

def live_trade_permission(strategy_name, optimizer=None, perf=None):
    if optimizer is None:
        optimizer = auto_tune_strategy_params(strategy_name, perf)
    
    tier = optimizer.get('state', 'pause')
    
    if optimizer['state'] == 'pause':
        return False, 'strategy optimizer verdict is PAUSE', tier
        
    block_reason = performance_block_reason(strategy_name)
    if block_reason:
        return False, block_reason, tier
        
    return True, '', tier

def get_btc_market_regime():
    from .okx_client import fetch_data
    try:
        btc_df = fetch_data('BTC/USDT:USDT', '4h', limit=40)
        if btc_df.empty or len(btc_df) < 20:
            return 'ranging'
        std = btc_df['close'].rolling(window=20).std()
        bb_mid = btc_df['close'].rolling(window=20).mean()
        bb_w = (2.0 * 2.0 * std) / bb_mid
        current_w = bb_w.iloc[-1]
        
        adx = btc_df.get('adx', pd.Series([20.0]*len(btc_df))).iloc[-1]
        
        if current_w > 0.05 and adx > 25:
            return 'trending'
        return 'ranging'
    except Exception:
        return 'ranging'

def evaluate_mode_gate(strategy_name, direction, rsi, trends, in_prz, true_rr, target_rr, div_ok, sweep_ok, df, optimizer=None, symbol=None, category=None):
    # Loosened gate limits for training mode (allows more trading signals)
    symbol = symbol or ''
    is_major = any(kw in symbol.upper() for kw in ['BTC', 'ETH', 'SOL'])
    regime = get_btc_market_regime()

    if strategy_name == 'MacroSniper':
        # Loosened: Allow ranging regime and check 1h trend instead of 4h
        if direction == 'bullish' and trends.get('1h') != 'bull' and trends.get('4h') != 'bull':
            return False, 'MacroSniper gate: trend is not bullish'
        if direction == 'bearish' and trends.get('1h') != 'bear' and trends.get('4h') != 'bear':
            return False, 'MacroSniper gate: trend is not bearish'

    if strategy_name == 'MeanReversion':
        # Loosened: Bypass anti-trend safety during training
        pass

    if strategy_name == 'Contrarian':
        # Loosened: Expand RSI thresholds from 38/62 to 45/55
        if direction == 'bullish' and rsi > 45:
            return False, 'Contrarian gate: RSI too high for long reversal entry (training threshold 45)'
        if direction == 'bearish' and rsi < 55:
            return False, 'Contrarian gate: RSI too low for short reversal entry (training threshold 55)'

    if strategy_name == 'SqueezeHunter':
        # Loosened: Bypass volatility narrowing check
        pass

    return True, ''

def calculate_adx(df, period=14):
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = abs(minus_dm)
    
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    return adx

def calculate_macd(df):
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist

def calculate_keltner(df, period=20, multiplier=1.5):
    ema = df['close'].ewm(span=period, adjust=False).mean()
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    k_upper = ema + (multiplier * atr)
    k_lower = ema - (multiplier * atr)
    return k_upper, k_lower


def build_bot_report(visible_trades=None, live_positions=None):
    from .engine import build_live_trade_snapshot
    from .utils import is_session_trade, timestamp_ms, session_started_at_ms
    from .okx_client import capital_snapshot
    from . import config
    from . import state
    import datetime

    if visible_trades is None:
        visible_trades = build_live_trade_snapshot()
    if live_positions is None:
        live_positions = [t for t in visible_trades if t.get('status') == 'active' and t.get('source') == 'okx_live']
    active = [t for t in visible_trades if t.get('status') == 'active']
    potentials = [t for t in visible_trades if t.get('status') == 'potential']
    session_active = [t for t in active if is_session_trade(t)]
    session_potentials = [t for t in potentials if is_session_trade(t)]
    session_history_rows = [
        row for row in state.trade_journal
        if timestamp_ms(row.get('closed_at') or row.get('timestamp') or row.get('uTime')) >= session_started_at_ms()
    ]
    perf = all_strategy_performance()
    optimizers = {name: auto_tune_strategy_params(name) for name in config.STRATEGY_PROFILES}
    active_pnl = sum(float(t.get('pnl') or 0) for t in active)
    session_active_pnl = sum(float(t.get('pnl') or 0) for t in session_active)
    session_realized_pnl = sum(float(r.get('realized_pnl') or r.get('realizedPnl') or 0) for r in session_history_rows)
    live_modes = []
    weak_modes = []
    for name, opt in optimizers.items():
        _, reason, tier = live_trade_permission(name, opt, perf.get(name))
        item = {
            'strategy': name,
            'label': strategy_profile(name)['label'],
            'tier': tier,
            'reason': reason,
            'pf': opt.get('profit_factor'),
            'expectancy': opt.get('expectancy'),
            'max_margin': opt.get('max_margin'),
            'state': opt.get('state'),
        }
        if tier in ['live_core', 'live_calibration']:
            live_modes.append(item)
        else:
            weak_modes.append(item)

    live_active = [t for t in active if t.get('source') == 'okx_live']
    tracked_active = [t for t in active if t.get('source') != 'okx_live']

    watch = []
    for t in live_active[:8]:
        entry = float(t.get('entry') or 0)
        current = float(t.get('current') or 0)
        sl = float(t.get('sl') or 0)
        tp = float(t.get('tp1') or 0)
        watch.append({
            'symbol': t.get('symbol'),
            'strategy': t.get('strategy'),
            'direction': t.get('direction'),
            'entry': entry,
            'current': current,
            'sl': sl,
            'tp1': tp,
            'pnl': round(float(t.get('pnl') or 0), 4),
            'highest_pnl': t.get('highest_pnl'),
            'highest_r': t.get('highest_r'),
            'current_r': t.get('current_r'),
            'stage': t.get('trailing_stage') or 'waiting',
            'protection': t.get('runner_policy'),
            'protection_status': t.get('protection_status') or 'unconfirmed',
            'protection_error': t.get('protection_error'),
            'actual_margin': t.get('initialMargin'),
            'actual_notional': t.get('notional'),
        })

    tracked_watch = []
    for t in tracked_active[:8]:
        tracked_watch.append({
            'symbol': t.get('symbol'),
            'strategy': t.get('strategy'),
            'direction': t.get('direction'),
            'entry': float(t.get('entry') or 0),
            'current': float(t.get('current') or 0),
            'sl': float(t.get('sl') or 0),
            'tp1': float(t.get('tp1') or 0),
            'pnl': round(float(t.get('pnl') or 0), 4),
            'highest_pnl': t.get('highest_pnl'),
            'highest_r': t.get('highest_r'),
            'current_r': t.get('current_r'),
            'stage': t.get('trailing_stage') or 'waiting',
            'protection': t.get('runner_policy'),
            'protection_status': t.get('protection_status') or 'unconfirmed',
            'protection_error': t.get('protection_error'),
            'actual_margin': t.get('initialMargin'),
            'actual_notional': t.get('notional'),
        })

    verdict = '資金保護中'
    if active_pnl > 0 and live_modes:
        verdict = '獲利單保護中'
    elif live_modes:
        verdict = '等待核心模式訊號'
    if not active and potentials:
        verdict = '無持倉，掃描候選訊號'
    elif not active and not potentials:
        verdict = '無持倉，市場掃描中'

    return {
        'server_time': datetime.datetime.now().isoformat(timespec='seconds'),
        'verdict': verdict,
        'account': state.account_data,
        'capital': capital_snapshot(),
        'active_count': len(active),
        'potential_count': len(potentials),
        'active_pnl': round(active_pnl, 4),
        'session_active_count': len(session_active),
        'session_potential_count': len(session_potentials),
        'session_active_pnl': round(session_active_pnl, 4),
        'session_realized_pnl': round(session_realized_pnl, 4),
        'session_started_at': config.SESSION_STARTED_AT,
        'live_modes': live_modes,
        'weak_modes': weak_modes,
        'positions': watch,
        'tracked_positions': tracked_watch,
        'protection_rule': '浮盈達 0.25R 推近保本，0.55R 鎖利，1R 後用最高 R 回吐 0.35R 移動止損。',
    }

def infer_exit_reason(trade, close_price):
    close_price = as_float(close_price)
    sl = as_float(trade.get('sl'))
    tp = as_float(trade.get('tp1'))
    direction = str(trade.get('direction') or '').lower()
    
    if not close_price:
        return 'unknown'
        
    if direction == 'long':
        if sl > 0 and close_price <= sl * 1.002:
            return 'stop_loss'
        if tp > 0 and close_price >= tp * 0.998:
            return 'take_profit'
    else:
        if sl > 0 and close_price >= sl * 0.998:
            return 'stop_loss'
        if tp > 0 and close_price <= tp * 1.002:
            return 'take_profit'
            
    return 'manual'

