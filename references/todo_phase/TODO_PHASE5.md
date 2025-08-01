# ASR_Hub 第五階段工作清單

## 📋 階段目標
基於前四階段的成果，實作完整的 Session-Based 架構，整合 VAD（語音活動偵測），建立智慧音訊流分配策略，實現每個連線獨立的狀態管理和資源優化。本階段將完成從待機監聽到活躍聆聽的完整狀態轉換流程。

## 🏗️ 架構說明

### Session-Based 架構 vs Provider Pool
本系統採用混合架構，結合 Session 隔離性和資源池化的優點：

#### 1. **Session-Based 架構（本階段重點）**
每個連線/用戶擁有完全獨立的 Session，包含：
- **獨立元件**：FSM 狀態機、喚醒詞偵測器、VAD 處理器、音訊緩衝區
- **狀態隔離**：每個 Session 的狀態變化不影響其他 Session
- **配置獨立**：可為不同 Session 設定不同參數

#### 2. **Provider Pool（已實作）**
資源密集型元件透過池化共享：
- **共享資源**：ASR Provider（如 Whisper）透過 ProviderPool 管理
- **動態分配**：Session 需要時從池中借用，用完歸還
- **資源優化**：避免每個 Session 都創建昂貴的 ASR 實例

#### 3. **架構示意圖**
```
┌─────────────────────────────────────────────┐
│                Session A                     │
│  ┌─────────────┐  ┌──────────────┐         │
│  │ FSM (獨立)  │  │ VAD (獨立)   │         │
│  └─────────────┘  └──────────────┘         │
│  ┌─────────────┐  ┌──────────────┐         │
│  │WakeWord(獨立)│ │ASR Provider │──────┐  │
│  └─────────────┘  └──────────────┘      │  │
└──────────────────────────────────────────┼──┘
                                           │
                    ┌──────────────────────▼───┐
                    │    Provider Pool         │
                    │  ┌────┐ ┌────┐ ┌────┐  │
                    │  │ASR1│ │ASR2│ │ASR3│  │ ← 共享
                    │  └────┘ └────┘ └────┘  │
                    └──────────────────────▲───┘
                                           │
┌──────────────────────────────────────────┼──┐
│                Session B                  │  │
│  ┌─────────────┐  ┌──────────────┐      │  │
│  │ FSM (獨立)  │  │ VAD (獨立)   │      │  │
│  └─────────────┘  └──────────────┘      │  │
│  ┌─────────────┐  ┌──────────────┐      │  │
│  │WakeWord(獨立)│ │ASR Provider │──────┘  │
│  └─────────────┘  └──────────────┘         │
└─────────────────────────────────────────────┘
```

### 資源分配策略
- **輕量級元件**（每 Session 獨立）：
  - FSM：狀態管理，記憶體占用小
  - WakeWord：ONNX 模型，約 10MB
  - VAD：Silero 模型，約 1.5MB
  - AudioBuffer：動態大小，通常 < 1MB
  
- **重量級元件**（池化共享）：
  - ASR Provider：Whisper 模型可達數 GB
  - 透過 ProviderPool 管理，支援並發使用
  - 動態擴展，根據負載自動調整池大小

## ✅ 工作項目清單

### 1. Session-Based 架構核心實作

#### 1.1 增強 Session 模型（src/models/session.py）
- [ ] 1.1.1 擴展 Session 類別
  - 新增 FSM 實例屬性（每個 Session 獨立的狀態機）
  - 新增 wakeword_operator 屬性（喚醒詞處理器）
  - 新增 vad_operator 屬性（VAD 處理器）
  - 新增 asr_provider 屬性（從 ProviderPool 動態獲取）
  - 新增 audio_buffer 屬性（Session 專屬緩衝區）
  - 新增 audio_dispatcher 屬性（音訊分發器）
- [ ] 1.1.2 實作 Session 初始化方法
  ```python
  async def initialize_processors(self, config: dict):
      """初始化 Session 的所有處理器"""
      # 初始化獨立元件
      self.fsm = StateMachine(initial_state=State.IDLE)
      self.wakeword_operator = OpenWakeWordOperator(config)
      self.vad_operator = SileroVADOperator(config)
      self.audio_buffer = AudioBuffer()
      self.audio_dispatcher = AudioDispatcher()
      
      # ASR Provider 將在需要時從 Pool 獲取
      self.asr_provider = None  # 延遲載入
  ```
