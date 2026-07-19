import time
import datetime
import uuid
import threading
import json
from types import SimpleNamespace
import pandas as pd
import ccxt

from . import config
from . import state
from core.pivot_detector import detect_pivots
from core.pattern_scanner import scan_patterns
from core.trade_planner import build_trade_plan
from core.divergence import check_divergence
from .utils import (
    as_float, clamp, timestamp_ms, trade_open_timestamp_ms,
    history_event_key, write_json_atomic, infer_strategy_from_metadata
)
from .okx_client import (
    okx, sync_exchange_history, fetch_open_positions_snapshot,
    fetch_okx_account_snapshot, fetch_data, resolve_okx_inst_id, okx_timeframe_to_bar,
    capital_snapshot, normalize_position_side, position_is_open, fetch_market_quality
)
from .strategies import (
    strategy_profile, category_profile, category_has_keyword, strategy_category_permission,
    recent_strategy_stats, strategy_performance, auto_tune_strategy_params, apply_rehab_sizing_if_needed,
    get_confidence_score, build_sizing_plan, apply_exit_state_limits, tuned_runner_profile,
    runner_policy_text, fee_safe_stop_price, apply_adaptive_exits, create_mode_direct_setup,
    live_trade_permission, evaluate_mode_gate, infer_exit_reason, performance_block_reason,
    squeeze_hunter_release_ready
)
from .execution import (
    expected_trade_edge, risk_based_leverage_cap, execute_bounded_limit_entry, rebase_plan_to_fill,
    place_exact_fill_protection, emergency_close_unprotected, protective_algo_targets,
    protection_algos_cover_size, amend_protective_stop, fetch_exchange_max_contracts,
    _fetch_pending_protection_algos,
    protection_retry_delay, okx_order_failed, set_okx_leverage
)
from .market_router import route_symbol_market, router_allows_mode

def active_net_key(t):
    inst_id = t.get('instId') or ''
    symbol = t.get('symbol') or ''
    direction = normalize_position_side(t.get('direction'))
    return (inst_id if inst_id else symbol, direction)

def okx_position_not_found_error(code=None, message=None):
    code_text = str(code or '')
    message_text = str(message or '')
    lowered = message_text.lower()
    return (
        code_text == '51169'
        or '51169' in code_text
        or '51169' in message_text
        or 'no positions in this direction' in lowered
        or 'already closed' in lowered
        or 'does not exist' in lowered
    )

def close_orphan_trade_record(
    trade,
    reason='exchange_position_missing',
    protection_status='confirmed',
    protection_error=None,
):
    trade['status'] = 'closed'
    trade['exit_reason'] = reason
    trade['emergency_close_submitted'] = True
    trade['protection_status'] = protection_status
    trade['protection_error'] = protection_error
    trade['sync_status'] = 'closed_without_open_position'
    trade['trailing_stage'] = 'protection_reconciled'

def rebuild_protection_plan(trade, live_pos=None, journal_trade=None):
    trade = trade or {}
    live_pos = live_pos or {}
    journal_trade = journal_trade or {}
    direction = str(
        trade.get('direction')
        or live_pos.get('direction')
        or journal_trade.get('direction')
        or live_pos.get('side')
        or journal_trade.get('side')
        or ''
    ).lower()
    entry = as_float(
        live_pos.get('entryPrice')
        or live_pos.get('avgPx')
        or trade.get('entry')
        or journal_trade.get('entry')
    )
    sl = as_float(trade.get('sl') or journal_trade.get('sl'))
    tp1 = as_float(trade.get('tp1') or journal_trade.get('tp1'))
    safe_stop = fee_safe_stop_price(entry, direction) if entry > 0 and direction in {'long', 'short'} else 0.0

    if entry > 0 and direction in {'long', 'short'}:
        # First try to recover the original distance from the journal or the live record.
        sl_dist = as_float(trade.get('original_sl_dist') or journal_trade.get('original_sl_dist'))
        tp_dist = as_float(trade.get('original_tp_dist') or journal_trade.get('original_tp_dist'))
        if sl_dist > 0 and tp_dist > 0:
            if direction == 'long':
                sl = entry - sl_dist
                tp1 = entry + tp_dist
            else:
                sl = entry + sl_dist
                tp1 = entry - tp_dist
        elif sl > 0 and tp1 <= 0:
            risk_dist = abs(entry - sl)
            if risk_dist > 0:
                tp1 = entry + risk_dist * 1.8 if direction == 'long' else entry - risk_dist * 1.8
        elif tp1 > 0 and sl <= 0:
            reward_dist = abs(tp1 - entry)
            if reward_dist > 0:
                risk_dist = reward_dist / 1.8
                sl = entry - risk_dist if direction == 'long' else entry + risk_dist
        elif sl <= 0 or tp1 <= 0:
            liquidation = as_float(
                live_pos.get('liquidationPrice')
                or trade.get('liquidationPrice')
                or journal_trade.get('liquidationPrice')
            )
            fallback_risk = 0.0
            if liquidation > 0:
                if direction == 'long':
                    sl = max(liquidation * 1.01, entry * 0.98)
                    if sl >= entry:
                        sl = entry * 0.995
                else:
                    sl = min(liquidation * 0.99, entry * 1.02)
                    if sl <= entry:
                        sl = entry * 1.005
                fallback_risk = abs(entry - sl)
            if fallback_risk <= 0:
                fallback_risk = max(entry * 0.01, abs(entry) * 0.005)
                if direction == 'long':
                    sl = entry - fallback_risk
                else:
                    sl = entry + fallback_risk
            if sl > 0:
                tp1 = entry + fallback_risk * 1.8 if direction == 'long' else entry - fallback_risk * 1.8

    if entry <= 0 or sl <= 0 or tp1 <= 0 or direction not in {'long', 'short'}:
        return None

    if direction == 'long' and not (sl < entry < tp1):
        return None
    if direction == 'short' and not (tp1 < entry < sl):
        return None

    return {
        'entry': entry,
        'sl': sl,
        'tp1': tp1,
        'sl_dist_pct': abs(entry - sl) / entry if entry > 0 else 0.0,
        'tp_dist_pct': abs(tp1 - entry) / entry if entry > 0 else 0.0,
    }

def protection_status_rank(status):
    text = str(status or '').lower().strip()
    return {
        'confirmed': 3,
        'failed': 2,
        'pending': 1,
        'unconfirmed': 0,
        '': 0,
        'none': 0,
    }.get(text, 0)

def prefer_protection_status(current_status, recovered_status):
    if protection_status_rank(recovered_status) > protection_status_rank(current_status):
        return recovered_status
    return current_status

def live_position_has_protection(pos, protective_algos=None):
    """Return True only when we have evidence that OKX still has live TP/SL protection."""
    if protective_algos:
        return True
    info = pos.get('info') or {}
    close_order_algo = info.get('closeOrderAlgo') or []
    if isinstance(close_order_algo, dict):
        close_order_algo = [close_order_algo]
    for algo in close_order_algo:
        if not isinstance(algo, dict):
            continue
        if any(as_float(algo.get(key)) > 0 for key in ('slTriggerPx', 'tpTriggerPx', 'tpOrdPx')):
            return True
        if algo.get('algoId') or algo.get('ordId') or algo.get('clOrdId'):
            return True
    return False

def fetch_live_position_contracts(inst_id, direction):
    if config.MOCK_MODE:
        return 0.0
    expected_direction = normalize_position_side(direction)
    try:
        response = okx.private_get_account_positions({'instType': 'SWAP', 'instId': inst_id})
        rows = response.get('data') if isinstance(response, dict) else []
    except Exception as exc:
        print(f"[SAFETY] Failed to query live position size for {inst_id}: {exc}")
        return 0.0
    total = 0.0
    for row in rows or []:
        if str(row.get('instId') or '').upper() != str(inst_id or '').upper():
            continue
        size = as_float(row.get('pos'))
        if abs(size) <= 0:
            continue
        row_direction = 'long' if size > 0 else 'short'
        if normalize_position_side(row_direction) == expected_direction:
            total += abs(size)
    return total

def ensure_live_position_fully_protected(symbol, direction, plan, client_order_id, known_protection_ids=None):
    if config.MOCK_MODE:
        return {
            'protection_order_ids': [str(x) for x in (known_protection_ids or []) if x],
            'exchange_protected_size': 0.0,
            'exchange_position_size': 0.0,
        }
    inst_id = resolve_okx_inst_id(symbol)
    close_side = 'sell' if direction == 'long' else 'buy'
    known_ids = [str(x) for x in (known_protection_ids or []) if x]
    live_contracts = fetch_live_position_contracts(inst_id, direction)
    if live_contracts <= 0:
        return {
            'protection_order_ids': known_ids,
            'exchange_protected_size': 0.0,
            'exchange_position_size': 0.0,
        }

    def current_targets():
        algos = _fetch_pending_protection_algos()
        targets = protective_algo_targets(algos, inst_id, close_side, known_ids or None)
        if not targets:
            targets = protective_algo_targets(algos, inst_id, close_side, None)
        return targets

    targets = current_targets()
    protected_size = sum(abs(as_float(a.get('sz'))) for a in targets if isinstance(a, dict))
    if not protection_algos_cover_size(targets, live_contracts):
        missing_size = max(0.0, live_contracts - protected_size)
        if missing_size > 0:
            repair = place_exact_fill_protection(
                symbol,
                direction,
                missing_size,
                plan,
                f"{client_order_id}NET",
            )
            repair_id = str(repair.get('id') or '')
            if repair_id:
                known_ids.append(repair_id)
            targets = current_targets()
            protected_size = sum(abs(as_float(a.get('sz'))) for a in targets if isinstance(a, dict))

    if not protection_algos_cover_size(targets, live_contracts):
        raise RuntimeError(
            f"OKX net position protection incomplete: {inst_id} protected "
            f"{protected_size:g} / live {live_contracts:g} contracts"
        )

    live_ids = [
        str(a.get('algoId') or '')
        for a in targets
        if isinstance(a, dict) and str(a.get('algoId') or '')
    ]
    merged_ids = list(dict.fromkeys(known_ids + live_ids))
    return {
        'protection_order_ids': merged_ids,
        'exchange_protected_size': protected_size,
        'exchange_position_size': live_contracts,
    }

def normalize_symbol_key(symbol):
    return str(symbol or '').upper().replace('/', '').replace(':USDT', '').replace('-USDT-SWAP', 'USDT')

def normalize_position_side(value):
    text = str(value or '').lower().strip()
    if text in {'long', 'buy'}:
        return 'long'
    if text in {'short', 'sell'}:
        return 'short'
    if text == 'net':
        return 'net'
    return text

def is_known_strategy_name(strategy):
    return str(strategy or '') in config.STRATEGY_PROFILES

def recover_trade_lifecycle_from_journal(pos=None, direction=None):
    pos = pos or {}
    pos_id = str(pos.get('id') or pos.get('posId') or '')
    inst_id = str(pos.get('info', {}).get('instId', '') or pos.get('instId') or '')
    direction_text = str(direction or pos.get('side') or pos.get('direction') or '').lower()
    fallback_manual = None

    for source in (reversed(state.active_trades), reversed(state.trade_journal)):
        for row in source:
            if pos_id and str(row.get('posId') or '') != pos_id:
                continue
            row_inst = str(row.get('instId') or '')
            row_dir = str(row.get('direction') or '').lower()
            if inst_id and row_inst and inst_id != row_inst:
                continue
            if row_dir and direction_text and row_dir != direction_text:
                continue
            if str(row.get('strategy') or '') == 'Manual':
                if fallback_manual is None:
                    fallback_manual = row
                continue
            return row

    if fallback_manual is not None:
        return fallback_manual

    if inst_id and direction_text:
        for source in (reversed(state.active_trades), reversed(state.trade_journal)):
            for row in source:
                row_inst = str(row.get('instId') or '')
                row_dir = str(row.get('direction') or '').lower()
                if row_inst and inst_id and row_inst != inst_id:
                    continue
                if row_dir and direction_text and row_dir != direction_text:
                    continue
                if str(row.get('strategy') or '') not in ['', 'Manual', 'Mixed']:
                    return row
    return None

def reconcile_active_trades_with_journal(write_back=False):
    changed = False
    for trade in state.active_trades:
        if trade.get('status') != 'active':
            continue

        matched = recover_trade_lifecycle_from_journal(
            {
                'id': trade.get('posId'),
                'posId': trade.get('posId'),
                'instId': trade.get('instId'),
                'side': trade.get('direction'),
                'direction': trade.get('direction'),
            },
            trade.get('direction'),
        )
        if not matched:
            continue
        if not trade_records_look_like_same_lifecycle(trade, matched):
            continue

        matched_strategy = str(matched.get('strategy') or '')
        current_strategy = str(trade.get('strategy') or '')
        preserve_current_strategy = is_known_strategy_name(current_strategy) and matched_strategy in ['', 'Manual', 'Mixed']
        matched_protection_ok = (
            str(matched.get('protection_status') or '').lower() == 'confirmed'
            and as_float(matched.get('sl')) > 0
            and as_float(matched.get('tp1')) > 0
            and (bool(matched.get('exchange_protection_verified')) or config.MOCK_MODE)
        )

        for key in [
            'strategy', 'strategy_version', 'lifecycle_id', 'mode_reason',
            'entry_reason', 'runner_policy', 'optimizer', 'signal_candle',
            'original_tp_dist', 'original_sl_dist', 'filled_contracts',
            'half_tp_done', 'tp_removed', 'trailing_stage', 'current_r', 'highest_r',
            'highest_pnl', 'highest_progress', 'missing_protection_checks',
            'emergency_close_submitted', 'sync_status', 'protection_error',
        ]:
            if preserve_current_strategy and key in {
                'strategy', 'strategy_version', 'lifecycle_id', 'mode_reason',
                'entry_reason', 'runner_policy', 'optimizer', 'signal_candle',
                'original_tp_dist', 'original_sl_dist', 'filled_contracts',
                'current_r', 'highest_r', 'highest_pnl', 'highest_progress',
                'missing_protection_checks', 'emergency_close_submitted',
                'sync_status', 'protection_error',
            }:
                continue
            value = matched.get(key)
            if value not in [None, '', []] and trade.get(key) != value:
                trade[key] = value
                changed = True

        for key in ['entry']:
            current_value = as_float(trade.get(key))
            recovered_value = as_float(matched.get(key))
            if current_value <= 0 and recovered_value > 0:
                trade[key] = recovered_value
                changed = True

        if matched_protection_ok:
            if as_float(trade.get('sl')) <= 0 and as_float(matched.get('sl')) > 0:
                trade['sl'] = as_float(matched.get('sl'))
                changed = True
            if as_float(trade.get('tp1')) <= 0 and as_float(matched.get('tp1')) > 0:
                trade['tp1'] = as_float(matched.get('tp1'))
                changed = True
        else:
            if as_float(trade.get('sl')) != 0 or as_float(trade.get('tp1')) != 0:
                trade['sl'] = 0.0
                trade['tp1'] = 0.0
                changed = True
            if trade.get('protection_order_id') is not None:
                trade['protection_order_id'] = None
                changed = True
            if trade.get('protection_order_ids'):
                trade['protection_order_ids'] = []
                changed = True

        if matched_protection_ok and (as_float(trade.get('sl')) <= 0 or as_float(trade.get('tp1')) <= 0):
            rebuilt_plan = rebuild_protection_plan(trade, journal_trade=matched)
            if rebuilt_plan:
                if as_float(trade.get('sl')) <= 0:
                    trade['sl'] = rebuilt_plan['sl']
                    changed = True
                if as_float(trade.get('tp1')) <= 0:
                    trade['tp1'] = rebuilt_plan['tp1']
                    changed = True

        current_status = str(trade.get('protection_status') or '').lower()
        recovered_status = str(matched.get('protection_status') or '').lower()
        if recovered_status == 'confirmed' and not matched_protection_ok:
            recovered_status = 'pending'
        preferred_status = prefer_protection_status(current_status, recovered_status)
        if preferred_status and preferred_status != current_status:
            trade['protection_status'] = preferred_status
            changed = True
        elif current_status == 'confirmed' and not (trade.get('protection_order_id') or trade.get('protection_order_ids')):
            trade['protection_status'] = 'pending'
            changed = True
        elif not current_status and as_float(trade.get('sl')) > 0 and as_float(trade.get('tp1')) > 0:
            # A restored SL/TP pair is not proof that OKX still has live protection orders.
            trade['protection_status'] = 'pending'
            changed = True

        if not matched_protection_ok and trade.get('protection_status') == 'confirmed':
            trade['protection_status'] = 'pending'
            changed = True
        if not matched_protection_ok:
            if trade.get('exchange_protection_verified'):
                trade['exchange_protection_verified'] = False
                changed = True
            if as_float(trade.get('exchange_protected_size')) != 0:
                trade['exchange_protected_size'] = 0.0
                changed = True

        if matched.get('protection_error') is not None and trade.get('protection_error') != matched.get('protection_error'):
            trade['protection_error'] = matched.get('protection_error')
            changed = True

        if matched_protection_ok:
            recovered_ids = [str(x) for x in (matched.get('protection_order_ids') or []) if x]
            if recovered_ids:
                merged_ids = list(dict.fromkeys(
                    [str(x) for x in (trade.get('protection_order_ids') or []) if x] + recovered_ids
                ))
                if merged_ids != list(trade.get('protection_order_ids') or []):
                    trade['protection_order_ids'] = merged_ids
                    changed = True

            recovered_id = matched.get('protection_order_id')
            if recovered_id and trade.get('protection_order_id') != recovered_id:
                trade['protection_order_id'] = recovered_id
                changed = True

    if changed and write_back:
        write_json_atomic(config.TRADE_FILE, state.active_trades)
    return changed

