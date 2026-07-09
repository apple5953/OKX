import datetime
import json
import os
import sys
import socket
from types import SimpleNamespace
from . import config
from . import state

# FORCE UTF-8 Encoding to prevent crash when printing emojis on Windows cp950 console
sys.stdout.reconfigure(encoding='utf-8')

def acquire_instance_guard(port=5017):
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow immediate rebind after crash (avoids "Address already in use" on restart)
    guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        # Windows-specific: still check for truly exclusive reuse
        try:
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except OSError:
            pass
    guard.bind(('127.0.0.1', port))
    guard.listen(1)
    state.instance_guard_socket = guard

def write_json_atomic(path, data):
    def default_json(value):
        if hasattr(value, 'item'):
            try:
                return value.item()
            except Exception:
                pass
        if hasattr(value, 'isoformat'):
            try:
                return value.isoformat()
            except Exception:
                pass
        return str(value)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, default=default_json)
    os.replace(tmp_path, path)

def load_json_list_candidates(paths, label):
    """Load the first valid JSON list from a set of candidate paths."""
    last_error = None
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            data = repair_truncated_json_list(path)
            if isinstance(data, list):
                return data, path
        except Exception as e:
            last_error = e
    if last_error:
        print(f"Failed to load {label} from candidates: {last_error}")
    return [], None

def repair_truncated_json_list(path):
    raw = open(path, 'r', encoding='utf-8').read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        cut = raw.rfind('}, {', 0, err.pos)
        if cut == -1:
            raise
        repaired = raw[:cut + 1] + ']'
        data = json.loads(repaired)
        backup = f"{path}.corrupt-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        os.replace(path, backup)
        write_json_atomic(path, data)
        print(f"Repaired truncated {path}; kept {len(data)} records, backup={backup}")
        return data

def load_json_list(path, label):
    if not os.path.exists(path):
        return []
    try:
        data = repair_truncated_json_list(path)
        return data if isinstance(data, list) else []
    except Exception as e:
        backup = f"{path}.bad-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        try:
            os.replace(path, backup)
        except Exception:
            backup = 'backup failed'
        print(f"Failed to load {label} state: {e}; backup={backup}")
        return []

def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def session_start_equity():
    if config.SESSION_START_EQUITY_USDT is None:
        base_equity = 0.0
        # Will be updated when account data is fetched
        if hasattr(state, 'account_data') and isinstance(state.account_data, dict):
            base_equity = as_float(
                state.account_data.get('usdtEq')
                or state.account_data.get('totalEq')
                or state.account_data.get('equity')
            )
        if base_equity > 0:
            config.SESSION_START_EQUITY_USDT = base_equity
    return config.SESSION_START_EQUITY_USDT if config.SESSION_START_EQUITY_USDT is not None else config.START_EQUITY_USDT

def session_started_at_ms():
    return timestamp_ms(config.SESSION_STARTED_AT)

def is_session_trade(trade):
    started_ms = session_started_at_ms()
    trade_ms = trade_open_timestamp_ms(trade)
    if trade_ms <= 0:
        trade_ms = timestamp_ms(
            trade.get('opened_at')
            or trade.get('open_timestamp')
            or trade.get('timestamp')
            or trade.get('closed_at')
        )
    return trade_ms >= started_ms if trade_ms > 0 else False

def timestamp_ms(value):
    if value in [None, '']:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        try:
            return int(datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp() * 1000)
        except (TypeError, ValueError):
            return 0

def trade_open_timestamp_ms(trade):
    return timestamp_ms(trade.get('opened_at') or trade.get('open_timestamp'))

def history_pos_id(record):
    info = record.get('info') or {}
    return str(info.get('posId') or record.get('posId') or record.get('id') or '')

def history_event_key(record):
    info = record.get('info') or {}
    pos_id = history_pos_id(record)
    close_ms = timestamp_ms(
        record.get('lastUpdateTimestamp') or record.get('timestamp')
        or info.get('uTime') or info.get('cTime')
    )
    return f'{pos_id}:{close_ms}' if pos_id and close_ms else ''

