# WebASRCore - 前端語音識別核心庫設計規劃書

## 執行摘要

WebASRCore 是一個基於 ASRHub 架構理念設計的純前端語音識別庫。它承襲了 ASRHub 的核心設計原則：KISS（Keep It Simple, Stupid）、無狀態服務架構、和音訊處理管線模式，同時針對瀏覽器環境進行了優化。

### 從 POC 學到的關鍵經驗

通過分析 wake-word-transcriber POC 實現，我們獲得以下重要洞察：

1. **執行模式固定**：初始化時檢測能力並選擇最適合的模式，之後不再改變
2. **Worker 密集使用**：將 CPU 密集任務卸載到 Worker 提升主線程響應  
3. **模型預載入**：使用 link prefetch 和快取策略加速模型載入
4. **音訊管線整合**：提供統一的介面層協調各個服務
5. **瀏覽器相容性**：初始化時的全面能力檢測和診斷
6. **配置優先**：提供預設配置但允許用戶覆寫，不做過度智能決策

### 核心特性
- 🎯 **零伺服器依賴**：完全在瀏覽器端運行
- 🔐 **隱私優先**：音訊數據不離開用戶設備
- 📦 **輕量級**：支援按需載入和 Tree Shaking
- 🌐 **CDN 友善**：可直接透過 script 標籤引入
- 🔧 **高度可配置**：靈活的服務啟用/停用機制
- 🚀 **即時處理**：低延遲的本地音訊處理

## 1. 架構總覽

### 1.1 設計理念承襲

從 ASRHub 繼承的核心理念：

1. **KISS 原則**
   - 簡單直接的 API 設計
   - 避免過度工程化
   - 清晰的責任劃分

2. **無狀態服務**
   - 每個服務獨立運作
   - 服務間無相互依賴
   - 易於測試和維護

3. **直接調用模式**
   - 避免不必要的抽象層
   - 服務直接暴露為模組級別的單例
   - 效果（Effects）直接調用服務

4. **音訊處理管線**
   ```
   Microphone/File → AudioQueue → Buffer → Enhance → Denoise → VAD → ASR Provider
   ```

### 1.2 前端環境適配

針對瀏覽器環境的特殊設計：

- **單一用戶場景**：移除多 session 管理
- **瀏覽器 API 優先**：充分利用原生 Web API
- **Web Worker 隔離**：CPU 密集型任務在 Worker 中執行
- **漸進式載入**：ML 模型按需載入，減少初始載入時間
- **固定模式**：初始化時檢測能力並選擇最適合模式，之後不再改變

## 2. 技術架構

### 2.1 技術棧選型

| 類別 | 技術選擇 | 理由 |
|------|----------|------|
| 狀態管理 | XState | 強大的 FSM 實現，TypeScript 支援完善 |
| 反應式系統 | SolidJS | 輕量級（~5KB），細粒度反應性，自動依賴追蹤 |
| 音訊處理 | Web Audio API + AudioWorklet | 低延遲、高性能音訊處理 |
| ML Runtime | ONNX Runtime Web | 跨平台 ML 模型執行 |
| 語音模型 | Transformers.js | Whisper 模型的 Web 版本 |
| 打包工具 | Vite/Rollup | ESM 優先，優秀的 Tree Shaking |
| 類型系統 | TypeScript | 完整的類型安全 |

### 2.2 模組架構

```
WebASRCore/
├── src/
│   ├── core/                 # 核心引擎
│   │   ├── fsm/              # 狀態機實現
│   │   │   ├── states.ts     # 狀態定義
│   │   │   ├── transitions.ts # 轉換規則
│   │   │   └── machine.ts    # XState 機器配置
│   │   ├── store/            # 狀態管理
│   │   │   ├── store.ts      # RxJS Subject
│   │   │   ├── actions.ts    # Action 定義
│   │   │   └── effects.ts    # Side Effects
│   │   ├── audio-queue/      # 音訊佇列
│   │   │   ├── queue.ts      # 佇列實現
│   │   │   └── types.ts      # 音訊數據類型
│   │   └── buffer/           # 緩衝管理
│   │       ├── manager.ts    # BufferManager
│   │       └── strategies.ts # Fixed/Sliding/Dynamic
│   │
│   ├── services/             # 無狀態服務
│   │   ├── microphone/       # 麥克風擷取
│   │   │   ├── capture.ts    # getUserMedia 封裝
│   │   │   └── processor.ts  # AudioWorklet 處理器
│   │   ├── vad/              # 語音活動檢測
│   │   │   ├── silero-vad.ts # Silero VAD ONNX
│   │   │   └── worker.ts     # VAD Web Worker
│   │   ├── wake-word/        # 喚醒詞檢測
│   │   │   ├── openwakeword.ts # OpenWakeWord ONNX
│   │   │   └── worker.ts     # Wake Word Worker
│   │   ├── denoise/          # 降噪處理
│   │   │   ├── rnnoise.ts    # RNNoise WASM
│   │   │   └── worker.ts     # Denoise Worker
│   │   └── timer/            # 計時器服務
│   │       └── timer.ts      # 倒數計時器
│   │
│   ├── providers/            # ASR 提供者
│   │   ├── base.ts           # Provider 介面
│   │   ├── webspeech/        # Web Speech API
│   │   │   └── provider.ts   # 原生 API 封裝
│   │   └── whisper/          # Whisper 模型
│   │       ├── provider.ts   # Transformers.js
│   │       └── worker.ts     # Whisper Worker
│   │
│   ├── config/               # 配置管理
│   │   ├── config.ts         # ConfigManager
│   │   ├── defaults.ts       # 預設配置
│   │   └── types.ts          # 配置介面
│   │
│   ├── utils/                # 工具函數
│   │   ├── logger.ts         # 日誌系統
│   │   ├── audio-tools.ts    # 音訊工具
│   │   └── singleton.ts      # 單例輔助
│   │
│   └── index.ts              # 主入口
│
├── dist/                     # 構建輸出
│   ├── webasr-core.esm.js   # ESM 版本
│   ├── webasr-core.umd.js   # UMD 版本
│   └── types/                # TypeScript 聲明
│
├── examples/                 # 使用範例
│   ├── basic/                # 基礎用法
│   ├── react/                # React 整合
│   ├── vue/                  # Vue 整合
│   └── cdn/                  # CDN 引入
│
├── models/                   # ML 模型文件（可選，打包時包含）
│   ├── silero-vad/           # VAD 模型
│   │   ├── silero_vad.onnx      # 完整版 (~1.5MB)
│   │   └── silero_vad_q8.onnx   # 量化版 (~400KB)
│   ├── openwakeword/         # 喚醒詞模型
│   │   ├── hey_assistant.onnx      # 完整版 (~2MB)
│   │   └── hey_assistant_q8.onnx   # 量化版 (~500KB)
│   └── whisper/              # Whisper 模型
│       ├── whisper-tiny.onnx       # 完整版 (~39MB)
│       └── whisper-tiny-q8.onnx    # 量化版 (~10MB)
│
└── package.json              # NPM 配置
```

## 3. 核心組件設計

### 3.1 FSM 狀態機

使用 XState 實現狀態管理，反映完整的音訊處理流程：

