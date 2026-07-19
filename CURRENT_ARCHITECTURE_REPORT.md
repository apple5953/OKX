# Current Architecture Report

Audit date: 2026-07-18

Scope: Phase 1 read-only audit of the current OKX four-mode trading bot in `D:/okx/harmonic_agent`.

## Executive Summary

The current system already has a working four-mode market adaptation backbone:

- Universe scanner: loads OKX USDT swap symbols ranked by 24h quote volume.
- Category classifier: assigns symbols to Majors, Squeeze Watch, Alpha Relative Strength, Deep Oversold, High Volatility, or High Volume.
- Market context router: scores each symbol into TREND, MEAN_REVERSION, EXTREME_REVERSAL, SQUEEZE_BREAKOUT, or NO_TRADE.
- Ownership layer: assigns one active mode owner per symbol for a TTL window, blocking other modes.
- Strategy layer: generates harmonic and direct-mode setups.
- Risk layer: applies PF/win-rate/sample sizing, RR checks, cost checks, leverage caps, and protection checks.
- Execution protection: bounded limit entry first, exact-fill TP/SL protection immediately after fill, emergency close/halt if protection fails.

The main architectural gap is that the requested ShortScalpEngine, FastExitManager, ShadowTrader, ReplayEngine, and setup-level performance router do not currently exist as separate modules. Their responsibilities are partly embedded inside `server_core/engine.py`, but they are not independently observable, replayable, or testable yet.

Verdict: CONDITIONAL_PASS for current four-mode architecture; INSUFFICIENT for long-term stable-profit proof because there is no complete replay/OOS/shadow pipeline yet.

## Existing Modules

| Layer | Current implementation | Status |
| --- | --- | --- |
| Configuration | `server_core/config.py` | Present |
| OKX data/account/order adapter | `server_core/okx_client.py` | Present |
| Strategy scanner and lifecycle engine | `server_core/engine.py` | Present |
| Market router / ownership | `server_core/market_router.py` | Present |
| Performance, optimizer, reports | `server_core/strategies.py` | Present |
| Execution adapter and cost model | `server_core/execution.py` | Present |
| Shared runtime state | `server_core/state.py` | Present |
| Web API / UI data | `server_core/web_server.py`, `ui/` | Present |
| Short scalp engine | `server_core/short_scalp_engine.py` | Missing |
| Fast exit manager | `server_core/fast_exit_manager.py` | Missing |
| Shadow trade engine | `server_core/shadow_trader.py` | Missing |
| Replay engine | `server_core/replay_engine.py` | Missing |
| Test suite directory | `tests/` | Missing |

## Current Data Flow

1. `get_top_symbols_and_categories()` loads OKX USDT swap tickers, sorts by `quoteVolume`, and returns the configured universe size.
   - Default limit: `MARKET_UNIVERSE_LIMIT = 100`.
   - Refresh cadence: `MARKET_UNIVERSE_REFRESH_SECONDS = 3600`.

2. Symbols are classified by:
   - Major symbols: BTC, ETH, SOL.
   - Funding-rate extremes.
   - Relative strength versus BTC.
   - Deep 24h downside.
   - 24h high-low volatility.
   - Remaining symbols become High Volume.

3. Each strategy loop calls `rotating_strategy_symbols()`.
   - If the universe exceeds `SCAN_SYMBOLS_PER_LOOP`, each strategy scans a rotating window.
   - Current default `SCAN_SYMBOLS_PER_LOOP = 100`, so the intended configuration scans the whole top-100 universe per strategy loop.

4. Each symbol gets multi-timeframe trend context:
   - 15m, 1h, 4h, 1d.
   - Trend is based on EMA50/EMA200 and current closed candle price.

5. `route_symbol_market()` scores the symbol:
   - TREND -> MacroSniper.
   - MEAN_REVERSION -> MeanReversion.
   - EXTREME_REVERSAL -> Contrarian.
   - SQUEEZE_BREAKOUT -> SqueezeHunter.
   - NO_TRADE if the best edge is weak, ambiguous, or dominated by no-trade conditions.

6. `router_allows_mode()` enforces ownership.
   - Only the selected owner mode can continue for that symbol.
   - Other modes remain visible as radar candidates but are blocked.

7. The allowed mode builds candidates:
   - Harmonic pattern scan via pivots.
   - Direct mode setup generation for trend, mean reversion, contrarian reversal, and squeeze expansion.

8. Candidate gates run:
   - PRZ / entry-zone check.
   - HTF trend filter.
   - Strategy-specific gate.
   - Profit room check.
   - True RR check.
   - Performance block.
   - Cooldown / duplicate signal / opposite position checks.

9. Execution path:
   - Risk-based leverage cap.
   - Confidence-based margin sizing.
   - Expected edge versus cost gate.
   - Protection safety pause if existing active/live positions lack verified TP/SL.
   - Bounded limit entry, no market chase.
   - Exact-fill TP/SL protection.
   - Emergency close/halt if protection cannot be verified.

## Four-Mode Market Adaptation

### MacroSniper

Target market: TREND.

The mode requires strong enough ADX, preferably rising, plus higher-timeframe trend alignment. It is stricter on altcoins than majors. It rejects ranging or cooling trend states and hands those markets to MeanReversion or NO_TRADE.

Primary setups:

- Trend pullback.
- Momentum continuation.
- Breakout retest.
- Macro trend direct setup.

Risk profile:

