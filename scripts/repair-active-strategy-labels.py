from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server_core import config  # noqa: E402
from server_core.utils import infer_strategy_from_metadata, load_json_list, write_json_atomic  # noqa: E402


def main():
    path = Path(config.TRADE_FILE)
    rows = load_json_list(str(path), "active trades")
    if not rows:
        print(f"No active trades to repair: {path}")
        return 0

    backup = path.with_suffix(path.suffix + ".strategy-label-backup")
    shutil.copy2(path, backup)

    changed = 0
    valid = set(config.STRATEGY_PROFILES.keys())
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "active":
            continue
        current = str(row.get("strategy") or "")
        inferred = infer_strategy_from_metadata(row, fallback="")
        if inferred not in valid:
            continue
        if current != inferred:
            row["strategy"] = inferred
            row["strategy_mix"] = [inferred]
            if row.get("pattern") in [None, "", "Manual / Unsynced"]:
                row["pattern"] = f"{inferred} / live recovered"
            changed += 1
        elif row.get("strategy_mix") in [None, [], ["Manual"]]:
            row["strategy_mix"] = [inferred]
            changed += 1

    write_json_atomic(str(path), rows)
    print(f"Repaired {changed} active strategy label(s). Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
