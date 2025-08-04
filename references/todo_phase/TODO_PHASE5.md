# ASR_Hub 第五階段工作清單

## 📋 階段目標
在前四階段建立的完整基礎架構上，實作 VAD（Voice Activity Detection）和錄音（Recording）兩個核心 Operator，並建立完整的測試框架。這兩個 Operator 將與現有的喚醒詞偵測功能協同工作，實現更智慧的音訊處理流程。

## 🎯 預期成果
1. **VAD Operator**：使用 Silero VAD 模型，能準確檢測語音活動
2. **Recording Operator**：支援音訊錄製、緩衝管理、分段儲存，**VAD 控制的自動停止機制**
3. **整合測試工具**：類似 test_wakeword_integration.py 的完整測試框架
4. **效能基準**：確保新增 Operator 不影響系統整體效能
5. **智慧錄音流程**：喚醒詞觸發 → 開始錄音 → VAD 監控 → 靜音倒數 → 自動停止

## ✅ 工作項目清單

### 1. VAD Operator 實作

#### 1.1 Silero VAD Operator 開發（src/pipeline/operators/vad/silero_vad.py）
- [ ] 1.1.1 建立 SileroVADOperator 類別（繼承 OperatorBase）
  ```python
  class SileroVADOperator(OperatorBase):
      """使用 Silero VAD 模型進行語音活動檢測"""
      def __init__(self, config: dict = None):
          super().__init__(config)
          self.model = None
          self.sample_rate = 16000  # Silero VAD 需要 16kHz
          self.threshold = config.get('threshold', 0.5)
          self.min_silence_duration = config.get('min_silence_duration', 0.5)
          self.min_speech_duration = config.get('min_speech_duration', 0.25)
  ```

- [ ] 1.1.2 實作模型載入和管理
  - 支援 ONNX Runtime 推論
  - 模型自動下載機制（類似 OpenWakeWord）
  - 模型快取管理
  - 多執行緒安全設計

- [ ] 1.1.3 實作核心 VAD 邏輯
  ```python
  async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
      """處理音訊並返回 VAD 結果"""
      # 1. 音訊預處理（確保 16kHz）
      # 2. 執行 VAD 推論
      # 3. 狀態管理（speech/silence 狀態追蹤）
      # 4. 事件觸發（speech_start, speech_end）
      # 5. 元數據注入（VAD 結果）
      return audio_data  # 透傳音訊，附加 VAD 資訊
  ```

- [ ] 1.1.4 實作進階功能
  - 滑動窗口處理（處理跨幀語音）
  - 自適應閾值調整
  - 多語言支援（如果模型支援）
  - GPU 加速支援（可選）

#### 1.2 VAD 基礎設施
- [ ] 1.2.1 建立 VAD 事件系統
  ```python
  class VADEvent:
      SPEECH_START = "speech_start"
      SPEECH_END = "speech_end"
      SILENCE_TIMEOUT = "silence_timeout"
  ```

- [ ] 1.2.2 實作 VAD 統計收集
  - 語音/靜音時長統計
  - 誤判率追蹤
  - 處理延遲監控

### 2. Recording Operator 實作

#### 2.1 基礎錄音功能（src/pipeline/operators/recording/recording_operator.py）
- [ ] 2.1.1 建立 RecordingOperator 類別
  ```python
  class RecordingOperator(OperatorBase):
      """音訊錄製和緩衝管理"""
      def __init__(self, config: dict = None):
          super().__init__(config)
          self.buffer = io.BytesIO()
          self.max_duration = config.get('max_duration', 60)  # 秒
          self.format = config.get('format', 'wav')
          self.is_recording = False
          self.start_time = None
  ```

- [ ] 2.1.2 實作核心錄音邏輯
  - 音訊資料累積
  - 時長限制檢查
  - 記憶體優化（串流寫入）
  - 多格式支援（WAV, MP3, OGG）

