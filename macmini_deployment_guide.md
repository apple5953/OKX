# Mac Mini 部署指南與 AI Agent 注意事項 (Mac Mini Deployment & AI Sync Guide)

本指南旨在為您在 **Mac Mini** 上運行的 AI Agent（或開發人員）提供一份清晰的操作清單，以確保多台電腦並行訓練時，數據同步、OKX 模擬盤接口與環境配置完全正確。

---

## 📌 一、 關於 OKX 模擬盤與平倉紀錄的運作機制

> [!IMPORTANT]
> **「為什麼不直接從 OKX 抓取統一的平倉紀錄，而是分開儲存 `journal_*.json`？」**
> 
> 1. **本地 AI 計算與策略狀態**：OKX 模擬盤只保存交易所委託與持倉的原始數據，但不保存「它是哪個 AI 模式開的」、「開倉時的信心指數是多少」、「當時的進場容差是多少」等策略背景數據。這些自適應優化所需的指標，必須依賴本地的 JSON 日誌來計算。
> 2. **避免持倉與文件覆蓋**：如果多台電腦直接共享同一個 `active_trades.json`，在 Git 拉取/推送時會將對方的持倉強制覆蓋，導致機器人在檢查持倉狀態時發生嚴重錯誤。
> 3. **AI 雲端融合**：每台 Mac Mini 各自記錄自己的平倉日誌（例如 `journal_macmini_02.json`）並上傳。GitHub Actions 會在雲端將它們**全部合併**，為您算出一套全域最優的 `global_optimizer.json` 參數。

---

## ⚙️ 二、 Mac Mini 部署與同步三步驟

當您在新的 Mac Mini 上啟動 AI Agent 時，請給它以下指示：

### 1. 克隆代碼與安裝環境
在 Mac Mini 的終端機執行：
```bash
# 克隆您的 GitHub 私有倉庫
git clone https://github.com/apple5953/OKX.git
cd OKX

# 安裝 Python 依賴套件（CCXT、Flask、Pandas）
pip install pandas ccxt flask urllib3
```

### 2. 修改節點配置 (最關鍵的一步)
打開 `server_core/config.py`，請 AI Agent 修改或確認以下參數：

```python
# 1. 設置這台 Mac Mini 專屬的節點名稱（例如 macmini_02）
NODE_NAME = 'macmini_02'

# 2. 確認 OKX 模擬盤 API 金鑰已填寫（如多台共用同一個帳號，金鑰保持一致即可）
OKX_API_KEY = '您的 API KEY'
OKX_SECRET = '您的 SECRET'
OKX_PASSWORD = '您的密碼'
```
> [!WARNING]
> **多台共用同一個 OKX 帳號的潛在風險**：
> 如果兩台電腦同時在 15m 週期掃描到了 `BTC/USDT` 的同一個信號，它們可能會在同一個 OKX 帳號中重複開單，或者互相影響持倉。
> *   **建議方案**：為不同的 Mac Mini 分配不同的**子帳號 (Sub-Account)** API 金鑰；或者在 `config.py` 中讓不同電腦掃描**不同的標的物名單 (Symbols)**，實現分散探索。

### 3. 背景啟動與守護
在 Mac Mini 終端機背景啟動伺服器：
```bash
python server.py
```
若希望機器人 24 小時不中斷運行且重啟自動啟動，建議使用 `pm2`：
```bash
# 安裝 pm2 (需要先安裝 Node.js)
npm install -g pm2
# 啟動並命名為 okx-bot
pm2 start server.py --name "okx-bot"
# 保存啟動配置
pm2 save
pm2 startup
```

---

## 🤖 三、 給 Mac Mini 上 AI Agent 的 Prompt 指令

當您在新電腦上與 AI Agent 對話時，可以直接複製並發送以下指令給它：

> **「你現在是這台 Mac Mini 上的量化機器人助手。請檢查目前的目錄，並完成以下任務：**
> 1. 確認 `server_core/config.py` 中的 `NODE_NAME` 已設置為此機專屬的名稱（如 `macmini_02`），並確認 `TRADE_FILE` 與 `JOURNAL_FILE` 正確引用了該名稱。
> 2. 確認本地已安裝 `ccxt`、`pandas`、`flask` 等庫，嘗試運行 `python test_strategy_v6.py` 確保單元測試 100% 通過。
> 3. 確認 Git 已連結至 `https://github.com/apple5953/OKX.git` 倉庫。
> 4. 啟動 `server.py`，並確認本機的網頁 UI（5017 或指定端口）可以正常展示本會話的統計與全域的歷史平倉紀錄。」

---

## 📈 四、 定期數據同步命令 (每週或每天執行一次)

在 Mac Mini 上運行一段時間後，請執行以下命令以將您的訓練數據上報至 GitHub，讓中央大腦進行參數優化：

```bash
git pull --rebase origin main
git add journal_macmini_*.json
git commit -m "macmini_02: Upload training feedback"
git push origin main
```
執行後，GitHub Actions 將會自動重新計算最新的最優參數，並在下一次自動 Pull 後更新您所有 Mac Mini 的開單 DNA！
