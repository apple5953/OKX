# OKX Harmonic Trading Agent

## Robot Version

- Robot family: OKX Harmonic Trading Agent
- Active strategy generation: `V13`
- Documentation update: `V13.2 Mac mini training handoff`
- Last reviewed: `2026-07-19`
- Default training target: OKX demo / sandbox, not real capital

This repository contains a four-mode OKX trading and training robot. It can scan high-liquidity USDT swap markets, route each symbol into a market regime, collect trade samples, and update strategy performance through per-node journals.

Important: this robot is still in training. The current configuration is suitable for collecting demo samples. It is not proof that the system can already produce long-term stable profit with larger real-money sizing.

---

## Current Four-Mode Design

| Mode | Market Type | Role |
| --- | --- | --- |
| `MacroSniper` | `TREND` | Trend continuation and breakout follow-through |
| `MeanReversion` | `MEAN_REVERSION` | Range-bound mean reversion after stretched moves |
| `Contrarian` | `EXTREME_REVERSAL` | Extreme reversal after exhaustion, divergence, or false move |
| `SqueezeHunter` | `SQUEEZE_BREAKOUT` | Volatility compression followed by breakout expansion |

The robot does not simply rotate modes. It first uses the market router to classify each symbol, then assigns that symbol to the mode with the best expected fit.

Current training safeguards:

- Top-volume universe target: `OKX_MARKET_UNIVERSE_LIMIT=100`
- Universe refresh interval: `OKX_MARKET_UNIVERSE_REFRESH_SECONDS=3600`
- Demo fast-training scan loop: about `12` seconds by default
- Per-loop scan target: `OKX_SCAN_SYMBOLS_PER_LOOP=100`
- Weak modes can still collect demo samples through a reduced-size training probe
- Training probe default margin: `8U`

---

## Mac Mini Training Verdict

You can use the same strategy settings on a Mac mini, but the Mac mini must run as an independent training node.

Recommended use:

- Same codebase
- Same strategy generation: `V13`
- Same OKX demo settings if you intentionally want demo execution
- Unique `OKX_NODE_NAME`
- Fresh zero-start journal
- No shared `active_trades` file

Not recommended:

- Do not copy the Windows active session and continue it on Mac mini.
- Do not let Windows and Mac mini use the same OKX demo account to auto-order at the same time.
- Do not reuse the same node name on two machines.
- Do not commit active trade state, credentials, screenshots, or `.deps`.

Why: active trades contain exchange position IDs, protection order IDs, lifecycle IDs, and node-specific accounting. Copying them across machines can corrupt attribution and TP/SL management.

---

## Critical Rules For AI Agents Installing On Mac Mini

When an AI agent helps install or run this robot on Mac mini, it must follow these rules exactly.

1. Confirm node identity first.

```bash
export OKX_NODE_NAME=macmini_02
```

Use a new unique name for every physical machine. Never reuse the Windows node name.

2. Confirm run mode before launch.

```bash
export OKX_RUN_MODE=mock
```

Use `mock` for first boot and UI verification. Use `demo` only after credentials, health, and port status are verified.

3. Run zero-start for a new Mac mini.

```bash
./scripts/bootstrap-zero-start.sh macmini_02 mock
```

This backs up old local state and creates clean files:

- `journal_macmini_02.json`
- `active_trades_macmini_02.json`
- `zero_start_state_macmini_02.json`

4. Never copy these as live source of truth from Windows to Mac mini:

- `active_trades_desktop-*.json`
- `account_session_baseline_desktop-*.json`
- `zero_start_state_desktop-*.json`
- `optimization_cycle_state.json`
- `auth_token.json`
- `.deps/`

5. Only journal files are training outputs.

The file that may be merged later is:

- `journal_macmini_02.json`

Do not commit:

- `active_trades_*.json`
- `.deps/`
- `auth_token.json`
- screenshots
- account snapshots
- local logs
- backup folders

6. Do not run two auto-order engines on the same OKX account.

If Windows is already demo auto-ordering, keep Mac mini in `mock` or stop Windows before enabling Mac mini `demo`.

7. Confirm port `5000` is free.

macOS AirPlay Receiver often uses port `5000`. If the UI does not start, check:

```bash
lsof -i :5000
```

If AirPlay owns it, disable AirPlay Receiver or modify the app to use a configurable port.

8. Prevent Mac mini sleep.

Training stops when macOS sleeps. For a temporary session:

```bash
caffeinate -dimsu ./start-main.sh macmini_02 demo
```

For long-running training, configure Energy Settings or launchd.

