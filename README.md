# OKX Harmonic AI Agent Bot

這是一個專門為 OKX 合約交易設計的量化交易機器人，整合了多種量化策略、動態風險管理（包含移動止損保護）以及基於歷史交易日誌的自適應 AI 最佳化最佳參數機制（Auto-Tuning）。

本項目已將龐大單一的 `server.py` 全面重構為模組化的 Python 套件結構，提高了程式碼的易讀性與維護性。

---

## 📁 專案架構與模組職責

所有核心邏輯都位於 `server_core/` 目錄下：

*   **`server.py` (主入口點)**：極簡的主入口。負責初始化全局狀態、取得端口鎖、啟動後台策略線程與 Flask API 網頁服務，並提供與測試相容的全局變數/函數重映射。
*   **`server_core/config.py`**：保存所有系統常數，包含 API 密鑰、風險控制邊界、保本/移動止損參數及核心策略的預設配置。
*   **`server_core/state.py`**：維護所有執行緒安全的全局共享狀態快取與線程鎖（如 `active_trades`、`trade_journal` 以及交易標的預約鎖等）。
*   **`server_core/utils.py`**：提供基礎的數值轉換、時間轉換、原子性 JSON 寫入（防止寫入中斷損毀）及多開守護程序。
*   **`server_core/okx_client.py`**：負責 OKX CCXT 交換所物件初始化（支持 Sandbox 模擬環境）、主動拉取 K 線、倉位及帳戶餘額，並包含歷史已實現交易的快取機制。
*   **`server_core/strategies.py`**：核心策略邏輯與技術指標（ADX, MACD, KC），包含進場檢驗機制 (`evaluate_mode_gate`)、AI 調諧器 (`auto_tune_strategy_params`) 以及日報表生成。
*   **`server_core/execution.py`**：負責與 OKX API 進行下單互動，包括 FOK 進場單、雙向 OCO 移動止損與止盈保護單的掛載與動態修改。
*   **`server_core/engine.py`**：主控後台背景迴圈，負責管理 4 大策略在各週期的實時市場掃描，以及定期的帳戶、倉位動態移動止損同步線程。
*   **`server_core/web_server.py`**：Flask 網頁伺服器，定義了與前端 UI 介面交互的 REST API 路由。

---

## 🚀 快速開始

### 1. 安裝依賴環境
本項目基於 Python 3.12+ 開發，請確保您已安裝相關依賴套件（CCXT、Flask、Pandas 等）：
```bash
pip install ccxt flask pandas werkzeug
```

### 2. 配置帳戶憑證
編輯 [**`server_core/config.py`**](file:///d:/okx/harmonic_agent/server_core/config.py)，填入您的 OKX API 密鑰與帳戶設定：
```python
OKX_API_KEY = '您的_API_KEY'
OKX_SECRET = '您的_SECRET_KEY'
OKX_PASSWORD = '您的_API_PASSWORD'
```

### 3. 切換模擬盤與實盤
機器人預設開啟模擬盤（Sandbox Mode）。若需調整為實盤，請至 [**`server_core/okx_client.py`**](file:///d:/okx/harmonic_agent/server_core/okx_client.py) 註解掉以下設定：
```python
# 啟用模擬盤 (Simulated Trading)
okx.set_sandbox_mode(True)
```

### 4. 啟動交易機器人
於專案根目錄下直接執行：
```bash
python server.py
```
啟動後會出現以下日誌，並開始自動輪詢熱門交易對與計算指標：
```text
[MacroSniper] Engine Started. (15m candles, 1h trend filter)
[MeanReversion] Engine Started. (5m candles, 15m trend filter)
...
Server running on http://127.0.0.1:5000
```
開啟瀏覽器並訪問 `http://127.0.0.1:5000` 即可打開視覺化控制面板。

---

## 📈 運行的策略與時間週期

系統啟動時會默認啟動 4 個獨立的策略線程，涵蓋了不同的市場週期與邏輯：

1.  **`MacroSniper`** (`15m` K線，`1h` 趨勢過濾)：大週期趨勢跟隨。
2.  **`MeanReversion`** (`5m` K線，`15m` 趨勢過濾)：通道突破極值回歸。
3.  **`Contrarian`** (`5m` K線，`15m` 趨勢過濾)：極端超買超賣反轉。
4.  **`SqueezeHunter`** (`15m` K線，`1h` 趨勢過濾)：波動率擠壓釋放突破。

---

## 🛡️ 移動保護與止損邏輯 (Trailing Protection)
機器人內建高精度的動態風險控制機制，在後台線程中對當前倉位進行實時監控：
*   **0.25R 保本鎖定**：當浮動利潤達到 0.25 倍風險收益比 (R) 時，機器人將止損價自動拉近至保本價（進場價 + 手續費安全邊界）。
*   **0.55R 鎖定部分利潤**：當浮盈達到 0.55R，自動鎖定部分浮盈。
*   **1R 以上動態追蹤**：當浮盈超過 1R 後，追蹤止損將以歷史最高利潤點（Highest R）回吐 0.35R 作為動態跟隨止損線。

---

## 🧪 自動化測試
本項目包含完整的單元測試套件，涵蓋了倉位週期狀態、自適應離場等功能的正確性驗證。

執行單元測試：
```bash
python test_strategy_v6.py
```
