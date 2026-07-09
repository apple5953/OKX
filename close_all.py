import ccxt
import os
okx = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY', ''),
    'secret': os.getenv('OKX_API_SECRET', os.getenv('OKX_SECRET', '')),
    'password': os.getenv('OKX_PASSPHRASE', os.getenv('OKX_PASSWORD', '')),
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
okx.load_markets()

print("Fetching open positions...")
try:
    positions = okx.fetch_positions()
    closed_count = 0
    for p in positions:
        symbol = p['symbol']
        side = 'sell' if p['side'] == 'long' else 'buy'
        contracts = float(p.get('contracts', 0))
        if contracts > 0:
            print(f"Closing {contracts} contracts of {symbol} (was {p['side']})")
            okx.create_order(symbol, 'market', side, contracts, None, {'reduceOnly': True})
            closed_count += 1
    print(f"Successfully closed {closed_count} positions.")
except Exception as e:
    print(f"Error: {e}")
