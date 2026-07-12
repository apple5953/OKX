import datetime
import os
import re
import socket
import uuid
from pathlib import Path

try:
    import tomllib as _tomllib
except Exception:
    _tomllib = None

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent


def _sanitize_node_name(value):
    text = re.sub(r'[^A-Za-z0-9._-]+', '-', str(value or '').strip())
    return text.strip('.-_')


def _env_flag(name):
    return str(os.getenv(name, '')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _first_non_empty(*values):
    for value in values:
        text = str(value or '').strip()
        if text:
            return text
    return ''


def _float_env(name, default):
    raw = _first_non_empty(os.getenv(name))
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _int_env(name, default):
    raw = _first_non_empty(os.getenv(name))
    if not raw:
        return int(default)
    try:
        return int(float(raw))
    except ValueError:
        return int(default)


def load_okx_profile_config():
    candidate_paths = []
    env_path = _first_non_empty(os.getenv('OKX_CONFIG_PATH'), os.getenv('OKX_CONFIG_TOML'))
    if env_path:
        candidate_paths.append(Path(env_path).expanduser())
    candidate_paths.append(Path.home() / '.okx' / 'config.toml')

    for path in candidate_paths:
        if not path.exists() or _tomllib is None:
            continue
        try:
            with open(path, 'rb') as f:
                payload = _tomllib.load(f)
        except Exception:
            continue

        profiles = payload.get('profiles') if isinstance(payload, dict) else None
        if not isinstance(profiles, dict) or not profiles:
            continue

        default_profile = _first_non_empty(payload.get('default_profile'))
        profile_name = default_profile if default_profile in profiles else next(iter(profiles.keys()))
        profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else None
        if not isinstance(profile, dict):
            continue

        return {
            'path': str(path),
            'profile_name': profile_name,
            'api_key': _first_non_empty(profile.get('api_key'), profile.get('apiKey')),
            'secret': _first_non_empty(profile.get('secret_key'), profile.get('secret'), profile.get('api_secret')),
            'password': _first_non_empty(profile.get('passphrase'), profile.get('password')),
            'demo': bool(profile.get('demo')),
            'site': _first_non_empty(profile.get('site'), payload.get('site'), 'global'),
        }

    return {}


OKX_PROFILE = load_okx_profile_config()


def resolve_run_mode():
    raw = str(os.getenv('OKX_RUN_MODE') or os.getenv('RUN_MODE') or 'auto').strip().lower()
    if raw in {'mock', 'simulate', 'simulation', 'paper'}:
        return 'mock'
    if raw in {'demo', 'sandbox', 'testnet'}:
        return 'demo'
    if raw in {'live', 'real', 'production'}:
        return 'live'
    if OKX_PROFILE.get('demo'):
        return 'demo'
    return 'auto'


def resolve_node_name():
    explicit = _sanitize_node_name(os.getenv('OKX_NODE_NAME') or os.getenv('NODE_NAME'))
    if explicit:
        return explicit

    hostname = _sanitize_node_name(socket.gethostname()).lower()
    if hostname:
        suffix = f'{uuid.getnode():012x}'[-6:]
        return f'{hostname}-{suffix}'

    return f'node-{uuid.getnode():012x}'

OKX_API_KEY = _first_non_empty(os.getenv('OKX_API_KEY'), OKX_PROFILE.get('api_key'))
OKX_SECRET = _first_non_empty(os.getenv('OKX_API_SECRET'), os.getenv('OKX_SECRET'), OKX_PROFILE.get('secret'))
OKX_PASSWORD = _first_non_empty(os.getenv('OKX_PASSPHRASE'), os.getenv('OKX_PASSWORD'), OKX_PROFILE.get('password'))
OKX_SITE = _first_non_empty(os.getenv('OKX_SITE'), OKX_PROFILE.get('site'))
RUN_MODE = resolve_run_mode()
MOCK_MODE = RUN_MODE == 'mock' or _env_flag('OKX_FORCE_MOCK') or _env_flag('OKX_SIMULATION_MODE')
DEMO_MODE = RUN_MODE == 'demo'
LIVE_MODE = RUN_MODE == 'live'
OKX_SANDBOX_MODE = DEMO_MODE or _env_flag('OKX_FORCE_SANDBOX') or bool(OKX_PROFILE.get('demo'))

# 本地模擬交易模式 (MOCK_MODE): 
# 若為 True，或 API 金鑰留空/無效時，機器人會轉為「本地虛擬開平倉」，不發送真實訂單到 OKX，專門用於無白名單權限的電腦進行訓練。

BASE_MARGIN_USDT = 60.0
STRATEGY_VERSION = 'v13'
ALLOW_LEGACY_LEARNING = _env_flag('OKX_ALLOW_LEGACY_LEARNING')
ZERO_START_MODE = not _env_flag('OKX_DISABLE_ZERO_START')
START_EQUITY_USDT = 5000.0
TARGET_EQUITY_USDT = 10000.0
SESSION_STARTED_AT = datetime.datetime.now().isoformat(timespec='seconds')
SESSION_START_EQUITY_USDT = None
EXCHANGE_HISTORY_LIMIT = 100
EXCHANGE_HISTORY_TTL_SECONDS = 20
MAX_CONFIDENCE_MARGIN_USDT = 150.0
MIN_CONFIDENCE_MARGIN_USDT = 20.0
REHAB_MARGIN_USDT = 20.0
LOSS_FIREWALL_MARGIN_USDT = 20.0
EXPLORE_MARGIN_USDT = 20.0
CORE_MAX_MARGIN_USDT = 120.0
base_leverages = [75, 50, 30, 20, 10, 5, 2, 1]
EXPLOIT_MAX_MARGIN_USDT = 150.0
REHAB_RR_MULTIPLIER = 1.0
REHAB_PROFIT_MULTIPLIER = 0.5
REHAB_COOLDOWN_MULTIPLIER = 0.25
MAX_LEVERAGE_CAP = 75
CORE_TRADE_MIN_SAMPLE = 30
CORE_TRADE_MIN_PROFIT_FACTOR = 1.05
CORE_TRADE_MIN_EXPECTANCY = 0.0
PROFIT_FIRST_MODE = True
PROFIT_FIRST_MIN_ROOM_FLOOR = 0.0025
PROFIT_FIRST_MIN_ROOM_BY_TIMEFRAME = {
    '5m': 0.0015,
    '15m': 0.0025,
    '1h': 0.0035,
    '4h': 0.0045,
}
MFE_BE_R = 0.15       # 提高保本觸發 R 值 (舊值: 0.08)
MFE_LOCK_R = 0.35     # 提高保利觸發 R 值 (舊值: 0.20)
MFE_RUNNER_R = 0.60   # 提高鎖死追隨 R 值 (舊值: 0.45)
MFE_BE_LOCK_R = 0.10  # 鎖定 R 值
MFE_LOCK_FRACTION = 0.40 # 鎖利回吐保護分位數 (舊值: 0.30)
MFE_TRAIL_GIVEBACK_R = 0.15 # 給予回吐 R 值 (舊值: 0.10)
ROUND_TRIP_TAKER_RATE = 0.0010
SLIPPAGE_BUFFER_RATE = 0.00025
FEE_SAFE_PROFIT_RATE = ROUND_TRIP_TAKER_RATE + SLIPPAGE_BUFFER_RATE
MAX_PLANNED_LOSS_USDT = 18.0
MAX_ACCEPTABLE_SPREAD_PCT = 0.0030
MIN_EXPECTED_NET_PROFIT_USDT = 2.0
MIN_GROSS_TO_COST_RATIO = 2.0
LIFECYCLE_OPEN_TOLERANCE_MS = 15 * 60 * 1000
ACCOUNTING_LOSS_QUARANTINE_MULTIPLIER = 3.0
ACCOUNTING_STOP_OVERSHOOT_MULTIPLIER = 6.0
ACCOUNTING_MIN_ADVERSE_MOVE_PCT = 0.05
PROTECTION_RETRY_BASE_SECONDS = 5
PROTECTION_RETRY_MAX_SECONDS = 60
PROTECTION_MISSING_CONFIRMATIONS = 3
ORPHAN_BYPASS_ENABLED = True
ORPHAN_BYPASS_SYMBOLS = {
    'BLUAI-USDT-SWAP',
}
ORPHAN_ASKLESS_CONFIRMATIONS = 3
ORPHAN_ORDERBOOK_LIMIT = 5

NON_CRYPTO_BASES = {
    'USDC', 'USDE', 'USDG', 'FDUSD', 'TUSD', 'DAI', 'PYUSD',
    'XAU', 'XAG', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF',
}

FALLBACK_SCAN_SYMBOLS = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
    'BNB/USDT:USDT', 'ADA/USDT:USDT', 'DOGE/USDT:USDT', 'AVAX/USDT:USDT',
    'LINK/USDT:USDT', 'LTC/USDT:USDT', 'BCH/USDT:USDT', 'TRX/USDT:USDT',
    'NEAR/USDT:USDT', 'UNI/USDT:USDT', 'DOT/USDT:USDT', 'SHIB/USDT:USDT',
]

