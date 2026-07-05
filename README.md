# OKX Harmonic Trading Agent - 分布式 AI 訓練中心 (Multi-Node AI Training Center)

本專案是一個基於 **OKX 模擬盤 (Demo Trading)** 的分布式 AI 諧波交易機器人系統。支持多台設備（例如 Mac Mini、雲端伺服器）並行掃描、模擬交易與數據採集，並通過 GitHub 進行去中心化參數聚合與 AI 自適應優化。

> **To the AI Agent reading this README on a new device:**
> Please read the instructions below carefully to initialize, configure, and safely run this node without causing Git conflicts or account margin overlaps.

---

## 🛠️ 一、 系統架構與去中心化學習機制 (Decentralized Learning)

本系統採用 **「Master-Slave 參數伺服器架構 (GitHub-based Parameter Server)」**，實現無衝突的分布式多機訓練：

1. **獨立文件隔離（無衝突設計）**：
   每台設備（Node）使用專屬的 `NODE_NAME`（例如 `macmini_01`, `macmini_02`）。
   * 本地持倉狀態保存於：`active_trades_<NODE_NAME>.json` (已被 Git 忽略，防止跨設備覆蓋)。
   * 本地平倉日誌保存於：`journal_<NODE_NAME>.json` (會提交推送至 GitHub)。
2. **AI 全局大腦（GitHub Actions）**：
   GitHub Actions 工作流配置在 `.github/workflows/optimize.yml`，**每天整點自動啟動運行 24 次**。它會：
   * 讀取並合併倉庫中所有的 `journal_*.json` 日誌。
   * 全局執行 AI 調參演算法，為 4 個策略計算最新最優的 `sl_atr`, `tp_atr`, `confidence_weight` 等。
   * 將最優參數寫入 `global_optimizer.json` 並推回倉庫。
3. **設備端自動同步**：
   各設備定時拉取（Git Pull）代碼，當檢測到 `global_optimizer.json` 時，策略引擎會自動載入雲端最新最優的參數 DNA，使全網機器人越跑越聰明。

---

## ⚙️ 二、 邊緣節點（新電腦/Mac Mini）部署清單

當您在新的 Mac Mini 或設備上部署時，請按照以下步驟操作：

### 1. 複製倉庫與安裝環境
```bash
# 複製項目倉庫
git clone https://github.com/apple5953/OKX.git
cd OKX

# 安裝 Python 依賴庫 (包含 ccxt 交易所接口、pandas 數據庫、flask UI)
pip install pandas ccxt flask urllib3
```

### 2. 修改節點配置 (`server_core/config.py`)
請確認或修改 `server_core/config.py` 中的以下參數：
*   **`NODE_NAME`**：設置為此設備專屬的代號（例如：`'macmini_02'`）。此設定會自動更改對應的 `active_trades` 和 `journal` 檔名。
*   **OKX API 金鑰**：填寫您的 OKX 模擬盤 API 金鑰（`OKX_API_KEY`, `OKX_SECRET`, `OKX_PASSWORD`）。
*   *提示：如果多台電腦使用同一個 OKX 帳號，為避免開倉衝突或保證金過載，建議在 `config.py` 中分配不同的交易對名單 (Symbols)，或使用 OKX 子帳號 (Sub-Account) API 金鑰。*

### 3. 運行單元測試
在啟動前，請執行以下命令以驗證策略邏輯與 API 連接正常：
```bash
python test_strategy_v6.py
```
*(必須看到所有測試通過：`Ran 16 tests ... OK`)*

### 4. 啟動機器人與 Dashboard
在終端機啟動：
```bash
python server.py
```
*   **網頁 UI 儀表板**：瀏覽器打開 `http://127.0.0.1:5000` 即可實時檢視。
*   此儀表板已配置為顯示**全局合併歷史績效**。您可以在上面直接看到多台電腦累積下來的訓練勝率與損益。

---

## 🔄 三、 數據回報與同步指令 (Daily / Weekly Sync)

為了將這台電腦採集到的交易回報給 GitHub 中央大腦進行重新擬合優化，請定期（如每天或每週）在項目目錄下執行以下命令：

```bash
# 1. 拉取最新參數與其它節點的日誌
git pull --rebase origin main

# 2. 提交本機專屬的平倉日誌
git add journal_macmini_*.json
git commit -m "Upload training feedback from NODE_NAME"

# 3. 推送上傳至 GitHub
git push origin main
```
推送完成後，GitHub Actions 雲端大腦會自動在下一個整點讀取您的日誌，將最新的獲利 DNA 參數更新至 `global_optimizer.json`。

---

## 🤖 To the AI Agent on this Machine:
If you are an AI assistant managing this repository:
1. Ensure `NODE_NAME` is customized for this machine before startup to prevent filesystem conflicts.
2. Ensure you never commit `active_trades_*.json` to Git (it is strictly for local state management).
3. Check the heartbeat logs of `server.py` regularly to monitor execution and trailing stop updates.