def lifecycle_trade_for_history(record):
    info = record.get('info') or {}
    pos_id = history_pos_id(record)
    opened_ms = timestamp_ms(info.get('cTime') or record.get('datetime') or record.get('timestamp'))
    inst_id = str(info.get('instId') or record.get('instId') or '')
    direction = str(info.get('direction') or record.get('side') or '').lower()
    candidates = []
    for trade in state.trade_journal + state.active_trades:
        if str(trade.get('posId') or '') != pos_id:
            continue
        trade_open_ms = trade_open_timestamp_ms(trade)
        if not trade_open_ms or not opened_ms:
            continue
        trade_inst = str(trade.get('instId') or '')
        trade_direction = str(trade.get('direction') or '').lower()
        if inst_id and trade_inst and inst_id != trade_inst:
            continue
        if direction and trade_direction and direction != trade_direction:
            continue
        distance = abs(trade_open_ms - opened_ms)
        if distance <= config.LIFECYCLE_OPEN_TOLERANCE_MS:
            manual_rank = 1 if str(trade.get('strategy') or '') == 'Manual' else 0
            candidates.append((manual_rank, distance, trade_open_ms, trade))
    if not candidates and pos_id:
        # Some OKX history payloads expose a distinct record id while the
        # lifecycle match lives under info.posId. If the timestamp tolerance
        # misses, fall back to a strict posId/instId/direction match so the
        # strategy identity is not lost and later normalized to Manual.
        for trade in state.trade_journal + state.active_trades:
            trade_pos_id = str(trade.get('posId') or '')
            if trade_pos_id != pos_id:
                continue
            trade_inst = str(trade.get('instId') or '')
            trade_direction = str(trade.get('direction') or '').lower()
            if inst_id and trade_inst and inst_id != trade_inst:
                continue
            if direction and trade_direction and direction != trade_direction:
                continue
            trade_open_ms = trade_open_timestamp_ms(trade)
            distance = abs(trade_open_ms - opened_ms) if trade_open_ms and opened_ms else 0
            manual_rank = 1 if str(trade.get('strategy') or '') == 'Manual' else 0
            candidates.append((manual_rank, distance, trade_open_ms, trade))
    if not candidates and inst_id and direction:
        # Broader recovery path: if the exact posId match is missing, try to
        # recover the lifecycle from the same instrument/direction pair near the
        # recorded open time instead of defaulting to Manual immediately.
        for trade in state.trade_journal + state.active_trades:
            trade_inst = str(trade.get('instId') or '')
            trade_direction = str(trade.get('direction') or '').lower()
            if trade_inst and inst_id and trade_inst != inst_id:
                continue
            if trade_direction and direction and trade_direction != direction:
                continue
            trade_open_ms = trade_open_timestamp_ms(trade)
            if not trade_open_ms:
                continue
            if opened_ms:
                distance = abs(trade_open_ms - opened_ms)
                if distance > config.LIFECYCLE_OPEN_TOLERANCE_MS * 4:
                    continue
            else:
                distance = 0
            manual_rank = 1 if str(trade.get('strategy') or '') == 'Manual' else 0
            candidates.append((manual_rank, distance, trade_open_ms, trade))
    if not candidates:
        return None
    return min(candidates, key=lambda row: (row[0], row[1], -row[2]))[3]

def assess_accounting_record(record, lifecycle):
    """Keep suspicious OKX history visible, but out of learning and sizing."""
    strategy_name = record.get('strategy')
    is_valid_strategy = strategy_name in ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter']

    if not lifecycle:
        return {
            'accounting_status': 'verified' if is_valid_strategy else 'manual',
            'eligible_for_learning': is_valid_strategy, # 如果是四大核心策略產生的單，強制允許納入學習
            'accounting_reasons': [] if is_valid_strategy else ['no exact strategy lifecycle match'],
        }

    info = record.get('info') or {}
    realized = as_float(
        record.get('realizedPnl', record.get('realized_pnl', record.get('pnl')))
    )
    open_price = as_float(
        record.get('openPrice', info.get('openAvgPx', record.get('entryPrice')))
    )
    close_price = as_float(
        record.get('closePrice', record.get('close_price', info.get('closeAvgPx')))
    )
    expected_entry = as_float(lifecycle.get('entry'))
    stop_distance = as_float(lifecycle.get('original_sl_dist'))
    if stop_distance <= 0:
        stop_price = as_float(lifecycle.get('sl'))
        stop_distance = abs(expected_entry - stop_price) if expected_entry and stop_price else 0.0
    planned_loss = max(
        as_float(lifecycle.get('max_planned_loss_usdt'), config.MAX_PLANNED_LOSS_USDT),
        config.MAX_PLANNED_LOSS_USDT,
    )
    reasons = []

    if expected_entry > 0 and open_price > 0:
        entry_tolerance = max(expected_entry * 0.01, stop_distance * 2.0)
        if abs(open_price - expected_entry) > entry_tolerance:
            reasons.append('exchange open price does not match lifecycle entry')

    direction = str(lifecycle.get('direction') or '').lower()
    adverse_move = 0.0
    if expected_entry > 0 and close_price > 0:
        adverse_move = (
            expected_entry - close_price
            if direction in ['long', 'buy']
            else close_price - expected_entry
        )
    extreme_loss = realized < -(planned_loss * config.ACCOUNTING_LOSS_QUARANTINE_MULTIPLIER)
    extreme_price = adverse_move > max(
        stop_distance * config.ACCOUNTING_STOP_OVERSHOOT_MULTIPLIER,
        expected_entry * config.ACCOUNTING_MIN_ADVERSE_MOVE_PCT,
    ) if expected_entry > 0 else False
    if extreme_loss and extreme_price:
        reasons.append('loss and close price exceed lifecycle risk envelope')

    # 強制放寬：如果是核心策略單，即使觸發了隔離審計，也依然允許學習其虧損和盈利軌跡來修復參數
    return {
        'accounting_status': 'quarantined' if reasons else 'verified',
        'eligible_for_learning': True if is_valid_strategy else not reasons,
        'accounting_reasons': reasons,
    }

def clamp(value, low, high):
    return max(low, min(value, high))

def json_safe(value):
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, 'isoformat'):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)
