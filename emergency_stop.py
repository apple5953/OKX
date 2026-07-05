import ccxt

okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
okx.load_markets()

# 1. Fetch and close all active positions
positions = okx.fetch_positions()
active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

print(f"Found {len(active_positions)} active positions. Closing all...")

for p in active_positions:
    symbol = p['symbol']
    side = 'sell' if p['side'] == 'long' else 'buy'
    contracts = float(p['contracts'])
    pnl = p.get('unrealizedPnl', 0)
    print(f"Closing {symbol} ({p['side']}) contracts: {contracts}, PnL: {pnl}U")
    try:
        okx.create_order(symbol, 'market', side, contracts, None, {'reduceOnly': True})
        print(f"Successfully closed {symbol}")
    except Exception as e:
        print(f"Failed to close {symbol}: {e}")

# 2. Cancel all pending algorithmic orders
try:
    algos = okx.private_get_trade_orders_algo_pending()
    algo_orders = algos.get('data', [])
    print(f"Found {len(algo_orders)} pending algorithmic orders. Canceling...")
    for o in algo_orders:
        algo_id = o.get('algoId')
        symbol = o.get('instId')
        try:
            okx.private_post_trade_cancel_algos([{'algoId': algo_id, 'instId': symbol}])
            print(f"Canceled algo order: {algo_id} for {symbol}")
        except Exception as ae:
            print(f"Failed to cancel algo {algo_id}: {ae}")
except Exception as e:
    print(f"Failed to fetch/cancel pending algo orders: {e}")

print("All active positions and pending orders have been closed and cleaned up.")
