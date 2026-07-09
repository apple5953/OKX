# OKX Harmonic Trading Agent - 分布式 AI 訓練中心 (Multi-Node AI Training Center)

本專案是一個基於 **OKX 模擬盤 (Demo Trading)** 的分布式 AI 諧波交易機器人系統。支持多台設備（例如 Mac Mini、本機、雲端伺服器）並行掃描、模擬交易與數據採集，並通過 GitHub 進行去中心化參數聚合與 AI 自適應優化。

> **To the AI Agent reading this README on a new device:**
> Please read the instructions below carefully to initialize, configure, and safely run this node using the built-in **Portable Green Sandbox** to avoid dependency issues or file conflicts.

---

## 🚀 核心優勢：免安裝、免權限一鍵部署 (Portable Green Sandbox)

本專案提供**「純綠色、零權限要求」**的自給自足運行套件。使用者和 AI Agent **完全不需要在電腦系統中安裝 Python 環境、環境變數或安裝任何外部依賴軟體**。

即使在硬碟有寫入限制（例如鎖死 C 槽）的辦公或邊緣計算設備上，只要將本專案下載並解壓到 **D 槽、E 槽、外接硬碟或 USB 隨身碟** 中，雙擊即可直接運行。

*   **Windows 系統**：直接雙擊運行根目錄下的 **`run_bot.bat`**。
*   **Mac / Linux 系統**：在終端機執行根目錄下的 **`./run_bot.sh`**。

---

## 🛠️ 一、 系統架構與去中心化學習機制 (Decentralized Learning)

本系統採用 **「Master-Slave 參數伺服器架構 (GitHub-based Parameter Server)」**，實現無衝突的分布式多機訓練：

1. **獨立文件隔離（無衝突設計）**：
   每台設備（Node）使用專屬的 `NODE_NAME`（例如 `macmini_01`, `macmini_02`）。
   *   本地持倉狀態保存於：`active_trades_<NODE_NAME>.json` (已被 Git 忽略，防止跨設備覆蓋)。
   *   本地平倉日誌保存於：`journal_<NODE_NAME>.json` (提交推送至 GitHub，共同組成訓練集)。
2. **AI 全局大腦（GitHub Actions）**：
   GitHub Actions 工作流配置在 `.github/workflows/optimize.yml`。它會：
   *   讀取並合併倉庫中所有的 `journal_*.json` 日誌。
   *   全局執行 AI 調參演算法，為 4 個策略計算最新最優的 `sl_atr`, `tp_atr`, `confidence_weight` 等。
   *   將最優參數寫入 `global_optimizer.json` 並推回倉庫。
3. **設備端自動同步**：
   各設備定時拉取（Git Pull）代碼，當檢測到 `global_optimizer.json` 時，策略引擎會自動載入雲端最新最優的參數 DNA，使全網機器人越跑越聰明。

---

## ⚙️ 二、 邊緣節點（新電腦/Mac Mini）部署步驟

當您在新的電腦或設備上部署時，請按照以下步驟操作：

### 1. 下載並釋放專案
將本專案下載（或 `git clone`）並解壓到您電腦的任意非受限磁碟分區（如 `D:\harmonic_agent\` 或 `/Volumes/USB/harmonic_agent/`）。

### 2. 修改節點配置 (`server_core/config.py`)
打開 `server_core/config.py`，配置以下屬性：
*   **`NODE_NAME`**：設置為此設備專屬的代號（例如：`'macmini_02'` 或 `'office_laptop_01'`）。此設定會自動為本機隔離出專屬的交易記錄與狀態檔，避免與其他電腦衝突。
*   **OKX API 金鑰**：填寫您的 OKX 模擬盤 API 金鑰（`OKX_API_KEY`, `OKX_SECRET`, `OKX_PASSWORD`）。
    *   *安全提示：為防範多台電腦開倉衝突，建議在 `config.py` 中分配不同的交易對 (Symbols)，或為每台電腦申報不同的子帳號 (Sub-Account) API 金鑰。*

### 3. 一鍵啟動 (Zero Install)

#### 🟩 Windows 系統：
直接雙擊執行 **`run_bot.bat`**。
*   腳本會全自動在 `.deps/` 目錄下載官方 Python 3.12 綠色版。
*   自動配置綠色 Pip 工具並於沙盒內安裝 `ccxt`, `pandas`, `flask` 等。
*   自動執行機器人主程序與 API 數據同步。

#### 🟩 macOS / Linux 系統：
在終端機中，給予執行權限並啟動：
```bash
chmod +x run_bot.sh
./run_bot.sh
```
*   腳本會自動建立一個 100% 獨立的用戶空間虛擬環境 (`.deps/venv`)。
*   在虛擬沙盒中下載安裝機器人所有依賴。
*   啟動 V12 機器人，且完全不需要管理員 `sudo` 權限。

---

## 🌐 三、 網頁監控與數據同步

1.  **Dashboard 儀表板**：啟動後打開瀏覽器訪問 `http://127.0.0.1:5000`。
2.  **績效查看**：此儀表板會自動拉取並顯示包含其他節點在內的全局合併歷史績效，讓大家直接檢視多機協同訓練的成果。
3.  **上傳日誌進行 AI 進化**：
    定期在專案目錄下執行 Git 推送，回傳訓練數據給 GitHub 大腦：
    ```bash
    git pull --rebase origin main
    git add journal_*.json
    git commit -m "Upload training data from NODE_NAME"
    git push origin main
    ```

---

## 🤖 To the AI Agent on this Machine:
If you are an AI assistant managing this repository:
1.  Verify the `NODE_NAME` variable in `server_core/config.py` is distinct and configured specifically for this physical machine.
2.  Do not commit local active state files `active_trades_*.json` to Git. Only commit `journal_*.json` output files.
3.  Use `run_bot.bat` (Windows) or `run_bot.sh` (Mac) to spawn the bot environment. Do not install system-wide Python dependencies.