- [ ] 1.1.3 實作處理器生命週期管理
  ```python
  async def cleanup(self):
      """釋放所有資源"""
      # 歸還 ASR Provider 到 Pool
      if self.asr_provider:
          await provider_pool.release(self.asr_provider)
      # 清理獨立元件
      await self.wakeword_operator.cleanup()
      await self.vad_operator.cleanup()
      
  async def acquire_asr_provider(self):
      """從 Pool 獲取 ASR Provider"""
      async with provider_pool.acquire() as provider:
          self.asr_provider = provider
          return provider
  ```

#### 1.2 重構 SessionManager（src/core/session_manager.py）
- [ ] 1.2.1 實作 Session 級別的音訊處理
  ```python
  async def process_audio(self, session_id: str, audio_data: bytes):
      """根據 Session 的 FSM 狀態決定音訊處理方式"""
      # IDLE: 只處理喚醒詞
      # LISTENING: 並行處理 VAD 和 ASR
      # BUSY: 緩衝音訊但不處理
  ```
- [ ] 1.2.2 實作 Session 隔離機制
  - 每個 Session 完全獨立運行
  - 狀態變化不影響其他 Session
  - 資源使用隔離
- [ ] 1.2.3 實作並發 Session 管理
  - 支援大量並發 Session（目標 1000+）
  - Session 池管理和回收
  - 過期 Session 自動清理

### 2. VAD (Voice Activity Detection) 整合

#### 2.1 Silero VAD Operator 實作（src/pipeline/operators/vad/）
- [ ] 2.1.1 建立 SileroVADOperator 類別（繼承 OperatorBase）
  - 整合 Silero VAD 模型
  - 支援 16kHz 音訊輸入
  - 實作即時語音偵測
  - 可配置的靈敏度設定
- [ ] 2.1.2 實作靜音超時檢測
  ```python
  class VADOperator:
      def __init__(self):
          self.silence_start = None
          self.silence_threshold = 1.5  # 可配置
      
      async def process(self, audio_chunk):
          # 偵測語音活動
          # 計算連續靜音時間
          # 返回 speech_detected 和 silence_duration
  ```
- [ ] 2.1.3 實作對話結束判定邏輯
  - 連續靜音時長檢測（非固定超時）
  - 用戶說話重置計時器
  - 支援動態調整閾值
  - 避免過早中斷

#### 2.2 VAD 與系統整合
- [ ] 2.2.1 實作 VAD 狀態管理
  - 從喚醒後立即啟動 VAD
  - 持續監測語音活動
  - 觸發對話結束事件
- [ ] 2.2.2 實作 VAD 效能優化
  - 使用 ONNX Runtime 加速
  - 批次處理音訊幀
  - 減少 CPU 使用率
  - 監控處理延遲

### 3. 智慧音訊流分配策略

#### 3.1 音訊分發器實作（src/stream/audio_dispatcher.py）
- [ ] 3.1.1 建立 AudioDispatcher 類別
  ```python
  class AudioDispatcher:
      def __init__(self):
          self.active_processors = set()
      
      async def dispatch(self, audio_chunk):
          # 並行發送到所有活躍的處理器
          # 根據 FSM 狀態決定處理器集合
  ```
- [ ] 3.1.2 實作狀態相關的分發邏輯
  - IDLE 狀態：音訊 → 喚醒詞偵測器
  - LISTENING 狀態：音訊 → VAD + ASR（並行）
  - BUSY 狀態：音訊 → 緩衝區（暫存）
- [ ] 3.1.3 實作背壓控制
  - 監控處理器處理速度
  - 動態調整分發策略
  - 防止記憶體溢出

#### 3.2 並行處理架構實作
- [ ] 3.2.1 實作並行音訊處理
  ```python
  async def process_audio_in_listening(audio_chunk):
      # 使用 asyncio.gather 並行處理
      vad_task = asyncio.create_task(vad_operator.process(audio_chunk))
      asr_task = asyncio.create_task(asr_provider.process(audio_chunk))
      
      vad_result, asr_result = await asyncio.gather(vad_task, asr_task)
  ```
