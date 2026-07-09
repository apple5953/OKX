import ccxt
import time
import datetime
import math
import json
import os
import pandas as pd
from . import config
from . import state
from .utils import as_float, clamp, json_safe, lifecycle_trade_for_history, assess_accounting_record, history_event_key, history_pos_id

okx = ccxt.okx({
    'apiKey': config.OKX_API_KEY,
    'secret': config.OKX_SECRET,
    'password': config.OKX_PASSWORD,
    'enableRateLimit': True,
})
okx.set_sandbox_mode(True)

def sync_exchange_history(force=False):
    now = time.time()
    if not force and state.exchange_history_cache and now - state.exchange_history_synced_at < config.EXCHANGE_HISTORY_TTL_SECONDS:
        return state.exchange_history_cache

    if not state.exchange_history_lock.acquire(blocking=False):
        return state.exchange_history_cache
    try:
        raw_history = okx.fetch_positions_history(None, None, config.EXCHANGE_HISTORY_LIMIT)
        normalized = []
        deduped = {}

        def row_dedupe_key(row):
            pos_id = str(row.get('posId') or '')
            closed_at = str(row.get('closed_at') or row.get('lastUpdateTimestamp') or row.get('timestamp') or '')
            inst_id = str(row.get('instId') or row.get('symbol') or '')
            direction = str(row.get('direction') or '').lower()
            key = str(row.get('close_event_key') or '')
            if key:
                return key
            return f'{pos_id}:{closed_at}:{inst_id}:{direction}'

        def row_priority(row):
            strategy_name = str(row.get('strategy') or '')
            accounting_status = str(row.get('accounting_status') or '')
            return (
                1 if strategy_name == 'Manual' else 0,
                1 if accounting_status == 'manual' else 0,
                1 if row.get('eligible_for_learning') is not True else 0,
                1 if not row.get('lifecycle_id') else 0,
                1 if not row.get('strategy_version') else 0,
                -as_float(row.get('realizedPnl') or row.get('alphaPnl') or 0),
            )

        for item in raw_history:
            record = dict(item)
            info = dict(record.get('info') or {})
            pos_id = history_pos_id(record)
            inst_id = str(info.get('instId') or record.get('instId') or '')
            direction = str(info.get('direction') or record.get('side') or '').lower()

            lifecycle = lifecycle_trade_for_history(record)
            recovered = None
            fallback_manual = None

            if not lifecycle and pos_id:
                for row in reversed(state.trade_journal):
                    if str(row.get('posId') or '') != pos_id:
                        continue
                    trade_inst = str(row.get('instId') or '')
                    trade_direction = str(row.get('direction') or '').lower()
                    history_inst = inst_id
                    history_direction = direction
                    if history_inst and trade_inst and history_inst != trade_inst:
                        continue
                    if history_direction and trade_direction and history_direction != trade_direction:
                        continue
                    if str(row.get('strategy') or '') == 'Manual':
                        if fallback_manual is None:
                            fallback_manual = row
                        continue
                    recovered = row
                    break
                if recovered is None:
                    recovered = fallback_manual

            effective_lifecycle = lifecycle or recovered
            if effective_lifecycle and str(effective_lifecycle.get('strategy') or '') == 'Manual' and inst_id:
                better_lifecycle = next(
                    (
                        row for row in reversed(state.trade_journal)
                        if str(row.get('instId') or '') == inst_id
                        and str(row.get('direction') or '').lower() == direction
                        and str(row.get('strategy') or '') not in ['', 'Manual', 'Mixed']
                    ),
                    None,
                )
                if better_lifecycle is not None:
                    effective_lifecycle = better_lifecycle

            strategy = effective_lifecycle.get('strategy') if effective_lifecycle else 'Manual'
            version = effective_lifecycle.get('strategy_version') if effective_lifecycle else None
            closed_at = (
                record.get('lastUpdateTimestamp')
                or record.get('timestamp')
                or info.get('uTime')
                or info.get('cTime')
            )
            raw_pnl = (
                record.get('realizedPnl') or info.get('realizedPnl')
                or record.get('pnl') or info.get('pnl')
            )
            realized = as_float(raw_pnl)
            fee = as_float(info.get('fee'))
            funding_fee = as_float(info.get('fundingFee') or info.get('funding'))

            record.update({
                'strategy': strategy,
                'strategy_mix': [strategy] if strategy not in ['Manual', 'Mixed'] else [],
                'strategy_version': version,
                'strategy_versions': [version] if version else [],
                'realizedPnl': realized,
                'alphaPnl': realized - funding_fee,
                'fee': fee,
                'fundingFee': funding_fee,
                'pnl_source': 'okx_realized',
                'posId': pos_id,
                'lifecycle_id': effective_lifecycle.get('lifecycle_id') if effective_lifecycle else None,
                'close_event_key': history_event_key(record),
                'direction': info.get('direction') or record.get('side'),
                'instId': inst_id or None,
                'symbol': info.get('instId') or record.get('symbol') or inst_id or None,
                'closePrice': as_float(info.get('closeAvgPx'), record.get('lastPrice')),
                'openPrice': as_float(info.get('openAvgPx'), record.get('entryPrice')),
                'closed_at': closed_at,
            })
            record.update(assess_accounting_record(record, effective_lifecycle))
            normalized.append(record)

        for row in normalized:
            key = row_dedupe_key(row)
            existing = deduped.get(key)
            if existing is None or row_priority(row) < row_priority(existing):
                deduped[key] = row
        normalized = list(deduped.values())

        if not normalized and state.trade_journal:
            fallback_history = []
            for row in reversed(state.trade_journal):
                if row.get('status') != 'closed' and not row.get('closed_at'):
                    continue
                fallback_row = dict(row)
                fallback_row.setdefault('pnl_source', 'journal_fallback')
                fallback_row.setdefault('realizedPnl', as_float(row.get('realized_pnl', row.get('pnl'))))
                fallback_row.setdefault('alphaPnl', as_float(row.get('realized_pnl', row.get('pnl'))) - as_float(row.get('funding_fee')))
                fallback_row.setdefault('fee', as_float(row.get('fee')))
                fallback_row.setdefault('fundingFee', as_float(row.get('funding_fee')))
                fallback_row.setdefault('strategy_version', row.get('strategy_version'))
                fallback_row.setdefault('strategy_mix', [row.get('strategy')] if row.get('strategy') not in ['Manual', 'Mixed'] else [])
                fallback_row.setdefault('strategy_versions', [row.get('strategy_version')] if row.get('strategy_version') else [])
                fallback_row.setdefault('accounting_status', row.get('accounting_status'))
                fallback_row.setdefault('eligible_for_learning', row.get('eligible_for_learning'))
                fallback_row.setdefault('accounting_reasons', row.get('accounting_reasons') or [])
                fallback_history.append(fallback_row)
            normalized = fallback_history[:config.EXCHANGE_HISTORY_LIMIT]

        normalized.sort(key=lambda row: int(row.get('lastUpdateTimestamp') or row.get('timestamp') or 0), reverse=True)
        state.exchange_history_cache = normalized
        state.exchange_history_synced_at = now
        state.exchange_history_error = None
    except Exception as exc:
        state.exchange_history_error = str(exc)
        fallback_history = []
        for row in reversed(state.trade_journal or []):
            if row.get('status') != 'closed' and not row.get('closed_at'):
                continue
            fallback_row = dict(row)
            fallback_row.setdefault('pnl_source', 'journal_fallback')
            fallback_row.setdefault('realizedPnl', as_float(row.get('realized_pnl', row.get('pnl'))))
            fallback_row.setdefault('alphaPnl', as_float(row.get('realized_pnl', row.get('pnl'))) - as_float(row.get('funding_fee')))
            fallback_row.setdefault('fee', as_float(row.get('fee')))
            fallback_row.setdefault('fundingFee', as_float(row.get('funding_fee')))
            fallback_row.setdefault('strategy_version', row.get('strategy_version'))
            fallback_row.setdefault('strategy_mix', [row.get('strategy')] if row.get('strategy') not in ['Manual', 'Mixed'] else [])
            fallback_row.setdefault('strategy_versions', [row.get('strategy_version')] if row.get('strategy_version') else [])
            fallback_row.setdefault('accounting_status', row.get('accounting_status'))
            fallback_row.setdefault('eligible_for_learning', row.get('eligible_for_learning'))
            fallback_row.setdefault('accounting_reasons', row.get('accounting_reasons') or [])
            fallback_history.append(fallback_row)
        if fallback_history:
            fallback_history.sort(key=lambda row: int(row.get('lastUpdateTimestamp') or row.get('timestamp') or 0), reverse=True)
            state.exchange_history_cache = fallback_history[:config.EXCHANGE_HISTORY_LIMIT]
            state.exchange_history_synced_at = now
    finally:
        state.exchange_history_lock.release()
    return state.exchange_history_cache

