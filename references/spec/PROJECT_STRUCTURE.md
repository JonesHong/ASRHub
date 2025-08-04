# ASR_Hub 專案檔案架構

## 專案概述

ASR_Hub 是一個語音辨識中介系統，整合多種 ASR 服務提供商，提供統一的 API 介面。本文件詳細說明專案的檔案架構設計。

## 檔案架構

```
ASRHub/
├── README.md                        # 專案說明文件
├── SRS.md                          # 軟體需求規格說明書
├── PRINCIPLE.md                    # 開發原則指引
├── PROJECT_STRUCTURE.md            # 專案架構文件（本檔案）
├── LICENSE                         # 授權文件
├── requirements.txt                # Python 依賴管理
├── setup.py                        # 專案安裝配置
├── .gitignore                      # Git 忽略規則
├── pyproject.toml                  # Python 專案配置
│
├── config/                         # YAML 設定檔目錄
│   ├── base.yaml                   # 主要設定檔（實際使用，不要提交到版本控制）
│   ├── base.sample.yaml           # 設定範例檔案（提交到版本控制）
│   ├── base.dev.yaml              # 開發環境覆蓋設定（可選）
│   └── base.prod.yaml             # 生產環境覆蓋設定（可選）
│
├── src/                           # 原始碼主目錄
│   ├── __init__.py
│   │
│   ├── config/                    # yaml2py 生成的配置類別目錄
│   │   ├── __init__.py           # 自動生成
│   │   ├── schema.py             # 自動生成的配置類別定義
│   │   └── manager.py            # 自動生成的 ConfigManager（單例）
│   │
│   ├── core/                      # 核心模組
│   │   ├── __init__.py
│   │   ├── asr_hub.py            # 主要入口類別
│   │   ├── session_manager.py    # Session 管理
│   │   ├── fsm.py               # 有限狀態機實作
│   │   └── exceptions.py         # 自定義異常
│   │
│   ├── api/                      # API 層（多協定支援）
│   │   ├── __init__.py
│   │   ├── base.py              # API 基礎類別
│   │   ├── http_sse/            # HTTP SSE 實作
│   │   │   ├── __init__.py
│   │   │   ├── server.py
│   │   │   └── handlers.py
│   │   ├── websocket/           # WebSocket 實作
│   │   │   ├── __init__.py
│   │   │   ├── server.py
│   │   │   └── handlers.py
│   │   ├── socketio/            # Socket.io 實作
│   │   │   ├── __init__.py
│   │   │   ├── server.py
│   │   │   └── handlers.py
│   │   ├── grpc/                # gRPC 實作
│   │   │   ├── __init__.py
│   │   │   ├── server.py
│   │   │   ├── proto/          # Protocol Buffers 定義
│   │   │   └── handlers.py
│   │   └── redis/               # Redis 實作
│   │       ├── __init__.py
│   │       ├── client.py
│   │       └── handlers.py
│   │
│   ├── pipeline/                 # Pipeline 處理模組
│   │   ├── __init__.py
│   │   ├── base.py              # Pipeline 基礎類別
│   │   ├── operators/           # 各種 Operator 實作
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Operator 基礎類別
│   │   │   ├── vad/            # VAD 模組
│   │   │   │   ├── __init__.py
│   │   │   │   ├── webrtc_vad.py
│   │   │   │   └── silero_vad.py
│   │   │   ├── denoise/        # 降噪模組
│   │   │   │   ├── __init__.py
│   │   │   │   ├── rnnoise.py
│   │   │   │   └── noisereduce.py
│   │   │   ├── sample_rate.py  # 取樣率調整
│   │   │   ├── voice_separation.py  # 人聲分離
│   │   │   ├── recording.py    # 錄音功能
│   │   │   ├── format_conversion.py # 格式轉換
│   │   │   └── wakeword/       # 喚醒詞偵測
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── openwakeword.py
│   │   │       └── asr_keyword.py
│   │   ├── validator.py         # Pipeline 組合驗證
│   │   └── manager.py           # Pipeline 管理器
│   │
│   ├── providers/                # ASR Provider 模組
│   │   ├── __init__.py
│   │   ├── base.py              # Provider 基礎類別
│   │   ├── provider_pool.py     # Provider 池化實作
│   │   ├── funasr/              # FunASR 實作
│   │   │   ├── __init__.py
│   │   │   └── provider.py
│   │   ├── whisper/             # Local Whisper 實作
│   │   │   ├── __init__.py
│   │   │   └── provider.py
│   │   ├── vosk/                # Vosk 實作
│   │   │   ├── __init__.py
│   │   │   └── provider.py
│   │   ├── google_stt/          # Google STT API 實作
│   │   │   ├── __init__.py
│   │   │   └── provider.py
│   │   ├── openai/              # OpenAI API 實作
│   │   │   ├── __init__.py
│   │   │   └── provider.py
│   │   └── manager.py           # Provider 管理器（支援池化）
│   │
│   ├── stream/                   # 串流處理模組
│   │   ├── __init__.py
│   │   ├── audio_stream.py      # 音訊串流處理
│   │   ├── buffer_manager.py    # Buffer 管理
│   │   └── stream_controller.py # 串流控制（timeout、終止）
│   │
│   ├── utils/                    # 工具模組
│   │   ├── __init__.py
│   │   ├── logger.py            # pretty-loguru 日誌配置
│   │   ├── audio_utils.py      # 音訊處理工具
│   │   ├── text_utils.py       # 文字處理（拼音、同音字等）
│   │   └── validators.py       # 各種驗證工具
│   │
│   └── models/                   # 資料模型
│       ├── __init__.py
│       ├── audio.py             # 音訊相關模型
│       ├── transcript.py        # 轉譯結果模型
│       └── session.py           # Session 模型
│
├── tests/                        # 測試目錄
│   ├── __init__.py
│   ├── conftest.py              # pytest 配置
│   ├── unit/                    # 單元測試
│   │   ├── __init__.py
│   │   ├── test_core/
│   │   ├── test_pipeline/
│   │   ├── test_providers/
│   │   └── test_utils/
│   ├── integration/             # 整合測試
│   │   ├── __init__.py
│   │   ├── test_api/
│   │   └── test_stream/
│   └── fixtures/                # 測試資料
│       ├── audio/
│       └── config/
│
├── models/                       # 模型檔案目錄（喚醒詞模型等）
│   ├── wakeword/
│   └── vad/
│
├── logs/                        # 日誌目錄
│   └── .gitkeep
│
├── recordings/                  # 錄音檔案目錄
│   └── .gitkeep
│
├── docs/                        # 文件目錄
│   ├── api/                    # API 文件
│   │   ├── openapi.yaml       # OpenAPI 規格
│   │   └── README.md
│   ├── architecture/           # 架構文件
│   │   ├── system_design.md
│   │   └── diagrams/
│   ├── guides/                 # 使用指南
│   │   ├── quickstart.md
│   │   ├── configuration.md
│   │   └── deployment.md
│   └── development/           # 開發文件
│       ├── contributing.md
│       └── coding_standards.md
│
├── scripts/                    # 工具腳本
│   ├── generate_config.py     # 生成設定檔
│   ├── validate_pipeline.py   # 驗證 Pipeline 配置
│   └── convert_models.py      # 模型轉換工具
│
└── docker/                     # Docker 相關檔案
    ├── Dockerfile
    ├── docker-compose.yml
    └── .dockerignore
```

