"""Redis 訊息模型定義 - 所有 Redis pub/sub 訊息的 Pydantic 模型"""

from typing import Optional
from pydantic import BaseModel


# === 輸入訊息格式 ===

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


# === 輸出訊息格式 ===

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