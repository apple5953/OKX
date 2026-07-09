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

symbols_to_close = ['HBAR/USDT:USDT', 'GRAM/USDT:USDT']  # marginRatio >100%

for sym in symbols_to_close:
    try:
        positions = okx.fetch_positions([sym])
        for p in positions:
            contracts = float(p.get('contracts', 0))
            if contracts > 0:
                side = 'sell' if p['side'] == 'long' else 'buy'
                print(f"Emergency closing {contracts} of {sym} marginRatio={p.get('marginRatio')}")
                okx.create_order(sym, 'market', side, contracts, None, {'reduceOnly': True})
                print(f"Closed {sym}")
    except Exception as e:
        print(f"Error closing {sym}: {e}")
