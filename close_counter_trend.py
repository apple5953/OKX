import ccxt
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
okx.load_markets()

# Close all 4h-bear long positions (counter-trend trades causing losses)
# Keep: NEAR (4h bear but 1d bull + profitable), JUP (all bull), AVAX (in profit), CRWV (short = correct direction)
counter_trend = [
    'SUI/USDT:USDT',   # 4h bear, 1d bear, long = wrong direction, -12.8U
    'FIL/USDT:USDT',   # 4h bear, 1d bear, long = wrong direction
    'BNB/USDT:USDT',   # 4h bear, 1d bear, long = wrong direction
    'ADA/USDT:USDT',   # 4h bear, 1d bear, long = wrong direction
    'CRCL/USDT:USDT',  # 4h bear, 1d bear, long = wrong direction
]

for sym in counter_trend:
    try:
        positions = okx.fetch_positions([sym])
        for p in positions:
            contracts = float(p.get('contracts', 0))
            if contracts > 0:
                side = 'sell' if p['side'] == 'long' else 'buy'
                pnl = p.get('unrealizedPnl', '?')
                print(f"Closing counter-trend {sym} ({p['side']}) PnL={pnl}")
                okx.create_order(sym, 'market', side, contracts, None, {'reduceOnly': True})
                print(f"  CLOSED {sym}")
    except Exception as e:
        print(f"  ERROR {sym}: {e}")

print("\nDone. Keeping: NEAR (profitable), JUP (trend ok), AVAX (in profit), CRWV (short, correct)")
