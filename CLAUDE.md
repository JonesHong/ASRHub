# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASR Hub is a unified speech recognition middleware system that integrates multiple ASR (Automatic Speech Recognition) service providers through a single API interface. The system follows a simple, stateless service architecture with support for multiple communication protocols and advanced audio processing capabilities.

### Latest Architecture (v0.3.0)
- **Provider Pool Management**: Parallel processing for multiple sessions
- **Audio Processing Pipeline**: Queue → Convert → Buffer → Enhance → Denoise → Detect → ASR
- **Intelligent Audio Enhancement**: Auto-adjusts volume and applies dynamic compression
- **Deep Learning Denoising**: DeepFilterNet for superior noise reduction

## Development Commands

### Setup and Configuration
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Setup configuration (IMPORTANT!)
cp config/config.sample.yaml config/config.yaml
# Edit config/config.yaml with your settings

# Generate configuration classes from YAML
yaml2py --config config/config.yaml --output ./src/config

# Alternative using Makefile
make install
make yaml2py
```

### Running the Application
```bash
# Run the main application
python -m src.core.asr_hub

# Or using Makefile
make run

# Run HTTP SSE test server
python main.py

# Test Whisper SSE implementation
python test_whisper_sse.py
```

### Development Tasks
```bash
# Run tests
make test
make test-cov  # with coverage

# Code quality
make lint       # Run linting
make format     # Format code with black
make type-check # Run mypy type checking

# Clean build artifacts
make clean
```

## Architecture Overview

### Core Design Principles
- **KISS Principle**: Keep It Simple, Stupid - avoid over-engineering and unnecessary abstractions
- **Stateless Services**: All services are stateless and can handle multiple sessions in parallel
- **Single Responsibility**: Each service does one thing well
- **Composition Over Inheritance**: Build complex features by composing simple services
- **Direct Method Calls**: Services are called directly from Effects, no unnecessary abstraction layers
- **Module-level Singletons**: Use `__new__` for singletons, expose as module-level variables
- **Pool-based Scalability**: Provider instances are pooled for maximum hardware utilization
- **Pipeline Processing**: Audio flows through a well-defined processing pipeline

### Project Structure
```
src/
├── config/         # yaml2py generated configuration (DO NOT EDIT - auto-generated)
├── core/           # Core system: ASRHub, FSM state management
│   ├── audio_queue_manager.py    # Audio queue (should move to service/)
│   ├── buffer_manager.py         # Buffer management (should move to service/)
│   └── fsm_transitions.py        # FSM state transitions
├── api/            # API implementations for each protocol
│   └── redis/      # Redis pub/sub server
├── service/        # Stateless services
│   ├── audio_converter/           # Audio format conversion
│   │   ├── scipy_converter.py    # SciPy-based converter with GPU support
│   │   └── ffmpeg_converter.py   # FFmpeg-based converter
│   ├── audio_enhancer.py         # Audio enhancement (volume, compression)
│   ├── denoise/                   # Noise reduction services
│   │   └── deepfilternet_denoiser.py # DeepFilterNet implementation
│   ├── vad/                       # Voice Activity Detection
│   │   └── silero_vad.py         # Silero VAD implementation
│   └── wakeword/                  # Wake word detection
│       └── openwakeword.py       # OpenWakeWord implementation
├── interface/      # Service interface definitions
├── provider/       # ASR provider implementations (note: provider not providers)
│   ├── provider_manager.py       # Provider Pool Manager
│   ├── whisper/                  # Whisper provider
│   ├── funasr/                   # FunASR provider
│   └── vosk/                     # Vosk provider
├── store/          # PyStoreX state management and effects
├── utils/          # Utilities: logger, validators, audio tools
└── models/         # Data models: Audio, Transcript, Session
```

### Key Components

1. **ASRHub** (`src/core/asr_hub.py`): Main entry point coordinating all modules
2. **PyStoreX Store** (`src/store/`): Event-driven state management with effects pattern
3. **Audio Processing Pipeline**:
   - **AudioQueueManager**: Stores converted 16kHz audio (not raw audio)
   - **BufferManager**: Intelligent windowing (fixed/sliding/dynamic modes)
   - **AudioEnhancer**: Auto volume adjustment, dynamic compression, soft limiting
   - **DeepFilterNet**: Deep learning noise reduction, human voice enhancement
   - **Silero VAD**: Voice Activity Detection
   - **OpenWakeWord**: Wake word detection
4. **Provider Pool Manager** (`src/provider/provider_manager.py`):
   - Lease mechanism for provider allocation
   - Aging prevention to avoid starvation
   - Quota management to prevent monopolization
   - Health checks and auto-recovery
5. **Session Effects**: Orchestrates services based on session events

## Current Implementation Status

### Phase 1 (Completed)
- Basic project structure and configuration system
- yaml2py integration for type-safe configuration
- pretty-loguru logging system
- Base classes for all major components

### Phase 2 (Completed)
- All base classes implemented (API, Pipeline, Operator, Provider)
- HTTP SSE server with control endpoints
- Sample rate adjustment operator
- Local Whisper provider with streaming support
- Core integration and session management
- Stream processing and buffer management

### Phase 3 (Completed)
- Refactoring from Operators to Stateless Services architecture
- AudioQueueManager service (stores 16kHz converted audio)
- BufferManager with intelligent windowing strategies
- AudioConverter service with FFmpeg and SciPy (GPU support)
- AudioEnhancer with auto_enhance() intelligent processing
- DeepFilterNet denoising service
- Silero VAD implementation
- OpenWakeWord implementation
- Provider Pool Manager with parallel processing

### Phase 4 (In Progress)
- WebSocket and Socket.io protocol implementations
- Redis pub/sub integration
- Additional ASR providers (Google STT, OpenAI API)
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

- **Never commit** `config/config.yaml` or generated `src/config/` files (they may contain API keys)
- **Always run** `yaml2py` after modifying configuration
- **Use pretty-loguru** for all logging with visual blocks and ASCII headers
- **Keep it simple** - avoid over-engineering and unnecessary abstractions
- **Services** should be stateless and focused on a single responsibility
- **Direct imports** - services are imported and called directly in Effects
- **Module-level singletons** - use `service_name = ServiceClass()` pattern
- **Error handling** uses custom exceptions in `src/core/exceptions.py`
- **State management** uses PyStoreX with minimal new Actions - prefer direct service calls
- **ID Generation** - Use UUID v7 (`uuid6.uuid7()`) for all new ID generation for better traceability and debugging
- **Audio Flow**: Raw → Convert (16kHz) → Queue → Buffer → Enhance → Denoise → VAD → Provider
- **Provider Pool**: Always use provider_manager.lease() for ASR provider allocation
- **Directory Naming**: Note that it's `provider/` not `providers/` (singular form)

## Testing Guidelines

When testing ASR functionality:
1. Check available test scripts: `test_whisper_sse.py` for Whisper SSE testing
2. Use the setup scripts: `setup_test.sh` for test environment setup
3. Refer to guides: `WHISPER_TEST_GUIDE.md` for Whisper-specific testing

## Development Workflow

1. Make configuration changes in `config/config.yaml`
2. Regenerate config classes: `make yaml2py`
3. Implement features as simple, stateless services
4. Use direct service imports in SessionEffects
5. Test using the provided test scripts
6. Avoid over-engineering - keep services simple and focused

## Service Implementation Guidelines

### Creating a New Service
```python
# src/service/my_service.py
class MyService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
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
from src.service.audio_enhancer import audio_enhancer
from src.service.denoise.deepfilternet_denoiser import denoiser
from src.provider.provider_manager import provider_pool

