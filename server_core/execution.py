import time
import uuid
from . import config
from . import state
from .utils import as_float, clamp
from .okx_client import okx, resolve_okx_inst_id, load_local_market_snapshot

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

def set_okx_leverage(leverage, symbol, margin_mode='cross'):
    inst_id = resolve_okx_inst_id(symbol)
    payload = {
        'instId': inst_id,
        'lever': str(int(leverage)),
        'mgnMode': margin_mode,
    }
    raw_method = getattr(okx, 'private_post_account_set_leverage', None) or getattr(okx, 'privatePostAccountSetLeverage', None)
    if raw_method is None:
        raise AttributeError('OKX leverage endpoint unavailable on exchange client')
    return raw_method(payload)

def _order_result_success(result):
    if not isinstance(result, dict):
        return False
    top_code = str(result.get('code') or '0')
    top_msg = str(result.get('msg') or '')
    data = result.get('data') or []
    row = data[0] if data and isinstance(data[0], dict) else {}
    row_code = str(row.get('sCode') or row.get('code') or '0')
    row_msg = str(row.get('sMsg') or row.get('msg') or '')
    if top_code not in ['', '0'] or row_code not in ['', '0']:
        return False
    if any(word in f"{top_msg} {row_msg}".lower() for word in ['fail', 'reject', 'error', 'invalid']):
        return False
    return bool(
        row.get('ordId')
        or row.get('algoId')
        or result.get('ordId')
        or result.get('algoId')
        or result.get('id')
    )

def _normalize_trade_order_response(result, symbol, side, size, price=None, execution='raw_trade_order'):
    data = result.get('data') if isinstance(result, dict) else None
    row = data[0] if data and isinstance(data, list) and data and isinstance(data[0], dict) else {}
    ord_id = row.get('ordId') or result.get('ordId') or result.get('id') or f"SIM-{uuid.uuid4().hex[:18]}"
    avg_price = as_float(row.get('avgPx') or row.get('fillPx') or row.get('px') or price or 0.0, price or 0.0)
    filled = as_float(row.get('fillSz') or row.get('accFillSz') or size)
    return {
        'id': ord_id,
        'clientOrderId': row.get('clOrdId') or result.get('clOrdId'),
        'symbol': symbol,
        'side': side,
        'type': row.get('ordType') or result.get('ordType') or execution,
        'price': as_float(price or row.get('px')),
        'amount': as_float(size),
        'filled': filled,
        'average': avg_price,
        'status': 'closed' if filled >= size * 0.999 else 'open',
        'info': result,
    }

def _simulate_trade_order(symbol, side, size, price=None, execution='simulated_trade_order'):
    avg_price = as_float(price)
    order_id = f"SIM-{uuid.uuid4().hex[:18]}"
    return {
        'id': order_id,
        'clientOrderId': order_id,
        'symbol': symbol,
        'side': side,
        'type': execution,
        'price': avg_price,
        'amount': as_float(size),
        'filled': as_float(size),
        'average': avg_price,
        'status': 'closed',
        'info': {
            'code': '0',
            'msg': 'simulated fill',
            'data': [{
                'ordId': order_id,
                'clOrdId': order_id,
                'sCode': '0',
                'sMsg': 'simulated fill',
                'avgPx': str(avg_price),
                'fillSz': str(size),
            }],
        },
    }

def _place_raw_trade_order(symbol, ord_type, side, size, price=None, params=None):
    inst_id = resolve_okx_inst_id(symbol)
    payload = {
        'instId': inst_id,
        'tdMode': 'cross',
        'side': side,
        'ordType': ord_type,
        'sz': str(size),
    }
    if price is not None and ord_type.lower() != 'market':
        payload['px'] = str(price)
    if params:
        payload.update(params)
    raw_method = getattr(okx, 'private_post_trade_order', None) or getattr(okx, 'privatePostTradeOrder', None)
    if raw_method is None:
        raise AttributeError('OKX trade order endpoint unavailable on exchange client')
    return raw_method(payload)

def _place_raw_trade_algo(symbol, ord_type, side, size, params=None):
    inst_id = resolve_okx_inst_id(symbol)
    payload = {
        'instId': inst_id,
        'tdMode': 'cross',
        'side': side,
        'ordType': ord_type,
        'sz': str(size),
    }
    if params:
        payload.update(params)
    raw_method = getattr(okx, 'private_post_trade_order_algo', None) or getattr(okx, 'privatePostTradeOrderAlgo', None)
    if raw_method is None:
        raise AttributeError('OKX algo order endpoint unavailable on exchange client')
    return raw_method(payload)

def refresh_order(order, symbol):
    if not isinstance(order, dict):
        return order
    order_id = order.get('id')
    if not order_id:
        return order
    info = order.get('info') or {}
    inst_id = info.get('instId') or resolve_okx_inst_id(symbol)
    try:
        raw_method = getattr(okx, 'private_get_trade_order', None) or getattr(okx, 'privateGetTradeOrder', None)
        if raw_method:
            response = raw_method({'ordId': order_id, 'instId': inst_id})
            rows = response.get('data') or []
            row = rows[0] if rows and isinstance(rows[0], dict) else {}
            merged = dict(order)
            merged['info'] = response
            merged['filled'] = as_float(row.get('fillSz') or merged.get('filled'))
            merged['average'] = as_float(row.get('avgPx') or merged.get('average'))
            merged['status'] = 'closed' if str(row.get('state') or '').lower() in ['filled', 'filled_partially', 'closed'] or merged['filled'] >= as_float(merged.get('amount')) * 0.999 else merged.get('status')
            return merged
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

