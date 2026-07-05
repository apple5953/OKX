import ccxt
import os
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
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