```typescript
// states.ts
export enum State {
  IDLE = 'idle',
  WAKE_WORD_LISTENING = 'wake_word_listening',  // 持續監聽喚醒詞
  RECORDING = 'recording',                       // 喚醒後開始錄音
  SILENCE_DETECTED = 'silence_detected',         // VAD 檢測到靜音
  COUNTDOWN = 'countdown',                        // 倒數計時中
  TRANSCRIBING = 'transcribing',                 // 轉譯中
  ERROR = 'error'
}

// machine.ts
export const createASRMachine = (config: ASRConfig) => {
  return createMachine({
    id: 'webASR',
    initial: State.IDLE,
    context: {
      mode: config.mode, // 'streaming' | 'non-streaming'
      wakeWordEnabled: config.wakeWord?.enabled,
      vadEnabled: config.vad?.enabled,
      countdownSeconds: config.silenceTimeout || 2,
      audioQueue: [],
      recordingBuffer: []
    },
    states: {
      [State.IDLE]: {
        on: {
          START: State.WAKE_WORD_LISTENING,
          UPLOAD: State.TRANSCRIBING  // 直接上傳檔案
        }
      },
      [State.WAKE_WORD_LISTENING]: {
        // 持續將音訊送給 OpenWakeWord
        on: {
          WAKE_WORD_DETECTED: {
            target: State.RECORDING,
            actions: 'clearAudioQueue'  // 清空佇列，開始新錄音
          },
          STOP: State.IDLE
        }
      },
      [State.RECORDING]: {
        // 同時啟動 VAD，記錄音訊
        on: {
          SILENCE_DETECTED: State.SILENCE_DETECTED,
          STOP: State.IDLE
        },
        invoke: {
          src: 'vadService',  // 啟動 VAD 服務
        }
      },
      [State.SILENCE_DETECTED]: {
        entry: 'startCountdown',
        on: {
          COUNTDOWN_COMPLETE: State.TRANSCRIBING,
          SPEECH_DETECTED: State.RECORDING,  // 重新檢測到語音，返回錄音
          STOP: State.IDLE
        }
      },
      [State.COUNTDOWN]: {
        // 倒數計時狀態（可選，如果需要更精細的控制）
        after: {
          COUNTDOWN_DELAY: State.TRANSCRIBING
        },
        on: {
          SPEECH_DETECTED: State.RECORDING,
          STOP: State.IDLE
        }
      },
      [State.TRANSCRIBING]: {
        entry: 'sendToProvider',  // 發送整個佇列給 ASR Provider
        on: {
          TRANSCRIPTION_COMPLETE: State.WAKE_WORD_LISTENING,  // 完成後返回監聽
          TRANSCRIPTION_PARTIAL: State.TRANSCRIBING,
          ERROR: State.ERROR
        }
      },
      [State.ERROR]: {
        on: {
          RETRY: State.IDLE,
          RESET: State.IDLE
        }
      }
    }
  });
};
```

### 3.2 音訊佇列管理

簡化版的 AudioQueue，適合單用戶場景，並整合 SolidJS 響應式：

```typescript
// audio-queue/queue.ts
import { createSignal, createEffect } from 'solid-js';

export class AudioQueue {
  private queue: AudioChunk[] = [];
  private maxSize: number;
  private [getSize, setSize] = createSignal(0);
  private [isRecording, setIsRecording] = createSignal(false);
  private recordingBuffer: AudioChunk[] = [];

  constructor(config: QueueConfig) {
    this.maxSize = config.maxQueueSize || 100;
  }

  push(chunk: AudioChunk): void {
    const timestampedChunk = {
      data: chunk.data,
      timestamp: Date.now(),
      sampleRate: chunk.sampleRate,
      channels: chunk.channels
    };

    // 如果正在錄音，同時加入錄音緩衝區
    if (this.isRecording()) {
      this.recordingBuffer.push(timestampedChunk);
    }

    this.queue.push(timestampedChunk);

    // 限制佇列大小
    if (this.queue.length > this.maxSize) {
      this.queue.shift();
    }
    
    this.setSize(this.queue.length);
  }

  pop(): AudioChunk | null {
    const chunk = this.queue.shift() || null;
    this.setSize(this.queue.length);
    return chunk;
  }

  // 開始錄音：清空佇列並開始記錄
  startRecording(): void {
    this.clear();
    this.recordingBuffer = [];
    this.setIsRecording(true);
  }

  // 停止錄音：返回錄音緩衝區
  stopRecording(): AudioChunk[] {
    this.setIsRecording(false);
    const recording = [...this.recordingBuffer];
    this.recordingBuffer = [];
    return recording;
  }

  // 獲取整個錄音緩衝區（不清空）
  getRecordingBuffer(): AudioChunk[] {
    return [...this.recordingBuffer];
  }

  getRange(startTime: number, endTime: number): AudioChunk[] {
    return this.queue.filter(
      chunk => chunk.timestamp >= startTime && chunk.timestamp <= endTime
    );
  }

  clear(): void {
    this.queue = [];
    this.setSize(0);
  }

  // SolidJS 響應式接口
  get size() {
    return this.getSize();
  }

  get recording() {
    return this.isRecording();
  }
}
```

### 3.3 無狀態服務設計

每個服務遵循單一職責原則：

```typescript
// services/microphone/capture.ts
export class MicrophoneCapture {
  private static instance: MicrophoneCapture;
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private processor: AudioWorkletNode | null = null;

  private constructor() {}

  static getInstance(): MicrophoneCapture {
    if (!MicrophoneCapture.instance) {
      MicrophoneCapture.instance = new MicrophoneCapture();
    }
    return MicrophoneCapture.instance;
  }

  async start(onData: (chunk: AudioChunk) => void): Promise<void> {
    // 請求麥克風權限
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true
      }
    });

    // 創建 AudioContext
    this.audioContext = new AudioContext({ sampleRate: 16000 });
    
    // 載入 AudioWorklet
    await this.audioContext.audioWorklet.addModule('/audio-processor.js');
    
    // 連接處理器
    const source = this.audioContext.createMediaStreamSource(this.stream);
    this.processor = new AudioWorkletNode(this.audioContext, 'audio-processor');
    
    // 監聽音訊數據
    this.processor.port.onmessage = (event) => {
      onData({
        data: event.data.buffer,
        sampleRate: 16000,
        channels: 1
      });
    };

    source.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
  }

  stop(): void {
    this.processor?.disconnect();
    this.stream?.getTracks().forEach(track => track.stop());
    this.audioContext?.close();
    
    this.processor = null;
    this.stream = null;
    this.audioContext = null;
  }
}

// 模組級別單例
export const microphoneCapture = MicrophoneCapture.getInstance();
```

### 3.4 ASR Provider 介面

統一的 Provider 介面設計：