def _fallback_touch_price(symbol, side):
    try:
        snapshot = load_local_market_snapshot() or {}
        inst_id = resolve_okx_inst_id(symbol)
        row = snapshot.get(inst_id) or {}
        close = as_float(row.get('close'))
        if close > 0:
            spread = max(close * 0.0005, as_float(row.get('atr')) * 0.01, close * 0.0002)
            return close + spread if side == 'buy' else max(close - spread, close * 0.0001)
    except Exception:
        pass
    return 0.0

def execute_bounded_limit_entry(symbol, side, size, strategy_name, client_order_id, atr_pct=0.0):
    policy = ENTRY_EXECUTION_POLICIES[strategy_name]

    for attempt in range(policy['attempts']):
        best_bid = 0.0
        best_ask = 0.0
        try:
            book = okx.fetch_order_book(symbol, limit=10)
            best_bid = as_float(book['bids'][0][0]) if book.get('bids') else 0.0
            best_ask = as_float(book['asks'][0][0]) if book.get('asks') else 0.0
        except Exception:
            touch_fallback = _fallback_touch_price(symbol, side)
            if touch_fallback > 0:
                if side == 'buy':
                    best_ask = touch_fallback
                    best_bid = max(touch_fallback * 0.999, 1e-12)
                else:
                    best_bid = touch_fallback
                    best_ask = touch_fallback * 1.001
        touch_price = best_ask if side == 'buy' else best_bid
        if touch_price <= 0:
            touch_price = _fallback_touch_price(symbol, side)
        if touch_price <= 0:
            raise ValueError(f"No executable order book price for {symbol}")

        cap = clamp(
            policy['base_slippage'] + max(0.0, atr_pct) * 0.04,
            policy['base_slippage'],
            policy['slippage_cap'],
        )
        limit_price = touch_price * (1.0 + cap if side == 'buy' else 1.0 - cap)
        attempt_id = f"{client_order_id[:22]}{attempt}{uuid.uuid4().hex[:4]}"
        order = None
        raw_error = None
        try:
            response = _place_raw_trade_order(symbol, 'limit', side, size, limit_price, {
                'clOrdId': attempt_id[:32],
                'timeInForce': 'FOK',
            })
            if _order_result_success(response):
                order = _normalize_trade_order_response(response, symbol, side, size, limit_price, 'bounded_fok_limit')
        except Exception as exc:
            raw_error = exc

        if order is None:
            if config.DEMO_MODE or config.MOCK_MODE:
                order = _simulate_trade_order(symbol, side, size, limit_price, 'bounded_fok_limit')
            else:
                if raw_error:
                    raise raw_error
                raise RuntimeError(f"Order placement failed for {symbol}")

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
    params = {
        'clOrdId': protection_id,
        'reduceOnly': True,
        'tpTriggerPx': str(plan['tp1']),
        'tpOrdPx': str(plan['tp1']),
        'tpTriggerPxType': 'last',
        'slTriggerPx': str(plan['sl']),
        'slOrdPx': '-1',
        'slTriggerPxType': 'mark',
        'cxlOnClosePos': True,
    }
    try:
        response = _place_raw_trade_algo(symbol, 'oco', close_side, filled_size, params)
        if _order_result_success(response):
            return {
                'id': response.get('data', [{}])[0].get('algoId') if isinstance(response.get('data'), list) and response.get('data') else response.get('algoId') or f"SIM-ALGO-{uuid.uuid4().hex[:16]}",
                'clientOrderId': protection_id,
                'info': response,
            }
        raise RuntimeError(str(response))
    except Exception as exc:
        if config.DEMO_MODE or config.MOCK_MODE:
            return {
                'id': f"SIM-ALGO-{uuid.uuid4().hex[:16]}",
                'clientOrderId': protection_id,
                'info': {
                    'code': '0',
                    'msg': f'simulated protection: {exc}',
                    'data': [{
                        'algoId': f"SIM-ALGO-{uuid.uuid4().hex[:16]}",
                        'sCode': '0',
                        'sMsg': 'simulated protection',
                    }],
                },
            }
        raise

def emergency_close_unprotected(symbol, direction, filled_size):
    """Close a position in Net Mode. Returns (success, error_code, error_msg)."""
    close_side = 'sell' if direction == 'long' else 'buy'
    try:
        result = _place_raw_trade_order(symbol, 'market', close_side, filled_size, None, {
            'posSide': 'net',
            'reduceOnly': True,
        })
        if not _order_result_success(result):
            raise RuntimeError(str(result))
        return True, '0', ''
    except Exception as e:
        err_str = str(e)
        # 51169 = no positions in this direction (already closed)
        if '51169' in err_str:
            return False, '51169', 'Position already closed or does not exist'
        if config.DEMO_MODE or config.MOCK_MODE:
            return True, '0', ''
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
                'tpTriggerPx': linked.get('tpTriggerPx') or algo.get('tpTriggerPx'),
                'tpOrdPx': linked.get('tpOrdPx') or algo.get('tpOrdPx'),
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
    # 徹底解決 51098 錯誤：如果這個 OCO 訂單是連結限價止盈 (tp_limit_linked) 或者是雙向 OCO，
    # 根據 OKX 官方限制，修改時絕對不能攜帶 TP 參數 (newTpTriggerPx)，否則會被拒絕。
    # 因此我們強制在此處過濾，只更新 SL，只有在非 linked 的狀況下才允許帶入 tp_update。
    if tp_update and not algo.get('tp_limit_linked') and not ('tpTriggerPx' in algo or 'tpOrdPx' in algo):
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
