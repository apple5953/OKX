# OKX Harmonic Trading Agent

Multi-node trading and training center for OKX.

This repo is built for a mixed setup:

- one main machine can run OKX demo or live trading if it has valid OKX API access and the right permissions
- every other machine can still participate in market scanning, simulated trades, and journal collection
- GitHub Actions merges all node journals into a global optimizer

---

## 🔐 Google 登入與集中式權限控管系統 (Google Sign-In & Permissions)

本專案引入了中央授權機制，透過 **Google 帳號身分驗證** 與 **Google 試算表 (Google Sheet)** 控制每台電腦節點的權限，適合「多台電腦協同訓練與交易」的安全管理：

### 1. 授權核心原則
*   **Google 驗證身分**：首次啟動本機精靈時，會自動引導使用者透過瀏覽器登入 Google 帳號。
*   **GAS 後端控管**：登入後會透過 Google Apps Script (GAS) 查詢雲端試算表名單：
    *   **非本人（新使用者）**：若 Google 帳號不在白名單上，系統會自動在 Excel 註冊此人，並強制指派其本機機器人運行於 **`mock` (模擬單)** 模式。
    *   **本人（管理員）**：在試算表中被手動指定為 `demo` 或 `live` 模式，才能載入並使用本機的 OKX API Key 進行實盤或沙盒交易。
*   **本機一鍵啟動精靈**：登入完成後會自動建立該節點的憑證與全新空白的 `journal_<NODE_NAME>.json` 資料庫，之後每次啟動都走靜默自動流程，無須手動重複設定。

### 2. 試算表 (Google Sheet) 格式配置
請確保您的 Google 試算表首行欄位設定為：
*   **A 欄**：`Email` (使用者 Google 信箱)
*   **B 欄**：`Mode` (手動填入 `live`、`demo` 或自動產生的 `mock`)
*   **C 欄**：`Expiration Date` (授權過期日，格式為 `yyyy-mm-dd`)
*   **D 欄**：`Active Devices` (系統自動在此處寫入 JSON 格式的已綁定裝置名稱與最後活躍時間)

---

## Modes

The bot supports explicit run modes.

| Mode | Purpose | Behavior |
| --- | --- | --- |
| `auto` | Default | Try OKX access based on credentials and mode settings |
| `mock` | Local simulation only | Never try to run as live; safe for secondary machines |
| `demo` | OKX sandbox/demo | Connects to OKX demo trading, not local mock |
| `live` | Primary machine | Use real OKX trading when credentials and whitelist work |

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
- `run-demo.bat`
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

If a machine does not have valid credentials, it should not be treated as a valid OKX demo machine until the credentials and permissions are fixed.

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

V13 uses a per-machine zero-start manifest. On the first launch, or whenever
the manifest is missing or the strategy version changes, the launcher backs up
old local history and rebuilds a clean empty journal before the bot starts.

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

```powershell
.\run-zero-start.bat macmini_01 demo
```

Or double-click:

- `set-node-name.bat`
- `set-run-mode.bat`
- `run-zero-start.bat`
- `run-mock.bat`
- `run-demo.bat`
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
- writes `zero_start_state_<NODE_NAME>.json` so the machine remembers it has been initialized
- creates fresh empty `[]` files for the current machine
- launches the bot unless `-SkipLaunch` / `SKIP_LAUNCH=1` is used

## Normal launch

Windows:

```powershell
run_bot.bat
```

One-click main launcher:

```powershell
start-main.bat
```

`run_bot.bat` and `start-main.bat` both re-check the zero-start manifest, so a
brand new machine still starts from 0 even if you skip the explicit bootstrap
step.

macOS/Linux:

```bash
run_bot.sh
```

One-click main launcher:

```bash
./start-main.sh
```

`run_bot.sh` and `start-main.sh` perform the same manifest check on Mac/Linux.

The local UI opens automatically at `http://127.0.0.1:5000` unless you set `OKX_OPEN_UI=0`.

## Training flow

1. Each machine writes to its own `journal_<NODE_NAME>.json`.
2. Secondary machines can stay in `mock` mode and still produce useful journals.
3. The server does not auto-load legacy shared journals on startup.
4. GitHub Actions merges all `journal_*.json` files.
5. `optimize_global.py` computes a fresh `global_optimizer.json`.
6. Each node pulls the updated optimizer and continues with its own local journal.

## Dashboard sync rules

To keep the UI consistent, the dashboard now follows these source rules:

