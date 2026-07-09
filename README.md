# OKX Harmonic Trading Agent

Multi-node demo trading and training center for OKX.

## What this repo does

- Runs a local bot on each machine.
- Keeps each machine's trade state and journal separate.
- Sends `journal_*.json` files to GitHub for global optimization.
- Merges all node journals in GitHub Actions into `global_optimizer.json`.

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

## First launch: zero-start

Use the bootstrap script the first time you start a machine.

Windows:

```powershell
.\set-node-name.bat macmini_01
```

```powershell
.\run-zero-start.bat macmini_01
```

Or double-click:

- `set-node-name.bat`
- `run-zero-start.bat`

macOS/Linux:

```bash
./scripts/bootstrap-zero-start.sh macmini_01
```

What it does:

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
./run_bot.sh
```

## Training data flow

1. Each machine writes to its own `journal_<NODE_NAME>.json`.
2. The server no longer auto-loads the legacy shared `trade_journal.json`.
3. GitHub Actions merges all `journal_*.json` files.
4. `optimize_global.py` computes a fresh `global_optimizer.json`.
5. Each node pulls the updated optimizer and keeps running with its own local journal.

## Files to know

- `server_core/config.py` - node name and file paths
- `server.py` - local boot/load logic
- `scripts/bootstrap-zero-start.ps1` - Windows zero-start bootstrap
- `scripts/bootstrap-zero-start.sh` - macOS/Linux zero-start bootstrap
- `set-node-name.bat` - Windows node-name setter
- `run-zero-start.bat` - Windows zero-start launcher
- `scripts\set-node-name.ps1` - PowerShell node-name setter implementation
- `.github/workflows/optimize.yml` - global optimization and commit
- `optimize_global.py` - merges all node journals and builds the optimizer

## Submission rules

- Do not commit `active_trades_*.json`.
- Commit `journal_*.json` only.
- Keep one unique node name per machine.
- Do not reuse the same node name on different computers.
