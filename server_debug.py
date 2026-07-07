from flask import Flask, jsonify, send_from_directory
import threading
import time
import ccxt
import uuid
import pandas as pd
from core.pivot_detector import detect_pivots
from core.pattern_scanner import scan_patterns
from core.divergence import check_divergence, calculate_rsi
from core.candle_filter import is_reversal_candle
from core.trade_planner import build_trade_plan

app = Flask(__name__, static_folder='ui')

import json
import os
import uuid
import sys
import datetime
from pathlib import Path

# FORCE UTF-8 Encoding to prevent crash when printing emojis on Windows cp950 console
sys.stdout.reconfigure(encoding='utf-8')

# Load existing state
TRADE_FILE = str(Path(__file__).resolve().parent / 'active_trades_macmini_01.json')
JOURNAL_FILE = str(Path(__file__).resolve().parent / 'journal_macmini_01.json')
active_trades = []
trade_journal = []

try:
    if os.path.exists(TRADE_FILE):
        with open(TRADE_FILE, 'r') as f:
            active_trades = json.load(f)
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, 'r') as f:
            trade_journal = json.load(f)
except Exception as e:
    print(f"Failed to load state files: {e}")

potential_signals = []
market_radar_dict = {'MacroSniper': [], 'MeanReversion': [], 'Contrarian': [], 'SqueezeHunter': []}
trade_id_counter = max([t['id'] for t in active_trades], default=0) + 1

# --- ML Core: Confidence Score ---
def get_confidence_score(strategy_name, category):
    """
    Evaluates historical trade_journal to assign a Confidence Score.
    Continuously scales with win rate: 50% Win Rate = 1.0 Confidence.
    """
    relevant = [t for t in trade_journal if t.get('strategy') == strategy_name and t.get('category') == category]
    if len(relevant) < 3:
        return 1.0 # Cold Start: Default weight

    wins = [t for t in relevant if t.get('pnl', 0) > 0]
    win_rate = len(wins) / len(relevant)
    
    # Continuous Scaling: 
    # Win Rate 0.50 = Confidence 1.0
    # Win Rate 0.80 = Confidence 1.6
    # Win Rate 1.00 = Confidence 2.0
    confidence = win_rate * 2.0
    
    # Cap between 0.2 (Minimum Survival) and 2.5 (High Conviction)
    return max(0.2, min(2.5, confidence))


# OKX API configuration (Loaded from CLI profile okx-demo)
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
    'enableRateLimit': True,
})
# Set CCXT to use the demo environment (Simulated Trading)
okx.set_sandbox_mode(True)

def fetch_data(symbol, timeframe, limit=200):
    ohlcv = okx.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['rsi'] = calculate_rsi(df)
    return df

htf_trend_cache = {}

