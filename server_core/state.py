import threading

active_trades = []
trade_journal = []
exchange_history_cache = []
exchange_history_synced_at = 0.0
exchange_history_error = None
exchange_history_lock = threading.Lock()
execution_state_lock = threading.RLock()
entry_execution_lock = threading.Lock()
reserved_symbols = set()
safety_halt_reason = None
safety_halt_at = 0.0
global_symbol_cooldowns = {}
global_executed_signal_candles = {}
strategy_scan_cursors = {}
tuning_log_state = {}

market_data_cache = {}
market_data_lock = threading.Lock()
market_data_last_request_at = 0.0

positions_snapshot_cache = {
    'fetched_at': 0.0,
    'raw': [],
    'normalized': [],
}
positions_snapshot_lock = threading.Lock()
orphan_position_state = {}
orphan_position_lock = threading.Lock()

account_snapshot_cache = {
    'fetched_at': 0.0,
    'data': None,
}
account_snapshot_lock = threading.Lock()

local_market_snapshot_cache = {
    'fetched_at': 0.0,
    'data': {},
}
local_market_snapshot_lock = threading.Lock()

local_account_snapshot_cache = {
    'fetched_at': 0.0,
    'data': None,
    'source': '',
}
local_account_snapshot_lock = threading.Lock()

potential_signals = []
market_radar_dict = {
    'MacroSniper': [],
    'MeanReversion': [],
    'Contrarian': [],
    'SqueezeHunter': []
}
ml_evolution_logs = [
    "[AI 學習模組啟動] 正在加載歷史交易記錄以開始反省優化...",
    "[模型配置] 最小止損底限設定為 1.5% | 各模式最小盈虧比解鎖 (1.10 ~ 1.30x) 正在等待信號..."
]
trade_id_counter = 1

# Scanner symbols and categories
global_symbols = []
global_symbol_categories = {}
market_universe_source = 'init'
market_universe_updated_at = None
market_universe_refresh_seconds = 3600
market_universe_limit = 100
market_universe_error = None
strategy_radar_status = {}
market_router_cache = {}
market_mode_ownership = {}
market_router_events = []
market_router_lock = threading.RLock()
instance_guard_socket = None

# Current synced account data
account_data = None
