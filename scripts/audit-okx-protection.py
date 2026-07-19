import json
import pathlib
import sys

PROJECT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from server_core.execution import protective_algo_targets, protection_algos_cover_size
from server_core.okx_client import okx
from server_core.utils import as_float


def fetch_pending_algos():
    rows = []
    for ord_type in ("oco", "conditional"):
        response = okx.private_get_trade_orders_algo_pending(
            {"instType": "SWAP", "ordType": ord_type}
        )
        if not isinstance(response, dict) or str(response.get("code")) != "0":
            raise RuntimeError(f"OKX algo pending query failed: {ord_type}: {response}")
        for row in response.get("data") or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def main():
    response = okx.private_get_account_positions({"instType": "SWAP"})
    positions = response.get("data") if isinstance(response, dict) else []
    algos = fetch_pending_algos()
    report = {
        "total_positions": 0,
        "ok": [],
        "partial": [],
        "missing": [],
    }

    for pos in positions or []:
        inst_id = str(pos.get("instId") or "").upper()
        size = as_float(pos.get("pos"))
        if not inst_id or abs(size) <= 0:
            continue
        direction = "long" if size > 0 else "short"
        close_side = "sell" if direction == "long" else "buy"
        targets = protective_algo_targets(algos, inst_id, close_side, None)
        protected_size = sum(abs(as_float(row.get("sz"))) for row in targets)
        item = {
            "instId": inst_id,
            "direction": direction,
            "position_size": abs(size),
            "protected_size": protected_size,
            "algo_count": len(targets),
        }
        report["total_positions"] += 1
        if protection_algos_cover_size(targets, abs(size)):
            report["ok"].append(item)
        elif protected_size > 0:
            report["partial"].append(item)
        else:
            report["missing"].append(item)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
