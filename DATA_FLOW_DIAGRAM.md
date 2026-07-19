# Data Flow Diagram

Audit date: 2026-07-18

This document describes the current real code path and the recommended target path for the requested short-scalp optimization system.

## Current Runtime Flow

```mermaid
flowchart TD
    A["OKX USDT swap tickers"] --> B["Universe Scanner<br/>top quoteVolume symbols"]
    B --> C["Category Classifier<br/>Majors, Alpha, Oversold, Volatility, Squeeze, High Volume"]
    C --> D["Strategy Loop<br/>MacroSniper / MeanReversion / Contrarian / SqueezeHunter"]
    D --> E["MTF Trend Context<br/>15m, 1h, 4h, 1d EMA50/EMA200"]
    E --> F["Market Router<br/>score TREND / MEAN_REVERSION / EXTREME_REVERSAL / SQUEEZE_BREAKOUT / NO_TRADE"]
    F --> G{"Mode owns symbol?"}
    G -- "No" --> H["Radar blocked candidate<br/>owner shown, mode blocked"]
    G -- "Yes" --> I["Setup Generation<br/>harmonic scan + direct mode setup"]
    I --> J["Entry Gates<br/>PRZ, HTF trend, mode gate, profit room, true RR"]
    J --> K{"Live allowed?"}
    K -- "No" --> L["Potential signal / blocked reason"]
    K -- "Yes" --> M["Risk Sizing<br/>PF, win rate, sample, category, optimizer"]
    M --> N["Execution Cost Gate<br/>fees, slippage, expected net edge"]
    N --> O{"Protection safety clear?"}
    O -- "No" --> P["Safety pause<br/>unverified TP/SL blocks new entries"]
    O -- "Yes" --> Q["Bounded Limit Entry<br/>no market chase"]
    Q --> R{"Filled?"}
    R -- "No" --> S["Retry next scan"]
    R -- "Yes" --> T["Exact Fill TP/SL Protection"]
    T --> U{"Protection verified?"}
    U -- "No" --> V["Emergency close or halt"]
    U -- "Yes" --> W["Active Trade Lifecycle"]
    W --> X["Trailing / BE / lock / partial logic"]
    X --> Y["Journal / Performance Store"]
    Y --> Z["Optimizer and UI metrics"]
```

## Current Market Router Flow

```mermaid
flowchart TD
    A["Closed candles + category + MTF trends"] --> B["Feature extraction"]
    B --> C["ADX / ADX slope"]
    B --> D["RSI pressure"]
    B --> E["Bollinger width / squeeze recent"]
    B --> F["Volume ratio"]
    B --> G["Reversal wick ratio"]
    B --> H["Trend alignment score"]
    C --> I["TREND score"]
    H --> I
    C --> J["MEAN_REVERSION score"]
    D --> J
    E --> K["SQUEEZE_BREAKOUT score"]
    F --> K
    D --> L["EXTREME_REVERSAL score"]
    G --> L
    I --> M["Rank states"]
    J --> M
    K --> M
    L --> M
    M --> N{"Confidence and score gap pass?"}
    N -- "No" --> O["NO_TRADE"]
    N -- "Yes" --> P["Assign activeModeOwner"]
    P --> Q["Cache ownership TTL"]
    Q --> R["Block non-owner modes"]
```

## Current Four-Mode Assignment

| Market state | Owner mode | Main purpose |
| --- | --- | --- |
| TREND | MacroSniper | Trend pullback and continuation |
| MEAN_REVERSION | MeanReversion | Range snapback and Bollinger re-entry |
| EXTREME_REVERSAL | Contrarian | Exhaustion reversal with proof |
| SQUEEZE_BREAKOUT | SqueezeHunter | Volatility compression release |
| NO_TRADE | none | Weak, ambiguous, or unsafe context |

## Target Phase 2-7 Flow

The requested target architecture should add observability and replayable short-scalp components without bypassing the current safety layer.

```mermaid
flowchart TD
    A["Universe Scanner"] --> B["Category Classifier"]
    B --> C["Market Context Router"]
    C --> D["Market Ownership Controller"]
    D --> E["Setup Permission Controller"]
    E --> F["ShortScalpEngine<br/>1m / 3m / 5m shadow candidates"]
    F --> G["Setup Ranker<br/>quality score buckets"]
    G --> H["Execution Cost Gate<br/>bps cost model"]
    H --> I["Dynamic Risk Sizing"]
    I --> J["ShadowTrader"]
    J --> K["FastExitManager simulation"]
    K --> L["Performance Store"]
    L --> M["Replay Engine"]
    M --> N["Optimizer Agent"]
    N --> O["Setup Performance Router"]
    O --> E
```

## Target Candidate Lifecycle

```mermaid
stateDiagram-v2
    [*] --> RAW_CANDIDATE
    RAW_CANDIDATE --> HARD_BLOCKED
    RAW_CANDIDATE --> SCORED_CANDIDATE
    SCORED_CANDIDATE --> SHADOW_ONLY
    SCORED_CANDIDATE --> LIVE_ELIGIBLE
    LIVE_ELIGIBLE --> REJECTED_TRADE
    LIVE_ELIGIBLE --> EXECUTED_TRADE
    SHADOW_ONLY --> SHADOW_RESULT
    EXECUTED_TRADE --> ACTIVE_TRADE
    ACTIVE_TRADE --> CLOSED_TRADE
    ACTIVE_TRADE --> EMERGENCY_CLOSED
    CLOSED_TRADE --> PERFORMANCE_STORE
    SHADOW_RESULT --> PERFORMANCE_STORE
    REJECTED_TRADE --> PERFORMANCE_STORE
    HARD_BLOCKED --> PERFORMANCE_STORE
```

## Required Event IDs

The target flow should persist these IDs for every candidate/trade:

- `market_event_id`: the market router scoring event.
- `setup_event_id`: the setup candidate event.
- `trade_event_id`: the live or shadow trade event.
- `lifecycle_id`: the current net lifecycle record already used by the engine.

## Phase 2 Minimal Event Schema

```json
{
  "event_id": "uuid",
  "timestamp": "2026-07-18T00:00:00Z",
  "symbol": "SOL-USDT-SWAP",
  "mode": "MacroSniper",
  "market_state": "TREND",
  "market_owner": "MacroSniper",
  "setup_type": "TREND_PULLBACK",
  "direction": "LONG",
  "candidate_state": "BLOCKED",
  "reason_code": "TRUE_RR_TOO_LOW",
  "quality_score": 61.5,
  "expected_move_bps": 18.2,
  "estimated_cost_bps": 9.1,
  "net_edge_bps": 9.1,
  "feature_snapshot": {}
}
```

## Critical No-Future-Leak Rule

The current scanner often uses `signal_df = df.iloc[:-1]` before generating candidates. Any replay or short-scalp module must keep this rule explicit:

- Never use an unfinished candle for signal confirmation.
- Market context should be derived from candles closed before the candidate timestamp.
- Execution simulation may use post-signal ticks/candles only after the signal timestamp.

