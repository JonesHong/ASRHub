# WebASRCore - 前端語音識別核心庫設計文檔

## 目錄

### 第一部分：入門指南
- [1. 專案概覽](#1-專案概覽)
- [2. 快速開始](#2-快速開始)

### 第二部分：架構設計
- [3. 系統架構](#3-系統架構)
- [4. 狀態機設計](#4-狀態機設計)

### 第三部分：核心組件
- [5. 核心組件實作](#5-核心組件實作)

### 第四部分：服務與Provider
- [6. 服務層架構](#6-服務層架構)
- [7. ASR Provider 系統](#7-asr-provider-系統)
- [8. 模型管理系統](#8-模型管理系統)

### 第五部分：Worker 與效能
- [9. Worker 架構](#9-worker-架構)
- [10. 效能優化](#10-效能優化)

### 第六部分：配置與部署
- [11. 配置管理](#11-配置管理)
- [12. 部署指南](#12-部署指南)

### 第七部分：開發支援
- [13. 開發指南](#13-開發指南)
- [14. 故障排除](#14-故障排除)

### 第八部分：參考文檔
- [15. API 參考](#15-api-參考)
- [16. 附錄](#16-附錄)

---

## 1. 專案概覽

### 1.1 專案介紹

WebASRCore 是一個基於 ASRHub 架構理念設計的純前端語音識別庫。它承襲了 ASRHub 的核心設計原則：KISS（Keep It Simple, Stupid）、無狀態服務架構、和音訊處理管線模式，同時針對瀏覽器環境進行了優化。

### 1.2 核心設計理念

1. **KISS 原則** - 保持簡單直接，避免過度工程化
2. **無狀態服務** - 每個服務專注單一職責
3. **音訊處理管線** - 標準化的音訊流處理
4. **隱私優先** - 支援完全本地處理

### 1.3 核心特性

- 🎯 **零伺服器依賴**：完全在瀏覽器端運行
- 🔐 **隱私優先**：音訊數據不離開用戶設備
- 📦 **輕量級**：支援按需載入和 Tree Shaking
- 🌐 **CDN 友善**：可直接透過 script 標籤引入
- 🔧 **高度可配置**：靈活的服務啟用/停用機制
- 🚀 **即時處理**：低延遲的本地音訊處理

### 1.4 ASR Provider 隱私分級

```typescript
export enum PrivacyLevel {
  LOCAL = 'local',        // 完全本地處理
  CLOUD_PROXY = 'cloud'   // 使用雲端服務  
}

export const PROVIDER_PRIVACY = {
  whisper: {
    level: PrivacyLevel.LOCAL,
    notice: '音訊完全在您的裝置上處理'
  },
  webSpeech: {
    level: PrivacyLevel.CLOUD_PROXY,
    notice: '音訊將上傳至 Google/Apple 伺服器'
  }
};

// 初始化時提示用戶
if (!config.provider) {
  const choice = await showProviderSelectionDialog();
  config.provider = choice;
}
```

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

### 2.3 Worker/Worklet 載入策略

使用 `import.meta.url` 確保正確的相對路徑解析：

```typescript
// services/worker-loader.ts
export class WorkerLoader {
  static createWorker(type: 'vad' | 'wakeword' | 'whisper'): Worker {
    // 使用 import.meta.url 確保 CDN 和子目錄部署相容
    const workerUrl = new URL(`./workers/${type}.worker.js`, import.meta.url);
    return new Worker(workerUrl, { type: 'module' });
  }
  
  static async createAudioWorklet(
    audioContext: AudioContext,
    processorName: string
  ): Promise<AudioWorkletNode> {
    // 使用 import.meta.url 載入 AudioWorklet
    const processorUrl = new URL(
      `./worklets/${processorName}.worklet.js`, 
      import.meta.url
    );
    
    await audioContext.audioWorklet.addModule(processorUrl);
    return new AudioWorkletNode(audioContext, processorName);
  }
}

// 使用範例
const vadWorker = WorkerLoader.createWorker('vad');
const audioWorklet = await WorkerLoader.createAudioWorklet(
  audioContext, 
  'audio-processor'
);
```

### 2.4 模型打包與載入策略

模型採用分離式打包，支援 CDN 載入和按需下載：

```typescript
// models/model-loader.ts
export interface ModelConfig {
  name: string;
  version: string;
  baseUrl?: string;  // 預設使用 import.meta.url 相對路徑
  files: {
    model: string;
    config?: string;
    tokenizer?: string;
  };
  cache?: boolean;  // 是否使用 IndexedDB 快取
}

export class ModelLoader {
  private static readonly DEFAULT_CDN = 'https://unpkg.com/@webasr/models@latest';
  private cache: Map<string, ArrayBuffer> = new Map();
  
  async loadModel(config: ModelConfig): Promise<ArrayBuffer> {
    // 支援多種載入來源
    const baseUrl = config.baseUrl || 
                   new URL('../models/', import.meta.url).href;
    
    const modelUrl = `${baseUrl}/${config.name}/${config.files.model}`;
    
    // 檢查快取
    if (config.cache) {
      const cached = await this.loadFromIndexedDB(modelUrl);
      if (cached) return cached;
    }
    
    // 使用 link prefetch 預載入
    this.prefetchModel(modelUrl);
    
    // 實際載入模型
    const response = await fetch(modelUrl, {
      method: 'GET',
      cache: 'force-cache',
      mode: 'cors'
    });
    
    if (!response.ok) {
      throw new Error(`Failed to load model: ${response.status}`);
    }
    
    const buffer = await response.arrayBuffer();
    
    // 儲存到 IndexedDB
    if (config.cache) {
      await this.saveToIndexedDB(modelUrl, buffer);
    }
    
    return buffer;
  }
  
  private prefetchModel(url: string): void {
    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = url;
    link.as = 'fetch';
    link.crossOrigin = 'anonymous';
    document.head.appendChild(link);
  }
}

// 模型打包為獨立 NPM 套件
// @webasr/models 套件結構：
// - /vad/silero_vad.onnx
// - /wakeword/hey_assistant.onnx
// - /whisper/whisper-tiny.onnx
```

### 2.5 執行模式管理器（ExecutionModeManager）

基於 POC 實作的執行模式管理器，負責檢測能力並決定最佳執行策略：

```typescript
interface SystemCapabilities {
  webWorker: boolean;
  sharedArrayBuffer: boolean;
  webAssembly: boolean;
  webGPU: boolean;
  webGL2: boolean;
  hardwareConcurrency: number;
  deviceMemory: number;
  connection: NetworkInfo;
  offscreenCanvas: boolean;
  atomics: boolean;
  simd: boolean;
  threads: boolean;
  performanceScore: number;
}

interface ExecutionMode {
  mode: string;
  score: number;
  description: string;
}

export class ExecutionModeManager {
  private capabilities: SystemCapabilities;
  private executionChain: ExecutionMode[] = [];
  private currentMode: ExecutionMode;
  private performanceMetrics = {
    worker: new Map<string, number[]>(),
    main: new Map<string, number[]>()
  };

  async initialize(): Promise<{
    capabilities: SystemCapabilities;
    currentMode: ExecutionMode;
    availableModes: ExecutionMode[];
  }> {
    // 檢測完整系統能力
    this.capabilities = await this.detectFullCapabilities();
    
    // 建立執行鏈（按優先順序）
    this.executionChain = this.buildExecutionChain();
    
    // 決定初始模式
    this.currentMode = await this.determineOptimalMode();
    
    console.log('[ExecutionMode] Initialized:', {
      capabilities: this.capabilities,
      executionChain: this.executionChain,
      currentMode: this.currentMode
    });
    
    return {
      capabilities: this.capabilities,
      currentMode: this.currentMode,
      availableModes: this.executionChain
    };
  }

  private async detectFullCapabilities(): Promise<SystemCapabilities> {
    const caps: SystemCapabilities = {
      // 基礎能力
      webWorker: typeof Worker !== 'undefined',
      sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
      webAssembly: typeof WebAssembly !== 'undefined',
      
      // GPU 相關
      webGPU: await this.checkWebGPU(),
      webGL2: this.checkWebGL2(),
      
      // 效能相關
      hardwareConcurrency: navigator.hardwareConcurrency || 1,
      deviceMemory: (navigator as any).deviceMemory || 0,
      connection: this.getConnectionInfo(),
      
      // 瀏覽器特性
      offscreenCanvas: typeof OffscreenCanvas !== 'undefined',
      atomics: typeof Atomics !== 'undefined',
      
      // ONNX Runtime 特定
      simd: await this.checkSIMD(),
      threads: self.crossOriginIsolated || false,
      
      performanceScore: 0  // 稍後計算
    };
    
    // 計算效能分數
    caps.performanceScore = this.calculatePerformanceScore(caps);
    
    return caps;
  }

  private buildExecutionChain(): ExecutionMode[] {
    const chain: ExecutionMode[] = [];
    const caps = this.capabilities;
    
    // 最佳：Worker + WebGPU
    if (caps.webWorker && caps.webGPU) {
      chain.push({
        mode: 'worker-webgpu',
        score: 100,
        description: 'Worker with WebGPU acceleration'
      });
    }
    
    // 次佳：Worker + WASM (SIMD + Threads)
    if (caps.webWorker && caps.simd && caps.threads) {
      chain.push({
        mode: 'worker-wasm-simd-threads',
        score: 90,
        description: 'Worker with WASM SIMD and multi-threading'
      });
    }
    
    // 良好：Worker + WASM (SIMD)
    if (caps.webWorker && caps.simd) {
      chain.push({
        mode: 'worker-wasm-simd',
        score: 80,
        description: 'Worker with WASM SIMD'
      });
    }
    
    // 標準：Worker + WASM
    if (caps.webWorker) {
      chain.push({
        mode: 'worker-wasm',
        score: 70,
        description: 'Worker with basic WASM'
      });
    }
    
    // 降級：主執行緒 + WebGPU
    if (caps.webGPU) {
      chain.push({
        mode: 'main-webgpu',
        score: 60,
        description: 'Main thread with WebGPU'
      });
    }
    
    // 基礎：主執行緒 + WASM
    chain.push({
      mode: 'main-wasm',
      score: 50,
      description: 'Main thread with WASM'
    });
    
    // 按分數排序
    return chain.sort((a, b) => b.score - a.score);
  }

  // 降級到下一個執行模式（允許一次性降級）
  fallbackToNextMode(): ExecutionMode | null {
    const currentIndex = this.executionChain.findIndex(
      m => m.mode === this.currentMode.mode
    );
    
    if (currentIndex < this.executionChain.length - 1) {
      this.currentMode = this.executionChain[currentIndex + 1];
      console.warn(`[ExecutionMode] Downgraded to: ${this.currentMode.mode}`);
      this.logDowngradeEvent();
      return this.currentMode;
    }
    
    console.error('[ExecutionMode] Already at lowest mode, cannot downgrade');
    return null;
  }

  // 記錄效能指標
  recordPerformance(mode: string, operation: string, duration: number): void {
    const modeType = mode.includes('worker') ? 'worker' : 'main';
    const metrics = this.performanceMetrics[modeType].get(operation) || [];
    
    metrics.push(duration);
    // 保留最近 100 筆記錄
    if (metrics.length > 100) metrics.shift();
    
    this.performanceMetrics[modeType].set(operation, metrics);
  }

  // 取得執行配置（供 ONNX Runtime 使用）
  getExecutionConfig(): any {
    const mode = this.currentMode;
    const config: any = {
      mode: mode.mode,
      useWorker: mode.mode.includes('worker'),
      useWebGPU: mode.mode.includes('webgpu'),
      useSIMD: mode.mode.includes('simd'),
      useThreads: mode.mode.includes('threads'),
      description: mode.description
    };
    
    // ONNX Runtime 配置
    if (config.useWebGPU) {
      config.executionProviders = ['webgpu', 'wasm'];
    } else {
      config.executionProviders = ['wasm'];
    }
    
    // WASM 配置
    config.wasmOptions = {
      simd: config.useSIMD,
      threads: config.useThreads,
      numThreads: config.useThreads ? 
        Math.min(4, this.capabilities.hardwareConcurrency) : 1
    };
    
    return config;
  }

  // 輔助方法
  private async checkWebGPU(): Promise<boolean> {
    if (!navigator.gpu) return false;
    try {
      const adapter = await navigator.gpu.requestAdapter();
      return !!adapter;
    } catch {
      return false;
    }
  }

  private checkWebGL2(): boolean {
    try {
      const canvas = document.createElement('canvas');
      return !!canvas.getContext('webgl2');
    } catch {
      return false;
    }
  }

  private async checkSIMD(): Promise<boolean> {
    try {
      // 檢查 WebAssembly SIMD
      const simdTest = new Uint8Array([
        0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b, 0x03,
        0x02, 0x01, 0x00, 0x0a, 0x0a, 0x01, 0x08, 0x00,
        0x41, 0x00, 0xfd, 0x0f, 0x0b
      ]);
      return WebAssembly.validate(simdTest);
    } catch {
      return false;
    }
  }

  private calculatePerformanceScore(caps: SystemCapabilities): number {
    let score = 0;
    
    // 硬體因素
    score += Math.min(caps.hardwareConcurrency * 10, 80);
    score += Math.min(caps.deviceMemory * 5, 40);
    
    // GPU 支援
    if (caps.webGPU) score += 50;
    else if (caps.webGL2) score += 30;
    
    // 進階功能
    if (caps.sharedArrayBuffer) score += 20;
    if (caps.simd) score += 20;
    if (caps.threads) score += 20;
    if (caps.offscreenCanvas) score += 10;
    if (caps.atomics) score += 10;
    
    // 網路狀況
    const conn = caps.connection;
    if (conn?.effectiveType === '4g') score += 10;
    else if (conn?.effectiveType === '3g') score += 5;
    
    return Math.min(score, 300);
  }

  private getConnectionInfo(): any {
    const connection = (navigator as any).connection || 
                      (navigator as any).mozConnection || 
                      (navigator as any).webkitConnection;
    
    if (!connection) return null;
    
    return {
      type: connection.type || 'unknown',
      effectiveType: connection.effectiveType || 'unknown',
      downlink: connection.downlink || 0,
      rtt: connection.rtt || 0,
      saveData: connection.saveData || false
    };
  }

  private determineOptimalMode(): ExecutionMode {
    const score = this.capabilities.performanceScore;
    
    if (score >= 200) {
      // 高效能設備：使用最佳模式
      return this.executionChain[0];
    } else if (score >= 100) {
      // 中等設備：平衡效能和資源
      const workerModes = this.executionChain.filter(m => 
        m.mode.includes('worker')
      );
      return workerModes[Math.min(1, workerModes.length - 1)] || 
             this.executionChain[0];
    } else {
      // 低效能設備：使用輕量模式
      const mainModes = this.executionChain.filter(m => 
        m.mode.includes('main')
      );
      return mainModes[0] || 
             this.executionChain[this.executionChain.length - 1];
    }
  }

  private logDowngradeEvent(): void {
    const event = {
      timestamp: Date.now(),
      from: this.executionChain[
        this.executionChain.indexOf(this.currentMode) - 1
      ],
      to: this.currentMode,
      capabilities: this.capabilities
    };
    
    // 儲存到 localStorage 供分析
    try {
      const events = JSON.parse(
        localStorage.getItem('execution_downgrades') || '[]'
      );
      events.push(event);
      localStorage.setItem('execution_downgrades', JSON.stringify(events));
    } catch (e) {
      console.error('[ExecutionMode] Failed to log downgrade event', e);
    }
  }
}

// 全局單例
export const executionModeManager = new ExecutionModeManager();
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

統一的 Provider 介面設計（區分串流與批次處理）：

```typescript
// providers/base.ts
export interface ASRProvider {
  name: string;
  privacyLevel: PrivacyLevel;
  supportsStreaming: boolean;  // 明確標示是否支援串流
  
  isAvailable(): Promise<boolean>;
  initialize(config?: any): Promise<void>;
  
  // Whisper 專用 - 批次轉譯
  transcribe?(audioSegment: AudioBuffer): Promise<TranscriptionResult>;
  
  // Web Speech API 專用 - 串流轉譯
  startStreaming?(onResult: (result: TranscriptionResult) => void): Promise<void>;
  stopStreaming?(): void;
  
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

// providers/whisper/provider.ts
export class WhisperProvider implements ASRProvider {
  name = 'whisper';
  privacyLevel = PrivacyLevel.LOCAL;
  supportsStreaming = false;  // Whisper 不支援真正的串流模式
  
  private pipeline: any = null;
  private audioBuffer: AudioBuffer[] = [];
  private isProcessing = false;
  
  async isAvailable(): Promise<boolean> {
    // 檢查 WebAssembly 和足夠的記憶體
    return 'WebAssembly' in window && 
           navigator.deviceMemory ? navigator.deviceMemory >= 4 : true;
  }
  
  async initialize(config: WhisperConfig): Promise<void> {
    const { pipeline } = await import('@xenova/transformers');
    
    // 載入 Whisper 模型（需要較長時間）
    this.pipeline = await pipeline(
      'automatic-speech-recognition',
      config.model || 'Xenova/whisper-tiny',
      {
        quantized: config.quantized ?? true,
        progress_callback: config.onProgress
      }
    );
  }
  
  // 批次轉譯 - Whisper 的唯一模式
  async transcribe(audioSegment: AudioBuffer): Promise<TranscriptionResult> {
    if (!this.pipeline) {
      throw new Error('Whisper not initialized');
    }
    
    if (this.isProcessing) {
      throw new Error('Whisper is already processing audio');
    }
    
    this.isProcessing = true;
    
    try {
      // 將 AudioBuffer 轉換為適合 Whisper 的格式
      const audioData = this.prepareAudioForWhisper(audioSegment);
      
      // 執行轉譯（這是一個完整的批次處理）
      const result = await this.pipeline(audioData, {
        language: config.language || 'zh',
        task: 'transcribe',
        chunk_length_s: 30,  // 30秒的音訊段落
        stride_length_s: 5    // 5秒的重疊
      });
      
      return {
        text: result.text,
        isFinal: true,  // Whisper 總是返回最終結果
        confidence: 1.0,  // Whisper 不提供信心分數
        timestamp: Date.now(),
        segments: result.chunks  // 包含時間戳的段落
      };
    } finally {
      this.isProcessing = false;
    }
  }
  
  // Whisper 不支援串流模式
  async startStreaming(): Promise<void> {
    throw new Error('Whisper does not support true streaming mode. Use transcribe() for batch processing.');
  }
  
  stopStreaming(): void {
    throw new Error('Whisper does not support streaming mode');
  }
  
  private prepareAudioForWhisper(audioBuffer: AudioBuffer): Float32Array {
    // 轉換為 16kHz 單聲道
    const targetSampleRate = 16000;
    const audioData = audioBuffer.getChannelData(0);
    
    // 如果採樣率不匹配，需要重採樣
    if (audioBuffer.sampleRate !== targetSampleRate) {
      // 實作重採樣邏輯
      return this.resample(audioData, audioBuffer.sampleRate, targetSampleRate);
    }
    
    return audioData;
  }
  
  private resample(data: Float32Array, fromRate: number, toRate: number): Float32Array {
    const ratio = fromRate / toRate;
    const newLength = Math.round(data.length / ratio);
    const result = new Float32Array(newLength);
    
    for (let i = 0; i < newLength; i++) {
      const index = i * ratio;
      const indexFloor = Math.floor(index);
      const indexCeil = Math.min(indexFloor + 1, data.length - 1);
      const fraction = index - indexFloor;
      
      result[i] = data[indexFloor] * (1 - fraction) + data[indexCeil] * fraction;
    }
    
    return result;
  }
  
  async destroy(): Promise<void> {
    this.pipeline = null;
    this.audioBuffer = [];
  }
}
```

### 4.1 串流模式的根本性差異

**重要說明：Whisper 與 Web Speech API 的根本差異**

```typescript
// 錯誤的理解：試圖讓 Whisper 支援串流
// ❌ 這是不可能的，Whisper 需要完整的音訊上下文
class IncorrectWhisperStreaming {
  async processChunk(chunk: AudioBuffer) {
    // 這會產生不連貫的轉譯結果
    return await whisper.transcribe(chunk);
  }
}

// 正確的理解：收集音訊後批次處理
// ✅ Whisper 需要完整的句子或段落
class CorrectWhisperBatch {
  private audioBuffer: AudioBuffer[] = [];
  
  collectChunk(chunk: AudioBuffer) {
    this.audioBuffer.push(chunk);
  }
  
  async processWhenReady() {
    // 當 VAD 偵測到靜音或達到時間限制
    const fullAudio = this.concatenateBuffers(this.audioBuffer);
    const result = await whisper.transcribe(fullAudio);
    this.audioBuffer = [];  // 清空緩衝區
    return result;
  }
}

// 使用場景的區分
export class ASRManager {
  private currentProvider: ASRProvider;
  
  selectProvider(requirements: ASRRequirements) {
    if (requirements.needRealtime && requirements.acceptCloudProcessing) {
      // 使用 Web Speech API（真串流）
      this.currentProvider = new WebSpeechProvider();
      console.log('Using Web Speech API for real-time streaming');
    } else if (requirements.needPrivacy || !requirements.needRealtime) {
      // 使用 Whisper（批次處理）
      this.currentProvider = new WhisperProvider();
      console.log('Using Whisper for private batch processing');
    }
  }
  
  async processAudio(audio: AudioBuffer) {
    if (this.currentProvider.supportsStreaming) {
      // Web Speech API：直接串流
      await this.currentProvider.startStreaming((result) => {
        console.log('Interim result:', result.text);
      });
    } else {
      // Whisper：收集後批次處理
      const result = await this.currentProvider.transcribe(audio);
      console.log('Final result:', result.text);
    }
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

### 7.0 模型打包策略

#### 分離式模型包

```json
// package.json
{
  "name": "@webasr/core",
  "version": "1.0.0",
  "files": [
    "dist",
    "!dist/models"  // 不包含模型
  ],
  "peerDependencies": {
    "@webasr/models": "^1.0.0"  // 可選
  }
}

// @webasr/models/package.json  
{
  "name": "@webasr/models",
  "version": "1.0.0",
  "files": [
    "manifest.json",
    "downloader.js"  // 不直接包含 .onnx
  ]
}
```

#### 模型 CDN 策略

```typescript
// 模型 manifest
export const MODEL_MANIFEST = {
  version: '1.0.0',
  models: {
    'silero-vad': {
      url: 'https://cdn.webasr.org/models/v1/silero-vad.onnx',
      size: 1800000,  // bytes
      hash: 'sha256-abc123...',  // SRI
      fallbacks: [
        'https://backup-cdn.webasr.org/models/v1/silero-vad.onnx',
        'https://huggingface.co/onnx-community/silero-vad/resolve/main/model.onnx'
      ]
    },
    'whisper-base': {
      url: 'https://cdn.webasr.org/models/v1/whisper-base/',
      files: [
        'encoder_model_quantized.onnx',
        'decoder_model_merged_quantized.onnx',
        'config.json',
        'tokenizer.json'
      ],
      totalSize: 148000000
    }
  }
};

// 支援 Range 請求和斷點續傳
class ModelDownloader {
  async downloadWithResume(url: string, onProgress?: (p: number) => void) {
    const stored = await this.getStoredChunks(url);
    const headers: HeadersInit = {};
    
    if (stored.size > 0) {
      headers['Range'] = `bytes=${stored.size}-`;
    }
    
    const response = await fetch(url, { headers });
    if (!response.ok && response.status !== 206) {
      throw new Error(`Failed to download: ${response.status}`);
    }
    
    // 處理分塊下載...
  }
}
```

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

### 10.1 COOP/COEP 部署手冊

#### 必要標頭設定

為了啟用 SharedArrayBuffer 和 WASM Threads，您的伺服器必須設定以下標頭：

```nginx
# Nginx 設定
add_header Cross-Origin-Opener-Policy "same-origin";
add_header Cross-Origin-Embedder-Policy "require-corp";
add_header Cross-Origin-Resource-Policy "cross-origin";
```

```apache
# Apache .htaccess
Header set Cross-Origin-Opener-Policy "same-origin"
Header set Cross-Origin-Embedder-Policy "require-corp"
Header set Cross-Origin-Resource-Policy "cross-origin"
```

```javascript
// Express.js
app.use((req, res, next) => {
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  next();
});
```

#### CDN 設定

如果使用 CDN，確保：

1. CDN 支援自訂標頭
2. 所有子資源（workers, wasm, models）都有正確 CORS 設定
3. 使用版本化 URL 避免快取問題

#### 降級策略

如果無法設定這些標頭：

```typescript
// 檢查 crossOriginIsolated 狀態
if (!self.crossOriginIsolated) {
  console.warn(
    'Page is not cross-origin isolated. ' +
    'Performance will be limited. ' +
    'See: https://web.dev/coop-coep/'
  );
  
  // 自動降級到單執行緒模式
  config.executionMode = 'worker'; // 不使用 threads
  config.onnxOptions.numThreads = 1;
  config.onnxOptions.simd = false;
}
```

## 10. 部署和發布（原有內容）

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
    // 使用 import.meta.url 獲取正確路徑
    const workerUrl = new URL(
      `./workers/${type}.worker.js`,
      import.meta.url
    );
    
    // 允許用戶覆寫 assets 路徑
    const finalUrl = this.config.assetsBaseUrl
      ? new URL(`workers/${type}.worker.js`, this.config.assetsBaseUrl)
      : workerUrl;
    
    const worker = new Worker(finalUrl.href, { type: 'module' });
    
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

## 13. COOP/COEP 部署手冊

### 13.1 為什麼需要 COOP/COEP

SharedArrayBuffer 和 WASM Threads 需要跨域隔離（Cross-Origin Isolation）環境，這需要設定兩個 HTTP 頭：

- **COOP (Cross-Origin-Opener-Policy)**: 防止其他來源的視窗存取你的視窗
- **COEP (Cross-Origin-Embedder-Policy)**: 確保所有資源都明確允許被嵌入

### 13.2 檢測 Cross-Origin Isolation

```javascript
// 檢測是否啟用了跨域隔離
if (self.crossOriginIsolated) {
  console.log('✅ Cross-Origin Isolation enabled');
  console.log('✅ SharedArrayBuffer available');
  console.log('✅ WASM Threads available');
} else {
  console.warn('⚠️ Cross-Origin Isolation disabled');
  console.warn('⚠️ Performance will be limited');
}
```

### 13.3 伺服器配置範例

#### Nginx
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # 啟用 COOP/COEP
    add_header Cross-Origin-Opener-Policy "same-origin" always;
    add_header Cross-Origin-Embedder-Policy "require-corp" always;
    
    # 額外的安全頭（可選但建議）
    add_header Cross-Origin-Resource-Policy "cross-origin" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    location / {
        root /var/www/webasr;
        try_files $uri $uri/ /index.html;
    }
    
    # 對 Worker 和 WASM 文件特別處理
    location ~* \.(wasm|worker\.js)$ {
        add_header Cross-Origin-Opener-Policy "same-origin" always;
        add_header Cross-Origin-Embedder-Policy "require-corp" always;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
```

#### Apache (.htaccess)
```apache
# 啟用 COOP/COEP
Header always set Cross-Origin-Opener-Policy "same-origin"
Header always set Cross-Origin-Embedder-Policy "require-corp"
Header always set Cross-Origin-Resource-Policy "cross-origin"

# 對特定文件類型設定
<FilesMatch "\.(wasm|worker\.js)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
</FilesMatch>
```

#### Node.js (Express)
```javascript
const express = require('express');
const app = express();

// COOP/COEP 中間件
app.use((req, res, next) => {
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  next();
});

// 服務靜態文件
app.use(express.static('dist'));

app.listen(3000);
```

#### Cloudflare Workers
```javascript
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const response = await fetch(request);
  
  // 複製響應並添加頭
  const newHeaders = new Headers(response.headers);
  newHeaders.set('Cross-Origin-Opener-Policy', 'same-origin');
  newHeaders.set('Cross-Origin-Embedder-Policy', 'require-corp');
  newHeaders.set('Cross-Origin-Resource-Policy', 'cross-origin');
  
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders
  });
}
```

#### GitHub Pages
GitHub Pages **不支援**自定義 HTTP 頭，因此無法啟用 SharedArrayBuffer。解決方案：

1. **使用 Service Worker 作為替代**（有限支援）
```javascript
// sw.js - Service Worker 降級方案
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('.wasm')) {
    event.respondWith(
      fetch(event.request).then(response => {
        const newHeaders = new Headers(response.headers);
        newHeaders.set('Cross-Origin-Embedder-Policy', 'require-corp');
        newHeaders.set('Cross-Origin-Opener-Policy', 'same-origin');
        
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders
        });
      })
    );
  }
});
```

2. **使用 Netlify/Vercel/Cloudflare Pages** 替代，它們支援自定義頭

### 13.4 第三方資源處理

當啟用 COEP 後，所有跨域資源都需要明確允許：

#### CDN 資源
```html
<!-- 需要 crossorigin 屬性 -->
<script src="https://cdn.jsdelivr.net/npm/onnxruntime-web@latest/dist/ort.min.js" 
        crossorigin="anonymous"></script>

<!-- 圖片也需要 -->
<img src="https://example.com/image.jpg" crossorigin="anonymous">
```

#### 動態載入資源
```javascript
// 載入跨域資源時設定 credentials
fetch('https://api.example.com/data', {
  mode: 'cors',
  credentials: 'omit',  // 或 'include' 如果需要 cookies
  headers: {
    'Content-Type': 'application/json'
  }
});

// 載入 Worker
const worker = new Worker(
  new URL('./worker.js', import.meta.url),
  { type: 'module', credentials: 'same-origin' }
);
```

### 13.5 降級策略

當無法啟用 COOP/COEP 時的降級方案：

```javascript
export class ExecutionModeDetector {
  static getAvailableMode() {
    if (self.crossOriginIsolated) {
      // 完整功能：SharedArrayBuffer + WASM Threads
      return {
        mode: 'full',
        features: {
          sharedArrayBuffer: true,
          wasmThreads: true,
          atomics: true,
          simd: true
        }
      };
    }
    
    // 降級模式：無 SharedArrayBuffer
    return {
      mode: 'degraded',
      features: {
        sharedArrayBuffer: false,
        wasmThreads: false,
        atomics: false,
        simd: this.checkSIMD()  // SIMD 仍可能可用
      },
      warning: 'Performance limited due to missing COOP/COEP headers'
    };
  }
  
  static checkSIMD() {
    try {
      // 測試 SIMD 支援
      const simdTest = new Uint8Array([
        0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b, 0x03,
        0x02, 0x01, 0x00, 0x0a, 0x0a, 0x01, 0x08, 0x00,
        0x41, 0x00, 0xfd, 0x0f, 0x0b
      ]);
      return WebAssembly.validate(simdTest);
    } catch {
      return false;
    }
  }
}
```

### 13.6 疑難排解

#### 問題：SharedArrayBuffer undefined
```javascript
// 診斷腳本
console.log('crossOriginIsolated:', self.crossOriginIsolated);
console.log('SharedArrayBuffer:', typeof SharedArrayBuffer);

// 檢查響應頭
fetch(location.href).then(r => {
  console.log('COOP:', r.headers.get('Cross-Origin-Opener-Policy'));
  console.log('COEP:', r.headers.get('Cross-Origin-Embedder-Policy'));
});
```

#### 問題：第三方資源載入失敗
```javascript
// 錯誤：Refused to load 'https://cdn.example.com/script.js'
// 解決：確保資源有正確的 CORS 頭

// 測試 CORS
fetch('https://cdn.example.com/script.js', {
  mode: 'cors'
}).then(r => {
  console.log('CORS OK:', r.headers.get('Access-Control-Allow-Origin'));
}).catch(e => {
  console.error('CORS Failed:', e);
});
```

### 13.7 建議部署檢查清單

- [ ] 伺服器設定 COOP: same-origin
- [ ] 伺服器設定 COEP: require-corp
- [ ] 所有 `<script>` 標籤加上 `crossorigin="anonymous"`
- [ ] 所有 `<img>` 跨域圖片加上 `crossorigin="anonymous"`
- [ ] 所有 fetch 請求設定正確的 mode 和 credentials
- [ ] Worker 載入使用 `import.meta.url`
- [ ] 測試 `self.crossOriginIsolated === true`
- [ ] 實作降級策略處理非隔離環境
- [ ] 在不同瀏覽器測試（Chrome、Firefox、Safari）
- [ ] 記錄效能指標對比（有/無 SharedArrayBuffer）

## 14. CSP (Content Security Policy) 配置指南

### 14.1 為什麼需要 CSP 配置

許多企業網站和安全敏感的應用會使用 CSP 來防止 XSS 攻擊。WebASRCore 需要特定的 CSP 設定才能正常運作。

### 14.2 最小必要 CSP 策略

```http
Content-Security-Policy: 
  default-src 'self';
  script-src 'self' 'wasm-unsafe-eval' blob:;
  worker-src 'self' blob:;
  connect-src 'self' https://cdn.jsdelivr.net https://unpkg.com https://huggingface.co;
  media-src 'self' blob:;
  style-src 'self' 'unsafe-inline';
```

### 14.3 各指令說明

| 指令 | 值 | 說明 |
|------|-----|------|
| `script-src` | `'wasm-unsafe-eval'` | WebAssembly 執行需要 |
| | `blob:` | Worker 動態創建需要 |
| `worker-src` | `'self' blob:` | Web Worker 和 AudioWorklet |
| `connect-src` | CDN URLs | 模型下載來源 |
| `media-src` | `blob:` | 音訊處理需要 |

### 14.4 不同環境的 CSP 配置

#### 開發環境（寬鬆）
```http
Content-Security-Policy: 
  script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob:;
  worker-src 'self' blob:;
  connect-src *;
```

#### 生產環境（嚴格）
```http
Content-Security-Policy: 
  default-src 'none';
  script-src 'self' 'wasm-unsafe-eval' blob: 'sha256-[hash]';
  worker-src 'self' blob:;
  connect-src 'self' https://your-cdn.com;
  media-src 'self' blob:;
  style-src 'self';
  base-uri 'self';
  form-action 'none';
  frame-ancestors 'none';
```

### 14.5 CSP 相容性測試

```javascript
// 測試 CSP 相容性
class CSPTester {
  static async testCompatibility() {
    const tests = {
      webAssembly: await this.testWebAssembly(),
      worker: await this.testWorker(),
      blob: await this.testBlob(),
      audioWorklet: await this.testAudioWorklet()
    };
    
    return tests;
  }
  
  static async testWebAssembly() {
    try {
      const module = new WebAssembly.Module(
        new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00])
      );
      return { success: true };
    } catch (e) {
      return { success: false, error: 'CSP blocks wasm-unsafe-eval' };
    }
  }
  
  static async testWorker() {
    try {
      const blob = new Blob(['self.postMessage("test")'], 
        { type: 'application/javascript' });
      const worker = new Worker(URL.createObjectURL(blob));
      worker.terminate();
      return { success: true };
    } catch (e) {
      return { success: false, error: 'CSP blocks blob: workers' };
    }
  }
}
```

## 15. 瀏覽器權限與兼容性

### 15.1 權限手勢要求

麥克風和某些 API 需要使用者手勢才能啟動：

```typescript
class PermissionManager {
  private audioContext: AudioContext | null = null;
  
  async requestMicrophonePermission(fromUserGesture: boolean = false) {
    // iOS Safari 必須有使用者手勢
    if (this.isIOS() && !fromUserGesture) {
      throw new Error(
        'iOS requires user gesture for microphone access. ' +
        'Please call this method from a button click handler.'
      );
    }
    
    try {
      // 請求麥克風權限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      });
      
      // iOS Safari 需要 resume AudioContext
      if (this.audioContext?.state === 'suspended') {
        await this.audioContext.resume();
      }
      
      return stream;
    } catch (error) {
      if (error.name === 'NotAllowedError') {
        throw new Error('Microphone permission denied');
      }
      throw error;
    }
  }
  
  private isIOS(): boolean {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && 
           !window.MSStream;
  }
}
```

### 15.2 瀏覽器兼容性矩陣

| Feature | Chrome | Firefox | Safari | Edge | 備註 |
|---------|--------|---------|--------|------|------|
| AudioWorklet | ✅ 66+ | ✅ 76+ | ✅ 14.1+ | ✅ 79+ | |
| Web Speech API | ✅ 25+ | ❌ | ⚠️ 14.1+ | ✅ 79+ | Safari 需要啟用實驗功能 |
| WebGPU | ✅ 113+ | ❌ | ❌ | ✅ 113+ | 需要 flag |
| SharedArrayBuffer | ✅* | ✅* | ✅* | ✅* | 需要 COOP/COEP |
| SIMD | ✅ 91+ | ✅ 89+ | ❌ | ✅ 91+ | |
| getUserMedia | ✅ 53+ | ✅ 36+ | ✅ 11+ | ✅ 12+ | HTTPS required |
| IndexedDB | ✅ 24+ | ✅ 16+ | ✅ 10+ | ✅ 79+ | Safari 有配額限制 |

* 需要正確的 COOP/COEP headers

### 15.3 自動降級策略

```typescript
class CompatibilityManager {
  static getOptimalConfiguration() {
    const features = {
      audioWorklet: 'audioWorklet' in AudioContext.prototype,
      webSpeech: 'webkitSpeechRecognition' in window || 
                 'SpeechRecognition' in window,
      webGPU: 'gpu' in navigator,
      sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
      simd: WebAssembly.validate(new Uint8Array([
        0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b
      ]))
    };
    
    // 根據能力選擇配置
    if (!features.audioWorklet) {
      console.warn('AudioWorklet not supported, using ScriptProcessor');
      return { audioProcessor: 'scriptProcessor' };
    }
    
    if (!features.webSpeech) {
      console.info('Web Speech not available, using Whisper only');
      return { provider: 'whisper' };
    }
    
    return { optimal: true, features };
  }
}
```

## 16. IndexedDB 儲存策略與 Fallback

### 16.1 IndexedDB 配額問題

iOS Safari 和私密瀏覽模式的限制：

```typescript
class StorageManager {
  private storageType: 'indexeddb' | 'memory' | 'sessionStorage' = 'indexeddb';
  
  async initialize() {
    // 檢測 IndexedDB 可用性
    const available = await this.checkIndexedDBAvailability();
    
    if (!available.success) {
      console.warn(`IndexedDB unavailable: ${available.reason}`);
      this.storageType = available.fallback;
    }
  }
  
  private async checkIndexedDBAvailability() {
    // 檢查私密瀏覽模式
    if (this.isPrivateMode()) {
      return {
        success: false,
        reason: 'Private browsing mode detected',
        fallback: 'sessionStorage' as const
      };
    }
    
    try {
      // 測試開啟 IndexedDB
      const testDB = await this.openTestDB();
      
      // 檢查配額
      if ('storage' in navigator && 'estimate' in navigator.storage) {
        const estimate = await navigator.storage.estimate();
        const quota = estimate.quota || 0;
        const usage = estimate.usage || 0;
        
        // iOS Safari 通常給很小的配額
        if (quota < 50 * 1024 * 1024) { // < 50MB
          console.warn(`Low storage quota: ${quota / 1024 / 1024}MB`);
          return {
            success: true,
            warning: 'Low storage quota',
            quota,
            usage
          };
        }
      }
      
      await testDB.close();
      return { success: true };
      
    } catch (error) {
      if (error.name === 'InvalidStateError') {
        // iOS Safari 私密模式
        return {
          success: false,
          reason: 'IndexedDB blocked (iOS private mode)',
          fallback: 'memory' as const
        };
      }
      
      return {
        success: false,
        reason: error.message,
        fallback: 'memory' as const
      };
    }
  }
  
  private isPrivateMode(): boolean {
    // Safari 私密模式檢測
    try {
      window.openDatabase(null, null, null, null);
      return false;
    } catch (_) {
      return true;
    }
  }
  
  async store(key: string, data: ArrayBuffer) {
    switch (this.storageType) {
      case 'indexeddb':
        return this.storeInIndexedDB(key, data);
      case 'sessionStorage':
        return this.storeInSessionStorage(key, data);
      case 'memory':
        return this.storeInMemory(key, data);
    }
  }
}

// Fallback: 記憶體儲存
class MemoryStorage {
  private cache = new Map<string, ArrayBuffer>();
  private maxSize = 100 * 1024 * 1024; // 100MB
  private currentSize = 0;
  
  store(key: string, data: ArrayBuffer) {
    // LRU 淘汰策略
    if (this.currentSize + data.byteLength > this.maxSize) {
      this.evict(data.byteLength);
    }
    
    this.cache.set(key, data);
    this.currentSize += data.byteLength;
  }
  
  private evict(requiredSize: number) {
    const entries = Array.from(this.cache.entries());
    let freed = 0;
    
    for (const [key, value] of entries) {
      if (freed >= requiredSize) break;
      freed += value.byteLength;
      this.cache.delete(key);
    }
    
    this.currentSize -= freed;
  }
}
```

## 17. 診斷 API 與遙測

### 17.1 診斷 API 設計

```typescript
interface DiagnosticsReport {
  // 環境檢測
  environment: {
    userAgent: string;
    platform: string;
    language: string;
    timezone: string;
  };
  
  // 安全性上下文
  security: {
    crossOriginIsolated: boolean;
    isSecureContext: boolean;
    cspViolations: string[];
  };
  
  // 能力檢測
  capabilities: {
    sharedArrayBuffer: boolean;
    webAssembly: boolean;
    simd: boolean;
    threads: boolean;
    webGPU: GPUInfo | null;
    audioWorklet: boolean;
    webSpeech: boolean;
  };
  
  // 音訊系統
  audio: {
    context: {
      state: AudioContextState;
      sampleRate: number;
      outputLatency: number;
      baseLatency: number;
    };
    microphone: MediaTrackSettings | null;
    constraints: MediaTrackConstraints | null;
  };
  
  // 儲存狀態
  storage: {
    type: 'indexeddb' | 'memory' | 'sessionStorage';
    quota: number;
    usage: number;
    persistent: boolean;
  };
  
  // 效能指標
  performance: {
    memory: MemoryInfo | null;
    connection: NetworkInformation | null;
  };
}

export class DiagnosticsService {
  async generateReport(): Promise<DiagnosticsReport> {
    const report: DiagnosticsReport = {
      environment: this.getEnvironmentInfo(),
      security: await this.getSecurityInfo(),
      capabilities: await this.getCapabilities(),
      audio: await this.getAudioInfo(),
      storage: await this.getStorageInfo(),
      performance: this.getPerformanceInfo()
    };
    
    return report;
  }
  
  // 即時監控
  startMonitoring(callback: (metrics: PerformanceMetrics) => void) {
    const observer = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const metrics = this.processEntries(entries);
      callback(metrics);
    });
    
    observer.observe({ entryTypes: ['measure', 'resource'] });
    
    return () => observer.disconnect();
  }
}
```

## 18. 效能預期與基準測試

### 18.1 效能預期表 (RTF - Real-Time Factor)

RTF < 1.0 表示比實時快，RTF > 1.0 表示比實時慢

| 模型 | 硬體 | 執行模式 | RTF | 記憶體 | 首次載入 |
|------|------|----------|-----|--------|----------|
| **Whisper-tiny** | | | | | |
| | M1 MacBook | WebGPU | 0.3x | 150MB | 3s |
| | M1 MacBook | WASM+SIMD+Threads | 0.8x | 120MB | 2s |
| | i7-10700K | WASM+SIMD | 1.2x | 120MB | 2.5s |
| | i5-8250U | WASM | 2.5x | 120MB | 3s |
| | 手機 (驍龍 888) | WASM | 3.5x | 120MB | 5s |
| **Silero VAD** | | | | | |
| | 任何硬體 | WASM | 0.05x | 15MB | 0.5s |
| **OpenWakeWord** | | | | | |
| | 任何硬體 | WASM | 0.1x | 25MB | 1s |

### 18.2 基準測試工具

```typescript
class BenchmarkRunner {
  async runBenchmark(audioFile: ArrayBuffer) {
    const results = {
      whisper: await this.benchmarkWhisper(audioFile),
      vad: await this.benchmarkVAD(audioFile),
      wakeword: await this.benchmarkWakeWord(audioFile)
    };
    
    return this.generateReport(results);
  }
  
  private async benchmarkWhisper(audio: ArrayBuffer) {
    const durations: number[] = [];
    const memoryUsage: number[] = [];
    
    // 預熱
    await this.runWhisperOnce(audio);
    
    // 執行 5 次測試
    for (let i = 0; i < 5; i++) {
      if (performance.memory) {
        memoryUsage.push(performance.memory.usedJSHeapSize);
      }
      
      const start = performance.now();
      await this.runWhisperOnce(audio);
      const duration = performance.now() - start;
      
      durations.push(duration);
    }
    
    // 計算音訊長度
    const audioDuration = audio.byteLength / (16000 * 2); // 16kHz, 16-bit
    
    return {
      rtf: this.mean(durations) / (audioDuration * 1000),
      latency: this.mean(durations),
      memory: this.mean(memoryUsage) / 1024 / 1024, // MB
      p95: this.percentile(durations, 95)
    };
  }
}
```

## 19. 模型載入與 CDN 策略

### 19.1 避免 Hugging Face 直接載入

```typescript
// ❌ 錯誤：直接使用 HF URL
const BAD_EXAMPLE = {
  modelUrl: 'https://huggingface.co/Xenova/whisper-tiny/resolve/main/model.onnx'
  // 問題：
  // 1. CORS 可能失敗
  // 2. 檔名可能變更
  // 3. Redirect 造成效能問題
};

// ✅ 正確：使用模型清單
interface ModelManifest {
  version: string;
  models: {
    [key: string]: {
      url: string;
      sha256: string;
      size: number;
      etag?: string;
      alternatives?: string[]; // fallback URLs
    };
  };
}

class ModelRegistry {
  private static MANIFEST_URL = 'https://your-cdn.com/models/manifest.json';
  private manifest: ModelManifest | null = null;
  
  async loadModel(modelName: string): Promise<ArrayBuffer> {
    if (!this.manifest) {
      this.manifest = await this.fetchManifest();
    }
    
    const modelInfo = this.manifest.models[modelName];
    if (!modelInfo) {
      throw new Error(`Model ${modelName} not found in manifest`);
    }
    
    // 嘗試主要 URL
    try {
      const data = await this.fetchWithVerification(
        modelInfo.url,
        modelInfo.sha256
      );
      return data;
    } catch (error) {
      // 嘗試備用 URL
      if (modelInfo.alternatives) {
        for (const altUrl of modelInfo.alternatives) {
          try {
            return await this.fetchWithVerification(
              altUrl,
              modelInfo.sha256
            );
          } catch {}
        }
      }
      throw error;
    }
  }
  
  private async fetchWithVerification(
    url: string,
    expectedHash: string
  ): Promise<ArrayBuffer> {
    const response = await fetch(url, {
      mode: 'cors',
      credentials: 'omit',
      headers: {
        'Accept': 'application/octet-stream'
      }
    });
    
    if (!response.ok) {
      throw new Error(`Failed to fetch model: ${response.status}`);
    }
    
    const data = await response.arrayBuffer();
    
    // 驗證 SHA256
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashHex = Array.from(new Uint8Array(hashBuffer))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
    
    if (hashHex !== expectedHash) {
      throw new Error('Model integrity check failed');
    }
    
    return data;
  }
}
```

### 19.2 CDN 配置建議

```javascript
// CDN 應該支援的功能
const CDN_REQUIREMENTS = {
  // 1. 支援 Range 請求（分段下載）
  headers: {
    'Accept-Ranges': 'bytes',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Cache-Control': 'public, max-age=31536000, immutable'
  },
  
  // 2. 提供 SRI (Subresource Integrity)
  integrity: 'sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/uxy9rx7HNQlGYl1kPzQho1wx4JwY8wC',
  
  // 3. 支援 Brotli/Gzip 壓縮
  compression: ['br', 'gzip'],
  
  // 4. 提供版本化 URL
  versioning: 'https://cdn.example.com/models/v1.0.0/whisper-tiny.onnx'
};
```

## 20. 安全性與授權聲明

### 20.1 模型授權檢查清單

| 模型/庫 | 授權 | 商用 | 再散布 | 歸屬要求 |
|---------|------|------|---------|----------|
| Silero VAD | MIT | ✅ | ✅ | MIT License 聲明 |
| OpenWakeWord | Apache 2.0 | ✅ | ✅ | Apache License 聲明 |
| Whisper | MIT | ✅ | ✅ | OpenAI 歸屬 |
| RNNoise | BSD | ✅ | ✅ | BSD License 聲明 |
| ONNX Runtime Web | MIT | ✅ | ✅ | Microsoft 歸屬 |
| Transformers.js | Apache 2.0 | ✅ | ✅ | Xenova 歸屬 |

### 20.2 隱私聲明範本

```typescript
class PrivacyNotice {
  static getNotice(provider: string): string {
    switch (provider) {
      case 'whisper':
        return `
          🔒 本地處理
          您的音訊資料完全在您的裝置上處理，不會傳送到任何伺服器。
          處理速度取決於您的裝置效能。
        `;
        
      case 'webspeech':
        return `
          ⚠️ 雲端處理
          使用 Web Speech API 時，您的音訊將被傳送到：
          - Chrome/Edge: Google 語音識別伺服器
          - Safari: Apple 語音識別伺服器
          
          請確認您同意將音訊資料傳送到這些第三方服務。
          
          [隱私政策連結] [切換到本地處理]
        `;
        
      default:
        return '';
    }
  }
}
```

## 21. Silero VAD 參數驗證

根據實測和官方範例，正確的參數應該是：

```typescript
interface VADConfig {
  // Silero VAD 官方建議參數
  frameSamples: 480,      // 30ms @ 16kHz (不是 512)
  positiveSpeechThreshold: 0.5,
  negativeSpeechThreshold: 0.35,
  redemptionFrames: 8,    // 240ms 的 redemption time
  preSpeechPadFrames: 8,  // 240ms 的 pre-speech padding
  minSpeechFrames: 16,    // 最少 480ms 的語音才觸發
}

// 實際實作
class SileroVAD {
  private readonly FRAME_SIZE = 480;  // 30ms @ 16kHz
  private readonly SAMPLE_RATE = 16000;
  
  processFrame(audioFrame: Float32Array) {
    if (audioFrame.length !== this.FRAME_SIZE) {
      throw new Error(
        `VAD frame size must be ${this.FRAME_SIZE} samples, ` +
        `got ${audioFrame.length}`
      );
    }
    
    // 處理邏輯...
  }
}
```

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