class SessionEffects:
    def on_audio_received(self, action):
        session_id = action['payload']['session_id']
        raw_audio = action['payload']['audio']
        
        # 1. Convert to 16kHz and store in queue
        converted = audio_converter.convert_to_16khz(raw_audio)
        audio_queue.push(session_id, converted)
        
        # 2. Buffer management for stable windowing
        buffer = BufferManager(BufferConfig.for_whisper())
        audio = audio_queue.pop(session_id)
        buffer.push(audio)
        
        # 3. Audio enhancement (if needed)
        if needs_enhancement:
            enhanced, report = audio_enhancer.auto_enhance(audio, "asr")
            
        # 4. Denoising (if needed)
        if needs_denoising:
            denoised = denoiser.auto_denoise(enhanced)
            
        # 5. Get ASR provider from pool
        with provider_pool.lease(session_id) as provider:
            result = provider.transcribe(denoised)
```

### Audio Processing Pipeline Example
```python
# Complete audio processing pipeline
def process_audio_chunk(session_id: str, raw_audio: bytes):
    \"\"\"Process raw audio through the complete pipeline\"\"\"
    
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
            
            # Step 4: Enhancement (automatic analysis)
            from src.service.audio_enhancer import audio_enhancer
            enhanced, report = audio_enhancer.auto_enhance(frame, "asr")
            
            # Step 5: Denoising
            from src.service.denoise.deepfilternet_denoiser import denoiser
            denoised = denoiser.auto_denoise(enhanced)
            
            # Step 6: VAD
            from src.service.vad.silero_vad import vad
            if vad.detect_speech(denoised):
                
                # Step 7: ASR with provider pool
                from src.provider.provider_manager import provider_pool
                with provider_pool.lease(session_id, timeout=10.0) as provider:
                    transcript = provider.transcribe(denoised)
                    return transcript
    
    return None
```