- Higher margin multiplier than most modes.
- Wider stop and larger target.
- Designed for fewer but larger trend-runner trades.

### MeanReversion

Target market: MEAN_REVERSION.

The mode targets overbought/oversold snapback and Bollinger re-entry in non-runaway markets. It rejects very strong rising ADX to avoid fighting active trend runs.

Primary setups:

- Bollinger re-entry.
- RSI snapback.
- Range-edge reversal.
- Failed extension back toward mean.

Risk profile:

- Smaller target.
- Faster breakeven and lock thresholds.
- More defensive sizing in weak performance states.

### Contrarian

Target market: EXTREME_REVERSAL.

The mode is designed for exhaustion reversal, not ordinary countertrend trading. It needs extreme RSI plus at least one reversal proof such as divergence, liquidity sweep, or strong reversal wick.

Primary setups:

- Liquidity sweep reclaim.
- Extreme exhaustion.
- Failed breakout reversal.
- Divergence confirmation.

Risk profile:

- Conservative margin multiplier.
- Wider stop than MeanReversion.
- Requires stronger reversal evidence to avoid random top/bottom picking.

### SqueezeHunter

Target market: SQUEEZE_BREAKOUT.

The mode requires recent volatility compression plus expansion and sufficient breakout volume. It rejects setups with no squeeze history or weak volume.

Primary setups:

- Squeeze breakout.
- Momentum expansion.
- Breakout retest.
- Failed breakout as a future extension candidate, not currently a separated engine.

Risk profile:

- Medium margin multiplier.
- Larger target than MeanReversion.
- Special partial/runner behavior exists in position management.

## Performance and Optimizer Layer

Performance is computed per mode from verified closed history. The system tracks:

- Trade count.
- Win rate.
- Profit factor.
- Expectancy.
- Total PnL.
- State/verdict such as explore, steady, exploit, recover, or pause.

Current gating:

- If sample size reaches `CORE_TRADE_MIN_SAMPLE = 30`, then PF below `CORE_TRADE_MIN_PROFIT_FACTOR = 1.05` or negative expectancy blocks the mode.
- Confidence score uses PF, win rate, sample size, and category multiplier.
- Sizing is clamped between `MIN_CONFIDENCE_MARGIN_USDT = 20` and `MAX_CONFIDENCE_MARGIN_USDT = 150`.

Gap:

- Performance is mode-level first. It is not yet deeply partitioned by Mode + Setup + Category + Direction + Session + Volatility Regime + Score Bucket.
- There is no effective independent sample count yet.

## Risk and Execution Layer

The current risk layer is stronger than a simple signal bot:

- Planned max loss cap: `MAX_PLANNED_LOSS_USDT = 18`.
- Non-major leverage cap is reduced in `risk_based_leverage_cap()`.
- Profit-first filter requires enough TP room to cover fees/slippage.
- Execution cost model estimates gross target, estimated cost, expected net, and required gross.
- Entry uses bounded limit logic with a no-chase behavior.
- Protection order placement is mandatory after fill.
- If TP/SL protection is rejected or cannot be verified, the engine calls emergency close/halt logic.
- New entries pause while existing active or exchange positions lack verified protection.

Gap:

- Fast exit logic is embedded in the large engine loop rather than isolated as a replayable `FastExitManager`.
- There is no explicit per-hour/per-day loss budget module for short scalp mode.

## Observability Gaps

The UI now receives consistent `ui_metrics`, but the system still lacks the following Phase 2 observability artifacts:

- `state/short-scalp-summary.json`
- `state/scalp-performance.json`
- `state/setup-health.json`
- `state/shadow-trades.json`
- `state/signal-blockers.json`
- `state/replay-report.json`
- `state/fast-exit-report.json`

Without those files, the bot cannot yet prove which setup type is contributing edge, which blocker is over-filtering, or whether a proposed optimization improves out-of-sample behavior.

## Main Risks

1. The scanner can identify and route markets, but there is no replay-grade evidence that each mode/setup has stable positive expectancy.
2. Many gates are hard rejects. They may protect capital, but without blocker statistics they may also suppress too many valid trades.
3. The current engine file combines scanning, setup generation, risk checks, execution, protection, and exit management. This increases regression risk.
4. Requested short scalp components are missing, so adding 1m/3m/5m logic directly to the existing engine would be risky.
5. Existing protection safety is necessary, but current health remains vulnerable if exchange-side protection verification fails.

## Recommended Phase Order

Phase 2: Add observability first.

- Record every raw candidate, blocked candidate, shadow candidate, live-eligible candidate, executed trade, and rejected trade.
- Persist blocker reason codes and setup quality scores.
- Do not change trading behavior yet.

Phase 3: Add Shadow ShortScalpEngine.

- Build 1m/3m/5m candidates as shadow-only.
- No live trading permission by default.
- Emit setup score, cost model, and expiry.

Phase 4: Replay engine.

- Replay MarketRouter + ShortScalpEngine + Risk + Cost + FastExit behavior.
- Test no-future-leak.

Phase 5: FastExit comparison.

- Compare static TP/SL against Time Stop, Momentum Decay, Structure Failure, Edge Decay, and Hybrid Exit.

Phase 6: Limited live.

- Permit only one setup, one direction, reduced margin, and strict safety halts.

Phase 7: Setup performance router.

- Promote/demote Mode + Setup + Category + Direction based on PF, expectancy, drawdown, sample quality, and OOS validation.

