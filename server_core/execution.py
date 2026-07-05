import time
import uuid
from . import config
from . import state
from .utils import as_float, clamp
from .okx_client import okx, resolve_okx_inst_id

ENTRY_EXECUTION_POLICIES = {
    'MacroSniper': {'base_slippage': 0.0006, 'slippage_cap': 0.0018, 'attempts': 3},
    'MeanReversion': {'base_slippage': 0.0004, 'slippage_cap': 0.0012, 'attempts': 3},
    'Contrarian': {'base_slippage': 0.0005, 'slippage_cap': 0.0015, 'attempts': 3},
    'SqueezeHunter': {'base_slippage': 0.0008, 'slippage_cap': 0.0020, 'attempts': 3},
}

def expected_trade_edge(notional_usdt, tp_dist_pct, market_quality):
    gross_target = max(0.0, notional_usdt) * max(0.0, tp_dist_pct)
    estimated_cost = max(0.0, notional_usdt) * (
        config.ROUND_TRIP_TAKER_RATE + as_float(market_quality.get('exit_slippage_pct'))
    )
    expected_net = gross_target - estimated_cost
    required_gross = max(
        estimated_cost * config.MIN_GROSS_TO_COST_RATIO,
        estimated_cost + config.MIN_EXPECTED_NET_PROFIT_USDT,
    )
    return {
        'gross_target_usdt': round(gross_target, 4),
        'estimated_cost_usdt': round(estimated_cost, 4),
        'expected_net_usdt': round(expected_net, 4),
        'required_gross_usdt': round(required_gross, 4),
        'passes': gross_target >= required_gross,
    }

def risk_based_leverage_cap(margin_usdt, sl_dist_pct, exit_slippage_pct=config.SLIPPAGE_BUFFER_RATE, symbol=None):
    max_cap = config.MAX_LEVERAGE_CAP
    if symbol:
        sym_clean = str(symbol).upper()
        if not any(k in sym_clean for k in ['BTC', 'ETH', 'XAU', 'GOLD']):
            max_cap = 5
            
    total_loss_rate = max(0.0001, sl_dist_pct + config.ROUND_TRIP_TAKER_RATE + exit_slippage_pct)
    cap = int(config.MAX_PLANNED_LOSS_USDT / (max(margin_usdt, 1.0) * total_loss_rate))
    return max(1, min(max_cap, cap))

def refresh_order(order, symbol):
    order_id = order.get('id')
    if not order_id:
        return order
    try:
        return okx.fetch_order(order_id, symbol)
    except Exception:
        return order

