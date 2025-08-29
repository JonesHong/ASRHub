# Microphone Capture Service (麥克風捕捉服務)

## 概述
麥克風捕捉服務提供跨平台的音訊輸入功能，支援多種音訊後端（PyAudio、sounddevice），可從麥克風或其他音訊輸入裝置即時捕捉音訊流。提供裝置管理、即時監控、自動增益控制等功能。

## 核心功能

### 音訊捕捉
- **即時串流** - 低延遲音訊流捕捉
- **多裝置支援** - 選擇不同輸入裝置
- **格式彈性** - 支援多種採樣率和位元深度
- **緩衝管理** - 智慧緩衝防止資料丟失

### 裝置管理
- **裝置列舉** - 列出所有可用音訊裝置
- **自動選擇** - 智慧選擇預設裝置
- **熱插拔** - 支援裝置動態連接/斷開
- **多裝置** - 同時從多個裝置捕捉

## 使用方式

### 基本捕捉
```python
from src.service.microphone_capture import mic_capture

# 列出可用裝置
devices = mic_capture.list_devices()
for device in devices:
    print(f"[{device['id']}] {device['name']} - {device['channels']}ch @ {device['sample_rate']}Hz")

# 使用預設麥克風開始捕捉
mic_capture.start_capture(
    session_id="user_123",
    callback=lambda audio: process_audio(audio)
)

# 停止捕捉
mic_capture.stop_capture("user_123")
```

### 指定裝置捕捉
```python
from src.service.microphone_capture import CaptureConfig

# 配置捕捉參數
config = CaptureConfig(
    device_id=2,              # 指定裝置 ID
    sample_rate=48000,        # 採樣率
    channels=2,               # 聲道數（立體聲）
    chunk_size=1024,          # 緩衝區大小
    format='int16'            # 音訊格式
)

# 開始捕捉
mic_capture.start_capture_with_config(
    session_id="user_123",
    config=config,
    callback=process_stereo_audio
)
```

### 串流處理
```python
class AudioStreamProcessor:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.buffer = []
        
    def start(self):
        """開始音訊捕捉和處理"""
        mic_capture.start_capture(
            self.session_id,
            callback=self.on_audio_chunk,
            error_callback=self.on_error
        )
    
    def on_audio_chunk(self, chunk: bytes):
        """處理音訊塊"""
        # 累積緩衝
        self.buffer.append(chunk)
        
        # 當累積足夠資料時處理
        if len(self.buffer) >= 10:  # 10 chunks
            self.process_buffer()
    
    def process_buffer(self):
        """處理累積的音訊"""
        full_audio = b''.join(self.buffer)
        self.buffer = []
        
        # 執行處理（如 VAD、ASR 等）
        process_audio_data(full_audio)
    
    def on_error(self, error: Exception):
        """處理錯誤"""
        logger.error(f"捕捉錯誤: {error}")
        # 嘗試重新連接
        self.restart_capture()
    
    def stop(self):
        """停止捕捉"""
        mic_capture.stop_capture(self.session_id)
```

## 實際應用範例

### 語音助理輸入
```python
from src.service.wakeword import wakeword_service
from src.service.vad import vad_service

class VoiceAssistantInput:
    """語音助理音訊輸入管理"""
    
    def __init__(self):
        self.session_id = "assistant"
        self.is_listening = False
        self.audio_buffer = []
        
    def start(self):
        """啟動語音助理"""
        # 配置高品質捕捉
        config = CaptureConfig(
            sample_rate=16000,  # 語音識別標準
            channels=1,         # 單聲道
            chunk_size=512,     # 32ms @ 16kHz
            auto_gain=True,     # 自動增益
            noise_suppression=True  # 噪音抑制
        )
        
        # 開始捕捉
        mic_capture.start_capture_with_config(
            self.session_id,
            config=config,
            callback=self.process_audio
        )
        
        logger.info("語音助理已啟動，等待喚醒詞...")
    
    def process_audio(self, chunk: bytes):
        """處理捕捉的音訊"""
        if not self.is_listening:
            # 檢測喚醒詞
            detection = wakeword_service.process_chunk(chunk)
            if detection:
                self.on_wake_word_detected()
        else:
            # 已喚醒，收集語音指令
            self.audio_buffer.append(chunk)
            
            # VAD 檢測語音結束
            vad_result = vad_service.process_chunk(chunk)
            if vad_result and not vad_result.is_speech:
                self.on_speech_end()
    
    def on_wake_word_detected(self):
        """喚醒詞檢測到"""
        self.is_listening = True
        self.audio_buffer = []
        play_activation_sound()
        logger.info("助理已喚醒，請說出指令...")
    
    def on_speech_end(self):
        """語音結束"""
        self.is_listening = False
        
        # 處理收集的語音
        full_audio = b''.join(self.audio_buffer)
        self.audio_buffer = []
        
        # 送去 ASR 識別
        transcribe_and_execute(full_audio)
```