## 模組說明

### 1. **config/** - 配置管理
- 採用單一 YAML 檔案（base.yaml）集中管理所有設定
- 提供 base.sample.yaml 作為設定範例（包含所有可用選項和說明）
- 支援環境變數替換（使用 ${VAR_NAME} 或 ${VAR_NAME:default} 語法）
- 敏感資料自動遮罩（password、secret、token、key 等）
- 可選的環境覆蓋檔案（base.dev.yaml、base.prod.yaml）供特殊需求使用

### 2. **src/config/** - yaml2py 生成目錄
- 使用 yaml2py 自動生成型別安全的 Python 類別
- 提供 ConfigManager 單例模式，全域共享配置
- 支援配置熱重載（開發環境）
- IDE 自動完成和型別提示支援

### 3. **src/core/** - 核心模組
- `asr_hub.py`: 系統主要入口，協調各模組運作
- `session_manager.py`: 管理多個並行的 ASR session
- `fsm.py`: 實作有限狀態機（IDLE、LISTENING、BUSY）
- `exceptions.py`: 定義系統專用異常類別

### 4. **src/api/** - API 層
- 支援多種通訊協定（HTTP SSE、WebSocket、Socket.io、gRPC、Redis）
- 每種協定獨立實作，共用基礎類別
- 統一的控制指令介面（start、stop、status、busy_start、busy_end）

### 5. **src/pipeline/** - Pipeline 處理
- 採用 RxJS 風格的流式架構
- 模組化的 Operator 設計，易於擴展
- 包含組合驗證機制，確保 Pipeline 配置正確
- 支援資源預警和最佳實踐檢查

### 6. **src/providers/** - ASR Provider
- 統一的 Provider 介面
- 支援多種 ASR 引擎（FunASR、Whisper、Vosk 等）
- Provider Manager 負責動態路由和錯誤處理
- **Provider 池化支援**：
  - `provider_pool.py`: 實作動態 Provider 實例池
  - 支援並發處理多個請求
  - 自動擴縮容（min_size 到 max_size）
  - 健康檢查和故障恢復機制
  - 完整的監控指標和資源管理