```typescript
// providers/base.ts
export interface ASRProvider {
  name: string;
  isAvailable(): Promise<boolean>;
  initialize(config?: any): Promise<void>;
  transcribe(audio: AudioData): Promise<TranscriptionResult>;
  transcribeStream(
    audioStream: Observable<AudioData>
  ): Observable<TranscriptionResult>;
  destroy(): Promise<void>;
}

// providers/webspeech/provider.ts
import { createSignal, onCleanup } from 'solid-js';

export class WebSpeechProvider implements ASRProvider {
  name = 'webspeech';
  private recognition: SpeechRecognition | null = null;
  private [getTranscript, setTranscript] = createSignal<TranscriptionResult | null>(null);

  async isAvailable(): Promise<boolean> {
    return 'webkitSpeechRecognition' in window || 
           'SpeechRecognition' in window;
  }

  async initialize(config: WebSpeechConfig): Promise<void> {
    const SpeechRecognition = 
      window.SpeechRecognition || window.webkitSpeechRecognition;
    
    this.recognition = new SpeechRecognition();
    this.recognition.continuous = config.continuous ?? true;
    this.recognition.interimResults = config.interimResults ?? true;
    this.recognition.lang = config.language ?? 'zh-TW';
  }

  // 串流轉譯（即時）
  async transcribeStream(onResult: (result: TranscriptionResult) => void): Promise<void> {
    if (!this.recognition) {
      throw new Error('WebSpeech not initialized');
    }

    this.recognition.onresult = (event) => {
      const result = event.results[event.resultIndex];
      const transcriptionResult = {
        text: result[0].transcript,
        isFinal: result.isFinal,
        confidence: result[0].confidence,
        timestamp: Date.now()
      };
      
      this.setTranscript(transcriptionResult);
      onResult(transcriptionResult);
    };

    this.recognition.onerror = (error) => {
      console.error('WebSpeech error:', error);
    };

    this.recognition.onend = () => {
      console.log('WebSpeech recognition ended');
    };

    this.recognition.start();
    
    // 清理函數
    onCleanup(() => {
      this.recognition?.stop();
    });
  }

  stop(): void {
    this.recognition?.stop();
  }

  // SolidJS 響應式接口
  get currentTranscript() {
    return this.getTranscript();
  }

  // 非串流模式不支援
  async transcribe(audio: AudioData): Promise<TranscriptionResult> {
    throw new Error('WebSpeech API only supports streaming mode');
  }

  async destroy(): Promise<void> {
    this.stop();
    this.recognition = null;
  }
}
```

## 4. 服務層架構

### 4.1 執行模式管理器

在初始化時檢測瀏覽器能力，選擇最適合的執行模式並固定使用：

```typescript
export class ExecutionModeManager {
  private capabilities: BrowserCapabilities;
  private executionChain: ExecutionMode[];
  
  async initialize(): Promise<ExecutionConfig> {
    // 檢測瀏覽器能力（只在初始化時執行一次）
    this.capabilities = await this.detectCapabilities();
    
    // 決定固定的執行模式
    this.executionMode = this.determineExecutionMode();
    
    // 返回固定配置
    return this.getFixedConfig();
  }
  
  private async detectCapabilities(): Promise<BrowserCapabilities> {
    return {
      webWorker: typeof Worker !== 'undefined',
      sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
      webAssembly: typeof WebAssembly !== 'undefined',
      webGPU: await this.checkWebGPU(),
      webGL2: this.checkWebGL2(),
      simd: await this.checkSIMD(),
      threads: self.crossOriginIsolated || false,
      hardwareConcurrency: navigator.hardwareConcurrency || 1,
      deviceMemory: navigator.deviceMemory || 0
    };
  }
}

  private determineExecutionMode(): ExecutionMode {
    // 根據能力選擇執行模式（初始化後不再改變）
    if (this.capabilities.webWorker && this.capabilities.threads) {
      console.log('Using worker-threaded mode (best performance)');
      return 'worker-threaded';
    }
    if (this.capabilities.webWorker) {
      console.warn('SharedArrayBuffer not available, using basic worker mode');
      return 'worker';
    }
    console.warn('Web Worker not supported, falling back to main thread');
    return 'main-thread';
  }
  
  getFixedConfig(): ExecutionConfig {
    // 返回固定的配置（不會動態改變）
    return {
      mode: this.executionMode,
      onnxExecutionProviders: this.getONNXProviders(),
      workerPoolSize: Math.min(4, this.capabilities.hardwareConcurrency),
      enableWASMSIMD: this.capabilities.simd,
      enableWASMThreads: this.capabilities.threads,
      modelCaching: this.capabilities.deviceMemory > 4 ? 'memory' : 'indexeddb'
    };
  }
}

export const executionModeManager = new ExecutionModeManager();
```

### 4.2 音訊管線整合器

提供統一的音訊管線管理，使用初始化時決定的固定配置：

```typescript
export class AudioPipelineIntegration {
  private audioContext: AudioContext;
  private workletNode: AudioWorkletNode;
  private executionMode: ExecutionConfig;
  
  async initialize(config: AudioPipelineConfig): Promise<void> {
    // 1. 檢查瀏覽器相容性
    const compatibility = await this.checkBrowserCompatibility();
    
    // 2. 執行音訊診斷
    const diagnostics = await this.diagnoseAudioCapabilities();
    
    // 3. 獲取固定執行模式（初始化時已決定）
    this.executionMode = executionModeManager.getFixedConfig();
    
    // 4. 載入 AudioWorklet（如果需要）
    if (this.executionMode.mode !== 'main-thread') {
      await this.loadAudioWorklet();
    }
  }
  
  private async loadAudioWorklet(): Promise<void> {
    const basePath = window.location.pathname.substring(
      0, 
      window.location.pathname.lastIndexOf('/') + 1
    );
    const workletPath = `${basePath}worklets/audio-processor.worklet.js`;
    
    await this.audioContext.audioWorklet.addModule(workletPath);
    
    this.workletNode = new AudioWorkletNode(
      this.audioContext,
      'audio-processor',
      {
        processorOptions: {
          sampleRate: 16000,
          frameSize: 1280, // 80ms chunks for wake word detection
          executionMode: this.executionMode.mode
        }
      }
    );
  }
}

export const audioPipeline = new AudioPipelineIntegration();
```

## 5. 配置系統

### 4.1 配置結構

```typescript
// config/types.ts
export interface WebASRConfig {
  // 模式配置
  mode: 'streaming' | 'non-streaming';
  
  // 音訊配置
  audio: {
    sampleRate: number;
    channels: number;
    bufferSize: number;
    queueMaxSize: number;
  };

  // 服務配置
  services: {
    microphone: {
      enabled: boolean;
      echoCancellation?: boolean;
      noiseSuppression?: boolean;
    };
    
    vad: {
      enabled: boolean;
      model?: string;
      threshold?: number;
      minSpeechDuration?: number;
      maxSilenceDuration?: number;
    };
    
    wakeWord: {
      enabled: boolean;
      words?: string[];
      model?: string;
      threshold?: number;
    };
    
    denoise: {
      enabled: boolean;
      model?: string;
      strength?: number;
    };
    
    timer: {
      enabled: boolean;
      defaultDuration?: number;
    };
  };

  // Provider 配置
  providers: {
    primary: 'webspeech' | 'whisper';
    webspeech?: {
      language: string;
      continuous: boolean;
      interimResults: boolean;
    };
    whisper?: {
      model: string;
      language: string;
      task: 'transcribe' | 'translate';
    };
  };

  // 日誌配置
  logging: {
    level: 'debug' | 'info' | 'warn' | 'error';
    enabled: boolean;
  };
}
```

### 4.2 預設配置

```typescript
// config/defaults.ts
export const defaultConfig: WebASRConfig = {
  mode: 'streaming',
  
  audio: {
    sampleRate: 16000,
    channels: 1,
    bufferSize: 4096,
    queueMaxSize: 100
  },

  services: {
    microphone: {
      enabled: true,
      echoCancellation: true,
      noiseSuppression: true
    },
    
    vad: {
      enabled: true,
      model: 'silero-vad',
      threshold: 0.5,
      minSpeechDuration: 250,
      maxSilenceDuration: 1000
    },
    
    wakeWord: {
      enabled: false,
      words: ['hey assistant'],
      threshold: 0.5
    },
    
    denoise: {
      enabled: false,
      strength: 0.7
    },
    
    timer: {
      enabled: false,
      defaultDuration: 30000
    }
  },

  providers: {
    primary: 'webspeech',
    webspeech: {
      language: 'zh-TW',
      continuous: true,
      interimResults: true
    }
  },

  logging: {
    level: 'info',
    enabled: true
  }
};
```

