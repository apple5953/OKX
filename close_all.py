import ccxt
import os
import time
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
            # 針對可能過大的單，進行拆單平倉限制（OKX 模擬盤 HMSTR 最大一次限制常為 5000）
            chunk_size = 3000
            remaining = contracts
            while remaining > 0:
                trade_sz = min(chunk_size, remaining)
                print(f" - Sending close chunk: {trade_sz} contracts")
                okx.create_order(symbol, 'market', side, trade_sz, None, {'reduceOnly': True})
                remaining -= trade_sz
                time.sleep(0.2)
            closed_count += 1
    print(f"Successfully closed {closed_count} positions.")
except Exception as e:
    import traceback
    traceback.print_exc()
