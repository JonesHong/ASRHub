# VAD Service (語音活動檢測服務)

## 概述
VAD（Voice Activity Detection）服務使用 Silero VAD 模型進行語音活動檢測，能夠準確判斷音訊中是否包含人聲。支援即時串流處理和批次處理，為每個 session 提供獨立的檢測狀態管理。

## 核心功能

### 語音檢測
- **Silero VAD 模型** - 使用輕量級 ONNX 模型，準確率高
- **即時處理** - 支援串流音訊的即時檢測
- **批次處理** - 可處理完整音訊檔案
- **多語言支援** - 支援多種語言的語音檢測

### Session 管理
- **獨立狀態** - 每個 session 維護獨立的檢測狀態
- **監聽執行緒** - 為每個 session 提供獨立的監聽執行緒
- **Callback 機制** - 檢測到語音變化時觸發回調

### 狀態追蹤
- **語音段落** - 追蹤語音開始和結束
- **靜音檢測** - 識別靜音段落
- **信心度分數** - 提供檢測信心度（0.0-1.0）

## 使用方式

### 基本初始化
```python
from src.service.vad import vad_service

# 使用預設配置初始化
vad_service.initialize()

# 使用自定義配置
from src.interface.vad import VADConfig

config = VADConfig(
    threshold=0.5,              # 語音檢測閾值
    min_silence_duration=1.0,   # 最小靜音時長（秒）
    min_speech_duration=0.25,   # 最小語音時長（秒）
    sample_rate=16000,          # 採樣率
    window_size=512            # 處理窗口大小
)
vad_service.initialize(config)
```

### 即時串流處理
```python
# 定義語音狀態變化的回調
def on_speech_change(session_id: str, is_speech: bool, confidence: float):
    if is_speech:
        print(f"🎤 檢測到語音開始 [{session_id}] 信心度: {confidence:.2f}")
    else:
        print(f"🔇 檢測到語音結束 [{session_id}]")

# 開始監控 session
session_id = "user_123"
vad_service.start_monitoring(
    session_id,
    on_speech_start=lambda sid, conf: on_speech_change(sid, True, conf),
    on_speech_end=lambda sid: on_speech_change(sid, False, 0)
)

# 處理串流音訊
while receiving_audio:
    audio_chunk = get_audio_chunk()  # 獲取音訊片段
    result = vad_service.process_stream(session_id, audio_chunk)
    
    if result and result.is_speech:
        print(f"當前為語音，信心度: {result.confidence:.2f}")

# 停止監控
vad_service.stop_monitoring(session_id)
```

### 批次處理
```python
import numpy as np

# 處理單個音訊片段（無狀態）
audio_data = np.array([...], dtype=np.float32)  # 音訊數據
result = vad_service.process_chunk(audio_data, sample_rate=16000)

if result:
    print(f"語音: {result.is_speech}, 信心度: {result.confidence:.2f}")
```

### 狀態管理
```python
# 檢查監控狀態
if vad_service.is_monitoring(session_id):
    print("正在監控中")

# 獲取 session 狀態
state = vad_service.get_session_state(session_id)
if state:
    print(f"當前狀態: {state.status}")
    print(f"語音段數: {state.speech_segments}")
    print(f"總語音時長: {state.total_speech_duration:.1f} 秒")

# 重置 session 狀態
vad_service.reset_session(session_id)

# 停止所有監控
count = vad_service.stop_all_monitoring()
print(f"停止了 {count} 個監控")
```

## 實際應用範例