## 6. 使用範例

### 5.1 基本使用

```javascript
// ESM 導入
import { WebASRCore } from 'webasr-core';

// 創建實例
const asr = new WebASRCore({
  mode: 'streaming',
  providers: {
    primary: 'webspeech',
    webspeech: {
      language: 'zh-TW'
    }
  }
});

// 監聽事件
asr.on('transcription', (result) => {
  console.log('識別結果:', result.text);
  console.log('是否最終:', result.isFinal);
});

asr.on('error', (error) => {
  console.error('錯誤:', error);
});

// 開始識別
await asr.start();

// 停止識別
asr.stop();
```

### 5.2 CDN 使用

```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/webasr-core/dist/webasr-core.umd.js"></script>
</head>
<body>
  <button id="start">開始錄音</button>
  <button id="stop">停止錄音</button>
  <div id="result"></div>

  <script>
    const asr = new WebASRCore.WebASRCore({
      mode: 'streaming',
      providers: {
        primary: 'webspeech'
      }
    });

    asr.on('transcription', (result) => {
      document.getElementById('result').textContent = result.text;
    });

    document.getElementById('start').onclick = () => asr.start();
    document.getElementById('stop').onclick = () => asr.stop();
  </script>
</body>
</html>
```

### 5.3 進階使用 - 啟用所有服務

```typescript
import { WebASRCore } from 'webasr-core';

const asr = new WebASRCore({
  mode: 'non-streaming',
  
  services: {
    // 啟用 VAD
    vad: {
      enabled: true,
      threshold: 0.5,
      minSpeechDuration: 250
    },
    
    // 啟用喚醒詞
    wakeWord: {
      enabled: true,
      words: ['小助手', '嘿 Siri'],
      threshold: 0.6
    },
    
    // 啟用降噪
    denoise: {
      enabled: true,
      strength: 0.8
    },
    
    // 啟用計時器
    timer: {
      enabled: true,
      defaultDuration: 30000
    }
  },

  // 使用 Whisper
  providers: {
    primary: 'whisper',
    whisper: {
      model: 'whisper-base',
      language: 'zh',
      task: 'transcribe'
    }
  }
});

// 喚醒詞檢測
asr.on('wake-word-detected', (word) => {
  console.log(`檢測到喚醒詞: ${word}`);
});

// VAD 事件
asr.on('speech-start', () => {
  console.log('開始說話');
});

asr.on('speech-end', () => {
  console.log('停止說話');
});

// 計時器事件
asr.on('timer-expired', () => {
  console.log('錄音超時');
  asr.stop();
});

await asr.start();
```

### 5.4 檔案上傳處理

```typescript
// 處理音訊檔案
const fileInput = document.getElementById('file-input');

fileInput.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  
  if (file) {
    // 使用檔案模式
    const result = await asr.transcribeFile(file, {
      provider: 'whisper',
      language: 'zh'
    });
    
    console.log('轉錄結果:', result.text);
  }
});
```

## 7. 模型管理系統

### 7.1 模型預載入系統

基於 POC 實踐，提供模型預載入策略：

```typescript
export class ModelPreloader {
  private preloadedUrls: Set<string> = new Set();
  private preloadPromises: Map<string, Promise<any>> = new Map();
  private loadingStatus: Map<string, LoadingStatus> = new Map();
  
  /**
   * 使用 link prefetch 預載入模型
   */
  prefetchModel(modelPath: string): void {
    const files = this.getModelFiles(modelPath);
    
    files.forEach(file => {
      const fullUrl = this.getFullUrl(file);
      if (!this.preloadedUrls.has(fullUrl)) {
        // 創建 link prefetch 標籤
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = fullUrl;
        link.as = 'fetch';
        link.crossOrigin = 'anonymous';
        document.head.appendChild(link);
        this.preloadedUrls.add(fullUrl);
      }
    });
  }
  
  /**
   * 使用 fetch 預載入並快取
   */
  async preloadModelWithCache(modelPath: string): Promise<boolean> {
    const files = this.getModelFiles(modelPath);
    const promises: Promise<Blob>[] = [];
    
    for (const file of files) {
      const fullUrl = this.getFullUrl(file);
      
      if (this.preloadPromises.has(fullUrl)) {
        promises.push(this.preloadPromises.get(fullUrl)!);
        continue;
      }
      
      const promise = this.fetchWithRetry(fullUrl, file);
      this.preloadPromises.set(fullUrl, promise);
      promises.push(promise);
    }
    
    try {
      await Promise.all(promises);
      console.log(`All files preloaded for ${modelPath}`);
      return true;
    } catch (error) {
      console.error('Failed to preload some files:', error);
      return false;
    }
  }
  
  /**
   * 帶重試機制的 fetch
   */
  private async fetchWithRetry(
    url: string, 
    fileName: string, 
    retries: number = 3
  ): Promise<Blob> {
    this.loadingStatus.set(fileName, { status: 'loading', progress: 0 });
    
    // 發送載入開始事件
    window.dispatchEvent(new CustomEvent('modelLoadStart', {
      detail: { modelName: fileName }
    }));
    
    for (let i = 0; i < retries; i++) {
      try {
        const response = await fetch(url, {
          method: 'GET',
          cache: 'force-cache', // 強制使用快取
          mode: 'cors',
          credentials: 'omit'
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        // 追蹤下載進度
        const blob = await this.trackProgress(response, fileName);
        
        this.loadingStatus.set(fileName, { status: 'completed', progress: 100 });
        return blob;
      } catch (error) {
        console.warn(`Failed to load ${fileName} (attempt ${i + 1}/${retries}):`, error);
        if (i === retries - 1) throw error;
        await this.delay(Math.pow(2, i) * 1000); // 指數退避
      }
    }
    
    throw new Error(`Failed to load ${fileName} after ${retries} attempts`);
  }
  
  /**
   * 追蹤下載進度
   */
  private async trackProgress(
    response: Response, 
    fileName: string
  ): Promise<Blob> {
    const contentLength = response.headers.get('content-length');
    const total = parseInt(contentLength || '0', 10);
    
    if (!total || !response.body) {
      return response.blob();
    }
    
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let received = 0;
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      chunks.push(value);
      received += value.length;
      
      const progress = Math.min((received / total) * 100, 100);
      this.loadingStatus.set(fileName, { status: 'loading', progress });
      
      // 發送進度事件
      window.dispatchEvent(new CustomEvent('modelLoadProgress', {
        detail: { fileName, progress: Math.round(progress), received, total }
      }));
    }
    
    return new Blob(chunks);
  }
}

export const modelPreloader = new ModelPreloader();
```

## 7. 模型管理系統（原有內容）

### 6.1 模型載入策略

WebASRCore 提供三種模型載入方式：

1. **內建模型**：打包在庫中的輕量級模型
2. **自定義路徑**：用戶指定的本地檔案路徑或遠端 URL
3. **Hugging Face**：自動從 HF 下載並快取

