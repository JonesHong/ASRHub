"""
WebSocket 路由定義
"""

# WebSocket 訊息類型路由 - 保持簡潔，類似 HTTP SSE
routes = {
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
    
    # === 音訊處理事件 ===
    "AUDIO": "audio",                              # 音訊資料（二進制）
    "AUDIO_CHUNK": "audio/chunk",                 # 音訊分塊
    "AUDIO_CONFIG": "audio/config",               # 音訊配置
    "AUDIO_RECEIVED": "audio/received",           # 音訊接收確認
    "AUDIO_METADATA": "audio/metadata",           # 音訊元資料
    
    # === 轉譯結果事件 ===
    "TRANSCRIPT": "transcript",                   # 最終轉譯結果
    "TRANSCRIPT_PARTIAL": "transcript/partial",   # 部分轉譯結果
    
    # === 狀態與進度事件 ===
    "STATUS": "status",                           # 狀態更新
    "PROGRESS": "progress",                       # 進度更新
    "BACKPRESSURE": "backpressure",              # 背壓通知
    
    # === 系統事件 ===
    "EVENT": "event",                             # 通用事件通知
    "ERROR": "error",                             # 錯誤訊息
    "WELCOME": "welcome",                         # 歡迎訊息
    "PING": "ping",                               # 心跳 ping
    "PONG": "pong",                               # 心跳 pong
    
}