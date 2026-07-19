import ccxt
import time
import datetime
import math
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
import pandas as pd
from . import config
from . import state
from .utils import (
    as_float, clamp, json_safe, lifecycle_trade_for_history,
    assess_accounting_record, history_event_key, history_pos_id,
    session_started_at_ms, timestamp_ms, learning_cutoff_ms,
    infer_strategy_from_metadata,
)

okx = ccxt.okx({
    'apiKey': config.OKX_API_KEY,
    'secret': config.OKX_SECRET,
    'password': config.OKX_PASSWORD,
    'enableRateLimit': True,
})
try:
    okx.set_sandbox_mode(True)
except Exception:
    pass

def _embedded_market_snapshot():
    return {
        'BTC-USDT-SWAP': {
            'instId': 'BTC-USDT-SWAP',
            'symbol': 'BTC/USDT:USDT',
            'close': 59463.57450326,
            'atr': 47.30984176928541,
            'ema20': 59389.94744579811,
            'ema50': 59252.519616331534,
            'ema200': 58623.32254267677,
            'scoreLong': 2.0,
            'scoreShort': 1.0,
            'signal': 'long',
            'source': 'embedded_default_snapshot',
            'high24h': 61000.0,
            'low24h': 58500.0,
            'open24h': 59000.0,
            'changePct24h': 1.694915254237288,
        }
    }

