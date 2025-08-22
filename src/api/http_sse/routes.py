"""
HTTP SSE 路由定義
"""

routes = {
    # 基礎路由
    "EVENTS": "events",          # GET 事件流
    "HEALTH": "health",          # GET 健康檢查
    "SESSION": "session",        # GET/POST/DELETE 會話管理
    "TRANSCRIBE": "transcribe",  # GET 串流轉錄
    "TRANSCRIBE_V1": "v1/transcribe",  # POST 一次性轉譯
    
    # Session 管理路由
    "SESSION_START_LISTENING": "session/start-listening",  # POST 開始監聽
    "SESSION_STATUS": "session/status",                    # GET 獲取狀態
    "SESSION_WAKE": "session/wake",                        # POST 喚醒 session
    "SESSION_SLEEP": "session/sleep",                      # POST 休眠 session
    "SESSION_WAKE_TIMEOUT": "session/wake/timeout",        # PUT 設定喚醒超時
    "SESSION_WAKE_STATUS": "session/wake/status",          # GET 獲取喚醒狀態
    "SESSION_BUSY_START": "session/busy/start",            # POST 進入忙碌模式
    "SESSION_BUSY_END": "session/busy/end",                # POST 結束忙碌模式
    
    # 上傳管理路由
    "UPLOAD": "audio",                    # POST 上傳音頻
    "UPLOAD_FILE": "upload/file",         # POST 開始檔案上傳
    "UPLOAD_FILE_DONE": "upload/file-done",  # POST 完成檔案上傳
    "UPLOAD_CHUNK_START": "upload/chunk-start",  # POST 開始分塊上傳
    "UPLOAD_CHUNK_DONE": "upload/chunk-done",    # POST 完成分塊上傳
    
    # 錄音管理路由
    "RECORDING_START": "recording/start",  # POST 開始錄音
    "RECORDING_END": "recording/end",      # POST 結束錄音
    
    # 轉譯路由
    "TRANSCRIPTION_BEGIN": "transcription/begin",  # POST 開始轉譯
    "AUDIO_CHUNK": "audio/chunk",                  # POST 音訊分塊
}
