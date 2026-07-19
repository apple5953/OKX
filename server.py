import json
import os
import sys
import time
import threading
from server_core import config, state, utils, okx_client, strategies, execution, engine, web_server

def _load_state_from_disk():
    # Keep import-time state reads lightweight; zero-start happens only from the
    # real app entrypoint so tests and helpers do not accidentally wipe files.
    state.active_trades = utils.load_json_list(config.TRADE_FILE, 'active trades')
    if not os.path.exists(config.TRADE_FILE):
        try:
            utils.write_json_atomic(config.TRADE_FILE, state.active_trades)
        except Exception as e:
            print(f"Failed to initialize active trades file {config.TRADE_FILE}: {e}")

    state.trade_journal = utils.load_json_list(config.JOURNAL_FILE, 'journal file')
    if not os.path.exists(config.JOURNAL_FILE):
        try:
            utils.write_json_atomic(config.JOURNAL_FILE, state.trade_journal)
        except Exception as e:
            print(f"Failed to initialize journal file {config.JOURNAL_FILE}: {e}")

    state.trade_id_counter = max([t['id'] for t in state.active_trades], default=0) + 1

    # Rebuild protection metadata from journal rows so restarts do not drop TP/SL state.
    try:
        if engine.reconcile_active_trades_with_journal(write_back=True):
            state.trade_id_counter = max([t['id'] for t in state.active_trades], default=0) + 1
    except Exception as reconcile_err:
        print(f"[Startup] Failed to reconcile active trades with journal: {reconcile_err}")


# Load existing state for import-time compatibility.
_load_state_from_disk()

# Re-export variables for compatibility with tests & external scripts
active_trades = state.active_trades
trade_journal = state.trade_journal
reserved_symbols = state.reserved_symbols
STRATEGY_VERSION = config.STRATEGY_VERSION
ROUND_TRIP_TAKER_RATE = config.ROUND_TRIP_TAKER_RATE
MAX_PLANNED_LOSS_USDT = config.MAX_PLANNED_LOSS_USDT
okx = okx_client.okx

# Re-export functions for compatibility with tests & external scripts
build_direct_mode_setup = strategies.build_direct_mode_setup
risk_based_leverage_cap = execution.risk_based_leverage_cap
apply_adaptive_exits = strategies.apply_adaptive_exits
merge_active_trade = engine.merge_active_trade
is_crypto_usdt_swap = okx_client.is_crypto_usdt_swap
reserve_symbol_for_entry = engine.reserve_symbol_for_entry
release_symbol_reservation = engine.release_symbol_reservation
expected_trade_edge = execution.expected_trade_edge
evaluate_mode_gate = strategies.evaluate_mode_gate
strategy_performance = strategies.strategy_performance
lifecycle_trade_for_history = utils.lifecycle_trade_for_history
assess_accounting_record = utils.assess_accounting_record
protective_algo_targets = execution.protective_algo_targets
okx_algo_amend_error = execution.okx_algo_amend_error
amend_protective_stop = execution.amend_protective_stop
timestamp_ms = utils.timestamp_ms
get_btc_market_regime = strategies.get_btc_market_regime
realized_strategy_rows = okx_client.realized_strategy_rows

# Intercept module attribute writes to keep state.active_trades synced when reassigned in tests
class ServerModuleWrapper(object):
    def __init__(self, wrapped):
        self.wrapped = wrapped
    def __getattr__(self, name):
        if name == 'active_trades':
            return state.active_trades
        if name == 'trade_journal':
            return state.trade_journal
        if name == 'reserved_symbols':
            return state.reserved_symbols
        if name == 'realized_strategy_rows':
            return okx_client.realized_strategy_rows
        return getattr(self.wrapped, name)
    def __setattr__(self, name, value):
        if name == 'active_trades':
            state.active_trades = value
        elif name == 'trade_journal':
            state.trade_journal = value
        elif name == 'reserved_symbols':
            state.reserved_symbols = value
        else:
            object.__setattr__(self, name, value)

