import ccxt
import json
import uuid
import datetime
from pathlib import Path

# OKX API configuration (Sandbox/Demo mode)
okx = ccxt.okx({
    'apiKey': 'f1b9af15-e584-4911-b949-ff42168fd53c',
    'secret': 'A64C98D3C5E8B38A963566313BA31EF1',
    'password': '@Sweetsweet556',
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
okx.load_markets()

# We force select 4 liquid hot symbols to trigger 4 different modes immediately
test_configs = [
    {"symbol": "SOL/USDT:USDT", "strategy": "MacroSniper", "direction": "bullish", "pattern": "Macro Trend Long"},
    {"symbol": "SUI/USDT:USDT", "strategy": "SqueezeHunter", "direction": "bullish", "pattern": "Squeeze Breakout Long"},
    {"symbol": "BTC/USDT:USDT", "strategy": "MeanReversion", "direction": "bearish", "pattern": "RSI Mean Reversion Short"},
    {"symbol": "ETH/USDT:USDT", "strategy": "Contrarian", "direction": "bearish", "pattern": "MACD Divergence Short"}
]

print("Forcing trade trigger on OKX Sandbox...")

active_trades = []

for config in test_configs:
    symbol = config["symbol"]
    strat = config["strategy"]
    direction = config["direction"]
    side = "buy" if direction == "bullish" else "sell"
    pattern_name = config["pattern"]
    
    ticker = okx.fetch_ticker(symbol)
    current_price = float(ticker['last'])
    contract_size = float(okx.markets[symbol]['contractSize'])
    
    # Setup trade entry/stop/target distances (approx 1% to 2% out)
    if direction == "bullish":
        sl = current_price * 0.985
        tp = current_price * 1.03
    else:
        sl = current_price * 1.015
        tp = current_price * 0.97
        
    # Sizing for 1U margin at 20x leverage (Notional: ~15U)
    actual_leverage = 20
    target_notional = 15.0
    raw_size = target_notional / (current_price * contract_size)
    size = int(raw_size)
    if size < 1:
        size = 1
        
    cl_ord_id = f"H{strat}{uuid.uuid4().hex[:8]}"
    print(f"[{strat}] Placing market {side} order for {symbol} size {size}...")
    
    try:
        okx.set_leverage(actual_leverage, symbol)
    except Exception:
        pass
        
    try:
        order_res = okx.create_order(symbol, 'market', side, size, None, {
            'tdMode': 'cross',
            'clientOrderId': cl_ord_id,
            'stopLoss': {'triggerPrice': sl},
            'takeProfit': {'triggerPrice': tp}
        })
        
        display_sym = symbol.replace(':USDT', '').replace('/', '')
        trade_obj = {
            "id": int(datetime.datetime.now().timestamp() * 100) % 1000000,
            "symbol": display_sym,
            "direction": "long" if direction == "bullish" else "short",
            "pattern": pattern_name,
            "status": "active",
            "entry": current_price,
            "current": current_price,
            "sl": sl,
            "tp1": tp,
            "original_tp_dist": abs(tp - current_price),
            "original_sl_dist": abs(current_price - sl),
            "opened_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "pnl": 0.0,
            "rsi_on_entry": 50.0,
            "trends": {"15m": "neutral", "1h": "neutral"},
            "strategy": strat,
            "category": "Majors",
            "category_key": "Majors",
            "confidence": 1.0,
            "planned_margin": 60.0,
            "planned_notional": target_notional,
            "planned_leverage": actual_leverage,
            "leverage": actual_leverage,
            "initialMargin": 60.0,
            "notional": size * current_price * contract_size,
            "trailing_stage": "waiting",
            "protection_status": "confirmed",
            "runner_policy": "BE 15%, trail 10%"
        }
        active_trades.append(trade_obj)
        print(f"-> Successfully executed and tracking {symbol}")
    except Exception as e:
        print(f"-> Order failed for {symbol}: {e}")

# Save the active trades so server reads them instantly
try:
    trade_file = str(Path(__file__).resolve().parent / 'active_trades_macmini_01.json')
    with open(trade_file, 'w', encoding='utf-8') as f:
        json.dump(active_trades, f)
    print("Database sync completed. 4 forced trades are active.")
except Exception as e:
    print(f"Failed to sync json file: {e}")