```typescript
// models/model-manager.ts
export interface ModelConfig {
  type: 'builtin' | 'custom' | 'huggingface';
  path?: string;  // 本地檔案路徑、URL 或 HF 模型 ID
  cache?: boolean;  // 是否快取到 IndexedDB
  quantized?: boolean;  // 是否使用量化版本
}

export class ModelManager {
  private static instance: ModelManager;
  private modelCache = new Map<string, ArrayBuffer>();
  private db: IDBDatabase | null = null;

  private constructor() {
    this.initIndexedDB();
  }

  static getInstance(): ModelManager {
    if (!ModelManager.instance) {
      ModelManager.instance = new ModelManager();
    }
    return ModelManager.instance;
  }

  private async initIndexedDB(): Promise<void> {
    const request = indexedDB.open('WebASRCore', 1);
    
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains('models')) {
        db.createObjectStore('models', { keyPath: 'name' });
      }
    };

    this.db = await new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async loadModel(name: string, config: ModelConfig): Promise<ArrayBuffer> {
    // 檢查記憶體快取
    const cacheKey = `${name}-${config.type}-${config.path}`;
    if (this.modelCache.has(cacheKey)) {
      console.log(`Model ${name} loaded from memory cache`);
      return this.modelCache.get(cacheKey)!;
    }

    // 檢查 IndexedDB 快取
    if (config.cache && this.db) {
      const cached = await this.getFromIndexedDB(cacheKey);
      if (cached) {
        console.log(`Model ${name} loaded from IndexedDB`);
        this.modelCache.set(cacheKey, cached);
        return cached;
      }
    }

    // 載入模型
    let modelData: ArrayBuffer;
    
    switch (config.type) {
      case 'builtin':
        modelData = await this.loadBuiltinModel(name, config.quantized);
        break;
      
      case 'custom':
        if (!config.path) {
          throw new Error('Custom model requires a path');
        }
        modelData = await this.loadFromPathOrFile(config.path);
        break;
      
      case 'huggingface':
        if (!config.path) {
          throw new Error('Hugging Face model requires a model ID');
        }
        modelData = await this.loadFromHuggingFace(config.path, config.quantized);
        break;
      
      default:
        throw new Error(`Unknown model type: ${config.type}`);
    }

    // 快取到記憶體
    this.modelCache.set(cacheKey, modelData);

    // 快取到 IndexedDB
    if (config.cache && this.db) {
      await this.saveToIndexedDB(cacheKey, modelData);
    }

    return modelData;
  }

  private async loadBuiltinModel(name: string, quantized = false): Promise<ArrayBuffer> {
    // 內建模型映射表
    const builtinModels = {
      'silero-vad': {
        normal: '/models/silero-vad/silero_vad.onnx',
        quantized: '/models/silero-vad/silero_vad_q8.onnx'
      },
      'openwakeword-hey': {
        normal: '/models/openwakeword/hey_assistant.onnx',
        quantized: '/models/openwakeword/hey_assistant_q8.onnx'
      },
      'whisper-tiny': {
        normal: '/models/whisper/whisper-tiny.onnx',
        quantized: '/models/whisper/whisper-tiny-q8.onnx'
      }
    };

    const modelPath = builtinModels[name];
    if (!modelPath) {
      throw new Error(`Unknown builtin model: ${name}`);
    }

    const url = quantized ? modelPath.quantized : modelPath.normal;
    return await this.loadFromPathOrFile(url);
  }

  private async loadFromPathOrFile(path: string): Promise<ArrayBuffer> {
    // 檢查是否為 File 物件或 Blob
    if (path instanceof File || path instanceof Blob) {
      return await path.arrayBuffer();
    }
    
    // 檢查是否為本地檔案路徑（File Input）
    if (path.startsWith('file://') || path.startsWith('blob:')) {
      // 處理本地檔案 URL
      const response = await fetch(path);
      return await response.arrayBuffer();
    }
    
    // 檢查是否為相對路徑（相對於當前網站）
    if (!path.startsWith('http://') && !path.startsWith('https://')) {
      // 相對路徑，構建完整 URL
      const baseUrl = window.location.origin;
      const fullPath = path.startsWith('/') ? path : `/${path}`;
      path = `${baseUrl}${fullPath}`;
    }
    
    // 從 URL 載入
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`Failed to load model from ${path}: ${response.statusText}`);
    }
    return await response.arrayBuffer();
  }
  
  // 支援從 File Input 載入模型
  async loadFromFileInput(file: File): Promise<ArrayBuffer> {
    return await file.arrayBuffer();
  }

  private async loadFromHuggingFace(modelId: string, quantized = false): Promise<ArrayBuffer> {
    // Hugging Face CDN URL 格式
    const baseUrl = 'https://huggingface.co';
    const quantizedSuffix = quantized ? '_q8' : '';
    
    // 根據模型類型構建 URL
    let url: string;
    
    if (modelId.includes('whisper')) {
      // Whisper 模型
      url = `${baseUrl}/${modelId}/resolve/main/onnx/model${quantizedSuffix}.onnx`;
    } else if (modelId.includes('silero')) {
      // Silero VAD
      url = `${baseUrl}/${modelId}/resolve/main/silero_vad${quantizedSuffix}.onnx`;
    } else if (modelId.includes('openwakeword')) {
      // OpenWakeWord
      const wordName = modelId.split('/').pop();
      url = `${baseUrl}/${modelId}/resolve/main/${wordName}${quantizedSuffix}.onnx`;
    } else {
      // 通用 ONNX 模型
      url = `${baseUrl}/${modelId}/resolve/main/model${quantizedSuffix}.onnx`;
    }

    console.log(`Loading model from Hugging Face: ${url}`);
    
    try {
      return await this.loadFromPathOrFile(url);
    } catch (error) {
      console.error(`Failed to load from HF, trying alternative URL...`);
      // 嘗試備用 URL 格式
      const altUrl = `${baseUrl}/${modelId}/resolve/main/onnx/model.onnx`;
      return await this.loadFromPathOrFile(altUrl);
    }
  }

  private async getFromIndexedDB(key: string): Promise<ArrayBuffer | null> {
    if (!this.db) return null;

    const transaction = this.db.transaction(['models'], 'readonly');
    const store = transaction.objectStore('models');
    const request = store.get(key);

    return new Promise((resolve) => {
      request.onsuccess = () => {
        resolve(request.result?.data || null);
      };
      request.onerror = () => resolve(null);
    });
  }

  private async saveToIndexedDB(key: string, data: ArrayBuffer): Promise<void> {
    if (!this.db) return;

    const transaction = this.db.transaction(['models'], 'readwrite');
    const store = transaction.objectStore('models');
    
    await store.put({
      name: key,
      data: data,
      timestamp: Date.now(),
      size: data.byteLength
    });
  }

  // 清理快取
  async clearCache(memory = true, indexed = true): Promise<void> {
    if (memory) {
      this.modelCache.clear();
    }
    
    if (indexed && this.db) {
      const transaction = this.db.transaction(['models'], 'readwrite');
      const store = transaction.objectStore('models');
      await store.clear();
    }
  }

  // 獲取快取統計
  async getCacheStats(): Promise<{
    memorySize: number;
    indexedDBSize: number;
    modelCount: number;
  }> {
    let memorySize = 0;
    for (const model of this.modelCache.values()) {
      memorySize += model.byteLength;
    }

    let indexedDBSize = 0;
    let modelCount = 0;
    
    if (this.db) {
      const transaction = this.db.transaction(['models'], 'readonly');
      const store = transaction.objectStore('models');
      const request = store.getAll();
      
      const models = await new Promise<any[]>((resolve) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => resolve([]);
      });
      
      modelCount = models.length;
      indexedDBSize = models.reduce((sum, m) => sum + m.size, 0);
    }

    return { memorySize, indexedDBSize, modelCount };
  }
}

// 模組級單例
export const modelManager = ModelManager.getInstance();
```

