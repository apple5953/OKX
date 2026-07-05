import sqlite3
from datetime import datetime

db_path = "trades.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- 1. TODAY'S TOTAL SUMMARY (2026-06-29) ---")
try:
    cursor.execute("""
        SELECT strategy, COUNT(*), SUM(pnl), AVG(pnl)
        FROM trade_history
        WHERE date(closed_at) = '2026-06-29' OR date(created_at) = '2026-06-29'
        GROUP BY strategy
    """)
    rows = cursor.fetchall()
    if not rows:
        print("No historical trades closed today on trades.db.")
    for row in rows:
        print(f"Strategy: {row[0]} | Count: {row[1]} | Net PnL: {row[2]:.4f} | Avg PnL: {row[3]:.4f}")
except Exception as e:
    print("Error querying trade_history table:", e)

print("\n--- 2. ACTIVE OPEN TRADES ---")
try:
    cursor.execute("SELECT id, symbol, direction, strategy, entry_price, current_price, pnl, status FROM active_trades")
    rows = cursor.fetchall()
    if not rows:
        print("No active open trades found right now.")
    for row in rows:
        print(f"ID: {row[0]} | Symbol: {row[1]} | Dir: {row[2]} | Strategy: {row[3]} | Entry: {row[4]} | Curr: {row[5]} | PnL: {row[6]} | Status: {row[7]}")
except Exception as e:
    print("Error querying active_trades table:", e)

conn.close()
