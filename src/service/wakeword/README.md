# WakeWord Service (喚醒詞檢測服務)

## 概述
喚醒詞檢測服務使用 OpenWakeWord 模型，提供高效準確的關鍵詞檢測功能。支援自定義喚醒詞、多詞同時檢測、連續檢測模式等功能，適用於智慧助理、語音控制等場景。

## 核心功能

### 喚醒詞檢測
- **OpenWakeWord 模型** - 開源、輕量、高準確率
- **多詞檢測** - 同時監聽多個喚醒詞
- **自定義模型** - 支援訓練和載入自定義喚醒詞
- **連續檢測** - 支援連續觸發或單次觸發模式

### 檢測管理
- **Session 隔離** - 每個 session 獨立管理檢測狀態
- **冷卻期控制** - 防止重複觸發
- **去抖動機制** - 減少誤觸發
- **信心度閾值** - 可調整的檢測敏感度

## 使用方式

### 基本初始化
```python
from src.service.wakeword import wakeword_service
from src.interface.wakeword import WakewordConfig

# 使用預設配置
wakeword_service.initialize()

# 自定義配置
config = WakewordConfig(
    model_path="models/openwakeword",      # 模型目錄
    threshold=0.5,                         # 檢測閾值
    cooldown_seconds=2.0,                  # 冷卻時間
    debounce_time=2.0,                     # 去抖動時間
    continuous_detection=True,             # 連續檢測模式
    sample_rate=16000,                     # 採樣率
    chunk_size=1280                        # 處理塊大小
)
wakeword_service.initialize(config)
```

### 開始檢測
```python
# 定義檢測回調
def on_wakeword_detected(session_id: str, detection):
    print(f"🎯 檢測到喚醒詞: {detection.keyword}")
    print(f"信心度: {detection.confidence:.2f}")
    print(f"時間戳: {detection.timestamp}")
    
    # 執行喚醒後動作
    activate_assistant(session_id)

# 開始監控（使用預設喚醒詞）
session_id = "user_123"
wakeword_service.start_monitoring(
    session_id,
    on_detected=on_wakeword_detected
)

# 監控特定關鍵詞
keywords = ["hey_assistant", "ok_computer", "hello_robot"]
wakeword_service.start_monitoring(
    session_id,
    keywords=keywords,
    on_detected=on_wakeword_detected
)
```

### 處理音訊
```python
import numpy as np

# 串流處理（保持 session 狀態）
while listening:
    audio_chunk = get_audio_chunk()  # 獲取音訊
    
    detection = wakeword_service.process_stream(
        session_id,
        audio_chunk,
        sample_rate=16000
    )
    
    if detection:
        print(f"檢測到: {detection.keyword} ({detection.confidence:.2f})")

# 單次處理（無狀態）
audio_data = np.array([...], dtype=np.float32)
detection = wakeword_service.process_chunk(audio_data)
if detection:
    handle_wakeword(detection)
```

### 狀態管理
```python
# 檢查監控狀態
if wakeword_service.is_monitoring(session_id):
    print("正在監聽喚醒詞")

# 獲取監控資訊
info = wakeword_service.get_monitoring_info(session_id)
if info:
    print(f"監聽詞彙: {info['keywords']}")
    print(f"檢測次數: {info['detection_count']}")
    print(f"上次檢測: {info['last_detection']}")

# 重置狀態（清除冷卻期等）
wakeword_service.reset_session(session_id)

# 停止監控
wakeword_service.stop_monitoring(session_id)
```

## 實際應用範例

### 智慧助理喚醒
```python
from src.service.wakeword import wakeword_service
from src.service.vad import vad_service
from enum import Enum

class AssistantState(Enum):
    SLEEPING = "sleeping"
    LISTENING = "listening"
    PROCESSING = "processing"

class SmartAssistant:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = AssistantState.SLEEPING
        
    def start(self):
        """啟動智慧助理"""
        # 設定預設檢測 hook
        wakeword_service.set_default_hook(self.on_wakeword)
        
        # 開始監聽喚醒詞
        wakeword_service.start_monitoring(
            self.session_id,
            keywords=["hey_assistant", "ok_jarvis"]
        )
        
        logger.info("助理已啟動，等待喚醒...")
    
    def on_wakeword(self, session_id: str, detection):
        """喚醒詞檢測到"""
        if self.state == AssistantState.SLEEPING:
            self.state = AssistantState.LISTENING
            
            # 播放喚醒音效
            play_activation_sound()
            
            # 開始 VAD 監聽使用者指令
            vad_service.start_monitoring(
                session_id,
                on_speech_end=self.on_command_complete
            )
            
            # 設定超時（10秒無語音則返回睡眠）
            timer.start_countdown(
                f"wake_{session_id}",
                callback=self.go_to_sleep,
                duration=10
            )
            
            logger.info(f"助理已喚醒！({detection.keyword})")
    
    def on_command_complete(self, session_id: str):
        """使用者指令結束"""
        self.state = AssistantState.PROCESSING
        
        # 停止超時計時器
        timer.stop_countdown(f"wake_{session_id}")
        
        # 處理指令...
        process_user_command(session_id)
        
        # 返回睡眠狀態
        self.go_to_sleep(session_id)
    
    def go_to_sleep(self, session_id: str):
        """返回睡眠狀態"""
        self.state = AssistantState.SLEEPING
        vad_service.stop_monitoring(session_id)
        logger.info("助理返回睡眠狀態")
```

