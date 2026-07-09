import ccxt, json
okx = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY', ''),
    'secret': os.getenv('OKX_API_SECRET', os.getenv('OKX_SECRET', '')),
    'password': os.getenv('OKX_PASSPHRASE', os.getenv('OKX_PASSWORD', '')),
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)
hist = okx.fetch_positions_history(limit=50)

losses = [h for h in hist if float(h['info']['realizedPnl']) < 0]
wins = [h for h in hist if float(h['info']['realizedPnl']) >= 0]
print(f'Total: {len(hist)}, Wins: {len(wins)}, Losses: {len(losses)}')

for l in losses[:10]:
    info = l['info']
    print(f"[{info['instId']}] Dir: {info['direction']} | Open: {info['openAvgPx']} | Close: {info['closeAvgPx']} | PnL: {info['realizedPnl']} | Fee: {info['fee']} | Lever: {info['lever']}x")

print("\nRecent Wins:")
for w in wins[:5]:
    info = w['info']
    print(f"[{info['instId']}] Dir: {info['direction']} | Open: {info['openAvgPx']} | Close: {info['closeAvgPx']} | PnL: {info['realizedPnl']} | Fee: {info['fee']} | Lever: {info['lever']}x")
