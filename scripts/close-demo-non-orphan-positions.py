import sys
import datetime

from server_core import config
from server_core.execution import _place_raw_trade_order
from server_core.okx_client import okx, resolve_okx_inst_id
from server_core.utils import as_float, load_json_list, write_json_atomic


def quarantine_local_lifecycles(closed_rows):
    if not closed_rows:
        return {"active_remaining": None, "journal_added": 0}

    closed_inst_ids = {str(row.get("instId") or "").upper() for row in closed_rows}
    now = datetime.datetime.now(datetime.UTC).isoformat()
    active_rows = load_json_list(config.TRADE_FILE, "active trades")
    journal_rows = load_json_list(config.JOURNAL_FILE, "journal file")
    existing_keys = {
        str(row.get("lifecycle_id") or row.get("posId") or row.get("id") or "")
        for row in journal_rows
    }
    remaining = []
    added = 0

    for trade in active_rows:
        inst_id = str(trade.get("instId") or trade.get("posId") or trade.get("symbol") or "").upper()
        if inst_id not in closed_inst_ids:
            remaining.append(trade)
            continue

        repaired = dict(trade)
        repaired.update({
            "status": "closed",
            "closed_at": now,
            "exit_reason": "repair_reduce_only_close",
            "sync_status": "repair_closed_on_okx",
            "emergency_close_submitted": True,
            "eligible_for_learning": False,
            "accounting_status": "quarantined",
            "accounting_reasons": ["repair reduce-only close is not a strategy sample"],
        })
        key = str(repaired.get("lifecycle_id") or repaired.get("posId") or repaired.get("id") or "")
        if key not in existing_keys:
            journal_rows.append(repaired)
            existing_keys.add(key)
            added += 1

    write_json_atomic(config.TRADE_FILE, remaining)
    write_json_atomic(config.JOURNAL_FILE, journal_rows)
    return {"active_remaining": len(remaining), "journal_added": added}


def main():
    if "--yes" not in sys.argv:
        raise SystemExit("Refusing to close positions without --yes")

    excluded = {str(item).upper() for item in getattr(config, "ORPHAN_BYPASS_SYMBOLS", set())}
    response = okx.private_get_account_positions({"instType": "SWAP"})
    rows = response.get("data") if isinstance(response, dict) else []
    closed = []
    skipped = []

    for row in rows or []:
        inst_id = str(row.get("instId") or "").upper()
        size = as_float(row.get("pos"))
        if not inst_id or abs(size) <= 0:
            continue
        if inst_id in excluded:
            skipped.append(inst_id)
            continue

        symbol = inst_id
        if inst_id.endswith("-USDT-SWAP"):
            symbol = inst_id.replace("-USDT-SWAP", "/USDT:USDT")
        side = "sell" if size > 0 else "buy"
        result = _place_raw_trade_order(
            symbol,
            "market",
            side,
            abs(size),
            None,
            {"reduceOnly": True, "posSide": "net"},
        )
        closed.append({"instId": inst_id, "side": side, "size": abs(size), "result": result})

    local_repair = quarantine_local_lifecycles(closed)
    print({"closed": closed, "skipped": skipped, "local_repair": local_repair})


if __name__ == "__main__":
    main()
