# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASR Hub is a unified speech recognition middleware system that integrates multiple ASR (Automatic Speech Recognition) service providers through a single API interface. The system follows a modular pipeline architecture with support for multiple communication protocols.

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
- **Event-Driven Architecture**: PyStoreX-based state management with effects pattern
- **Provider Abstraction**: Unified interface for multiple ASR providers (Whisper, FunASR, Vosk, etc.)
- **Multi-Protocol Support**: HTTP SSE, WebSocket, Socket.io, gRPC, Redis
- **FSM State Management**: Finite State Machine for session state (IDLE, LISTENING, BUSY)
- **YAML Configuration**: All settings managed through yaml2py-generated type-safe classes

### Project Structure
```
src/
├── config/         # yaml2py generated configuration (DO NOT EDIT - auto-generated)
├── core/           # Core system: ASRHub, FSM state management
├── api/            # API implementations for each protocol
├── operators/      # Stream processing operators (VAD, wakeword, recording, etc.)
├── providers/      # ASR provider implementations
├── store/          # PyStoreX state management and effects
├── stream/         # Audio stream handling
├── utils/          # Utilities: logger, validators, audio tools
└── models/         # Data models: Audio, Transcript, Session
```

### Key Components

1. **ASRHub** (`src/core/asr_hub.py`): Main entry point coordinating all modules
2. **PyStoreX Store** (`src/store/`): Event-driven state management with effects pattern
3. **Operators** (`src/operators/`): Audio processing operators managed by SessionEffects:
   - VAD (Voice Activity Detection)
   - Denoising
   - Sample rate adjustment
   - Format conversion
   - Wake word detection
4. **Provider System**: Abstraction layer for different ASR engines
5. **Stream Controller**: Manages timeout and manual termination for streaming

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

### Phase 3 (In Progress)
- Need to implement WebSocket and Socket.io protocols
- Additional pipeline operators (VAD, denoising)
- More ASR providers integration

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
- **Follow SOLID principles** - all components use base classes and interfaces
- **Operators** should extend `OperatorBase` and are managed by SessionEffects
- **Error handling** uses custom exceptions in `src/core/exceptions.py`
- **State management** uses PyStoreX with actions, reducers, and effects patterns

## Testing Guidelines

When testing ASR functionality:
1. Check available test scripts: `test_whisper_sse.py` for Whisper SSE testing
2. Use the setup scripts: `setup_test.sh` for test environment setup
3. Refer to guides: `WHISPER_TEST_GUIDE.md` for Whisper-specific testing

## Development Workflow

1. Make configuration changes in `config/config.yaml`
2. Regenerate config classes: `make yaml2py`
3. Implement features following the base class patterns
4. Use the logger for debugging with visual formatting
5. Test using the provided test scripts
6. Follow the TODO phase documents for feature planning