def realized_strategy_rows(strategy_name, limit):
    history = sync_exchange_history()
    rows = []
    seen_keys = set()

    def row_key(row):
        return (
            str(row.get('close_event_key') or ''),
            str(row.get('posId') or ''),
            str(row.get('closed_at') or row.get('lastUpdateTimestamp') or row.get('timestamp') or ''),
            str(row.get('strategy') or ''),
            str(row.get('symbol') or row.get('instId') or ''),
        )

    for row in reversed(history):
        if row.get('strategy') != strategy_name:
            continue
        if row.get('eligible_for_learning') is not True:
            continue
        from .strategies import version_matches_strategy_scope
        if version_matches_strategy_scope(row.get('strategy_version')):
            key = row_key(row)
            if key not in seen_keys:
                rows.append(row)
                seen_keys.add(key)

    if len(rows) < min(8, limit):
        from .strategies import version_matches_strategy_scope
        journal_rows = [
            row for row in reversed(state.trade_journal)
            if row.get('strategy') == strategy_name
            and row.get('status') == 'closed'
            and row.get('eligible_for_learning') is not False
            and version_matches_strategy_scope(row.get('strategy_version'))
        ]
        for row in journal_rows:
            key = row_key(row)
            if key in seen_keys:
                continue
            normalized = dict(row)
            normalized['alphaPnl'] = as_float(normalized.get('realized_pnl', normalized.get('pnl'))) - as_float(normalized.get('funding_fee'))
            rows.append(normalized)
            seen_keys.add(key)

    return rows[-limit:]

