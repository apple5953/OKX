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
- write `zero_start_state_<NODE_NAME>.json`
- create fresh empty JSON files for the current node

The normal launchers also re-check the zero-start manifest, so a brand new
machine still starts from 0 even if you skip the explicit bootstrap step.

If you want to keep the old machine's history instead of starting fresh, copy these files before first launch:

- `journal_<NODE_NAME>.json`
- `active_trades_<NODE_NAME>.json`
- `backups/`

Do not use `trade_journal.json` or `active_trades.json` as the main source of truth on the new machine.

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

The UI opens automatically at `http://127.0.0.1:5000` unless you set `OKX_OPEN_UI=0`.

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

## 8. Google OAuth 授權安全設定

為了防止 Google Client ID/Secret 金鑰在 GitHub 上被公開洩露，我們採用環境變數安全設計。在新電腦（如 Mac mini）上啟動前，請先配置以下環境變數：

### 執行環境變數設定

在執行後端認證服務前，請設定您的 Google OAuth 用戶端密鑰：

**Windows (PowerShell)**:
```powershell
$env:GOOGLE_CLIENT_ID = "YOUR_GOOGLE_CLIENT_ID"
$env:GOOGLE_CLIENT_SECRET = "YOUR_GOOGLE_CLIENT_SECRET"
```

**macOS / Linux (Bash/Zsh)**:
```bash
export GOOGLE_CLIENT_ID="YOUR_GOOGLE_CLIENT_ID"
export GOOGLE_CLIENT_SECRET="YOUR_GOOGLE_CLIENT_SECRET"
```

設定完成後，再啟動授權後端 `python auth_server/server.py` 與機器人即可安全運行。