### 多麥克風陣列
```python
class MicrophoneArray:
    """多麥克風陣列捕捉"""
    
    def __init__(self, device_ids: list):
        self.device_ids = device_ids
        self.sessions = {}
        self.audio_streams = {}
        
    def start_array_capture(self):
        """啟動陣列捕捉"""
        for i, device_id in enumerate(self.device_ids):
            session_id = f"mic_{i}"
            self.sessions[device_id] = session_id
            self.audio_streams[session_id] = []
            
            # 每個麥克風獨立捕捉
            config = CaptureConfig(
                device_id=device_id,
                sample_rate=48000,
                channels=1
            )
            
            mic_capture.start_capture_with_config(
                session_id,
                config=config,
                callback=lambda audio, sid=session_id: 
                    self.on_mic_audio(sid, audio)
            )
        
        logger.info(f"已啟動 {len(self.device_ids)} 個麥克風")
    
    def on_mic_audio(self, session_id: str, audio: bytes):
        """處理單個麥克風音訊"""
        self.audio_streams[session_id].append(audio)
        
        # 當所有麥克風都有新資料時處理
        if all(len(stream) > 0 for stream in self.audio_streams.values()):
            self.process_array_audio()
    
    def process_array_audio(self):
        """處理陣列音訊"""
        # 收集所有麥克風的音訊
        array_audio = []
        for session_id in self.sessions.values():
            if self.audio_streams[session_id]:
                audio = self.audio_streams[session_id].pop(0)
                array_audio.append(audio)
        
        # 執行波束成形或其他陣列處理
        enhanced_audio = self.beamforming(array_audio)
        process_enhanced_audio(enhanced_audio)
    
    def beamforming(self, multi_channel_audio: list) -> bytes:
        """波束成形處理（簡化示例）"""
        # 這裡應該實作真正的波束成形算法
        # 簡單平均作為示例
        import numpy as np
        
        arrays = [np.frombuffer(audio, dtype=np.int16) 
                 for audio in multi_channel_audio]
        averaged = np.mean(arrays, axis=0).astype(np.int16)
        return averaged.tobytes()
```

### 音訊監控器
```python
class AudioMonitor:
    """即時音訊監控"""
    
    def __init__(self):
        self.session_id = "monitor"
        self.level_history = []
        self.clipping_count = 0
        
    def start_monitoring(self):
        """開始監控"""
        # 高採樣率捕捉
        config = CaptureConfig(
            sample_rate=48000,
            channels=2,
            chunk_size=256,  # 小緩衝for低延遲
            format='float32'
        )
        
        mic_capture.start_capture_with_config(
            self.session_id,
            config=config,
            callback=self.analyze_audio
        )
        
        # 啟動即時顯示
        self.start_level_display()
    
    def analyze_audio(self, chunk: bytes):
        """分析音訊"""
        import numpy as np
        
        # 轉換為浮點數陣列
        audio = np.frombuffer(chunk, dtype=np.float32)
        
        # 計算音量
        rms = np.sqrt(np.mean(audio ** 2))
        db = 20 * np.log10(rms + 1e-10)
        
        # 檢測削波
        if np.any(np.abs(audio) >= 0.99):
            self.clipping_count += 1
            logger.warning(f"⚠️ 檢測到削波！總計: {self.clipping_count}")
        
        # 記錄歷史
        self.level_history.append({
            'timestamp': time.time(),
            'rms': rms,
            'db': db,
            'peak': np.max(np.abs(audio))
        })
        
        # 保持歷史長度
        if len(self.level_history) > 1000:
            self.level_history.pop(0)
    
    def start_level_display(self):
        """啟動音量顯示"""
        import threading
        
        def display_loop():
            while True:
                if self.level_history:
                    latest = self.level_history[-1]
                    bars = int(latest['rms'] * 50)
                    bar_display = '█' * bars + '░' * (50 - bars)
                    print(f"\r音量: {bar_display} {latest['db']:.1f} dB", end='')
                time.sleep(0.1)
        
        thread = threading.Thread(target=display_loop, daemon=True)
        thread.start()
    
    def get_statistics(self):
        """取得統計資料"""
        if not self.level_history:
            return None
        
        rms_values = [h['rms'] for h in self.level_history]
        return {
            'avg_rms': np.mean(rms_values),
            'max_rms': np.max(rms_values),
            'min_rms': np.min(rms_values),
            'clipping_count': self.clipping_count,
            'duration': len(self.level_history) * 256 / 48000  # seconds
        }
```