MARKET_DATA_MIN_INTERVAL_SECONDS = 0.18
MARKET_DATA_TTL_SECONDS = {
    '5m': 15,
    '15m': 30,
    '1h': 180,
    '4h': 600,
    '1d': 1800,
}

NODE_NAME = resolve_node_name()
TRADE_FILE = str(PROJECT_DIR / f'active_trades_{NODE_NAME}.json')
JOURNAL_FILE = str(PROJECT_DIR / f'journal_{NODE_NAME}.json')
ZERO_START_STATE_FILE = str(PROJECT_DIR / f'zero_start_state_{NODE_NAME}.json')
GLOBAL_OPTIMIZER_FILE = str(PROJECT_DIR / 'global_optimizer.json')
TRAINING_CYCLE_STATE_FILE = str(PROJECT_DIR / 'optimization_cycle_state.json')
LEGACY_TRADE_FILE = str(PROJECT_DIR / 'active_trades.json')
LEGACY_JOURNAL_FILE = str(PROJECT_DIR / 'trade_journal.json')

LOCAL_MARKET_SNAPSHOT_PATH = str(WORKSPACE_DIR / 'auto-trader-swap' / 'state' / 'market-snapshot.json')
LOCAL_LIVE_SNAPSHOT_PATH = str(PROJECT_DIR / 'state' / 'okx_live_snapshot.json')
LOCAL_POSITIONS_SNAPSHOT_PATHS = [
    LOCAL_LIVE_SNAPSHOT_PATH,
    str(PROJECT_DIR / 'state' / 'okx_live_positions_snapshot.json'),
]
LOCAL_ACCOUNT_SNAPSHOT_PATHS = [
    LOCAL_LIVE_SNAPSHOT_PATH,
    str(PROJECT_DIR / 'api_dump.json'),
    str(PROJECT_DIR / 'api_output.json'),
]

