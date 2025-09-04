# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASRHub is an enterprise-grade unified speech recognition middleware system that integrates multiple ASR service providers through a single API interface. The system adopts a stateless service architecture, supporting various communication protocols and advanced audio processing capabilities.

### Core Architecture
- **Event-Driven Architecture**: Combined with Redux-like state management pattern
- **Provider Pool Management**: Parallel processing for multiple sessions, maximizing hardware resource utilization
- **Stateless Services**: Simple and clear functional composition, each service does one thing well
- **Audio Processing Pipeline**: Raw Audio → Convert (16kHz) → Queue → Buffer → WakeWord → VAD → ASR

## Development Commands

### Setup and Configuration
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install -e .  # Development mode installation

# Install PyTorch (with CUDA support)
pip install torch==2.6.0+cu126 torchvision==0.21.0+cu126 torchaudio==2.6.0 --extra-index-url https://download.pytorch.org/whl/cu126

# Setup configuration (IMPORTANT!)
cp config/config.sample.yaml config/config.yaml
# Edit config/config.yaml with your settings

# Generate configuration classes from YAML
yaml2py --config config/config.yaml --output ./src/config

# Alternative using Makefile
make install
make yaml2py
```

### System Dependencies
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg portaudio19-dev

# macOS
brew install ffmpeg portaudio

# Windows
# Download FFmpeg: https://ffmpeg.org/download.html
# PyAudio needs Visual C++ Build Tools
```

### Running the Application
```bash
# Run the main application
python main.py
```

## Architecture Overview

### Core Design Principles
- **KISS (Keep It Simple, Stupid)**: Keep it simple, avoid over-engineering
- **Stateless Services**: All services are stateless and can handle multiple sessions in parallel
- **Single Responsibility**: Each service does one thing and does it well
- **Composition Over Inheritance**: Build complex features using composition pattern
- **Direct Method Calls**: Services are imported and called directly in Effects
- **Module-level Singletons**: Use `SingletonMixin` inheritance for singletons, expose as module-level variables
- **Pool-based Scalability**: Provider instances are pooled for maximum hardware utilization
- **Pipeline Processing**: Audio flows through a well-defined processing pipeline

### Project Structure
```
ASRHub/
├── src/
│   ├── config/                    # yaml2py auto-generated configuration classes (DO NOT EDIT)
│   │   ├── manager.py            # ConfigManager singleton
│   │   └── schema.py             # Configuration schema definition
│   ├── core/                     # 🎯 Core system
│   │   ├── asr_hub.py           # System entry point and initialization
│   │   ├── audio_queue_manager.py   # Audio queue management (timestamp support)
│   │   ├── buffer_manager.py        # Buffer management (intelligent windowing)
│   │   └── fsm_transitions.py       # FSM state machine transition definitions
│   ├── api/                      # 📡 API protocol layer
│   │   ├── http_sse/            # HTTP SSE implementation
│   │   ├── webrtc/              # WebRTC implementation
│   │   ├── redis/               # Redis Pub/Sub implementation
│   │   ├── websocket/           # WebSocket implementation (planned)
│   │   ├── socketio/            # Socket.IO implementation (planned)
│   │   └── grpc/                # gRPC implementation (planned)
│   ├── service/                  # ⚙️ Stateless service layer
│   │   ├── audio_converter/     # 音訊格式轉換
│   │   │   ├── scipy_converter.py   # SciPy 轉換器（GPU 支援）
│   │   │   └── ffmpeg_converter.py  # FFmpeg 轉換器
│   │   ├── audio_enhancer.py    # 音訊增強（自動音量、動態壓縮）
│   │   ├── denoise/              # 降噪服務
│   │   │   └── deepfilternet_denoiser.py # DeepFilterNet 深度降噪
│   │   ├── vad/                  # 語音活動偵測
│   │   │   └── silero_vad.py    # Silero VAD 實現
│   │   ├── wakeword/             # 喚醒詞偵測
│   │   │   └── openwakeword.py  # OpenWakeWord 實現
│   │   ├── recording/            # 錄音服務
│   │   ├── microphone_capture/   # 麥克風擷取
│   │   └── timer/                # 計時服務
│   ├── provider/                 # 🎙️ ASR 提供者（注意：單數形式 provider）
│   │   ├── provider_manager.py  # Provider Pool 管理器（並行處理）
│   │   ├── whisper/             # Whisper 本地模型
│   │   ├── funasr/              # FunASR 實現
│   │   ├── vosk/                # Vosk 實現
│   │   ├── google_stt/          # Google STT API
│   │   └── openai/              # OpenAI Whisper API
│   ├── store/                    # 🗄️ PyStoreX 狀態管理
│   │   ├── main_store.py        # 全域 Store 實例
│   │   └── sessions/            # Session 管理
│   │       ├── sessions_state.py    # 狀態定義
│   │       ├── sessions_action.py   # Action 類型
│   │       ├── sessions_reducer.py  # Reducer 純函數
│   │       └── sessions_effect.py   # Effects 副作用處理
│   ├── interface/                # 📐 服務介面定義
│   └── utils/                    # 🛠️ 工具模組
│       ├── logger.py            # pretty-loguru 日誌系統
│       ├── id_provider.py       # UUID v7 ID 生成器
│       └── visualization/       # 視覺化工具
├── config/                       # ⚙️ 配置檔案
│   ├── config.yaml              # 主配置檔（不納入版控）
│   └── config.sample.yaml       # 配置範例
└── models/                       # 🧠 AI 模型檔案
    ├── whisper/                 # Whisper 模型
    ├── vosk/                    # Vosk 模型
    └── wakeword/                # 喚醒詞模型
```