def orphan_bypass_symbol(inst_id):
    return str(inst_id or '').upper() in {s.upper() for s in config.ORPHAN_BYPASS_SYMBOLS}

def annotate_orphan_positions(records):
    if not config.ORPHAN_BYPASS_ENABLED:
        return records

    for record in records:
        inst_id = record.get('instId') or (record.get('info') or {}).get('instId') or record.get('symbol')
        if not orphan_bypass_symbol(inst_id):
            record['orphan_bypass'] = False
            continue
        try:
            orders = okx.fetch_open_orders(record.get('symbol'))
            symbol_orders = [o for o in orders if (o.get('symbol') or '') == record.get('symbol')]
            reduce_only = bool(symbol_orders) and all(bool(o.get('reduceOnly')) for o in symbol_orders)
            book = okx.fetch_order_book(record.get('symbol'), limit=config.ORPHAN_ORDERBOOK_LIMIT)
            asks = book.get('asks') or []
            with state.orphan_position_lock:
                tracker = state.orphan_position_state.setdefault(inst_id, {'askless_count': 0})
                tracker['askless_count'] = tracker['askless_count'] + 1 if not asks else 0
                tracker['last_checked_at'] = datetime.datetime.now(datetime.UTC).isoformat()
                tracker['last_open_order_count'] = len(symbol_orders)
                tracker['last_reduce_only_only'] = reduce_only
                tracker['last_asks_empty'] = not asks
                askless_count = tracker['askless_count']
            is_orphan = (
                reduce_only
                and not asks
                and askless_count >= config.ORPHAN_ASKLESS_CONFIRMATIONS
            )
            record['orphan_bypass'] = is_orphan
            if is_orphan:
                record['non_blocking_active'] = True
                record['orphan_reason'] = (
                    f"orphan bypass: asks empty for {askless_count} checks and only reduce-only close orders remain"
                )
        except Exception as exc:
            record['orphan_bypass'] = False
            record['orphan_error'] = str(exc)
            if orphan_bypass_symbol(inst_id):
                record['orphan_bypass'] = True
                record['non_blocking_active'] = True
                record['orphan_reason'] = (
                    f"orphan bypass: unable to verify live order-book state ({exc})"
                )
    return records

def reserve_symbol_for_entry(symbol):
    key = normalize_symbol_key(symbol)
    with state.execution_state_lock:
        if key in state.reserved_symbols:
            return False, 'another strategy is already executing this symbol'
        if any(
            trade.get('status') == 'active'
            and not trade.get('non_blocking_active')
            and str(trade.get('sync_status') or '') != 'awaiting exact OKX close lifecycle'
            and normalize_symbol_key(trade.get('symbol') or trade.get('instId')) == key
            for trade in state.active_trades
        ):
            return False, 'one net lifecycle per symbol; existing position must close first'
        state.reserved_symbols.add(key)
    return True, key

def release_symbol_reservation(key):
    if not key:
        return
    with state.execution_state_lock:
        state.reserved_symbols.discard(key)

def active_unprotected_trades():
    blocked = []
    for trade in state.active_trades:
        if trade.get('status') != 'active' or trade.get('non_blocking_active'):
            continue
        if str(trade.get('sync_status') or '') == 'awaiting exact OKX close lifecycle':
            continue
        if orphan_bypass_symbol(trade.get('instId') or trade.get('posId') or trade.get('symbol')):
            continue
        status = str(trade.get('protection_status') or '').lower()
        exchange_verified = bool(trade.get('exchange_protection_verified')) or config.MOCK_MODE
        if (
            status != 'confirmed'
            or as_float(trade.get('sl')) <= 0
            or as_float(trade.get('tp1')) <= 0
            or not exchange_verified
        ):
            blocked.append(trade)
    return blocked

_exchange_unprotected_cache = {'at': 0.0, 'rows': []}

def exchange_unprotected_positions(ttl_seconds=6):
    """Audit OKX live positions directly, not only local active_trades state."""
    if config.MOCK_MODE:
        return []
    now = time.time()
    cached_at = as_float(_exchange_unprotected_cache.get('at'))
    if now - cached_at < ttl_seconds:
        return list(_exchange_unprotected_cache.get('rows') or [])

    try:
        response = okx.private_get_account_positions({'instType': 'SWAP'})
        positions = response.get('data') if isinstance(response, dict) else []
        algos = _fetch_pending_protection_algos()
    except Exception as exc:
        rows = [{
            'instId': 'OKX_AUDIT_UNAVAILABLE',
            'direction': 'unknown',
            'position_size': 0.0,
            'protected_size': 0.0,
            'algo_count': 0,
            'reason': str(exc),
        }]
        _exchange_unprotected_cache.update({'at': now, 'rows': rows})
        return list(rows)

    bad = []
    for row in positions or []:
        if not isinstance(row, dict):
            continue
        inst_id = str(row.get('instId') or '').upper()
        contracts = abs(as_float(row.get('pos')))
        if not inst_id or contracts <= 0:
            continue
        raw_side = normalize_position_side(row.get('posSide') or row.get('side'))
        if raw_side in ('long', 'short'):
            direction = raw_side
        else:
            direction = 'long' if as_float(row.get('pos')) > 0 else 'short'
        close_side = 'sell' if direction == 'long' else 'buy'
        targets = protective_algo_targets(algos, inst_id, close_side, None)
        protected_size = sum(
            abs(as_float(algo.get('sz')))
            for algo in targets
            if isinstance(algo, dict)
        )
        if not protection_algos_cover_size(targets, contracts):
            missing_size = max(0.0, contracts - protected_size)
            bad.append({
                'instId': inst_id,
                'direction': direction,
                'position_size': contracts,
                'protected_size': protected_size,
                'algo_count': len(targets),
                'missing_size': missing_size,
                'requires_manual_trade_confirmation': True,
                'repair_action': {
                    'type': 'place_or_confirm_reduce_only_tp_sl',
                    'instId': inst_id,
                    'direction': direction,
                    'close_side': close_side,
                    'size': missing_size or contracts,
                    'note': 'Needs explicit user approval before submitting OKX TP/SL protection.',
                },
            })

    _exchange_unprotected_cache.update({'at': now, 'rows': bad})
    return list(bad)

def safety_halt_reason():
    with state.execution_state_lock:
        return state.safety_halt_reason

def trigger_safety_halt(reason):
    reason_text = str(reason or 'unknown safety halt').strip()
    with state.execution_state_lock:
        if not state.safety_halt_reason:
            state.safety_halt_reason = reason_text
            state.safety_halt_at = time.time()
            state.ml_evolution_logs.append(f"[SAFETY HALT] {reason_text}")
            state.ml_evolution_logs = state.ml_evolution_logs[-60:]
    print(f"[SAFETY HALT] {reason_text}")

def emergency_close_or_halt(symbol, direction, close_size, context):
    try:
        ok, ec, em = emergency_close_unprotected(symbol, direction, close_size)
        if ok:
            print(f"{context}: emergency close succeeded.")
            return True
        if okx_position_not_found_error(ec, em):
            print(f"{context}: position already closed ({ec}).")
            return True
        message = f"{context}: emergency close failed for {symbol}: code={ec} {em}"
        trigger_safety_halt(message)
        print(f"[URGENT] {message}")
        return False
    except Exception as emergency_err:
        message = f"{context}: emergency close raised for {symbol}: {emergency_err}"
        trigger_safety_halt(message)
        print(f"[URGENT] {message}")
        return False

def has_mergeable_value(val):
    if val is None:
        return False
    if isinstance(val, str):
        return val != ''
    if isinstance(val, (list, tuple, set, dict)):
        return len(val) > 0

    size = getattr(val, 'size', None)
    if isinstance(size, int):
        return size > 0
    empty = getattr(val, 'empty', None)
    if isinstance(empty, bool):
        return not empty

    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)):
        return val != 0
    return True

def merge_active_trade(existing, incoming):
    strategies = set()
    for row in (existing, incoming):
        inferred = infer_strategy_from_metadata(row, fallback='')
        if is_known_strategy_name(inferred):
            strategies.add(inferred)
        for mixed in row.get('strategy_mix') or []:
            if is_known_strategy_name(mixed):
                strategies.add(str(mixed))

    existing['add_count'] = int(existing.get('add_count') or 1) + int(incoming.get('add_count') or 1)
    existing['strategy_mix'] = sorted(strategies)
    if len(strategies) > 1:
        existing['strategy'] = 'Mixed'
        existing['mode_reason'] = 'net position combined from multiple strategy entries'
    elif strategies:
        existing['strategy'] = next(iter(strategies))
    else:
        existing['strategy'] = infer_strategy_from_metadata(incoming, existing)

    protection_ids = set(existing.get('protection_order_ids') or [])
    protection_ids.update(incoming.get('protection_order_ids') or [])
    for row in [existing, incoming]:
        if row.get('protection_order_id'):
            protection_ids.add(str(row['protection_order_id']))
    if protection_ids:
        existing['protection_order_ids'] = sorted(protection_ids)

    strategy_versions = set(existing.get('strategy_versions') or [])
    strategy_versions.update(incoming.get('strategy_versions') or [])
    for row in [existing, incoming]:
        if row.get('strategy_version'):
            strategy_versions.add(str(row['strategy_version']))
    if strategy_versions:
        existing['strategy_versions'] = sorted(strategy_versions)
        existing['strategy_version'] = (
            next(iter(strategy_versions)) if len(strategy_versions) == 1 else 'mixed-version'
        )

    for key in [
        'posId', 'instId', 'entry', 'current', 'sl', 'tp1', 'pnl', 'percentage',
        'leverage', 'initialMargin', 'notional', 'liquidationPrice', 'marginRatio',
        'runner_policy', 'optimizer', 'sizing_plan', 'planned_margin',
        'planned_notional', 'planned_leverage', 'protection_order_id',
        'protection_order_ids',
        'missing_protection_checks', 'emergency_close_submitted', 'sync_status',
        'trailing_stage', 'entry_reason', 'mode_reason', 'signal_candle',
        'original_tp_dist', 'original_sl_dist', 'filled_contracts',
        'highest_progress', 'highest_r', 'highest_pnl', 'current_r',
    ]:
        val = incoming.get(key)
        if has_mergeable_value(val):
            existing[key] = val

    existing_verified = bool(existing.get('exchange_protection_verified')) or config.MOCK_MODE
    incoming_verified = bool(incoming.get('exchange_protection_verified')) or config.MOCK_MODE
    existing_status = str(existing.get('protection_status') or '').lower()
    incoming_status = str(incoming.get('protection_status') or '').lower()
    if existing_status == 'confirmed' and not existing_verified:
        existing_status = 'pending'
    if incoming_status == 'confirmed' and not incoming_verified:
        incoming_status = 'pending'
    existing['exchange_protection_verified'] = bool(
        existing.get('exchange_protection_verified') or incoming.get('exchange_protection_verified')
    )
    existing['protection_status'] = prefer_protection_status(existing_status, incoming_status)
    if (
        existing['protection_status'] == 'confirmed'
        and not existing.get('exchange_protection_verified')
        and not config.MOCK_MODE
    ):
        existing['protection_status'] = 'pending'
    if incoming.get('protection_error') not in [None, '']:
        existing['protection_error'] = incoming.get('protection_error')

    existing['status'] = 'active'
    existing['last_signal_id'] = incoming.get('id', existing.get('last_signal_id'))
    return existing

def collapse_active_records(records):
    collapsed = []
    index = {}
    for t in records:
        if t.get('status') != 'active':
            collapsed.append(t)
            continue
        key = active_net_key(t)
        if key in index:
            merge_active_trade(index[key], t)
        else:
            index[key] = dict(t)
            collapsed.append(index[key])
    return collapsed

def live_position_key(pos):
    info = pos.get('info') or {}
    inst_id = str(pos.get('instId') or info.get('instId') or '')
    symbol = normalize_symbol_key(pos.get('symbol'))
    return (inst_id if inst_id else symbol, normalize_position_side(pos.get('direction') or pos.get('side')))

def normalize_okx_position(pos):
    info = pos.get('info') or {}
    raw_symbol = str(pos.get('symbol') or pos.get('instId') or info.get('instId') or '')
    inst_id = str(info.get('instId') or pos.get('instId') or raw_symbol)
    pos_qty = as_float(pos.get('contracts') or pos.get('pos') or info.get('pos'))
    raw_side = pos.get('side') or pos.get('posSide') or info.get('posSide')
    side = normalize_position_side(
        raw_side if str(raw_side or '').lower() not in {'', 'net'} else ('long' if pos_qty >= 0 else 'short')
    )
    contracts = pos_qty
    mark_price = as_float(pos.get('markPrice') or pos.get('markPx'))
    entry_price = as_float(pos.get('entryPrice') or pos.get('avgPx') or info.get('avgPx'))
    pnl = as_float(pos.get('unrealizedPnl', pos.get('upl', 0.0)))
    normalized = {
        'id': pos.get('id'),
        'posId': pos.get('id'),
        'instId': inst_id,
        'symbol': normalize_symbol_key(raw_symbol),
        'raw_symbol': raw_symbol,
        'direction': side,
        'status': 'active',
        'source': 'okx_live',
        'entry': entry_price,
        'current': mark_price,
        'pnl': pnl,
        'percentage': as_float(pos.get('percentage', pos.get('uplRatio', 0.0))),
        'leverage': pos.get('leverage') or pos.get('lever'),
        'initialMargin': as_float(pos.get('initialMargin')),
        'notional': as_float(pos.get('notional') or pos.get('notionalUsd')),
        'liquidationPrice': as_float(pos.get('liquidationPrice') or pos.get('liqPx')),
        'marginRatio': as_float(pos.get('marginRatio')),
        'contracts': contracts,
        'availPos': as_float(pos.get('availPos') or info.get('availPos')),
        'marginMode': info.get('mgnMode') or pos.get('marginMode') or pos.get('mgnMode'),
        'info': info or dict(pos),
    }
    if normalized['entry'] == 0:
        normalized['entry'] = as_float(info.get('avgPx') or pos.get('avgPx'))
    return normalized

