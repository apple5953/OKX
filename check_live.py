import urllib.request, json

def fetch(url):
    try:
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("Error fetching:", e)
        return None

trades = fetch('http://127.0.0.1:5000/api/trades')
radar = fetch('http://127.0.0.1:5000/api/radar')

print('--- LIVE TRADES ---')
if trades and trades.get('trades'):
    for t in trades['trades']:
        print(f"[{t['strategy']}] {t['symbol']} {t['direction']} | Entry: {t['entry']} | Current: {t['current']} | PnL: {t['pnl']} | SL: {t['sl']} | TP1: {t['tp1']}")
else:
    print('No active trades at the moment.')

print('\n--- LIVE POTENTIAL SIGNALS (Radar) ---')
if radar and radar.get('potentials'):
    for p in radar['potentials']:
        print(f"[{p['strategy']}] {p['symbol']} {p['direction']} {p['pattern']} | Entry: {p['entry']}")
else:
    print('No potential signals detected yet.')
