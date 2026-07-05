import urllib.request, json
try:
    with urllib.request.urlopen('http://127.0.0.1:5000/api/trades') as r:
        t_data = json.loads(r.read().decode())
    with urllib.request.urlopen('http://127.0.0.1:5000/api/history') as r:
        h_data = json.loads(r.read().decode())
        
    trades = t_data.get('trades', [])
    hist = h_data.get('history', [])
    
    active_pnl = sum(t.get('pnl', 0) for t in trades if t.get('status') == 'active')
    realized_pnl = sum(float(h.get('info', {}).get('realizedPnl', 0)) for h in hist)
    
    print('--- PROFITABILITY SUMMARY ---')
    print(f'Active Unrealized PnL: {active_pnl:.2f}')
    print(f'Closed Realized PnL:   {realized_pnl:.2f}')
    print(f'Total Net PnL:         {active_pnl + realized_pnl:.2f}')
    print('\n--- ACTIVE TOP WINNERS ---')
    active_sorted = sorted([t for t in trades if t.get('status') == 'active'], key=lambda x: x.get('pnl', 0), reverse=True)
    for t in active_sorted[:5]:
        print(f"[{t.get('strategy')}] {t.get('symbol')} {t.get('direction')} | PnL: {t.get('pnl', 0):.2f}")
        
    print('\n--- ACTIVE TOP LOSERS ---')
    for t in active_sorted[-5:]:
        print(f"[{t.get('strategy')}] {t.get('symbol')} {t.get('direction')} | PnL: {t.get('pnl', 0):.2f}")
        
    print('\n--- CLOSED TRADES (Since Update) ---')
    if not hist:
        print("No closed trades yet.")
    for h in hist:
        print(f"[{h.get('strategy')}] {h.get('symbol')} | Realized PnL: {float(h.get('info', {}).get('realizedPnl', 0)):.2f}")

except Exception as e:
    print('Error:', e)