if __name__ == '__main__':
    # V13 zero-start bootstrap: back up polluted history and start each generation from a clean local state.
    utils.ensure_zero_start_storage()
    _load_state_from_disk()

    # Initialize scanner symbols
    state.global_symbols, state.global_symbol_categories = okx_client.get_top_symbols_and_categories()
    
    # Try to acquire instance lock (soft guard — won't kill process if already occupied)
    try:
        utils.acquire_instance_guard(5017)
    except Exception as e:
        print(f"[Warning] Instance guard port 5017 unavailable ({e}); continuing anyway (managed by auto_restart.py)")
        
    def update_symbols_loop():
        while True:
            time.sleep(int(getattr(config, 'MARKET_UNIVERSE_REFRESH_SECONDS', 3600) or 3600))
            try:
                new_symbols, new_cats = okx_client.get_top_symbols_and_categories()
                if new_symbols and len(new_symbols) > 0:
                    state.global_symbols = new_symbols
                    state.global_symbol_categories = new_cats
                    print(
                        f"[Intelligence] Refreshed top {len(new_symbols)} high-liquidity markets "
                        f"from {getattr(state, 'market_universe_source', 'unknown')}."
                    )
            except Exception:
                pass
                
    # Start Cloud Session Heartbeat Tracker to record login times and device session runtimes
    email_addr = "unknown"
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_token.json")
    if os.path.exists(token_path):
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                email_addr = json.load(f).get("email", "unknown")
        except Exception:
            pass

    class CloudSessionTracker:
        def __init__(self, node_name, email):
            self.node_name = node_name
            self.email = email
            self.gas_url = "https://script.google.com/macros/s/AKfycbwd75y2vsmgA7g0AtNxqiCSLkqT4Ied1n-nV5JpOy__gM3bB8pWqNw6PZiyWpbrNeSjqg/exec"

        def send_status(self, status="active"):
            def run():
                usdt_equity = float(state.account_data.get('usdtEq', 0.0))
                usdt_avail = float(state.account_data.get('usdtAvail', 0.0))
                payload = {
                    "action": "log_session",
                    "node_name": self.node_name,
                    "email": self.email,
                    "status": status,
                    "usdt_equity": usdt_equity,
                    "usdt_avail": usdt_avail
                }
                try:
                    req = urllib.request.Request(
                        self.gas_url,
                        data=json.dumps(payload).encode('utf-8'),
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    urllib.request.urlopen(req)
                except Exception:
                    pass
            threading.Thread(target=run, daemon=True).start()

        def start_heartbeat_loop(self):
            self.send_status("active")
            def loop():
                while True:
                    time.sleep(300)  # Heartbeat every 5 minutes
                    self.send_status("active")
            threading.Thread(target=loop, daemon=True).start()

    import urllib.request
    import json
    tracker = CloudSessionTracker(config.NODE_NAME, email_addr)
    tracker.start_heartbeat_loop()

    threading.Thread(target=update_symbols_loop, daemon=True).start()
    threading.Thread(target=engine.background_sync_loop, daemon=True).start()
    threading.Thread(target=strategies.training_loop, kwargs={'interval_seconds': 600}, daemon=True).start()
    
    # Start 4 Strategy Threads with High-Win Rate Trend-Following Parameters
    t1 = threading.Thread(target=engine.run_strategy, args=('MacroSniper', '15m', 0.14, 0.012, '1h', 0.45), daemon=True)
    t2 = threading.Thread(target=engine.run_strategy, args=('MeanReversion', '5m', 0.10, 0.015, '15m', 0.2), daemon=True)
    t3 = threading.Thread(target=engine.run_strategy, args=('Contrarian', '5m', 0.10, 0.04, '15m', 0.2), daemon=True)
    t4 = threading.Thread(target=engine.run_strategy, args=('SqueezeHunter', '15m', 0.10, 0.03, '1h', 0.5), daemon=True)
    
    t1.start()
    t2.start()
    t3.start()
    t4.start()
    
    print("Server running on http://127.0.0.1:5000")
    print("Open your browser and navigate to the link above to view the Dashboard.")

    # Catch all unhandled exceptions in any thread so crashes are visible in log
    import traceback as _tb
    _original_excepthook = sys.excepthook
    def _global_excepthook(exc_type, exc_value, exc_tb):
        print("[CRASH] Unhandled exception in main thread:")
        _tb.print_exception(exc_type, exc_value, exc_tb)
        _original_excepthook(exc_type, exc_value, exc_tb)
    sys.excepthook = _global_excepthook

    try:
        web_server.app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as flask_err:
        print(f"[CRASH] Flask app.run() crashed: {flask_err}")
        import traceback as _tb2
        _tb2.print_exc()
        sys.exit(1)
else:
    sys.modules[__name__] = ServerModuleWrapper(sys.modules[__name__])