def fetch_live_okx_positions():
    try:
        return [normalize_okx_position(p) for p in fetch_open_positions_snapshot()]
    except Exception as e:
        print(f"[live_positions ERROR] {e}")
        return []

def overlay_live_position_metadata(live_pos, tracked_trade=None, copy_risk_metadata=False):
    record = dict(live_pos)
    if tracked_trade:
        record['trade_id'] = tracked_trade.get('id')
        for key in [
            'strategy', 'pattern', 'trailing_stage', 'runner_policy',
            'tp_removed',
            'sync_status', 'strategy_version', 'lifecycle_id', 'last_signal_id',
            'block_reason', 'entry_reason', 'mode_reason', 'highest_pnl',
            'highest_r', 'current_r',
        ]:
            value = tracked_trade.get(key)
            if value not in [None, '']:
                record[key] = value
        if copy_risk_metadata:
            for key in [
                'protection_status', 'protection_error', 'missing_protection_checks',
                'protection_order_id', 'protection_order_ids', 'tp1', 'sl',
                'exchange_protection_verified', 'exchange_protected_size',
                'exchange_position_size',
            ]:
                value = tracked_trade.get(key)
                if value not in [None, '', []]:
                    record[key] = value
        else:
            tracked_status = str(tracked_trade.get('protection_status') or '').lower()
            if tracked_status in {'failed', 'pending', 'unconfirmed'}:
                for key in ['protection_status', 'protection_error', 'missing_protection_checks']:
                    value = tracked_trade.get(key)
                    if value not in [None, '']:
                        record[key] = value
            elif tracked_status == 'confirmed':
                record['protection_status'] = 'unconfirmed'
                record['protection_error'] = 'OKX TP/SL protection has not been exchange-verified in this snapshot'
        if tracked_trade.get('source'):
            record['trade_source'] = tracked_trade.get('source')
        inferred_strategy = infer_strategy_from_metadata(tracked_trade, record, fallback='')
        if is_known_strategy_name(inferred_strategy):
            record['strategy'] = inferred_strategy
            record['strategy_mix'] = [inferred_strategy]
            if record.get('pattern') in [None, '', 'Manual / Unsynced']:
                record['pattern'] = f'{inferred_strategy} / live recovered'
    else:
        record.update({
            'strategy': 'ExternalLive',
            'pattern': 'live position without journal record',
            'trailing_stage': 'waiting',
            'runner_policy': None,
            'protection_status': 'unconfirmed',
            'protection_error': None,
            'external_orphan': True,
            'eligible_for_learning': False,
            'sample_exclusion_reason': 'OKX live position has no matching bot lifecycle record',
        })
        record.setdefault('entry_reason', 'OKX live position, no journal record found for this symbol')
    record['status'] = 'active'
    return record

def tracked_trade_matches_live_position(tracked_trade, live_pos):
    if not tracked_trade or not live_pos:
        return False
    tracked_inst = str(tracked_trade.get('instId') or '').upper()
    live_inst = str(live_pos.get('instId') or (live_pos.get('info') or {}).get('instId') or '').upper()
    if tracked_inst and live_inst and tracked_inst != live_inst:
        return False
    tracked_dir = str(tracked_trade.get('direction') or '').lower()
    live_dir = str(live_pos.get('direction') or live_pos.get('side') or '').lower()
    if tracked_dir and live_dir and tracked_dir != live_dir:
        return False

    tracked_entry = as_float(tracked_trade.get('entry'))
    live_entry = as_float(live_pos.get('entryPrice') or live_pos.get('avgPx') or live_pos.get('entry'))
    if tracked_entry > 0 and live_entry > 0:
        entry_delta = abs(tracked_entry - live_entry)
        entry_scale = max(abs(tracked_entry), abs(live_entry), 1.0)
        if entry_delta / entry_scale > 0.15 and entry_delta > entry_scale * 0.05:
            return False
    return True

def trade_records_look_like_same_lifecycle(left_trade, right_trade, entry_tolerance=0.08):
    """Reject journal/active-trade crossovers unless they look like the same live lifecycle."""
    if not left_trade or not right_trade:
        return False

    left_inst = str(left_trade.get('instId') or left_trade.get('symbol') or '').upper()
    right_inst = str(right_trade.get('instId') or right_trade.get('symbol') or '').upper()
    if left_inst and right_inst and left_inst != right_inst:
        return False

    left_dir = str(left_trade.get('direction') or left_trade.get('side') or '').lower()
    right_dir = str(right_trade.get('direction') or right_trade.get('side') or '').lower()
    if left_dir and right_dir and left_dir != right_dir:
        return False

    left_entry = as_float(
        left_trade.get('entry')
        or left_trade.get('entryPrice')
        or left_trade.get('avgPx')
    )
    right_entry = as_float(
        right_trade.get('entry')
        or right_trade.get('entryPrice')
        or right_trade.get('avgPx')
    )
    if left_entry > 0 and right_entry > 0:
        entry_delta = abs(left_entry - right_entry)
        entry_scale = max(abs(left_entry), abs(right_entry), 1.0)
        if entry_delta / entry_scale > entry_tolerance:
            return False

    return True

def build_live_trade_snapshot(tracked_records=None, live_positions=None, include_potentials=True):
    tracked_records = tracked_records if tracked_records is not None else collapse_active_records(state.active_trades)
    live_positions = live_positions if live_positions is not None else fetch_live_okx_positions()
    tracked_index = {
        active_net_key(t): dict(t)
        for t in tracked_records
        if t.get('status') == 'active'
    }

    # Build fallback: instId -> most recent journal strategy (from any closed rows)
    journal_strategy_map = {}
    for row in (state.trade_journal or []):
        strat = row.get('strategy')
        if not strat or strat == 'Manual':
            continue
        inst = row.get('instId') or row.get('symbol') or ''
        if inst:
            journal_strategy_map[inst] = strat  # last-write wins (sorted by file order)

    merged = []
    for pos in live_positions:
        key = live_position_key(pos)
        tracked = tracked_index.get(key)
        if tracked and tracked_trade_matches_live_position(tracked, pos):
            merged.append(overlay_live_position_metadata(pos, tracked))
        else:
            # Fallback: try to recover strategy from journal by instId
            inst_id = pos.get('instId') or (pos.get('info') or {}).get('instId') or ''
            fallback_strategy = journal_strategy_map.get(inst_id)
            if fallback_strategy:
                fake_tracked = {
                    'strategy': fallback_strategy,
                    'pattern': f'{fallback_strategy} / 甇瑕閮??Ｗ儔',
                    'trailing_stage': 'waiting',
                    'sync_status': 'journal_recovered',
                }
                merged.append(overlay_live_position_metadata(pos, fake_tracked))
            else:
                merged.append(overlay_live_position_metadata(pos, None))
    merged = annotate_orphan_positions(merged)
    if include_potentials:
        merged.extend([dict(t) for t in state.potential_signals if t.get('symbol') and t.get('status') != 'active'])
    return merged


def build_live_trade_snapshot_safe(tracked_records=None, live_positions=None, include_potentials=True):
    tracked_records = tracked_records if tracked_records is not None else collapse_active_records(state.active_trades)
    live_positions = live_positions if live_positions is not None else fetch_live_okx_positions()
    tracked_index = {
        active_net_key(t): dict(t)
        for t in tracked_records
        if t.get('status') == 'active'
    }

    merged = []
    for pos in live_positions:
        key = live_position_key(pos)
        tracked = tracked_index.get(key)
        if tracked and tracked_trade_matches_live_position(tracked, pos):
            copy_risk = (
                str(tracked.get('protection_status') or '').lower() == 'confirmed'
                and bool(tracked.get('exchange_protection_verified') or config.MOCK_MODE)
                and as_float(tracked.get('sl')) > 0
                and as_float(tracked.get('tp1')) > 0
            )
            merged.append(overlay_live_position_metadata(pos, tracked, copy_risk_metadata=copy_risk))
        else:
            merged.append(overlay_live_position_metadata(pos, None))

    merged = annotate_orphan_positions(merged)
    if include_potentials:
        merged.extend([dict(t) for t in state.potential_signals if t.get('symbol') and t.get('status') != 'active'])
    return merged


build_live_trade_snapshot = build_live_trade_snapshot_safe


def rotating_strategy_symbols(strategy_name, symbols):
    rows = list(symbols or [])
    limit = int(getattr(config, 'SCAN_SYMBOLS_PER_LOOP', 0) or 0)
    if limit <= 0 or len(rows) <= limit:
        return rows
    cursor = int(state.strategy_scan_cursors.get(strategy_name, 0) or 0)
    selected = [rows[(cursor + offset) % len(rows)] for offset in range(limit)]
    state.strategy_scan_cursors[strategy_name] = (cursor + limit) % len(rows)
    return selected