### 7. **src/stream/** - 串流處理
- 處理音訊串流的接收和分發
- Buffer 管理確保資料完整性
- 串流控制實作 timeout 和手動終止機制

### 8. **src/utils/** - 工具模組
- 整合 pretty-loguru 的日誌系統（美化輸出、環境感知配置）
- 音訊和文字處理工具函式
- 各種驗證和輔助功能

## 設計特點

### 1. **模組化設計**
- 符合 SoC（關注點分離）原則
- 每個模組職責單一明確（SRP）
- 透過介面和抽象類別實現低耦合

### 2. **可擴展性**
- 新增 Provider 只需實作基礎類別
- 新增 Operator 只需繼承 base operator
- 新增通訊協定只需實作 API 基礎類別

### 3. **可維護性**
- 清晰的目錄結構
- 完整的測試覆蓋
- 詳細的文件說明

### 4. **遵循開發原則**
- KISS: 保持簡單直觀的設計
- YAGNI: 聚焦核心功能，避免過度設計
- DRY: 抽取共用邏輯到 utils 和 base 類別
- SOLID: 透過介面和抽象實現五大原則

## 開發流程建議

1. **初始化專案與配置管理**
   ```bash
   # 建立配置目錄
   mkdir -p config
   
   # 建立設定範例檔案（base.sample.yaml）
   cat > config/base.sample.yaml << 'EOF'
   # 系統基本設定
   system:
     name: "ASR_Hub"
     version: "0.1.0"
     mode: ${APP_ENV:development}  # development, production, testing
     debug: ${DEBUG:true}
     
   # 日誌設定
   logging:
     path: "./logs"
     rotation: "100 MB"
     retention: "30 days"
     level: ${LOG_LEVEL:INFO}
     format: "detailed"  # detailed, simple, json
     
   # API 設定
   api:
     http_sse:
       host: ${API_HOST:0.0.0.0}
       port: ${API_PORT:8080}
       cors_enabled: true
       max_connections: 100
     websocket:
       enabled: false
       port: ${WS_PORT:8081}
     grpc:
       enabled: false
       port: ${GRPC_PORT:50051}
       
   # Pipeline 設定
   pipeline:
     default_sample_rate: 16000
     buffer_size: 4096
     operators:
       vad:
         enabled: true
         type: "webrtc"  # webrtc, silero
         sensitivity: 0.5
       denoise:
         enabled: false
         type: "rnnoise"
       sample_rate_adjustment:
         enabled: true
         target_rate: 16000
         
   # Provider 設定
   providers:
     default: "whisper"
     whisper:
       enabled: true
       model_size: ${WHISPER_MODEL:base}
       language: "zh"
       device: ${WHISPER_DEVICE:cpu}
       compute_type: "float32"
       # Provider 池化配置（可選）
       pool:
         enabled: true
         min_size: 2
         max_size: 5
         acquire_timeout: 30.0
         idle_timeout: 300.0
         health_check_interval: 60.0
     funasr:
       enabled: false
       model: "paraformer"
       # 池化配置可按需添加
     vosk:
       enabled: false
       model_path: "./models/vosk"
       # 池化配置可按需添加
       
   # 喚醒詞設定
   wakeword:
     enabled: false
     type: "asr_keyword"  # asr_keyword, openwakeword
     keywords: ["你好小明", "Hey Assistant"]
     sensitivity: 0.5
     
   # 串流設定
   stream:
     silence_timeout: 3.0
     manual_termination: true
     busy_mode:
       enabled: true
       continue_listening: true
       
   # 資料庫設定（範例）
   database:
     host: ${DB_HOST:localhost}
     port: ${DB_PORT:5432}
     name: ${DB_NAME:asr_hub}
     user: ${DB_USER:postgres}
     password: ${DB_PASSWORD}  # 敏感資料，會自動遮罩
   EOF

   # 複製範例檔案為實際配置檔
   cp config/base.sample.yaml config/base.yaml
   
   # 編輯 base.yaml，設定實際的配置值（特別是敏感資料）
   # vim config/base.yaml
   
   # 將 base.yaml 加入 .gitignore（避免提交敏感資料）
   echo "config/base.yaml" >> .gitignore
   
   # 使用 yaml2py 生成型別安全的配置類別
   yaml2py --config config/base.yaml --output ./src/config
   ```

2. **安裝依賴**
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. **執行測試**
   ```bash
   pytest tests/ -v --cov=src
   ```

4. **啟動服務**
   ```bash
   python -m src.core.asr_hub
   ```

## 部署考量

1. **容器化部署**
   - 使用 Docker 進行容器化
   - docker-compose 支援多服務編排

