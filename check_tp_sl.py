import urllib.request, json
with urllib.request.urlopen('http://127.0.0.1:5000/api/trades') as r:
    trades = json.loads(r.read().decode())['trades']
for t in trades[:20]:
    entry = float(t['entry'])
    sl = float(t['sl'])
    tp1 = float(t['tp1'])
    risk_pct = abs(entry - sl) / entry * 100
    reward_pct = abs(tp1 - entry) / entry * 100
    rr = reward_pct / risk_pct if risk_pct > 0 else 0
    print(f"{t['symbol']} {t.get('pattern')} | Risk: {risk_pct:.2f}% | Reward: {reward_pct:.2f}% | RR: {rr:.2f}")
