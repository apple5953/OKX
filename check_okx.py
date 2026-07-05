import ccxt
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556'
})
okx.set_sandbox_mode(True)
positions = okx.fetch_positions()
print(f'Total Open Positions: {len(positions)}')
for p in positions:
    print(f"{p['symbol']} | PnL: {p.get('unrealizedPnl')} | Notional: {p.get('notional')}")