def wait_for_order(order, symbol, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    latest = order
    while time.monotonic() < deadline:
        latest = refresh_order(latest, symbol)
        status = str(latest.get('status') or '').lower()
        if status in ['closed', 'canceled', 'rejected', 'expired']:
            break
        time.sleep(0.5)
    return refresh_order(latest, symbol)

def execute_bounded_limit_entry(symbol, side, size, strategy_name, client_order_id, atr_pct=0.0):
    policy = ENTRY_EXECUTION_POLICIES[strategy_name]

    for attempt in range(policy['attempts']):
        book = okx.fetch_order_book(symbol, limit=10)
        best_bid = as_float(book['bids'][0][0]) if book.get('bids') else 0.0
        best_ask = as_float(book['asks'][0][0]) if book.get('asks') else 0.0
        touch_price = best_ask if side == 'buy' else best_bid
        if touch_price <= 0:
            raise ValueError(f"No executable order book price for {symbol}")

        cap = clamp(
            policy['base_slippage'] + max(0.0, atr_pct) * 0.04,
            policy['base_slippage'],
            policy['slippage_cap'],
        )
        limit_price = touch_price * (1.0 + cap if side == 'buy' else 1.0 - cap)
        attempt_id = f"{client_order_id[:22]}{attempt}{uuid.uuid4().hex[:4]}"
        order = okx.create_order(symbol, 'limit', side, size, limit_price, {
            'tdMode': 'cross',
            'clientOrderId': attempt_id[:32],
            'timeInForce': 'FOK',
        })
        order = wait_for_order(order, symbol, 1.5)
        filled = as_float(order.get('filled'))
        if filled >= size * 0.999:
            return {
                'order': order,
                'filled': filled,
                'average': as_float(order.get('average'), touch_price),
                'execution': 'bounded_fok_limit',
                'limit_price': limit_price,
                'max_slippage': cap,
                'spread_pct': (best_ask - best_bid) / ((best_ask + best_bid) / 2) if best_bid > 0 and best_ask > 0 else 0.0,
            }
        time.sleep(0.35 * (attempt + 1))
    return None

def rebase_plan_to_fill(plan, signal_price, fill_price, direction):
    sl_distance = abs(signal_price - plan['sl'])
    tp_distance = abs(plan['tp1'] - signal_price)
    if direction == 'long':
        plan['sl'] = fill_price - sl_distance
        plan['tp1'] = fill_price + tp_distance
    else:
        plan['sl'] = fill_price + sl_distance
        plan['tp1'] = fill_price - tp_distance
    plan['entry'] = fill_price
    plan['sl_dist_pct'] = round(sl_distance / fill_price, 5)
    plan['tp_dist_pct'] = round(tp_distance / fill_price, 5)
    return plan

def place_exact_fill_protection(symbol, direction, filled_size, plan, client_order_id):
    close_side = 'sell' if direction == 'long' else 'buy'
    protection_id = f"P{client_order_id}"[:32]
    return okx.create_order(symbol, 'oco', close_side, filled_size, None, {
        'tdMode': 'cross',
        'clientOrderId': protection_id,
        'reduceOnly': True,
        'takeProfitPrice': plan['tp1'],
        'tpOrdPx': plan['tp1'],
        'tpOrdKind': 'limit',
        'tpTriggerPxType': 'last',
        'stopLossPrice': plan['sl'],
        'slOrdPx': -1,
        'slTriggerPxType': 'mark',
        'cxlOnClosePos': True,
    })

def emergency_close_unprotected(symbol, direction, filled_size):
    """Close a position in Net Mode. Returns (success, error_code, error_msg)."""
    close_side = 'sell' if direction == 'long' else 'buy'
    try:
        result = okx.create_order(symbol, 'market', close_side, filled_size, None, {
            'tdMode': 'cross',
            'posSide': 'net',       # Required for Net Mode on OKX
            'reduceOnly': True,
        })
        info = (result or {}).get('info') or {}
        data = info.get('data') or [{}]
        s_code = str((data[0] if data else {}).get('sCode') or '0')
        if s_code not in ['', '0']:
            s_msg = (data[0] if data else {}).get('sMsg', '')
            return False, s_code, s_msg
        return True, '0', ''
    except Exception as e:
        err_str = str(e)
        # 51169 = no positions in this direction (already closed)
        if '51169' in err_str:
            return False, '51169', 'Position already closed or does not exist'
        raise

def okx_order_failed(result):
    info = dict((result or {}).get('info') or {})
    code = str(info.get('sCode') or info.get('code') or '0')
    message = str(info.get('sMsg') or info.get('msg') or '')
    failed = code not in ['', '0'] or any(word in message.lower() for word in ['fail', 'reject', 'error', 'invalid'])
    return failed, code, message

def okx_algo_amend_error(result):
    if not isinstance(result, dict):
        return True, 'invalid_response', str(result)
    top_code = str(result.get('code') or '0')
    top_message = str(result.get('msg') or '')
    rows = result.get('data') or []
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    item_code = str(row.get('sCode') or '0')
    item_message = str(row.get('sMsg') or '')
    failed = top_code not in ['', '0'] or item_code not in ['', '0']
    return failed, item_code if item_code not in ['', '0'] else top_code, item_message or top_message

def protective_algo_targets(all_algos, inst_id, expected_side, tracked_algo_ids=None):
    tracked = {str(value) for value in (tracked_algo_ids or []) if value}
    targets = []
    seen = set()
    for algo in all_algos:
        if algo.get('instId') != inst_id or algo.get('side') != expected_side:
            continue
        algo_id = str(algo.get('algoId') or '')
        linked = algo.get('linkedAlgoOrd') or {}
        linked_id = str(linked.get('algoId') or '') if isinstance(linked, dict) else ''
        if tracked and algo_id not in tracked and linked_id not in tracked:
            continue

        if linked_id:
            target = {
                'instId': algo.get('instId'),
                'algoId': linked_id,
                'slTriggerPx': linked.get('slTriggerPx') or algo.get('slTriggerPx'),
                'tp_limit_linked': True,
                'parentAlgoId': algo_id,
            }
        elif as_float(algo.get('slTriggerPx')) > 0:
            target = dict(algo)
            target['tp_limit_linked'] = False
        else:
            continue
        key = (target.get('instId'), str(target.get('algoId') or ''))
        if key[1] and key not in seen:
            targets.append(target)
            seen.add(key)
    return targets

def protection_retry_delay(failure_count):
    return min(
        config.PROTECTION_RETRY_MAX_SECONDS,
        config.PROTECTION_RETRY_BASE_SECONDS * (2 ** max(0, int(failure_count) - 1)),
    )

def amend_protective_stop(algo, formatted_sl, tp_update=None):
    payload = {
        'instId': algo['instId'],
        'algoId': algo['algoId'],
        'newSlTriggerPx': formatted_sl,
        'newSlOrdPx': '-1',
    }
    if tp_update and not algo.get('tp_limit_linked'):
        payload.update(tp_update)
    result = okx.private_post_trade_amend_algos(payload)
    failed, code, message = okx_algo_amend_error(result)
    if failed and tp_update and str(code) == '51098':
        payload = dict(payload)
        payload.pop('newTpTriggerPx', None)
        payload.pop('newTpOrdPx', None)
        payload.pop('newTpOrdKind', None)
        result = okx.private_post_trade_amend_algos(payload)
        failed, code, message = okx_algo_amend_error(result)
    return result, failed, code, message

def fetch_exchange_max_contracts(symbol, side):
    try:
        inst_id = resolve_okx_inst_id(symbol)
        response = okx.private_get_account_max_size({
            'instId': inst_id,
            'tdMode': 'cross',
        })
        rows = response.get('data') or []
        if not rows:
            return float('inf')
        key = 'maxBuy' if side == 'buy' else 'maxSell'
        maximum = as_float(rows[0].get(key))
        return maximum if maximum > 0 else float('inf')
    except Exception as exc:
        print(f"Max-size lookup failed for {symbol}: {exc}")
        return float('inf')