def run_strategy(strategy_name, timeframe, tolerance, sl_buffer_pct, trend_tf, target_rr):
    
    print(f"[{strategy_name}] Engine Started. ({timeframe} candles, {trend_tf} trend filter)")
    
    if timeframe.endswith('m'):
        tf_minutes = int(timeframe[:-1])
    elif timeframe.endswith('h'):
        tf_minutes = int(timeframe[:-1]) * 60
    else:
        tf_minutes = 5
    COOLDOWN_SECONDS = 10
    
    while True:
        try:
            symbols = rotating_strategy_symbols(strategy_name, state.global_symbols)
            state.strategy_radar_status[strategy_name] = {
                'status': 'scanning' if symbols else 'waiting_for_universe',
                'updated_at': datetime.datetime.now(datetime.UTC).isoformat(),
                'strategy': strategy_name,
                'timeframe': timeframe,
                'trend_filter': trend_tf,
                'symbols_this_loop': len(symbols),
                'universe_size': len(state.global_symbols or []),
                'universe_source': getattr(state, 'market_universe_source', 'unknown'),
                'universe_updated_at': getattr(state, 'market_universe_updated_at', None),
            }
            if not symbols:
                time.sleep(5)
                continue
                
            current_potentials = []
            current_radar = []
            
            for symbol in symbols:
                try:
                    # Apply Coin-Specific Profiles based on Dynamic Categories
                    cat = state.global_symbol_categories.get(symbol, 'Uncategorized')
                    
                    # Mode Alignment (Soft Whitelisting)
                    alignment_penalty = 1.0
                    if strategy_name == 'MeanReversion' and ('Squeeze' in cat):
                        alignment_penalty = 0.3
                    elif strategy_name == 'Contrarian' and not ('Oversold' in cat or 'Volatility' in cat):
                        alignment_penalty = 0.6
                    elif strategy_name == 'SqueezeHunter' and not ('Squeeze' in cat):
                        alignment_penalty = 0.4

                    # Fetch MTF Trend Data (1H, 4H, 1D)
                    def get_trend(sym, tf):
                        d = fetch_data(sym, tf, limit=500)
                        if d.empty or len(d) < 202: return 'neutral'
                        closed = d.iloc[:-1]
                        e50 = closed['close'].ewm(span=50, adjust=False).mean().iloc[-1]
                        e200 = closed['close'].ewm(span=200, adjust=False).mean().iloc[-1]
                        current_price = closed['close'].iloc[-1]
                        
                        if current_price > e200 and e50 > e200:
                            return 'bull'
                        elif current_price < e200 and e50 < e200:
                            return 'bear'
                        else:
                            return 'neutral' # Choppy transition phase, do not trade

                    trends_dict = {
                        '15m': get_trend(symbol, '15m'),
                        '1h': get_trend(symbol, '1h'),
                        '4h': get_trend(symbol, '4h'),
                        '1d': get_trend(symbol, '1d')
                    }
                    # MTF Trend Resonance (Triple Screen Logic)
                    # We dynamically select the macro timeframe (Factor of 4-6x higher than intermediate)
                    if timeframe == '5m': macro_tf = '1h'
                    elif timeframe == '15m': macro_tf = '4h'
                    elif timeframe == '1h': macro_tf = '1d'
                    else: macro_tf = '4h'
                    
                    trend_val = trends_dict.get(trend_tf, 'neutral')
                    macro_val = trends_dict.get(macro_tf, 'neutral')
                    
                    if trend_tf == 'none':
                        htf_bull = True
                        htf_bear = True
                    else:
                        # BOTH the strategy's specific trend AND the dynamic macro trend must not contradict
                        htf_bull = (trend_val == 'bull' and macro_val != 'bear')
                        htf_bear = (trend_val == 'bear' and macro_val != 'bull')
                    
                    # Fetch Entry Data
                    df = fetch_data(symbol, timeframe)
                    if df.empty or len(df) < 52:
                        continue
                    live_price = as_float(df['close'].iloc[-1])
                    signal_df = df.iloc[:-1].copy(deep=False)
                    
                    # Profit-first entry filter: require enough profit room to absorb fees/slippage.
                    min_profit = config.PROFIT_FIRST_MIN_ROOM_BY_TIMEFRAME.get(timeframe, 0.0035)
                    
                    # Calculate True ATR % (Average True Range as a percentage of price over last 14 candles)
                    recent_df = signal_df.tail(14)
                    if not recent_df.empty:
                        avg_range = (recent_df['high'] - recent_df['low']).mean()
                        atr_pct = (avg_range / live_price) if live_price > 0 else 0
                    else:
                        atr_pct = 0
                    
                    category_key, cat_prof = category_profile(cat)
                    mode_prof = strategy_profile(strategy_name)
                    active_tolerance = tolerance * cat_prof['tolerance_mult']
                    base_sl_buffer = sl_buffer_pct * cat_prof['sl_mult']
                    active_min_profit = min_profit * cat_prof['profit_mult']
                        
                    # DYNAMIC ATR-BASED STOP LOSS ADAPTATION
                    # Keep the ATR floor tight enough to avoid over-widening exits on low-priced contracts.
                    active_sl_buffer = max(base_sl_buffer, atr_pct * mode_prof['sl_atr'] * 0.22)

                    # Apply alignment penalty to tolerance (make it stricter for bad regimes)
                    active_tolerance = active_tolerance * alignment_penalty

                    # ML Engine Feedback (Determines position size multiplier)
                    confidence = get_confidence_score(strategy_name, cat) * alignment_penalty
                    confidence = clamp(confidence, 0.2, 2.5)
                    mode_perf = strategy_performance(strategy_name)
                    optimizer = auto_tune_strategy_params(strategy_name, mode_perf)
                    training_probe_reason = mode_perf.get('execution_probe_reason') if mode_perf.get('execution_limited') else None
                    if training_probe_reason:
                        optimizer = dict(optimizer)
                        optimizer['training_probe'] = True
                        optimizer['training_probe_reason'] = training_probe_reason
                    runner_prof = tuned_runner_profile(strategy_name, optimizer)
                    mode_block_reason = performance_block_reason(strategy_name)
                    active_tolerance = active_tolerance * optimizer['tolerance_mult']
                    active_min_profit = active_min_profit * optimizer['min_profit_mult']
                    tuned_target_rr = max(0.05, target_rr * optimizer['target_rr_mult'])
                    if training_probe_reason:
                        active_min_profit *= as_float(getattr(config, 'TRAINING_PROBE_MIN_PROFIT_MULT', 1.10), 1.10)
                        tuned_target_rr *= as_float(getattr(config, 'TRAINING_PROBE_TARGET_RR_MULT', 1.15), 1.15)
                    if (
                        getattr(config, 'FAST_TRAINING_MODE', False)
                        and int(optimizer.get('sample_size') or 0) <= 0
                        and int(optimizer.get('closed_sample') or 0) <= 0
                    ):
                        active_tolerance *= config.ZERO_SAMPLE_ENTRY_TOLERANCE_MULT
                        active_min_profit *= config.ZERO_SAMPLE_MIN_PROFIT_MULT
                        tuned_target_rr *= config.ZERO_SAMPLE_TARGET_RR_MULT

                    display_sym = symbol.replace(':USDT', '').replace('/', '')
                    market_route = route_symbol_market(symbol, cat, trends_dict, signal_df, timeframe)
                    route_allowed, route_block_reason = router_allows_mode(market_route, strategy_name)
                    routing_confidence = as_float(market_route.get('routingConfidence'), 0.0)
                    min_live_route_conf = as_float(
                        getattr(config, 'MARKET_ROUTER_LIVE_MIN_CONFIDENCE_BY_MODE', {}).get(strategy_name),
                        0.0,
                    )
                    if route_allowed and min_live_route_conf > 0 and routing_confidence < min_live_route_conf:
                        route_allowed = False
                        route_block_reason = (
                            f"market router confidence {routing_confidence:.3f} "
                            f"< live minimum {min_live_route_conf:.3f}"
                        )
                    if route_allowed and training_probe_reason:
                        min_probe_conf = as_float(
                            getattr(config, 'TRAINING_PROBE_MIN_CONFIDENCE_BY_MODE', {}).get(strategy_name),
                            0.0,
                        )
                        if min_probe_conf > 0 and routing_confidence < min_probe_conf:
                            route_allowed = False
                            route_block_reason = (
                                f"training probe requires router confidence {routing_confidence:.3f} "
                                f">= {min_probe_conf:.3f}"
                            )
                    if route_allowed:
                        confidence = clamp(
                            confidence * clamp(0.65 + routing_confidence, 0.5, 1.25),
                            0.2,
                            2.5,
                        )
                    else:
                        radar_item = {
                            'symbol': display_sym,
                            'category': state.global_symbol_categories.get(symbol, 'Uncategorized'),
                            'trends': trends_dict,
                            'rsi': round(signal_df['rsi'].iloc[-1], 1) if pd.notna(signal_df['rsi'].iloc[-1]) else 50,
                            'pattern': 'None',
                            'score': 0,
                            'trigger_reason': route_block_reason,
                            'strategy': strategy_name,
                            'active_tolerance': round(active_tolerance, 3),
                            'active_sl_buffer': round(active_sl_buffer, 3),
                            'active_min_profit': round(active_min_profit, 3),
                            'confidence': round(confidence, 2),
                            'mode_role': mode_prof['role'],
                            'category_key': category_key,
                            'mode_verdict': mode_perf.get('verdict'),
                            'optimizer': optimizer,
                            'tuned_target_rr': round(tuned_target_rr, 3),
                            'market_route': market_route,
                            'market_state': market_route.get('selectedMarketState'),
                            'active_mode_owner': market_route.get('selectedMode'),
                            'routing_confidence': market_route.get('routingConfidence'),
                            'score_gap': market_route.get('scoreGap'),
                        }
                        current_radar.append(radar_item)
                        if len(current_radar) == 1 or len(current_radar) % 5 == 0:
                            state.market_radar_dict[strategy_name] = list(current_radar)
                        continue

                    # Dynamic pivot depth based on standard Fractal/ZigZag math
                    pivot_depth = 4
                    if timeframe == '5m': pivot_depth = 1
                    elif timeframe == '15m': pivot_depth = 3
                    elif timeframe in ['1h', '4h']: pivot_depth = 4
                    
                    hist_pivots = detect_pivots(signal_df, depth=pivot_depth)
                    
                    # SYNTHESIZE REAL-TIME D-POINT
                    pivots = list(hist_pivots)
                    if len(pivots) >= 4:
                        pivots = pivots[-4:]
                        last_p = pivots[-1]
                        fake_type = "low" if last_p.type == "high" else "high"
                        current_close = signal_df['close'].iloc[-1]
                        current_time = str(signal_df['time'].iloc[-1])
                        current_idx = len(signal_df) - 1
                        
                        from core.pivot_detector import PivotPoint
                        fake_d = PivotPoint(current_idx, current_time, current_close, fake_type)
                        pivots.append(fake_d)
                    
                    patterns = scan_patterns(pivots, tolerance=active_tolerance)
                    direct_setup = create_mode_direct_setup(
                        strategy_name,
                        signal_df,
                        trends_dict,
                        htf_bull,
                        htf_bear,
                    )
                    if direct_setup:
                        patterns.append(direct_setup)
                    
                    # Radar Item
                    radar_item = {
                        'symbol': display_sym,
                        'category': state.global_symbol_categories.get(symbol, 'Uncategorized'),
                        'trends': trends_dict,
                        'rsi': round(signal_df['rsi'].iloc[-1], 1) if pd.notna(signal_df['rsi'].iloc[-1]) else 50,
                        'pattern': 'None',
                        'score': 0,
                        'trigger_reason': '????銝?(Scanning)',
                        'strategy': strategy_name,
                        'active_tolerance': round(active_tolerance, 3),
                        'active_sl_buffer': round(active_sl_buffer, 3),
                        'active_min_profit': round(active_min_profit, 3),
                        'confidence': round(confidence, 2),
                        'mode_role': mode_prof['role'],
                        'category_key': category_key,
                        'mode_verdict': mode_perf.get('verdict'),
                        'optimizer': optimizer,
                        'tuned_target_rr': round(tuned_target_rr, 3),
                        'market_route': market_route,
                        'market_state': market_route.get('selectedMarketState'),
                        'active_mode_owner': market_route.get('selectedMode'),
                        'routing_confidence': market_route.get('routingConfidence'),
                        'score_gap': market_route.get('scoreGap'),
                    }
                    if mode_block_reason:
                        radar_item['trigger_reason'] = mode_block_reason
                    
                    if patterns:
                        best_p = patterns[-1]
                        radar_item['pattern'] = best_p.pattern_name
                        radar_item['setup_source'] = getattr(best_p, 'setup_source', 'harmonic')
                        d_price = best_p.d.price
                        prz_width = best_p.prz_high - best_p.prz_low
                        buffer = max(prz_width * 0.15, abs(d_price) * 0.002, avg_range * 0.25)
                        try:
                            radar_plan = build_trade_plan(best_p.direction, best_p.x.price, best_p.a.price, best_p.c.price, d_price, best_p.pattern_name, min_rr=0.2, sl_buffer_pct=active_sl_buffer)
                            radar_plan['structural_stop'] = getattr(best_p, 'stop_reference', None)
                            radar_plan['structural_target'] = getattr(best_p, 'target_reference', None)
                            radar_plan = apply_adaptive_exits(radar_plan, strategy_name, live_price, best_p.direction, atr_pct, optimizer)
                            est_tp_pct = abs(radar_plan['tp1'] - live_price) / live_price
                            est_sl_pct = abs(live_price - radar_plan['sl']) / live_price
                            safe_lev = risk_based_leverage_cap(config.BASE_MARGIN_USDT, est_sl_pct, symbol=symbol)
                            radar_sizing = build_sizing_plan(strategy_name, cat, confidence, safe_lev, state.account_data.get('usdtAvail'))
                            radar_sizing = apply_rehab_sizing_if_needed(radar_sizing, mode_perf.get('verdict'), safe_lev, optimizer)
                            radar_item.update({
                                'est_tp_pct': round(est_tp_pct * 100, 2),
                                'est_sl_pct': round(est_sl_pct * 100, 2),
                                'est_rr': radar_plan.get('risk_reward'),
                                'planned_margin': radar_sizing['margin_usdt'],
                                'planned_notional': radar_sizing['target_notional'],
                                'planned_leverage': safe_lev,
                                'exit_model': radar_plan.get('exit_model'),
                            })
                        except Exception as radar_err:
                            radar_item['trigger_reason'] = f"radar plan error: {radar_err}"
                        in_prz = (best_p.prz_low - buffer) <= live_price <= (best_p.prz_high + buffer)
                        if in_prz:
                            radar_item['score'] = 100
                            radar_item['trigger_reason'] = 'PRZ ?菟?嚗?敺?璅?舫脣'
                        else:
                            dist = min(abs(live_price - best_p.prz_low), abs(live_price - best_p.prz_high))
                            radar_item['score'] = max(10, int(100 - (dist / live_price) * 1000))
                            direction = "??" if best_p.direction == 'bullish' else "?征"
                            radar_item['trigger_reason'] = f'PRZ breakout {direction} near {best_p.prz_center:.4g}'
                            
                    current_radar.append(radar_item)
                    if len(current_radar) == 1 or len(current_radar) % 5 == 0:
                        state.market_radar_dict[strategy_name] = list(current_radar)
                    
                    for p in patterns:
                        d_price = p.d.price
                        prz_width = p.prz_high - p.prz_low
                        buffer = max(prz_width * 0.15, abs(d_price) * 0.002, avg_range * 0.25)
                        
                        # CRITICAL ENTRY POSITION OPTIMIZATION:
                        if strategy_name in ['SqueezeHunter', 'Contrarian', 'MeanReversion']:
                            in_prz = (p.prz_low - buffer) <= live_price <= (p.prz_high + buffer)
                        else:
                            # Trend mode waits for a real retest of its closed-bar level.
                            if p.direction == 'bullish':
                                trigger_price = p.prz_center + (prz_width * 0.2)
                                in_prz = live_price <= trigger_price and live_price >= (p.prz_low - buffer)
                            else:
                                trigger_price = p.prz_center - (prz_width * 0.2)
                                in_prz = live_price >= trigger_price and live_price <= (p.prz_high + buffer)
                        
                        # HTF Trend Filter - ENFORCED FOR ALL STRATEGIES (High Win-Rate Training Mode)
                        rsi = signal_df['rsi'].iloc[-1] if pd.notna(signal_df['rsi'].iloc[-1]) else 50
                        trend_ok = (p.direction == 'bullish' and htf_bull) or (p.direction == 'bearish' and htf_bear)
                        
                        # Pass the strategy's specific sl_buffer to the planner
                        plan = build_trade_plan(
                            p.direction,
                            p.x.price,
                            p.a.price,
                            p.c.price,
                            p.d.price,
                            p.pattern_name,
                            min_rr=max(0.2, as_float(optimizer.get('min_rr'), mode_prof['min_rr'])),
                            sl_buffer_pct=active_sl_buffer,
                        )
                        
                        # DYNAMIC TARGET COMPRESSION: Secure profits faster for aggressive/intraday modes
                        if strategy_name in ['MeanReversion', 'Contrarian']:
                            move_ad = abs(p.a.price - p.d.price)
                            if p.direction == 'bullish':
                                plan['tp1'] = p.d.price + move_ad * 0.382
                            else:
                                plan['tp1'] = p.d.price - move_ad * 0.382
                        
                        # CRITICAL WIN-RATE FIX: Calculate TRUE Risk/Reward based on the real-time execution price!
                        current_price = live_price
                        true_risk = abs(current_price - plan['sl'])
                        true_reward = abs(plan['tp1'] - current_price)
                        true_rr = true_reward / true_risk if true_risk > 0 else 0
                        
                        # Override the theoretical RR with the TRUE real-time RR
                        plan["risk_reward"] = round(true_rr, 2)
                        
                        # CHECK: Valid Live Target Prices?
                        sl_valid = (plan['sl'] < current_price) if p.direction == 'bullish' else (plan['sl'] > current_price)
                        tp_valid = (plan['tp1'] > current_price) if p.direction == 'bullish' else (plan['tp1'] < current_price)
                        
                        block_reason = None
                        squeeze_ready = False
                        if strategy_name == 'SqueezeHunter':
                            squeeze_ready = squeeze_hunter_release_ready(signal_df, sample=int(mode_perf.get('sample') or 0))
                        if not sl_valid or not tp_valid:
                            block_reason = "invalid TP/SL settings"
                        elif not trend_ok:
                            t_dir = 'bear' if htf_bear and not htf_bull else ('bull' if htf_bull and not htf_bear else 'flat')
                            block_reason = f"trend mismatch ({trend_tf} {t_dir})"
                        # Keep entries anchored to the PRZ; SqueezeHunter also needs a confirmed release.
                        is_prz_ok = in_prz
                        if not is_prz_ok:
                            block_reason = "entry not in PRZ"
                        else:
                            # PROFITABILITY CHECK (Live Fire Calibration)
                            active_min_profit = max(active_min_profit, config.PROFIT_FIRST_MIN_ROOM_FLOOR)
                            profit_pct = abs(plan["tp1"] - current_price) / current_price
                            if profit_pct < active_min_profit:
                                block_reason = f"?拇膜蝛粹?憭芸? (<{(active_min_profit*100):.2f}%)"
                            elif true_rr < tuned_target_rr:
                                block_reason = f"?祕?瘥?雿?({round(true_rr, 2)} < {round(tuned_target_rr, 2)})"
                                
                        # Growth engine override
                        div_ok = check_divergence(signal_df, len(signal_df)-1, lookback=30, direction=p.direction)
                        current_candle = signal_df.iloc[-1]
                        sweep_ok = current_candle['low'] <= p.x.price if p.direction == 'bullish' else current_candle['high'] >= p.x.price
                        current_price = live_price
                        plan['structural_stop'] = getattr(p, 'stop_reference', None)
                        plan['structural_target'] = getattr(p, 'target_reference', None)
                        plan = apply_adaptive_exits(plan, strategy_name, current_price, p.direction, atr_pct, optimizer)
                        true_risk = abs(current_price - plan['sl'])
                        true_reward = abs(plan['tp1'] - current_price)
                        true_rr = true_reward / true_risk if true_risk > 0 else 0
                        plan["risk_reward"] = round(true_rr, 2)
                        sl_valid = (plan['sl'] < current_price) if p.direction == 'bullish' else (plan['sl'] > current_price)
                        tp_valid = (plan['tp1'] > current_price) if p.direction == 'bullish' else (plan['tp1'] < current_price)
                        mode_ok, mode_reason = evaluate_mode_gate(
                            strategy_name, p.direction, rsi, trends_dict, in_prz,
                            true_rr, tuned_target_rr, div_ok, sweep_ok,
                            signal_df, optimizer, symbol, cat,
                        )
                        profit_pct = abs(plan["tp1"] - current_price) / current_price
                        mode_paused = mode_perf.get('verdict') == 'pause'
                        rehab_rr_floor = max(tuned_target_rr, mode_prof['min_rr']) * config.REHAB_RR_MULTIPLIER
                        rehab_profit_floor = active_min_profit * config.REHAB_PROFIT_MULTIPLIER
                        rehab_ok = mode_paused and true_rr >= rehab_rr_floor and profit_pct >= rehab_profit_floor
                        if not sl_valid or not tp_valid:
                            block_reason = "invalid live TP/SL direction"
                        elif not mode_ok:
                            block_reason = mode_reason
                        elif mode_paused and not rehab_ok:
                            block_reason = f"training rehab waiting: needs RR >= {round(rehab_rr_floor, 2)} and profit room >= {(rehab_profit_floor*100):.2f}%"
                        elif profit_pct < active_min_profit:
                            block_reason = f"profit room too small (<{(active_min_profit*100):.2f}%)"
                        else:
                            block_reason = None
                            if rehab_ok:
                                mode_reason = "training sample allowed: base setup"

                        live_allowed, live_reason, live_tier = live_trade_permission(strategy_name, optimizer, mode_perf)
                        soft_override_note = None
                        if block_reason and live_allowed and live_tier in ['live_probe', 'live_learning', 'live_calibration']:
                            soft_reason = str(block_reason).lower()
                            soft_block = (
                                soft_reason.startswith('waiting for ')
                                or 'training rehab waiting' in soft_reason
                                or 'learning lane' in soft_reason
                                or 'profit room too small' in soft_reason
                                or soft_reason.startswith('rr ')
                            )
                            if soft_block and true_rr >= max(0.9, tuned_target_rr * 0.85) and profit_pct >= max(active_min_profit * 0.75, config.PROFIT_FIRST_MIN_ROOM_FLOOR):
                                soft_override_note = f"{live_reason}; soft override"
                                block_reason = None
                        display_sym = symbol.replace(':USDT', '').replace('/', '')
                        signal_obj = {
                            "id": state.trade_id_counter,
                            "symbol": display_sym,
                            "direction": "long" if p.direction == "bullish" else "short",
                            "pattern": p.pattern_name,
                            "setup_source": getattr(p, 'setup_source', 'harmonic'),
                            "status": "potential",
                            "entry": plan["entry"],
                            "current": live_price,
                            "signal_close": as_float(p.d.price),
                            "entry_reference": as_float(p.prz_center),
                            "entry_zone_low": as_float(p.prz_low),
                            "entry_zone_high": as_float(p.prz_high),
                            "structural_stop": as_float(getattr(p, 'stop_reference', 0)),
                            "structural_target": as_float(getattr(p, 'target_reference', 0)),
                            "sl": plan["sl"],
                            "tp1": plan["tp1"],
                            "original_tp_dist": abs(plan["tp1"] - current_price),
                            "original_sl_dist": abs(current_price - plan["sl"]),
                            "opened_at": datetime.datetime.now(datetime.UTC).isoformat(),
                            "pnl": 0.0,
                            "rsi_on_entry": round(signal_df['rsi'].iloc[-1], 1) if pd.notna(signal_df['rsi'].iloc[-1]) else 50,
                            "trends": trends_dict,
                            "strategy": strategy_name,
                            "lifecycle_id": uuid.uuid4().hex,
                            "category": cat,
                            "category_key": category_key,
                            "confidence": round(confidence, 2),
                            "mode_role": mode_prof['role'],
                            "mode_reason": mode_reason,
                            "mode_verdict": mode_perf.get('verdict'),
                            "market_route": market_route,
                            "market_state": market_route.get('selectedMarketState'),
                            "active_mode_owner": market_route.get('selectedMode'),
                            "routing_confidence": market_route.get('routingConfidence'),
                            "score_gap": market_route.get('scoreGap'),
                            "rehab_mode": rehab_ok,
                            "optimizer": optimizer,
                            "tuned_target_rr": round(tuned_target_rr, 3),
                            "active_tolerance": round(active_tolerance, 4),
                            "active_min_profit": round(active_min_profit, 5),
                            "execution_mode": live_tier,
                            "training_probe": bool(training_probe_reason),
                            "training_probe_reason": training_probe_reason,
                            "live_permission": live_reason,
                            "exit_model": plan.get("exit_model"),
                            "est_rr": plan.get("risk_reward"),
                            "sl_dist_pct": plan.get("sl_dist_pct"),
                            "tp_dist_pct": plan.get("tp_dist_pct"),
                            "runner_policy": runner_policy_text(runner_prof),
                            "strategy_version": config.STRATEGY_VERSION,
                            "estimated_round_trip_cost_pct": round(config.FEE_SAFE_PROFIT_RATE * 100, 3),
                            "cost_safe_stop": fee_safe_stop_price(
                                current_price,
                                "long" if p.direction == "bullish" else "short",
                            ),
                            "signal_candle": int(signal_df['timestamp'].iloc[-1]),
                            "block_reason": block_reason
                        }

                        if soft_override_note:
                            signal_obj["mode_reason"] = f"{mode_reason}; {soft_override_note}"

                        if not live_allowed and not block_reason:
                            block_reason = live_reason
                            signal_obj["block_reason"] = block_reason
                            signal_obj["mode_reason"] = live_reason
                        
                        on_cooldown = False
                        signal_key = (strategy_name, symbol, p.direction)
                        signal_candle = signal_obj['signal_candle']
                        if state.global_executed_signal_candles.get(signal_key) == signal_candle and not block_reason:
                            block_reason = "same mode/symbol/candle already executed"
                            signal_obj["block_reason"] = block_reason
                        active_cooldown = COOLDOWN_SECONDS * optimizer['cooldown_mult']
                        if rehab_ok:
                            active_cooldown = min(active_cooldown, COOLDOWN_SECONDS * config.REHAB_COOLDOWN_MULTIPLIER)
                        cooldown_key = (strategy_name, symbol)
                        if cooldown_key in state.global_symbol_cooldowns and (time.time() - state.global_symbol_cooldowns[cooldown_key] < active_cooldown):
                            on_cooldown = True
                            if not block_reason:
                                block_reason = "cooldown active"
                                signal_obj["block_reason"] = block_reason
                        
                        # 瑼Ｘ閰脣馳蝔格?行?????
                        has_opposite_position = False
                        try:
                            with open(config.TRADE_FILE, 'r', encoding='utf-8') as af:
                                active_list = json.load(af)
                            for act_t in active_list:
                                if act_t.get('non_blocking_active') or str(act_t.get('sync_status') or '') == 'awaiting exact OKX close lifecycle':
                                    continue
                                if act_t.get('symbol') == symbol:
                                    existing_dir = str(act_t.get('direction')).lower()
                                    new_dir = 'long' if p.direction == 'bullish' else 'short'
                                    if existing_dir != new_dir:
                                        has_opposite_position = True
                                        break
                        except Exception as e:
                            print(f'Error reading {config.TRADE_FILE} for conflict check: {e}')

                        if has_opposite_position:
                            block_reason = 'conflict: opposite position already exists'
                            signal_obj['block_reason'] = block_reason

                        reservation_key = None
                        if not block_reason:
                            reserved, reservation_result = reserve_symbol_for_entry(display_sym)
                            if reserved:
                                reservation_key = reservation_result
                            else:
                                block_reason = reservation_result
                                signal_obj['block_reason'] = block_reason

                        if not block_reason:
                            # ACTUAL OKX ORDER EXECUTION
                            try:
                                side = 'buy' if p.direction == 'bullish' else 'sell'
                                filled_size = 0.0
                                protection_confirmed = False
                                entry_lock_acquired = False
                                
                                # Size leverage by planned U loss, including an
                                # order-book-derived allowance for stop slippage.
                                sl_dist_pct = abs(current_price - plan['sl']) / current_price
                                market_quality = fetch_market_quality(symbol)
                                max_safe_leverage = int(0.8 / (sl_dist_pct + 0.002)) if sl_dist_pct > 0 else config.MAX_LEVERAGE_CAP
                                risk_preview = build_sizing_plan(
                                    strategy_name, cat, confidence, 1, state.account_data.get('usdtAvail')
                                )
                                risk_preview = apply_rehab_sizing_if_needed(
                                    risk_preview, mode_perf.get('verdict'), 1, optimizer
                                )
                                risk_leverage = risk_based_leverage_cap(
                                    risk_preview['margin_usdt'],
                                    sl_dist_pct,
                                    market_quality['exit_slippage_pct'],
                                    symbol,
                                )
                                safe_leverage_target = min(config.MAX_LEVERAGE_CAP, max_safe_leverage, risk_leverage)
                                base_leverages = [75, 50, 20, 10, 5, 2, 1]
                                leverages_to_try = [l for l in base_leverages if l <= safe_leverage_target]
                                if not leverages_to_try: leverages_to_try = [1]
                                
                                actual_leverage = None
                                sizing_plan = None
                                margin_usdt = config.BASE_MARGIN_USDT
                                target_notional = 0.0
                                size = 0
                                current_price = live_price
                                market_meta = (getattr(okx, 'markets', None) or {}).get(symbol) or {}
                                contract_size = as_float(
                                    market_meta.get('contractSize') or market_meta.get('contract_size') or 1.0,
                                    1.0,
                                )
                                for lev in leverages_to_try:
                                    try:
                                        set_okx_leverage(lev, symbol)
                                    except Exception:
                                        continue

                                    candidate_plan = build_sizing_plan(
                                        strategy_name,
                                        cat,
                                        confidence,
                                        lev,
                                        state.account_data.get('usdtAvail'),
                                    )
                                    candidate_plan = apply_rehab_sizing_if_needed(
                                        candidate_plan,
                                        mode_perf.get('verdict'),
                                        lev,
                                        optimizer,
                                    )
                                    candidate_notional = candidate_plan['target_notional']
                                    candidate_size = int(candidate_notional / (current_price * contract_size))
                                    if candidate_size < 1:
                                        continue

                                    max_contracts = fetch_exchange_max_contracts(symbol, side)
                                    if candidate_size > max_contracts:
                                        print(
                                            f"[{strategy_name}] {symbol}: {candidate_size} contracts exceed "
                                            f"OKX max {int(max_contracts)} at {lev}x; trying lower leverage."
                                        )
                                        continue

                                    actual_leverage = lev
                                    sizing_plan = candidate_plan
                                    margin_usdt = candidate_plan['margin_usdt']
                                    target_notional = candidate_notional
                                    size = candidate_size
                                    break

                                if actual_leverage is None or sizing_plan is None or size < 1:
                                    print(f"[{strategy_name}] Skip {symbol}: no leverage fits OKX contract limits.")
                                    continue

                                signal_obj['sizing_plan'] = sizing_plan
                                signal_obj['planned_margin'] = margin_usdt
                                signal_obj['planned_notional'] = target_notional
                                signal_obj['planned_leverage'] = actual_leverage
                                signal_obj['max_planned_loss_usdt'] = config.MAX_PLANNED_LOSS_USDT
                                signal_obj['market_quality'] = market_quality

                                actual_order_notional = size * current_price * contract_size
                                actual_order_margin = actual_order_notional / max(actual_leverage, 1)
                                edge_check = expected_trade_edge(
                                    actual_order_notional,
                                    as_float(plan.get('tp_dist_pct')),
                                    market_quality,
                                )
                                signal_obj['expected_edge'] = edge_check
                                edge_bias = max(1.0, as_float(optimizer.get('entry_edge_mult'), 1.0))
                                min_expected_net = config.MIN_EXPECTED_NET_PROFIT_USDT * edge_bias
                                min_required_gross = edge_check['required_gross_usdt'] * edge_bias
                                if (
                                    not edge_check['passes']
                                    or edge_check['expected_net_usdt'] < min_expected_net
                                    or edge_check['gross_target_usdt'] < min_required_gross
                                ):
                                    signal_obj['block_reason'] = (
                                        f"target gross {edge_check['gross_target_usdt']:.2f}U cannot cover "
                                        f"estimated cost and {min_expected_net:.2f}U net edge"
                                    )
                                    current_potentials.append(signal_obj)
                                    continue
                                halt_reason = safety_halt_reason()
                                if halt_reason:
                                    signal_obj['block_reason'] = f"safety halt: {halt_reason}"
                                    current_potentials.append(signal_obj)
                                    print(f"[{strategy_name}] Safety halt active; skip new entry: {halt_reason}")
                                    continue
                                with state.execution_state_lock:
                                    unsafe_open_trades = active_unprotected_trades()
                                if unsafe_open_trades:
                                    blocked_symbols = ', '.join(
                                        str(t.get('symbol') or t.get('instId') or '?')
                                        for t in unsafe_open_trades[:5]
                                    )
                                    signal_obj['block_reason'] = (
                                        "safety pause: existing active position has unverified TP/SL protection"
                                    )
                                    current_potentials.append(signal_obj)
                                    print(
                                        f"[{strategy_name}] Safety pause: skip new entry while "
                                        f"{len(unsafe_open_trades)} active trade(s) lack verified protection "
                                        f"({blocked_symbols})."
                                    )
                                    continue
                                exchange_unsafe_positions = exchange_unprotected_positions()
                                if exchange_unsafe_positions:
                                    blocked_symbols = ', '.join(
                                        str(t.get('instId') or t.get('symbol') or '?')
                                        for t in exchange_unsafe_positions[:5]
                                    )
                                    signal_obj['block_reason'] = (
                                        "safety pause: OKX live position lacks verified TP/SL protection"
                                    )
                                    signal_obj['exchange_unprotected_positions'] = exchange_unsafe_positions[:8]
                                    current_potentials.append(signal_obj)
                                    print(
                                        f"[{strategy_name}] Safety pause: skip new entry while OKX has "
                                        f"{len(exchange_unsafe_positions)} live position(s) without verified "
                                        f"TP/SL protection ({blocked_symbols})."
                                    )
                                    continue
                                account_data = state.account_data or {}
                                available_usdt = max(
                                    as_float(account_data.get('usdtAvail')),
                                    as_float(account_data.get('usdtEq')),
                                    as_float(account_data.get('totalEq')),
                                )
                                if available_usdt <= 0 or actual_order_margin > available_usdt * 0.95:
                                    print(
                                        f"[{strategy_name}] Skip {symbol}: actual margin {actual_order_margin:.2f}U "
                                        f"exceeds available {available_usdt:.2f}U"
                                    )
                                    continue

                                entry_lock_acquired = state.entry_execution_lock.acquire(timeout=45)
                                if not entry_lock_acquired:
                                    signal_obj['block_reason'] = 'safety pause: another entry is still being protected'
                                    current_potentials.append(signal_obj)
                                    print(f"[{strategy_name}] Skip {symbol}: entry lock timeout.")
                                    continue

                                halt_reason = safety_halt_reason()
                                if halt_reason:
                                    signal_obj['block_reason'] = f"safety halt: {halt_reason}"
                                    current_potentials.append(signal_obj)
                                    print(f"[{strategy_name}] Safety halt active after lock; skip {symbol}: {halt_reason}")
                                    continue

                                exchange_unsafe_positions = exchange_unprotected_positions(ttl_seconds=0)
                                if exchange_unsafe_positions:
                                    blocked_symbols = ', '.join(
                                        str(t.get('instId') or t.get('symbol') or '?')
                                        for t in exchange_unsafe_positions[:5]
                                    )
                                    signal_obj['block_reason'] = (
                                        "safety pause: OKX live position lacks verified TP/SL protection"
                                    )
                                    signal_obj['exchange_unprotected_positions'] = exchange_unsafe_positions[:8]
                                    current_potentials.append(signal_obj)
                                    print(
                                        f"[{strategy_name}] Safety pause after lock: OKX has "
                                        f"{len(exchange_unsafe_positions)} unprotected live position(s) "
                                        f"({blocked_symbols})."
                                    )
                                    continue

                                with state.execution_state_lock:
                                    existing_active = next(
                                        (
                                            t for t in state.active_trades
                                            if t.get('status') == 'active'
                                            and normalize_symbol_key(t.get('symbol') or t.get('instId')) == normalize_symbol_key(display_sym)
                                        ),
                                        None,
                                    )
                                if existing_active:
                                    print(
                                        f"[{strategy_name}] Skip {symbol}: an existing net lifecycle is active; "
                                        "cross-mode add-on disabled."
                                    )
                                    continue
                                entry_direction = 'long' if p.direction == 'bullish' else 'short'
                                entry_inst_id = resolve_okx_inst_id(symbol)
                                live_existing_contracts = fetch_live_position_contracts(entry_inst_id, entry_direction)
                                if live_existing_contracts > 0:
                                    signal_obj['block_reason'] = (
                                        f"OKX live {entry_direction} position already exists on {entry_inst_id}; "
                                        "skip add-on until the current net lifecycle is closed"
                                    )
                                    current_potentials.append(signal_obj)
                                    print(
                                        f"[{strategy_name}] Skip {symbol}: OKX already has "
                                        f"{live_existing_contracts:g} {entry_direction} contracts on {entry_inst_id}."
                                    )
                                    continue
                                
                                # OKX clOrdId must be alphanumeric (1-32 chars)
                                cl_ord_id = f"H{strategy_name}{uuid.uuid4().hex[:8]}"
                                execution = execute_bounded_limit_entry(
                                    symbol,
                                    side,
                                    size,
                                    strategy_name,
                                    cl_ord_id,
                                    atr_pct,
                                )
                                if not execution:
                                    signal_obj['block_reason'] = 'bounded limit not filled; retry on next scan'
                                    signal_obj['execution_mode'] = 'limit_waiting'
                                    current_potentials.append(signal_obj)
                                    print(f"[{strategy_name}] {symbol} bounded limit not filled; no market chase.")
                                    continue

                                filled_size = execution['filled']
                                fill_price = execution['average']
                                direction = signal_obj['direction']
                                plan = rebase_plan_to_fill(plan, current_price, fill_price, direction)
                                sl_valid = plan['sl'] < fill_price if direction == 'long' else plan['sl'] > fill_price
                                tp_valid = plan['tp1'] > fill_price if direction == 'long' else plan['tp1'] < fill_price
                                if not sl_valid or not tp_valid:
                                    raise ValueError(
                                        f"Fill-rebased protection invalid: fill={fill_price}, SL={plan['sl']}, TP={plan['tp1']}"
                                    )

                                try:
                                    protection = place_exact_fill_protection(
                                        symbol,
                                        direction,
                                        filled_size,
                                        plan,
                                        cl_ord_id,
                                    )
                                except Exception as protection_exc:
                                    emergency_close_or_halt(
                                        symbol,
                                        direction,
                                        filled_size,
                                        f"[{strategy_name}] protection exception",
                                    )
                                    continue
                                protection_failed, protection_code, protection_message = okx_order_failed(protection)
                                if protection_failed:
                                    print(
                                        f"[{strategy_name}] Protection rejected on {symbol}: "
                                        f"code={protection_code}, msg={protection_message}"
                                    )
                                    emergency_close_or_halt(
                                        symbol,
                                        direction,
                                        filled_size,
                                        f"[{strategy_name}] protection rejection",
                                    )
                                    continue
                                protection_confirmed = True
                                try:
                                    net_protection = ensure_live_position_fully_protected(
                                        symbol,
                                        direction,
                                        plan,
                                        cl_ord_id,
                                        [protection.get('id')] if protection.get('id') else [],
                                    )
                                except Exception as net_protection_exc:
                                    print(
                                        f"[{strategy_name}] URGENT: net protection verification failed on "
                                        f"{symbol}: {net_protection_exc}"
                                    )
                                    live_size = fetch_live_position_contracts(resolve_okx_inst_id(symbol), direction)
                                    close_size = live_size if live_size > 0 else filled_size
                                    emergency_close_or_halt(
                                        symbol,
                                        direction,
                                        close_size,
                                        f"[{strategy_name}] net protection failure",
                                    )
                                    continue

                                actual_order_notional = filled_size * fill_price * float(contract_size)
                                signal_obj.update({
                                    'entry': fill_price,
                                    'current': fill_price,
                                    'sl': plan['sl'],
                                    'tp1': plan['tp1'],
                                    'original_tp_dist': abs(plan['tp1'] - fill_price),
                                    'original_sl_dist': abs(fill_price - plan['sl']),
                                    'sl_dist_pct': plan['sl_dist_pct'],
                                    'tp_dist_pct': plan['tp_dist_pct'],
                                    'cost_safe_stop': fee_safe_stop_price(fill_price, direction),
                                    'filled_contracts': filled_size,
                                    'entry_order_type': execution['execution'],
                                    'entry_limit_price': execution['limit_price'],
                                    'entry_max_slippage_pct': round(execution['max_slippage'] * 100, 4),
                                    'entry_spread_pct': round(execution.get('spread_pct', 0.0) * 100, 4),
                                    'protection_order_id': protection.get('id'),
                                    'protection_order_ids': net_protection.get('protection_order_ids') or ([str(protection.get('id'))] if protection.get('id') else []),
                                    'protection_status': 'confirmed',
                                    'exchange_protection_verified': True,
                                    'exchange_protected_size': net_protection.get('exchange_protected_size') or filled_size,
                                    'exchange_position_size': net_protection.get('exchange_position_size') or filled_size,
                                    'tp_order_type': 'limit',
                                    'sl_order_type': 'market',
                                })
                                print(
                                    f"DEMO LIMIT EXECUTED: {side} {filled_size} contracts of {symbol} "
                                    f"@ {fill_price} ({execution['execution']}, notional ~${int(actual_order_notional)})"
                                )
                                
                                signal_obj["status"] = "active"
                                signal_obj["entry_reason"] = f"閫貊 {p.pattern_name} (???望/頞典?餃?)"
                                signal_obj["entry_reason"] = (
                                    f"{mode_reason}; {execution['execution']} fill {fill_price}; "
                                    f"{plan.get('exit_model')}; margin {margin_usdt}U at {actual_leverage}x"
                                )
                                with state.execution_state_lock:
                                    state.global_symbol_cooldowns[cooldown_key] = time.time()
                                    state.global_executed_signal_candles[signal_key] = signal_candle
                                    state.active_trades.append(signal_obj)
                                    if len(state.active_trades) > 1000:
                                        state.active_trades = state.active_trades[-1000:]
                                    write_json_atomic(config.TRADE_FILE, state.active_trades)
                                    state.trade_id_counter += 1
                                print(f"SIGNAL GENERATED: {display_sym} {p.direction.upper()} {p.pattern_name} @ {plan['entry']}")

                            except Exception as ex:
                                print(f"Demo Execution Error: {ex}")
                                if filled_size > 0 and not protection_confirmed:
                                    emergency_close_or_halt(
                                        symbol,
                                        signal_obj['direction'],
                                        filled_size,
                                        f"[{strategy_name}] execution exception",
                                    )
                            finally:
                                if entry_lock_acquired:
                                    state.entry_execution_lock.release()
                                release_symbol_reservation(reservation_key)
                        else:
                            # It's a potential setup waiting for PRZ or Trend alignment
                            current_potentials.append(signal_obj)
                            
                    # Network calls are already serialized and throttled in fetch_data.
                    time.sleep(0.08)
                except Exception as e:
                    print(f"Error scanning {symbol}: {e}")
                    time.sleep(1)
            
            # Merge potentials safely
            state.potential_signals = [s for s in state.potential_signals if s.get('strategy') != strategy_name] + current_potentials
            
            # Merge radar safely into the dict
            state.market_radar_dict[strategy_name] = current_radar
            state.strategy_radar_status[strategy_name].update({
                'status': 'updated',
                'updated_at': datetime.datetime.now(datetime.UTC).isoformat(),
                'radar_count': len(current_radar),
                'potential_count': len(current_potentials),
                'next_loop_seconds': max(5.0, float(getattr(config, 'SCAN_LOOP_SECONDS', 60))),
            })

            # Update ML evolution logs dynamically for frontend visibility
            time_str = datetime.datetime.now().strftime('%H:%M:%S')
            log_msg = f'[{time_str}] [{strategy_name}] radar updated with {len(symbols)} symbols'
            if not any(strategy_name in item and 'radar updated' in item for item in state.ml_evolution_logs[-8:]):
                state.ml_evolution_logs.append(log_msg)
                if len(state.ml_evolution_logs) > 60:
                    state.ml_evolution_logs = state.ml_evolution_logs[-60:]
            
            # Wait before next full market scan
            time.sleep(max(5.0, float(getattr(config, 'SCAN_LOOP_SECONDS', 60))))
        except Exception as e:
            print(f"Error in main bot loop: {e}")
            time.sleep(10)

