"""HTTP SSE API 資料模型定義"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


# === 請求模型 (HTTP Request Bodies) ===

class CreateSessionRequest(BaseModel):
    """建立 Session 請求"""
    strategy: str = Field(default="non_streaming", description="ASR 策略: batch, non_streaming, streaming")
    request_id: Optional[str] = Field(default=None, description="客戶端請求 ID（可選）")


class StartListeningRequest(BaseModel):
    """開始監聽請求 - 設定音訊參數"""
    session_id: str = Field(..., description="Session ID")
    sample_rate: int = Field(default=16000, description="取樣率 (Hz)")
    channels: int = Field(default=1, description="聲道數")
    format: str = Field(default="int16", description="音訊格式: int16, float32")


class EmitAudioChunkRequest(BaseModel):
    """發送音訊請求"""
    session_id: str = Field(..., description="Session ID")
    audio_data: str = Field(..., description="Base64 編碼的音訊資料")
    chunk_id: Optional[str] = Field(default=None, description="音訊片段 ID（用於追蹤）")


class WakeActivateRequest(BaseModel):
    """喚醒啟用請求"""
    session_id: str = Field(..., description="Session ID")
    source: str = Field(..., description="啟用來源: visual, ui, keyword")


class WakeDeactivateRequest(BaseModel):
    """喚醒停用請求"""
    session_id: str = Field(..., description="Session ID")
    source: str = Field(..., description="停用來源: visual, ui, vad_silence_timeout")


# === 回應模型 (HTTP Response Bodies) ===

class CreateSessionResponse(BaseModel):
    """建立 Session 回應"""
    session_id: str = Field(..., description="新建立的 Session ID")
    request_id: Optional[str] = Field(default=None, description="原始請求 ID")
    sse_url: str = Field(..., description="SSE 事件串流 URL")
    audio_url: str = Field(..., description="音訊上傳 URL")


class StartListeningResponse(BaseModel):
    """開始監聽回應"""
    session_id: str = Field(..., description="Session ID")
    sample_rate: int = Field(..., description="已設定的取樣率")
    channels: int = Field(..., description="已設定的聲道數")
    format: str = Field(..., description="已設定的音訊格式")
    status: str = Field(default="listening", description="狀態")


class WakeActivateResponse(BaseModel):
    """喚醒啟用回應"""
    session_id: str = Field(..., description="Session ID")
    source: str = Field(..., description="啟用來源")
    status: str = Field(default="activated", description="狀態")


class WakeDeactivateResponse(BaseModel):
    """喚醒停用回應"""
    session_id: str = Field(..., description="Session ID")
    source: str = Field(..., description="停用來源")
    status: str = Field(default="deactivated", description="狀態")


class AudioChunkResponse(BaseModel):
    """音訊接收確認回應"""
    session_id: str = Field(..., description="Session ID")
    chunk_id: Optional[str] = Field(default=None, description="音訊片段 ID")
    bytes_received: int = Field(..., description="接收的位元組數")
    status: str = Field(default="received", description="狀態")


class ErrorResponse(BaseModel):
    """錯誤回應"""
    error_code: str = Field(..., description="錯誤代碼")
    error_message: str = Field(..., description="錯誤訊息")
    session_id: Optional[str] = Field(default=None, description="相關的 Session ID")
    details: Optional[Dict[str, Any]] = Field(default=None, description="詳細錯誤資訊")


# === SSE 事件模型 ===

class SSEEvent(BaseModel):
    """SSE 事件基礎模型"""
    event: str = Field(..., description="事件類型")
    data: Dict[str, Any] = Field(..., description="事件資料")
    id: Optional[str] = Field(default=None, description="事件 ID")
    retry: Optional[int] = Field(default=None, description="重試間隔（毫秒）")


class TranscribeDoneEvent(BaseModel):
    """轉譯完成事件資料"""
    session_id: str = Field(..., description="Session ID")
    text: str = Field(..., description="轉譯結果文字")
    confidence: Optional[float] = Field(default=None, description="信心度分數")
    language: Optional[str] = Field(default=None, description="語言代碼")
    duration: Optional[float] = Field(default=None, description="音訊長度（秒）")
    timestamp: str = Field(..., description="時間戳記")


class PlayASRFeedbackEvent(BaseModel):
    """播放 ASR 回饋音事件資料"""
    session_id: str = Field(..., description="Session ID")
    command: str = Field(..., description="指令: play 或 stop")
    timestamp: str = Field(..., description="時間戳記")


class HeartbeatEvent(BaseModel):
    """心跳事件資料"""
    session_id: str = Field(..., description="Session ID")
    timestamp: str = Field(..., description="時間戳記")
    sequence: int = Field(..., description="序列號")


class ConnectionReadyEvent(BaseModel):
    """連線就緒事件資料"""
    session_id: str = Field(..., description="Session ID")
    timestamp: str = Field(..., description="時間戳記")
    message: str = Field(default="SSE connection established", description="訊息")