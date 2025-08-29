# Recording Service (錄音服務)

## 概述
錄音服務提供完整的音訊錄製功能，包括即時錄音、檔案儲存、格式轉換等。支援多 session 並行錄音、即時串流處理、自動檔案管理等進階功能。

## 核心功能

### 錄音管理
- **多 Session 支援** - 同時處理多個獨立錄音 session
- **即時錄音** - 從麥克風或音訊流即時錄製
- **緩衝管理** - 智慧記憶體管理，防止溢出
- **格式支援** - WAV、MP3、FLAC 等多種格式

### 檔案處理
- **自動儲存** - 定時或觸發式自動儲存
- **分段錄音** - 支援按時間或大小分段
- **元資料** - 自動記錄時間戳、時長等資訊
- **檔案命名** - 智慧命名規則，避免覆蓋

## 使用方式

### 基本錄音
```python
from src.service.recording import recording_service

# 開始錄音
session_id = "user_123"
success = recording_service.start_recording(session_id)
if success:
    print(f"開始錄音: {session_id}")

# 停止錄音並獲取資料
audio_data = recording_service.stop_recording(session_id)
if audio_data:
    print(f"錄音完成，時長: {len(audio_data)/16000:.1f} 秒")

# 儲存到檔案
file_path = recording_service.save_recording(
    session_id,
    filename="recording_001.wav",
    format="wav"
)
print(f"已儲存至: {file_path}")
```

### 串流錄音
```python
# 處理串流音訊
def process_audio_stream(session_id: str):
    """處理即時音訊流"""
    recording_service.start_recording(session_id)
    
    while streaming:
        audio_chunk = get_audio_chunk()  # 獲取音訊片段
        
        # 寫入錄音緩衝
        recording_service.write_audio(session_id, audio_chunk)
        
        # 可選：取得當前緩衝區大小
        buffer_size = recording_service.get_buffer_size(session_id)
        if buffer_size > 16000 * 60:  # 超過 60 秒
            # 儲存並清空緩衝
            recording_service.save_and_clear(session_id)
    
    # 結束時儲存剩餘資料
    recording_service.stop_recording(session_id)
```

### 自動分段錄音
```python
from src.service.recording import RecordingConfig

# 配置分段錄音
config = RecordingConfig(
    auto_save=True,              # 啟用自動儲存
    segment_duration=300,        # 每 5 分鐘一個檔案
    segment_size_mb=100,         # 或每 100MB 一個檔案
    output_dir="recordings/",    # 儲存目錄
    filename_pattern="{session_id}_{timestamp}_{segment}.wav"
)

recording_service.configure(session_id, config)
recording_service.start_recording(session_id)

# 錄音會自動分段儲存
# segment_001.wav, segment_002.wav, ...
```

### 狀態查詢
```python
# 檢查錄音狀態
if recording_service.is_recording(session_id):
    info = recording_service.get_recording_info(session_id)
    print(f"正在錄音...")
    print(f"已錄製: {info['duration']:.1f} 秒")
    print(f"緩衝大小: {info['buffer_size']} bytes")
    print(f"開始時間: {info['start_time']}")

# 獲取所有活躍的錄音 session
active_sessions = recording_service.get_active_sessions()
print(f"活躍錄音數: {len(active_sessions)}")
```

## 實際應用範例

### 會議錄音系統
```python
from datetime import datetime
from src.service.vad import vad_service

class MeetingRecorder:
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id
        self.session_id = f"meeting_{meeting_id}"
        self.participants = []
        
    def start_meeting(self):
        """開始會議錄音"""
        # 配置錄音參數
        config = RecordingConfig(
            auto_save=True,
            segment_duration=1800,  # 30 分鐘分段
            output_dir=f"meetings/{datetime.now().strftime('%Y%m%d')}/",
            filename_pattern=f"meeting_{self.meeting_id}_{{segment}}.wav",
            save_metadata=True  # 儲存元資料
        )
        
        recording_service.configure(self.session_id, config)
        recording_service.start_recording(self.session_id)
        
        # 同時啟動 VAD 檢測發言
        vad_service.start_monitoring(
            self.session_id,
            on_speech_start=self.mark_speech_start,
            on_speech_end=self.mark_speech_end
        )
        
        logger.info(f"會議 {self.meeting_id} 開始錄音")
    
    def mark_speech_start(self, session_id: str, confidence: float):
        """標記發言開始"""
        timestamp = recording_service.get_current_timestamp(session_id)
        recording_service.add_marker(
            session_id,
            timestamp,
            "speech_start",
            {"confidence": confidence}
        )
    
    def mark_speech_end(self, session_id: str):
        """標記發言結束"""
        timestamp = recording_service.get_current_timestamp(session_id)
        recording_service.add_marker(
            session_id,
            timestamp,
            "speech_end"
        )
    
    def end_meeting(self):
        """結束會議"""
        # 停止錄音
        audio_data = recording_service.stop_recording(self.session_id)
        
        # 生成會議報告
        info = recording_service.get_recording_info(self.session_id)
        report = {
            'meeting_id': self.meeting_id,
            'duration': info['duration'],
            'segments': info['segments_saved'],
            'markers': info['markers'],
            'file_paths': info['saved_files']
        }
        
        save_meeting_report(report)
        return report
```