2. **日誌管理**
   - 使用 pretty-loguru 格式化輸出（Rich blocks、ASCII art headers）
   - 環境感知配置（開發/生產模式自動切換）
   - 支援日誌輪轉和遠端收集

3. **監控與可觀察性**
   - 整合 metrics 收集
   - 支援分散式追蹤

## 後續擴展

1. **效能優化**
   - 加入快取機制
   - 實作連線池管理

2. **安全性增強**
   - API 認證機制
   - 資料加密傳輸

3. **高可用性**
   - 支援水平擴展
   - 實作健康檢查機制

## 配置管理策略

### 為什麼使用單一 YAML 檔案？

yaml2py 的設計理念是生成一個集中的 ConfigManager，因此最佳實踐是使用單一 YAML 檔案管理所有配置：

1. **型別安全**：所有配置在一個地方，yaml2py 可以生成完整的型別定義
2. **IDE 支援**：單一 ConfigManager 提供完整的自動完成功能
3. **維護簡單**：避免多檔案同步和合併的複雜性
4. **熱重載**：單一檔案更容易實現配置熱重載

### 配置組織建議

```yaml
# config/base.yaml - 使用註解和分組組織配置
# ===== 系統核心設定 =====
system:
  # 基本資訊...

# ===== 外部服務設定 =====
api:
  # 各種 API 配置...

# ===== 功能模組設定 =====
pipeline:
  # Pipeline 相關配置...

providers:
  # Provider 相關配置...
```

### 環境差異處理

由於所有配置都在 YAML 中管理，環境變數主要用於：

1. **切換環境模式**
   ```bash
   export APP_ENV=development  # 或 production
   ```

2. **覆蓋特定值**（只在需要時使用）
   ```bash
   export API_PORT=9090  # 臨時改變 port
   export LOG_LEVEL=DEBUG  # 臨時開啟 debug
   ```

3. **提供敏感資料**（如果不想寫在 YAML 中）
   ```bash
   export DB_PASSWORD=my_secure_password
   ```

大部分配置應該直接在 base.yaml 中設定，環境變數只作為補充。

## 配置與日誌使用範例

### 使用 yaml2py 生成的配置
```python
# src/core/asr_hub.py
from src.config.manager import ConfigManager
from src.utils.logger import get_logger

# 獲取配置（單例模式）
config = ConfigManager()
logger = get_logger("core")

class ASRHub:
    def __init__(self):
        # 型別安全的配置存取 - 所有配置都在同一個 ConfigManager 中
        self.app_name = config.system.name
        self.version = config.system.version
        self.debug = config.system.debug
        
        # 存取不同模組的配置
        self.api_port = config.api.http_sse.port
        self.default_provider = config.providers.default
        self.sample_rate = config.pipeline.default_sample_rate
        self.wakeword_enabled = config.wakeword.enabled
        
        # 使用 pretty-loguru 美化輸出
        logger.ascii_header("ASR HUB", font="slant")
        logger.block(
            "系統初始化",
            [
                f"應用名稱：{self.app_name}",
                f"版本：{self.version}",
                f"模式：{config.system.mode}",
                f"API 埠號：{self.api_port}",
                f"預設 Provider：{self.default_provider}",
                f"喚醒詞：{'啟用' if self.wakeword_enabled else '停用'}"
            ],
            border_style="blue"
        )
```

### 日誌系統設置
```python
# src/utils/logger.py
from pretty_loguru import create_logger, ConfigTemplates
from src.config.manager import ConfigManager

config = ConfigManager()

def get_logger(module_name: str):
    """為特定模組建立 logger"""
    # 根據環境選擇配置模板
    if config.system.mode == "development":
        logger_config = ConfigTemplates.development()
    else:
        logger_config = ConfigTemplates.production()
    
    # 自訂配置
    logger_config.log_path = config.logging.path
    logger_config.rotation = config.logging.rotation
    logger_config.retention = config.logging.retention
    
    return create_logger(f"asr_hub.{module_name}", config=logger_config)
```

### 配置檔案最佳實踐

```bash
# 開發流程
1. 從 base.sample.yaml 複製建立 base.yaml
2. 修改 base.yaml 中的實際配置值
3. 確保 base.yaml 在 .gitignore 中（保護敏感資料）
4. 只將 base.sample.yaml 提交到版本控制

# .gitignore 應包含
config/base.yaml
config/base.dev.yaml
config/base.prod.yaml

# 版本控制只包含
config/base.sample.yaml  # 包含所有配置選項和預設值
```

---

此架構設計遵循 PRINCIPLE.md 中的所有核心原則，並根據 SRS.md 的功能需求進行規劃，確保系統的可擴展性、可維護性和穩定性。