1. Top summary, mode console, and health status prefer the live `/api/trades` report.
2. Session history is only used as a fallback when the live report does not provide a value.
3. Strategy cards prefer backend strategy stats first, then local session stats.
4. The engine heartbeat panel prefers backend strategy stats so the cards and top summary stay aligned.
5. Zero-start banners only show the current machine's local bootstrap state, not another machine's history.

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

### Demo machine

- connect to the OKX sandbox/demo environment
- place demo orders without touching real funds
- read demo account and position state from OKX
- contribute demo execution history to the global journal

The top-right runtime badge on the dashboard now shows `mock / demo / live / auto` so you can tell the mode at a glance.

## Update flow

If the repo is already cloned on a machine:

```bash
git pull origin codex/upload-current-bot
```

If you want a fresh download:

- ZIP: [https://github.com/apple5953/OKX/archive/refs/heads/codex/upload-current-bot.zip](https://github.com/apple5953/OKX/archive/refs/heads/codex/upload-current-bot.zip)

## Move Main Bot To Mac Mini

If you move the main bot from Windows to a Mac mini, copy the repo folder and rebuild only the machine-specific runtime pieces.

Bring these files with you:

- the full `harmonic_agent` repository folder
- the current `journal_<NODE_NAME>.json` if you want to keep the same node history
- the current `active_trades_<NODE_NAME>.json` if you want to keep the same active UI snapshot
- any backup folder you want to archive from `backups/`
- your OKX credentials from environment variables or your local OKX profile config

Do not rely on these as the primary source of truth:

- `trade_journal.json`
- `active_trades.json`

Mac mini setup order:

1. Install Python 3.12+ and Git if they are not already available.
2. Copy the repo to the Mac mini.
3. Set a unique `OKX_NODE_NAME` for the Mac mini, for example `macmini_main`.
4. Set the run mode you want:
   - `mock` for local simulation
   - `demo` for OKX sandbox/demo
   - `live` only on the primary machine with the right whitelist and permissions
5. If this is a brand new machine, do a zero-start first.
6. Start the bot with `bash run_bot.sh` or `OKX_RUN_MODE=demo bash run_bot.sh`.
7. The dashboard UI will open automatically at `http://127.0.0.1:5000`.

For an easier first launch, you can use:

```powershell
start-main.bat macmini_main demo
```

or on Mac/Linux:

```bash
./start-main.sh macmini_main demo
```

If you want a fresh start on the Mac mini, use:

```bash
export OKX_NODE_NAME=macmini_main
export OKX_RUN_MODE=demo
./scripts/bootstrap-zero-start.sh macmini_main
```

If you want to preserve the old history instead, copy the node-specific journal files before the first launch and keep the same `OKX_NODE_NAME`.

## Files to know

- `server_core/config.py` - node name, run mode, and file paths
- `server.py` - local boot/load logic
- `scripts/bootstrap-zero-start.ps1` - Windows zero-start bootstrap
- `scripts/bootstrap-zero-start.sh` - macOS/Linux zero-start bootstrap
- `scripts/set-node-name.ps1` - PowerShell node-name setter
- `scripts/set-run-mode.ps1` - PowerShell run-mode setter
- `set-node-name.bat` - Windows node-name setter
- `set-run-mode.bat` - Windows run-mode setter
- `run-demo.bat` - Windows demo launcher
- `run-zero-start.bat` - Windows zero-start launcher
- `.github/workflows/optimize.yml` - global optimization and commit
- `optimize_global.py` - merges all node journals and builds the optimizer

## Submission rules

- Do not commit `active_trades_*.json`.
- Commit `journal_*.json` only.
- Keep one unique node name per machine.
- Set `OKX_RUN_MODE=mock` on secondary machines if you want them locked to simulation.
- Set `OKX_RUN_MODE=demo` on the main OKX sandbox/demo machine.
- Do not reuse the same node name on different computers.

## Troubleshooting

- If a machine should be mock but starts trying to behave like live, set `OKX_RUN_MODE=mock` and restart.
- If a machine should use OKX sandbox/demo, set `OKX_RUN_MODE=demo` and restart.
- If a machine must be live, confirm its OKX API key and whitelist first.
- If the journals look polluted, run zero-start again so the machine starts from an empty local history.

## Quick mode switching

- Mock only: `run-mock.bat`
- Demo mode: `run-demo.bat`
- Live preferred: `run-live.bat`
- Zero-start with a mode: `run-zero-start.bat macmini_02 demo`
- Normal launch with a mode: `run_bot.bat mock`, `run_bot.bat demo`, or `run_bot.bat live`
- One-click main launcher: `start-main.bat` or `start-main.sh`