9. Verify dependencies in a local venv.

The launcher creates `.deps/venv` and installs:

- `ccxt`
- `pandas`
- `flask`

The current script does not pin exact package versions. If reproducibility matters, create a lock file before long training.

10. Watch the OKX CLI fallback issue.

The main path uses `ccxt` REST and is cross-platform. However, the current fallback for OKX CLI in `server_core/okx_client.py` still assumes Windows paths such as `okx.cmd` and `powershell.exe`.

Impact:

- Mac mini can still run if REST works.
- If REST balance or positions temporarily fail, CLI fallback may fail on macOS.
- This should be fixed before relying on Mac mini as the main demo execution node.

---

## Mac Mini Installation Checklist

Run these commands on Mac mini from a terminal.

1. Install or verify basic tools.

```bash
git --version
python3 --version
```

Python 3.11+ is recommended.

2. Clone or update the repository.

```bash
git clone https://github.com/apple5953/OKX.git
cd OKX/harmonic_agent
```

If already cloned:

```bash
git pull origin codex/upload-current-bot
cd harmonic_agent
```

3. Set a unique node and first run in mock.

```bash
export OKX_NODE_NAME=macmini_02
export OKX_RUN_MODE=mock
export OKX_OPEN_UI=1
```

4. Initialize clean local training state.

```bash
./scripts/bootstrap-zero-start.sh macmini_02 mock
```

5. Start normally after zero-start.

```bash
./start-main.sh macmini_02 mock
```

6. Open the UI.

```text
http://127.0.0.1:5000
```

7. Verify UI health.

Check that the UI shows:

- Market radar is updating
- Four mode cards are visible
- Health check is not blank
- Candidate count changes over time
- Journal file exists for the Mac node

8. Only after mock verification, switch to demo if desired.

```bash
export OKX_RUN_MODE=demo
./start-main.sh macmini_02 demo
```

Before demo auto-ordering, confirm Windows is not also auto-ordering on the same OKX demo account.

---

## OKX Credentials On Mac Mini

The robot can read OKX credentials from environment variables:

```bash
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."
export OKX_RUN_MODE=demo
```

It can also read an OKX profile from:

```text
~/.okx/config.toml
```

The config loader supports profile fields such as:

- `api_key`
- `secret_key`
- `passphrase`
- `demo`
- `site`

If `demo=true`, the robot resolves run mode as demo unless another explicit mode is provided.

Security rules:

- Never commit credentials.
- Never paste credentials into README.
- Never push `auth_token.json`.
- Prefer OKX API keys restricted to demo/sandbox for training.

---

## Multi-Node Training Policy

Each machine writes its own state:

```text
journal_<NODE_NAME>.json
active_trades_<NODE_NAME>.json
zero_start_state_<NODE_NAME>.json
account_session_baseline_<NODE_NAME>.json
```

Training aggregation should use journals, not active state.

Safe to review or merge intentionally:

- `journal_macmini_02.json`

Usually unsafe to merge:

- `active_trades_macmini_02.json`
- `zero_start_state_macmini_02.json`
- `account_session_baseline_macmini_02.json`
- `optimization_cycle_state.json`
- `global_optimizer.json` unless the optimizer update is intentional and reviewed

Git rules already ignore most local runtime files, but an AI agent must still inspect `git status --short` before staging.

---

## Current Profitability Status

The robot should be treated as a training system, not as a proven stable-profit system.

As of the latest local review on `2026-07-19`:

- `MacroSniper` had negative expectancy and was limited to training probe behavior.
- `SqueezeHunter` had negative expectancy and was limited to training probe behavior.
- `MeanReversion` had too few samples to prove stability.
- `Contrarian` had insufficient or zero effective samples.

This means the Mac mini should help collect clean samples. It should not be used to increase live risk.

Minimum evidence needed before calling a mode stable:

- At least `30` verified learnable closed trades per mode
- Positive expectancy
- Profit factor above the configured threshold
- Acceptable drawdown
- No large TP/SL protection failures
- No pollution from manual, recovered, mixed, or version-mismatch trades

---

## UI Validation Checklist

After the robot starts, verify:

- `/api/trades` returns HTTP 200
- UI loads at `http://127.0.0.1:5000`
- Browser console has no JavaScript errors
- Account equity, active PnL, and four-mode closed PnL are clearly separated
- Market radar has candidates or clear block reasons
- Mode cards show sample count, win rate, PF, expectancy, and training probe status
- Health panel is populated
- Active positions show TP/SL or protection status

If UI is blank:

1. Check port `5000`.
2. Check terminal logs.
3. Check Python dependencies.
4. Check OKX credentials if running demo.
5. Re-open `http://127.0.0.1:5000`.

---

## Technical Risks On Mac Mini

| Risk | Severity | Why It Matters | Mitigation |
| --- | --- | --- | --- |
| Same OKX account runs on Windows and Mac | Critical | duplicate entries, TP/SL conflicts, polluted attribution | only one demo auto-order node at a time |
| Same `OKX_NODE_NAME` reused | Critical | journal and active state overwrite each other | unique node per physical machine |
| Copying active state from Windows | Critical | protection order IDs and lifecycle IDs do not belong to Mac | zero-start on Mac |
| macOS port 5000 conflict | High | UI may fail to start | check AirPlay Receiver or add configurable port |
| Windows-only OKX CLI fallback | Medium/High | fallback balance/position recovery can fail on Mac | use REST path or patch CLI resolver |
| Unpinned Python packages | Medium | future ccxt/pandas changes can alter behavior | add requirements lock for long training |
| Mac sleep | Medium | scanner and TP/SL monitor pause | use `caffeinate` or disable sleep |
| OKX rate limit | Medium | two nodes scanning with same key may hit limits | avoid duplicate demo nodes, reduce scan loop |
| Dirty git worktree | Medium | runtime data may be committed accidentally | stage only intended source/docs |

---

## Recommended Mac Mini First-Day Procedure

1. Pull latest repository.
2. Set `OKX_NODE_NAME=macmini_02`.
3. Start in `mock`.
4. Run zero-start.
5. Verify UI and radar for 15-30 minutes.
6. Confirm no console errors.
7. Confirm `journal_macmini_02.json` exists.
8. Stop Windows demo auto-order if Mac will take over demo.
9. Start Mac in `demo`.
10. Watch the first few candidates and active positions.
11. Confirm every active position has protection.
12. Commit only the Mac journal when intentionally contributing training data.

---

## Commands Reference

Start mock training:

```bash
export OKX_NODE_NAME=macmini_02
export OKX_RUN_MODE=mock
./start-main.sh macmini_02 mock
```

Start demo training:

```bash
export OKX_NODE_NAME=macmini_02
export OKX_RUN_MODE=demo
./start-main.sh macmini_02 demo
```

Start without auto-opening UI:

```bash
export OKX_OPEN_UI=0
./start-main.sh macmini_02 mock
```

Keep Mac awake for a session:

```bash
caffeinate -dimsu ./start-main.sh macmini_02 demo
```

Inspect local API:

```bash
curl http://127.0.0.1:5000/api/trades
```

Inspect git before committing:

```bash
git status --short
```

---

## AI Agent Handoff Prompt For Mac Mini

Use this prompt when asking an AI agent on Mac mini to install or verify the robot:

```text
You are helping install OKX Harmonic Trading Agent V13 on a Mac mini.
Do not run live mode.
Do not reuse a Windows node name.
Use a new OKX_NODE_NAME such as macmini_02.
Start in mock mode first.
Run zero-start before first launch.
Do not copy active_trades from Windows.
Do not commit active_trades, credentials, .deps, screenshots, or logs.
Check whether port 5000 is occupied by macOS AirPlay.
Verify http://127.0.0.1:5000 and /api/trades.
Only after mock UI and health checks are normal, ask before switching to OKX demo auto-ordering.
If demo mode is enabled, confirm no other machine is auto-ordering on the same OKX demo account.
Report exact files changed and exact validation commands.
```

---

## Files To Know

- `server.py` - main local server and four strategy thread startup
- `server_core/config.py` - node name, run mode, scan limits, training probe settings
- `server_core/engine.py` - strategy scan and execution loop
- `server_core/market_router.py` - market regime routing
- `server_core/okx_client.py` - OKX REST client and local snapshots
- `server_core/strategies.py` - performance, optimizer, mode logic
- `server_core/web_server.py` - UI/API endpoints
- `ui/index.html` - dashboard shell
- `ui/app.js` - main UI logic
- `ui/app-v13-canonical.js` - V13 UI consistency overrides
- `run_bot.sh` - Mac/Linux launcher
- `start-main.sh` - Mac/Linux guarded launcher
- `scripts/bootstrap-zero-start.sh` - Mac/Linux zero-start
- `macmini_deployment_guide.md` - shorter deployment notes

---

## Summary

Mac mini training is technically feasible with the same strategy generation, but it must be treated as a separate training node. The safe path is mock first, zero-start, unique node name, UI/API verification, then demo only if no other machine is controlling the same OKX account.
