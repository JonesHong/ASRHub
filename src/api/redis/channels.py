"""Redis 頻道定義與工具函數"""

from src.interface.action import InputAction, OutputAction




def session2channel(channel: str, session_id: str) -> str:
    """
    將 Session ID 與頻道名稱結合
    例如: create:session:12345
    Args:
        channel (str): 頻道名稱
        session_id (str): Session ID
    Returns:
        str: 完整的 Redis 頻道名稱
    """
    return f"{channel}:{session_id}"


class RedisChannels:
    """Redis 頻道定義 - 使用廣播模式，所有訊息帶 session_id"""

    # === 輸入頻道 (客戶端 -> ASRHub) ===
    # 主要輸入：create_session, start_listening, receive_audio_chunk
    REQUEST_CREATE_SESSION = "request:" + InputAction.CREATE_SESSION
    REQUEST_START_LISTENING = "request:" + InputAction.START_LISTENING
    REQUEST_EMIT_AUDIO_CHUNK = "request:" + InputAction.EMIT_AUDIO_CHUNK
    
    # Wake control events
    REQUEST_WAKE_ACTIVATE = "request:" + InputAction.WAKE_ACTIVATED  # 喚醒啟用（包含 source）
    REQUEST_WAKE_DEACTIVATE = "request:" + InputAction.WAKE_DEACTIVATED  # 喚醒停用（包含 source）
    
    # 其他輸入事件（保留但可選）
    REQUEST_DELETE_SESSION = "request:" + InputAction.DELETE_SESSION
    
    # === 輸出頻道 (ASRHub -> 客戶端) ===
    # 主要輸出：transcribe_done, play_asr_feedback
    RESPONSE_TRANSCRIBE_DONE = "response:" + OutputAction.TRANSCRIBE_DONE
    RESPONSE_PLAY_ASR_FEEDBACK = "response:" + OutputAction.PLAY_ASR_FEEDBACK
    
    # 錯誤通知
    RESPONSE_ERROR_REPORTED = "response:" + OutputAction.ERROR_REPORTED
    
    # 狀態確認通知（客戶端可選擇性訂閱）
    RESPONSE_SESSION_CREATED = "response:session_created"      # 回應 session 建立成功
    RESPONSE_LISTENING_STARTED = "response:listening_started"  # 回應開始監聽成功
    RESPONSE_WAKE_ACTIVATED = "response:wake_activated"        # 回應喚醒啟用成功
    RESPONSE_WAKE_DEACTIVATED = "response:wake_deactivated"    # 回應喚醒停用成功
    RESPONSE_AUDIO_RECEIVED = "response:audio_received"        # 確認收到音訊（通常不用）
    RESPONSE_ERROR = "response:error"                          # 錯誤通知


# 訂閱的頻道列表（ASRHub 要監聽的）
channels = [
    RedisChannels.REQUEST_CREATE_SESSION,      # request:create_session
    RedisChannels.REQUEST_START_LISTENING,     # request:start_listening
    RedisChannels.REQUEST_EMIT_AUDIO_CHUNK,    # request:emit_audio_chunk
    RedisChannels.REQUEST_WAKE_ACTIVATE,       # request:wake_activate
    RedisChannels.REQUEST_WAKE_DEACTIVATE,     # request:wake_deactivate
    # RedisChannels.REQUEST_DELETE_SESSION,    # request:delete_session (可選)
]