### Key Components

#### 1. 核心系統 (Core System)
- **ASRHub** (`main.py`): 系統入口點，協調所有模組
- **FSM 狀態機**: 狀態轉換驗證（IDLE → PROCESSING → BUSY）
- **時間戳協調機制**: 支援非破壞性多讀取器、獨立讀取位置與時間戳索引

#### 2. 狀態管理 (State Management)
- **PyStoreX Store** (`src/store/`): 事件驅動狀態管理，Redux-like 模式
- **職責分離**: FSM 定義規則、Effects 處理副作用、Reducer 以純函數更新狀態
- **Session 管理**: 支援 Session 重用機制，降低連線/載入開銷

#### 3. 音訊處理管道 (Audio Pipeline)
- **AudioConverter**: FFmpeg/SciPy 雙引擎，支援 GPU 加速，轉換至 16kHz
- **AudioQueueManager**: 儲存轉換後的 16kHz 音訊，時間戳索引
- **BufferManager**: 智能切窗（fixed/sliding/dynamic 三種模式）
- **AudioEnhancer**: 自動調整音量、動態壓縮、軟限幅
- **DeepFilterNet**: 深度學習降噪，消除白噪音、增強人聲
- **Silero VAD**: 語音活動偵測
- **OpenWakeWord**: 喚醒詞檢測

#### 4. Provider 池化管理
- **Provider Pool Manager** (`src/provider/provider_manager.py`)
  - 租借機制（lease mechanism）進行 provider 分配
  - 老化防止（aging prevention）避免饑餓問題
  - 配額管理（quota management）防止獨占
  - 健康檢查與自動恢復
  - 並行處理多個 Session

#### 5. API 協議層
- **HTTP SSE**: Server-Sent Events，支援 Session 重用
- **WebRTC (LiveKit)**: 低延遲實時音訊串流
- **Redis Pub/Sub**: 分散式訊息傳遞

## Current Implementation Status

### ✅ 已完成功能
- 事件驅動架構與 PyStoreX 狀態管理
- FSM 狀態機整合與狀態轉換驗證
- 完整的音訊處理管道（轉換、佇列、緩衝、增強、降噪）
- Provider Pool Manager 並行處理機制
- HTTP SSE 協議支援與 Session 重用
- WebRTC/LiveKit 整合
- Redis Pub/Sub 實現
- Whisper 本地模型支援（原始版與 Faster Whisper）
- 時間戳協調機制與非破壞性多讀取器

### 🚧 開發中功能
- FunASR、Vosk 等其他 ASR Provider
- WebSocket 與 Socket.IO 協議
- gRPC 協議支援
- Google STT、OpenAI API 整合
- 性能優化與基準測試

## Configuration Management

The project uses yaml2py for configuration:
1. Edit `config/config.yaml` (contains actual settings, not in version control)
2. Run `yaml2py --config config/config.yaml --output ./src/config` to regenerate classes
3. Access configuration through `ConfigManager` singleton

Example:
```python
from src.config.manager import ConfigManager
config = ConfigManager()
port = config.api.http_sse.port
```

## Important Notes

### 配置管理
- **永不提交** `config/config.yaml` 或生成的 `src/config/` 檔案（可能包含 API 金鑰）
- **務必執行** `yaml2py` 在修改配置後重新生成類別
- **配置存取**: 透過 `ConfigManager` 單例存取配置

