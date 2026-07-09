import os
import glob
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 1. Merge all node journal files
all_journals = glob.glob(str(BASE_DIR / 'journal_*.json'))
global_journal = []
for j_file in all_journals:
    try:
        with open(j_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                global_journal.extend(data)
    except Exception as e:
        print(f"Error reading {j_file}: {e}")

print(f"Total merged global trades: {len(global_journal)}")

# 2. Temporarily rename global_optimizer.json to bypass cache
optimizer_path = BASE_DIR / 'global_optimizer.json'
has_old = optimizer_path.exists()
if has_old:
    tmp_path = BASE_DIR / 'global_optimizer.json.tmp'
    if tmp_path.exists():
        tmp_path.unlink()
    optimizer_path.rename(tmp_path)

try:
    from server_core import state, strategies
    state.trade_journal = global_journal
    
    global_optimizer = {}
    for name in ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter']:
        perf = strategies.strategy_performance(name)
        opt = strategies.auto_tune_strategy_params(name, perf)
        global_optimizer[name] = opt
        print(f"[{name}] Optimized: {opt}")

    # Write global parameters
    with open(optimizer_path, 'w', encoding='utf-8') as f:
        json.dump(global_optimizer, f, indent=4, ensure_ascii=False)
    print("global_optimizer.json successfully generated.")
finally:
    # Cleanup temp file
    tmp_path = BASE_DIR / 'global_optimizer.json.tmp'
    if tmp_path.exists():
        tmp_path.unlink()
