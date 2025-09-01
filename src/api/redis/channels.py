from typing import Optional, Any, Dict
from pydantic import BaseModel
from src.interface.action import InputAction, OutputAction


def action2channel(action: str) -> str:
    """
    將 Action 名稱轉換為 Redis 頻道名稱
    例如: create_session -> create:session
    Args:
        action (str): Action 名稱
    Returns:
        str: Redis 頻道名稱
    """
    return action.replace("_", ":").lower()


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
    REQUEST_CREATE_SESSION = "request:" + action2channel(InputAction.CREATE_SESSION)
    REQUEST_START_LISTENING = "request:" + action2channel(InputAction.START_LISTENING)
    REQUEST_EMIT_AUDIO_CHUNK = "request:" + action2channel(InputAction.EMIT_AUDIO_CHUNK)
    
    # Wake control events
    REQUEST_WAKE_ACTIVATE = "request:" + action2channel(InputAction.WAKE_ACTIVATED)  # 喚醒啟用（包含 source）
    REQUEST_WAKE_DEACTIVATE = "request:" + action2channel(InputAction.WAKE_DEACTIVATED)  # 喚醒停用（包含 source）
    
    # 其他輸入事件（保留但可選）
    REQUEST_DELETE_SESSION = "request:" + action2channel(InputAction.DELETE_SESSION)
    
    # === 輸出頻道 (ASRHub -> 客戶端) ===
    # 主要輸出：transcribe_done, play_asr_feedback
    RESPONSE_TRANSCRIBE_DONE = "response:" + action2channel(OutputAction.TRANSCRIBE_DONE)
    RESPONSE_PLAY_ASR_FEEDBACK = "response:" + action2channel(OutputAction.PLAY_ASR_FEEDBACK)
    
    # 錯誤通知
    RESPONSE_ERROR_REPORTED = "response:" + action2channel(OutputAction.ERROR_REPORTED)
    
    # 狀態確認通知（客戶端可選擇性訂閱）
    RESPONSE_SESSION_CREATED = "response:session:created"      # 回應 session 建立成功
    RESPONSE_LISTENING_STARTED = "response:listening:started"  # 回應開始監聽成功
    RESPONSE_WAKE_ACTIVATED = "response:wake:activated"        # 回應喚醒啟用成功
    RESPONSE_WAKE_DEACTIVATED = "response:wake:deactivated"    # 回應喚醒停用成功
    RESPONSE_AUDIO_RECEIVED = "response:audio:received"        # 確認收到音訊（通常不用）
    RESPONSE_ERROR = "response:error"                          # 錯誤通知


# 訂閱的頻道列表（ASRHub 要監聽的）
channels = [
    RedisChannels.REQUEST_CREATE_SESSION,      # request:create:session
    RedisChannels.REQUEST_START_LISTENING,     # request:start:listening  
    RedisChannels.REQUEST_EMIT_AUDIO_CHUNK,    # request:emit:audio:chunk
    RedisChannels.REQUEST_WAKE_ACTIVATE,       # request:wake:activate
    RedisChannels.REQUEST_WAKE_DEACTIVATE,     # request:wake:deactivate
    # RedisChannels.REQUEST_DELETE_SESSION,    # request:delete:session (可選)
]


# === 訊息格式定義（使用 Pydantic） ===

# 輸入訊息格式
class CreateSessionMessage(BaseModel):
    """建立 Session 訊息"""
    strategy: str = "non_streaming"  # batch, non_streaming, streaming
    request_id: str


class StartListeningMessage(BaseModel):
    """開始監聽訊息 - 設定音訊參數"""
    session_id: str
    sample_rate: int = 16000
    channels: int = 1
    format: str = "int16"  # int16, float32


class EmitAudioChunkMessage(BaseModel):
    """發送音訊訊息"""
    session_id: str
    audio_data: str  # encoded audio data


class DeleteSessionMessage(BaseModel):
    """刪除 Session 訊息"""
    session_id: str


class WakeActivateMessage(BaseModel):
    """喚醒啟用訊息"""
    session_id: str
    source: str  # visual, ui, keyword (from WakeActivateSource)


class WakeDeactivateMessage(BaseModel):
    """喚醒停用訊息"""
    session_id: str
    source: str  # visual, ui, vad_silence_timeout (from WakeDeactivateSource)


# 輸出訊息格式
class SessionCreatedMessage(BaseModel):
    """Session 建立成功回應"""
    request_id: str
    session_id: str
    timestamp: Optional[str] = None


class ListeningStartedMessage(BaseModel):
    """開始監聽成功回應"""
    session_id: str
    sample_rate: int = 16000
    channels: int = 1
    format: str = "int16"
    timestamp: Optional[str] = None


class WakeActivatedMessage(BaseModel):
    """喚醒啟用成功回應"""
    session_id: str
    source: str  # 啟用來源
    timestamp: Optional[str] = None


class WakeDeactivatedMessage(BaseModel):
    """喚醒停用成功回應"""
    session_id: str
    source: str  # 停用來源
    timestamp: Optional[str] = None


# class AudioReceivedMessage(BaseModel):
#     """確認收到音訊"""
#     session_id: str
#     chunk_id: Optional[str] = None
#     timestamp: Optional[str] = None


class TranscribeDoneMessage(BaseModel):
    """轉譯完成訊息"""
    session_id: str
    text: str  # 轉譯結果文字
    confidence: Optional[float] = None  # 信心度分數
    language: Optional[str] = None  # 語言代碼
    duration: Optional[float] = None  # 音訊長度（秒）
    timestamp: Optional[str] = None


class PlayASRFeedbackMessage(BaseModel):
    """播放 ASR 回饋音訊息"""
    session_id: str
    command: str  # "play" 或 "stop"
    timestamp: Optional[str] = None


class ErrorMessage(BaseModel):
    """錯誤訊息"""
    session_id: Optional[str] = None
    error_code: str
    error_message: str
    timestamp: Optional[str] = None
