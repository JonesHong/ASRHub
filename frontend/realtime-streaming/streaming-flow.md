# 實時音訊串流流程說明

## 完整事件流程

### 1. 前端開始音訊串流
當用戶點擊麥克風按鈕開始串流時：

```javascript
// 1. AudioStreamManager 初始化並開始串流
audioStreamManager.startStreaming()
  ↓
// 2. 發送 start_listening 事件到後端，包含音訊格式
{
  type: '[Session] Start Listening',
  payload: {
    session_id: 'session-xxx',
    audio_format: {
      sample_rate: 16000,
      channels: 1,
      encoding: 'pcm_f32le',
      bits_per_sample: 32,
      format: 'raw',
      buffer_size: 4096
    },
    protocol: 'websocket',
    timestamp: 1234567890
  }
}
```

### 2. 後端處理 start_listening 事件
後端收到事件後的處理流程：

```python
# 1. SessionEffects 處理 start_listening action
# 2. 創建音訊佇列管理器 (AudioQueueManager)
# 3. 啟動 OpenWakeWord operator
# 4. OpenWakeWord 開始從 audio_queue_manager 持續取得音訊
# 5. 等待喚醒詞觸發或手動喚醒
```

### 3. 音訊資料串流
前端持續發送音訊資料：

```javascript
// 每個音訊塊都會被發送
handleAudioData(audioData) {
  // 通過 WebSocket 發送音訊塊
  protocolAdapter.sendAudioChunk(
    sessionId,
    audioData.buffer,
    chunkId
  )
}
```

後端接收並處理：

```python
# 音訊資料流向：
WebSocket → AudioQueueManager → OpenWakeWord → VAD → Recording
```

### 4. 喚醒詞觸發後的流程

```
喚醒詞檢測到 → 開始倒數計時 → VAD 控制暫停/恢復 → 錄音完成 → ASR 處理
```

## 關鍵組件說明

### 前端組件
- **AudioStreamManager**: 管理麥克風音訊捕獲和串流
- **WakeWordManager**: 處理喚醒詞檢測結果
- **VADDisplay**: 顯示語音活動狀態
- **CountdownTimer**: 錄音倒數計時器（VAD 控制）
- **ASRResultDisplay**: 顯示轉錄結果

### 後端組件
- **AudioQueueManager**: 管理音訊資料佇列
- **OpenWakeWord Operator**: 喚醒詞檢測
- **VAD Operator**: 語音活動檢測
- **Recording Operator**: 後端錄音
- **ASR Provider**: 語音轉文字處理

## WebSocket 訊息格式

### 前端 → 後端

1. **Action 訊息**（PyStoreX 格式）
```json
{
  "type": "action",
  "action": {
    "type": "[Session] Start Listening",
    "payload": { ... }
  }
}
```

2. **音訊塊訊息**
```json
{
  "type": "audio_chunk",
  "session_id": "session-xxx",
  "audio": "base64_encoded_audio",
  "chunk_id": 123
}
```

### 後端 → 前端

1. **狀態更新**
```json
{
  "type": "status_update",
  "session_id": "session-xxx",
  "state": "LISTENING",
  "details": { ... }
}
```

2. **ASR 結果**
```json
{
  "type": "transcript_final",
  "text": "辨識結果文字",
  "confidence": 0.95,
  "timestamp": "2025-08-20T12:00:00Z"
}
```

## 測試步驟

1. 啟動後端服務：
```bash
python main.py
```

2. 開啟前端頁面：
```
http://localhost:8082/realtime-streaming/
```

3. 測試流程：
   - 選擇 WebSocket 協議
   - 點擊「連接」按鈕
   - 點擊麥克風按鈕開始串流
   - 說出喚醒詞或點擊手動喚醒
   - 開始說話（VAD 會自動暫停計時器）
   - 停止說話後計時器繼續
   - 計時結束後查看 ASR 結果

## 錯誤處理

- WebSocket 連接失敗：檢查後端服務是否運行
- 麥克風權限被拒：確保瀏覽器允許麥克風訪問
- 音訊格式不匹配：檢查前後端的採樣率設定

## 配置說明

前端配置（app.js）：
```javascript
config: {
  audio: {
    sampleRate: 16000,    // 採樣率
    bufferSize: 4096,     // 緩衝區大小
    channels: 1           // 聲道數
  }
}
```

後端配置（config.yaml）：
```yaml
audio:
  sample_rate: 16000
  channels: 1
  format: pcm_f32le
```