def _resolve_okx_cli_path():
    env_path = str(os.getenv('OKX_CLI_PATH') or '').strip()
    if env_path:
        return env_path

    hardcoded = r'C:\Users\User\AppData\Roaming\npm\okx.cmd'
    if hardcoded:
        return hardcoded

    candidates = [
        shutil.which('okx.cmd'),
        str(Path(os.getenv('APPDATA') or '') / 'npm' / 'okx.cmd') if os.getenv('APPDATA') else '',
        str(Path.home() / 'AppData' / 'Roaming' / 'npm' / 'okx.cmd'),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ''

def _run_okx_cli(args):
    cli_path = _resolve_okx_cli_path()
    if not cli_path:
        raise FileNotFoundError('okx.cmd not found')
    def _ps_quote(value):
        text = str(value or '')
        return "'" + text.replace("'", "''") + "'"

    command = ' '.join([f"& {_ps_quote(cli_path)}", *(str(arg) for arg in args)])
    proc = subprocess.run(
        [
            'powershell.exe',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-Command',
            command,
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='ignore',
        timeout=25,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or '').strip()
        stdout = (proc.stdout or '').strip()
        raise RuntimeError(stderr or stdout or f'okx cli returned {proc.returncode}')
    return proc.stdout or ''

def _parse_okx_positions_cli_output(text):
    def _symbol_from_inst_id(inst_id):
        raw = str(inst_id or '').strip().upper()
        if not raw:
            return ''
        raw = raw.replace('/', '')
        if raw.endswith('-USDT-SWAP'):
            return raw.replace('-USDT-SWAP', 'USDT')
        if raw.endswith('-USD-SWAP'):
            return raw.replace('-USD-SWAP', 'USD')
        return raw

    rows = []
    header_seen = False
    for raw_line in str(text or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith('instid') and 'avgpx' in lowered and 'uplratio' in lowered:
            header_seen = True
            continue
        if not header_seen:
            continue
        if line.startswith('-') or lowered.startswith('environment:') or lowered.startswith('update available') or lowered.startswith('run:'):
            continue
        parts = re.split(r'\s{2,}|\t+', line)
        if len(parts) < 7:
            parts = line.split()
        if len(parts) < 7:
            continue
        inst_id, _side, size, avg_px, upl, upl_ratio, lever = parts[:7]
        try:
            size_num = float(size)
        except ValueError:
            continue
        side = 'short' if size_num < 0 else 'long'
        qty = abs(size_num)
        rows.append({
            'id': inst_id,
            'posId': inst_id,
            'instId': inst_id,
            'symbol': _symbol_from_inst_id(inst_id) or inst_id,
            'raw_symbol': inst_id,
            'side': side,
            'posSide': side,
            'direction': side,
            'status': 'active',
            'source': 'okx_cli_demo',
            'entryPrice': as_float(avg_px),
            'markPrice': as_float(avg_px),
            'unrealizedPnl': as_float(upl),
            'percentage': as_float(upl_ratio),
            'leverage': lever,
            'initialMargin': 0.0,
            'notional': 0.0,
            'liquidationPrice': 0.0,
            'marginRatio': 0.0,
            'contracts': qty,
            'availPos': qty,
            'marginMode': 'cross',
            'info': {
                'instId': inst_id,
                'side': side,
                'avgPx': as_float(avg_px),
                'upl': as_float(upl),
                'uplRatio': as_float(upl_ratio),
                'lever': lever,
                'source': 'okx_cli_demo',
            },
        })
    return rows

def _parse_okx_balance_cli_output(text):
    snapshot = {
        'totalEq': 0.0,
        'usdtEq': 0.0,
        'usdtAvail': 0.0,
        'source': 'okx_cli_demo',
        'synced_at': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    header_seen = False
    for raw_line in str(text or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith('currency') and 'equity' in lowered and 'available' in lowered:
            header_seen = True
            continue
        if not header_seen:
            continue
        if line.startswith('-') or lowered.startswith('environment:') or lowered.startswith('update available') or lowered.startswith('run:'):
            continue
        parts = re.split(r'\s{2,}|\t+', line)
        if len(parts) < 4:
            parts = line.split()
        if len(parts) < 4:
            continue
        ccy, equity, available, frozen = parts[:4]
        if str(ccy).upper() == 'USDT':
            snapshot['usdtEq'] = as_float(equity)
            snapshot['usdtAvail'] = as_float(available)
            snapshot['totalEq'] = as_float(equity)
            return snapshot
    return None

if not config.OKX_API_KEY or config.OKX_API_KEY.startswith("YOUR_") or config.OKX_API_KEY == 'OKX_API_KEY_PLACEHOLDER':
    print("[SYSTEM CONFIG] OKX API key is not configured.")
else:
    try:
        okx.load_markets()
        print("[SYSTEM CONFIG] OKX API loaded successfully.")
    except ccxt.PermissionDenied as pd_err:
        print(f"[SYSTEM CONFIG] OKX permission denied or IP not whitelisted: {pd_err}")
    except Exception as exc:
        print(f"[SYSTEM CONFIG] OKX load_markets failed: {exc}")

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
                        row for row in list(reversed(state.active_trades)) + list(reversed(state.trade_journal))
                        if str(row.get('instId') or '') == inst_id
                        and str(row.get('direction') or '').lower() == direction
                        and str(row.get('strategy') or '') not in ['', 'Manual', 'Mixed']
                    ),
                    None,
                )
                if better_lifecycle is not None:
                    effective_lifecycle = better_lifecycle

            strategy = infer_history_strategy(record, effective_lifecycle)
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
                inferred_strategy = infer_history_strategy(row, row)
                fallback_row.setdefault('pnl_source', 'journal_fallback')
                fallback_row.setdefault('realizedPnl', as_float(row.get('realized_pnl', row.get('pnl'))))
                fallback_row.setdefault('alphaPnl', as_float(row.get('realized_pnl', row.get('pnl'))) - as_float(row.get('funding_fee')))
                fallback_row.setdefault('fee', as_float(row.get('fee')))
                fallback_row.setdefault('fundingFee', as_float(row.get('funding_fee')))
                fallback_row['strategy'] = inferred_strategy
                fallback_row.setdefault('strategy_version', row.get('strategy_version'))
                fallback_row['strategy_mix'] = [inferred_strategy] if inferred_strategy not in ['Manual', 'Mixed'] else []
                fallback_row.setdefault('strategy_versions', [row.get('strategy_version')] if row.get('strategy_version') else [])
                fallback_row.update(assess_accounting_record(fallback_row, fallback_row))
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
            inferred_strategy = infer_history_strategy(row, row)
            fallback_row.setdefault('pnl_source', 'journal_fallback')
            fallback_row.setdefault('realizedPnl', as_float(row.get('realized_pnl', row.get('pnl'))))
            fallback_row.setdefault('alphaPnl', as_float(row.get('realized_pnl', row.get('pnl'))) - as_float(row.get('funding_fee')))
            fallback_row.setdefault('fee', as_float(row.get('fee')))
            fallback_row.setdefault('fundingFee', as_float(row.get('funding_fee')))
            fallback_row['strategy'] = inferred_strategy
            fallback_row.setdefault('strategy_version', row.get('strategy_version'))
            fallback_row['strategy_mix'] = [inferred_strategy] if inferred_strategy not in ['Manual', 'Mixed'] else []
            fallback_row.setdefault('strategy_versions', [row.get('strategy_version')] if row.get('strategy_version') else [])
            fallback_row.update(assess_accounting_record(fallback_row, fallback_row))
            fallback_history.append(fallback_row)
        if fallback_history:
            fallback_history.sort(key=lambda row: int(row.get('lastUpdateTimestamp') or row.get('timestamp') or 0), reverse=True)
            state.exchange_history_cache = fallback_history[:config.EXCHANGE_HISTORY_LIMIT]
            state.exchange_history_synced_at = now
    finally:
        state.exchange_history_lock.release()
    return state.exchange_history_cache

def infer_history_strategy(record, lifecycle=None):
    return infer_strategy_from_metadata(lifecycle or {}, record or {})

def realized_strategy_rows(strategy_name, limit):
    history = sync_exchange_history()
    rows = []
    seen_keys = set()
    cutoff_ms = learning_cutoff_ms()

    def row_key(row):
        return (
            str(row.get('close_event_key') or ''),
            str(row.get('posId') or ''),
            str(row.get('closed_at') or row.get('lastUpdateTimestamp') or row.get('timestamp') or ''),
            str(row.get('strategy') or ''),
            str(row.get('symbol') or row.get('instId') or ''),
        )

    def row_after_cutoff(row):
        row_ms = timestamp_ms(
            row.get('closed_at')
            or row.get('lastUpdateTimestamp')
            or row.get('timestamp')
            or row.get('uTime')
            or row.get('updated_at')
        )
        return row_ms >= cutoff_ms if cutoff_ms > 0 and row_ms > 0 else False

    for row in reversed(history):
        if not row_after_cutoff(row):
            continue
        if row.get('strategy') != strategy_name:
            continue
        if row.get('eligible_for_learning') is not True or row.get('accounting_status') != 'verified':
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
            if infer_history_strategy(row, row) == strategy_name
            and row_after_cutoff(row)
            and row.get('status') == 'closed'
            and row.get('eligible_for_learning') is True
            and row.get('accounting_status') == 'verified'
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

def _okx_public_call(method_names, params=None):
    params = params or {}
    for name in method_names:
        method = getattr(okx, name, None)
        if method is not None:
            return method(params)
    raise AttributeError(f"OKX public method unavailable: {method_names[0]}")

def _okx_swap_symbol_from_inst_id(inst_id):
    raw = str(inst_id or '').upper().strip()
    if not raw.endswith('-USDT-SWAP'):
        return ''
    base = raw.replace('-USDT-SWAP', '')
    if not base or base in config.NON_CRYPTO_BASES:
        return ''
    return f'{base}/USDT:USDT'

def _native_okx_usdt_swap_universe():
    instruments_res = _okx_public_call(
        ['public_get_public_instruments', 'publicGetPublicInstruments'],
        {'instType': 'SWAP'},
    )
    tickers_res = _okx_public_call(
        ['public_get_market_tickers', 'publicGetMarketTickers'],
        {'instType': 'SWAP'},
    )
    instruments = instruments_res.get('data') if isinstance(instruments_res, dict) else []
    tickers = tickers_res.get('data') if isinstance(tickers_res, dict) else []
    valid_inst = {}
    for inst in instruments or []:
        if not isinstance(inst, dict):
            continue
        inst_id = str(inst.get('instId') or '')
        symbol = _okx_swap_symbol_from_inst_id(inst_id)
        if not symbol:
            continue
        if str(inst.get('settleCcy') or inst.get('settle') or 'USDT').upper() != 'USDT':
            continue
        if str(inst.get('state') or 'live').lower() not in {'live', ''}:
            continue
        valid_inst[inst_id] = symbol

    rows = []
    for ticker in tickers or []:
        if not isinstance(ticker, dict):
            continue
        inst_id = str(ticker.get('instId') or '')
        symbol = valid_inst.get(inst_id) or _okx_swap_symbol_from_inst_id(inst_id)
        if not symbol:
            continue
        last = as_float(ticker.get('last') or ticker.get('lastPx'))
        open24h = as_float(ticker.get('open24h') or ticker.get('sodUtc0'))
        change_pct = ((last - open24h) / open24h * 100.0) if last > 0 and open24h > 0 else 0.0
        quote_volume = as_float(ticker.get('volCcy24h') or ticker.get('volUsd24h'))
        if quote_volume <= 0:
            quote_volume = as_float(ticker.get('vol24h')) * last
        rows.append({
            'symbol': symbol,
            'instId': inst_id,
            'quoteVolume': quote_volume,
            'percentage': change_pct,
            'high': as_float(ticker.get('high24h')),
            'low': as_float(ticker.get('low24h')),
            'last': last,
        })
    rows.sort(key=lambda row: as_float(row.get('quoteVolume')), reverse=True)
    return rows

def _classify_scan_symbol(ticker, btc_pct, funding_rate=0.0):
    sym = str(ticker.get('symbol') or '')
    sym_clean = sym.replace(':USDT', '').replace('/', '')
    if sym_clean in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        return 'Majors'
    fr = as_float(funding_rate)
    if fr and (fr < -0.0005 or fr > 0.0005):
        return 'Squeeze Watch'
    pct = as_float(ticker.get('percentage'))
    if pct > btc_pct + 5:
        return 'Alpha Rel. Strength'
    if pct < -5:
        return 'Deep Oversold'
    high = as_float(ticker.get('high'))
    low = as_float(ticker.get('low'))
    if low > 0 and ((high - low) / low) > 0.10:
        return 'High Volatility'
    return 'High Volume'

def _build_scan_universe_from_tickers(tickers, funding=None, limit=None):
    funding = funding or {}
    limit = int(limit or getattr(config, 'MARKET_UNIVERSE_LIMIT', 200) or 200)
    btc_pct = 0.0
    if isinstance(tickers, dict):
        for key in ['BTC/USDT:USDT', 'BTC-USDT-SWAP']:
            row = tickers.get(key)
            if row:
                btc_pct = as_float(row.get('percentage'))
                break
        ticker_rows = list(tickers.values())
    else:
        ticker_rows = list(tickers or [])
        for row in ticker_rows:
            if str(row.get('symbol') or '') == 'BTC/USDT:USDT':
                btc_pct = as_float(row.get('percentage'))
                break

    ticker_rows = [row for row in ticker_rows if isinstance(row, dict) and row.get('symbol')]
    ticker_rows.sort(key=lambda row: as_float(row.get('quoteVolume')), reverse=True)
    selected_symbols = []
    categories = {}
    for row in ticker_rows[:max(limit, 1)]:
        sym = row['symbol']
        if sym in selected_symbols:
            continue
        fr_row = funding.get(sym) if isinstance(funding, dict) else None
        fr = as_float((fr_row or {}).get('fundingRate')) if isinstance(fr_row, dict) else 0.0
        selected_symbols.append(sym)
        categories[sym] = _classify_scan_symbol(row, btc_pct, fr)
    return selected_symbols[:limit], categories

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
        top_200 = sorted_swaps[:200]
        
        btc_pct = tickers.get('BTC/USDT:USDT', {}).get('percentage', 0)
        if btc_pct is None: btc_pct = 0
        
        for t in top_200:
            sym = t['symbol']
            sym_clean = sym.replace(':USDT', '').replace('/', '')
            if sym in selected_symbols: continue
            
            if sym_clean in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                categories[sym] = "撌券祠銝餅? (Majors)"
                selected_symbols.append(sym)
                continue
                
            fr = funding.get(sym, {}).get('fundingRate', 0)
            if fr is None: fr = 0
            if fr and (fr < -0.0005 or fr > 0.0005):
                categories[sym] = "鞈?鞎餌??啣虜 (Squeeze Watch)"
                selected_symbols.append(sym)
                continue
                
            pct = t.get('percentage', 0)
            if pct is None: pct = 0
            if pct > btc_pct + 5:
                categories[sym] = "Alpha ?函?銵? (Rel. Strength)"
                selected_symbols.append(sym)
                continue
                
            if pct < -5:
                categories[sym] = "璆萇垢頞? (Deep Oversold)"
                selected_symbols.append(sym)
                continue
                
            high = t.get('high', 0)
            low = t.get('low', 0)
            if high is None: high = 0
            if low is None: low = 0
            if low > 0 and ((high - low) / low) > 0.10:
                categories[sym] = "??擃郭??(High Volatility)"
                selected_symbols.append(sym)
                continue
                
        for t in top_200:
            if len(selected_symbols) >= 100: break
            sym = t['symbol']
            if sym not in selected_symbols:
                categories[sym] = "?桅???(High Volume)"
                selected_symbols.append(sym)
                
        return selected_symbols[:100], categories
    except Exception as e:
        print(f"Error fetching top symbols: {e}")
        categories = {sym: 'Majors' for sym in config.FALLBACK_SCAN_SYMBOLS}
        return config.FALLBACK_SCAN_SYMBOLS, categories

def get_top_symbols_and_categories():
    """Load a broad OKX USDT swap universe before falling back to the static list."""
    limit = int(getattr(config, 'MARKET_UNIVERSE_LIMIT', 200) or 200)
    state.market_universe_limit = limit
    state.market_universe_refresh_seconds = int(getattr(config, 'MARKET_UNIVERSE_REFRESH_SECONDS', 3600) or 3600)
    try:
        okx.load_markets()
        tickers = okx.fetch_tickers(params={'instType': 'SWAP'})
        try:
            funding = okx.fetch_funding_rates(params={'instType': 'SWAP'})
        except Exception:
            funding = {}
        swap_symbols = {
            market['symbol']
            for market in (getattr(okx, 'markets', {}) or {}).values()
            if is_crypto_usdt_swap(market)
        }
        usdt_swaps = {symbol: row for symbol, row in (tickers or {}).items() if symbol in swap_symbols}
        selected, categories = _build_scan_universe_from_tickers(usdt_swaps, funding, limit)
        if len(selected) >= min(50, limit):
            print(f"[Market Universe] Loaded {len(selected)} OKX USDT swap symbols via ccxt.")
            state.market_universe_source = 'okx_ccxt_top_volume'
            state.market_universe_updated_at = datetime.datetime.now(datetime.UTC).isoformat()
            state.market_universe_error = None
            return selected, categories
        raise RuntimeError(f'ccxt universe too small: {len(selected)} symbols')
    except Exception as ccxt_err:
        print(f"Error fetching top symbols via ccxt: {ccxt_err}")
        try:
            native_rows = _native_okx_usdt_swap_universe()
            selected, categories = _build_scan_universe_from_tickers(native_rows, {}, limit)
            if len(selected) >= min(50, limit):
                print(f"[Market Universe] Loaded {len(selected)} OKX USDT swap symbols via native public API.")
                state.market_universe_source = 'okx_native_top_volume'
                state.market_universe_updated_at = datetime.datetime.now(datetime.UTC).isoformat()
                state.market_universe_error = None
                return selected, categories
            raise RuntimeError(f'native universe too small: {len(selected)} symbols')
        except Exception as native_err:
            print(f"Error fetching top symbols via OKX native public API: {native_err}")
            categories = {sym: 'Majors' for sym in config.FALLBACK_SCAN_SYMBOLS}
            state.market_universe_source = 'fallback_static'
            state.market_universe_updated_at = datetime.datetime.now(datetime.UTC).isoformat()
            state.market_universe_error = str(native_err)
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
            raw_text = f.read()

        def parse_snapshot_payload(text):
            try:
                return json.loads(text)
            except Exception:
                start = text.find('{')
                end = text.rfind('}')
                if start >= 0 and end > start:
                    try:
                        return json.loads(text[start:end + 1])
                    except Exception:
                        return {}
                return {}

        payload = parse_snapshot_payload(raw_text)
        instruments = payload.get('instruments') or []
        snapshot = {}
        for item in instruments:
            inst_id = str(item.get('instId') or '').strip()
            if inst_id:
                snapshot[inst_id] = dict(item)
        if not snapshot:
            snapshot = _embedded_market_snapshot()
        with state.local_market_snapshot_lock:
            state.local_market_snapshot_cache['fetched_at'] = now
            state.local_market_snapshot_cache['data'] = snapshot
        return dict(snapshot)
    except Exception:
        return _embedded_market_snapshot()

def load_local_positions_snapshot():
    now = time.monotonic()
    with state.positions_snapshot_lock:
        cached = state.positions_snapshot_cache['raw']
        if cached and now - state.positions_snapshot_cache['fetched_at'] < 30:
            return [dict(p) for p in cached]

    best_positions = None
    best_source = ''
    best_mtime = 0.0

    def extract_positions(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ('positions', 'data', 'items', 'rows'):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        nested = payload.get('snapshot')
        if isinstance(nested, dict):
            return extract_positions(nested)
        return []

    for file_name in config.LOCAL_POSITIONS_SNAPSHOT_PATHS:
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
                except Exception:
                    continue
            positions = extract_positions(payload) if payload is not None else []
            if not positions:
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        raw_text = f.read()
                    positions = _parse_okx_positions_cli_output(raw_text)
                except Exception:
                    positions = []
            if not positions:
                continue
            best_positions = [dict(row) for row in positions if isinstance(row, dict)]
            best_source = path
            best_mtime = mtime
        except Exception:
            continue

    if best_positions:
        with state.positions_snapshot_lock:
            state.positions_snapshot_cache['fetched_at'] = time.monotonic()
            state.positions_snapshot_cache['raw'] = [dict(p) for p in best_positions]
            state.positions_snapshot_cache['normalized'] = []
            state.positions_snapshot_cache['source'] = best_source
        return [dict(p) for p in best_positions]
    return []

def load_local_account_snapshot():
    now = time.monotonic()
    with state.local_account_snapshot_lock:
        cached = state.local_account_snapshot_cache['data']
        if cached and now - state.local_account_snapshot_cache['fetched_at'] < 30:
            return dict(cached)

    best_snapshot = None
    best_source = ''
    best_mtime = 0.0

    def build_snapshot_from_account_dict(account, source_label, synced_at):
        if not isinstance(account, dict):
            return None
        total_eq = as_float(account.get('totalEq') or account.get('eq') or account.get('adjEq') or account.get('equity'))
        usdt_eq = as_float(account.get('usdtEq') or account.get('cashBal') or account.get('bal'))
        usdt_avail = as_float(account.get('usdtAvail') or account.get('availEq') or account.get('availBal') or account.get('avail'))

        if isinstance(account.get('total'), dict):
            total_eq = max(total_eq, as_float(account['total'].get('USDT')))
        if isinstance(account.get('free'), dict):
            usdt_avail = max(usdt_avail, as_float(account['free'].get('USDT')))
        if isinstance(account.get('used'), dict):
            used_total = as_float(account['used'].get('USDT'))
            if usdt_eq <= 0 and (usdt_avail > 0 or used_total > 0):
                usdt_eq = usdt_avail + used_total
        if isinstance(account.get('details'), list):
            for det in account.get('details') or []:
                if not isinstance(det, dict):
                    continue
                if str(det.get('ccy') or '').upper() != 'USDT':
                    continue
                usdt_eq = max(usdt_eq, as_float(det.get('eq') or det.get('cashBal') or det.get('bal')))
                usdt_avail = max(usdt_avail, as_float(det.get('availEq') or det.get('availBal') or det.get('avail')))
                total_eq = max(total_eq, as_float(det.get('eqUsd') or det.get('eq') or det.get('cashBal') or det.get('bal')))
                break
        if total_eq <= 0 and usdt_eq > 0:
            total_eq = usdt_eq
        if usdt_avail <= 0 and usdt_eq > 0:
            usdt_avail = usdt_eq

        if total_eq <= 0 and usdt_eq <= 0 and usdt_avail <= 0:
            return None
        return {
            'totalEq': total_eq,
            'usdtEq': usdt_eq,
            'usdtAvail': usdt_avail,
            'source': source_label,
            'synced_at': synced_at,
        }

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
                except Exception:
                    continue
            candidate = None
            if payload is not None:
                account = payload.get('account') if isinstance(payload, dict) and isinstance(payload.get('account'), dict) else payload if isinstance(payload, dict) else None
                candidate = build_snapshot_from_account_dict(
                    account,
                    f'cached_account_snapshot:{os.path.basename(path)}',
                    datetime.datetime.fromtimestamp(mtime).isoformat(timespec='seconds'),
                )
            if candidate is None:
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        raw_text = f.read()
                    candidate = _parse_okx_balance_cli_output(raw_text)
                    if candidate:
                        candidate['source'] = f'cached_account_snapshot:{os.path.basename(path)}'
                        candidate['synced_at'] = datetime.datetime.fromtimestamp(mtime).isoformat(timespec='seconds')
                except Exception:
                    candidate = None
            if candidate is None:
                continue
            best_snapshot = candidate
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
    if config.MOCK_MODE:
        # Mock mode directly returns fallback positions derived from active_trades to bypass API permission blocks
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

    def _fetch_positions_from_cli():
        cli_output = _run_okx_cli([
            '--profile',
            config.OKX_PROFILE.get('profile_name') or 'okx-demo',
            '--demo',
            'swap',
            'positions',
        ])
        cli_positions = _parse_okx_positions_cli_output(cli_output)
        if cli_positions:
            with state.positions_snapshot_lock:
                state.positions_snapshot_cache['fetched_at'] = time.monotonic()
                state.positions_snapshot_cache['raw'] = [dict(p) for p in cli_positions]
                state.positions_snapshot_cache['normalized'] = []
                state.positions_snapshot_cache['source'] = 'okx_cli_positions'
            return cli_positions
        return []

    if config.DEMO_MODE or config.OKX_SANDBOX_MODE:
        try:
            cli_positions = _fetch_positions_from_cli()
            if cli_positions:
                return cli_positions
        except Exception as cli_exc:
            print(f"[positions cli primary ERROR] {cli_exc}")
        local_positions = load_local_positions_snapshot()
        if local_positions:
            print(f"[positions source] using local demo snapshot ({len(local_positions)} rows)")
            with state.positions_snapshot_lock:
                state.positions_snapshot_cache['fetched_at'] = time.monotonic()
                state.positions_snapshot_cache['raw'] = [dict(p) for p in local_positions]
                state.positions_snapshot_cache['normalized'] = []
                state.positions_snapshot_cache['source'] = 'local_demo_snapshot'
            return local_positions

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
        # Prefer a fresher CLI positions read before falling back to any cached
        # in-memory snapshot. This keeps the UI aligned with the actual demo/live
        # account when the REST endpoint is stale or temporarily unavailable.
        try:
            cli_positions = _fetch_positions_from_cli()
            if cli_positions:
                print(f"[positions fallback] {exc}; recovered {len(cli_positions)} positions from okx cli")
                return cli_positions
        except Exception as cli_exc:
            print(f"[positions fallback CLI ERROR] {cli_exc}")

        with state.positions_snapshot_lock:
            cached = state.positions_snapshot_cache.get('raw') or []
            if cached:
                print(f"[positions fallback] {exc}")
                return [dict(p) for p in cached]
        local_positions = load_local_positions_snapshot()
        if local_positions:
            print(f"[positions fallback] {exc}; recovered {len(local_positions)} positions from local live snapshot")
            return local_positions
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
    if config.MOCK_MODE:
        return {
            'totalEq': config.START_EQUITY_USDT,
            'usdtEq': config.START_EQUITY_USDT,
            'usdtAvail': config.START_EQUITY_USDT,
            'source': 'mock_account_balance',
            'synced_at': datetime.datetime.now().isoformat(timespec='seconds'),
        }

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

    if response is None and last_error:
        print(f"[account REST fallback] {last_error}; trying okx cli/local snapshots")

    snapshot = {
        'totalEq': 0.0,
        'usdtEq': 0.0,
        'usdtAvail': 0.0,
        'source': 'okx_account_balance',
        'synced_at': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    found = False
    rows = []
    def ingest_account_bucket(bucket):
        nonlocal found
        if not isinstance(bucket, dict):
            return
        snapshot['usdtEq'] = max(
            snapshot['usdtEq'],
            as_float(bucket.get('total') or bucket.get('eq') or bucket.get('bal') or bucket.get('cashBal')),
        )
        snapshot['usdtAvail'] = max(
            snapshot['usdtAvail'],
            as_float(bucket.get('free') or bucket.get('available') or bucket.get('avail') or bucket.get('availBal')),
        )
        if snapshot['usdtEq'] > 0 or snapshot['usdtAvail'] > 0:
            found = True

    if isinstance(response, dict):
        if isinstance(response.get('data'), list):
            rows = response.get('data') or []
        elif isinstance(response.get('info'), dict) and isinstance(response['info'].get('data'), list):
            rows = response['info'].get('data') or []

        usdt_bucket = response.get('USDT')
        if isinstance(usdt_bucket, dict):
            ingest_account_bucket(usdt_bucket)
        elif isinstance(usdt_bucket, (int, float, str)):
            snapshot['usdtEq'] = max(snapshot['usdtEq'], as_float(usdt_bucket))
            snapshot['usdtAvail'] = max(snapshot['usdtAvail'], as_float(usdt_bucket))
            found = found or snapshot['usdtEq'] > 0

        for key in ('free', 'used', 'total'):
            value = response.get(key)
            if isinstance(value, dict):
                if key == 'free':
                    snapshot['usdtAvail'] = max(snapshot['usdtAvail'], as_float(value.get('USDT')))
                    found = found or snapshot['usdtAvail'] > 0
                elif key == 'used':
                    used_total = as_float(value.get('USDT'))
                    if used_total > 0 and snapshot['usdtEq'] <= 0 and snapshot['usdtAvail'] > 0:
                        snapshot['usdtEq'] = snapshot['usdtAvail'] + used_total
                    found = found or used_total > 0
                elif key == 'total':
                    snapshot['usdtEq'] = max(snapshot['usdtEq'], as_float(value.get('USDT')))
                    found = found or snapshot['usdtEq'] > 0

        if isinstance(response.get('balances'), list):
            rows.extend([row for row in response.get('balances') if isinstance(row, dict)])
        if isinstance(response.get('info'), dict) and isinstance(response['info'].get('details'), list):
            rows.extend([row for row in response['info'].get('details') if isinstance(row, dict)])

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
    if snapshot['usdtEq'] <= 0 and snapshot['totalEq'] > 0:
        snapshot['usdtEq'] = snapshot['totalEq']
    if snapshot['usdtAvail'] <= 0 and snapshot['usdtEq'] > 0:
        snapshot['usdtAvail'] = snapshot['usdtEq']

    if found:
        with state.account_snapshot_lock:
            state.account_snapshot_cache['fetched_at'] = time.monotonic()
            state.account_snapshot_cache['data'] = dict(snapshot)
        return snapshot

    with state.account_snapshot_lock:
        cached = state.account_snapshot_cache['data']
        if cached:
            return dict(cached)

    try:
        cli_output = _run_okx_cli(['--profile', config.OKX_PROFILE.get('profile_name') or 'okx-demo', '--demo', 'account', 'balance'])
        cli_snapshot = _parse_okx_balance_cli_output(cli_output)
        if cli_snapshot:
            with state.account_snapshot_lock:
                state.account_snapshot_cache['fetched_at'] = time.monotonic()
                state.account_snapshot_cache['data'] = dict(cli_snapshot)
            return cli_snapshot
    except Exception as cli_exc:
        print(f"[account fallback CLI ERROR] {cli_exc}")

    local_snapshot = load_local_account_snapshot()
    if local_snapshot:
        with state.account_snapshot_lock:
            state.account_snapshot_cache['fetched_at'] = time.monotonic()
            state.account_snapshot_cache['data'] = dict(local_snapshot)
        return local_snapshot

    return None

def capital_snapshot(account_snapshot=None, visible_trades=None):
    # Helper to calculate start-equity based metrics
    acc_snap = account_snapshot if isinstance(account_snapshot, dict) else fetch_okx_account_snapshot(force=True)
    account_equity = 0.0
    account_total_equity = 0.0
    equity_basis = 'missing'

    def _pull_equity(snapshot):
        nonlocal account_equity, account_total_equity, equity_basis
        if not isinstance(snapshot, dict):
            return
        usdt_eq = as_float(snapshot.get('usdtEq'))
        usdt_avail = as_float(snapshot.get('usdtAvail'))
        total_eq = max(as_float(snapshot.get('totalEq')), as_float(snapshot.get('equity')))
        account_total_equity = max(account_total_equity, total_eq)

        # V13 reports the trading capital in USDT terms. OKX totalEq can include
        # non-USDT assets, so it is only a last-resort fallback.
        if usdt_eq > 0:
            candidate = usdt_eq
            basis = 'usdtEq'
        elif usdt_avail > 0:
            candidate = usdt_avail
            basis = 'usdtAvail'
        else:
            candidate = total_eq
            basis = 'totalEq_fallback'

        if candidate > account_equity:
            account_equity = candidate
            equity_basis = basis
        nested = snapshot.get('account')
        if isinstance(nested, dict):
            _pull_equity(nested)

    _pull_equity(acc_snap)
    if account_equity <= 0:
        _pull_equity(load_local_account_snapshot())
    if account_equity <= 0 and isinstance(state.account_data, dict):
        _pull_equity(state.account_data)
        if isinstance(state.account_data.get('account'), dict):
            _pull_equity(state.account_data.get('account'))
    if account_equity <= 0 and isinstance(acc_snap, dict) and isinstance(acc_snap.get('account'), dict):
        _pull_equity(acc_snap.get('account'))
    from .utils import session_start_equity
    session_start = session_start_equity()
    session_target = session_start + (config.TARGET_EQUITY_USDT - config.START_EQUITY_USDT)
    history = sync_exchange_history()
    session_cutoff_ms = session_started_at_ms()
    session_history_rows = [
        row for row in history
        if timestamp_ms(row.get('closed_at') or row.get('timestamp') or row.get('uTime') or row.get('updated_at')) >= session_cutoff_ms
    ]
    strategy_realized = sum(
        as_float(row.get('realizedPnl') or row.get('realized_pnl') or row.get('pnl'))
        for row in session_history_rows
        if row.get('status') == 'closed' or row.get('closed_at')
    )
    # Keep unrealized PnL aligned with the live UI snapshot.
    # This mirrors the same live-trade view used by /api/trades and /api/report.
    strategy_unrealized = 0.0
    try:
        if visible_trades is None:
            from .engine import build_live_trade_snapshot, collapse_active_records, fetch_live_okx_positions
            live_positions = fetch_live_okx_positions()
            visible_trades = build_live_trade_snapshot(
                tracked_records=collapse_active_records(state.active_trades),
                live_positions=live_positions,
                include_potentials=False,
            )
        strategy_unrealized = sum(
            as_float(trade.get('pnl'))
            for trade in (visible_trades or [])
            if trade.get('status') == 'active' and not trade.get('non_blocking_active')
        )
    except Exception:
        seen_active_keys = set()
        for trade in state.active_trades:
            if trade.get('status') != 'active' or trade.get('non_blocking_active'):
                continue
            key = (
                str(trade.get('instId') or trade.get('symbol') or '').upper(),
                str(trade.get('direction') or '').lower(),
            )
            if key in seen_active_keys:
                continue
            seen_active_keys.add(key)
            strategy_unrealized += as_float(trade.get('pnl'))
    session_cumulative_pnl = strategy_realized + strategy_unrealized
    account_snapshot_available = account_equity > 0
    if account_snapshot_available:
        equity = account_equity
        account_layer_pnl = equity - session_start
        cumulative_pnl = account_layer_pnl
        cumulative_source = 'okx_account'
        account_layer_source = 'okx_account'
    else:
        equity = session_start + session_cumulative_pnl
        account_layer_pnl = None
        cumulative_pnl = None
        cumulative_source = 'account_snapshot_missing'
        account_layer_source = 'account_snapshot_missing'
    pnl_from_start = equity - session_start
    return_pct = (pnl_from_start / session_start * 100) if session_start else 0.0
    goal_progress = (pnl_from_start / (session_target - session_start) * 100) if session_target > session_start else 0.0
    return {
        'start': round(session_start, 4),
        'target': round(session_target, 4),
        'equity': round(equity, 4),
        'account_equity': account_equity,
        'account_total_equity': round(account_total_equity, 4),
        'equity_basis': equity_basis,
        'account_snapshot_available': account_snapshot_available,
        'account_layer_pnl': round(account_layer_pnl, 4) if account_layer_pnl is not None else None,
        'account_layer_source': account_layer_source,
        'session_started_at': config.SESSION_STARTED_AT,
        'strategy_realized': round(strategy_realized, 4),
        'cumulative_pnl': round(cumulative_pnl, 4) if cumulative_pnl is not None else None,
        'cumulative_source': cumulative_source,
        'session_cumulative_pnl': round(session_cumulative_pnl, 4),
        'session_cumulative_source': 'synthetic_session',
        'strategy_unrealized_source': 'collapsed_active_trades',
        'quarantined_count': sum(1 for row in session_history_rows if row.get('accounting_status') == 'quarantined'),
        'quarantined_reported_pnl': round(sum(as_float(row.get('realizedPnl') or row.get('realized_pnl')) for row in session_history_rows if row.get('accounting_status') == 'quarantined'), 4),
        'strategy_unrealized': round(strategy_unrealized, 4),
        'pnl_from_start': round(pnl_from_start, 4),
        'return_pct': round(return_pct, 3),
        'goal_progress_pct': round(goal_progress, 3),
        'remaining': round(session_target - equity, 4),
        'state': 'drawdown' if equity < session_start else ('target_reached' if equity >= session_target else 'growing'),
    }
