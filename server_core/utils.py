import datetime
import json
import os
import sys
import socket
import shutil
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

def load_json_dict(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def infer_strategy_from_metadata(*sources, fallback='Manual'):
    """Infer the real bot strategy from lifecycle metadata without trusting Manual."""
    valid = set(config.STRATEGY_PROFILES.keys())
    label_map = {
        'macro sniper': 'MacroSniper',
        'macrosniper': 'MacroSniper',
        'macro': 'MacroSniper',
        'mean reversion': 'MeanReversion',
        'meanreversion': 'MeanReversion',
        'mean': 'MeanReversion',
        'contrarian': 'Contrarian',
        'squeeze hunter': 'SqueezeHunter',
        'squeezehunter': 'SqueezeHunter',
        'squeeze': 'SqueezeHunter',
    }

    rows = [row for row in sources if isinstance(row, dict)]
    for row in rows:
        strategy = str(row.get('strategy') or '')
        if strategy in valid:
            return strategy
        for mixed in row.get('strategy_mix') or []:
            if str(mixed) in valid:
                return str(mixed)

    for row in rows:
        text = ' '.join(
            str(row.get(key) or '')
            for key in [
                'pattern', 'entry_reason', 'mode_reason', 'exit_model',
                'runner_policy', 'setup_source', 'category_key', 'mode_verdict',
            ]
        ).lower()
        for needle, strategy in label_map.items():
            if needle in text:
                return strategy

    for row in rows:
        optimizer = row.get('optimizer') or {}
        has_lifecycle_evidence = any(
            row.get(key) not in [None, '', [], {}]
            for key in ['lifecycle_id', 'strategy_version', 'entry_reason', 'signal_candle']
        )
        pattern = str(row.get('pattern') or '')
        if pattern and pattern != 'Manual / Unsynced':
            has_lifecycle_evidence = True
        if isinstance(optimizer, dict) and has_lifecycle_evidence:
            strategy = str(optimizer.get('strategy') or '')
            if strategy in valid:
                return strategy

    for row in rows:
        strategy = str(row.get('strategy') or '')
        if strategy and strategy not in {'Manual', 'Mixed'}:
            return strategy
    return fallback

def has_valid_protection(trade):
    if not isinstance(trade, dict):
        return False
    sl = as_float(trade.get('sl'))
    tp1 = as_float(trade.get('tp1'))
    if sl <= 0 or tp1 <= 0:
        return False
    status = str(trade.get('protection_status') or '').lower()
    if status != 'confirmed':
        return False
    if not config.MOCK_MODE and not trade.get('exchange_protection_verified'):
        return False
    return True

def session_start_equity():
    if config.SESSION_START_EQUITY_USDT is None:
        baseline = load_json_dict(getattr(config, 'ACCOUNT_SESSION_BASELINE_FILE', ''))
        saved_equity = as_float(baseline.get('session_start_equity'))
        if saved_equity > 0:
            config.SESSION_START_EQUITY_USDT = saved_equity
            saved_started_at = baseline.get('session_started_at')
            if saved_started_at:
                config.SESSION_STARTED_AT = saved_started_at
            return config.SESSION_START_EQUITY_USDT

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
            started_at = config.SESSION_STARTED_AT or datetime.datetime.now().isoformat(timespec='seconds')
            try:
                write_json_atomic(getattr(config, 'ACCOUNT_SESSION_BASELINE_FILE', ''), {
                    'node_name': config.NODE_NAME,
                    'strategy_version': config.STRATEGY_VERSION,
                    'session_started_at': started_at,
                    'session_start_equity': round(base_equity, 8),
                    'source': 'okx_account_snapshot',
                })
            except Exception as exc:
                print(f"Failed to persist account session baseline: {exc}")
    return config.SESSION_START_EQUITY_USDT if config.SESSION_START_EQUITY_USDT is not None else config.START_EQUITY_USDT

def reset_session_equity_baseline():
    config.SESSION_STARTED_AT = datetime.datetime.now().isoformat(timespec='seconds')
    config.SESSION_START_EQUITY_USDT = None
    path = getattr(config, 'ACCOUNT_SESSION_BASELINE_FILE', '')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as exc:
            print(f"Failed to remove account session baseline: {exc}")

def session_started_at_ms():
    return timestamp_ms(config.SESSION_STARTED_AT)

def learning_cutoff_ms():
    """Earliest close/open time allowed to affect V13 learning metrics."""
    if config.ZERO_START_MODE:
        manifest = load_json_dict(config.ZERO_START_STATE_FILE)
        reset_ms = timestamp_ms(
            manifest.get('reset_at')
            or manifest.get('bootstrapped_at')
        )
        if reset_ms > 0:
            return reset_ms
    return session_started_at_ms()

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
    open_price = as_float(
        info.get('openAvgPx')
        or record.get('openPrice')
        or record.get('entryPrice')
        or record.get('avgPx')
    )
    candidates = []
    def add_candidate(trade, distance=0, active_rank=None):
        trade_open_ms = trade_open_timestamp_ms(trade)
        trade_entry = as_float(trade.get('entry'))
        entry_delta = abs(open_price - trade_entry) if open_price > 0 and trade_entry > 0 else 0.0
        entry_scale = max(open_price, trade_entry, 1.0)
        entry_rank = entry_delta / entry_scale if entry_scale > 0 else 0.0
        manual_rank = 1 if str(trade.get('strategy') or '') == 'Manual' else 0
        if active_rank is None:
            active_rank = 0 if trade in state.active_trades else 1
        candidates.append((manual_rank, active_rank, entry_rank, distance, trade_open_ms or 0, trade))

    for trade in list(reversed(state.active_trades)) + list(reversed(state.trade_journal)):
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
            add_candidate(trade, distance)
    if not candidates and pos_id:
        # Some OKX history payloads expose a distinct record id while the
        # lifecycle match lives under info.posId. If the timestamp tolerance
        # misses, fall back to a strict posId/instId/direction match so the
        # strategy identity is not lost and later normalized to Manual.
        for trade in list(reversed(state.active_trades)) + list(reversed(state.trade_journal)):
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
            add_candidate(trade, distance)
    if not candidates and inst_id and direction:
        # Broader recovery path: if the exact posId match is missing, try to
        # recover the lifecycle from the same instrument/direction pair near the
        # recorded open time instead of defaulting to Manual immediately.
        for trade in list(reversed(state.active_trades)) + list(reversed(state.trade_journal)):
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
            add_candidate(trade, distance)
    if not candidates:
        return None
    return min(candidates, key=lambda row: (row[0], row[1], row[2], row[3], -row[4]))[5]

def default_training_cycle_state():
    return {
        'generation': config.STRATEGY_VERSION,
        'last_evaluated_trade_count': 0,
        'completed_cycles': 0,
        'consecutive_positive_cycles': 0,
        'last_checked_at': None,
        'mode': 'training_active',
        'summary': {},
        'top_drags': [],
        'strategies': {},
        'notes': '',
    }

def zero_start_manifest():
    return {
        'node_name': config.NODE_NAME,
        'strategy_version': config.STRATEGY_VERSION,
        'zero_start_mode': True,
        'bootstrapped_at': datetime.datetime.now(datetime.UTC).isoformat(),
    }

def ensure_zero_start_storage(force=False):
    if not config.ZERO_START_MODE and not force:
        return {
            'reset': False,
            'reason': 'zero-start disabled',
            'manifest_path': config.ZERO_START_STATE_FILE,
        }

    manifest_path = config.ZERO_START_STATE_FILE
    manifest = load_json_dict(manifest_path)
    current_version = str(config.STRATEGY_VERSION).strip().lower()
    saved_version = str(manifest.get('strategy_version') or '').strip().lower()
    saved_node = str(manifest.get('node_name') or '').strip().lower()
    saved_mode = bool(manifest.get('zero_start_mode'))

    needs_reset = (
        force
        or not manifest
        or not saved_mode
        or saved_version != current_version
        or saved_node != str(config.NODE_NAME).strip().lower()
    )

    if not needs_reset:
        return {
            'reset': False,
            'reason': 'manifest already matches current generation',
            'manifest_path': manifest_path,
            'manifest': manifest,
        }

    backup_root = os.path.join(config.PROJECT_DIR, 'backups')
    backup_dir = os.path.join(
        backup_root,
        f"zero-start-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    os.makedirs(backup_dir, exist_ok=True)

    paths_to_backup = [
        config.JOURNAL_FILE,
        config.TRADE_FILE,
        config.LEGACY_JOURNAL_FILE,
        config.LEGACY_TRADE_FILE,
        *config.LOCAL_POSITIONS_SNAPSHOT_PATHS,
        *config.LOCAL_ACCOUNT_SNAPSHOT_PATHS,
        config.ZERO_START_STATE_FILE,
        getattr(config, 'ACCOUNT_SESSION_BASELINE_FILE', ''),
        config.GLOBAL_OPTIMIZER_FILE,
        config.TRAINING_CYCLE_STATE_FILE,
    ]
    for raw_path in paths_to_backup:
        if not raw_path or not os.path.exists(raw_path):
            continue
        try:
            shutil.move(raw_path, os.path.join(backup_dir, os.path.basename(raw_path)))
        except Exception:
            pass

    write_json_atomic(config.JOURNAL_FILE, [])
    write_json_atomic(config.TRADE_FILE, [])
    write_json_atomic(config.GLOBAL_OPTIMIZER_FILE, {})
    write_json_atomic(config.TRAINING_CYCLE_STATE_FILE, default_training_cycle_state())

    manifest_payload = zero_start_manifest()
    manifest_payload.update({
        'reset_at': datetime.datetime.now(datetime.UTC).isoformat(),
        'backup_dir': backup_dir,
        'reset_reason': 'first launch or version change requires zero-start',
    })
    write_json_atomic(manifest_path, manifest_payload)

    print(
        f"[Zero-Start] Initialized V{config.STRATEGY_VERSION} zero-start for {config.NODE_NAME}; "
        f"backup={backup_dir}"
    )
    return {
        'reset': True,
        'reason': 'initialized zero-start storage',
        'manifest_path': manifest_path,
        'manifest': manifest_payload,
        'backup_dir': backup_dir,
    }

def assess_accounting_record(record, lifecycle):
    """Keep suspicious OKX history visible, but out of learning and sizing."""
    strategy_name = record.get('strategy') or (lifecycle or {}).get('strategy')
    valid_strategies = ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter']
    # Some legacy lifecycle rows do not carry a strategy name, but still have an
    # exact lifecycle match. Keep them learnable if the risk envelope is sane.
    is_valid_strategy = strategy_name in valid_strategies or (not strategy_name and bool(lifecycle))

    if not lifecycle:
        return {
            'accounting_status': 'unmatched' if is_valid_strategy else 'manual',
            'eligible_for_learning': False,
            'accounting_reasons': ['no exact strategy lifecycle match'],
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
    lifecycle_sl = as_float(lifecycle.get('sl'))
    lifecycle_tp1 = as_float(lifecycle.get('tp1'))
    protection_status = str(lifecycle.get('protection_status') or '').lower()
    exit_reason = str(lifecycle.get('exit_reason') or '').lower()
    sync_status = str(lifecycle.get('sync_status') or '').lower()
    if (
        lifecycle.get('emergency_close_submitted')
        or 'emergency' in exit_reason
        or 'repair' in exit_reason
        or 'manual_close' in exit_reason
        or sync_status == 'closed_without_open_position'
    ):
        reasons.append('repair/emergency close is not a strategy learning sample')
    if lifecycle_sl <= 0 or protection_status in {'failed', 'pending', 'unconfirmed'}:
        reasons.append('missing TP/SL protection')

    if expected_entry > 0 and open_price > 0:
        entry_delta = abs(open_price - expected_entry)
        entry_tolerance = max(expected_entry * 0.015, stop_distance * 4.0)
        hard_entry_tolerance = max(expected_entry * 0.05, stop_distance * 10.0)
        if entry_delta > hard_entry_tolerance:
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
    elif expected_entry > 0 and open_price > 0 and abs(open_price - expected_entry) > entry_tolerance:
        # OKX position history can report an averaged open price after partial
        # fills or add-ons. Keep the loss learnable if the close still stayed
        # inside the planned risk envelope.
        record['accounting_warnings'] = list(record.get('accounting_warnings') or [])
        record['accounting_warnings'].append('exchange open price differs from lifecycle entry but stayed within risk envelope')

    # 強制放寬：如果是核心策略單，即使觸發了隔離審計，也依然允許學習其虧損和盈利軌跡來修復參數
    return {
        'accounting_status': 'quarantined' if reasons else 'verified',
        'eligible_for_learning': bool(is_valid_strategy and not reasons),
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
