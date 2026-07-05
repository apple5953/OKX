import ccxt

okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
okx.load_markets()

bal = okx.fetch_balance()
print('Sandbox Total Equity:', bal['info']['data'][0].get('totalEq'))
usdt_eq = 0
for d in bal['info']['data'][0].get('details', []):
    print(f"Asset: {d['ccy']} Eq: {d.get('eq')} Avail: {d.get('availEq')}")
    if d['ccy'] == 'USDT':
        usdt_eq = float(d.get('eq', 0))
print(f'USDT Balance: {usdt_eq}')
