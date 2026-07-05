import os
from flask import Flask, jsonify, send_from_directory
from . import state
from . import config
from .utils import as_float, timestamp_ms, json_safe
from .okx_client import sync_exchange_history, capital_snapshot, okx, load_local_account_snapshot
from .strategies import all_strategy_performance, recent_strategy_stats, get_btc_market_regime, auto_tune_strategy_params, build_bot_report
from .engine import build_live_trade_snapshot, fetch_live_okx_positions, collapse_active_records

app = Flask(__name__, static_folder='../ui')

def serve_ui():
    return send_from_directory('../ui', 'index.html')

@app.route('/')
def serve_root():
    return serve_ui()

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../ui', path)

# --- BACKGROUND SYNC DAEMON INIT ---
state.account_data = load_local_account_snapshot() or {'totalEq': 0.0, 'usdtEq': 0.0, 'usdtAvail': 0.0, 'source': 'init'}

@app.route('/api/trades')
def api_trades():
    # Fetch real-time tickers for potential signals only (Lightweight)
    if state.potential_signals:
        symbols_to_fetch = [t['symbol'] + "/USDT:USDT" for t in state.potential_signals]
        try:
            tickers = okx.fetch_tickers(symbols_to_fetch)
            for t in state.potential_signals:
                sym = t['symbol'] + "/USDT:USDT"
                if sym in tickers and tickers[sym].get('last'):
                    t['current'] = float(tickers[sym]['last'])
        except Exception:
            pass
            
    live_positions = fetch_live_okx_positions()
    visible_trades = build_live_trade_snapshot(
        tracked_records=collapse_active_records(state.active_trades),
        live_positions=live_positions,
        include_potentials=True,
    )
    visible_trades = [t for t in visible_trades if t.get('symbol')]
                    
    try:
        return jsonify(json_safe({
            'trades': visible_trades,
            'live_positions': live_positions,
            'radar': state.market_radar_dict,
            'regime': get_btc_market_regime(),
            'account': state.account_data,
            'profiles': config.STRATEGY_PROFILES,
            'strategy_stats': {name: recent_strategy_stats(name) for name in config.STRATEGY_PROFILES},
            'performance': all_strategy_performance(),
            'optimizer': {name: auto_tune_strategy_params(name) for name in config.STRATEGY_PROFILES},
            'ml_logs': state.ml_evolution_logs,
            'report': build_bot_report(visible_trades, live_positions=live_positions),
            'strategy_version': config.STRATEGY_VERSION,
        }))
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[api_trades ERROR] {err}")
        return jsonify(json_safe({'error': str(e), 'trades': visible_trades, 'radar': {}, 'account': state.account_data, 'profiles': {}, 'strategy_stats': {}, 'performance': {}})), 200

@app.route('/api/report')
def api_report():
    live_positions = fetch_live_okx_positions()
    visible_trades = [t for t in build_live_trade_snapshot(
        tracked_records=collapse_active_records(state.active_trades),
        live_positions=live_positions,
        include_potentials=True,
    ) if t.get('symbol')]
    return jsonify(json_safe({'report': build_bot_report(visible_trades, live_positions=live_positions), 'live_positions': live_positions}))

@app.route('/api/history')
def api_history():
    try:
        hist = sync_exchange_history(force=True)
        return jsonify(json_safe({
            'history': hist[:config.EXCHANGE_HISTORY_LIMIT],
            'source': 'okx_realized',
            'synced_at': state.exchange_history_synced_at,
            'error': state.exchange_history_error,
        }))
    except Exception as e:
        print(f"History Sync Error: {e}")
        return jsonify({'history': [], 'source': 'okx_realized', 'error': str(e)})

@app.route('/api/journal')
def api_journal():
    return jsonify(json_safe({'journal': state.trade_journal}))

@app.route('/api/performance')
def api_performance():
    return jsonify(json_safe({
        'performance': all_strategy_performance(),
        'optimizer': {name: auto_tune_strategy_params(name) for name in config.STRATEGY_PROFILES},
    }))

@app.route('/api/intelligence')
def api_intelligence():
    # ML intelligence dashboard API
    perf = all_strategy_performance()
    tuned = {name: auto_tune_strategy_params(name, perf[name]) for name in config.STRATEGY_PROFILES}
    
    # Calculate total portfolio stats
    total_trades = sum(p['total_trades'] for p in perf.values())
    total_wins = sum(p['win_count'] for p in perf.values())
    total_losses = sum(p['loss_count'] for p in perf.values())
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    
    total_pnl = sum(p['total_pnl'] for p in perf.values())
    
    return jsonify(json_safe({
        'performance': perf,
        'tuning': tuned,
        'summary': {
            'total_trades': total_trades,
            'win_rate': round(win_rate, 2),
            'win_count': total_wins,
            'loss_count': total_losses,
            'total_pnl': round(total_pnl, 4),
            'market_regime': get_btc_market_regime()
        },
        'logs': state.ml_evolution_logs
    }))
