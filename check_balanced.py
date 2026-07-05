import json
import urllib.request

try:
    with urllib.request.urlopen('http://127.0.0.1:5000/api/history') as response:
        data = json.loads(response.read().decode())
        history = data.get('history', [])
        
    balanced_trades = [t for t in history if t.get('strategy') == 'Balanced']
    
    print(f'Total Balanced History Trades: {len(balanced_trades)}')
    for t in balanced_trades[:15]:
        info = t.get('info', {})
        print(f"[{t.get('symbol')}] Dir: {info.get('direction')} | Entry: {info.get('openAvgPx')} | Close: {info.get('closeAvgPx')} | PnL: {info.get('realizedPnl')} | Lever: {info.get('lever')}x")
        
    print('\nActive Balanced Trades:')
    with urllib.request.urlopen('http://127.0.0.1:5000/api/trades') as response:
        data = json.loads(response.read().decode())
        active = data.get('trades', [])
        for t in active:
            if t.get('strategy') == 'Balanced':
                print(f"[{t['symbol']}] Dir: {t['direction']} | Status: {t['status']} | Entry: {t['entry']} | SL: {t['sl']} | TP1: {t['tp1']} | Current: {t.get('current')}")
                
except Exception as e:
    print(e)