STRATEGY_PROFILES = {
    'MacroSniper': {
        'label': 'Macro Sniper',
        'role': '1h/4h trend rider. Fewer entries, larger runner target.',
        'margin_mult': 1.10,
        'sl_atr': 1.2,         # 稍收緊，1.5% ATR -> 1.8%
        'tp_atr': 3.5,         # 下調，1.5% ATR -> 5.2% 止盈
        'min_rr': 1.40,        # 務實盈虧比
        'be_threshold': 0.20,  # 提高成本保護門檻，給波動空間 (舊值: 0.16)
        'lock_threshold': 0.45, # 提高保利鎖定門檻，避免回調甩下車 (舊值: 0.35)
        'trail_buffer': 0.15,  # 增加追蹤回吐容忍緩衝區 (舊值: 0.10)
        'remove_tp_at': 0.50,
    },
    'MeanReversion': {
        'label': 'Mean Reversion',
        'role': 'Fast oversold/overbought repair. Smaller target, fast lock.',
        'margin_mult': 0.95,
        'sl_atr': 0.8,         # 快速認錯，1.5% ATR -> 1.2%
        'tp_atr': 1.4,         # 均值回歸快進快出，1.5% ATR -> 2.1% 止盈
        'min_rr': 1.05,
        'be_threshold': 0.08,  # (舊值: 0.05)
        'lock_threshold': 0.20, # (舊值: 0.15)
        'trail_buffer': 0.08,  # (舊值: 0.05)
        'remove_tp_at': 0.95,
    },
    'Contrarian': {
        'label': 'Contrarian',
        'role': 'Extreme reversal hunter. Wider stop, needs exhaustion proof.',
        'margin_mult': 0.85,
        'sl_atr': 1.1,         # 配合精準極端 RSI, 1.5% ATR -> 1.65%
        'tp_atr': 2.6,         # 反彈波段，1.5% ATR -> 3.9% 止盈
        'min_rr': 1.30,
        'be_threshold': 0.15,  # (舊值: 0.10)
        'lock_threshold': 0.35, # (舊值: 0.28)
        'trail_buffer': 0.12,  # (舊值: 0.08)
        'remove_tp_at': 0.60,
    },
    'SqueezeHunter': {
        'label': 'Squeeze Hunter',
        'role': 'Volatility expansion hunter. Requires fresh squeeze release and confirmed breakout.',
        'margin_mult': 1.00,
        'sl_atr': 1.1,         # 突破不回頭，1.5% ATR -> 1.65%
        'tp_atr': 3.0,         # 追突破吃波段，1.5% ATR -> 4.5% 止盈
        'min_rr': 1.25,
        'be_threshold': 0.15,  # (舊值: 0.10)
        'lock_threshold': 0.32, # (舊值: 0.24)
        'trail_buffer': 0.12,  # (舊值: 0.08)
        'remove_tp_at': 0.45,
    },
}