- [ ] 2.1.3 實作錄音控制
  ```python
  async def start_recording(self, session_id: str):
      """開始錄音"""
      
  async def stop_recording(self, session_id: str) -> bytes:
      """停止錄音並返回音訊資料"""
      
  async def pause_recording(self, session_id: str):
      """暫停錄音"""
      
  async def resume_recording(self, session_id: str):
      """恢復錄音"""
  ```

#### 2.2 進階錄音功能
- [ ] 2.2.1 實作分段錄音
  - 自動分段（基於時長或檔案大小）
  - 無縫銜接
  - 段落管理和索引

- [ ] 2.2.2 實作智慧錄音
  - 與 VAD 整合（只錄製有語音的部分）
  - 前後緩衝（保留語音前後的靜音）
  - 自動停止（基於 VAD 結果）

- [ ] 2.2.3 實作 VAD 控制的錄音結束機制
  ```python
  class RecordingOperator(OperatorBase):
      def __init__(self, config: dict = None):
          # ... 其他初始化
          self.silence_countdown_duration = config.get('silence_countdown', 1.8)  # 秒
          self.countdown_timer = None
          self.is_countdown_active = False
      
      async def on_vad_result(self, vad_result: dict):
          """處理 VAD 結果並控制錄音"""
          if vad_result['speech_detected']:
              # 檢測到語音，取消倒數計時
              await self._cancel_countdown()
          else:
              # 檢測到靜音，開始或繼續倒數
              await self._start_countdown()
      
      async def _start_countdown(self):
          """開始靜音倒數計時"""
          if not self.is_countdown_active:
              self.is_countdown_active = True
              self.countdown_timer = asyncio.create_task(self._countdown_task())
      
      async def _countdown_task(self):
          """倒數計時任務"""
          try:
              await asyncio.sleep(self.silence_countdown_duration)
              # 倒數結束，停止錄音
              await self.stop_recording()
              logger.info(f"靜音 {self.silence_countdown_duration}s，自動停止錄音")
          except asyncio.CancelledError:
              # 倒數被取消（檢測到語音）
              pass
      
      async def _cancel_countdown(self):
          """取消倒數計時"""
          if self.countdown_timer and not self.countdown_timer.done():
              self.countdown_timer.cancel()
              self.is_countdown_active = False
  ```

#### 2.3 儲存和匯出
- [ ] 2.3.1 實作多種儲存選項
  - 記憶體緩衝
  - 臨時檔案
  - 永久儲存
  - 雲端上傳（可選）

- [ ] 2.3.2 實作元數據管理
  - 錄音時間戳
  - 音訊參數（採樣率、位深度等）
  - VAD 標記
  - 自定義標籤

### 3. 整合測試框架

#### 3.1 VAD 測試工具（test_vad_integration.py）
- [ ] 3.1.1 建立 VAD 整合測試器
  ```python
  class VADIntegrationTester:
      """VAD 功能整合測試"""
      def __init__(self):
          self.vad_operator = SileroVADOperator()
  ```

- [ ] 3.1.2 實作測試場景
  - 純語音測試
  - 純靜音測試
  - 語音+噪音測試
  - 多人對話測試
  - 不同語言測試

- [ ] 3.1.3 實作視覺化監控
  - 即時 VAD 狀態顯示
  - 語音/靜音時長統計圖
  - 準確率追蹤
  - 延遲監控圖表

#### 3.2 錄音測試工具（test_recording_integration.py）
- [ ] 3.2.1 建立錄音整合測試器
  - 多格式錄音測試
  - 長時間錄音穩定性測試
  - 記憶體使用監控
  - 併發錄音測試

- [ ] 3.2.2 實作效能測試
  - CPU 使用率監控
  - 記憶體占用追蹤
  - I/O 效能測試
  - 最大併發數測試

#### 3.3 組合測試工具（test_pipeline_integration.py）
- [ ] 3.3.1 建立完整 Pipeline 測試
  - 喚醒詞 → VAD → 錄音 完整流程
  - 多 Operator 串聯測試
  - 狀態轉換測試
  - 錯誤恢復測試

