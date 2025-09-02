"""
WebRTC API 資料模型

使用 Pydantic 定義請求和回應的資料結構。
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


# === 列舉類型 ===

class SessionStrategy(str, Enum):
    """Session 策略"""
    WHISPER = "whisper"
    FUNASR = "funasr"
    VOSK = "vosk"
    AUTO = "auto"


class SessionStatus(str, Enum):
    """Session 狀態"""
    CREATED = "created"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LISTENING = "listening"
    STOPPED = "stopped"
    ERROR = "error"


class TrackType(str, Enum):
    """Track 類型"""
    AUDIO = "audio"
    VIDEO = "video"
    DATA = "data"


# === 請求模型 ===

class CreateSessionRequest(BaseModel):
    """建立 Session 請求"""
    strategy: SessionStrategy = Field(
        default=SessionStrategy.AUTO,
        description="ASR 策略選擇"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="客戶端請求 ID（用於追蹤）"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Session 元資料"
    )


class StartSessionRequest(BaseModel):
    """開始 Session 請求"""
    session_id: str = Field(description="Session ID")
    sample_rate: int = Field(
        default=16000,
        description="音訊取樣率"
    )
    channels: int = Field(
        default=1,
        description="音訊聲道數"
    )
    format: str = Field(
        default="int16",
        description="音訊格式"
    )


class StopSessionRequest(BaseModel):
    """停止 Session 請求"""
    session_id: str = Field(description="Session ID")
    reason: Optional[str] = Field(
        default=None,
        description="停止原因"
    )


# === 回應模型 ===

class CreateSessionResponse(BaseModel):
    """建立 Session 回應"""
    session_id: str = Field(description="Session ID")
    request_id: str = Field(description="請求 ID")
    token: str = Field(description="LiveKit 存取 token")
    room_name: str = Field(description="LiveKit 房間名稱")
    livekit_url: str = Field(description="LiveKit 伺服器 URL")
    api_url: str = Field(description="WebRTC API 基礎 URL")


class StartSessionResponse(BaseModel):
    """開始 Session 回應"""
    session_id: str = Field(description="Session ID")
    status: SessionStatus = Field(description="Session 狀態")
    sample_rate: int = Field(description="音訊取樣率")
    channels: int = Field(description="音訊聲道數")
    format: str = Field(description="音訊格式")


class StopSessionResponse(BaseModel):
    """停止 Session 回應"""
    session_id: str = Field(description="Session ID")
    status: SessionStatus = Field(description="Session 狀態")
    message: str = Field(description="狀態訊息")


class SessionStatusResponse(BaseModel):
    """Session 狀態回應"""
    session_id: str = Field(description="Session ID")
    status: SessionStatus = Field(description="Session 狀態")
    is_connected: bool = Field(description="是否已連線")
    is_listening: bool = Field(description="是否正在監聽")
    participant_count: int = Field(
        default=0,
        description="房間參與者數量"
    )
    created_at: datetime = Field(description="建立時間")
    connected_at: Optional[datetime] = Field(
        default=None,
        description="連線時間"
    )
    last_activity: Optional[datetime] = Field(
        default=None,
        description="最後活動時間"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Session 元資料"
    )


class RoomStatusResponse(BaseModel):
    """房間狀態回應"""
    room_name: str = Field(description="房間名稱")
    is_active: bool = Field(description="房間是否活躍")
    participant_count: int = Field(description="參與者數量")
    active_sessions: List[str] = Field(
        default_factory=list,
        description="活躍的 session IDs"
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="房間建立時間"
    )


# === 廣播資料模型 ===

class TranscriptionBroadcast(BaseModel):
    """轉譯結果廣播"""
    type: str = Field(
        default="transcription",
        description="訊息類型"
    )
    session_id: str = Field(description="Session ID")
    text: str = Field(description="轉譯文字")
    language: Optional[str] = Field(
        default=None,
        description="語言代碼"
    )
    confidence: Optional[float] = Field(
        default=None,
        description="信心度分數"
    )
    duration: Optional[float] = Field(
        default=None,
        description="音訊長度（秒）"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="時間戳記"
    )


class ASRFeedbackBroadcast(BaseModel):
    """ASR 回饋音廣播"""
    type: str = Field(
        default="asr_feedback",
        description="訊息類型"
    )
    session_id: str = Field(description="Session ID")
    command: str = Field(description="指令（play/stop）")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="時間戳記"
    )


# === 錯誤模型 ===

class ErrorResponse(BaseModel):
    """錯誤回應"""
    error: str = Field(description="錯誤類型")
    message: str = Field(description="錯誤訊息")
    detail: Optional[Dict[str, Any]] = Field(
        default=None,
        description="錯誤詳情"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="時間戳記"
    )