def is_crypto_usdt_swap(market):
    if not market.get('swap') or market.get('quote') != 'USDT' or market.get('settle') != 'USDT':
        return False
    info = market.get('info') or {}
    inst_category = str(info.get('instCategory') or '')
    if inst_category and inst_category != '1':
        return False
    base = str(market.get('base') or info.get('baseCcy') or '').upper()
    return bool(base) and base not in config.NON_CRYPTO_BASES

def get_top_symbols_and_categories():
    categories = {}
    selected_symbols = []
    try:
        okx.load_markets()
        tickers = okx.fetch_tickers(params={'instType': 'SWAP'})
        funding = okx.fetch_funding_rates(params={'instType': 'SWAP'})
        
        swap_symbols = set([
            m['symbol'] for m in okx.markets.values()
            if is_crypto_usdt_swap(m)
        ])
        usdt_swaps = [v for k, v in tickers.items() if k in swap_symbols]
        sorted_swaps = sorted(usdt_swaps, key=lambda x: float(x.get('quoteVolume', 0) or 0), reverse=True)
        top_150 = sorted_swaps[:150]
        
        btc_pct = tickers.get('BTC/USDT:USDT', {}).get('percentage', 0)
        if btc_pct is None: btc_pct = 0
        
        for t in top_150:
            sym = t['symbol']
            sym_clean = sym.replace(':USDT', '').replace('/', '')
            if sym in selected_symbols: continue
            
            if sym_clean in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                categories[sym] = "巨鯨主流 (Majors)"
                selected_symbols.append(sym)
                continue
                
            fr = funding.get(sym, {}).get('fundingRate', 0)
            if fr is None: fr = 0
            if fr and (fr < -0.0005 or fr > 0.0005):
                categories[sym] = "資金費率異常 (Squeeze Watch)"
                selected_symbols.append(sym)
                continue
                
            pct = t.get('percentage', 0)
            if pct is None: pct = 0
            if pct > btc_pct + 5:
                categories[sym] = "Alpha 獨立行情 (Rel. Strength)"
                selected_symbols.append(sym)
                continue
                
            if pct < -5:
                categories[sym] = "極端超跌 (Deep Oversold)"
                selected_symbols.append(sym)
                continue
                
            high = t.get('high', 0)
            low = t.get('low', 0)
            if high is None: high = 0
            if low is None: low = 0
            if low > 0 and ((high - low) / low) > 0.10:
                categories[sym] = "爆量高波動 (High Volatility)"
                selected_symbols.append(sym)
                continue
                
        for t in top_150:
            if len(selected_symbols) >= 120: break
            sym = t['symbol']
            if sym not in selected_symbols:
                categories[sym] = "普通高量 (High Volume)"
                selected_symbols.append(sym)
                
        return selected_symbols[:120], categories
    except Exception as e:
        print(f"Error fetching top symbols: {e}")
        categories = {sym: 'Majors' for sym in config.FALLBACK_SCAN_SYMBOLS}
        return config.FALLBACK_SCAN_SYMBOLS, categories

def fetch_market_quality(symbol):
    book = okx.fetch_order_book(symbol, limit=10)
    best_bid = as_float(book['bids'][0][0]) if book.get('bids') else 0.0
    best_ask = as_float(book['asks'][0][0]) if book.get('asks') else 0.0
    mid = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.0
    spread_pct = (best_ask - best_bid) / mid if mid > 0 else config.MAX_ACCEPTABLE_SPREAD_PCT
    exit_slippage_pct = clamp(spread_pct * 3.0, config.SLIPPAGE_BUFFER_RATE, 0.0060)
    return {
        'best_bid': best_bid,
        'best_ask': best_ask,
        'spread_pct': max(0.0, spread_pct),
        'exit_slippage_pct': exit_slippage_pct,
        'quality': 'thin' if spread_pct > config.MAX_ACCEPTABLE_SPREAD_PCT else 'normal',
    }

