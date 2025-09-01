"""HTTP SSE API 端點定義"""

from enum import Enum
from src.interface.action import InputAction, OutputAction


class SSEEndpoints:
    """SSE 端點定義 - 基於 Action 定義保持協議一致性"""
    
    # === API 路徑前綴 ===
    API_PREFIX = "/api/v1"
    
    # === 輸入端點 (基於 InputAction) - 與 Redis 相同功能 ===
    # 主要控制：create_session, start_listening, emit_audio_chunk
    CREATE_SESSION = f"{API_PREFIX}/{InputAction.CREATE_SESSION}"      # POST - 建立新 session
    START_LISTENING = f"{API_PREFIX}/{InputAction.START_LISTENING}"    # POST - 開始監聽
    EMIT_AUDIO_CHUNK = f"{API_PREFIX}/{InputAction.EMIT_AUDIO_CHUNK}"  # POST - 發送音訊
    
    # Wake control endpoints
    WAKE_ACTIVATE = f"{API_PREFIX}/{InputAction.WAKE_ACTIVATED}"       # POST - 啟用喚醒
    WAKE_DEACTIVATE = f"{API_PREFIX}/{InputAction.WAKE_DEACTIVATED}"   # POST - 停用喚醒
    
    # Session management (optional - Redis 有但沒啟用)
    # DELETE_SESSION = f"{API_PREFIX}/{InputAction.DELETE_SESSION}"    # DELETE - 刪除 session
    
    # === SSE 事件串流端點 (GET) ===
    EVENTS_STREAM = f"{API_PREFIX}/sessions/{{session_id}}/events"     # GET - SSE 事件串流


class SSEEventTypes:
    """SSE 事件類型定義 - 基於 OutputAction 保持一致性"""
    
    # === 主要輸出事件 (基於 OutputAction) ===
    TRANSCRIBE_DONE = OutputAction.TRANSCRIBE_DONE         # 轉譯完成
    PLAY_ASR_FEEDBACK = OutputAction.PLAY_ASR_FEEDBACK     # 播放 ASR 回饋音
    ERROR_REPORTED = OutputAction.ERROR_REPORTED           # 錯誤已回報
    
    # === 狀態確認事件 (HTTP 特有，用於確認請求處理成功) ===
    SESSION_CREATED = "session_created"        # Session 建立成功
    LISTENING_STARTED = "listening_started"    # 開始監聽成功
    WAKE_ACTIVATED = "wake_activated"          # 喚醒啟用成功
    WAKE_DEACTIVATED = "wake_deactivated"      # 喚醒停用成功
    AUDIO_RECEIVED = "audio_received"          # 確認收到音訊（可選）
    
    # === 系統事件 (SSE 連線管理) ===
    HEARTBEAT = "heartbeat"                    # 心跳事件（保持連線）
    CONNECTION_READY = "connection_ready"      # 連線就緒


class HTTPMethod(str, Enum):
    """HTTP 方法枚舉"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"