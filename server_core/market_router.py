import datetime
import math
import time
import uuid

import pandas as pd

from . import config
from . import state
from .utils import as_float, clamp


STATE_TO_MODE = {
    'TREND': 'MacroSniper',
    'MEAN_REVERSION': 'MeanReversion',
    'EXTREME_REVERSAL': 'Contrarian',
    'SQUEEZE_BREAKOUT': 'SqueezeHunter',
}

MODE_TO_STATE = {mode: market_state for market_state, mode in STATE_TO_MODE.items()}


def _utc_now():
    return datetime.datetime.now(datetime.UTC).isoformat()


def _normalize_symbol(symbol):
    return str(symbol or '').upper().replace('/', '').replace(':USDT', '').replace('-USDT-SWAP', 'USDT')


def _series_last(series, default=0.0):
    try:
        value = series.iloc[-1]
    except Exception:
        return default
    return as_float(value, default)


def _calculate_adx(df, period=14):
    if df is None or df.empty or len(df) < period + 2:
        return pd.Series(dtype='float64')
    high = df['high']
    low = df['low']
    close = df['close']
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = minus_dm.abs()
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(window=period).mean().fillna(20.0)


def _trend_alignment_score(trends):
    h15 = str((trends or {}).get('15m') or 'neutral')
    h1 = str((trends or {}).get('1h') or 'neutral')
    h4 = str((trends or {}).get('4h') or 'neutral')
    d1 = str((trends or {}).get('1d') or 'neutral')
    score = 0.0
    direction = 'neutral'
    if h1 == h4 and h1 in {'bull', 'bear'}:
        score += 0.48
        direction = h1
    elif h1 in {'bull', 'bear'} or h4 in {'bull', 'bear'}:
        score += 0.28
        direction = h1 if h1 in {'bull', 'bear'} else h4
    if direction != 'neutral' and h15 == direction:
        score += 0.12
    if direction != 'neutral' and d1 == direction:
        score += 0.10
    if h1 in {'bull', 'bear'} and h4 in {'bull', 'bear'} and h1 != h4:
        score -= 0.20
    return clamp(score, 0.0, 0.75), direction


def _safe_bool(value):
    try:
        return bool(value)
    except Exception:
        return False


def _finite(value, default=0.0):
    value = as_float(value, default)
    return value if math.isfinite(value) else default