### 自動增益控制
```python
class AutoGainController:
    """自動增益控制"""
    
    def __init__(self, target_level: float = 0.3):
        self.target_level = target_level  # 目標 RMS
        self.gain = 1.0
        self.session_id = "agc"
        
    def start(self):
        """開始 AGC"""
        mic_capture.start_capture(
            self.session_id,
            callback=self.process_with_agc
        )
    
    def process_with_agc(self, chunk: bytes):
        """應用 AGC"""
        import numpy as np
        
        # 轉換格式
        audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        # 計算當前音量
        current_level = np.sqrt(np.mean(audio ** 2))
        
        # 調整增益（緩慢調整避免突變）
        if current_level > 0.001:  # 避免除零
            target_gain = self.target_level / current_level
            # 平滑調整
            self.gain = 0.95 * self.gain + 0.05 * target_gain
            # 限制增益範圍
            self.gain = np.clip(self.gain, 0.1, 10.0)
        
        # 應用增益
        adjusted_audio = audio * self.gain
        
        # 防止削波
        adjusted_audio = np.clip(adjusted_audio, -1.0, 1.0)
        
        # 轉回 int16
        output = (adjusted_audio * 32768).astype(np.int16).tobytes()
        
        # 送出處理後的音訊
        send_processed_audio(output)
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  microphone_capture:
    enabled: true
    backend: "auto"              # auto, pyaudio, sounddevice
    
    default_config:
      device: "default"          # default 或裝置名稱
      sample_rate: 16000         # 預設採樣率
      channels: 1                # 預設聲道數
      chunk_size: 1024           # 緩衝區大小
      format: "int16"            # int16, int32, float32
      
    audio_processing:
      auto_gain: false           # 自動增益控制
      noise_suppression: false   # 噪音抑制
      echo_cancellation: false   # 回音消除
      
    buffer:
      size: 10                   # 緩衝區數量
      drop_on_overflow: false    # 溢出時是否丟棄
      
    monitoring:
      detect_clipping: true      # 削波檢測
      log_levels: false          # 記錄音量
```

## 支援的音訊後端

| 後端 | 平台 | 延遲 | 穩定性 | 說明 |
|------|------|------|--------|------|
| PyAudio | 全平台 | 中 | 高 | 最廣泛支援 |
| sounddevice | 全平台 | 低 | 高 | 現代化 API |
| WASAPI | Windows | 極低 | 高 | Windows 原生 |
| CoreAudio | macOS | 極低 | 高 | macOS 原生 |
| ALSA | Linux | 低 | 中 | Linux 原生 |

## 效能優化

### 延遲優化
- **小緩衝區**: 256-512 樣本for低延遲
- **回調模式**: 使用回調而非輪詢
- **原生 API**: 使用平台原生音訊 API
- **直接處理**: 避免不必要的複製

### CPU 優化
- **適當採樣率**: 語音用 16kHz 即可
- **單聲道**: 不需要立體聲時用單聲道
- **整數格式**: int16 比 float32 省 CPU

## 注意事項

1. **權限**: 需要麥克風存取權限
2. **獨占模式**: 某些後端可能獨占裝置
3. **緩衝區**: 太小會增加 CPU，太大增加延遲
4. **格式轉換**: 盡量使用原生格式
5. **錯誤處理**: 裝置可能突然斷開

## 錯誤處理

```python
from src.interface.exceptions import (
    CaptureError,
    DeviceNotFoundError,
    PermissionError
)

try:
    mic_capture.start_capture(session_id)
except DeviceNotFoundError as e:
    logger.error(f"找不到音訊裝置: {e}")
    # 使用虛擬裝置或檔案輸入
    use_fallback_input()
except PermissionError as e:
    logger.error(f"無麥克風權限: {e}")
    # 提示使用者授權
    request_microphone_permission()
```

## 裝置管理

```python
# 取得預設裝置
default = mic_capture.get_default_device()
print(f"預設裝置: {default['name']}")

# 尋找特定裝置
usb_mic = mic_capture.find_device("USB Microphone")
if usb_mic:
    config = CaptureConfig(device_id=usb_mic['id'])

# 監聽裝置變化
mic_capture.on_device_change(lambda: refresh_device_list())
```

## 未來擴展

- WebRTC 整合
- 網路音訊流捕捉
- 藍牙裝置支援
- AI 降噪整合
- 多語言語音檢測
- 3D 音訊定位