def get_cached_trend(sym, tf):
    cache_key = f"{sym}_{tf}"
    now = time.time()
    
    # Expiry: 15m -> 5m, 1h -> 15m, 4h/1d -> 60m
    expiry = 300 if tf == '15m' else (900 if tf == '1h' else 3600)
    
    if cache_key in htf_trend_cache:
        if now - htf_trend_cache[cache_key]['timestamp'] < expiry:
            return htf_trend_cache[cache_key]['trend']
            
    d = fetch_data(sym, tf, limit=200)
    if d.empty: return 'neutral'
    e50 = d['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    e200 = d['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    current_price = d['close'].iloc[-1]
    
    if current_price > e200 and e50 > e200:
        res = 'bull'
    elif current_price < e200 and e50 < e200:
        res = 'bear'
    else:
        res = 'neutral'
        
    htf_trend_cache[cache_key] = {"trend": res, "timestamp": now}
    return res

def get_top_symbols_and_categories():
    categories = {}
    selected_symbols = []
    try:
        okx.load_markets()
        tickers = okx.fetch_tickers(params={'instType': 'SWAP'})
        funding = okx.fetch_funding_rates(params={'instType': 'SWAP'})
        
        swap_symbols = set([m['symbol'] for m in okx.markets.values() if m.get('swap') and m.get('quote') == 'USDT'])
        usdt_swaps = [v for k, v in tickers.items() if k in swap_symbols]
        # Sort by volume to ensure we only look at liquid pairs
        sorted_swaps = sorted(usdt_swaps, key=lambda x: float(x.get('quoteVolume', 0) or 0), reverse=True)
        top_swaps = sorted_swaps[:250]
        
        btc_pct = tickers.get('BTC/USDT:USDT', {}).get('percentage', 0)
        if btc_pct is None: btc_pct = 0
        
        for t in top_swaps:
            sym = t['symbol']
            sym_clean = sym.replace(':USDT', '').replace('/', '')
            if sym in selected_symbols: continue
            
            # Majors
            if sym_clean in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                categories[sym] = "主流大餅 (Majors)"
                selected_symbols.append(sym)
                continue
                
            # Funding Extremes (Squeeze)
            fr = funding.get(sym, {}).get('fundingRate', 0)
            if fr is None: fr = 0
            if fr and (fr < -0.0005 or fr > 0.0005):
                categories[sym] = "極端費率 (Squeeze Watch)"
                selected_symbols.append(sym)
                continue
                
            # Relative Strength (Alpha)
            pct = t.get('percentage', 0)
            if pct is None: pct = 0
            if pct > btc_pct + 5: # Outperforming BTC by 5%
                categories[sym] = "Alpha 強勢幣 (Rel. Strength)"
                selected_symbols.append(sym)
                continue
                
            # Deep Oversold
            if pct < -5:
                categories[sym] = "深跌超賣 (Deep Oversold)"
                selected_symbols.append(sym)
                continue
                
            # High Volatility
            high = t.get('high', 0)
            low = t.get('low', 0)
            if high is None: high = 0
            if low is None: low = 0
            if low > 0 and ((high - low) / low) > 0.10:
                categories[sym] = "高波動狙擊 (High Volatility)"
                selected_symbols.append(sym)
                continue
                
        # Fill the rest with high volume
        for t in top_swaps:
            if len(selected_symbols) >= 200: break
            sym = t['symbol']
            if sym not in selected_symbols:
                categories[sym] = "普通高量 (High Volume)"
                selected_symbols.append(sym)
                
        return selected_symbols[:80], categories
    except Exception as e:
        print(f"Error fetching top symbols: {e}")
        return ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT'], {'BTC/USDT:USDT':'Majors','ETH/USDT:USDT':'Majors','SOL/USDT:USDT':'Majors'}

# Global symbols fetched once
global_symbols = []
global_symbol_categories = {}

def run_strategy(strategy_name, timeframe, tolerance, sl_buffer_pct, trend_tf, target_rr):
    global trade_id_counter, active_trades, potential_signals, market_radar_dict
    global global_symbols
    
    print(f"[{strategy_name}] Engine Started. ({timeframe} candles, {trend_tf} trend filter)")
    
    # Anti-whipsaw dictionary to track last entry time per symbol
    cooldowns = {}
    tf_minutes = int(timeframe.replace('m', '').replace('h', '60')) if any(c.isdigit() for c in timeframe) else 5
    COOLDOWN_SECONDS = tf_minutes * 60
    
    while True:
        try:
            symbols = global_symbols
            if not symbols:
                time.sleep(5)
                continue
                
            current_potentials = []
            current_radar = []
            current_potentials = []
            current_radar = []
            
            for symbol in symbols:
                try:
                    # Apply Coin-Specific Profiles based on Dynamic Categories
                    cat = global_symbol_categories.get(symbol, 'Uncategorized')
                    
                    # Mode Alignment (Soft Whitelisting)
                    alignment_penalty = 1.0
                    if strategy_name == 'MacroSniper' and not ('Alpha' in cat or 'Majors' in cat):
                        alignment_penalty = 0.5
                    elif strategy_name == 'MeanReversion' and ('Squeeze' in cat):
                        alignment_penalty = 0.3
                    elif strategy_name == 'Contrarian' and not ('Oversold' in cat or 'Volatility' in cat):
                        alignment_penalty = 0.6
                    elif strategy_name == 'SqueezeHunter' and not ('Squeeze' in cat):
                        alignment_penalty = 0.4

                    trends_dict = {
                        '15m': get_cached_trend(symbol, '15m'),
                        '1h': get_cached_trend(symbol, '1h'),
                        '4h': get_cached_trend(symbol, '4h'),
                        '1d': get_cached_trend(symbol, '1d')
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
                    if df.empty: continue
                    
                    # Extreme Relaxation: Lowered to 0.05% to force trades even in dead markets
                    min_profit = 0.002
                    if timeframe == '5m': min_profit = 0.0005
                    elif timeframe == '15m': min_profit = 0.001
                    
                    # Apply Coin-Specific Profiles based on Dynamic Categories
                    cat = global_symbol_categories.get(symbol, 'Uncategorized')
                    
                    # Calculate True ATR % (Average True Range as a percentage of price over last 14 candles)
                    recent_df = df.tail(14)
                    if not recent_df.empty:
                        avg_range = (recent_df['high'] - recent_df['low']).mean()
                        current_price = df['close'].iloc[-1]
                        atr_pct = (avg_range / current_price) if current_price > 0 else 0
                    else:
                        atr_pct = 0
                    
                    # Mode Alignment (Soft Whitelisting)
                    alignment_penalty = 1.0
                    if strategy_name == 'MacroSniper' and not ('Alpha' in cat or 'Majors' in cat):
                        alignment_penalty = 0.5
                    elif strategy_name == 'MeanReversion' and ('Squeeze' in cat):
                        alignment_penalty = 0.3
                    elif strategy_name == 'Contrarian' and not ('Oversold' in cat or 'Volatility' in cat):
                        alignment_penalty = 0.6
                    elif strategy_name == 'SqueezeHunter' and not ('Squeeze' in cat):
                        alignment_penalty = 0.4
                        
                    if 'Squeeze' in cat:
                        active_tolerance = tolerance * 0.7
                        base_sl_buffer = sl_buffer_pct * 1.5
                        active_min_profit = min_profit * 2.0
                    elif 'Alpha' in cat:
                        active_tolerance = tolerance * 0.8
                        base_sl_buffer = sl_buffer_pct * 1.2
                        active_min_profit = min_profit * 1.5
                    elif 'Oversold' in cat:
                        active_tolerance = tolerance * 0.5
                        base_sl_buffer = sl_buffer_pct * 2.0
                        active_min_profit = min_profit * 1.5
                    elif 'Volatility' in cat:
                        active_tolerance = tolerance * 0.6
                        base_sl_buffer = sl_buffer_pct * 1.5
                        active_min_profit = min_profit * 1.2
                    elif 'Majors' in cat:
                        active_tolerance = tolerance
                        base_sl_buffer = sl_buffer_pct
                        active_min_profit = min_profit
                    else:
                        # Default High Volume
                        active_tolerance = tolerance * 0.8
                        base_sl_buffer = sl_buffer_pct * 1.2
                        active_min_profit = min_profit * 1.2
                        
                    # DYNAMIC ATR-BASED STOP LOSS ADAPTATION
                    # Ensure SL is at least 60% of the average candle wick (ATR) so it doesn't get swept by noise
                    active_sl_buffer = max(base_sl_buffer, atr_pct * 0.6)

                    # Apply alignment penalty to tolerance (make it stricter for bad regimes)
                    active_tolerance = active_tolerance * alignment_penalty

                    # ML Engine Feedback (Determines position size multiplier)
                    confidence = get_confidence_score(strategy_name, cat) * alignment_penalty

                    # Dynamic pivot depth based on standard Fractal/ZigZag math
                    pivot_depth = 4
                    if timeframe == '5m': pivot_depth = 1
                    elif timeframe == '15m': pivot_depth = 3
                    elif timeframe in ['1h', '4h']: pivot_depth = 4
                    
                    hist_pivots = detect_pivots(df, depth=pivot_depth)
                    
                    # SYNTHESIZE REAL-TIME D-POINT
                    # Harmonic trading relies on entering AS the price touches the PRZ.
                    # We cannot wait `pivot_depth` candles for D to be confirmed historically.
                    # So we take the historical pivots (X,A,B,C) and append the live ticking price as D.
                    pivots = list(hist_pivots)
                    if len(pivots) >= 4:
                        # CRITICAL: We only need the last 4 historical pivots (X,A,B,C)
                        # This prevents the scanner from matching old, expired 5-point patterns in the history.
                        pivots = pivots[-4:]
                        last_p = pivots[-1]
                        fake_type = "low" if last_p.type == "high" else "high"
                        # Use the current close price as the potential pivot D
                        current_close = df['close'].iloc[-1]
                        current_time = str(df['time'].iloc[-1])
                        current_idx = len(df) - 1
                        
                        from core.pivot_detector import PivotPoint
                        fake_d = PivotPoint(current_idx, current_time, current_close, fake_type)
                        pivots.append(fake_d)
                    
                    patterns = scan_patterns(pivots, tolerance=active_tolerance)
                    
                    display_sym = symbol.replace(':USDT', '').replace('/', '')
                    
                    # Radar Item
                    radar_item = {
                        'symbol': display_sym,
                        'category': global_symbol_categories.get(symbol, 'Uncategorized'),
                        'trends': trends_dict,
                        'rsi': round(df['rsi'].iloc[-1], 1) if pd.notna(df['rsi'].iloc[-1]) else 50,
                        'pattern': 'None',
                        'score': 0,
                        'trigger_reason': '掃描型態中 (Scanning)',
                        'strategy': strategy_name,
                        'active_tolerance': round(active_tolerance, 3),
                        'active_sl_buffer': round(active_sl_buffer, 3),
                        'active_min_profit': round(active_min_profit, 3),
                        'confidence': round(confidence, 2)
                    }
                    
                    if patterns:
                        best_p = patterns[-1]
                        radar_item['pattern'] = best_p.pattern_name
                        d_price = best_p.d.price
                        prz_width = best_p.prz_high - best_p.prz_low
                        buffer = prz_width * 0.15 if prz_width > 0 else best_p.prz_center * 0.002
                        # Radar UI can still show 100 score when entering the outer PRZ box
                        in_prz = (best_p.prz_low - buffer) <= d_price <= (best_p.prz_high + buffer)
                        if in_prz:
                            radar_item['score'] = 100
                            radar_item['trigger_reason'] = 'PRZ 抵達！等待指標共振進場'
                        else:
                            dist = min(abs(d_price - best_p.prz_low), abs(d_price - best_p.prz_high))
                            radar_item['score'] = max(10, int(100 - (dist / d_price) * 1000))
                            direction = "做多" if best_p.direction == 'bullish' else "做空"
                            radar_item['trigger_reason'] = f"等待 D 點{direction}至 {best_p.prz_center:.4g}"
                            
                    current_radar.append(radar_item)
                    
                    for p in patterns:
                        d_price = p.d.price
                        prz_width = p.prz_high - p.prz_low
                        buffer = prz_width * 0.15 if prz_width > 0 else p.prz_center * 0.002
                        
                        # CRITICAL ENTRY POSITION OPTIMIZATION:
                        print(f'DEBUG PRZ: {symbol} d_price={d_price} prz=[{p.prz_low}, {p.prz_high}] width={prz_width} buffer={buffer}')
                        if strategy_name in ['SqueezeHunter', 'Contrarian', 'MeanReversion']:
                            # AGGRESSIVE MODES: Force execute instantly when hitting PRZ edge
                            in_prz = (p.prz_low - buffer) <= d_price <= (p.prz_high + buffer)
                        else:
                            # PATIENT MODES: Wait for price to penetrate PRZ deeply
                            if p.direction == 'bullish':
                                trigger_price = p.prz_center + (prz_width * 0.2)
                                in_prz = d_price <= trigger_price and d_price >= (p.prz_low - buffer)
                            else:
                                trigger_price = p.prz_center - (prz_width * 0.2)
                                in_prz = d_price >= trigger_price and d_price <= (p.prz_high + buffer)
                        
                        # HTF Trend Filter - ENFORCED FOR ALL STRATEGIES (High Win-Rate Training Mode)
                        rsi = df['rsi'].iloc[-1] if pd.notna(df['rsi'].iloc[-1]) else 50
                        rsi_ok = rsi < 45 if p.direction == 'bullish' else rsi > 55
                        trend_ok = (p.direction == 'bullish' and htf_bull) or (p.direction == 'bearish' and htf_bear)
                        
                        # Institutional Filters (v2.0)
                        div_ok = check_divergence(df, len(df)-1, lookback=30, direction=p.direction)
                        
                        # Liquidity Sweep Check: Did price pierce X point?
                        sweep_ok = False
                        current_candle = df.iloc[-1]
                        if p.direction == 'bullish':
                            sweep_ok = current_candle['low'] <= p.x.price
                        else:
                            sweep_ok = current_candle['high'] >= p.x.price
                        
                        # Pass the strategy's specific sl_buffer to the planner
                        plan = build_trade_plan(p.direction, p.x.price, p.a.price, p.c.price, p.d.price, p.pattern_name, min_rr=0.2, sl_buffer_pct=active_sl_buffer)
                        
                        # DYNAMIC TARGET COMPRESSION: Secure profits faster for aggressive/intraday modes
                        if strategy_name in ['MeanReversion', 'Contrarian']:
                            move_ad = abs(p.a.price - p.d.price)
                            if p.direction == 'bullish':
                                plan['tp1'] = p.d.price + move_ad * 0.382 # Restored to 0.382 to ensure RR is viable
                            else:
                                plan['tp1'] = p.d.price - move_ad * 0.382
                        
                        # CRITICAL WIN-RATE FIX: Calculate TRUE Risk/Reward based on the real-time execution price!
                        current_price = df.iloc[-1]['close']
                        true_risk = abs(current_price - plan['sl'])
                        true_reward = abs(plan['tp1'] - current_price)
                        true_rr = true_reward / true_risk if true_risk > 0 else 0
                        
                        # Override the theoretical RR with the TRUE real-time RR
                        plan["risk_reward"] = round(true_rr, 2)
                        
                        # CHECK: Valid Live Target Prices?
                        sl_valid = (plan['sl'] < current_price) if p.direction == 'bullish' else (plan['sl'] > current_price)
                        tp_valid = (plan['tp1'] > current_price) if p.direction == 'bullish' else (plan['tp1'] < current_price)
                        
                        block_reason = None
                        if not sl_valid or not tp_valid:
                            block_reason = "API 參數無效 (止損/止盈方向錯誤)"
                        elif not in_prz:
                            block_reason = "未進入 PRZ 區間"
                        else:
                            # Apply Strategy-Specific Logic
                            t_dir = '空' if htf_bear and not htf_bull else ('多' if htf_bull and not htf_bear else '盤')
                            
                            if strategy_name == 'MacroSniper':
                                # Strict Patient Killer: Requires Trend + Institutional
                                if not trend_ok:
                                    block_reason = f"大級別趨勢不符 ({trend_tf} {t_dir})"
                                elif not div_ok and not sweep_ok:
                                    block_reason = "缺乏機構信號 (無背離/無掃蕩)"
                                    
                            elif strategy_name == 'MeanReversion':
                                # Range Scalper: Requires Trend, ignores Institutional
                                if not trend_ok:
                                    block_reason = f"大級別趨勢不符 ({trend_tf} {t_dir})"
                                    
                            elif strategy_name == 'Contrarian':
                                # Falling Knife Catcher: Ignores Trend, REQUIRES Institutional confirmation
                                if not div_ok and not sweep_ok:
                                    block_reason = "缺乏反轉信號 (無背離/無掃蕩)"
                                    
                            elif strategy_name == 'SqueezeHunter':
                                # Volatility Surfer: Pure PRZ edge bounce (Fastest execution)
                                pass
                                
                        if not block_reason:
                            # PROFITABILITY CHECK (Live Fire Calibration)
                            active_min_profit = 0.0015 # Minimum 0.15% profit space to cover OKX Maker+Taker fees
                            
                            profit_pct = abs(plan["tp1"] - current_price) / current_price
                            if profit_pct < active_min_profit:
                                block_reason = f"利潤空間太小 (<{(active_min_profit*100):.2f}%)"
                            elif true_rr < target_rr:
                                block_reason = f"真實盈虧比過低 ({round(true_rr, 2)} < {target_rr})"
                                
                        display_sym = symbol.replace(':USDT', '').replace('/', '')
                        already_active = any(t['symbol'] == display_sym and t['status'] == 'active' for t in active_trades)
                        
                        signal_obj = {
                            "id": trade_id_counter,
                            "symbol": display_sym,
                            "direction": "long" if p.direction == "bullish" else "short",
                            "pattern": p.pattern_name,
                            "status": "potential",
                            "entry": plan["entry"],
                            "current": df.iloc[-1]['close'],
                            "sl": plan["sl"],
                            "tp1": plan["tp1"],
                            "original_tp_dist": abs(plan["tp1"] - current_price),
                            "pnl": 0.0,
                            "rsi_on_entry": round(df['rsi'].iloc[-1], 1) if pd.notna(df['rsi'].iloc[-1]) else 50,
                            "trends": trends_dict,
                            "strategy": strategy_name,
                            "block_reason": block_reason
                        }
                        
                        # Check anti-whipsaw cooldown
                        on_cooldown = False
                        if symbol in cooldowns and (time.time() - cooldowns[symbol] < COOLDOWN_SECONDS):
                            on_cooldown = True
                            if not block_reason:
                                block_reason = "進場冷卻中"
                                signal_obj["block_reason"] = block_reason
                        
                        if not block_reason and not already_active and not on_cooldown:
                            # ACTUAL OKX ORDER EXECUTION
                            try:
                                side = 'buy' if p.direction == 'bullish' else 'sell'
                                
                                # Dynamic Leverage Cap to prevent liquidation before SL
                                sl_dist_pct = abs(current_price - plan['sl']) / current_price
                                # Leave a 0.5% buffer for OKX maintenance margin penalty
                                max_safe_leverage = int(1.0 / (sl_dist_pct + 0.005)) if sl_dist_pct > 0 else 75
                                safe_leverage_target = min(75, max_safe_leverage)
                                
                                # Fallback Leverage Logic (capped by safety)
                                base_leverages = [75, 50, 20, 10, 5, 2, 1]
                                leverages_to_try = [l for l in base_leverages if l <= safe_leverage_target]
                                if not leverages_to_try: leverages_to_try = [1]
                                
                                actual_leverage = leverages_to_try[0]
                                for lev in leverages_to_try:
                                    try:
                                        okx.set_leverage(lev, symbol)
                                        actual_leverage = lev
                                        break
                                    except Exception:
                                        continue
                                        
                                # Dynamic Position Sizing (Base 60U Margin * ML Confidence)
                                margin_usdt = 60 * max(0.2, confidence) # Floor at 12U if confidence is very low
                                target_notional = margin_usdt * actual_leverage
                                current_price = df.iloc[-1]['close']
                                contract_size = okx.markets[symbol]['contractSize']
                                
                                # Calculate number of contracts needed
                                raw_size = target_notional / (current_price * float(contract_size))
                                size = max(1, int(raw_size)) # Must be at least 1 contract
                                
                                # OKX clOrdId must be alphanumeric (1-32 chars)
                                cl_ord_id = f"H{strategy_name}{uuid.uuid4().hex[:8]}"
                                # Format the Trigger Prices to exactly match the instrument's required tickSize precision.
                                # If we pass raw Python floats, OKX will silently reject the Algo Order attachment!
                                formatted_sl = okx.price_to_precision(symbol, plan['sl'])
                                formatted_tp = okx.price_to_precision(symbol, plan['tp1'])
                                
                                # CRITICAL FAIL-SAFE: Verify TP/SL are mathematically valid against the REAL-TIME execution price.
                                # If the price has drifted past our targets while waiting for candle confirmation, 
                                # OKX will reject the Algo order but still place the market order, creating a naked position!
                                sl_valid = (plan['sl'] < current_price) if side == 'buy' else (plan['sl'] > current_price)
                                tp_valid = (plan['tp1'] > current_price) if side == 'buy' else (plan['tp1'] < current_price)
                                
                                if not sl_valid or not tp_valid:
                                    print(f"[{strategy_name}] Skipped naked position risk on {symbol}. Price {current_price} violates SL {plan['sl']} or TP {plan['tp1']}")
                                    continue
                                
                                # Use OKX Native TP/SL parameters for bulletproof order placement.
                                # This avoids OKX native attachAlgoOrds silent drop issues by ensuring tickSize precision matching.
                                order_res = okx.create_order(symbol, 'market', side, size, None, {
                                    'tdMode': 'cross',
                                    'clientOrderId': cl_ord_id,
                                    'slTriggerPx': formatted_sl,
                                    'slOrdPx': '-1',
                                    'tpTriggerPx': formatted_tp,
                                    'tpOrdPx': '-1'
                                })
                                
                                # CRITICAL FAIL-SAFE: Check for silent OKX API rejection of Algo Orders
                                info = order_res.get('info', {})
                                s_msg = info.get('sMsg', '')
                                s_code = str(info.get('sCode', '0'))
                                
                                # OKX sometimes drops attachAlgoOrds silently if distance is too small, returning sCode != '0'
                                is_failure = (s_code != '0') or (s_msg and any(k in s_msg.lower() for k in ['fail', 'reject', 'error', 'invalid', 'warning']))
                                if is_failure:
                                    print(f"[{strategy_name}] OKX WARNING on {symbol}: Code {s_code}, Msg: {s_msg}")
                                    # If OKX threw a warning, it almost certainly means the attachAlgoOrds failed.
                                    # We must immediately close the naked position to protect the user!
                                    print(f"[{strategy_name}] FATAL: TP/SL attachment silently rejected by OKX. Closing naked position immediately!")
                                    close_side = 'sell' if side == 'buy' else 'buy'
                                    try:
                                        okx.create_order(symbol, 'market', close_side, size, None, {'tdMode': 'cross'})
                                        print(f"[{strategy_name}] Emergency close successful. Naked position annihilated.")
                                    except Exception as emergency_err:
                                        print(f"[{strategy_name}] URGENT ERROR: Failed to close naked position: {emergency_err}")
                                    
                                    # Skip adding this aborted trade to active tracking
                                    continue
                                print(f"DEMO ORDER EXECUTED: {side} {size} contracts of {symbol} (Notional: ~${int(size*current_price*float(contract_size))})")
                                
                                # ONLY append to UI after OKX confirms execution!
                                cooldowns[symbol] = time.time()
                                signal_obj["status"] = "active"
                                signal_obj["entry_reason"] = f"觸發 {p.pattern_name} (指標共振/趨勢吻合)"
                                active_trades.append(signal_obj)
                                # Garbage collection
                                if len(active_trades) > 1000:
                                    active_trades = active_trades[-1000:]
                                trade_id_counter += 1
                                print(f"SIGNAL GENERATED: {display_sym} {p.direction.upper()} {p.pattern_name} @ {plan['entry']}")

                            except Exception as ex:
                                print(f"Demo Execution Error: {ex}")
                        elif not already_active:
                            # It's a potential setup waiting for PRZ or Trend alignment
                            current_potentials.append(signal_obj)
                            
                    time.sleep(1.5) # Extended rate limit protection per symbol to avoid 50011
                except Exception as e:
                    print(f"Error scanning {symbol}: {e}")
                    time.sleep(1)
            
            # Merge potentials safely
            global potential_signals, market_radar_dict
            potential_signals = [s for s in potential_signals if s.get('strategy') != strategy_name] + current_potentials
            
            # Merge radar safely into the dict
            market_radar_dict[strategy_name] = current_radar
            
            # Wait before next full market scan
            time.sleep(60)
        except Exception as e:
            print(f"Error in main bot loop: {e}")
            time.sleep(10)

@app.route('/')
def serve_ui():
    return send_from_directory('ui', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('ui', path)

# --- BACKGROUND SYNC DAEMON ---
account_data = {'totalEq': 0.0, 'usdtEq': 0.0, 'usdtAvail': 0.0}

def background_sync_loop():
    global active_trades, trade_id_counter, account_data, potential_signals, trade_journal
    while True:
        try:
            # 1. Sync Account Balance
            new_account_data = {'totalEq': 0.0, 'usdtEq': 0.0, 'usdtAvail': 0.0}
            try:
                bal = okx.fetch_balance()
                new_account_data['totalEq'] = float(bal['info']['data'][0].get('totalEq', 0))
                for det in bal['info']['data'][0].get('details', []):
                    if det['ccy'] == 'USDT':
                        new_account_data['usdtEq'] = float(det.get('eq', 0))
                        new_account_data['usdtAvail'] = float(det.get('availEq', 0))
                account_data = new_account_data
            except Exception:
                pass

            # 2. Sync Active Positions & Clear Closed Trades
            try:
                positions = okx.fetch_positions()
                for t in active_trades:
                    if t['status'] == 'active':
                        pos = next((p for p in positions if p['symbol'].replace('/', '').replace(':USDT', '') == t['symbol'] and p['side'] == t['direction']), None)
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
                            t['status'] = 'closed'
                            trade_journal.append(t)
                            
                # Cleanup and Save
                if any(t['status'] == 'closed' for t in active_trades):
                    active_trades = [t for t in active_trades if t['status'] != 'closed']
                    with open(JOURNAL_FILE, 'w') as f:
                        json.dump(trade_journal, f)
                            
                for pos in positions:
                    sym = pos['symbol'].replace('/', '').replace(':USDT', '')
                    direction = pos.get('side', 'long')
                    exists = any(t['symbol'] == sym and t['direction'] == direction and t['status'] == 'active' for t in active_trades)
                    if not exists:
                        active_trades.append({
                            "id": trade_id_counter, "posId": pos.get('id'), "instId": pos.get('info', {}).get('instId', ''),
                            "symbol": sym, "direction": direction, "pattern": "Manual / Unsynced", "status": "active",
                            "entry": float(pos.get('entryPrice', 0)), "current": float(pos['markPrice']), "sl": 0, "tp1": 0,
                            "pnl": float(pos.get('unrealizedPnl', 0.0)), "percentage": float(pos.get('percentage', 0.0)),
                            "rsi_on_entry": '--', "trends": {}, "strategy": "Manual", "leverage": pos.get('leverage'),
                            "initialMargin": pos.get('initialMargin'), "notional": pos.get('notional'),
                            "liquidationPrice": pos.get('liquidationPrice'), "marginRatio": pos.get('marginRatio')
                        })
                        trade_id_counter += 1

                # 3. Sync Algo Orders (TP/SL)
                oco_res = okx.private_get_trade_orders_algo_pending({'instType':'SWAP', 'ordType': 'oco'})
                cond_res = okx.private_get_trade_orders_algo_pending({'instType':'SWAP', 'ordType': 'conditional'})
                all_algos = []
                if oco_res and oco_res.get('code') == '0': all_algos.extend(oco_res.get('data', []))
                if cond_res and cond_res.get('code') == '0': all_algos.extend(cond_res.get('data', []))

                for t in active_trades:
                    if t['status'] == 'active':
                        expected_inst_id = t.get('instId') or (t['symbol'].replace('USDT', '') + "-USDT-SWAP")
                        expected_side = 'sell' if t['direction'] == 'long' else 'buy'
                        matching_algos = [a for a in all_algos if a['instId'] == expected_inst_id and a['side'] == expected_side]
                        for a in matching_algos:
                            if a.get('slTriggerPx') and float(a['slTriggerPx']) > 0: t['sl'] = float(a['slTriggerPx'])
                            if a.get('tpTriggerPx') and float(a['tpTriggerPx']) > 0: t['tp1'] = float(a['tpTriggerPx'])
                        
                        # 🏃 DYNAMIC TRAILING STOP MECHANISM (動態追蹤止盈)
                        if t.get('tp1') and t.get('sl') and t.get('entry'):
                            # Original theoretical distance to TP1
                            if 'original_tp_dist' not in t:
                                t['original_tp_dist'] = abs(t['tp1'] - t['entry'])
                            
                            total_dist = t['original_tp_dist']
                            current_dist = abs(t['current'] - t['entry'])
                            is_profitable = (t['direction'] == 'long' and t['current'] > t['entry']) or (t['direction'] == 'short' and t['current'] < t['entry'])
                            
                            if is_profitable and total_dist > 0:
                                progress = current_dist / total_dist
                                
                                # Track High Water Mark (Highest progress reached)
                                highest_progress = t.get('highest_progress', 0.0)
                                if progress > highest_progress:
                                    t['highest_progress'] = progress
                                    highest_progress = progress
                                
                                new_sl = None
                                remove_tp = False
                                
                                # STAGE 1: BREAK-EVEN (60% to TP1)
                                if highest_progress >= 0.6 and highest_progress < 1.0:
                                    new_sl = t['entry']
                                    
                                # STAGE 2: REMOVE TP CEILING AND LOCK IN 50% PROFIT (100% to TP1)
                                elif highest_progress >= 1.0:
                                    # Trail SL by 40% of the TP distance behind the current high water mark
                                    locked_progress = highest_progress - 0.4
                                    # But never worse than 50% of original TP
                                    locked_progress = max(0.5, locked_progress)
                                    
                                    if t['direction'] == 'long':
                                        new_sl = t['entry'] + (total_dist * locked_progress)
                                    else:
                                        new_sl = t['entry'] - (total_dist * locked_progress)
                                    
                                    remove_tp = True

                                # APPLY CHANGES TO OKX
                                if new_sl:
                                    # Only update if the new_sl is strictly BETTER than the current SL
                                    is_better_sl = (t['direction'] == 'long' and new_sl > t['sl']) or (t['direction'] == 'short' and new_sl < t['sl'])
                                    
                                    # Allow 0.05% margin for floating point comparison
                                    sl_diff_pct = abs(t['sl'] - new_sl) / t['entry']
                                    
                                    if is_better_sl and sl_diff_pct > 0.0005:
                                        # REAL-TIME PRICE VALIDATION
                                        if (t['direction'] == 'long' and new_sl >= t['current']) or \
                                           (t['direction'] == 'short' and new_sl <= t['current']):
                                            print(f"[🚨 EMERGENCY] {t['symbol']} trailing SL {new_sl} already breached by market {t['current']}. Closing immediately!")
                                            try:
                                                ccxt_sym = (t.get('instId') or (t['symbol'].replace('USDT', '') + "-USDT-SWAP")).replace("-USDT-SWAP", "/USDT:USDT")
                                                close_side = 'sell' if t['direction'] == 'long' else 'buy'
                                                pos = okx.fetch_position(ccxt_sym)
                                                if pos and pos.get('contracts') and float(pos['contracts']) > 0:
                                                    okx.create_order(ccxt_sym, 'market', close_side, pos['contracts'], None, {'tdMode': 'cross', 'reduceOnly': True})
                                                    print(f"[🚨 EMERGENCY] {t['symbol']} closed successfully to prevent OKX Error 51278.")
                                                else:
                                                    print(f"[🚨 EMERGENCY] {t['symbol']} position not found or already closed.")
                                            except Exception as e:
                                                print(f"[ERROR] Emergency close failed for {t['symbol']}: {e}")
                                            # Skip amend as position is closed
                                            continue
                                            
                                        for a in matching_algos:
                                            try:
                                                ccxt_sym = f"{t['symbol'].replace('USDT', '')}/USDT:USDT"
                                                formatted_sl = okx.price_to_precision(ccxt_sym, new_sl)
                                                
                                                amend_payload = {
                                                    "instId": a['instId'],
                                                    "algoId": a['algoId'],
                                                    "newSlTriggerPx": formatted_sl,
                                                    "newSlOrdPx": "-1"
                                                }
                                                
                                                # If we are in Stage 2, push the TP out of the way!
                                                if remove_tp and not t.get('tp_removed'):
                                                    # Push TP to 300% distance to act as an emergency backup instead of a hard limit
                                                    if t['direction'] == 'long':
                                                        far_tp = t['entry'] + (total_dist * 3.0)
                                                    else:
                                                        far_tp = max(0.0001, t['entry'] - (total_dist * 3.0))
                                                    
                                                    formatted_far_tp = okx.price_to_precision(ccxt_sym, far_tp)
                                                    amend_payload["newTpTriggerPx"] = formatted_far_tp
                                                    amend_payload["newTpOrdPx"] = "-1"
                                                    t['tp_removed'] = True
                                                    print(f"[🚀 INFINITE RUN] {t['symbol']} TP ceiling removed! Let profits run.")

                                                # OKX Amend API
                                                res = okx.private_post_trade_amend_algos(amend_payload)
                                                if res.get('code') == '0':
                                                    print(f"[🛡️ TRAILING STOP] {t['symbol']} SL moved to: {formatted_sl} (Progress: {highest_progress*100:.1f}%)")
                                                    t['sl'] = new_sl
                                                else:
                                                    print(f"[ERROR] Amend failed for {t['symbol']}: {res}")
                                            except Exception as e:
                                                print(f"[ERROR] Failed to trail stop for {t['symbol']}: {e}")
                # Save the persisted state so we don't lose UI metadata on restart
                with open(TRADE_FILE, 'w') as f:
                    json.dump(active_trades, f)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(10)

@app.route('/api/trades')
def api_trades():
    global active_trades, potential_signals, account_data, market_radar_dict
    
    # Fetch real-time tickers for potential signals only (Lightweight)
    if potential_signals:
        symbols_to_fetch = [t['symbol'] + "/USDT:USDT" for t in potential_signals]
        try:
            tickers = okx.fetch_tickers(symbols_to_fetch)
            for t in potential_signals:
                sym = t['symbol'] + "/USDT:USDT"
                if sym in tickers and tickers[sym].get('last'):
                    t['current'] = float(tickers[sym]['last'])
        except Exception:
            pass
            
    # Deduplicate trades by symbol to prevent UI duplicates (e.g. multiple timeframes finding the same pattern)
    all_trades = active_trades + potential_signals
    deduped_trades = {}
    
    for t in all_trades:
        sym = t.get('symbol')
        if not sym: continue
        
        if sym not in deduped_trades:
            deduped_trades[sym] = t
        else:
            # Override potential with active
            if t.get('status') == 'active' and deduped_trades[sym].get('status') != 'active':
                deduped_trades[sym] = t
            # If both are active, prioritize algorithmic trades over 'Manual / Unsynced'
            elif t.get('status') == 'active' and deduped_trades[sym].get('status') == 'active':
                if t.get('pattern') != 'Manual / Unsynced':
                    deduped_trades[sym] = t
                    
    return jsonify({
        'trades': list(deduped_trades.values()),
        'radar': market_radar_dict,
        'account': account_data
    })

@app.route('/api/history')
def api_history():
    try:
        hist = okx.fetch_positions_history()
        
        # 100% Dashboard Sync: Only show trades that exist in our local trade_journal
        journal_pos_ids = {t.get('posId') for t in trade_journal if t.get('posId')}
        hist = [h for h in hist if h.get('id') in journal_pos_ids]
        
        for h in hist:
            sym = h['symbol'].replace('/', '').replace(':USDT', '')
            pos_id = h.get('id')
            # Match strategy from active_trades memory by posId first
            matched = next((t for t in reversed(active_trades) if t.get('posId') == pos_id), None)
            if not matched:
                # Fallback to symbol matching for old trades
                matched = next((t for t in reversed(active_trades) if t['symbol'] == sym), None)
            h['strategy'] = matched['strategy'] if matched and 'strategy' in matched else 'Manual'
        return jsonify({'history': hist[:50]})
    except Exception as e:
        print(f"History Sync Error: {e}")
        return jsonify({'history': []})

@app.route('/api/journal')
def api_journal():
    # Provide the actual trade_journal used by the ML core to ensure the UI perfectly matches reality.
    return jsonify({'journal': trade_journal})

@app.route('/api/intelligence')
def api_intelligence():
    # Provide the selection logic and the current active array of tracked coins
    return jsonify({
        'logic': '每 60 分鐘自動向 OKX 交易所請求前 100 大流動性合約，並透過高手獨家演算法(資金費率異常、相對大盤強弱、極端波動)篩選出最適合諧波交易的 30 大金剛陣容。',
        'symbols': [s.split('/')[0] for s in globals().get('global_symbols', [])],
        'categories': {k.split('/')[0]: v for k, v in globals().get('global_symbol_categories', {}).items()}
    })

if __name__ == '__main__':
    global_symbols, global_symbol_categories = get_top_symbols_and_categories()
    print(f"Tracking {len(global_symbols)} markets: {', '.join([s.split('/')[0] for s in global_symbols])}")
    
    print("Recovering open positions from OKX...")
    try:
        open_positions = okx.fetch_positions()
        for pos in open_positions:
            sym = pos['symbol'].replace('/', '').replace(':USDT', '')
            direction = pos.get('side', 'long')
            exists = any(t['symbol'] == sym and t['direction'] == direction and t['status'] == 'active' for t in active_trades)
            if not exists:
                active_trades.append({
                    "id": trade_id_counter,
                    "symbol": sym,
                    "direction": direction,
                    "pattern": "Recovered",
                    "status": "active",
                    "entry": float(pos.get('entryPrice', 0)),
                    "current": float(pos.get('markPrice', 0)),
                    "sl": 0,
                    "tp1": 0,
                    "pnl": float(pos.get('unrealizedPnl', 0)),
                    "rsi_on_entry": '--',
                    "trends": {},
                    "strategy": "Recovered"
                })
                trade_id_counter += 1
        print(f"Recovered {len(open_positions)} active positions.")
    except Exception as e:
        print(f"Failed to recover positions: {e}")
    def update_symbols_loop():
        global global_symbols
        while True:
            time.sleep(3600) # Refresh every 1 hour
            try:
                new_symbols, new_cats = get_top_symbols_and_categories()
                if new_symbols and len(new_symbols) > 0:
                    global_symbols = new_symbols
                    global_symbol_categories = new_cats
                    print(f"[Intelligence] Refreshed Top 30 Markets. Now tracking hottest coins.")
            except Exception as e:
                pass
                
    threading.Thread(target=update_symbols_loop, daemon=True).start()
    threading.Thread(target=background_sync_loop, daemon=True).start()
    
    # Start 4 Strategy Threads with High-Win Rate Trend-Following Parameters
    t1 = threading.Thread(target=run_strategy, args=('MacroSniper', '1h', 0.10, 0.02, '4h', 0.8), daemon=True)
    t2 = threading.Thread(target=run_strategy, args=('MeanReversion', '5m', 0.10, 0.015, '15m', 0.2), daemon=True)
    t3 = threading.Thread(target=run_strategy, args=('Contrarian', '5m', 0.10, 0.04, '15m', 0.2), daemon=True)
    t4 = threading.Thread(target=run_strategy, args=('SqueezeHunter', '15m', 0.10, 0.03, '1h', 0.5), daemon=True)
    
    t1.start()
    time.sleep(5)
    t2.start()
    time.sleep(5)
    t3.start()
    time.sleep(5)
    t4.start()
    # market_radar_dict handles it now
    print("Server running on http://127.0.0.1:5000")
    print("Open your browser and navigate to the link above to view the Dashboard.")
    app.run(port=5000, debug=False)
