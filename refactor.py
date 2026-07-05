with open('server.py', 'r', encoding='utf-8') as f:
    code = f.read()

import re

# 1. Add uuid to imports
code = code.replace('import ccxt', 'import ccxt\nimport uuid')

# 2. Replace trading_bot_loop signature and initial setup
old_loop_start = """def trading_bot_loop():
    global trade_id_counter, active_trades, potential_signals, market_radar
    market_radar = []
    timeframe = '1h'
    trend_timeframe = '4h'
    
    print(f"Trading bot starting up, fetching top 30 USDT Swap markets by volume...")
    symbols = get_top_symbols(30)
    print(f"Tracking {len(symbols)} markets: {', '.join([s.split('/')[0] for s in symbols])}")
    
    while True:
        try:
            print(f"[{time.strftime('%X')}] Scanning all {len(symbols)} markets...")"""

new_loop_start = """# Global symbols fetched once
global_symbols = []

def run_strategy(strategy_name, timeframe, tolerance, trend_tf):
    global trade_id_counter, active_trades, potential_signals, market_radar
    global global_symbols
    
    print(f"[{strategy_name}] Engine Started. ({timeframe} candles, {trend_tf} trend filter)")
    
    while True:
        try:
            symbols = global_symbols
            if not symbols:
                time.sleep(5)
                continue
                
            current_potentials = []
            current_radar = []"""

code = code.replace(old_loop_start, new_loop_start)

# 3. Replace parameters in scan and fetch
code = code.replace("df = fetch_data(symbol, timeframe)", "df = fetch_data(symbol, timeframe)") # Already timeframe
code = code.replace("patterns = scan_patterns(pivots, tolerance=0.15)", "patterns = scan_patterns(pivots, tolerance=tolerance)")

# 4. Replace trend filter logic
old_trend_filter = """htf_bull = (trends_dict['4h'] == 'bull')
                        htf_bear = (trends_dict['4h'] == 'bear')"""

new_trend_filter = """htf_bull = True
                        htf_bear = True
                        if trend_tf != 'none':
                            htf_bull = (trends_dict.get(trend_tf) == 'bull')
                            htf_bear = (trends_dict.get(trend_tf) == 'bear')"""

code = code.replace(old_trend_filter, new_trend_filter)

# 5. Add strategy to signal obj and already_active check
old_active_check = "already_active = any(t['symbol'] == display_sym and t['status'] == 'active' and t['pattern'] == p.pattern_name for t in active_trades)"
new_active_check = "already_active = any(t['symbol'] == display_sym and t['status'] == 'active' for t in active_trades)" # Prevent ANY strategy from opening the same symbol if active
code = code.replace(old_active_check, new_active_check)

old_signal_obj = """"rsi_on_entry": round(df['rsi'].iloc[-1], 1) if pd.notna(df['rsi'].iloc[-1]) else 50,
                            "trends": trends_dict
                        }"""
new_signal_obj = """"rsi_on_entry": round(df['rsi'].iloc[-1], 1) if pd.notna(df['rsi'].iloc[-1]) else 50,
                            "trends": trends_dict,
                            "strategy": strategy_name
                        }"""
code = code.replace(old_signal_obj, new_signal_obj)

# 6. Add clOrdId to okx.create_order
old_create_order = """okx.create_order(symbol, 'market', side, size, None, {
                                    'stopLoss': {'triggerPrice': plan['sl']},
                                    'takeProfit': {'triggerPrice': plan['tp1']}
                                })"""
new_create_order = """cl_ord_id = f"Harmonic_{strategy_name}_{uuid.uuid4().hex[:8]}"
                                okx.create_order(symbol, 'market', side, size, None, {
                                    'stopLoss': {'triggerPrice': plan['sl']},
                                    'takeProfit': {'triggerPrice': plan['tp1']},
                                    'clientOrderId': cl_ord_id
                                })"""
code = code.replace(old_create_order, new_create_order)

# 7. Update potential_signals append to be thread safe
old_append_potentials = """potential_signals = current_potentials
            # Sort radar by opportunity score descending
            market_radar = sorted(current_radar, key=lambda x: x['score'], reverse=True)"""
new_append_potentials = """# Merge potentials safely
            global potential_signals, market_radar
            potential_signals = [s for s in potential_signals if s.get('strategy') != strategy_name] + current_potentials
            # Merge radar safely
            market_radar = current_radar # Simplified for now"""
code = code.replace(old_append_potentials, new_append_potentials)

# 8. Thread start logic at bottom
old_threads = """if __name__ == '__main__':
    bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
    bot_thread.start()"""
new_threads = """if __name__ == '__main__':
    global_symbols = get_top_symbols(30)
    print(f"Tracking {len(global_symbols)} markets: {', '.join([s.split('/')[0] for s in global_symbols])}")
    
    # Start 3 Strategy Threads
    t1 = threading.Thread(target=run_strategy, args=('Strict', '15m', 0.15, '4h'), daemon=True)
    t2 = threading.Thread(target=run_strategy, args=('Balanced', '15m', 0.15, '1h'), daemon=True)
    t3 = threading.Thread(target=run_strategy, args=('Aggressive', '5m', 0.20, 'none'), daemon=True)
    
    t1.start()
    t2.start()
    t3.start()
    market_radar = []"""
code = code.replace(old_threads, new_threads)

with open('server_new.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Done writing server_new.py')
