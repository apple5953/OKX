import datetime

OKX_API_KEY = 'f1b9af15-e584-4911-b949-ff42168fd53c'
OKX_SECRET = 'A64C98D3C5E8B38A963566313BA31EF1'
OKX_PASSWORD = '@Sweetsweet556'

BASE_MARGIN_USDT = 60.0
STRATEGY_VERSION = 'netmode-align-v9-20260705'
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
MFE_BE_R = 0.08
MFE_LOCK_R = 0.20
MFE_RUNNER_R = 0.45
MFE_BE_LOCK_R = 0.06
MFE_LOCK_FRACTION = 0.30
MFE_TRAIL_GIVEBACK_R = 0.10
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

NODE_NAME = 'macmini_01'
TRADE_FILE = f'active_trades_{NODE_NAME}.json'
JOURNAL_FILE = f'journal_{NODE_NAME}.json'

LOCAL_MARKET_SNAPSHOT_PATH = '../auto-trader-swap/state/market-snapshot.json'
LOCAL_ACCOUNT_SNAPSHOT_PATHS = ['api_dump.json', 'api_output.json']

STRATEGY_PROFILES = {
    'MacroSniper': {
        'label': 'Macro Sniper',
        'role': '1h/4h trend rider. Fewer entries, larger runner target.',
        'margin_mult': 1.10,
        'sl_atr': 1.6,
        'tp_atr': 6.0,
        'min_rr': 0.8,
        'be_threshold': 0.14,
        'lock_threshold': 0.30,
        'trail_buffer': 0.10,
        'remove_tp_at': 0.60,
    },
    'MeanReversion': {
        'label': 'Mean Reversion',
        'role': 'Fast oversold/overbought repair. Smaller target, fast lock.',
        'margin_mult': 0.95,
        'sl_atr': 1.4,
        'tp_atr': 2.2,
        'min_rr': 0.7,
        'be_threshold': 0.12,
        'lock_threshold': 0.28,
        'trail_buffer': 0.09,
        'remove_tp_at': 0.80,
    },
    'Contrarian': {
        'label': 'Contrarian',
        'role': 'Extreme reversal hunter. Wider stop, needs exhaustion proof.',
        'margin_mult': 0.85,
        'sl_atr': 2.0,
        'tp_atr': 3.4,
        'min_rr': 0.85,
        'be_threshold': 0.14,
        'lock_threshold': 0.32,
        'trail_buffer': 0.11,
        'remove_tp_at': 0.70,
    },
    'SqueezeHunter': {
        'label': 'Squeeze Hunter',
        'role': 'Volatility expansion hunter. Requires fresh squeeze release and confirmed breakout.',
        'margin_mult': 1.00,
        'sl_atr': 1.5,
        'tp_atr': 3.5,
        'min_rr': 1.05,
        'be_threshold': 0.12,
        'lock_threshold': 0.26,
        'trail_buffer': 0.08,
        'remove_tp_at': 0.55,
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
        'explore': {'sl_cap': 0.0250, 'tp_cap': 0.0950, 'rr_floor': 1.35},
        'train': {'sl_cap': 0.0220, 'tp_cap': 0.0800, 'rr_floor': 1.25},
        'recover': {'sl_cap': 0.0180, 'tp_cap': 0.0650, 'rr_floor': 1.15},
    },
    'MeanReversion': {
        'explore': {'sl_cap': 0.0180, 'tp_cap': 0.0650, 'rr_floor': 1.30},
        'train': {'sl_cap': 0.0160, 'tp_cap': 0.0500, 'rr_floor': 1.20},
        'recover': {'sl_cap': 0.0140, 'tp_cap': 0.0450, 'rr_floor': 1.10},
    },
    'Contrarian': {
        'explore': {'sl_cap': 0.0220, 'tp_cap': 0.0750, 'rr_floor': 1.35},
        'train': {'sl_cap': 0.0180, 'tp_cap': 0.0600, 'rr_floor': 1.25},
        'recover': {'sl_cap': 0.0160, 'tp_cap': 0.0500, 'rr_floor': 1.15},
    },
    'SqueezeHunter': {
        'explore': {'sl_cap': 0.0200, 'tp_cap': 0.0700, 'rr_floor': 1.40},
        'train': {'sl_cap': 0.0180, 'tp_cap': 0.0550, 'rr_floor': 1.25},
        'recover': {'sl_cap': 0.0160, 'tp_cap': 0.0450, 'rr_floor': 1.15},
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