def score_market_state(symbol, category, trends, df, timeframe):
    if df is None or df.empty or len(df) < 30:
        return {
            'marketStateScores': {
                'TREND': 0.0,
                'MEAN_REVERSION': 0.0,
                'EXTREME_REVERSAL': 0.0,
                'SQUEEZE_BREAKOUT': 0.0,
                'NO_TRADE': 1.0,
            },
            'features': {'reason': 'insufficient candle history'},
            'directionHint': 'neutral',
            'routingReasons': ['insufficient candle history'],
        }

    closed = df.iloc[:-1].copy(deep=False) if len(df) > 2 else df
    if len(closed) < 30:
        closed = df
    last = closed.iloc[-1]
    prev = closed.iloc[-2]
    close = as_float(last.get('close'))
    open_ = as_float(last.get('open'))
    high = as_float(last.get('high'))
    low = as_float(last.get('low'))
    rsi = _finite(last.get('rsi'), 50.0)

    adx_series = _calculate_adx(closed)
    adx = _finite(_series_last(adx_series, 20.0), 20.0)
    adx_prev = _finite(adx_series.iloc[-2], 20.0) if len(adx_series) > 1 else 20.0
    adx_rising = adx > adx_prev

    avg_vol = _finite(closed['volume'].tail(20).mean(), 0.0) if 'volume' in closed else 0.0
    vol_ratio = as_float(last.get('volume'), 0.0) / avg_vol if avg_vol > 0 else 1.0
    avg_body = as_float((closed['close'].tail(10) - closed['open'].tail(10)).abs().mean(), 0.0)
    lower_wick = max(0.0, min(open_, close) - low)
    upper_wick = max(0.0, high - max(open_, close))
    reversal_wick_ratio = max(lower_wick, upper_wick) / max(avg_body, abs(close) * 0.0005, 1e-9)

    bb_mid = as_float(last.get('bb_mid'), close)
    bb_upper = as_float(last.get('bb_upper'), 0.0)
    bb_lower = as_float(last.get('bb_lower'), 0.0)
    bb_width = _finite(last.get('bb_width'), 0.0)
    if bb_width <= 0 and bb_upper > 0 and bb_lower > 0 and bb_mid > 0:
        bb_width = (bb_upper - bb_lower) / bb_mid
    bb_width_prev = as_float(prev.get('bb_width'), bb_width)
    if bb_width_prev <= 0 and bb_upper > 0 and bb_lower > 0 and bb_mid > 0:
        bb_width_prev = bb_width
    squeeze_recent = False
    if 'is_squeezed' in closed:
        squeeze_recent = any(_safe_bool(v) for v in closed.tail(8)['is_squeezed'])
    squeeze_expanding = bb_width > bb_width_prev and bb_width > 0

    trend_alignment, trend_direction = _trend_alignment_score(trends)
    adx_score = clamp((adx - 18.0) / 18.0, 0.0, 1.0)
    trend_score = clamp(trend_alignment + adx_score * 0.30 + (0.08 if adx_rising else -0.04), 0.0, 1.0)

    low_adx_score = clamp((32.0 - adx) / 18.0, 0.0, 1.0)
    rsi_revert_pressure = max(
        clamp((45.0 - rsi) / 18.0, 0.0, 1.0),
        clamp((rsi - 55.0) / 18.0, 0.0, 1.0),
    )
    bb_touch = 0.0
    if bb_lower > 0 and low <= bb_lower:
        bb_touch = max(bb_touch, 0.35)
    if bb_upper > 0 and high >= bb_upper:
        bb_touch = max(bb_touch, 0.35)
    mean_score = clamp(low_adx_score * 0.42 + rsi_revert_pressure * 0.36 + bb_touch, 0.0, 1.0)
    if adx > 32 and adx_rising:
        mean_score *= 0.45

    extreme_rsi = max(
        clamp((32.0 - rsi) / 14.0, 0.0, 1.0),
        clamp((rsi - 68.0) / 14.0, 0.0, 1.0),
    )
    wick_score = clamp((reversal_wick_ratio - 1.0) / 2.5, 0.0, 1.0)
    extreme_score = clamp(extreme_rsi * 0.56 + wick_score * 0.30 + bb_touch * 0.45, 0.0, 1.0)
    if trend_score > 0.72 and extreme_rsi < 0.55:
        extreme_score *= 0.55

    required_vol = 1.15 if any(kw in str(symbol).upper() for kw in ['BTC', 'ETH', 'SOL']) else 1.25
    vol_score = clamp((vol_ratio - 1.0) / max(required_vol - 1.0, 0.1), 0.0, 1.0)
    squeeze_score = clamp(
        (0.42 if squeeze_recent else 0.0)
        + (0.24 if squeeze_expanding else 0.0)
        + vol_score * 0.28
        + adx_score * 0.12,
        0.0,
        1.0,
    )
    if 'squeeze' not in str(category or '').lower() and not squeeze_recent:
        squeeze_score *= 0.62

    conflict_penalty = 0.0
    if trends and str(trends.get('1h')) in {'bull', 'bear'} and str(trends.get('4h')) in {'bull', 'bear'}:
        conflict_penalty = 0.20 if trends.get('1h') != trends.get('4h') else 0.0
    max_edge_score = max(trend_score, mean_score, extreme_score, squeeze_score)
    no_trade_score = clamp(
        0.22
        + (0.38 if max_edge_score < config.MARKET_ROUTER_MIN_CONFIDENCE else 0.0)
        + conflict_penalty
        + (0.14 if not math.isfinite(close) or close <= 0 else 0.0),
        0.0,
        1.0,
    )

    features = {
        'timeframe': timeframe,
        'rsi': round(rsi, 2),
        'adx': round(adx, 2),
        'adx_prev': round(adx_prev, 2),
        'adx_rising': bool(adx_rising),
        'volume_ratio': round(vol_ratio, 3),
        'bb_width': round(bb_width, 6),
        'bb_width_expanding': bool(squeeze_expanding),
        'squeeze_recent': bool(squeeze_recent),
        'reversal_wick_ratio': round(reversal_wick_ratio, 3),
        'trend_direction': trend_direction,
        'trends': dict(trends or {}),
        'category': category,
    }
    reasons = [
        f"ADX={adx:.1f} {'rising' if adx_rising else 'cooling'}",
        f"RSI={rsi:.1f}",
        f"vol={vol_ratio:.2f}x",
        f"trend={trend_direction}",
    ]
    return {
        'marketStateScores': {
            'TREND': round(trend_score, 3),
            'MEAN_REVERSION': round(mean_score, 3),
            'EXTREME_REVERSAL': round(extreme_score, 3),
            'SQUEEZE_BREAKOUT': round(squeeze_score, 3),
            'NO_TRADE': round(no_trade_score, 3),
        },
        'features': features,
        'directionHint': trend_direction,
        'routingReasons': reasons,
    }


