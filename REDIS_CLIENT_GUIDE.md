# Redis 客戶端實作指南

## 連接設定

```python
import redis
import json
import base64
import time
import uuid

# 連接 Redis
r = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)
pubsub = r.pubsub()
```

## 事件執行順序

### 1. 創建 Session

```python
# 客戶端使用 request_id，伺服器會回傳分配的 session_id
request_id = str(uuid.uuid4())  # 客戶端產生的請求 ID

create_payload = {
    "request_id": request_id,  # 客戶端的請求 ID
    "strategy": "non_streaming"  
}
r.publish("request:create:session", json.dumps(create_payload))

# 訂閱回應頻道以取得 session_id
pubsub.subscribe([
    "response:session:created",  # 會回傳實際的 session_id
    "response:transcribe:done",
    "response:error",
    "response:play:asr:feedback"
])

# 等待並取得 session_id
session_id = None
for message in pubsub.listen():
    if message['type'] == 'message':
        if message['channel'] == 'response:session:created':
            data = json.loads(message['data'])
            if data.get('request_id') == request_id:
                session_id = data['session_id']  # 伺服器分配的 session_id
                print(f"取得 session_id: {session_id}")
                break
```

### 2. 開始監聽

```python
# 使用伺服器分配的 session_id
# 音訊格式根據實際裝置設定，伺服器會自動轉換
listen_payload = {
    "session_id": session_id,  # 使用伺服器分配的 ID
    "sample_rate": 48000,  # 根據實際裝置，如：8000, 16000, 44100, 48000
    "channels": 2,         # 1=單聲道, 2=立體聲
    "format": "int16"      # 音訊格式：int16, int32, float32
}
r.publish("request:start:listening", json.dumps(listen_payload))
```

### 3. 發送音訊資料

```python
# 發送音訊塊 (base64 編碼)
audio_payload = {
    "session_id": session_id,  # 使用伺服器分配的 ID
    "audio_data": base64.b64encode(audio_bytes).decode('utf-8')
}
r.publish("request:emit:audio:chunk", json.dumps(audio_payload))
```

### 4. 接收轉譯結果與回饋音效

```python
# 監聽回應
for message in pubsub.listen():
    if message['type'] == 'message':
        data = json.loads(message['data'])
        
        if message['channel'] == 'response:transcribe:done':
            # 轉譯結果格式
            # {
            #     "session_id": "xxx",
            #     "text": "轉譯的文字",
            #     "language": "zh",
            #     "duration": 5.5,
            #     "timestamp": "2024-08-30T..."
            # }
            if data['session_id'] == session_id:
                print(f"轉譯結果: {data['text']}")
        
        elif message['channel'] == 'response:play:asr:feedback':
            # ASR 回饋音效指令（用於 UI 互動體驗）
            # {
            #     "session_id": "xxx",
            #     "command": "start",  # 或 "stop"
            #     "timestamp": "2024-08-30T..."
            # }
            # command 說明：
            # - "start": 開始播放提示音（如：開始錄音的嗶聲）
            # - "stop": 停止播放提示音（如：錄音結束的嗶聲）
            if data['session_id'] == session_id:
                if data['command'] == 'start':
                    print("🔔 播放開始錄音提示音")
                    # 客戶端可在此播放提示音效
                elif data['command'] == 'stop':
                    print("🔕 播放結束錄音提示音")
                    # 客戶端可在此播放結束音效
            
        elif message['channel'] == 'response:error':
            # 錯誤格式
            # {
            #     "session_id": "xxx",
            #     "error_code": "ERR_XXX",
            #     "error_message": "錯誤描述",
            #     "timestamp": "2024-08-30T..."
            # }
            if data.get('session_id') == session_id:
                print(f"錯誤: {data['error_message']}")
```

## 資料格式規範

### 音訊資料支援

* **格式**：int16, int32, float32
* **取樣率**：任意（常見：8000, 16000, 22050, 44100, 48000 Hz）
* **聲道**：單聲道或立體聲
* **編碼**：Base64 字串傳輸
* **說明**：伺服器會根據 `start_listening` 提供的參數自動轉換音訊格式

### 重要概念

* **request\_id**：客戶端產生，用於追蹤請求
* **session\_id**：伺服器分配，用於後續所有操作
* **ASR Feedback**：提供 UI 互動音效指令，提升使用者體驗
* 一個 session 可處理多個音訊轉譯

## 注意事項

1. **Session 管理**

   * request\_id 由客戶端產生，僅用於請求追蹤
   * session\_id 由伺服器分配，必須等待回應取得
   * 所有後續操作都使用 session\_id

2. **音訊格式彈性**

   * 支援多種取樣率（8kHz \~ 48kHz）
   * 支援單聲道或立體聲
   * 伺服器會自動進行格式轉換
   * 使用 Base64 編碼傳輸二進位資料
   * 範例：可直接使用裝置原生音訊格式，伺服器會自動轉換

3. **ASR Feedback 音效**

   * 伺服器會發送音效播放指令
   * "start" 指令：建議播放開始錄音提示音
   * "stop" 指令：建議播放結束錄音提示音
   * 有助於提升使用者互動體驗
