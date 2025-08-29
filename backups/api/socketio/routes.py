"""
Socket.IO 事件路由定義
"""

# Socket.IO 事件路由 - 遵循 KISS 原則，參考 WebSocket 設計
routes = {
    # === 連線管理 ===
    "CONNECT": "connect",
    "DISCONNECT": "disconnect",
    "WELCOME": "welcome",
    "PING": "ping",
    "PONG": "pong",
    
    # === Session 管理事件 ===
    "SESSION_CREATE": "session/create",           # 創建會話
    "SESSION_START": "session/start",             # 開始監聽
    "SESSION_STOP": "session/stop",               # 停止監聽
    "SESSION_DESTROY": "session/destroy",         # 銷毀會話
    
    # === 錄音管理事件 ===
    "RECORDING_START": "recording/start",         # 開始錄音
    "RECORDING_END": "recording/end",             # 結束錄音
    
    # === 上傳管理事件 ===
    "CHUNK_UPLOAD_START": "chunk/upload/start",   # 開始分塊上傳
    "CHUNK_UPLOAD_DONE": "chunk/upload/done",     # 完成分塊上傳
    "FILE_UPLOAD": "file/upload",                 # 檔案上傳
    "FILE_UPLOAD_DONE": "file/upload/done",       # 檔案上傳完成
    
    # === 音訊處理 ===
    "AUDIO_CHUNK": "audio/chunk",                 # 音訊分塊
    "AUDIO_RECEIVED": "audio/received",           # 音訊接收確認
    "BACKPRESSURE": "backpressure",              # 背壓通知
    
    # === Session 訂閱 ===
    "SUBSCRIBE": "subscribe",
    "UNSUBSCRIBE": "unsubscribe",
    "SUBSCRIBED": "subscribed",
    "UNSUBSCRIBED": "unsubscribed",
    
    # === 狀態與進度 ===
    "STATUS_UPDATE": "status/update",             # 狀態更新
    "PROGRESS": "progress",                       # 進度更新
    
    # === 轉譯結果 ===
    "TRANSCRIPT_PARTIAL": "transcript/partial",   # 部分轉譯結果
    "TRANSCRIPT": "transcript",       # 最終轉譯結果
    
    # === 錯誤處理 ===
    "ERROR": "error",
    
}