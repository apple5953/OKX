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

# Close OP position immediately - margin ratio 84% is near liquidation
print("Closing OP position (instId: OP-USDT-SWAP)...")
try:
    positions = okx.fetch_positions(['OP/USDT:USDT'])
    for p in positions:
        contracts = float(p.get('contracts', 0))
        if contracts > 0:
            side = 'sell' if p['side'] == 'long' else 'buy'
            print(f"Closing {contracts} contracts of OP/USDT:USDT (was {p['side']}), margin ratio was 84%")
            okx.create_order('OP/USDT:USDT', 'market', side, contracts, None, {'reduceOnly': True})
            print("OP position closed successfully.")
        else:
            print("No OP position found.")
except Exception as e:
    print(f"Error: {e}")
