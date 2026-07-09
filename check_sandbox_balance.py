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

bal = okx.fetch_balance()
print('Sandbox Total Equity:', bal['info']['data'][0].get('totalEq'))
usdt_eq = 0
for d in bal['info']['data'][0].get('details', []):
    print(f"Asset: {d['ccy']} Eq: {d.get('eq')} Avail: {d.get('availEq')}")
    if d['ccy'] == 'USDT':
        usdt_eq = float(d.get('eq', 0))
print(f'USDT Balance: {usdt_eq}')