### 6.2 服務中的模型使用

```typescript
// services/vad/silero-vad.ts
import * as ort from 'onnxruntime-web';
import { modelManager, ModelConfig } from '../../models/model-manager';

export class SileroVAD {
  private static instance: SileroVAD;
  private session: ort.InferenceSession | null = null;
  private modelConfig: ModelConfig;

  private constructor() {
    // 預設使用內建的量化模型
    this.modelConfig = {
      type: 'builtin',
      quantized: true,
      cache: true
    };
  }

  static getInstance(): SileroVAD {
    if (!SileroVAD.instance) {
      SileroVAD.instance = new SileroVAD();
    }
    return SileroVAD.instance;
  }

  // 允許用戶覆蓋模型配置
  async initialize(customConfig?: Partial<ModelConfig>): Promise<void> {
    // 合併配置
    this.modelConfig = { ...this.modelConfig, ...customConfig };

    // 載入模型
    const modelData = await modelManager.loadModel('silero-vad', this.modelConfig);

    // 創建 ONNX Runtime session
    this.session = await ort.InferenceSession.create(modelData, {
      executionProviders: ['wasm'],  // 使用 WASM backend
      graphOptimizationLevel: 'all'
    });

    console.log('Silero VAD initialized');
  }

  async detect(audioData: Float32Array): Promise<{
    isSpeech: boolean;
    confidence: number;
  }> {
    if (!this.session) {
      throw new Error('VAD not initialized');
    }

    // 準備輸入張量
    const inputTensor = new ort.Tensor('float32', audioData, [1, audioData.length]);

    // 執行推理
    const results = await this.session.run({ input: inputTensor });
    
    // 解析結果
    const output = results.output.data as Float32Array;
    const confidence = output[0];
    
    return {
      isSpeech: confidence > 0.5,
      confidence: confidence
    };
  }
}

export const sileroVAD = SileroVAD.getInstance();
```

### 6.3 配置中的模型設定

```typescript
// 使用範例 1: 使用內建模型
const asr = new WebASRCore({
  services: {
    vad: {
      enabled: true,
      modelConfig: {
        type: 'builtin',
        quantized: true,  // 使用量化版本以減少大小
        cache: true
      }
    }
  }
});

// 使用範例 2: 從本地檔案系統載入
const fileInput = document.getElementById('model-file') as HTMLInputElement;
fileInput.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  
  const asr = new WebASRCore({
    services: {
      vad: {
        enabled: true,
        modelConfig: {
          type: 'custom',
          path: file,  // 直接傳入 File 物件
          cache: true
        }
      }
    }
  });
});

// 使用範例 3: 從相對路徑載入（相對於網站根目錄）
const asr = new WebASRCore({
  services: {
    wakeWord: {
      enabled: true,
      modelConfig: {
        type: 'custom',
        path: '/assets/models/custom-wakeword.onnx',  // 本地相對路徑
        cache: true
      }
    }
  }
});

// 使用範例 4: 從遠端 URL 載入
const asr = new WebASRCore({
  services: {
    denoise: {
      enabled: true,
      modelConfig: {
        type: 'custom',
        path: 'https://example.com/models/rnnoise.wasm',  // 遠端 URL
        cache: true
      }
    }
  }
});

// 使用範例 5: 從 Hugging Face 載入
const asr = new WebASRCore({
  providers: {
    whisper: {
      modelConfig: {
        type: 'huggingface',
        path: 'openai/whisper-tiny',  // HF 模型 ID
        quantized: true,
        cache: true
      }
    }
  }
});

// 動態載入模型檔案
const modelFileInput = document.getElementById('upload-model') as HTMLInputElement;
modelFileInput.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (file) {
    // 直接使用 File 物件
    const modelData = await modelManager.loadFromFileInput(file);
    
    // 或者透過配置
    await asr.services.vad.initialize({
      type: 'custom',
      path: file,
      cache: true
    });
  }
});
```

## 8. 性能優化策略

### 7.1 智慧型模型預載入

```typescript
class ModelPreloader {
  static async preloadEssentials(): Promise<void> {
    // 預載入常用的小模型
    const essentials = [
      { name: 'silero-vad', config: { type: 'builtin', quantized: true } },
      { name: 'openwakeword-hey', config: { type: 'builtin', quantized: true } }
    ];

    await Promise.all(
      essentials.map(m => modelManager.loadModel(m.name, m.config))
    );
  }

  static async preloadOnIdle(): Promise<void> {
    // 在瀏覽器空閒時預載入大模型
    if ('requestIdleCallback' in window) {
      requestIdleCallback(async () => {
        await modelManager.loadModel('whisper-tiny', {
          type: 'builtin',
          quantized: true,
          cache: true
        });
      });
    }
  }
}
```

### 7.2 Web Worker 隔離

```typescript
// workers/vad.worker.ts
let vadModel: any = null;

self.onmessage = async (event) => {
  const { type, data } = event.data;

  switch (type) {
    case 'init':
      // 載入模型
      vadModel = await loadVADModel(data.modelPath);
      self.postMessage({ type: 'ready' });
      break;

    case 'process':
      // 處理音訊
      const result = await vadModel.process(data.audio);
      self.postMessage({ 
        type: 'result', 
        data: { isSpeech: result.isSpeech, confidence: result.confidence }
      });
      break;
  }
};
```

### 7.3 音訊緩衝優化

```typescript
class OptimizedBuffer {
  private buffer: Float32Array;
  private writeIndex = 0;
  private readIndex = 0;

  constructor(size: number) {
    this.buffer = new Float32Array(size);
  }

  push(data: Float32Array): void {
    // 環形緩衝區實現
    for (let i = 0; i < data.length; i++) {
      this.buffer[this.writeIndex] = data[i];
      this.writeIndex = (this.writeIndex + 1) % this.buffer.length;
    }
  }

  read(size: number): Float32Array {
    const result = new Float32Array(size);
    for (let i = 0; i < size; i++) {
      result[i] = this.buffer[this.readIndex];
      this.readIndex = (this.readIndex + 1) % this.buffer.length;
    }
    return result;
  }
}
```

## 9. 測試策略

### 7.1 單元測試

```typescript
// tests/services/microphone.test.ts
describe('MicrophoneCapture', () => {
  it('should request correct audio constraints', async () => {
    const mockGetUserMedia = jest.fn();
    navigator.mediaDevices.getUserMedia = mockGetUserMedia;

    await microphoneCapture.start(() => {});

    expect(mockGetUserMedia).toHaveBeenCalledWith({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true
      }
    });
  });
});
```

### 7.2 整合測試

```typescript
// tests/integration/pipeline.test.ts
describe('Audio Pipeline', () => {
  it('should process audio through complete pipeline', async () => {
    const asr = new WebASRCore(testConfig);
    const results: any[] = [];

    asr.on('transcription', (result) => {
      results.push(result);
    });

    // 模擬音訊輸入
    await simulateAudioInput(asr, testAudioFile);

    expect(results).toHaveLength(greaterThan(0));
    expect(results[results.length - 1].isFinal).toBe(true);
  });
});
```