def resolve_okx_inst_id(symbol):
    raw = str(symbol or '').strip()
    if not raw:
        return raw

    markets = getattr(okx, 'markets', None) or {}
    market = markets.get(raw)
    if market and market.get('id'):
        return market['id']

    if raw.endswith('-USDT-SWAP') or raw.endswith('-USD-SWAP'):
        return raw

    if ':' in raw and '/' in raw:
        base, quote = raw.split('/', 1)
        quote = quote.split(':', 1)[0]
        if quote.upper() == 'USDT':
            return f"{base}-USDT-SWAP"
        return f"{base}-{quote.upper()}-SWAP"

    if '/' in raw:
        base, quote = raw.split('/', 1)
        quote = quote.split(':', 1)[0]
        if quote.upper() == 'USDT':
            return f"{base}-USDT-SWAP"
        return f"{base}-{quote.upper()}-SWAP"

    if raw.upper().endswith('USDT') and '-' not in raw:
        return f"{raw[:-4]}-USDT-SWAP"

    return raw

def okx_timeframe_to_bar(timeframe):
    tf = str(timeframe or '').strip().lower()
    mapping = {
        '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
        '1h': '1H', '2h': '2H', '4h': '4H', '6h': '6H', '12h': '12H',
        '1d': '1D', '2d': '2D', '3d': '3D', '1w': '1W', '1mo': '1M',
    }
    return mapping.get(tf, timeframe)

