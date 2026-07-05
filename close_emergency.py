import ccxt
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
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
