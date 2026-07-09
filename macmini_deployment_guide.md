# Multi-Node Deployment Guide

This guide explains how to set up one machine so it trains with its own data and contributes clean journals to the shared GitHub optimizer.

## 1. Goal

- Each machine keeps its own local state.
- Each machine starts from a zeroed journal on first launch.
- GitHub merges all journals later to build the shared optimizer.

## 2. Set a unique node name

Use one unique node name per physical machine.

Recommended environment variable:

- `OKX_NODE_NAME`

Fallback:

- `NODE_NAME`

Examples:

```powershell
$env:OKX_NODE_NAME = "macmini_02"
```

```bash
export OKX_NODE_NAME=macmini_02
```

Do not reuse the same node name on two computers.

## 3. First launch zero-start

Windows:

```powershell
.\set-node-name.bat macmini_02
.\run-zero-start.bat macmini_02
```

macOS/Linux:

```bash
./scripts/bootstrap-zero-start.sh macmini_02
```

The bootstrap script will:

- back up any existing `journal_<NODE_NAME>.json`
- back up any existing `active_trades_<NODE_NAME>.json`
- back up legacy `trade_journal.json`
- back up legacy `active_trades.json`
- create fresh empty JSON files for the current node

If you only want to set the machine name without zero-starting, use:

```powershell
.\set-node-name.bat macmini_02
```

## 4. Normal daily launch

Windows:

```powershell
run_bot.bat
```

macOS/Linux:

```bash
./run_bot.sh
```

## 5. What gets trained

- Local journal file: `journal_<NODE_NAME>.json`
- Local active state file: `active_trades_<NODE_NAME>.json`
- GitHub optimizer input: all `journal_*.json` files in the repo
- Shared optimizer output: `global_optimizer.json`

## 6. Practical rules

- Do not let two machines share the same node name.
- Do not keep using a legacy shared journal file as the live source of truth.
- Do not commit `active_trades_*.json`.
- Commit only the journal output files.

## 7. Troubleshooting

If a machine appears to inherit old data:

1. Stop the bot.
2. Run the zero-start bootstrap again with the correct node name.
3. Check that the new journal file is empty before normal launch.
4. Confirm the current node name is what you expected.
