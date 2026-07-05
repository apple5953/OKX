import json
from datetime import datetime

with open('trade_journal.json', 'r', encoding='utf-8') as f:
    journal = json.load(f)

# The trade_journal structure has active and history/closed trades
# Let's check keys and print summary
print("Journal keys:", journal.keys())

today_str = "2026-06-29"
closed_trades = journal.get("history", []) or journal.get("closed", [])
if not closed_trades and isinstance(journal, list):
    closed_trades = journal
elif isinstance(journal, dict):
    # Sometimes it's structured differently
    closed_trades = journal.get("trades", [])

print(f"Total trades in journal: {len(closed_trades)}")

today_trades = []
for t in closed_trades:
    closed_at = t.get("closed_at", "")
    created_at = t.get("created_at", "")
    # Check if closed or created today
    if today_str in closed_at or today_str in created_at:
        today_trades.append(t)

print(f"\n--- Today's ({today_str}) Trades Analysis (Count: {len(today_trades)}) ---")
stats = {}
for t in today_trades:
    strategy = t.get("strategy", "Unknown")
    pnl = float(t.get("pnl", 0.0) or 0.0)
    symbol = t.get("symbol", "Unknown")
    dir = t.get("direction", "Unknown")
    exit_type = t.get("exit_reason", t.get("exit_type", "Unknown"))
    
    if strategy not in stats:
        stats[strategy] = {"count": 0, "win": 0, "loss": 0, "pnl": 0.0, "details": []}
    
    stats[strategy]["count"] += 1
    stats[strategy]["pnl"] += pnl
    if pnl > 0:
        stats[strategy]["win"] += 1
    else:
        stats[strategy]["loss"] += 1
    stats[strategy]["details"].append((symbol, dir, pnl, exit_type))

for strat, data in stats.items():
    wr = (data["win"] / data["count"] * 100) if data["count"] > 0 else 0
    print(f"\n策略: {strat} | 總單數: {data['count']} | 勝率: {wr:.1f}% | 總收益: {data['pnl']:.4f} USDT")
    print("交易明細:")
    for sym, d, p, exit in data["details"]:
        print(f"  - {sym} ({d}): PnL: {p:+.4f} | 離場原因: {exit}")
