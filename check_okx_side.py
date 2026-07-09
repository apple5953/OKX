import ccxt
import os
okx = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY', ''),
    'secret': os.getenv('OKX_API_SECRET', os.getenv('OKX_SECRET', '')),
    'password': os.getenv('OKX_PASSPHRASE', os.getenv('OKX_PASSWORD', ''))
})
okx.set_sandbox_mode(True)
positions = okx.fetch_positions()
for p in positions[:2]:
    print(f"{p['symbol']} | Side: {p.get('side')} | Direction: {p.get('info', {}).get('posSide')}")