## 10. 部署和發布

### 8.1 NPM 發布配置

```json
{
  "name": "webasr-core",
  "version": "1.0.0",
  "description": "零伺服器依賴的前端語音識別核心庫",
  "main": "dist/webasr-core.umd.js",
  "module": "dist/webasr-core.esm.js",
  "types": "dist/types/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/webasr-core.esm.js",
      "require": "./dist/webasr-core.umd.js",
      "types": "./dist/types/index.d.ts"
    }
  },
  "files": [
    "dist",
    "models"
  ],
  "sideEffects": false,
  "scripts": {
    "build": "vite build",
    "test": "vitest",
    "lint": "eslint src",
    "type-check": "tsc --noEmit"
  },
  "keywords": [
    "speech-recognition",
    "asr",
    "voice",
    "audio",
    "webrtc",
    "whisper",
    "vad",
    "wake-word"
  ],
  "license": "MIT"
}
```

### 8.2 CDN 配置

```javascript
// vite.config.js
export default {
  build: {
    lib: {
      entry: 'src/index.ts',
      name: 'WebASRCore',
      formats: ['es', 'umd']
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {}
      }
    }
  }
};
```

## 11. Worker 整合架構

### 11.1 Worker 管理器

基於 POC 實踐，提供完整的 Worker 管理架構：

```typescript
export class WorkerManager {
  private workers: Map<string, Worker> = new Map();
  private pendingMessages: Map<string, PendingMessage> = new Map();
  
  /**
   * 創建或獲取 Worker
   */
  async getWorker(type: WorkerType): Promise<Worker> {
    if (this.workers.has(type)) {
      return this.workers.get(type)!;
    }
    
    const worker = await this.createWorker(type);
    this.workers.set(type, worker);
    return worker;
  }
  
  /**
   * 創建 Worker
   */
  private async createWorker(type: WorkerType): Promise<Worker> {
    const basePath = window.location.pathname.replace(/\/[^\/]*$/, '/');
    const workerPath = `${basePath}workers/${type}.worker.js`;
    
    const worker = new Worker(workerPath, { type: 'module' });
    
    // 設定訊息處理
    worker.onmessage = (event) => {
      const data = event.data;
      
      // 處理帶 messageId 的回應
      if (data.messageId && this.pendingMessages.has(data.messageId)) {
        const handler = this.pendingMessages.get(data.messageId)!;
        this.pendingMessages.delete(data.messageId);
        
        if (data.error) {
          handler.reject(new Error(data.error));
        } else {
          handler.resolve(data);
        }
      } else {
        // 處理一般訊息
        this.handleWorkerMessage(type, data);
      }
    };
    
    worker.onerror = (error) => {
      console.error(`[${type}] Worker error:`, error);
      this.handleWorkerError(type, error);
    };
    
    // 初始化 Worker
    await this.sendMessage(worker, {
      type: 'initialize',
      config: this.getWorkerConfig(type)
    });
    
    return worker;
  }
  
  /**
   * 發送訊息給 Worker 並等待回應
   */
  async sendMessage(worker: Worker, message: any): Promise<any> {
    return new Promise((resolve, reject) => {
      const messageId = this.generateMessageId();
      
      this.pendingMessages.set(messageId, { resolve, reject });
      
      worker.postMessage({
        ...message,
        messageId
      });
      
      // 超時處理
      setTimeout(() => {
        if (this.pendingMessages.has(messageId)) {
          this.pendingMessages.delete(messageId);
          reject(new Error('Worker message timeout'));
        }
      }, 30000); // 30 秒超時
    });
  }
}

export const workerManager = new WorkerManager();
```

### 11.2 ML 推論 Worker

專門處理 ONNX Runtime 推論：

```typescript
// workers/ml-inference.worker.js
import * as ort from 'onnxruntime-web';

class MLInferenceWorker {
  private sessions: Map<string, ort.InferenceSession> = new Map();
  
  async handleMessage(event: MessageEvent) {
    const { type, data, messageId } = event.data;
    
    try {
      switch (type) {
        case 'initialize':
          await this.initialize(data);
          self.postMessage({ messageId, success: true });
          break;
          
        case 'loadModel':
          const session = await this.loadModel(data);
          self.postMessage({ messageId, sessionId: data.modelId });
          break;
          
        case 'inference':
          const result = await this.runInference(data);
          self.postMessage({ messageId, result });
          break;
          
        default:
          throw new Error(`Unknown message type: ${type}`);
      }
    } catch (error) {
      self.postMessage({
        messageId,
        error: error.message
      });
    }
  }
  
  private async loadModel(data: any): Promise<void> {
    const { modelId, modelPath, options } = data;
    
    const session = await ort.InferenceSession.create(
      modelPath,
      options
    );
    
    this.sessions.set(modelId, session);
  }
  
  private async runInference(data: any): Promise<any> {
    const { sessionId, inputs } = data;
    const session = this.sessions.get(sessionId);
    
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }
    
    // 轉換輸入為 ONNX Tensor
    const feeds: Record<string, ort.Tensor> = {};
    for (const [name, value] of Object.entries(inputs)) {
      feeds[name] = new ort.Tensor(
        value.type,
        value.data,
        value.dims
      );
    }
    
    // 執行推論
    const results = await session.run(feeds);
    
    // 轉換輸出
    const outputs: Record<string, any> = {};
    for (const [name, tensor] of Object.entries(results)) {
      outputs[name] = {
        data: tensor.data,
        dims: tensor.dims,
        type: tensor.type
      };
    }
    
    return outputs;
  }
}

const worker = new MLInferenceWorker();
self.addEventListener('message', (e) => worker.handleMessage(e));
```

## 12. 系統架構圖

### 9.1 整體架構

```
┌──────────────────────────────────────────────┐
│                 WebASR Core                      │
├──────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐     ┌──────────┐                 │
│  │   FSM    │────▶│  Store   │                 │
│  │ (XState) │     │(SolidJS) │                 │
│  └──────────┘     └──────────┘                 │
│       ▲                │                        │
│       │                ▼                        │
│  ┌──────────────────────────────────────┐      │
│  │           Services Layer              │      │
│  │  ┌──────────┐  ┌──────────┐         │      │
│  │  │Microphone│  │   VAD    │         │      │
│  │  └──────────┘  └──────────┘         │      │
│  │  ┌──────────┐  ┌──────────┐         │      │
│  │  │WakeWord  │  │  Timer   │         │      │
│  │  └──────────┘  └──────────┘         │      │
│  └──────────────────────────────────────┘      │
│                                                  │
│  ┌──────────────────────────────────────┐      │
│  │         Audio Processing              │      │
│  │  ┌──────────┐  ┌──────────┐         │      │
│  │  │AudioQueue│  │ Buffer   │         │      │
│  │  │(Storage) │  │ Manager  │         │      │
│  │  └──────────┘  └──────────┘         │      │
│  └──────────────────────────────────────┘      │
│                                                  │
│  ┌──────────────────────────────────────┐      │
│  │           ASR Providers               │      │
│  │  ┌──────────┐  ┌──────────┐         │      │
│  │  │WebSpeech │  │ Whisper  │         │      │
│  │  └──────────┘  └──────────┘         │      │
│  └──────────────────────────────────────┘      │
└──────────────────────────────────────────────┘
```