### 多喚醒詞場景控制
```python
class MultiWakewordController:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.keyword_actions = {
            "lights_on": self.turn_on_lights,
            "lights_off": self.turn_off_lights,
            "play_music": self.play_music,
            "stop_music": self.stop_music,
            "volume_up": self.increase_volume,
            "volume_down": self.decrease_volume
        }
        
    def start(self):
        """開始多喚醒詞監控"""
        keywords = list(self.keyword_actions.keys())
        
        wakeword_service.start_monitoring(
            self.session_id,
            keywords=keywords,
            on_detected=self.on_keyword_detected
        )
        
        logger.info(f"監聽 {len(keywords)} 個控制詞")
    
    def on_keyword_detected(self, session_id: str, detection):
        """執行對應動作"""
        keyword = detection.keyword
        
        if keyword in self.keyword_actions:
            action = self.keyword_actions[keyword]
            action()
            logger.info(f"執行動作: {keyword}")
        
        # 如果是連續檢測模式，會自動繼續監聽
        # 如果不是，需要重新開始監控
        if not wakeword_service.get_config().continuous_detection:
            self.start()  # 重新開始監聽
    
    def turn_on_lights(self):
        print("💡 開燈")
        
    def turn_off_lights(self):
        print("🌙 關燈")
        
    def play_music(self):
        print("🎵 播放音樂")
        
    def stop_music(self):
        print("⏹️ 停止音樂")
        
    def increase_volume(self):
        print("🔊 音量增加")
        
    def decrease_volume(self):
        print("🔉 音量減少")
```

### 自定義喚醒詞訓練
```python
# 載入自定義模型
def load_custom_wakeword(model_file: str, keyword_name: str):
    """載入自定義喚醒詞模型"""
    config = WakewordConfig(
        model_path=model_file,
        threshold=0.6  # 自定義模型可能需要調整閾值
    )
    
    wakeword_service.update_config(config)
    
    # 監聽自定義喚醒詞
    wakeword_service.start_monitoring(
        "custom_session",
        keywords=[keyword_name],
        on_detected=lambda s, d: print(f"自定義喚醒詞觸發: {d.keyword}")
    )

# HuggingFace 模型載入
def load_from_huggingface():
    """從 HuggingFace 載入模型"""
    config = WakewordConfig(
        hf_repo_id="david-uhlig/openwakeword",
        hf_filename="hey_jarvis_v0.1.tflite",
        hf_token="your_token_here"  # 如果需要
    )
    
    wakeword_service.initialize(config)
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  wakeword:
    enabled: true
    model_path: "models/openwakeword"      # 模型目錄
    threshold: 0.5                         # 檢測閾值 (0.0-1.0)
    cooldown_seconds: 2.0                  # 冷卻期（秒）
    debounce_time: 2.0                     # 去抖動時間（秒）
    continuous_detection: true             # 連續檢測模式
    sample_rate: 16000                     # 採樣率
    chunk_size: 1280                       # 處理塊大小
    max_buffer_size: 100                   # 最大緩衝區大小
    use_gpu: false                         # 是否使用 GPU
    
    # HuggingFace 配置（可選）
    hf_repo_id: null
    hf_filename: null
    hf_token: null
```

## 效能優化

### 閾值調整
- **0.3-0.4**: 高敏感度，易觸發，適合安靜環境
- **0.5-0.6**: 平衡設定，適合一般環境（預設）
- **0.7-0.8**: 低敏感度，減少誤觸發，適合嘈雜環境

### 處理優化
- **Chunk Size**: 1280 樣本（80ms @ 16kHz）提供良好平衡
- **Buffer Size**: 控制在 100 以內避免延遲累積
- **冷卻期**: 2 秒防止重複觸發
- **去抖動**: 2 秒內多次檢測視為一次

### 資源使用
- **CPU**: 單核約 10-15% @ 16kHz
- **記憶體**: 每個模型約 5-20MB
- **延遲**: < 100ms 檢測延遲
- **GPU**: 可選，但 CPU 通常已足夠

## 注意事項

1. **模型格式**: 支援 TFLite、ONNX 格式
2. **音訊要求**: 16kHz 單聲道效果最佳
3. **連續檢測**: 開啟後會持續監聽，適合長時間運行
4. **多詞檢測**: 同時監聽多個詞會略微增加 CPU 使用
5. **自定義模型**: 需要足夠的訓練數據（建議 > 100 樣本）

## 錯誤處理

```python
from src.interface.exceptions import (
    WakewordInitializationError,
    WakewordModelError,
    WakewordSessionError
)

try:
    wakeword_service.initialize()
except WakewordInitializationError as e:
    logger.error(f"初始化失敗: {e}")
    # 嘗試使用備用模型
    use_fallback_model()

try:
    detection = wakeword_service.process_chunk(audio)
except WakewordModelError as e:
    logger.error(f"模型推論失敗: {e}")
```

## 支援的預設喚醒詞

- hey_assistant
- ok_computer
- hello_robot
- alexa
- hey_siri
- ok_google
- 自定義訓練詞彙

## 未來擴展

- 支援更多預訓練模型
- 線上學習和個性化
- 多語言喚醒詞
- 聲紋識別整合
- 低功耗模式
- 邊緣設備優化