### 語音備忘錄
```python
from src.service.wakeword import wakeword_service

class VoiceMemo:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session_id = f"memo_{user_id}"
        self.is_recording = False
        
    def initialize(self):
        """初始化語音備忘錄"""
        # 監聽開始/停止錄音的喚醒詞
        wakeword_service.start_monitoring(
            self.session_id,
            keywords=["start_memo", "stop_memo"],
            on_detected=self.handle_wakeword
        )
    
    def handle_wakeword(self, session_id: str, detection):
        """處理喚醒詞"""
        if detection.keyword == "start_memo" and not self.is_recording:
            self.start_memo()
        elif detection.keyword == "stop_memo" and self.is_recording:
            self.stop_memo()
    
    def start_memo(self):
        """開始錄製備忘錄"""
        self.is_recording = True
        
        # 配置簡單錄音
        config = RecordingConfig(
            output_dir=f"memos/{self.user_id}/",
            filename_pattern="memo_{timestamp}.wav",
            audio_format="wav",
            sample_rate=16000
        )
        
        recording_service.configure(self.session_id, config)
        recording_service.start_recording(self.session_id)
        
        # 播放開始音效
        play_sound("memo_start.wav")
        logger.info("開始錄製備忘錄")
    
    def stop_memo(self):
        """停止錄製並儲存"""
        self.is_recording = False
        
        # 停止錄音
        audio_data = recording_service.stop_recording(self.session_id)
        
        if audio_data and len(audio_data) > 16000:  # 至少 1 秒
            # 儲存備忘錄
            file_path = recording_service.save_recording(
                self.session_id,
                format="mp3"  # 壓縮格式節省空間
            )
            
            # 播放完成音效
            play_sound("memo_saved.wav")
            
            # 可選：轉譯成文字
            transcribe_memo(file_path)
            
            logger.info(f"備忘錄已儲存: {file_path}")
        else:
            logger.warning("備忘錄太短，已取消")
```

### 通話錄音
```python
class CallRecorder:
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.session_id = f"call_{call_id}"
        
    def start_call_recording(self, caller: str, callee: str):
        """開始通話錄音"""
        # 配置雙聲道錄音（如果需要）
        config = RecordingConfig(
            channels=2,  # 雙聲道：左聲道=來電，右聲道=去電
            sample_rate=8000,  # 電話音質
            output_dir="calls/",
            filename_pattern=f"call_{self.call_id}.wav",
            save_metadata=True,
            metadata={
                'caller': caller,
                'callee': callee,
                'start_time': datetime.now().isoformat()
            }
        )
        
        recording_service.configure(self.session_id, config)
        recording_service.start_recording(self.session_id)
        
    def add_event(self, event_type: str, data: dict = None):
        """添加通話事件標記"""
        timestamp = recording_service.get_current_timestamp(self.session_id)
        recording_service.add_marker(
            self.session_id,
            timestamp,
            event_type,
            data
        )
    
    def end_call_recording(self):
        """結束通話錄音"""
        recording_service.stop_recording(self.session_id)
        
        # 生成通話記錄
        info = recording_service.get_recording_info(self.session_id)
        
        call_record = {
            'call_id': self.call_id,
            'duration': info['duration'],
            'file_path': info['saved_files'][0],
            'events': info['markers']
        }
        
        return call_record
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  recording:
    enabled: true
    default_format: "wav"              # 預設格式
    default_sample_rate: 16000         # 預設採樣率
    default_channels: 1                # 預設聲道數
    output_dir: "recordings/"          # 預設輸出目錄
    
    buffer:
      max_size_mb: 500                 # 最大緩衝區大小
      auto_flush_size_mb: 100          # 自動刷新大小
      
    auto_save:
      enabled: false                   # 自動儲存
      interval_seconds: 300            # 儲存間隔
      
    file_naming:
      pattern: "{session_id}_{timestamp}.{format}"
      timestamp_format: "%Y%m%d_%H%M%S"
```

## 進階功能

### 音訊處理管線
```python
# 錄音時即時處理
def recording_with_processing(session_id: str):
    """錄音同時進行音訊處理"""
    from src.service.audio_enhancer import audio_enhancer
    
    # 設定處理管線
    recording_service.set_processor(
        session_id,
        lambda audio: audio_enhancer.enhance_for_recording(audio)
    )
    
    recording_service.start_recording(session_id)
```

### 多軌錄音
```python
# 多軌混音錄製
config = RecordingConfig(
    channels=4,  # 4 軌錄音
    track_labels=["vocal", "guitar", "bass", "drums"]
)

recording_service.configure(session_id, config)

# 分別寫入各軌
recording_service.write_track(session_id, 0, vocal_audio)
recording_service.write_track(session_id, 1, guitar_audio)
```

## 效能考量

- **緩衝區管理**: 自動調整大小，防止記憶體溢出
- **檔案 I/O**: 使用異步寫入，不阻塞錄音
- **壓縮格式**: MP3/AAC 可節省 80% 空間
- **採樣率**: 語音用 16kHz，音樂用 44.1kHz

## 注意事項

1. **記憶體使用**: 每秒單聲道 16kHz 約 32KB
2. **儲存空間**: WAV 格式每小時約 115MB
3. **並發限制**: 建議同時錄音 < 100 個 session
4. **檔案系統**: 確保有足夠的寫入權限
5. **格式轉換**: MP3 轉換需要 ffmpeg

## 錯誤處理

```python
from src.interface.exceptions import (
    RecordingError,
    RecordingSessionError,
    StorageError
)

try:
    recording_service.start_recording(session_id)
except RecordingSessionError as e:
    logger.error(f"Session 錯誤: {e}")
except StorageError as e:
    logger.error(f"儲存空間不足: {e}")
    # 清理舊錄音
    cleanup_old_recordings()
```

## 支援的音訊格式

- WAV (無壓縮，最高品質)
- MP3 (有損壓縮，體積小)
- FLAC (無損壓縮)
- AAC (有損壓縮，效率高)
- OGG (開源格式)

## 未來擴展

- 雲端儲存整合
- 即時串流上傳
- 多裝置同步錄音
- 智慧降噪整合
- 語音辨識即時字幕