MODE_TRAINING_PROFILES = {
    'MacroSniper': {
        'pressure_scale': 1.15,
        'positive_relief': 0.02,
        'rr_expand': 0.24,
        'profit_expand': 0.18,
        'cooldown_expand': 0.18,
        'tolerance_shrink': 0.20,
        'min_rr_expand': 0.20,
        'edge_boost': 0.30,
        'slippage_edge_factor': 18.0,
        'sample_penalty': 0.06,
        'min_sample_floor': 30,
    },
    'MeanReversion': {
        'pressure_scale': 0.72,
        'positive_relief': 0.16,
        'rr_expand': 0.08,
        'profit_expand': 0.06,
        'cooldown_expand': 0.08,
        'tolerance_shrink': 0.08,
        'min_rr_expand': 0.10,
        'edge_boost': 0.12,
        'slippage_edge_factor': 10.0,
        'sample_penalty': 0.00,
        'min_sample_floor': 20,
    },
    'Contrarian': {
        'pressure_scale': 0.92,
        'positive_relief': 0.05,
        'rr_expand': 0.16,
        'profit_expand': 0.10,
        'cooldown_expand': 0.14,
        'tolerance_shrink': 0.14,
        'min_rr_expand': 0.18,
        'edge_boost': 0.20,
        'slippage_edge_factor': 14.0,
        'sample_penalty': 0.03,
        'min_sample_floor': 25,
    },
    'SqueezeHunter': {
        'pressure_scale': 0.68,
        'positive_relief': 0.14,
        'rr_expand': 0.10,
        'profit_expand': 0.12,
        'cooldown_expand': 0.10,
        'tolerance_shrink': 0.10,
        'min_rr_expand': 0.12,
        'edge_boost': 0.14,
        'slippage_edge_factor': 12.0,
        'sample_penalty': 0.04,
        'min_sample_floor': 15,
    },
}

CATEGORY_PROFILES = {
    'Squeeze':    {'tolerance_mult': 1.20, 'sl_mult': 1.35, 'profit_mult': 1.8, 'margin_mult': 1.05},
    'Alpha':      {'tolerance_mult': 1.30, 'sl_mult': 1.15, 'profit_mult': 1.3, 'margin_mult': 1.10},
    'Oversold':   {'tolerance_mult': 1.10, 'sl_mult': 1.70, 'profit_mult': 1.4, 'margin_mult': 0.95},
    'Volatility': {'tolerance_mult': 1.15, 'sl_mult': 1.45, 'profit_mult': 1.2, 'margin_mult': 0.90},
    'Majors':     {'tolerance_mult': 1.50, 'sl_mult': 1.00, 'profit_mult': 1.0, 'margin_mult': 1.00},
    'Default':    {'tolerance_mult': 1.20, 'sl_mult': 1.15, 'profit_mult': 1.2, 'margin_mult': 0.90},
}

EXIT_STATE_LIMITS = {
    'MacroSniper': {
        'explore': {'sl_cap': 0.0250, 'tp_cap': 0.0600, 'rr_floor': 1.45},
        'train': {'sl_cap': 0.0220, 'tp_cap': 0.0500, 'rr_floor': 1.40},
        'recover': {'sl_cap': 0.0180, 'tp_cap': 0.0450, 'rr_floor': 1.30},
    },
    'MeanReversion': {
        'explore': {'sl_cap': 0.0180, 'tp_cap': 0.0300, 'rr_floor': 1.15},
        'train': {'sl_cap': 0.0160, 'tp_cap': 0.0250, 'rr_floor': 1.10},
        'recover': {'sl_cap': 0.0140, 'tp_cap': 0.0200, 'rr_floor': 1.05},
    },
    'Contrarian': {
        'explore': {'sl_cap': 0.0220, 'tp_cap': 0.0450, 'rr_floor': 1.35},
        'train': {'sl_cap': 0.0180, 'tp_cap': 0.0400, 'rr_floor': 1.30},
        'recover': {'sl_cap': 0.0160, 'tp_cap': 0.0350, 'rr_floor': 1.20},
    },
    'SqueezeHunter': {
        'explore': {'sl_cap': 0.0200, 'tp_cap': 0.0500, 'rr_floor': 1.30},
        'train': {'sl_cap': 0.0180, 'tp_cap': 0.0450, 'rr_floor': 1.25},
        'recover': {'sl_cap': 0.0160, 'tp_cap': 0.0400, 'rr_floor': 1.15},
    },
}

MIN_EXIT_DISTANCE_PCT = {
    'MacroSniper': 0.0050,
    'MeanReversion': 0.0035,
    'Contrarian': 0.0050,
    'SqueezeHunter': 0.0040,
}

MIN_TARGET_DISTANCE_PCT = {
    'MacroSniper': 0.0080,
    'MeanReversion': 0.0050,
    'Contrarian': 0.0060,
    'SqueezeHunter': 0.0060,
}
