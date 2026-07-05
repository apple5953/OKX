import ccxt
import os
from dotenv import load_dotenv
import traceback

load_dotenv()

okx = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_API_SECRET'),
    'password': os.getenv('OKX_PASSPHRASE'),
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
okx.load_markets()

try:
    print("Testing market order with native OKX attachAlgoOrds...")
    # Using OKX native v5 syntax for attached TP/SL
    order = okx.create_order('BTC/USDT:USDT', 'market', 'buy', 0.01, None, {
        'attachAlgoOrds': [{
            'attachAlgoId': '1',
            'slTriggerPx': '50000',
            'slOrdPx': '-1',
            'tpTriggerPx': '100000',
            'tpOrdPx': '-1'
        }]
    })
    print(f"Order created: {order['id']}")
    
    # Try fetching open conditional orders
    orders = okx.fetch_open_orders('BTC/USDT:USDT')
    print(f"Found {len(orders)} total open orders.")
    print(orders)
        
    print("\nAttempting to close position to clean up...")
    okx.create_order('BTC/USDT:USDT', 'market', 'sell', 0.01, None, {'reduceOnly': True})
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