### 9.2 音訊處理流程圖

```
┌──────────────────────────────────────────────────────┐
│                   Audio Processing Pipeline               │
│                                                           │
│  Microphone ──▶ AudioQueue ──▶ BufferManager             │
│                     │               │                     │
│                     │               ▼                     │
│                     │        OpenWakeWord Buffer         │
│                     │         (1024 samples)             │
│                     │               │                     │
│                     │               ▼                     │
│                     │         Wake Detected              │
│                     │               │                     │
│                     ▼               ▼                     │
│                Clear Queue    Start Recording            │
│                     │               │                     │
│                     ▼               ▼                     │
│                AudioQueue    BufferManager               │
│               (Recording)     (VAD Buffer)               │
│                     │         (512 samples)              │
│                     │               │                     │
│                     │               ▼                     │
│                     │          VAD Service               │
│                     │               │                     │
│                     │               ▼                     │
│                     │       Silence Detected             │
│                     │               │                     │
│                     │               ▼                     │
│                     │       Countdown Timer              │
│                     │               │                     │
│                     │               ▼                     │
│                     └─────────▶ BufferManager            │
│                              (ASR Buffer)                │
│                                    │                     │
│                                    ▼                     │
│                              ASR Provider                │
│                         ├─▶ WebSpeech (4096/2048)      │
│                         └─▶ Whisper (dynamic)          │
└──────────────────────────────────────────────────────┘
```

### 9.3 AudioQueue 與 BufferManager 協作

```
┌──────────────────────────────────────────────────────┐
│                  AudioQueue (暫存)                       │
│                                                          │
│  [chunk1][chunk2][chunk3][chunk4][chunk5][chunk6]...    │
│     ▲                                                    │
│     │ push (from microphone)                            │
│     │                                                    │
│  readIndex ────────────────▶                           │
│                                                          │
└──────────────────────────────────────────────────────┘
                    │ read (non-destructive)
                    ▼
┌──────────────────────────────────────────────────────┐
│              BufferManager Instances                     │
├──────────────────────────────────────────────────────┤
│                                                          │
│  OpenWakeWord Buffer:  [1024 samples] ──▶ Process       │
│                                                          │
│  VAD Buffer:          [512 samples]  ──▶ Process        │
│                                                          │
│  WebSpeech Buffer:    [4096 samples] ──▶ Stream         │
│                        (step: 2048)                      │
│                                                          │
│  Whisper Buffer:      [dynamic size] ──▶ Batch          │
│                        (1-30 seconds)                    │
│                                                          │
└──────────────────────────────────────────────────────┘
```

### 9.4 關鍵設計說明

#### AudioQueue 職責
- **暫存音訊**: 持續接收並儲存來自麥克風的音訊數據
- **非破壞性讀取**: 使用 readIndex 追蹤讀取位置，不刪除數據
- **循環緩衝**: 當達到最大容量時，使用 FIFO 策略
- **清空機制**: 喚醒詞觸發時清空佇列，開始新的錄音段

#### BufferManager 職責
- **窗口管理**: 根據不同服務需求，提供適當大小的數據窗口
- **模式支援**:
  - Fixed: 固定大小窗口（VAD: 512, OpenWakeWord: 1024）
  - Sliding: 滑動窗口（WebSpeech: 4096/2048）
  - Dynamic: 動態累積（Whisper: 1-30秒）
- **從 AudioQueue 取值**: 非破壞性地從 AudioQueue 讀取數據
- **就緒檢查**: 判斷是否有足夠數據供服務處理

## 10. 開發路線圖

### Phase 1 - MVP (第一階段)
- [x] 核心架構設計
- [ ] FSM 狀態機實現
- [ ] 音訊佇列和緩衝管理
- [ ] 麥克風擷取服務
- [ ] WebSpeech API 整合
- [ ] 基本配置系統

### Phase 2 - 進階功能
- [ ] VAD 服務實現（Silero ONNX）
- [ ] 喚醒詞檢測（OpenWakeWord）
- [ ] Whisper 整合（Transformers.js）
- [ ] Web Worker 優化
- [ ] 降噪服務（RNNoise WASM）

### Phase 3 - 生產就緒
- [ ] 完整測試覆蓋
- [ ] 性能優化
- [ ] 文檔完善
- [ ] 範例應用
- [ ] CI/CD 設置
- [ ] NPM 發布

### Phase 4 - 生態系統
- [ ] React Hooks
- [ ] Vue Composables  
- [ ] Angular Service
- [ ] 插件系統
- [ ] 自定義 Provider 支援

## 10. 技術挑戰和解決方案

### 10.1 模型大小問題

**挑戰**：ML 模型檔案較大，影響載入速度

**解決方案**：
- 模型量化（INT8）
- 分層載入（按需載入）
- CDN 託管 + 快取策略
- 提供多種模型大小選項

### 10.2 跨瀏覽器兼容性

**挑戰**：不同瀏覽器 API 支援度不一

**解決方案**：
- Polyfill 策略
- 功能檢測 + 優雅降級
- 多 Provider 備選方案

### 10.3 實時性能要求

**挑戰**：音訊處理需要低延遲

**解決方案**：
- AudioWorklet 處理音訊
- Web Worker 運行 ML 推理
- 環形緩衝區優化
- WebAssembly 加速

## 11. 安全性考量

- **隱私保護**：所有處理本地完成，無數據上傳
- **權限管理**：明確的麥克風權限請求流程
- **錯誤處理**：完善的錯誤邊界和降級策略
- **資源清理**：自動釋放音訊資源和記憶體

## 12. 結論

WebASRCore 通過承襲 ASRHub 的優秀架構設計，並針對前端環境進行優化，提供了一個強大、靈活且易用的語音識別解決方案。它不僅保護用戶隱私，還提供了出色的開發體驗和性能表現。

### 核心優勢總結

1. **零伺服器成本**：完全客戶端處理
2. **即插即用**：簡單的 API，豐富的配置選項
3. **漸進式架構**：按需啟用服務和功能
4. **響應式系統**：基於 SolidJS 的細粒度響應式架構
5. **生態友好**：支援主流前端框架
6. **未來就緒**：模組化設計便於擴展

### 核心音訊處理流程

1. **持續監聽**：麥克風音訊持續傳送給 OpenWakeWord
2. **喚醒觸發**：檢測到喚醒詞後清空佇列，開始新的錄音段
3. **VAD 監測**：同時啟動 VAD 檢測語音活動
4. **靜音檢測**：當 VAD 檢測到靜音時啟動倒數計時
5. **倒數計時**：倒數期間若重新檢測到語音則取消倒數
6. **轉譯處理**：
   - **串流模式**：即時傳送給 Web Speech API
   - **非串流模式**：倒數結束後將整個錄音佇列傳送給 Whisper
7. **循環監聽**：完成轉譯後自動返回喚醒詞監聽狀態

### SolidJS 優勢

- **細粒度響應式**：只更新真正改變的部分，最小化渲染開銷
- **自動依賴追蹤**：無需手動管理訂閱和取消訂閱
- **輕量級**：比 RxJS 更小的 bundle size
- **直覺 API**：更簡單的響應式程式設計模型

透過這個設計，開發者可以快速構建具有語音識別能力的 Web 應用，無需擔心後端基礎設施和隱私問題。

---

*本設計文檔基於 ASRHub v0.3.0 架構理念*
*文檔版本: 1.0.0*
*更新日期: 2025*