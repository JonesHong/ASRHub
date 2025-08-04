# ASR_Hub 第一階段工作清單

## 📋 階段目標
建立專案基礎架構，完成配置管理系統，初始化日誌系統，確保所有基礎設施就緒。

## ✅ 工作項目清單

### 1. 專案基礎設置（Prerequisites）
- [x] 1.1 建立專案根目錄 `/ASRHub`
- [x] 1.2 初始化 Git 儲存庫
- [x] 1.3 建立虛擬環境 `python -m venv venv`
- [x] 1.4 啟動虛擬環境

### 2. 建立專案檔案結構
- [x] 2.1 建立部分的目錄結構（根據 PROJECT_STRUCTURE.md），忽略 tests/, docs/, docker/, scripts/ 等目錄，保留以下結構：
  ```
  - config/
  - src/
    - config/
    - core/
    - api/（含所有子目錄）
    - pipeline/operators/（含所有子目錄）
    - providers/（含所有子目錄）
    - stream/
    - utils/
    - models/
  ```
- [x] 2.2 在空目錄中建立 `.gitkeep` 檔案
- [x] 2.3 建立所有必要的 `__init__.py` 檔案

### 3. 建立專案基礎檔案
- [x] 3.1 建立 `.gitignore` 檔案（包含 config/base.yaml 等敏感資料）
- [x] 3.2 建立 `requirements.txt`（包含 yaml2py==0.2.0、pretty-loguru==1.1.3 及其他依賴）
- [x] 3.3 建立 `setup.py` 專案安裝配置
- [x] 3.4 建立 `pyproject.toml` Python 專案配置
- [x] 3.5 建立 `LICENSE` 檔案（MIT 授權）
- [x] 3.6 建立 `README.md` 專案說明文件
- [x] 3.7 建立 `Makefile`（開發工具指令）

### 4. 安裝核心套件
- [x] 4.1 安裝 yaml2py：`pip install yaml2py`
- [x] 4.2 安裝 pretty-loguru：`pip install pretty-loguru`
- [x] 4.3 安裝其他基礎依賴：`pip install pyyaml watchdog python-dotenv click rich art`

### 5. 建立 YAML 配置系統
- [x] 5.1 建立 `config/base.sample.yaml` 範例配置檔（包含所有配置選項）
  - 系統基本設定（name, version, mode, debug）
  - 日誌設定（path, rotation, retention, level, format）
  - API 設定（http_sse, websocket, grpc, redis）
  - Pipeline 設定（operators, buffer_size, sample_rate）
  - Provider 設定（default, whisper, funasr, vosk 等）
  - 喚醒詞設定（enabled, type, keywords, sensitivity）
  - 串流設定（silence_timeout, manual_termination, busy_mode）
- [x] 5.2 複製 `base.sample.yaml` 為 `base.yaml`
- [x] 5.3 編輯 `base.yaml` 設定實際配置值（特別是敏感資料）

### 6. 使用 yaml2py 生成配置類別
- [x] 6.1 執行 yaml2py 生成配置類別：`yaml2py --config config/base.yaml --output ./src/config`
- [x] 6.2 確認生成檔案：
  - `src/config/__init__.py`
  - `src/config/schema.py`（配置類別定義）
  - `src/config/manager.py`（ConfigManager 單例）

### 7. 建立日誌系統
- [x] 7.1 建立 `src/utils/logger.py`
  - 匯入 pretty_loguru 和 ConfigManager
  - 實作 `get_logger(module_name: str)` 函式
  - 根據環境選擇配置模板（development/production）
  - 從 ConfigManager 讀取日誌配置

### 8. 建立核心模組基礎檔案
- [x] 8.1 建立 `src/core/asr_hub.py`（主要入口類別）
  - 匯入 ConfigManager 和 logger
  - 建立 ASRHub 類別
  - 初始化配置讀取
  - 使用 pretty-loguru 輸出啟動訊息
- [x] 8.2 建立 `src/core/exceptions.py`（自定義異常類別）
- [x] 8.3 建立 `src/core/session_manager.py`（Session 管理骨架）
- [x] 8.4 建立 `src/core/fsm.py`（有限狀態機骨架）

### 9. 建立基礎類別檔案
- [x] 9.1 建立 `src/api/base.py`（API 基礎類別）
- [x] 9.2 建立 `src/pipeline/base.py`（Pipeline 基礎類別）
- [x] 9.3 建立 `src/pipeline/operators/base.py`（Operator 基礎類別）
- [x] 9.4 建立 `src/providers/base.py`（Provider 基礎類別）


### 12. 版本控制
- [x] 12.1 執行 `git add .`
- [x] 12.2 執行 `git commit -m "feat: 完成第一階段基礎架構建置"`
- [x] 12.3 建立標籤 `git tag v0.1.0-alpha`

## 🔍 驗收標準
1. ✅ 所有目錄和檔案結構已建立
2. ✅ yaml2py 和 pretty-loguru 已安裝並可正常使用
3. ✅ 配置系統可正確載入 YAML 並生成型別安全的類別
4. ✅ 日誌系統可正確初始化並輸出美化日誌
5. ✅ 環境變數替換功能正常運作

## 📝 注意事項
1. 確保 `config/base.yaml` 不被提交到版本控制（已加入 .gitignore）
2. 所有敏感資料使用環境變數或在 base.yaml 中設定
3. 遵循 PRINCIPLE.md 中的所有開發原則
4. 使用 pretty-loguru 格式化所有日誌輸出
5. 確保型別安全，充分利用 yaml2py 生成的類別



---
建立時間：2025-07-24
最後更新：2025-07-24
負責人：ASR Hub Team