- [ ] 3.3.2 實作壓力測試
  - 長時間運行測試（24小時+）
  - 高併發測試
  - 資源洩漏檢測
  - 效能退化監控

#### 3.4 喚醒後自動錄音流程（test_wake_record_flow.py）
- [ ] 3.4.1 實作喚醒觸發錄音機制
  ```python
  class WakeRecordFlow:
      """喚醒詞觸發的自動錄音流程"""
      def __init__(self):
          self.wakeword_operator = OpenWakeWordOperator()
          self.vad_operator = SileroVADOperator()
          self.recording_operator = RecordingOperator({
              'silence_countdown': 1.8,  # 靜音倒數秒數
              'vad_controlled': True     # 啟用 VAD 控制
          })
          self.is_recording = False
      
      async def on_wake_detected(self, wake_event: dict):
          """喚醒詞檢測回調"""
          logger.info("🎤 檢測到喚醒詞，開始錄音...")
          
          # 1. 開始錄音
          await self.recording_operator.start_recording(
              session_id=wake_event['session_id']
          )
          self.is_recording = True
          
          # 2. 啟動 VAD 監控
          self.vad_operator.set_callback(self.on_vad_result)
          await self.vad_operator.start()
          
      async def on_vad_result(self, vad_result: dict):
          """VAD 結果回調"""
          if self.is_recording:
              # 將 VAD 結果傳遞給錄音 Operator
              await self.recording_operator.on_vad_result(vad_result)
  ```

- [ ] 3.4.2 實作倒數計時器視覺化
  ```python
  class CountdownVisualizer:
      """倒數計時器視覺化"""
      def __init__(self):
          self.countdown_value = 0
          self.max_countdown = 1.8
          
      def update_countdown(self, remaining_time: float):
          """更新倒數顯示"""
          self.countdown_value = remaining_time
          # 顯示進度條或數字倒數
          progress = remaining_time / self.max_countdown
          bar_length = int(progress * 20)
          bar = "█" * bar_length + "░" * (20 - bar_length)
          print(f"\r倒數計時: [{bar}] {remaining_time:.1f}s", end="")
  ```

- [ ] 3.4.3 整合測試場景
  - 正常對話場景：說話 → 短暫停頓 → 繼續說話（倒數重置）
  - 結束對話場景：說話 → 靜音 1.8s → 自動停止
  - 長對話場景：持續說話超過最大錄音時長
  - 噪音干擾場景：背景噪音對 VAD 判定的影響

- [ ] 3.4.4 實作狀態機整合
  ```python
  # FSM 狀態擴展
  class State:
      IDLE = "idle"              # 待機，等待喚醒
      LISTENING = "listening"    # 監聽中，VAD 啟用
      RECORDING = "recording"    # 錄音中，VAD 控制結束
      PROCESSING = "processing"  # 處理中，錄音已結束
      
  # 狀態轉換
  # IDLE → LISTENING (喚醒詞檢測)
  # LISTENING → RECORDING (開始錄音)
  # RECORDING → PROCESSING (VAD 倒數結束)
  # PROCESSING → IDLE (處理完成)
  ```

### 4. 配置系統更新

#### 4.1 更新 YAML 配置模板
- [ ] 4.1.1 新增 VAD 配置項
  ```yaml
  pipeline:
    operators:
      vad:
        silero:
          enabled: true
          threshold: 0.5
          min_silence_duration: 0.5
          min_speech_duration: 0.25
          model_path: "models/silero_vad.onnx"
  ```

- [ ] 4.1.2 新增錄音配置項
  ```yaml
  pipeline:
    operators:
      recording:
        enabled: true
        format: "wav"
        sample_rate: 16000
        max_duration: 60  # seconds
        max_file_size: 100  # MB
        storage:
          type: "memory"  # memory, file, s3
          path: "/tmp/recordings"
        vad_control:
          enabled: true
          silence_countdown: 1.8  # 靜音倒數秒數
          min_recording_duration: 0.5  # 最短錄音時長
          pre_speech_buffer: 0.3  # 語音前緩衝秒數
          post_speech_buffer: 0.2  # 語音後緩衝秒數
  ```