def _select_route(scored):
    scores = dict(scored.get('marketStateScores') or {})
    tradable = {key: scores.get(key, 0.0) for key in STATE_TO_MODE}
    ranked = sorted(tradable.items(), key=lambda item: item[1], reverse=True)
    best_state, best_score = ranked[0] if ranked else ('NO_TRADE', 0.0)
    second_state, second_score = ranked[1] if len(ranked) > 1 else ('NO_TRADE', 0.0)
    no_trade_score = scores.get('NO_TRADE', 0.0)
    score_gap = max(0.0, best_score - second_score)

    selected_state = best_state
    selected_mode = STATE_TO_MODE.get(best_state, 'NO_TRADE')
    if (
        best_score < config.MARKET_ROUTER_MIN_CONFIDENCE
        or no_trade_score >= best_score + 0.05
        or (score_gap < config.MARKET_ROUTER_MIN_SCORE_GAP and best_score < 0.65)
    ):
        selected_state = 'NO_TRADE'
        selected_mode = 'NO_TRADE'

    return {
        'selectedMarketState': selected_state,
        'selectedMode': selected_mode,
        'routingConfidence': round(best_score if selected_mode != 'NO_TRADE' else no_trade_score, 3),
        'secondBestState': second_state,
        'secondBestMode': STATE_TO_MODE.get(second_state, 'NO_TRADE'),
        'scoreGap': round(score_gap, 3),
        'blockedModes': [
            mode for mode in STATE_TO_MODE.values()
            if mode != selected_mode
        ] if selected_mode != 'NO_TRADE' else list(STATE_TO_MODE.values()),
    }


def _cache_key(symbol):
    return _normalize_symbol(symbol)


def route_symbol_market(symbol, category, trends, df, timeframe):
    if not getattr(config, 'MARKET_ROUTER_ENABLED', True):
        return {
            'symbol': symbol,
            'selectedMarketState': MODE_TO_STATE.get('MacroSniper', 'TREND'),
            'selectedMode': 'MacroSniper',
            'routingConfidence': 1.0,
            'secondBestMode': 'NO_TRADE',
            'scoreGap': 1.0,
            'marketStateScores': {},
            'routingReasons': ['market router disabled'],
            'blockedModes': [],
        }

    key = _cache_key(symbol)
    now = time.time()
    ttl = max(30, int(getattr(config, 'MARKET_ROUTER_OWNER_TTL_SECONDS', 600) or 600))
    with state.market_router_lock:
        cached = state.market_router_cache.get(key)
        if cached and now - as_float(cached.get('_cached_at')) < ttl:
            return dict(cached)

    scored = score_market_state(symbol, category, trends, df, timeframe)
    route = _select_route(scored)
    payload = {
        'eventId': uuid.uuid4().hex,
        'timestamp': _utc_now(),
        'symbol': key,
        'rawSymbol': symbol,
        'category': category,
        **scored,
        **route,
        '_cached_at': now,
        'ownershipExpiresAt': datetime.datetime.fromtimestamp(now + ttl, datetime.UTC).isoformat(),
    }
    payload['activeModeOwner'] = payload['selectedMode']

    with state.market_router_lock:
        cached = state.market_router_cache.get(key)
        if cached and now - as_float(cached.get('_cached_at')) < ttl:
            return dict(cached)
        state.market_router_cache[key] = dict(payload)
        state.market_mode_ownership[key] = {
            'symbol': key,
            'activeModeOwner': payload['selectedMode'],
            'marketState': payload['selectedMarketState'],
            'routingConfidence': payload['routingConfidence'],
            'ownershipStartedAt': payload['timestamp'],
            'ownershipExpiresAt': payload['ownershipExpiresAt'],
            'blockedModes': payload['blockedModes'],
            'scoreGap': payload['scoreGap'],
        }
        event = {
            'eventId': payload['eventId'],
            'timestamp': payload['timestamp'],
            'symbol': key,
            'mode': payload['selectedMode'],
            'marketState': payload['selectedMarketState'],
            'routingScore': payload['routingConfidence'],
            'routingConfidence': payload['routingConfidence'],
            'features': payload['features'],
            'approved': payload['selectedMode'] != 'NO_TRADE',
            'rejectionReason': [] if payload['selectedMode'] != 'NO_TRADE' else ['NO_TRADE market state'],
            'blockedModes': payload['blockedModes'],
            'scoreGap': payload['scoreGap'],
        }
        state.market_router_events.append(event)
        limit = max(100, int(getattr(config, 'MARKET_ROUTER_EVENT_LIMIT', 2000) or 2000))
        if len(state.market_router_events) > limit:
            state.market_router_events = state.market_router_events[-limit:]
    return payload


def router_allows_mode(route, strategy_name):
    selected = str((route or {}).get('selectedMode') or 'NO_TRADE')
    if selected == 'NO_TRADE':
        return False, 'market router selected NO_TRADE'
    if selected != strategy_name:
        return False, f"market owner is {selected}; {strategy_name} blocked"
    return True, ''
