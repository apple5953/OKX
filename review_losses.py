import json
import urllib.request
import time
from datetime import datetime

try:
    with urllib.request.urlopen('http://127.0.0.1:5000/api/history') as response:
        data = json.loads(response.read().decode())
        history = data.get('history', [])
        
    losses = [t for t in history if float(t.get('info', {}).get('realizedPnl', 0)) < 0]
    
    print(f'Total Losing Trades in history: {len(losses)}')
    for t in losses[:20]:
        info = t.get('info', {})
        dt = datetime.fromtimestamp(int(info.get('uTime', 0))/1000).strftime('%m-%d %H:%M:%S')
        sym = t.get('symbol')
        strat = t.get('strategy', 'Unknown')
        direction = info.get('direction')
        open_px = float(info.get('openAvgPx', 0))
        close_px = float(info.get('closeAvgPx', 0))
        pnl = float(info.get('realizedPnl', 0))
        fee = float(info.get('fee', 0))
        
        # Determine if it was a true price loss or just fee loss
        gross = pnl - fee
        loss_type = "PRICE_LOSS" if gross < 0 else "FEE_LOSS"
        
        print(f"[{dt}] {strat} | {sym} {direction} | Open: {open_px:.5f} | Close: {close_px:.5f} | PnL: {pnl:.2f} (Fee: {fee:.2f}) | {loss_type}")
        
except Exception as e:
    print("Error:", e)