#### 4.2 更新配置類別
- [ ] 4.2.1 執行 yaml2py 重新生成配置類別
- [ ] 4.2.2 更新 ConfigManager 以支援新配置
- [ ] 4.2.3 實作配置驗證和預設值

### 5. 文檔和範例

#### 5.1 使用指南
- [ ] 5.1.1 撰寫 VAD Operator 使用指南
  - 配置說明
  - API 文檔
  - 最佳實踐
  - 常見問題

- [ ] 5.1.2 撰寫 Recording Operator 使用指南
  - 錄音控制 API
  - 格式轉換
  - 儲存選項
  - 效能優化建議

#### 5.2 整合範例
- [ ] 5.2.1 建立簡單範例
  ```python
  # examples/vad_recording_example.py
  """展示 VAD 控制錄音的基本用法"""
  ```

- [ ] 5.2.2 建立進階範例
  ```python
  # examples/smart_recording_example.py
  """展示智慧錄音功能：喚醒詞觸發、VAD 控制、自動停止"""
  ```


## 🔍 驗收標準

### 功能驗收
1. ✅ VAD Operator 能準確檢測語音活動（準確率 > 95%）
2. ✅ Recording Operator 支援多種格式和儲存選項
3. ✅ VAD 控制的錄音自動停止機制正常運作（靜音 1.8s 後停止）
4. ✅ 倒數計時器能正確重置和取消
5. ✅ 兩個 Operator 能與現有 Pipeline 無縫整合
6. ✅ 完整的測試工具和視覺化監控

### 效能驗收
1. ✅ VAD 處理延遲 < 50ms
2. ✅ 錄音不影響即時性（CPU 增量 < 5%）
3. ✅ 倒數計時器不造成額外負擔
4. ✅ 支援 100+ 併發 session
5. ✅ 24小時穩定運行無記憶體洩漏

### 品質驗收
1. ✅ 完整的單元測試覆蓋率（> 80%）
2. ✅ 整合測試通過所有場景（包含倒數重置場景）
3. ✅ 詳細的文檔和使用範例
4. ✅ 程式碼符合專案規範（SOLID、asyncio、pretty-loguru）

## 📅 時程規劃（建議）

### 第一週：VAD Operator 實作
- Silero VAD 基礎功能
- WebRTC VAD 實作
- VAD 事件系統

### 第二週：Recording Operator 實作
- 基礎錄音功能
- 智慧錄音整合
- 儲存和匯出功能

### 第三週：測試框架開發
- 個別 Operator 測試工具
- 整合測試工具
- 視覺化監控

### 第四週：整合和文檔
- 整合測試
- 文檔撰寫
- 最終測試和驗收

## 📝 注意事項

1. **遵循現有架構**：所有 Operator 必須繼承 OperatorBase，遵循統一介面
2. **非阻塞設計**：使用 asyncio，避免阻塞操作
3. **錯誤處理**：完善的異常處理和錯誤恢復機制
4. **資源管理**：注意記憶體使用，避免洩漏
5. **配置驅動**：所有參數應可通過配置調整
6. **日誌規範**：使用 pretty-loguru，保持日誌風格一致
7. **測試優先**：每個功能都應有對應的測試
8. **倒數計時器設計**：
   - 使用 asyncio.Task 實現非阻塞倒數
   - 支援隨時取消（檢測到語音時）
   - 避免多個計時器同時運行
   - 提供視覺化回饋選項

## 🚀 快速開始

```bash
# 1. 創建開發分支
git checkout -b feature/phase5-vad-recording

# 2. 安裝新依賴
pip install silero-vad

# 3. 開始開發 Silero VAD Operator

# 4. 執行測試
python test_vad_integration.py
```

---
建立時間：2025-08-03
最後更新：2025-08-03
負責人：ASR Hub Team