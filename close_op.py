import ccxt
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
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