- [ ] 3.2.2 實作結果協調機制
  - VAD 結果用於流程控制
  - ASR 結果用於轉譯輸出
  - 結果同步和聚合
  - 錯誤處理和恢復

### 4. 狀態轉換和資源管理優化

#### 4.1 喚醒觸發流程實作（src/core/event_handlers.py）
- [ ] 4.1.1 建立統一的事件處理器
  ```python
  class SystemEventHandler:
      async def on_wake_detected(self, session: Session):
          # 1. FSM 轉換：IDLE → LISTENING
          # 2. 暫停喚醒詞偵測器
          # 3. 啟動 VAD 和 ASR
      
      async def on_silence_timeout(self, session: Session):
          # 1. FSM 轉換：LISTENING → IDLE
          # 2. 停止 VAD 和 ASR
          # 3. 恢復喚醒詞偵測
  ```
- [ ] 4.1.2 實作資源優化策略
  - 動態啟用/停用處理器
  - 最小化 IDLE 狀態資源使用
  - 快速狀態切換（< 100ms）
- [ ] 4.1.3 實作狀態轉換保護
  - 防止並發狀態變更
  - 狀態轉換原子性
  - 異常狀態恢復

#### 4.2 ASR Provider 適配優化
- [ ] 4.2.1 實作 Streaming ASR 適配
  - 喚醒後立即開始串流
  - 持續接收部分結果
  - VAD 觸發結束信號
  - 優雅的串流終止
- [ ] 4.2.2 實作 Non-Streaming ASR 適配
  - 喚醒後開始緩衝音訊
  - 基於 VAD 決定錄音結束
  - 批次發送完整音訊
  - 處理超長音訊情況

### 5. 進階 Session 管理功能

#### 5.1 資源池化整合與擴展
- [ ] 5.1.1 整合現有 ProviderPool（src/providers/provider_pool.py）
  - 確認 ProviderPool 支援 Session-Based 使用模式
  - 優化 acquire/release 機制以支援高頻切換
  - 實作 Session 專屬的 Provider 預留機制
- [ ] 5.1.2 擴展池化支援其他處理器
  ```python
  # 為 VAD 等其他處理器建立通用池化機制
  class ProcessorPool(Generic[T]):
      def __init__(self, processor_class: Type[T], 
                   min_size=2, max_size=10):
          # 基於 ProviderPool 的設計模式
          # 支援任何類型的處理器池化
  ```
- [ ] 5.1.3 實作智慧池化策略
  - 根據 Session 優先級分配資源
  - 預測性擴容（基於歷史使用模式）
  - 差異化的池配置（如 VAD 池較大，ASR 池較小）
  - Session 親和性（優先分配上次使用的實例）

#### 5.2 Session 監控和診斷
- [ ] 5.2.1 實作 Session 指標收集
  - 狀態轉換統計
  - 資源使用監控
  - 處理延遲追蹤
  - 錯誤率統計
- [ ] 5.2.2 建立診斷工具
  - Session 狀態快照
  - 處理器健康檢查
  - 音訊流追蹤
  - 效能瓶頸分析

### 6. API 層 Session 整合

#### 6.1 更新所有 API 實作
- [ ] 6.1.1 HTTP SSE Session 整合
  - 每個 SSE 連線創建獨立 Session
  - 綁定音訊處理到特定 Session
  - 支援 Session 狀態查詢
- [ ] 6.1.2 WebSocket Session 整合
  - 連線時創建 Session
  - 支援 Session 遷移
  - 實作 Session 恢復機制
- [ ] 6.1.3 Socket.io Session 整合
  - 房間對應 Session
  - 支援多客戶端共享 Session
  - 實作 Session 廣播

#### 6.2 跨協定 Session 同步
- [ ] 6.2.1 實作 Session 共享機制
  - 統一的 Session ID 管理
  - 跨協定狀態同步
  - Session 鎖定和解鎖
- [ ] 6.2.2 實作 Session 遷移
  - 支援協定切換（如 HTTP → WebSocket）
  - 保持狀態連續性
  - 無縫音訊處理

### 7. 配置系統擴展