def background_sync_loop():
    while True:
        try:
            # Keep in-memory active trades aligned with the journal before we
            # evaluate live positions or write the dashboard snapshot.
            reconcile_active_trades_with_journal(write_back=False)

            # 1. Sync Account Balance
            new_account_data = fetch_okx_account_snapshot(force=True)
            if new_account_data:
                new_account_data['capital'] = capital_snapshot()
                state.account_data = new_account_data
            elif state.account_data:
                state.account_data['capital'] = capital_snapshot()

            # 2. Sync Active Positions & Clear Closed Trades
            try:
                positions = fetch_open_positions_snapshot(force=True)
                cycle_history = None
                for t in state.active_trades:
                    if t['status'] == 'active':
                        def get_base_ccy(sym):
                            return sym.replace('/', '').replace(':USDT', '').replace('-USDT', '').replace('USDT', '').upper()
                        pos = next((p for p in positions if get_base_ccy(p['symbol']) == get_base_ccy(t['symbol']) and ('long' if p['side'] in ['long', 'buy'] else 'short') == ('long' if t['direction'] in ['long', 'buy'] else 'short')), None)
                        if pos:
                            journal_trade = recover_trade_lifecycle_from_journal(pos, t.get('direction'))
                            if journal_trade and not trade_records_look_like_same_lifecycle(pos, journal_trade):
                                journal_trade = None
                            t['current'] = float(pos['markPrice'])
                            if pos.get('entryPrice'):
                                t['entry'] = float(pos['entryPrice']) # CRITICAL: Use the REAL exchange fill price, not theoretical signal price
                            t['posId'] = pos.get('id')
                            t['instId'] = pos.get('info', {}).get('instId', '')
                            t['pnl'] = float(pos.get('unrealizedPnl', 0.0))
                            t['percentage'] = float(pos.get('percentage', 0.0))
                            t['leverage'] = pos.get('leverage')
                            t['initialMargin'] = pos.get('initialMargin')
                            t['notional'] = pos.get('notional')
                            t['liquidationPrice'] = pos.get('liquidationPrice')
                            t['marginRatio'] = pos.get('marginRatio')
                            if journal_trade:
                                for key in [
                                    'strategy', 'strategy_version', 'lifecycle_id', 'mode_reason',
                                    'entry_reason', 'runner_policy', 'optimizer', 'signal_candle',
                                    'original_tp_dist', 'original_sl_dist', 'filled_contracts',
                                    'half_tp_done', 'tp_removed', 'trailing_stage', 'current_r',
                                    'highest_r', 'highest_pnl', 'highest_progress',
                                ]:
                                    value = journal_trade.get(key)
                                    if value not in [None, '', []]:
                                        t[key] = value
                                if as_float(t.get('entry')) <= 0 and as_float(journal_trade.get('entry')) > 0:
                                    t['entry'] = as_float(journal_trade.get('entry'))
                                t['protection_status'] = 'unconfirmed'
                                t['exchange_protection_verified'] = False
                                t['protection_error'] = 'pending OKX TP/SL exchange verification'
                                if journal_trade.get('protection_order_ids'):
                                    t['protection_order_ids'] = list(journal_trade.get('protection_order_ids') or [])
                                if journal_trade.get('protection_order_id'):
                                    t['protection_order_id'] = journal_trade.get('protection_order_id')
                        else:
                            if cycle_history is None:
                                cycle_history = sync_exchange_history(force=True)
                            pos_id = str(t.get('posId') or '')
                            lifecycle_id = str(t.get('lifecycle_id') or '')
                            trade_inst = str(t.get('instId') or t.get('symbol') or '').upper()
                            trade_dir = str(t.get('direction') or '').lower()
                            trade_entry = as_float(t.get('entry'))
                            trade_open_ms = trade_open_timestamp_ms(t)

                            def close_candidate_score(history_row):
                                history_inst = str(history_row.get('instId') or history_row.get('symbol') or '').upper()
                                history_dir = str(history_row.get('direction') or '').lower()
                                history_pos = str(history_row.get('posId') or '')
                                history_lifecycle = str(history_row.get('lifecycle_id') or '')
                                if lifecycle_id and history_lifecycle == lifecycle_id:
                                    lifecycle_rank = 0
                                elif pos_id and history_pos == pos_id:
                                    lifecycle_rank = 1
                                else:
                                    lifecycle_rank = 2
                                if trade_inst and history_inst and trade_inst != history_inst:
                                    return None
                                if trade_dir and history_dir and trade_dir != history_dir:
                                    return None
                                history_open = as_float(history_row.get('openPrice') or history_row.get('entryPrice'))
                                entry_delta = abs(history_open - trade_entry) if history_open > 0 and trade_entry > 0 else 0.0
                                entry_scale = max(history_open, trade_entry, 1.0)
                                entry_rank = entry_delta / entry_scale if entry_scale > 0 else 0.0
                                close_ms = timestamp_ms(
                                    history_row.get('closed_at')
                                    or history_row.get('lastUpdateTimestamp')
                                    or history_row.get('timestamp')
                                )
                                if close_ms > 0 and trade_open_ms > 0 and close_ms < trade_open_ms - config.LIFECYCLE_OPEN_TOLERANCE_MS:
                                    return None
                                time_rank = abs(close_ms - trade_open_ms) if close_ms > 0 and trade_open_ms > 0 else 0
                                manual_rank = 1 if str(history_row.get('strategy') or '') == 'Manual' else 0
                                return (lifecycle_rank, manual_rank, entry_rank, time_rank)

                            scored_history = []
                            for history_row in cycle_history:
                                score = close_candidate_score(history_row)
                                if score is not None:
                                    scored_history.append((score, history_row))
                            actual_close = min(scored_history, key=lambda item: item[0])[1] if scored_history else None
                            if actual_close is None:
                                t['sync_status'] = 'awaiting exact OKX close lifecycle'
                                t['non_blocking_active'] = True
                                t['protection_error'] = (
                                    'OKX live position is missing; waiting for exact close lifecycle match. '
                                    'This stale local record will not block new entries.'
                                )
                                continue
                            if actual_close:
                                t['pnl'] = as_float(actual_close.get('realizedPnl'))
                                t['realized_pnl'] = t['pnl']
                                t['fee'] = as_float(actual_close.get('fee'))
                                t['funding_fee'] = as_float(actual_close.get('fundingFee'))
                                t['close_price'] = actual_close.get('closePrice')
                                t['gross_price_pnl'] = round(
                                    t['realized_pnl'] - t['fee'] - t['funding_fee'],
                                    8,
                                )
                                t['exit_reason'] = infer_exit_reason(t, t['close_price'])
                                t['closed_at'] = actual_close.get('lastUpdateTimestamp') or actual_close.get('timestamp')
                                t['close_event_key'] = actual_close.get('close_event_key') or history_event_key(actual_close)
                                t['pnl_source'] = 'okx_realized'
                                t['accounting_status'] = actual_close.get('accounting_status')
                                t['eligible_for_learning'] = actual_close.get('eligible_for_learning') is True
                                t['accounting_reasons'] = actual_close.get('accounting_reasons') or []
                            t['status'] = 'closed'
                            already_recorded = any(
                                row.get('close_event_key') and row.get('close_event_key') == t.get('close_event_key')
                                for row in state.trade_journal
                            )
                            if not already_recorded:
                                state.trade_journal.append(dict(t))
                                # Cap journal at 5000 records to prevent memory/disk bloat
                                if len(state.trade_journal) > 5000:
                                    state.trade_journal = state.trade_journal[-5000:]
                            
                # Cleanup and Save
                if any(t['status'] == 'closed' for t in state.active_trades):
                    state.active_trades = [t for t in state.active_trades if t['status'] != 'closed']
                    write_json_atomic(config.JOURNAL_FILE, state.trade_journal)
                            
                for pos in positions:
                    # Normalize symbol formats (e.g. LAB-USDT-SWAP -> LABUSDT) to match active strategy trades
                    def get_base_ccy(s):
                        return s.replace('/', '').replace(':USDT', '').replace('-USDT', '').replace('USDT', '').replace('-SWAP', '').upper()
                    sym = get_base_ccy(pos['symbol']) + "USDT"
                    direction = pos.get('side', 'long')
                    exists = any(
                        get_base_ccy(t['symbol']) == get_base_ccy(sym)
                        and str(t['direction']).lower() == str(direction).lower()
                        and t['status'] == 'active'
                        for t in state.active_trades
                    )
                    if not exists:
                        recovered_trade = recover_trade_lifecycle_from_journal(pos, direction)
                        if recovered_trade and not trade_records_look_like_same_lifecycle(pos, recovered_trade):
                            recovered_trade = None
                        pos_id = str(pos.get('id') or pos.get('posId') or '')
                        inst_id = str(pos.get('info', {}).get('instId', '') or pos.get('instId') or '')
                        raw_entry = as_float(pos.get('entryPrice', 0))
                        raw_sl = 0.0
                        raw_tp1 = 0.0
                        protection_status = 'unconfirmed'
                        recovered_strategy = infer_strategy_from_metadata(recovered_trade or {}, fallback='Manual')
                        recovered_pattern = (recovered_trade or {}).get('pattern', "Manual / Unsynced")
                        if is_known_strategy_name(recovered_strategy) and recovered_pattern in [None, '', 'Manual / Unsynced']:
                            recovered_pattern = f'{recovered_strategy} / live recovered'
                        state.active_trades.append({
                            "id": state.trade_id_counter, "posId": pos.get('id'), "instId": pos.get('info', {}).get('instId', ''),
                            "symbol": sym, "direction": direction, "pattern": recovered_pattern, "status": "active",
                            "entry": float((recovered_trade or {}).get('entry') or raw_entry), "current": float(pos['markPrice']), "sl": raw_sl, "tp1": raw_tp1,
                            "pnl": float(pos.get('unrealizedPnl', 0.0)), "percentage": float(pos.get('percentage', 0.0)),
                            "rsi_on_entry": (recovered_trade or {}).get('rsi_on_entry', '--'), "trends": (recovered_trade or {}).get('trends', {}),
                            "strategy": recovered_strategy, "leverage": pos.get('leverage'),
                            "initialMargin": pos.get('initialMargin'), "notional": pos.get('notional'),
                            "liquidationPrice": pos.get('liquidationPrice'), "marginRatio": pos.get('marginRatio'),
                            "strategy_version": (recovered_trade or {}).get('strategy_version'),
                            "lifecycle_id": (recovered_trade or {}).get('lifecycle_id'),
                            "protection_status": protection_status,
                            "exchange_protection_verified": False,
                            "protection_error": "pending OKX TP/SL exchange verification",
                            "protection_order_id": (recovered_trade or {}).get('protection_order_id'),
                            "protection_order_ids": list((recovered_trade or {}).get('protection_order_ids') or []),
                            "entry_reason": (recovered_trade or {}).get('entry_reason'),
                            "mode_reason": (recovered_trade or {}).get('mode_reason'),
                            "runner_policy": (recovered_trade or {}).get('runner_policy'),
                            "optimizer": (recovered_trade or {}).get('optimizer'),
                            "signal_candle": (recovered_trade or {}).get('signal_candle'),
                            "original_tp_dist": (recovered_trade or {}).get('original_tp_dist'),
                            "original_sl_dist": (recovered_trade or {}).get('original_sl_dist'),
                            "filled_contracts": abs(as_float((recovered_trade or {}).get('filled_contracts') or pos.get('contracts') or pos.get('pos'))),
                        })
                        state.trade_id_counter += 1

                state.active_trades = collapse_active_records(state.active_trades)

                # 3. Sync Algo Orders (TP/SL)
                all_algos = []
                algo_fetch_error = None
                if not config.MOCK_MODE:
                    try:
                        oco_res = okx.private_get_trade_orders_algo_pending({'instType':'SWAP', 'ordType': 'oco'})
                        cond_res = okx.private_get_trade_orders_algo_pending({'instType':'SWAP', 'ordType': 'conditional'})
                        if oco_res and oco_res.get('code') == '0': all_algos.extend(oco_res.get('data', []))
                        if cond_res and cond_res.get('code') == '0': all_algos.extend(cond_res.get('data', []))
                    except Exception as algo_err:
                        algo_fetch_error = str(algo_err)
                        print(f"[BACKGROUND SYNC ERROR] Failed to fetch algo orders: {algo_err}")
                for t in state.active_trades:
                    if t['status'] == 'active':
                        raw_strat = t.get('strategy', 'SqueezeHunter')
                        
                        if config.MOCK_MODE:
                            # ? Mock Mode: 璅⊥靽風????湔?仿???祕??API ?郊?漱????甇Ｙ?甇Ｘ?
                            t['missing_protection_checks'] = 0
                            t['protection_status'] = 'confirmed'
                            t['protection_error'] = None
                            continue
                        
                        # ?梧? MeanReversion 40 ????甇Ｘ?撘瑕像
                        mean_reversion_identity = (
                            raw_strat == 'MeanReversion'
                            and (
                                str(t.get('pattern') or '').startswith('Mean ')
                                or str(t.get('market_state') or '') == 'MEAN_REVERSION'
                                or str(t.get('active_mode_owner') or '') == 'MeanReversion'
                            )
                        )
                        if mean_reversion_identity:
                            opened_ms = trade_open_timestamp_ms(t)
                            if opened_ms:
                                opened_sec = float(opened_ms) / 1000.0
                                if time.time() - opened_sec > 40 * 60:
                                    print("[MR TIME LIMIT] " + str(t.get('symbol')) + " reached the 40 minute limit")
                                    try:
                                        ccxt_sym = f"{normalize_symbol_key(t['symbol']).replace('USDT', '')}/USDT:USDT"
                                        close_size = as_float(t.get('filled_contracts'))
                                        ok, ec, em = emergency_close_unprotected(ccxt_sym, t['direction'], close_size)
                                        if ok or okx_position_not_found_error(ec, em):
                                            close_orphan_trade_record(t, 'time_based_timeout')
                                            continue
                                    except Exception as err:
                                        print(f"[?梧? MR TIME LIMIT ERROR] 撟喳仃?? {err}")

                        # ? SqueezeHunter 1.0R 憭挾甇Ｙ? 50%
                        if raw_strat == 'SqueezeHunter' and not t.get('half_tp_done') and as_float(t.get('entry')) > 0 and as_float(t.get('sl')) > 0:
                            risk_dist = abs(as_float(t.get('entry')) - as_float(t.get('sl')))
                            favorable_move = (as_float(t.get('current')) - as_float(t.get('entry'))) if t['direction'] == 'long' else (as_float(t.get('entry')) - as_float(t.get('current')))
                            r_now = favorable_move / risk_dist if risk_dist > 0 else 0
                            if r_now >= 1.0:
                                print("[SH MULTI-TP] " + str(t.get('symbol')) + " hit 1.0R, closing 50%")
                                try:
                                    ccxt_sym = f"{normalize_symbol_key(t['symbol']).replace('USDT', '')}/USDT:USDT"
                                    close_size = round(as_float(t.get('filled_contracts')) / 2.0, 4)
                                    if close_size > 0:
                                        ok, ec, em = emergency_close_unprotected(ccxt_sym, t['direction'], close_size)
                                        if ok:
                                            t['filled_contracts'] = as_float(t.get('filled_contracts')) - close_size
                                            t['half_tp_done'] = True
                                            print(f"[? SH MULTI-TP SUCCESS] {t['symbol']} 撟喳??詨??擗?蝝? {t['filled_contracts']}")
                                            previous_protection_id = t.get('protection_order_id')
                                            # Keep the old protection alive until the replacement TP/SL is verified.
                                            plan_half = {'tp1': t['tp1'], 'sl': t['sl']}
                                            new_prot = place_exact_fill_protection(
                                                ccxt_sym, t['direction'], t['filled_contracts'], plan_half, t.get('clOrdId', 'HALF')
                                            )
                                            t['protection_order_id'] = new_prot.get('id')
                                            t['protection_order_ids'] = [str(new_prot.get('id'))]
                                            t['protection_status'] = 'confirmed'
                                            t['exchange_protection_verified'] = True
                                            t['exchange_protected_size'] = as_float(t.get('filled_contracts'))
                                            t['exchange_position_size'] = as_float(t.get('filled_contracts'))
                                            t['protection_error'] = None
                                            if previous_protection_id and str(previous_protection_id) != str(new_prot.get('id')):
                                                try:
                                                    okx.cancel_order(previous_protection_id, ccxt_sym)
                                                except Exception as cancel_err:
                                                    t['protection_cleanup_error'] = f"old protection cleanup failed: {cancel_err}"
                                        elif okx_position_not_found_error(ec, em):
                                            close_orphan_trade_record(t, 'half_tp_already_closed')
                                            continue
                                except Exception as err:
                                    t['protection_status'] = 'failed'
                                    t['exchange_protection_verified'] = False
                                    t['protection_error'] = f"half-tp protection refresh failed: {err}"
                                    print(f"[? SH MULTI-TP ERROR] ?瑁?憭挾甇Ｙ?憭望?: {err}")

                        expected_inst_id = t.get('instId') or (normalize_symbol_key(t['symbol']).replace('USDT', '') + "-USDT-SWAP")
                        expected_side = 'sell' if t['direction'] == 'long' else 'buy'
                        live_pos = next(
                            (
                                p for p in positions
                                if str((p.get('info') or {}).get('instId') or p.get('instId') or '') == expected_inst_id
                                and normalize_position_side(p.get('side') or p.get('direction')) == normalize_position_side(t.get('direction'))
                            ),
                            None,
                        )
                        tracked_algo_ids = set(str(x) for x in (t.get('protection_order_ids') or []) if x)
                        if t.get('protection_order_id'):
                            tracked_algo_ids.add(str(t['protection_order_id']))
                        candidate_algos = [
                            a for a in all_algos
                            if a.get('instId') == expected_inst_id and a.get('side') == expected_side
                        ]
                        protective_algos = protective_algo_targets(
                            all_algos, expected_inst_id, expected_side, tracked_algo_ids
                        )
                        # Fallback: if tracked_algo_ids yielded nothing but active OCOs exist on exchange, match them
                        if not protective_algos:
                            protective_algos = protective_algo_targets(
                                all_algos, expected_inst_id, expected_side, None
                            )
                        live_protection_ids = [
                            str(a.get('algoId') or '')
                            for a in protective_algos
                            if isinstance(a, dict) and str(a.get('algoId') or '')
                        ]
                        if live_protection_ids:
                            merged_live_ids = list(dict.fromkeys(
                                [str(x) for x in (t.get('protection_order_ids') or []) if x] + live_protection_ids
                            ))
                            if merged_live_ids != list(t.get('protection_order_ids') or []):
                                t['protection_order_ids'] = merged_live_ids
                            if not t.get('protection_order_id'):
                                t['protection_order_id'] = live_protection_ids[0]
                        for a in protective_algos:
                            if as_float(a.get('slTriggerPx')) > 0: t['sl'] = float(a['slTriggerPx'])
                        for a in protective_algos + candidate_algos:
                            tp_trigger = as_float(a.get('tpTriggerPx'))
                            if tp_trigger > 0:
                                t['tp1'] = float(tp_trigger)
                                break
                            tp_ord = as_float(a.get('tpOrdPx'))
                            if tp_ord > 0 and not t.get('tp1'):
                                t['tp1'] = float(tp_ord)

                        protection_confirmed = str(t.get('protection_status') or '').lower() == 'confirmed'
                        live_contracts = abs(as_float((live_pos or {}).get('contracts')))
                        protection_size_ok = protection_algos_cover_size(protective_algos, live_contracts)
                        exchange_protection_visible = (
                            live_pos is not None
                            and live_position_has_protection(live_pos, protective_algos)
                            and protection_size_ok
                        )
                        if algo_fetch_error and not exchange_protection_visible:
                            t['protection_status'] = 'pending'
                            t['exchange_protection_verified'] = False
                            t['protection_error'] = f"unable to verify OKX TP/SL algos: {algo_fetch_error}"
                            t['sync_status'] = 'algo_verification_unavailable'
                            print(
                                f"[WARN] {t['symbol']} protection verification unavailable; "
                                "skip repair/close until OKX algo endpoint is readable."
                            )
                            continue

                        protection_present = (
                            (
                                live_pos is not None
                                and exchange_protection_visible
                                and as_float(t.get('sl')) > 0
                                and as_float(t.get('tp1')) > 0
                            )
                            or (
                                protection_confirmed
                                and live_pos is not None
                                and exchange_protection_visible
                                and as_float(t.get('sl')) > 0
                                and as_float(t.get('tp1')) > 0
                            )
                        )
                        if protection_present:
                            t['missing_protection_checks'] = 0
                            t['protection_status'] = 'confirmed'
                            t['protection_error'] = None
                            t['exchange_protection_verified'] = True
                            t['exchange_protected_size'] = sum(
                                abs(as_float(a.get('sz')))
                                for a in protective_algos
                                if isinstance(a, dict)
                            )
                            t['exchange_position_size'] = live_contracts
                        else:
                            missing_checks = int(t.get('missing_protection_checks') or 0) + 1
                            t['missing_protection_checks'] = missing_checks
                            t['protection_status'] = 'pending' if missing_checks < config.PROTECTION_MISSING_CONFIRMATIONS else 'failed'
                            t['exchange_protection_verified'] = False
                            t['exchange_protected_size'] = sum(
                                abs(as_float(a.get('sz')))
                                for a in protective_algos
                                if isinstance(a, dict)
                            )
                            t['exchange_position_size'] = live_contracts
                            if live_pos is not None and protective_algos and not protection_size_ok:
                                protected_size = sum(abs(as_float(a.get('sz'))) for a in protective_algos if isinstance(a, dict))
                                t['protection_error'] = (
                                    f'partial TP/SL protection only: protected {protected_size:g} / '
                                    f'position {live_contracts:g} contracts'
                                )
                            else:
                                t['protection_error'] = 'missing TP/SL protection'

                            close_size = abs(as_float((live_pos or {}).get('contracts')))
                            if close_size <= 0:
                                close_size = abs(as_float(t.get('filled_contracts')))
                            if close_size <= 0:
                                print(
                                    f"[URGENT] {t['symbol']} is missing TP/SL and no live position match was found; "
                                    "closing local record as quarantined."
                                )
                                close_orphan_trade_record(
                                    t,
                                    'missing_tp_sl_protection',
                                    protection_status='failed',
                                    protection_error='missing TP/SL protection',
                                )
                                continue

                            ccxt_sym = f"{normalize_symbol_key(t['symbol']).replace('USDT', '')}/USDT:USDT"
                            repair_context = live_pos if live_pos is not None else t
                            repair_plan = rebuild_protection_plan(t, live_pos=repair_context, journal_trade=journal_trade)
                            if repair_plan:
                                try:
                                    repair_key = t.get('clOrdId') or t.get('lifecycle_id') or t.get('symbol') or expected_inst_id
                                    repair = place_exact_fill_protection(
                                        ccxt_sym,
                                        t['direction'],
                                        close_size,
                                        repair_plan,
                                        f"REPAIR-{repair_key}",
                                    )
                                    repair_failed, repair_code, repair_message = okx_order_failed(repair)
                                    if not repair_failed:
                                        t['sl'] = repair_plan['sl']
                                        t['tp1'] = repair_plan['tp1']
                                        t['protection_order_id'] = repair.get('id')
                                        t['protection_order_ids'] = [str(repair.get('id'))] if repair.get('id') else []
                                        t['protection_status'] = 'confirmed'
                                        t['exchange_protection_verified'] = True
                                        t['exchange_protected_size'] = close_size
                                        t['exchange_position_size'] = close_size
                                        t['protection_error'] = None
                                        t['missing_protection_checks'] = 0
                                        print(f"[RECOVERY] {t['symbol']} protection restored on OKX.")
                                        continue
                                    t['protection_error'] = f"repair protection rejected: {repair_code}: {repair_message}"
                                    print(f"[RECOVERY] {t['symbol']} protection repair rejected: code={repair_code}, msg={repair_message}")
                                except Exception as repair_err:
                                    t['protection_error'] = f"repair protection failed: {repair_err}"
                                    print(f"[RECOVERY] {t['symbol']} protection repair failed: {repair_err}")

                            if live_pos is None:
                                if t.get('emergency_close_submitted') and missing_checks >= config.PROTECTION_MISSING_CONFIRMATIONS:
                                    print(
                                        f"[RECOVERY] {t['symbol']} no longer appears in OKX live positions after "
                                        "emergency close; closing stale local active record."
                                    )
                                    close_orphan_trade_record(
                                        t,
                                        'exchange_position_missing_after_emergency_close',
                                        protection_status='failed',
                                        protection_error='missing TP/SL protection; OKX live position no longer present',
                                    )
                                    continue
                                print(
                                    f"[WARN] {t['symbol']} live position snapshot missing; "
                                    "keeping record pending for one more sync cycle."
                                )
                                continue

                            if missing_checks < config.PROTECTION_MISSING_CONFIRMATIONS:
                                print(
                                    f"[WARN] {t['symbol']} missing TP/SL protection; "
                                    f"repair pending ({missing_checks}/{config.PROTECTION_MISSING_CONFIRMATIONS})."
                                )
                                continue

                            try:
                                ok, ec, em = emergency_close_unprotected(ccxt_sym, t['direction'], close_size)
                                if ok:
                                    t['emergency_close_submitted'] = True
                                    t['protection_status'] = 'failed'
                                    t['protection_error'] = 'missing TP/SL protection'
                                    print(f"[URGENT] {t['symbol']} had no TP/SL; emergency close submitted.")
                                elif okx_position_not_found_error(ec, em):
                                    print(f"[URGENT] {t['symbol']} emergency close 51169: position already closed. Removing from active trades.")
                                    close_orphan_trade_record(
                                        t,
                                        'missing_tp_sl_protection',
                                        protection_status='failed',
                                        protection_error='missing TP/SL protection',
                                    )
                                else:
                                    t['protection_error'] = f"missing TP/SL; emergency close failed: code={ec} {em}"
                                    print(f"[URGENT] {t['symbol']} emergency close failed: code={ec} {em}")
                            except Exception as emergency_err:
                                if okx_position_not_found_error(message=emergency_err):
                                    print(f"[URGENT] {t['symbol']} emergency close exception indicates position already closed. Removing from active trades.")
                                    close_orphan_trade_record(
                                        t,
                                        'missing_tp_sl_protection',
                                        protection_status='failed',
                                        protection_error='missing TP/SL protection',
                                    )
                                    continue
                                t['protection_error'] = f"missing TP/SL; emergency close failed: {emergency_err}"
                                print(f"[URGENT] {t['symbol']} emergency close failed: {emergency_err}")
                            continue
                        
                        # Current price is already refreshed from the live position snapshot.
                        if live_pos is not None and not as_float(t.get('current')) and as_float(live_pos.get('markPrice')) > 0:
                            t['current'] = float(live_pos['markPrice'])

                        fee_safe_stop = fee_safe_stop_price(
                            as_float(t.get('entry')),
                            t.get('direction'),
                        )
                        stop_is_locked = (
                            (t.get('direction') == 'long' and as_float(t.get('sl')) >= fee_safe_stop)
                            or (t.get('direction') == 'short' and 0 < as_float(t.get('sl')) <= fee_safe_stop)
                        )
                        if stop_is_locked:
                            t['stop_is_locked'] = True
                            live_contracts_for_lock = abs(as_float((live_pos or {}).get('contracts')))
                            if (
                                live_pos is not None
                                and live_position_has_protection(live_pos, protective_algos)
                                and protection_algos_cover_size(protective_algos, live_contracts_for_lock)
                            ):
                                t['protection_status'] = 'confirmed'
                                t['exchange_protection_verified'] = True
                                t['exchange_protected_size'] = sum(
                                    abs(as_float(a.get('sz')))
                                    for a in protective_algos
                                    if isinstance(a, dict)
                                )
                                t['exchange_position_size'] = live_contracts_for_lock
                        
                        # ?? DYNAMIC TRAILING STOP MECHANISM (??餈質馱甇Ｙ?)
                        if t.get('tp1') and t.get('sl') and t.get('entry'):
                            raw_strat = t.get('strategy', 'SqueezeHunter')
                            strat_lookup = 'SqueezeHunter' if raw_strat not in ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'] else raw_strat
                            runtime_optimizer = auto_tune_strategy_params(strat_lookup)
                            runner_prof = tuned_runner_profile(strat_lookup, runtime_optimizer)
                            t['optimizer'] = runtime_optimizer
                            t['runner_policy'] = runner_policy_text(runner_prof)

                            # Original theoretical distance to TP1
                            if 'original_tp_dist' not in t:
                                t['original_tp_dist'] = abs(t['tp1'] - t['entry'])
                            if 'original_sl_dist' not in t or not t.get('original_sl_dist'):
                                t['original_sl_dist'] = abs(t['entry'] - t['sl'])
                            
                            total_dist = t['original_tp_dist']
                            current_dist = abs(t['current'] - t['entry'])
                            is_profitable = (t['direction'] == 'long' and t['current'] > t['entry']) or (t['direction'] == 'short' and t['current'] < t['entry'])
                            risk_dist = float(t.get('original_sl_dist') or abs(t['entry'] - t['sl']) or 0)
                            favorable_move = (t['current'] - t['entry']) if t['direction'] == 'long' else (t['entry'] - t['current'])
                            t['current_r'] = round(favorable_move / risk_dist, 3) if risk_dist > 0 else 0

                            if not is_profitable and as_float(t.get('highest_r')) >= config.MFE_BE_R and not stop_is_locked:
                                t['trailing_stage'] = 'missed_be_lock'
                            
                            if is_profitable and total_dist > 0:
                                progress = current_dist / total_dist
                                
                                # Track High Water Mark (Highest progress reached)
                                highest_progress = t.get('highest_progress', 0.0)
                                if progress > highest_progress:
                                    t['highest_progress'] = progress
                                    highest_progress = progress
                                
                                new_sl = None
                                remove_tp = False
                                desired_stage = t.get('trailing_stage') or 'waiting'
                                
                                be_threshold = runner_prof['be_threshold']
                                lock_threshold = runner_prof['lock_threshold']
                                trail_buffer = runner_prof['trail_buffer']
                                remove_tp_at = runner_prof['remove_tp_at']
                                fee_safe_stop = fee_safe_stop_price(t['entry'], t['direction'])
                                cost_distance = abs(fee_safe_stop - t['entry'])
                                cost_progress = cost_distance / total_dist if total_dist > 0 else 1.0
                                be_threshold = max(be_threshold, cost_progress * 1.20)
                                lock_threshold = max(lock_threshold, be_threshold + 0.10)
                                cost_covered_now = favorable_move > cost_distance + abs(t['current']) * 0.0002
                                r_now = favorable_move / risk_dist if risk_dist > 0 else 0
                                t['current_r'] = round(r_now, 3)
                                highest_r = max(float(t.get('highest_r') or 0), r_now)
                                t['highest_r'] = round(highest_r, 3)
                                t['highest_pnl'] = round(max(float(t.get('highest_pnl') or 0), float(t.get('pnl') or 0)), 4)

                                lock_r = None
                                if raw_strat == 'MacroSniper' and highest_r >= 0.8:
                                    lock_r = 0.3
                                    desired_stage = 'macrosniper_profit_lock_0.3R'
                                elif highest_r >= config.MFE_RUNNER_R:
                                    lock_r = max(config.MFE_LOCK_FRACTION, highest_r - config.MFE_TRAIL_GIVEBACK_R)
                                    desired_stage = 'mfe_runner_lock'
                                elif highest_r >= config.MFE_LOCK_R:
                                    lock_r = config.MFE_LOCK_FRACTION
                                    desired_stage = 'mfe_profit_lock'
                                elif highest_r >= config.MFE_BE_R:
                                    lock_r = config.MFE_BE_LOCK_R
                                    desired_stage = 'mfe_break_even'

                                if lock_r is not None and risk_dist > 0 and cost_covered_now:
                                    if t['direction'] == 'long':
                                        new_sl = max(new_sl or -float('inf'), t['entry'] + risk_dist * lock_r, fee_safe_stop)
                                    else:
                                        new_sl = min(new_sl or float('inf'), t['entry'] - risk_dist * lock_r, fee_safe_stop)

                                if lock_r is None and cost_covered_now and highest_progress >= be_threshold and highest_progress < lock_threshold:
                                    if t['direction'] == 'long':
                                        new_sl = max(new_sl or -float('inf'), fee_safe_stop)
                                    else:
                                        new_sl = min(new_sl or float('inf'), fee_safe_stop)
                                    desired_stage = 'cost_safe_break_even'
                                     
                                elif cost_covered_now and highest_progress >= lock_threshold:
                                    locked_progress = max(0.0, highest_progress - trail_buffer)
                                     
                                    if t['direction'] == 'long':
                                        new_sl = max(new_sl or -float('inf'), t['entry'] + (total_dist * locked_progress), fee_safe_stop)
                                    else:
                                        new_sl = min(new_sl or float('inf'), t['entry'] - (total_dist * locked_progress), fee_safe_stop)
                                    
                                    desired_stage = 'runner'
                                    remove_tp = highest_progress >= remove_tp_at
                                t['runner_policy'] = runner_policy_text(runner_prof)

                                # APPLY CHANGES TO OKX
                                if new_sl:
                                    trigger_guard = max(abs(t['current']) * 0.0015, 1e-10)
                                    if t['direction'] == 'long' and new_sl >= t['current']:
                                        new_sl = t['current'] - trigger_guard
                                    elif t['direction'] == 'short' and new_sl <= t['current']:
                                        new_sl = t['current'] + trigger_guard

                                    # Only update if the new_sl is strictly BETTER than the current SL
                                    is_better_sl = (t['direction'] == 'long' and new_sl > t['sl']) or (t['direction'] == 'short' and new_sl < t['sl'])
                                    
                                    # Allow 0.05% margin for floating point comparison
                                    sl_diff_pct = abs(t['sl'] - new_sl) / t['entry']
                                    
                                    if is_better_sl and sl_diff_pct > 0.0005:
                                        if config.MOCK_MODE:
                                            # ? Mock Mode: ?砍?湔?湔璅⊥?迫?嚗?靽格鈭斗??
                                            t['sl'] = round(new_sl, 6)
                                            t['trailing_stage'] = desired_stage
                                            t['protection_status'] = 'confirmed'
                                            t['protection_error'] = None
                                            print(f"[?儭?MOCK TRAILING STOP] {t['symbol']} Mock SL moved locally to: {t['sl']} (Progress: {highest_progress*100:.1f}%)")
                                            continue
                                        
                                        retry_after = as_float(t.get('protection_retry_after'))
                                        if retry_after > time.time():
                                            continue
                                        for a in protective_algos:
                                            try:
                                                base_sym = normalize_symbol_key(t['symbol']).replace('USDT', '')
                                                # Handle special single letter symbols like H, HUSDT -> H/USDT:USDT
                                                ccxt_sym = f"{base_sym}/USDT:USDT"
                                                
                                                # Fallback check: if token markets aren't loaded or coin is not found by CCXT unified symbol, try fetching it via instId
                                                try:
                                                    formatted_sl = okx.price_to_precision(ccxt_sym, new_sl)
                                                except Exception:
                                                    ccxt_sym = f"{t.get('instId') or (base_sym + '-USDT-SWAP')}"
                                                    formatted_sl = okx.price_to_precision(ccxt_sym, new_sl)
                                                
                                                # Avoid redundant API calls if string format matches existing OKX order
                                                if formatted_sl == str(a.get('slTriggerPx')):
                                                    t['trailing_stage'] = desired_stage
                                                    t['protection_status'] = 'confirmed'
                                                    t['exchange_protection_verified'] = True
                                                    t['exchange_protected_size'] = sum(
                                                        abs(as_float(item.get('sz')))
                                                        for item in protective_algos
                                                        if isinstance(item, dict)
                                                    )
                                                    t['exchange_position_size'] = abs(as_float((live_pos or {}).get('contracts')))
                                                    t['protection_error'] = None
                                                    break
                                                    
                                                tp_update = None
                                                if remove_tp and not t.get('tp_removed'):
                                                    if t['direction'] == 'long':
                                                        far_tp = t['entry'] + (total_dist * 3.0)
                                                    else:
                                                        far_tp = max(0.0001, t['entry'] - (total_dist * 3.0))
                                                    try:
                                                        formatted_far_tp = okx.price_to_precision(ccxt_sym, far_tp)
                                                    except Exception:
                                                        formatted_far_tp = str(round(far_tp, 4))
                                                    if a.get('tp_limit_linked'):
                                                        t['tp_extension_status'] = 'kept_limit_tp_for_linked_oco_safety'
                                                    else:
                                                        tp_update = {
                                                            'newTpTriggerPx': formatted_far_tp,
                                                            'newTpOrdPx': '-1',
                                                        }

                                                res, failed, code, message = amend_protective_stop(
                                                    a, formatted_sl, tp_update
                                                )
                                                # 51119 = Order amend details cannot be same
                                                if failed and str(code) == '51119':
                                                    failed = False
                                                
                                                if not failed:
                                                    print(f"[?儭?TRAILING STOP] {t['symbol']} SL moved to: {formatted_sl} (Progress: {highest_progress*100:.1f}%)")
                                                    t['sl'] = float(formatted_sl)
                                                    t['trailing_stage'] = desired_stage
                                                    t['protection_status'] = 'confirmed'
                                                    t['exchange_protection_verified'] = True
                                                    t['exchange_protected_size'] = sum(
                                                        abs(as_float(item.get('sz')))
                                                        for item in protective_algos
                                                        if isinstance(item, dict)
                                                    )
                                                    t['exchange_position_size'] = abs(as_float((live_pos or {}).get('contracts')))
                                                    t['protection_error'] = None
                                                    t['protection_retry_count'] = 0
                                                    t['protection_retry_after'] = 0
                                                    if tp_update:
                                                        t['tp_removed'] = True
                                                        print(f"[?? INFINITE RUN] {t['symbol']} TP ceiling extended after confirmed amend.")
                                                    break
                                                else:
                                                    failures = int(t.get('protection_retry_count') or 0) + 1
                                                    t['trailing_stage'] = 'protection_failed'
                                                    t['protection_status'] = 'failed'
                                                    t['protection_retry_count'] = failures
                                                    t['protection_retry_after'] = time.time() + protection_retry_delay(failures)
                                                    t['protection_error'] = f"{code}: {message}"
                                                    print(f"[ERROR] Amend failed for {t['symbol']}: code={code}, msg={message}")
                                            except Exception as e:
                                                failures = int(t.get('protection_retry_count') or 0) + 1
                                                t['trailing_stage'] = 'protection_failed'
                                                t['protection_status'] = 'failed'
                                                t['protection_retry_count'] = failures
                                                t['protection_retry_after'] = time.time() + protection_retry_delay(failures)
                                                t['protection_error'] = str(e)
                                                print(f"[ERROR] Failed to trail stop for {t['symbol']}: {e}")
                # Save the persisted state so we don't lose UI metadata on restart
                write_json_atomic(config.TRADE_FILE, state.active_trades)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(3)

