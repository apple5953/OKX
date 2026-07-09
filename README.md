# OKX Harmonic Trading Agent

Multi-node trading and training center for OKX.

This repo is built for a mixed setup:

- one main machine can run live trading if it has valid OKX API access and whitelist permission
- every other machine can still participate in market scanning, simulated trades, and journal collection
- GitHub Actions merges all node journals into a global optimizer

## Modes

The bot supports explicit run modes.

| Mode | Purpose | Behavior |
| --- | --- | --- |
| `auto` | Default | Use live access when credentials and whitelist work, otherwise fall back to mock |
| `mock` | Simulation only | Never try to run as live; safe for secondary machines |
| `live` | Primary machine | Prefer live access, but still fall back to mock if OKX blocks the account or IP |

Set it with:

```powershell
$env:OKX_RUN_MODE = "mock"
```

or:

```bash
export OKX_RUN_MODE=mock
```

Windows users also have:

- `set-run-mode.bat`
- `run-mock.bat`
- `run-live.bat`

## Credentials

Set your OKX credentials as environment variables on the machine that should connect to OKX.

Required variables:

- `OKX_API_KEY`
- `OKX_API_SECRET`
- `OKX_PASSPHRASE`

Examples:

```powershell
$env:OKX_API_KEY = "your_api_key"
$env:OKX_API_SECRET = "your_api_secret"
$env:OKX_PASSPHRASE = "your_passphrase"
```

```bash
export OKX_API_KEY=your_api_key
export OKX_API_SECRET=your_api_secret
export OKX_PASSPHRASE=your_passphrase
```

If a machine does not have valid credentials, it will fall back to mock mode.

## What this repo does

- Runs a local bot on each machine.
- Keeps each machine's trade state and journal separate.
- Uses `journal_*.json` for aggregation.
- Builds `global_optimizer.json` from all node journals.
- Prevents legacy shared journals from polluting zero-start training.

## Node identity

Every machine must have a unique node name.

Recommended:

- Windows: set `OKX_NODE_NAME`
- macOS/Linux: set `OKX_NODE_NAME`

Fallback behavior:

- If no env var is set, `server_core/config.py` generates a node name from hostname plus a stable suffix.

Examples:

```powershell
$env:OKX_NODE_NAME = "macmini_01"
```

```bash
export OKX_NODE_NAME=macmini_01
```

You can also persist the name with:

- `set-node-name.bat`

## First launch: zero-start

Use the bootstrap script the first time you start a machine.

Windows:

```powershell
.\set-node-name.bat macmini_01
```

```powershell
.\set-run-mode.bat mock
```

```powershell
.\run-zero-start.bat macmini_01
```

Or double-click:

- `set-node-name.bat`
- `set-run-mode.bat`
- `run-zero-start.bat`
- `run-mock.bat`
- `run-live.bat`

macOS/Linux:

```bash
export OKX_NODE_NAME=macmini_01
export OKX_RUN_MODE=mock
./scripts/bootstrap-zero-start.sh macmini_01
```

What zero-start does:

- backs up any existing `journal_<NODE_NAME>.json`
- backs up any existing `active_trades_<NODE_NAME>.json`
- backs up legacy `trade_journal.json` and `active_trades.json`
- creates fresh empty `[]` files for the current machine
- launches the bot unless `-SkipLaunch` / `SKIP_LAUNCH=1` is used

## Normal launch

Windows:

```powershell
run_bot.bat
```

macOS/Linux:

```bash
run_bot.sh
```

## Training flow

1. Each machine writes to its own `journal_<NODE_NAME>.json`.
2. Secondary machines can stay in `mock` mode and still produce useful journals.
3. The server does not auto-load legacy shared journals on startup.
4. GitHub Actions merges all `journal_*.json` files.
5. `optimize_global.py` computes a fresh `global_optimizer.json`.
6. Each node pulls the updated optimizer and continues with its own local journal.

## What each machine can do

### Live machine

- place real OKX orders
- read live positions and balances
- keep real execution and journal history
- contribute to the global optimizer

### Mock machine

- scan public candles and tickers
- simulate entries, exits, take-profit, and stop-loss
- verify strategy logic without real capital risk
- contribute simulated learning data through journals

## Update flow

If the repo is already cloned on a machine:

```bash
git pull origin codex/upload-current-bot
```

If you want a fresh download:

- ZIP: [https://github.com/apple5953/OKX/archive/refs/heads/codex/upload-current-bot.zip](https://github.com/apple5953/OKX/archive/refs/heads/codex/upload-current-bot.zip)

## Files to know

- `server_core/config.py` - node name, run mode, and file paths
- `server.py` - local boot/load logic
- `scripts/bootstrap-zero-start.ps1` - Windows zero-start bootstrap
- `scripts/bootstrap-zero-start.sh` - macOS/Linux zero-start bootstrap
- `scripts/set-node-name.ps1` - PowerShell node-name setter
- `scripts/set-run-mode.ps1` - PowerShell run-mode setter
- `set-node-name.bat` - Windows node-name setter
- `set-run-mode.bat` - Windows run-mode setter
- `run-zero-start.bat` - Windows zero-start launcher
- `.github/workflows/optimize.yml` - global optimization and commit
- `optimize_global.py` - merges all node journals and builds the optimizer

## Submission rules

- Do not commit `active_trades_*.json`.
- Commit `journal_*.json` only.
- Keep one unique node name per machine.
- Set `OKX_RUN_MODE=mock` on secondary machines if you want them locked to simulation.
- Do not reuse the same node name on different computers.

## Troubleshooting

- If a machine should be mock but starts trying to behave like live, set `OKX_RUN_MODE=mock` and restart.
- If a machine must be live, confirm its OKX API key and whitelist first.
- If the journals look polluted, run zero-start again so the machine starts from an empty local history.

## Quick mode switching

- Mock only: `run-mock.bat`
- Live preferred: `run-live.bat`
- Zero-start with a mode: `run-zero-start.bat macmini_02 mock`
- Normal launch with a mode: `run_bot.bat mock` or `run_bot.bat live`