#### 7.1 Session 相關配置
- [ ] 7.1.1 更新 YAML 配置
  ```yaml
  session:
    max_concurrent: 1000
    idle_timeout: 300  # 5 分鐘
    
  audio_routing:
    idle_processors: ["wakeword"]
    listening_processors: ["vad", "asr"]
    
  vad:
    model: "silero"
    silence_threshold: 1.5
    speech_confidence: 0.5
    
  resource_optimization:
    pause_wakeword_on_listening: true
    processor_pooling:
      enabled: true
      asr_pool_size: 10
      vad_pool_size: 20
  ```
- [ ] 7.1.2 重新生成配置類別
  - 執行 yaml2py 更新
  - 驗證新配置項
  - 支援動態配置更新

### 8. 測試和驗證工具

#### 8.1 Session 測試工具
- [ ] 8.1.1 建立多 Session 測試腳本
  - 並發 Session 創建測試
  - 狀態轉換壓力測試
  - 資源使用監控
  - 長時間穩定性測試
- [ ] 8.1.2 建立 VAD 測試工具
  - 靜音檢測準確性測試
  - 不同環境噪音測試
  - 延遲測量工具
  - 參數調優指南

#### 8.2 整合測試場景
- [ ] 8.2.1 端到端測試場景
  - 喚醒 → 說話 → 靜音 → 結束 完整流程
  - 多用戶並發對話測試
  - 長對話處理測試
  - 異常情況恢復測試
- [ ] 8.2.2 效能基準測試
  - 單 Session 處理延遲
  - 最大並發 Session 數
  - 資源使用效率
  - 狀態轉換速度

## 🔍 驗收標準
1. ✅ 完整的 Session-Based 架構運行正常
2. ✅ 每個 Session 有獨立的 FSM、處理器和資源
3. ✅ VAD 能準確檢測語音活動和靜音
4. ✅ 音訊流根據狀態正確分配到不同處理器
5. ✅ IDLE 狀態只運行喚醒詞，LISTENING 狀態運行 VAD+ASR
6. ✅ 支援 1000+ 並發 Session
7. ✅ 狀態轉換延遲 < 100ms
8. ✅ 資源使用優化，IDLE 狀態 CPU < 5%
9. ✅ Provider Pool 與 Session 整合正常運作
10. ✅ ASR Provider 能正確從池中獲取和釋放

## 📝 注意事項
1. 確保 Session 完全隔離，避免相互影響
2. VAD 和 ASR 必須並行處理以降低延遲
3. 注意資源管理，及時釋放未使用的處理器
4. 使用 pretty-loguru 記錄所有關鍵事件
5. 保持程式碼模組化，便於未來擴展
6. 考慮異常情況的處理和恢復
7. 為大規模部署預留優化空間
8. **重要**：ASR Provider 使用現有的 ProviderPool，不要重複實作
9. **重要**：輕量級元件（VAD、WakeWord）每個 Session 獨立，避免共享帶來的狀態污染
10. **重要**：Session 清理時必須正確歸還所有從 Pool 借用的資源

## 🚀 實作優先順序建議
1. **第一優先級**：增強 Session 模型和 SessionManager
2. **第二優先級**：實作 VAD Operator 和整合
3. **第三優先級**：音訊流分配策略和並行處理
4. **第四優先級**：狀態轉換和資源管理優化
5. **第五優先級**：資源池化和進階功能
6. **第六優先級**：測試工具和效能優化

## 🔄 與現有系統的整合點

### 1. Provider Pool 整合
- **位置**：`src/providers/provider_pool.py`
- **使用方式**：
  ```python
  # Session 中獲取 ASR Provider
  async with self.provider_manager.get_pool("whisper").acquire() as provider:
      result = await provider.transcribe(audio_data)
  ```
- **注意**：不需要修改現有 ProviderPool，只需正確使用

### 2. Session Manager 擴展
- **現有功能**：基本的 Session CRUD 操作
- **需要擴展**：
  - 音訊處理路由
  - 處理器管理
  - 狀態同步機制

### 3. FSM 整合
- **現有 FSM**：基礎狀態機框架
- **需要增強**：
  - 每個 Session 獨立的 FSM 實例
  - 狀態轉換事件系統
  - 與音訊處理器的聯動

---
建立時間：2025-07-30
最後更新：2025-07-30
負責人：ASR Hub Team