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
│   │   ├── audio_converter/     # Audio format conversion
│   │   │   ├── scipy_converter.py   # SciPy converter (GPU support)
│   │   │   └── ffmpeg_converter.py  # FFmpeg converter
│   │   ├── audio_enhancer.py    # Audio enhancement (auto volume, dynamic compression)
│   │   ├── denoise/              # Noise reduction services
│   │   │   └── deepfilternet_denoiser.py # DeepFilterNet deep denoising
│   │   ├── vad/                  # Voice Activity Detection
│   │   │   └── silero_vad.py    # Silero VAD implementation
│   │   ├── wakeword/             # Wake word detection
│   │   │   └── openwakeword.py  # OpenWakeWord implementation
│   │   ├── recording/            # Recording service
│   │   ├── microphone_capture/   # Microphone capture
│   │   └── timer/                # Timer service
│   ├── provider/                 # 🎙️ ASR providers (note: singular form 'provider')
│   │   ├── provider_manager.py  # Provider Pool Manager (parallel processing)
│   │   ├── whisper/             # Whisper local model
│   │   ├── funasr/              # FunASR implementation
│   │   ├── vosk/                # Vosk implementation
│   │   ├── google_stt/          # Google STT API
│   │   └── openai/              # OpenAI Whisper API
│   ├── store/                    # 🗄️ PyStoreX state management
│   │   ├── main_store.py        # Global Store instance
│   │   └── sessions/            # Session management
│   │       ├── sessions_state.py    # State definition
│   │       ├── sessions_action.py   # Action types
│   │       ├── sessions_reducer.py  # Reducer pure functions
│   │       └── sessions_effect.py   # Effects side-effect handling
│   ├── interface/                # 📐 Service interface definitions
│   └── utils/                    # 🛠️ Utility modules
│       ├── logger.py            # pretty-loguru logging system
│       ├── id_provider.py       # UUID v7 ID generator
│       └── visualization/       # Visualization tools
├── config/                       # ⚙️ Configuration files
│   ├── config.yaml              # Main configuration (not in version control)
│   └── config.sample.yaml       # Configuration example
└── models/                       # 🧠 AI model files
    ├── whisper/                 # Whisper models
    ├── vosk/                    # Vosk models
    └── wakeword/                # Wake word models