### 開發準則
- **Use pretty-loguru** 所有日誌使用 pretty-loguru，包含視覺化區塊和 ASCII 標題
- **保持簡單 (KISS)** - 避免過度工程和不必要的抽象
- **無狀態服務** - 服務應該是無狀態的，專注於單一職責
- **直接導入** - 在 Effects 中直接 import 並調用服務
- **模組級單例** - 使用 `service_name = ServiceClass()` 模式
- **錯誤處理** - 使用 `src/core/exceptions.py` 中的自定義例外
- **狀態管理** - 使用 PyStoreX，最小化新 Action 創建，優先直接服務調用

### 技術細節
- **ID 生成**: 使用 UUID v7 (`uuid6.uuid7()`) 進行所有新 ID 生成，提供更好的可追蹤性和調試能力
- **音訊流程**: Raw → Convert (16kHz) → Queue → Buffer → Enhance → Denoise → VAD → Provider
- **Provider Pool**: 總是使用 `provider_manager.lease()` 進行 ASR provider 分配
- **目錄命名**: 注意是 `provider/` 而不是 `providers/`（單數形式）
- **時間戳協調**: 使用時間戳索引實現非破壞性多讀取器


## Development Workflow

1. 修改配置於 `config/config.yaml`
2. 重新生成配置類別: `make yaml2py` 或 `yaml2py --config config/config.yaml --output ./src/config`
3. 實作簡單、無狀態的服務
4. 在 SessionEffects 中使用直接服務導入
5. 使用提供的測試腳本進行測試
6. 避免過度設計 - 保持服務簡單且專注

## Service Implementation Guidelines

### Creating a New Service
```python
# src/service/my_service.py
from utils.singleton import SingletonMixin
class MyService(SingletonMixin):
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            # Initialize once
    
    def process(self, data):
        # Simple, focused processing
        return processed_data

# Module-level singleton
my_service = MyService()
```

### Using Services in Effects
```python
# src/store/sessions/sessions_effects.py
from src.core.audio_queue_manager import audio_queue
from src.core.buffer_manager import BufferManager
from src.interface.buffer import BufferConfig
from src.service.audio_converter.scipy_converter import scipy_converter
from src.service.wakeword.openwakeword import open_wake_word
from src.service.vad.silero_vad import silero_vad
from src.service.recording.recording import recorder
from src.service.timer.timer_service import timer_service
from src.service.audio_enhancer import audio_enhancer
from src.service.denoise.deepfilternet_denoiser import denoiser
from src.provider.provider_manager import provider_pool

class SessionEffects:
    def on_audio_received(self, action):
        session_id = action['payload']['session_id']
        raw_audio = action['payload']['audio']
        
        # 1. Convert to 16kHz and store in queue
        converted = scipy_converter.convert_to_16khz(raw_audio)
        audio_queue.push(session_id, converted)
        
        # 2. Buffer management for stable windowing
        buffer = BufferManager(BufferConfig.for_whisper())
        audio = audio_queue.pop(session_id)
        buffer.push(audio)

        # 3. Wake word detection
        if open_wake_word.detect_wake_word(audio):
            recorder.start(session_id)
        
        # 4. Speech activity detection
        if silero_vad.detect_silence(audio):
            if timer_service.has_elapsed(session_id):
                recording = recorder.stop(session_id)
                
                # 5. Post-processing for recording
                enhanced, _ = audio_enhancer.auto_enhance(recording, "asr")
                denoised = denoiser.auto_denoise(enhanced)
                
                # 6. Get ASR provider from pool and transcribe
                with provider_pool.lease(session_id) as provider:
                    result = provider.transcribe(denoised)
        else:
            timer_service.reset_and_pause(session_id)


## FAQ

### Q: 如何選擇合適的 ASR 提供者？
**A:** 
- **Whisper**: 最佳的中文識別效果，支援多語言
- **FunASR**: 中文優化，速度快，適合即時應用
- **Vosk**: 離線識別，隱私保護，資源消耗低
- **Google STT**: 雲端服務，高準確率，需要網路
- **OpenAI API**: 最新模型，最高準確率，需要付費

### Q: Session 重用機制如何運作？
**A:** HTTP SSE 的 Session 重用機制：
1. 首次連線時建立 Session
2. Session ID 儲存在記憶體中
3. 後續請求使用相同 Session ID
4. 自動清理過期 Session（預設 30 分鐘）

### Q: 如何提升識別準確率？
**A:** 提升準確率的方法：
1. 啟用 VAD 過濾靜音片段
2. 使用降噪處理環境音
3. 調整取樣率至 16kHz
4. 選擇適合的 ASR 模型
5. 提供語言提示（initial_prompt）