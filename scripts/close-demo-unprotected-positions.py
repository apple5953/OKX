import datetime
import json
import math
import pathlib
import sys
import time

PROJECT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from server_core import config
from server_core.execution import (
    fetch_exchange_max_contracts,
    _place_raw_trade_order,
    protection_algos_cover_size,
    protective_algo_targets,
)
from server_core.okx_client import okx
from server_core.utils import as_float, load_json_list, write_json_atomic

LOT_SIZE_CACHE = {}


def inst_id_to_symbol(inst_id):
    inst_id = str(inst_id or "").upper()
    if inst_id.endswith("-USDT-SWAP"):
        return inst_id.replace("-USDT-SWAP", "/USDT:USDT")
    return inst_id


def fetch_pending_algos():
    rows = []
    for ord_type in ("oco", "conditional"):
        response = okx.private_get_trade_orders_algo_pending(
            {"instType": "SWAP", "ordType": ord_type}
        )
        if not isinstance(response, dict) or str(response.get("code")) != "0":
            raise RuntimeError(f"OKX algo pending query failed: {ord_type}: {response}")
        rows.extend(row for row in response.get("data") or [] if isinstance(row, dict))
    return rows


def fetch_lot_size(inst_id):
    inst_id = str(inst_id or "").upper()
    if inst_id in LOT_SIZE_CACHE:
        return LOT_SIZE_CACHE[inst_id]
    lot_size = 0.0
    try:
        response = okx.public_get_public_instruments({
            "instType": "SWAP",
            "instId": inst_id,
        })
        rows = response.get("data") if isinstance(response, dict) else []
        if rows:
            lot_size = as_float(rows[0].get("lotSz"))
    except Exception:
        lot_size = 0.0
    LOT_SIZE_CACHE[inst_id] = lot_size
    return lot_size


def format_order_size(inst_id, size):
    size = abs(as_float(size))
    lot_size = fetch_lot_size(inst_id)
    if lot_size > 0:
        steps = math.floor((size / lot_size) + 1e-9)
        size = steps * lot_size
    if size <= 0:
        return 0.0
    text = format(size, ".12g")
    return as_float(text)


def classify_unprotected_positions():
    response = okx.private_get_account_positions({"instType": "SWAP"})
    positions = response.get("data") if isinstance(response, dict) else []
    algos = fetch_pending_algos()
    close_rows = []
    ok_rows = []

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
            "close_side": close_side,
            "position_size": abs(size),
            "protected_size": protected_size,
            "algo_count": len(targets),
            "reason": "ok",
        }
        if protection_algos_cover_size(targets, abs(size)):
            ok_rows.append(item)
            continue
        item["reason"] = "partial_tp_sl" if protected_size > 0 else "missing_tp_sl"
        close_rows.append(item)
    return close_rows, ok_rows


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
            "exit_reason": "repair_close_unprotected_demo_position",
            "sync_status": "repair_closed_on_okx",
            "emergency_close_submitted": True,
            "eligible_for_learning": False,
            "accounting_status": "quarantined",
            "accounting_reasons": ["unprotected repair close is not a strategy learning sample"],
        })
        key = str(repaired.get("lifecycle_id") or repaired.get("posId") or repaired.get("id") or "")
        if key not in existing_keys:
            journal_rows.append(repaired)
            existing_keys.add(key)
            added += 1

    write_json_atomic(config.TRADE_FILE, remaining)
    write_json_atomic(config.JOURNAL_FILE, journal_rows)
    return {"active_remaining": len(remaining), "journal_added": added}


def close_position_in_chunks(row):
    symbol = inst_id_to_symbol(row["instId"])
    remaining = abs(as_float(row["position_size"]))
    max_contracts = fetch_exchange_max_contracts(symbol, row["close_side"])
    if max_contracts == float("inf") or max_contracts <= 0:
        max_contracts = remaining
    chunk_size = max(1.0, max_contracts * 0.90)
    results = []

    while remaining > 0:
        size = min(remaining, chunk_size)
        # Keep OKX sz compact while preserving fractional contract positions.
        size = format_order_size(row["instId"], size)
        if size <= 0:
            raise RuntimeError(f"Cannot format valid lot-size close amount for {row['instId']}: remaining={remaining}")
        try:
            result = _place_raw_trade_order(
                symbol,
                "market",
                row["close_side"],
                size,
                None,
                {"reduceOnly": True, "posSide": "net"},
            )
            results.append({"size": size, "result": result})
            remaining = max(0.0, remaining - size)
            if remaining > 0:
                remaining = max(0.0, as_float(format_order_size(row["instId"], remaining)))
            time.sleep(0.12)
        except Exception as exc:
            text = str(exc)
            if "51202" in text and size > 1:
                chunk_size = max(1.0, size / 2.0)
                continue
            raise
    return results


def main():
    if not (config.DEMO_MODE or config.OKX_SANDBOX_MODE):
        raise SystemExit("Refusing to run outside OKX demo/sandbox mode")

    execute = "--yes" in sys.argv
    close_rows, ok_rows = classify_unprotected_positions()
    result = {
        "mode": "execute" if execute else "dry_run",
        "will_close_count": len(close_rows),
        "kept_ok_count": len(ok_rows),
        "will_close": close_rows,
        "kept_ok": ok_rows,
        "closed": [],
        "local_repair": None,
    }

    if not execute:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for row in close_rows:
        closed = dict(row)
        closed["orders"] = close_position_in_chunks(row)
        result["closed"].append(closed)

    result["local_repair"] = quarantine_local_lifecycles(result["closed"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
