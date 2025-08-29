# BufferManager (音訊緩衝區管理)

## 概述
BufferManager 為不同 ASR 服務提供統一的音訊切窗管理。支援 fixed（固定窗口）、sliding（滑動窗口）、dynamic（動態聚合）三種模式，讓各種 ASR 引擎都能以最適合的方式處理音訊資料。

## 核心功能

### 緩衝模式
- **Fixed Mode** - 固定大小窗口，無重疊（VAD、喚醒詞）
- **Sliding Mode** - 滑動窗口，可重疊（Whisper、長語音）
- **Dynamic Mode** - 動態聚合，彈性輸出（即時串流）

### 主要特性
- **統一介面** - 所有模式使用相同 API
- **自動切窗** - 根據配置自動分割音訊
- **防溢出** - 可設定最大緩衝區大小
- **零複製** - 使用 bytearray 減少記憶體複製

## 使用方式

### Fixed Mode（固定窗口）
```python
from src.interface.buffer import BufferConfig
from src.core.buffer_manager import BufferManager

# Silero VAD 配置：400ms 固定窗口
config = BufferConfig.for_silero_vad(sample_rate=16000, window_ms=400)
buffer = BufferManager(config)

# 推入音訊
buffer.push(audio_bytes)

# 當準備好時取出固定大小窗口
while buffer.ready():
    frame = buffer.pop()  # 固定 400ms 音訊
    vad_result = process_vad(frame)
```

### Sliding Mode（滑動窗口）
```python
# Whisper 配置：5秒窗口，50% 重疊
config = BufferConfig.for_whisper(
    sample_rate=16000, 
    window_sec=5.0, 
    overlap=0.5  # 50% 重疊
)
buffer = BufferManager(config)

# 推入音訊
buffer.push(audio_chunk)

# 取出滑動窗口（每次前進 2.5 秒，保留 2.5 秒重疊）
while buffer.ready():
    frame = buffer.pop()  # 5 秒音訊，與前一幀有 2.5 秒重疊
    transcript = whisper_transcribe(frame)
```

### Dynamic Mode（動態聚合）
```python
# 動態模式：最小 0.5 秒，最大 5 秒
config = BufferConfig(
    mode="dynamic",
    sample_rate=16000,
    min_duration_ms=500,   # 最小 500ms
    max_duration_ms=5000    # 最大 5000ms
)
buffer = BufferManager(config)

# 推入音訊流
for chunk in audio_stream:
    buffer.push(chunk)
    
    # 當累積足夠時自動輸出
    if buffer.ready():
        frame = buffer.pop()
        process_dynamic_audio(frame)

# 結束時強制輸出剩餘資料
final_frame = buffer.flush()
```

## 實際應用範例

### VAD 處理管線
```python
class VADProcessor:
    def __init__(self):
        # 使用預設的 Silero VAD 配置
        self.config = BufferConfig.for_silero_vad()
        self.buffer = BufferManager(self.config)
        
    def process_stream(self, audio_stream):
        """處理音訊流並檢測語音"""
        for chunk in audio_stream:
            self.buffer.push(chunk)
            
            # 處理所有就緒的窗口
            frames = self.buffer.pop_all()
            for frame in frames:
                is_speech = self.detect_speech(frame)
                if is_speech:
                    yield frame
    
    def detect_speech(self, frame):
        # 實際 VAD 檢測邏輯
        return vad_model.predict(frame)
```

### 喚醒詞檢測
```python
class WakewordDetector:
    def __init__(self, model_name="alexa"):
        # OpenWakeWord 需要固定 512 samples
        self.config = BufferConfig.for_openwakeword(
            sample_rate=16000,
            frame_samples=512  # 32ms @ 16kHz
        )
        self.buffer = BufferManager(self.config)
        self.model = load_wakeword_model(model_name)
    
    def detect(self, audio_chunk):
        """檢測喚醒詞"""
        self.buffer.push(audio_chunk)
        
        while self.buffer.ready():
            frame = self.buffer.pop()
            confidence = self.model.predict(frame)
            if confidence > 0.5:
                return True, confidence
        
        return False, 0.0
```

### Whisper 轉譯器
```python
class WhisperTranscriber:
    def __init__(self):
        # 5 秒窗口，1 秒重疊
        self.config = BufferConfig.for_whisper(
            sample_rate=16000,
            window_sec=5.0,
            overlap=0.2  # 20% 重疊 = 1 秒
        )
        self.buffer = BufferManager(self.config)
        
    def transcribe_stream(self, audio_stream):
        """串流轉譯with重疊窗口"""
        transcripts = []
        
        for chunk in audio_stream:
            self.buffer.push(chunk)
            
            if self.buffer.ready():
                frame = self.buffer.pop()
                text = whisper_model.transcribe(frame)
                
                # 處理重疊部分的重複文字
                text = self.merge_overlapped_text(text, transcripts)
                transcripts.append(text)
                yield text
        
        # 處理剩餘音訊
        final = self.buffer.flush()
        if final:
            yield whisper_model.transcribe(final)
```