def load_local_market_snapshot():
    now = time.monotonic()
    with state.local_market_snapshot_lock:
        if state.local_market_snapshot_cache['data'] and now - state.local_market_snapshot_cache['fetched_at'] < 30:
            return dict(state.local_market_snapshot_cache['data'])
    try:
        real_path = os.path.join(os.path.dirname(__file__), '..', config.LOCAL_MARKET_SNAPSHOT_PATH)
        with open(real_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        instruments = payload.get('instruments') or []
        snapshot = {}
        for item in instruments:
            inst_id = str(item.get('instId') or '').strip()
            if inst_id:
                snapshot[inst_id] = dict(item)
        with state.local_market_snapshot_lock:
            state.local_market_snapshot_cache['fetched_at'] = now
            state.local_market_snapshot_cache['data'] = snapshot
        return dict(snapshot)
    except Exception:
        return {}

def load_local_account_snapshot():
    now = time.monotonic()
    with state.local_account_snapshot_lock:
        cached = state.local_account_snapshot_cache['data']
        if cached and now - state.local_account_snapshot_cache['fetched_at'] < 30:
            return dict(cached)

    best_snapshot = None
    best_source = ''
    best_mtime = 0.0
    for file_name in config.LOCAL_ACCOUNT_SNAPSHOT_PATHS:
        path = os.path.join(os.path.dirname(__file__), '..', file_name)
        if not os.path.exists(path):
            continue
        try:
            mtime = os.path.getmtime(path)
            if mtime < best_mtime:
                continue
            payload = None
            for encoding in ('utf-8-sig', 'utf-16', 'utf-16-le', 'utf-8'):
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        payload = json.load(f)
                    break
                except UnicodeError:
                    continue
            if payload is None:
                continue
            account = payload.get('account') if isinstance(payload, dict) else None
            if not isinstance(account, dict):
                continue
            if as_float(account.get('totalEq')) <= 0 and as_float(account.get('usdtEq')) <= 0 and as_float(account.get('usdtAvail')) <= 0:
                continue
            best_snapshot = {
                'totalEq': as_float(account.get('totalEq')),
                'usdtEq': as_float(account.get('usdtEq')),
                'usdtAvail': as_float(account.get('usdtAvail')),
                'source': f'cached_account_snapshot:{os.path.basename(path)}',
                'synced_at': datetime.datetime.fromtimestamp(mtime).isoformat(timespec='seconds'),
            }
            best_source = path
            best_mtime = mtime
        except Exception:
            continue

    if best_snapshot:
        with state.local_account_snapshot_lock:
            state.local_account_snapshot_cache['fetched_at'] = time.monotonic()
            state.local_account_snapshot_cache['data'] = dict(best_snapshot)
            state.local_account_snapshot_cache['source'] = best_source
        return best_snapshot
    return None

def build_synthetic_candles_from_snapshot(snapshot_item, timeframe, limit):
    close = as_float(snapshot_item.get('close'))
    if close <= 0:
        return []

    atr = max(as_float(snapshot_item.get('atr')), close * 0.001)
    ema20 = as_float(snapshot_item.get('ema20'))
    ema50 = as_float(snapshot_item.get('ema50'))
    ema200 = as_float(snapshot_item.get('ema200'))
    score_long = as_float(snapshot_item.get('scoreLong'))
    score_short = as_float(snapshot_item.get('scoreShort'))
    signal = str(snapshot_item.get('signal') or 'none').lower()

    bias = 0
    if signal == 'long' or score_long > score_short + 1:
        bias = 1
    elif signal == 'short' or score_short > score_long + 1:
        bias = -1
    elif ema20 and ema50 and ema200:
        if ema20 >= ema50 >= ema200:
            bias = 1
        elif ema20 <= ema50 <= ema200:
            bias = -1

    bars = max(120, min(int(limit) if limit else 120, 300))
    tf_bar_minutes = 15
    tf_lower = str(timeframe or '').lower()
    if tf_lower.endswith('m'):
        tf_bar_minutes = int(tf_lower[:-1] or 15)
    elif tf_lower.endswith('h'):
        tf_bar_minutes = int(tf_lower[:-1] or 1) * 60
    elif tf_lower.endswith('d'):
        tf_bar_minutes = int(tf_lower[:-1] or 1) * 60 * 24
    timeframe_ms = max(60_000, tf_bar_minutes * 60_000)
    now_ms = int(time.time() * 1000)
    start_ts = now_ms - timeframe_ms * bars

    amplitude = max(atr * 0.65, close * 0.0015)
    slope = bias * max(atr * 0.015, close * 0.00015)
    trend_anchor = ema50 if ema50 > 0 else close
    candles = []
    for i in range(bars):
        cycle = math.sin(i / 4.5) * amplitude * 0.28
        drift = (i - bars + 1) * slope
        center = trend_anchor + drift + cycle
        open_px = center - math.cos(i / 3.2) * amplitude * 0.08
        close_px = center + math.sin(i / 2.6) * amplitude * 0.08
        high_px = max(open_px, close_px) + amplitude * (0.22 + 0.04 * math.cos(i / 5.5))
        low_px = min(open_px, close_px) - amplitude * (0.22 + 0.04 * math.sin(i / 6.5))
        volume = max(1.0, abs(close_px - open_px) * 1200 + close * (0.04 + 0.01 * math.sin(i / 8.0)))
        candles.append([
            start_ts + i * timeframe_ms,
            round(open_px, 8),
            round(high_px, 8),
            round(low_px, 8),
            round(close_px, 8),
            round(volume, 8),
        ])
    return candles

def fetch_data(symbol, timeframe, limit=200):
    cache_key = (symbol, timeframe)
    ttl = config.MARKET_DATA_TTL_SECONDS.get(timeframe, 30)
    now = time.monotonic()
    cached = state.market_data_cache.get(cache_key)
    if cached and now - cached['fetched_at'] < ttl and cached['requested_limit'] >= limit:
        return cached['data'].copy(deep=False)

    from core.divergence import calculate_rsi
    from core.divergence import calculate_rsi
    with state.market_data_lock:
        now = time.monotonic()
        cached = state.market_data_cache.get(cache_key)
        if cached and now - cached['fetched_at'] < ttl and cached['requested_limit'] >= limit:
            return cached['data'].copy(deep=False)

    last_error = None
    ohlcv = None
    for attempt in range(4):
        with state.market_data_lock:
            wait_for = config.MARKET_DATA_MIN_INTERVAL_SECONDS - (time.monotonic() - state.market_data_last_request_at)
            if wait_for > 0:
                time.sleep(wait_for)
            state.market_data_last_request_at = time.monotonic()

        try:
            inst_id = resolve_okx_inst_id(symbol)
            bar = okx_timeframe_to_bar(timeframe)
            raw_fetch = getattr(okx, 'public_get_market_candles', None) or getattr(okx, 'publicGetMarketCandles', None)
            if raw_fetch is None:
                raise AttributeError('OKX candles endpoint not available on this exchange client')
            response = raw_fetch({
                'instId': inst_id,
                'bar': bar,
                'limit': min(int(limit), 300),
            })
            rows = response.get('data') if isinstance(response, dict) else response
            if not rows:
                raise ValueError(f'No candles returned for {inst_id} {bar}')
            ohlcv = []
            for row in rows:
                if not row or len(row) < 6:
                    continue
                ohlcv.append([
                    row[0], row[1], row[2], row[3], row[4], row[5],
                ])
            if not ohlcv:
                raise ValueError(f'No usable candle rows returned for {inst_id} {bar}')
            break
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            rate_limited = isinstance(exc, ccxt.RateLimitExceeded) or '50011' in message or 'too many requests' in message
            local_snapshot = load_local_market_snapshot()
            inst_id = resolve_okx_inst_id(symbol)
            snapshot_item = local_snapshot.get(inst_id)
            if snapshot_item:
                synthetic = build_synthetic_candles_from_snapshot(snapshot_item, timeframe, limit)
                if synthetic:
                    print(f"[fetch_data fallback] {symbol} {timeframe}: using local market snapshot after error: {exc}")
                    ohlcv = synthetic
                    break
            with state.market_data_lock:
                cached = state.market_data_cache.get(cache_key)
                cached_df = cached.get('data') if cached else None
                if cached_df is not None and len(cached_df) >= 20:
                    print(f"[fetch_data fallback] {symbol} {timeframe}: using cached candles after error: {exc}")
                    return cached_df.copy(deep=False)
            if attempt < 3:
                time.sleep(2.0 * (attempt + 1))
    else:
        with state.market_data_lock:
            cached = state.market_data_cache.get(cache_key)
            cached_df = cached.get('data') if cached else None
            if cached_df is not None and len(cached_df) >= 20:
                print(f"[fetch_data fallback] {symbol} {timeframe}: using cached candles after repeated errors: {last_error}")
                return cached_df.copy(deep=False)
        print(f"[fetch_data fallback] {symbol} {timeframe}: returning empty frame after repeated errors: {last_error}")
        return pd.DataFrame()

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last').reset_index(drop=True)
    for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['time'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['rsi'] = calculate_rsi(df)
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['vol_ma'] = df['volume'].rolling(window=5).mean()

    df['std'] = df['close'].rolling(window=20).std()
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_upper'] = df['bb_mid'] + (2.0 * df['std'])
    df['bb_lower'] = df['bb_mid'] - (2.0 * df['std'])

    from .strategies import calculate_macd, calculate_keltner, calculate_adx
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df)
    df['kc_upper'], df['kc_lower'] = calculate_keltner(df)
    df['bb_width'] = df['bb_upper'] - df['bb_lower']
    df['kc_width'] = df['kc_upper'] - df['kc_lower']
    df['is_squeezed'] = df['bb_width'] < df['kc_width']

    try:
        df['adx'] = calculate_adx(df)
    except Exception:
        df['adx'] = 20.0

    with state.market_data_lock:
        state.market_data_cache[cache_key] = {
            'fetched_at': time.monotonic(),
            'requested_limit': limit,
            'data': df,
        }
    return df.copy(deep=False)

def position_is_open(pos):
    if not pos:
        return False
    size = as_float(pos.get('pos') or pos.get('sz'))
    return abs(size) > 0

def normalize_position_side(side):
    val = str(side or '').strip().lower()
    if val in ['long', 'buy', 'net_long']:
        return 'long'
    if val in ['short', 'sell', 'net_short']:
        return 'short'
    return 'long'

def fetch_open_positions_snapshot(force=False):
    now = time.monotonic()
    with state.positions_snapshot_lock:
        if (
            not force
            and state.positions_snapshot_cache['raw']
            and now - state.positions_snapshot_cache['fetched_at'] < 5
        ):
            return [dict(p) for p in state.positions_snapshot_cache['raw']]

    try:
        response = okx.private_get_account_positions({'instType': 'SWAP'})
        rows = response.get('data') or [] if isinstance(response, dict) else []
        positions = []
        for row in rows:
            if not position_is_open(row):
                continue
            inst_id = str(row.get('instId') or '')
            pos_qty = as_float(row.get('pos') or row.get('sz'))
            raw_side = row.get('posSide') or row.get('side')
            if raw_side == 'net':
                side = 'long' if pos_qty >= 0 else 'short'
            else:
                side = normalize_position_side(
                    raw_side or ('long' if pos_qty >= 0 else 'short')
                )
            normalized = {
                'id': row.get('posId') or row.get('id') or inst_id,
                'posId': row.get('posId') or row.get('id') or inst_id,
                'instId': inst_id,
                'symbol': inst_id,
                'raw_symbol': inst_id,
                'side': side,
                'posSide': row.get('posSide') or row.get('side') or side,
                'direction': side,
                'status': 'active',
                'source': 'okx_live',
                'entryPrice': as_float(row.get('avgPx') or row.get('entryPrice')),
                'markPrice': as_float(row.get('markPx') or row.get('markPrice')),
                'unrealizedPnl': as_float(row.get('upl') or row.get('unrealizedPnl')),
                'percentage': as_float(row.get('uplRatio') or row.get('percentage')),
                'leverage': row.get('lever') or row.get('leverage'),
                'initialMargin': as_float(row.get('imr') or row.get('initialMargin')),
                'notional': as_float(row.get('notionalUsd') or row.get('notional')),
                'liquidationPrice': as_float(row.get('liqPx') or row.get('liquidationPrice')),
                'marginRatio': as_float(row.get('mgnRatio') or row.get('marginRatio')),
                'contracts': as_float(row.get('pos') or row.get('sz') or row.get('contracts')),
                'availPos': as_float(row.get('availPos')),
                'marginMode': row.get('mgnMode'),
                'info': dict(row),
            }
            if normalized['entryPrice'] == 0:
                normalized['entryPrice'] = as_float(row.get('avgPx'))
            positions.append(normalized)
        with state.positions_snapshot_lock:
            state.positions_snapshot_cache['fetched_at'] = time.monotonic()
            state.positions_snapshot_cache['raw'] = [dict(p) for p in positions]
            state.positions_snapshot_cache['normalized'] = []
        return positions
    except Exception as exc:
        with state.positions_snapshot_lock:
            cached = state.positions_snapshot_cache.get('raw') or []
            if cached:
                print(f"[positions fallback] {exc}")
                return [dict(p) for p in cached]
        if state.active_trades:
            print(f"[positions fallback] {exc}")
            fallback_positions = []
            for trade in state.active_trades:
                if trade.get('status') != 'active':
                    continue
                fallback_positions.append({
                    'id': trade.get('posId') or trade.get('id') or trade.get('symbol'),
                    'posId': trade.get('posId') or trade.get('id') or trade.get('symbol'),
                    'instId': trade.get('instId') or trade.get('symbol'),
                    'symbol': trade.get('instId') or trade.get('symbol'),
                    'raw_symbol': trade.get('instId') or trade.get('symbol'),
                    'side': trade.get('direction') or 'long',
                    'posSide': trade.get('direction') or 'long',
                    'direction': trade.get('direction') or 'long',
                    'status': 'active',
                    'source': 'local_active_trade_fallback',
                    'entryPrice': as_float(trade.get('entry')),
                    'markPrice': as_float(trade.get('current') or trade.get('entry')),
                    'unrealizedPnl': as_float(trade.get('pnl')),
                    'percentage': as_float(trade.get('percentage')),
                    'leverage': trade.get('leverage'),
                    'initialMargin': as_float(trade.get('initialMargin')),
                    'notional': as_float(trade.get('notional')),
                    'liquidationPrice': as_float(trade.get('liquidationPrice')),
                    'marginRatio': as_float(trade.get('marginRatio')),
                    'contracts': as_float(trade.get('contracts') or trade.get('filled_contracts')),
                    'availPos': as_float(trade.get('contracts') or trade.get('filled_contracts')),
                    'marginMode': trade.get('marginMode'),
                    'info': dict(trade),
                })
            return fallback_positions
        print(f"[positions ERROR] {exc}")
        return []

def create_okx_balance_client():
    client = ccxt.okx({
        'apiKey': config.OKX_API_KEY,
        'secret': config.OKX_SECRET,
        'password': config.OKX_PASSWORD,
        'enableRateLimit': True,
    })
    try:
        client.set_sandbox_mode(True)
    except Exception:
        pass
    client.options['defaultType'] = 'swap'
    client.options['defaultSubType'] = 'linear'
    return client

def fetch_okx_account_snapshot(force=False):
    now = time.monotonic()
    with state.account_snapshot_lock:
        cached = state.account_snapshot_cache['data']
        if (
            not force
            and cached
            and now - state.account_snapshot_cache['fetched_at'] < 5
        ):
            return dict(cached)

    response = None
    last_error = None
    balance_client = None
    fetch_attempts = []
    try:
        balance_client = create_okx_balance_client()
        fetch_attempts.extend([
            ('fresh_fetch_balance_swap', balance_client.fetch_balance, {'type': 'swap', 'ccy': 'USDT'}),
            ('fresh_fetch_balance_trading', balance_client.fetch_balance, {'type': 'trading', 'ccy': 'USDT'}),
            ('fresh_fetch_balance_usdt', balance_client.fetch_balance, {'ccy': 'USDT'}),
            ('fresh_fetch_balance_default', balance_client.fetch_balance, {}),
        ])
    except Exception as exc:
        last_error = exc

    raw_fetch = getattr(okx, 'private_get_account_balance', None) or getattr(okx, 'privateGetAccountBalance', None)
    if raw_fetch:
        fetch_attempts.extend([
            ('raw_balance_usdt', raw_fetch, {'ccy': 'USDT'}),
            ('raw_balance_default', raw_fetch, {}),
        ])
    if hasattr(okx, 'fetch_balance'):
        fetch_attempts.extend([
            ('global_fetch_swap', okx.fetch_balance, {'type': 'swap', 'ccy': 'USDT'}),
            ('global_fetch_trading', okx.fetch_balance, {'type': 'trading', 'ccy': 'USDT'}),
            ('global_fetch_default', okx.fetch_balance, {}),
        ])
    for label, fetcher, params in fetch_attempts:
        try:
            response = fetcher(params)
            break
        except Exception as exc:
            last_error = exc

    if response is None:
        return None

    snapshot = {
        'totalEq': 0.0,
        'usdtEq': 0.0,
        'usdtAvail': 0.0,
        'source': 'okx_account_balance',
        'synced_at': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    found = False
    rows = []
    if isinstance(response, dict):
        if isinstance(response.get('data'), list):
            rows = response.get('data') or []
        elif isinstance(response.get('info'), dict) and isinstance(response['info'].get('data'), list):
            rows = response['info'].get('data') or []

        usdt_bucket = response.get('USDT')
        if isinstance(usdt_bucket, dict):
            snapshot['usdtEq'] = as_float(usdt_bucket.get('total') or usdt_bucket.get('free') or usdt_bucket.get('used'))
            snapshot['usdtAvail'] = as_float(usdt_bucket.get('free') or usdt_bucket.get('available') or usdt_bucket.get('balance'))
            found = True

    for row in rows:
        if not isinstance(row, dict):
            continue
        total_eq = as_float(row.get('totalEq') or row.get('eq') or row.get('adjEq'))
        if total_eq > 0:
            snapshot['totalEq'] = max(snapshot['totalEq'], total_eq)
            found = True
        row_ccy = str(row.get('ccy') or '').upper()
        if row_ccy == 'USDT':
            snapshot['usdtEq'] = as_float(row.get('eq') or row.get('cashBal') or row.get('bal'))
            snapshot['usdtAvail'] = as_float(row.get('availEq') or row.get('availBal') or row.get('avail'))
            found = True
        details = row.get('details') or []
        if isinstance(details, list):
            for det in details:
                if not isinstance(det, dict):
                    continue
                if str(det.get('ccy') or '').upper() != 'USDT':
                    continue
                snapshot['usdtEq'] = as_float(det.get('eq') or det.get('cashBal') or det.get('bal'))
                snapshot['usdtAvail'] = as_float(det.get('availEq') or det.get('availBal') or det.get('avail'))
                found = True

    if snapshot['totalEq'] <= 0 and snapshot['usdtEq'] > 0:
        snapshot['totalEq'] = snapshot['usdtEq']

    if found:
        with state.account_snapshot_lock:
            state.account_snapshot_cache['fetched_at'] = time.monotonic()
            state.account_snapshot_cache['data'] = dict(snapshot)
        return snapshot

    with state.account_snapshot_lock:
        cached = state.account_snapshot_cache['data']
        if cached:
            return dict(cached)

    local_snapshot = load_local_account_snapshot()
    if local_snapshot:
        with state.account_snapshot_lock:
            state.account_snapshot_cache['fetched_at'] = time.monotonic()
            state.account_snapshot_cache['data'] = dict(local_snapshot)
        return local_snapshot
    return None

def capital_snapshot():
    # Helper to calculate start-equity based metrics
    acc_snap = fetch_okx_account_snapshot()
    account_equity = as_float(acc_snap.get('usdtEq')) if acc_snap else 0.0
    
    from .utils import session_start_equity
    session_start = session_start_equity()
    session_target = session_start + (config.TARGET_EQUITY_USDT - config.START_EQUITY_USDT)
    history = sync_exchange_history()
    from .strategies import version_matches_strategy_scope
    strategy_rows = [
        row for row in history
        if version_matches_strategy_scope(row.get('strategy_version'))
    ]
    if not strategy_rows:
        strategy_rows = list(history)
    verified_rows = [row for row in strategy_rows if row.get('eligible_for_learning') is True]
    quarantined_rows = [row for row in strategy_rows if row.get('accounting_status') == 'quarantined']
    strategy_realized = sum(
        as_float(row.get('realizedPnl'))
        for row in verified_rows
    )
    strategy_unrealized = sum(
        as_float(trade.get('pnl'))
        for trade in state.active_trades
        if trade.get('status') == 'active' and version_matches_strategy_scope(trade.get('strategy_version'))
    )
    equity = account_equity if account_equity > 0 else session_start
    pnl_from_start = equity - session_start
    return_pct = (pnl_from_start / session_start * 100) if session_start else 0.0
    goal_progress = (pnl_from_start / (session_target - session_start) * 100) if session_target > session_start else 0.0
    return {
        'start': round(session_start, 4),
        'target': round(session_target, 4),
        'equity': round(equity, 4),
        'account_equity': account_equity,
        'session_started_at': config.SESSION_STARTED_AT,
        'strategy_realized': round(strategy_realized, 4),
        'quarantined_count': len(quarantined_rows),
        'quarantined_reported_pnl': round(sum(as_float(row.get('realizedPnl')) for row in quarantined_rows), 4),
        'strategy_unrealized': round(strategy_unrealized, 4),
        'pnl_from_start': round(pnl_from_start, 4),
        'return_pct': round(return_pct, 3),
        'goal_progress_pct': round(goal_progress, 3),
        'remaining': round(session_target - equity, 4),
        'state': 'drawdown' if equity < session_start else ('target_reached' if equity >= session_target else 'growing'),
    }