### 錄音自動分段
```python
from src.service.vad import vad_service
from src.service.recording import recording_service

class AutoSegmentRecorder:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.segment_count = 0
        
    def start(self):
        """開始錄音並自動分段"""
        # 開始錄音
        recording_service.start_recording(self.session_id)
        
        # 設定 VAD 回調
        vad_service.start_monitoring(
            self.session_id,
            on_speech_start=self.on_speech_start,
            on_speech_end=self.on_speech_end
        )
    
    def on_speech_start(self, session_id: str, confidence: float):
        """語音開始 - 標記段落開始"""
        logger.info(f"段落 {self.segment_count + 1} 開始")
        
    def on_speech_end(self, session_id: str):
        """語音結束 - 保存段落"""
        self.segment_count += 1
        
        # 保存當前段落
        audio_data = recording_service.get_buffer(session_id)
        save_segment(f"segment_{self.segment_count}.wav", audio_data)
        
        # 清空緩衝準備下一段
        recording_service.clear_buffer(session_id)
        logger.info(f"段落 {self.segment_count} 已保存")
```

### VAD 進階技巧：Hysteresis 與緩衝管理

為了提高 VAD 的準確性和避免語音被切斷，以下是重要的優化技巧：

```python
class OptimizedVADProcessor:
    """優化的 VAD 處理器"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        
        # Hysteresis 雙閾值設定
        self.config = {
            'start_threshold': 0.5,     # 開始語音的閾值（較高）
            'continue_threshold': 0.35,  # 持續語音的閾值（中等）
            'stop_threshold': 0.25,      # 結束語音的閾值（較低）
            'min_speech_duration': 0.25, # 最小語音長度（秒）
            'min_silence_duration': 1.5, # 最小靜音長度才判定結束（秒）
            'pre_buffer_size': 25,       # Pre-roll 緩衝大小（幀）
            'tail_padding_size': 20      # Tail padding 大小（幀）
        }
        
        # 狀態管理
        self.current_state = 'silence'  # silence, speech, trailing
        self.speech_frames = 0
        self.silence_frames = 0
        
    def get_adaptive_threshold(self):
        """根據當前狀態返回適應性閾值"""
        if self.current_state == 'silence':
            # 靜音狀態需要較高閾值才開始
            return self.config['start_threshold']
        elif self.current_state == 'speech':
            # 語音中使用較低閾值維持
            return self.config['continue_threshold']
        else:  # trailing
            # 尾部使用最低閾值
            return self.config['stop_threshold']
    
    def process_with_hysteresis(self, audio_chunk: bytes):
        """使用 Hysteresis 處理音訊"""
        # VAD 檢測
        result = vad_service.process_chunk(audio_chunk)
        confidence = result.confidence if result else 0
        
        # 使用適應性閾值
        threshold = self.get_adaptive_threshold()
        is_speech = confidence > threshold
        
        # 狀態轉換邏輯
        if self.current_state == 'silence':
            if is_speech:
                self.speech_frames += 1
                # 檢查是否達到最小語音長度
                if self.speech_frames * 0.032 >= self.config['min_speech_duration']:
                    self.current_state = 'speech'
                    self.on_speech_start()
            else:
                self.speech_frames = 0
                
        elif self.current_state == 'speech':
            if is_speech:
                # 重置靜音計數
                self.silence_frames = 0
            else:
                self.silence_frames += 1
                # 檢查是否達到最小靜音長度
                if self.silence_frames * 0.032 >= self.config['min_silence_duration']:
                    self.current_state = 'trailing'
                    self.start_tail_padding()
                    
        elif self.current_state == 'trailing':
            # 尾部處理
            if is_speech:
                # 尾部又檢測到語音，返回語音狀態
                self.current_state = 'speech'
                self.silence_frames = 0
                logger.info("尾部檢測到語音，繼續")
            else:
                # 繼續尾部處理
                self.finish_tail_padding()
    
    def on_speech_start(self):
        logger.info(f"語音開始 (閾值: {self.config['start_threshold']})")
        
    def start_tail_padding(self):
        logger.info(f"開始尾部保留 ({self.config['tail_padding_size']} 幀)")
        
    def finish_tail_padding(self):
        self.current_state = 'silence'
        self.speech_frames = 0
        self.silence_frames = 0
        logger.info("語音結束（含尾部）")
```