### 動態串流處理
```python
class DynamicStreamProcessor:
    def __init__(self):
        self.config = BufferConfig(
            mode="dynamic",
            sample_rate=16000,
            min_duration_ms=200,  # 至少 200ms
            max_duration_ms=3000   # 最多 3 秒
        )
        self.buffer = BufferManager(self.config)
        
    def process_with_vad(self, audio_stream, vad_service):
        """結合 VAD 的動態處理"""
        for chunk in audio_stream:
            self.buffer.push(chunk)
            
            # VAD 檢測
            is_speech = vad_service.detect(chunk)
            
            if is_speech and self.buffer.ready():
                # 有語音且達到最小長度
                frame = self.buffer.pop()
                yield frame
            elif not is_speech and self.buffer.buffered_bytes() > 0:
                # 靜音時強制輸出
                frame = self.buffer.flush()
                if frame:
                    yield frame
```

## 預設配置建議

### Silero VAD
```python
cfg = BufferConfig.for_silero_vad(
    sample_rate=16000,
    window_ms=400  # 400ms 窗口
)
```
- **用途**: 語音活動檢測
- **特點**: 低延遲、穩定
- **窗口**: 400-512ms 最佳

### OpenWakeWord
```python
cfg = BufferConfig.for_openwakeword(
    sample_rate=16000,
    frame_samples=512  # 固定 512 samples
)
```
- **用途**: 關鍵字喚醒
- **特點**: 模型要求固定大小
- **窗口**: 512 或 1024 samples

### FunASR Streaming
```python
cfg = BufferConfig.for_funasr(
    sample_rate=16000,
    frame_samples=9600  # 600ms
)
```
- **用途**: 串流 ASR
- **特點**: 固定 context window
- **窗口**: 9600 samples (0.6s)

### Whisper
```python
cfg = BufferConfig.for_whisper(
    sample_rate=16000,
    window_sec=5.0,   # 5 秒窗口
    overlap=0.5       # 50% 重疊
)
```
- **用途**: 長語音轉譯
- **特點**: 大窗口避免斷句
- **重疊**: 避免邊界切斷

## 配置參數說明

```python
BufferConfig(
    # 基本參數
    mode="fixed",           # fixed|sliding|dynamic
    sample_rate=16000,      # 採樣率 (Hz)
    sample_width=2,         # 每個樣本位元組數 (int16=2)
    channels=1,             # 聲道數
    
    # Fixed/Sliding 模式
    frame_size=8000,        # 窗口大小 (samples)
    step_size=4000,         # 步進大小 (samples，sliding mode)
    
    # Dynamic 模式
    min_duration_ms=200,    # 最小輸出長度 (ms)
    max_duration_ms=5000,   # 最大輸出長度 (ms)
    
    # 防溢出
    max_buffer_size=160000  # 最大緩衝 (bytes)
)
```

## 效能優化

### 記憶體管理
- 使用 bytearray 減少複製
- 配置 max_buffer_size 防止溢出
- pop_all() 批量處理提高效率

### 計算優化
```python
# 批量處理所有就緒幀
frames = buffer.pop_all()
results = batch_process(frames)  # 批量處理更高效

# 避免頻繁檢查
if buffer.buffered_bytes() > threshold:
    # 達到閾值才處理
    process_buffer()
```

## 錯誤處理

所有方法都包含異常處理：
- **push**: 返回 bool，失敗記錄日誌
- **pop**: 返回 None 表示未就緒
- **flush**: 返回 None 表示緩衝區空
- **reset**: 返回 bool 表示成功與否

## 注意事項

1. **採樣率一致**: 確保推入的音訊採樣率與配置一致
2. **防止溢出**: 長時間運行應配置 max_buffer_size
3. **及時清理**: 使用 flush() 或 reset() 清理未處理資料
4. **模式選擇**: 
   - VAD/喚醒詞 → Fixed
   - Whisper/長語音 → Sliding
   - 串流/即時 → Dynamic
5. **重疊處理**: Sliding mode 需處理文字重複問題

## 設計原則

- **通用性**: 統一介面適配各種 ASR 服務
- **效能**: 最小化記憶體複製和計算開銷
- **靈活性**: 三種模式滿足不同需求
- **可靠性**: 完整的參數驗證和錯誤處理