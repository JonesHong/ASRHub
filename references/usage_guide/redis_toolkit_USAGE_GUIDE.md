# Redis Toolkit 快速使用指南

<div align="center">

```
╔═══════════════════════════════════════════════╗
║   Redis Toolkit - 強大的 Redis 增強工具包     ║
╚═══════════════════════════════════════════════╝
```

*支援自動序列化、媒體處理、批次操作的 Redis 工具包*

[![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/redis-toolkit.svg)](https://pypi.org/project/redis-toolkit/)

</div>

## 📚 目錄

1. [簡介](#簡介)
2. [安裝](#安裝)
3. [快速開始](#快速開始)
4. [基礎使用](#基礎使用)
5. [進階功能](#進階功能)
6. [媒體處理](#媒體處理)
7. [配置管理](#配置管理)
8. [最佳實踐](#最佳實踐)
9. [常見問題](#常見問題)

---

## 🌟 簡介

Redis Toolkit 是一個功能豐富的 Redis 增強工具包，提供了：

- 🎯 **自動序列化**：支援字典、列表、NumPy 陣列等多種資料類型
- 📡 **發布訂閱增強**：簡化的 Pub/Sub API，自動序列化消息
- 🎨 **媒體處理**：內建圖片、音頻、視頻轉換器
- 🚀 **批次操作**：高效的批次讀寫操作
- 🔧 **靈活配置**：豐富的連接和行為配置選項

### 核心理念

1. **簡單優先**：一行代碼即可開始使用
2. **功能強大**：滿足各種 Redis 使用場景
3. **高效可靠**：生產環境下的穩定性能
4. **易於擴展**：支援自定義序列化和轉換器

---

## 📦 安裝

### 基本安裝

```bash
pip install redis-toolkit
```

### 完整安裝（含媒體處理）

```bash
pip install redis-toolkit[all]
```

### 特定功能安裝

```bash
# 圖片處理
pip install redis-toolkit[image]

# 音頻處理
pip install redis-toolkit[audio]

# 視頻處理
pip install redis-toolkit[video]
```

---

## 🚀 快速開始

### 30 秒上手

```python
from redis_toolkit import RedisToolkit

# 創建實例
toolkit = RedisToolkit()

# 基本操作
toolkit.set('user:1', {'name': '張三', 'age': 30})
user = toolkit.get('user:1')
print(user)  # {'name': '張三', 'age': 30}

# 發布訂閱
def message_handler(channel, message):
    print(f"收到消息: {message}")

subscriber = toolkit.subscribe('notifications', handler=message_handler)
toolkit.publish('notifications', {'type': 'alert', 'content': '新消息'})
```

### 一分鐘進階

```python
from redis_toolkit import RedisToolkit, RedisConnectionConfig, RedisOptions

# 自定義配置
config = RedisConnectionConfig(
    host='localhost',
    port=6379,
    password='your_password'
)

options = RedisOptions(
    is_logger_info=True,
    use_connection_pool=True
)

# 創建配置化實例
toolkit = RedisToolkit(config=config, options=options)

# 批次操作
users = {
    'user:2': {'name': '李四', 'age': 25},
    'user:3': {'name': '王五', 'age': 35}
}
toolkit.batch_set(users)

# 批次獲取
result = toolkit.batch_get(['user:1', 'user:2', 'user:3'])
```

---

## 🔧 基礎使用

### 創建 RedisToolkit

#### 方法一：默認配置

```python
from redis_toolkit import RedisToolkit

# 使用默認配置（localhost:6379）
toolkit = RedisToolkit()
```

#### 方法二：自定義配置

```python
from redis_toolkit import RedisToolkit, RedisConnectionConfig, RedisOptions

# 連接配置
config = RedisConnectionConfig(
    host='redis.example.com',
    port=6379,
    password='secure_password',
    db=0,
    ssl=True
)

# 行為配置
options = RedisOptions(
    is_logger_info=True,
    log_level='INFO',
    use_connection_pool=True,
    max_connections=50
)

# 創建實例
toolkit = RedisToolkit(config=config, options=options)
```

### 基本操作

```python
# 設置值（自動序列化）
toolkit.set('config', {
    'debug': True,
    'version': '1.0.0',
    'features': ['auth', 'cache', 'api']
})

# 獲取值（自動反序列化）
config = toolkit.get('config')

# 設置過期時間
toolkit.set('session:123', {'user_id': 456}, expire=3600)  # 1小時

# 檢查存在
exists = toolkit.exists('session:123')

# 刪除鍵
toolkit.delete('temp:data')

# 設置 TTL
toolkit.expire('cache:result', 1800)  # 30分鐘
```

### 批次操作

```python
# 批次設置
data = {
    'product:1': {'name': '手機', 'price': 5999},
    'product:2': {'name': '電腦', 'price': 8999},
    'product:3': {'name': '平板', 'price': 3999}
}
results = toolkit.batch_set(data, expire=86400)  # 24小時

# 批次獲取
keys = ['product:1', 'product:2', 'product:3']
products = toolkit.batch_get(keys)

# 批次刪除
deleted = toolkit.batch_delete(keys)
```

### 發布訂閱

```python
# 訂閱單個頻道
def handler(channel, message):
    print(f"[{channel}] {message}")

subscriber = toolkit.subscribe('news', handler=handler)

# 訂閱多個頻道
subscriber = toolkit.subscribe(
    'news', 'alerts', 'updates',
    handler=handler
)

# 模式訂閱
pattern_sub = toolkit.psubscribe(
    'user:*', 'order:*',
    handler=handler
)

# 發布消息
toolkit.publish('news', {
    'title': '重要通知',
    'content': '系統維護公告',
    'time': '2024-01-15 10:00'
})

# 停止訂閱
subscriber.stop()
```

---

## 🎨 進階功能

### 上下文管理器

```python
# 自動資源清理
with RedisToolkit() as toolkit:
    toolkit.set('temp', 'data')
    value = toolkit.get('temp')
# 連接自動關閉
```

### 序列化控制

```python
import numpy as np

# NumPy 陣列
array = np.array([1, 2, 3, 4, 5])
toolkit.set('matrix', array)
restored = toolkit.get('matrix')

# 自定義對象
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email

user = User('張三', 'zhang@example.com')
toolkit.set('user:obj', user)  # 自動使用 pickle
```

### 原子操作

```python
# 僅當不存在時設置
toolkit.set('lock:resource', 'locked', nx=True, expire=10)

# 僅當存在時設置
toolkit.set('counter', 100, xx=True)

# 保留原有 TTL
toolkit.set('cache:data', new_data, keepttl=True)
```

---

## 🎬 媒體處理 - 聲音、影像、圖片傳遞

Redis Toolkit 提供了強大的媒體處理能力，讓您可以輕鬆地在 Redis 中存儲和傳輸各種媒體格式。所有媒體資料都會自動進行優化編碼，確保高效傳輸。

### 🖼️ 圖片傳遞

#### 基本圖片存儲與讀取

```python
import cv2
from PIL import Image
from redis_toolkit import RedisToolkit

toolkit = RedisToolkit()

# === OpenCV 圖片傳遞 ===
# 讀取高解析度照片
img_cv = cv2.imread('family_photo_4k.jpg')
print(f"原始圖片大小: {img_cv.shape}")  # (2160, 3840, 3)

# 自動壓縮並傳送到 Redis
toolkit.set('photo:family:2024', img_cv)

# 從 Redis 接收並還原圖片
received_photo = toolkit.get('photo:family:2024')
print(f"接收圖片大小: {received_photo.shape}")  # 完整還原

# === PIL 圖片傳遞 ===
# 處理透明背景 PNG
logo = Image.open('company_logo.png')
toolkit.set('assets:logo:main', logo)

# 多個裝置同時讀取
logo_device1 = toolkit.get('assets:logo:main')
logo_device2 = toolkit.get('assets:logo:main')
```

#### 批次圖片傳輸

```python
# 大量圖片批次傳送（例如：相簿同步）
import os
from pathlib import Path

def sync_photo_album(album_path, album_name):
    """同步整個相簿到 Redis"""
    photos = {}
    
    for img_path in Path(album_path).glob('*.jpg'):
        img = cv2.imread(str(img_path))
        key = f'album:{album_name}:{img_path.stem}'
        photos[key] = img
    
    # 批次上傳所有照片
    toolkit.batch_set(photos, expire=86400*30)  # 保存30天
    print(f"已同步 {len(photos)} 張照片到雲端")
    
    return list(photos.keys())

# 使用案例：家庭相簿同步
photo_keys = sync_photo_album('/Users/photos/vacation2024', 'vacation2024')

# 從任何地方讀取相簿
for key in photo_keys[:5]:  # 讀取前5張
    photo = toolkit.get(key)
    cv2.imshow(f'Photo: {key}', photo)
```

### 🎵 音頻傳遞

#### 音頻資料存儲與串流

```python
import numpy as np
import soundfile as sf  # 需要安裝: pip install soundfile

# === 錄音資料傳送 ===
# 模擬錄音（實際應用中從麥克風獲取）
sample_rate = 44100  # CD 音質
duration = 10  # 10秒錄音

# 生成測試音頻（實際場景：從麥克風錄製）
time = np.linspace(0, duration, int(sample_rate * duration))
# 混合多個頻率模擬真實聲音
audio_data = (
    0.3 * np.sin(2 * np.pi * 440 * time) +  # A4 音符
    0.2 * np.sin(2 * np.pi * 554 * time) +  # C#5 音符
    0.1 * np.sin(2 * np.pi * 659 * time)    # E5 音符
)

# 傳送到 Redis（例如：語音留言系統）
toolkit.set('voice:message:user123:001', {
    'audio': audio_data,
    'sample_rate': sample_rate,
    'duration': duration,
    'timestamp': '2024-01-15 14:30:00',
    'sender': 'Alice'
})

# === 接收並播放音頻 ===
message = toolkit.get('voice:message:user123:001')
audio = message['audio']
sr = message['sample_rate']

# 保存為文件（可選）
sf.write('received_message.wav', audio, sr)
print(f"收到來自 {message['sender']} 的 {message['duration']}秒語音留言")
```

#### 實時音頻串流

```python
# 實時音樂串流範例
class AudioStreamer:
    def __init__(self, toolkit, channel_name):
        self.toolkit = toolkit
        self.channel = f'stream:audio:{channel_name}'
        
    def broadcast_audio(self, audio_chunk, chunk_id):
        """廣播音頻片段"""
        self.toolkit.publish(self.channel, {
            'chunk_id': chunk_id,
            'audio_data': audio_chunk,
            'timestamp': time.time()
        })
    
    def stream_live_music(self, audio_file):
        """串流整首歌曲"""
        data, samplerate = sf.read(audio_file)
        chunk_size = samplerate * 1  # 1秒一個片段
        
        for i, start in enumerate(range(0, len(data), chunk_size)):
            chunk = data[start:start + chunk_size]
            self.broadcast_audio(chunk, i)
            time.sleep(1)  # 實時播放

# 廣播端
streamer = AudioStreamer(toolkit, 'radio_pop')
# streamer.stream_live_music('favorite_song.mp3')

# 接收端（多個聽眾）
def audio_receiver(channel, message):
    chunk = message['audio_data']
    chunk_id = message['chunk_id']
    print(f"正在播放片段 {chunk_id}")
    # 這裡可以連接到音頻播放器播放

toolkit.subscribe('stream:audio:radio_pop', handler=audio_receiver)
```

### 🎥 視頻傳遞

#### 視頻幀傳輸

```python
import cv2

# === 視頻幀序列傳送 ===
def video_frame_sender(video_path, stream_name):
    """將視頻分解為幀並傳送"""
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # 每一幀都傳送到 Redis
        toolkit.set(
            f'video:{stream_name}:frame:{frame_count:06d}',
            {
                'frame': frame,
                'frame_number': frame_count,
                'fps': fps,
                'timestamp': time.time()
            },
            expire=300  # 5分鐘後過期
        )
        
        frame_count += 1
        
        # 實時串流模擬
        time.sleep(1/fps)
    
    cap.release()
    
    # 存儲視頻元數據
    toolkit.set(f'video:{stream_name}:metadata', {
        'total_frames': frame_count,
        'fps': fps,
        'duration': frame_count / fps
    })
    
    return frame_count

# 發送端：上傳視頻
# frames_sent = video_frame_sender('presentation.mp4', 'meeting_2024_01_15')
```

#### 視頻接收與重建

```python
def video_frame_receiver(stream_name, output_path=None):
    """接收視頻幀並重建視頻"""
    # 獲取元數據
    metadata = toolkit.get(f'video:{stream_name}:metadata')
    if not metadata:
        print("視頻流不存在")
        return
    
    total_frames = metadata['total_frames']
    fps = metadata['fps']
    
    # 獲取第一幀以確定視頻尺寸
    first_frame = toolkit.get(f'video:{stream_name}:frame:000000')
    if not first_frame:
        print("無法獲取視頻幀")
        return
    
    height, width = first_frame['frame'].shape[:2]
    
    # 準備視頻寫入器
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    # 逐幀讀取並顯示/保存
    for i in range(total_frames):
        frame_data = toolkit.get(f'video:{stream_name}:frame:{i:06d}')
        if frame_data:
            frame = frame_data['frame']
            
            # 顯示視頻（可選）
            cv2.imshow(f'Video: {stream_name}', frame)
            if cv2.waitKey(int(1000/fps)) & 0xFF == ord('q'):
                break
                
            # 寫入文件（可選）
            if output_path:
                out.write(frame)
    
    cv2.destroyAllWindows()
    if output_path:
        out.release()
        print(f"視頻已保存至: {output_path}")

# 接收端：下載並播放視頻
# video_frame_receiver('meeting_2024_01_15', 'downloaded_meeting.mp4')
```

### 🔄 綜合應用：多媒體聊天室

```python
class MultimediaChatRoom:
    """支援文字、圖片、音頻、視頻的聊天室"""
    
    def __init__(self, toolkit, room_id):
        self.toolkit = toolkit
        self.room_id = room_id
        self.channel = f'chat:room:{room_id}'
    
    def send_text(self, user, text):
        """發送文字消息"""
        self.toolkit.publish(self.channel, {
            'type': 'text',
            'user': user,
            'content': text,
            'timestamp': time.time()
        })
    
    def send_image(self, user, image_path):
        """發送圖片"""
        img = cv2.imread(image_path)
        # 壓縮大圖片
        if img.shape[0] > 1080 or img.shape[1] > 1920:
            img = cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_AREA)
        
        self.toolkit.publish(self.channel, {
            'type': 'image',
            'user': user,
            'content': img,
            'timestamp': time.time()
        })
    
    def send_voice(self, user, audio_data, sample_rate):
        """發送語音消息"""
        self.toolkit.publish(self.channel, {
            'type': 'voice',
            'user': user,
            'content': {
                'audio': audio_data,
                'sample_rate': sample_rate,
                'duration': len(audio_data) / sample_rate
            },
            'timestamp': time.time()
        })
    
    def send_video_clip(self, user, video_path, max_duration=30):
        """發送短視頻（最長30秒）"""
        cap = cv2.VideoCapture(video_path)
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        frames = []
        
        max_frames = fps * max_duration
        frame_count = 0
        
        while cap.isOpened() and frame_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 降低解析度以減少傳輸大小
            frame = cv2.resize(frame, (640, 480))
            frames.append(frame)
            frame_count += 1
        
        cap.release()
        
        self.toolkit.publish(self.channel, {
            'type': 'video',
            'user': user,
            'content': {
                'frames': frames,
                'fps': fps,
                'duration': len(frames) / fps
            },
            'timestamp': time.time()
        })

# 使用範例
chat = MultimediaChatRoom(toolkit, 'family_chat')

# 消息處理器
def message_handler(channel, message):
    msg_type = message['type']
    user = message['user']
    
    if msg_type == 'text':
        print(f"[{user}]: {message['content']}")
    
    elif msg_type == 'image':
        print(f"[{user}] 發送了一張圖片")
        cv2.imshow(f"Image from {user}", message['content'])
        cv2.waitKey(3000)  # 顯示3秒
        cv2.destroyAllWindows()
    
    elif msg_type == 'voice':
        audio_info = message['content']
        print(f"[{user}] 發送了 {audio_info['duration']:.1f}秒 語音")
        # 這裡可以播放音頻
    
    elif msg_type == 'video':
        video_info = message['content']
        print(f"[{user}] 發送了 {video_info['duration']:.1f}秒 視頻")
        # 播放視頻幀

# 加入聊天室
toolkit.subscribe('chat:room:family_chat', handler=message_handler)

# 發送各種消息
chat.send_text('Alice', '大家好！')
chat.send_image('Bob', 'vacation_photo.jpg')
# chat.send_voice('Carol', voice_data, 44100)
# chat.send_video_clip('David', 'funny_cat.mp4')
```

### 🎨 進階媒體處理技巧

#### 自適應品質調整

```python
from redis_toolkit.converters import encode_image, decode_image

def adaptive_image_storage(toolkit, key, image, network_quality='auto'):
    """根據網路品質自動調整圖片壓縮率"""
    quality_presets = {
        'high': 95,      # 高品質，適合 WiFi
        'medium': 85,    # 中等品質，適合 4G
        'low': 70,       # 低品質，適合 3G
        'auto': None     # 自動判斷
    }
    
    if network_quality == 'auto':
        # 這裡可以實現網路品質檢測邏輯
        quality = 85
    else:
        quality = quality_presets.get(network_quality, 85)
    
    # 使用指定品質編碼
    encoded = encode_image(image, format='.jpg', quality=quality)
    
    # 存儲編碼後的圖片和元數據
    toolkit.set(key, {
        'image_data': encoded,
        'quality': quality,
        'original_shape': image.shape,
        'encoding': 'jpeg'
    })
    
    return len(encoded)  # 返回壓縮後大小

# 使用範例
img = cv2.imread('high_res_photo.jpg')
size = adaptive_image_storage(toolkit, 'photo:compressed', img, 'medium')
print(f"圖片已壓縮至 {size/1024:.1f} KB")
```

### 📋 媒體處理最佳實踐

1. **圖片優化**
   - 大圖片自動調整尺寸
   - 使用適當的壓縮格式（JPEG for photos, PNG for graphics）
   - 考慮縮圖生成

2. **音頻優化**
   - 適當的採樣率（語音 16kHz，音樂 44.1kHz）
   - 使用音頻壓縮格式儲存
   - 分段處理長音頻

3. **視頻優化**
   - 限制視頻長度和解析度
   - 使用關鍵幀壓縮
   - 考慮串流而非整體傳輸

4. **記憶體管理**
   - 設置適當的過期時間
   - 定期清理過期媒體
   - 監控 Redis 記憶體使用

---

## ⚙️ 配置管理

### 連接配置

```python
from redis_toolkit import RedisConnectionConfig

# 基本連接
config = RedisConnectionConfig(
    host='localhost',
    port=6379,
    password='password',
    db=0
)

# SSL 連接
secure_config = RedisConnectionConfig(
    host='redis.example.com',
    port=6380,
    ssl=True,
    ssl_cert_reqs='required',
    ssl_ca_certs='/path/to/ca.pem'
)

# 高級選項
advanced_config = RedisConnectionConfig(
    host='redis-cluster',
    port=6379,
    socket_keepalive=True,
    socket_timeout=5,
    connection_timeout=10,
    retry_on_timeout=True,
    health_check_interval=30
)
```

### 行為配置

```python
from redis_toolkit import RedisOptions

# 開發環境
dev_options = RedisOptions(
    is_logger_info=True,
    log_level='DEBUG',
    enable_validation=True,
    max_value_size=10*1024*1024  # 10MB
)

# 生產環境
prod_options = RedisOptions(
    is_logger_info=True,
    log_level='WARNING',
    use_connection_pool=True,
    max_connections=100,
    enable_validation=True,
    subscriber_retry_delay=5.0
)
```

### 連接池管理

```python
from redis_toolkit import pool_manager

# 配置全局連接池
pool_manager.configure_pool(
    'default',
    host='localhost',
    port=6379,
    max_connections=50
)

# 多個實例共享連接池
toolkit1 = RedisToolkit()
toolkit2 = RedisToolkit()
```

---

## 🏆 最佳實踐

### 1. 錯誤處理

```python
from redis_toolkit.exceptions import (
    RedisToolkitError,
    SerializationError,
    ValidationError
)

try:
    toolkit.set('key', complex_object)
except SerializationError as e:
    logger.error(f"序列化失敗: {e}")
except ValidationError as e:
    logger.error(f"驗證失敗: {e}")
except RedisToolkitError as e:
    logger.error(f"Redis 錯誤: {e}")
```

### 2. 性能優化

```python
# 使用連接池
toolkit = RedisToolkit(options=RedisOptions(
    use_connection_pool=True,
    max_connections=200
))

# 批次操作替代循環
# 不好的做法
for i in range(1000):
    toolkit.set(f'key:{i}', f'value:{i}')

# 好的做法
data = {f'key:{i}': f'value:{i}' for i in range(1000)}
toolkit.batch_set(data)
```

### 3. 資源管理

```python
# 使用上下文管理器
with RedisToolkit() as toolkit:
    # 自動處理連接和清理
    toolkit.set('data', value)

# 或手動清理
toolkit = RedisToolkit()
try:
    # 使用 toolkit
    pass
finally:
    toolkit.cleanup()
```

---

## ❓ 常見問題

### Q1: 如何處理大型數據？

**A:** 對於大型數據，建議：
- 設置合適的 `max_value_size` 限制
- 考慮分片存儲
- 使用壓縮（即將支援）

### Q2: 發布訂閱斷線重連？

**A:** RedisToolkit 內建自動重連機制：
```python
options = RedisOptions(
    subscriber_retry_delay=5.0,  # 5秒重試
    subscriber_stop_timeout=5.0
)
```

### Q3: 如何自定義序列化？

**A:** 可以通過繼承和重寫方法實現：
```python
from redis_toolkit import RedisToolkit

class CustomToolkit(RedisToolkit):
    def _serialize(self, value):
        # 自定義序列化邏輯
        return custom_serialize(value)
    
    def _deserialize(self, data):
        # 自定義反序列化邏輯
        return custom_deserialize(data)
```

### Q4: 支援 Redis 集群嗎？

**A:** 目前主要支援單節點和主從模式。集群支援在規劃中。

### Q5: 媒體處理性能如何？

**A:** 媒體處理性能取決於：
- 使用適當的圖片格式和壓縮率
- 合理的音頻採樣率
- 考慮使用專門的媒體存儲服務

---

## 🎯 總結

Redis Toolkit 提供了一個功能完整、易於使用的 Redis 增強解決方案。

### 核心優勢

- ✅ **零配置啟動**：導入即用，無需複雜設置
- ✅ **強大功能**：自動序列化、批次操作、媒體處理
- ✅ **生產就緒**：連接池、錯誤處理、日誌記錄
- ✅ **靈活擴展**：豐富的配置選項和擴展接口
- ✅ **類型安全**：完整的類型提示支援

### 下一步

- 查看[完整文檔](https://joneshong.github.io/redis-toolkit/)
- 瀏覽[API 參考](https://joneshong.github.io/redis-toolkit/api/)
- 參考[使用範例](https://joneshong.github.io/redis-toolkit/examples/)

---

<div align="center">

**Happy Coding! 🎉**

[GitHub](https://github.com/JonesHong/redis-toolkit) | [PyPI](https://pypi.org/project/redis-toolkit/) | [文檔](https://joneshong.github.io/redis-toolkit/) | [問題回報](https://github.com/JonesHong/redis-toolkit/issues)

</div>