### ASR 智慧觸發
```python
from src.service.timer import timer
from collections import deque

class SmartASRTrigger:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.speech_buffer = []
        
    def start(self):
        """開始智慧 ASR 觸發"""
        vad_service.start_monitoring(
            self.session_id,
            on_speech_start=self.on_speech_start,
            on_speech_end=self.on_speech_end
        )
    
    def on_speech_start(self, session_id: str, confidence: float):
        """語音開始 - 開始收集"""
        logger.info("開始收集語音")
        self.speech_buffer = []
        
        # 停止靜音計時器
        timer.stop_countdown(f"silence_{session_id}")
        
    def on_speech_end(self, session_id: str):
        """語音結束 - 觸發轉譯"""
        logger.info("語音結束，準備轉譯")
        
        # 設定靜音計時器（1.5 秒後觸發轉譯）
        timer.start_countdown(
            f"silence_{session_id}",
            callback=lambda _: self.trigger_asr(),
            duration=1.5
        )
    
    def trigger_asr(self):
        """觸發 ASR 轉譯"""
        if self.speech_buffer:
            # 送出語音進行轉譯
            transcribe_audio(self.speech_buffer)
            self.speech_buffer = []
```

### 會議靜音檢測
```python
class MeetingSilenceDetector:
    def __init__(self, session_id: str, max_silence: float = 30.0):
        self.session_id = session_id
        self.max_silence = max_silence
        self.last_speech_time = time.time()
        
    def start(self):
        """開始檢測會議靜音"""
        vad_service.start_monitoring(
            self.session_id,
            on_speech_start=self.on_speech,
            on_speech_end=self.check_silence
        )
        
    def on_speech(self, session_id: str, confidence: float):
        """更新最後語音時間"""
        self.last_speech_time = time.time()
        
    def check_silence(self, session_id: str):
        """檢查靜音時長"""
        silence_duration = time.time() - self.last_speech_time
        
        if silence_duration > self.max_silence:
            logger.warning(f"會議靜音超過 {self.max_silence} 秒")
            send_silence_alert(session_id)
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  vad:
    enabled: true
    model_path: "models/silero_vad.onnx"  # 模型路徑
    threshold: 0.5                        # 檢測閾值 (0.0-1.0)
    min_silence_duration: 1.0             # 最小靜音時長（秒）
    min_speech_duration: 0.25             # 最小語音時長（秒）
    window_size: 512                      # 處理窗口大小
    sample_rate: 16000                    # 預設採樣率
    use_gpu: false                         # 是否使用 GPU
```

## 效能優化

### 處理建議
- **窗口大小**: 512 樣本（32ms @ 16kHz）平衡準確度和延遲
- **閾值調整**: 
  - 0.3-0.4: 高敏感度，可能有誤判
  - 0.5-0.6: 平衡設定（預設）
  - 0.7-0.8: 低敏感度，減少誤判

### 資源使用
- **CPU**: 單核約 5-10% @ 16kHz
- **記憶體**: 模型約 10MB，每 session 約 1MB
- **延遲**: < 50ms 處理延遲

## 注意事項

1. **模型載入**: 首次使用時會自動下載模型（約 1.5MB）
2. **採樣率**: 建議使用 16kHz，8kHz 也支援但準確度略低
3. **音訊格式**: 輸入需為單聲道 float32 格式
4. **執行緒安全**: 所有操作都是執行緒安全的
5. **GPU 支援**: 可選用 GPU 加速，但 CPU 已足夠快速

## 錯誤處理

```python
from src.interface.exceptions import (
    VADInitializationError,
    VADModelError,
    VADSessionError
)

try:
    vad_service.initialize()
except VADInitializationError as e:
    logger.error(f"VAD 初始化失敗: {e}")
    
try:
    result = vad_service.process_chunk(audio_data)
except VADModelError as e:
    logger.error(f"模型推論失敗: {e}")
```

## 模型資訊

- **模型**: Silero VAD v4
- **格式**: ONNX
- **大小**: ~1.5MB
- **支援語言**: 多語言（包含中文、英文等）
- **準確率**: > 95% (SNR > 10dB)

## 未來擴展

- 支援多模型切換
- 音樂/語音分類
- 說話人分離
- 情緒檢測整合
- 語言識別功能