```

### Key Components

#### 1. Core System
- **ASRHub** (`main.py`): System entry point coordinating all modules
- **FSM State Machine**: State transition validation (IDLE → PROCESSING → BUSY)
- **Timestamp Coordination**: Non-destructive multi-reader support, independent read positions and timestamp indexing

#### 2. State Management
- **PyStoreX Store** (`src/store/`): Event-driven state management with Redux-like pattern
- **Separation of Concerns**: FSM defines rules, Effects handle side effects, Reducer updates state with pure functions
- **Session Management**: Session reuse mechanism to reduce connection/loading overhead

#### 3. Audio Processing Pipeline
- **AudioConverter**: FFmpeg/SciPy dual engine with GPU acceleration, converts to 16kHz
- **AudioQueueManager**: Stores converted 16kHz audio with timestamp indexing
- **BufferManager**: Intelligent windowing (fixed/sliding/dynamic modes)
- **AudioEnhancer**: Auto volume adjustment, dynamic compression, soft limiting
- **DeepFilterNet**: Deep learning noise reduction, eliminates white noise and enhances human voice
- **Silero VAD**: Voice Activity Detection
- **OpenWakeWord**: Wake word detection

#### 4. Provider Pool Management
- **Provider Pool Manager** (`src/provider/provider_manager.py`)
  - Lease mechanism for provider allocation
  - Aging prevention to avoid starvation
  - Quota management to prevent monopolization
  - Health checks and auto-recovery
  - Parallel processing for multiple sessions

#### 5. API Protocol Layer
- **HTTP SSE**: Server-Sent Events with Session reuse support
- **WebRTC (LiveKit)**: Low-latency real-time audio streaming
- **Redis Pub/Sub**: Distributed messaging

## Current Implementation Status

### ✅ Completed Features
- Event-driven architecture with PyStoreX state management
- FSM state machine integration and state transition validation
- Complete audio processing pipeline (conversion, queue, buffer, enhancement, denoising)
- Provider Pool Manager parallel processing mechanism
- HTTP SSE protocol support with Session reuse
- WebRTC/LiveKit integration
- Redis Pub/Sub implementation
- Whisper local model support (original and Faster Whisper)
- Timestamp coordination mechanism with non-destructive multi-readers

### 🚧 In Development
- FunASR, Vosk and other ASR Providers
- WebSocket and Socket.IO protocols
- gRPC protocol support
- Google STT, OpenAI API integration
- Performance optimization and benchmarking

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

### Configuration Management
- **Never commit** `config/config.yaml` or generated `src/config/` files (may contain API keys)
- **Always run** `yaml2py` after modifying configuration to regenerate classes
- **Configuration access**: Access configuration through `ConfigManager` singleton

### Development Guidelines
- **Use pretty-loguru** for all logging with visual blocks and ASCII headers
- **Keep it simple (KISS)** - Avoid over-engineering and unnecessary abstractions
- **Stateless services** - Services should be stateless and focused on single responsibility
- **Direct imports** - Import and call services directly in Effects
- **Module-level singletons** - Use `service_name = ServiceClass()` pattern
- **Error handling** - Use custom exceptions from `src/core/exceptions.py`
- **State management** - Use PyStoreX with minimal new Actions, prefer direct service calls

### Technical Details
- **ID Generation**: Use UUID v7 (`uuid6.uuid7()`) for all new ID generation for better traceability and debugging
- **Audio Flow**: Raw → Convert (16kHz) → Queue → Buffer → Enhance → Denoise → VAD → Provider
- **Provider Pool**: Always use `provider_manager.lease()` for ASR provider allocation
- **Directory Naming**: Note that it's `provider/` not `providers/` (singular form)
- **Timestamp Coordination**: Use timestamp indexing for non-destructive multi-readers


## Development Workflow

1. Make configuration changes in `config/config.yaml`
2. Regenerate config classes: `make yaml2py` or `yaml2py --config config/config.yaml --output ./src/config`
3. Implement simple, stateless services
4. Use direct service imports in SessionEffects
5. Test using provided test scripts
6. Avoid over-engineering - keep services simple and focused

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


### Audio Processing Pipeline Example
```python
# Complete audio processing pipeline example
def process_audio_chunk(session_id: str, raw_audio: bytes):
    """Process raw audio through the complete pipeline"""
    
    # Step 1: Convert to 16kHz (required by most ASR)
    from src.service.audio_converter import audio_converter
    converted = audio_converter.convert(
        raw_audio,
        target_sample_rate=16000,
        target_channels=1
    )
    
    # Step 2: Store in queue (already converted)
    from src.core.audio_queue_manager import audio_queue
    audio_queue.push(session_id, converted)
    
    # Step 3: Buffer management
    from src.core.buffer_manager import BufferManager
    from src.interface.buffer import BufferConfig
    
    buffer_config = BufferConfig.for_whisper()  # or for_silero_vad()
    buffer = BufferManager(buffer_config)
    
    while audio_queue.size(session_id) > 0:
        chunk = audio_queue.pop(session_id)
        buffer.push(chunk)
        
        if buffer.ready():
            frame = buffer.pop()
            
            # Step 4: Audio enhancement (automatic analysis)
            from src.service.audio_enhancer import audio_enhancer
            enhanced, report = audio_enhancer.auto_enhance(frame, "asr")
            
            # Step 5: Denoising
            from src.service.denoise.deepfilternet_denoiser import denoiser
            denoised = denoiser.auto_denoise(enhanced)
            
            # Step 6: Voice Activity Detection
            from src.service.vad.silero_vad import vad
            if vad.detect_speech(denoised):
                
                # Step 7: ASR with provider pool
                from src.provider.provider_manager import provider_pool
                with provider_pool.lease(session_id, timeout=10.0) as provider:
                    transcript = provider.transcribe(denoised)
                    return transcript
    
    return None
```

## FAQ

### Q: How to choose the right ASR provider?
**A:** 
- **Whisper**: Best Chinese recognition, multilingual support
- **FunASR**: Chinese optimized, fast speed, suitable for real-time applications
- **Vosk**: Offline recognition, privacy protection, low resource consumption
- **Google STT**: Cloud service, high accuracy, requires network
- **OpenAI API**: Latest models, highest accuracy, requires payment

### Q: How does the Session reuse mechanism work?
**A:** HTTP SSE Session reuse mechanism:
1. Establish Session on first connection
2. Session ID stored in memory
3. Subsequent requests use the same Session ID
4. Auto-cleanup of expired Sessions (default 30 minutes)

### Q: How to improve recognition accuracy?
**A:** Methods to improve accuracy:
1. Enable VAD to filter silence segments
2. Use denoising to process environmental noise
3. Adjust sample rate to 16kHz
4. Choose appropriate ASR model
5. Provide language hints (initial_prompt)