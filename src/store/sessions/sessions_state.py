"""
Sessions 域的狀態定義
"""

from typing import Dict, Any, Optional, List
from typing_extensions import TypedDict
from enum import Enum



# ============================================================================
# 事件定義
# ============================================================================
class FSMEvent(str, Enum):
    """FSM 事件枚舉"""
    # 核心事件
    START_LISTENING = "start_listening"
    UPLOAD_FILE = "upload_file"
    UPLOAD_FILE_DONE = "upload_file_done"
    CHUNK_UPLOAD_START = "chunk_upload_start"
    CHUNK_UPLOAD_DONE = "chunk_upload_done"
    WAKE_TRIGGERED = "wake_triggered"
    START_RECORDING = "start_recording"
    END_RECORDING = "end_recording"
    BEGIN_TRANSCRIPTION = "begin_transcription"
    TRANSCRIPTION_DONE = "transcription_done"
    START_ASR_STREAMING = "start_asr_streaming"
    END_ASR_STREAMING = "end_asr_streaming"
    
    # LLM/TTS 事件 (Inbound)
    LLM_REPLY_STARTED = "llm_reply_started"
    LLM_REPLY_FINISHED = "llm_reply_finished"
    TTS_PLAYBACK_STARTED = "tts_playback_started"
    TTS_PLAYBACK_FINISHED = "tts_playback_finished"
    
    # 打斷事件
    INTERRUPT_REPLY = "interrupt_reply"
    
    # 系統事件
    TIMEOUT = "timeout"
    RESET = "reset"
    ERROR = "error"
    RECOVER = "recover"



# ============================================================================
# 狀態定義
# ============================================================================
class FSMStateEnum(str, Enum):
    """FSM 狀態枚舉"""
    ANY = "ANY"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    ACTIVATED = "ACTIVATED"
    RECORDING = "RECORDING"
    STREAMING = "STREAMING"
    TRANSCRIBING = "TRANSCRIBING"
    PROCESSING = "PROCESSING"
    BUSY = "BUSY"
    ERROR = "ERROR"
    RECOVERING = "RECOVERING"


class FSMStrategy(str, Enum):
    """FSM 策略枚舉"""
    STREAMING = "streaming"
    NON_STREAMING = "non_streaming"
    BATCH = "batch"


class AudioFormat(TypedDict):
    """音訊格式定義"""
    sample_rate: int
    channels: int
    encoding: str  # 'LINEAR16', 'MULAW', 'FLAC', etc.
    bits_per_sample: int


class AudioMetadata(TypedDict):
    """音訊 metadata 定義"""
    filename: str
    mimeType: str
    fileSize: int
    duration: float
    sampleRate: int
    channels: int
    bitRate: int
    codec: str
    detectedFormat: str
    needsConversion: bool
    conversionSuggestions: List[str]

class ConversionStrategy(TypedDict):
    """音訊轉換策略定義"""
    needsConversion: bool
    targetSampleRate: int
    targetChannels: int
    targetFormat: str
    conversionSteps: List[str]
    estimatedProcessingTime: float
    priority: str  # "high", "medium", "low"

class SessionState(TypedDict):
    """單個會話狀態"""
    id: str
    fsm_state: FSMStateEnum
    previous_state: Optional[FSMStateEnum]
    strategy: FSMStrategy
    wake_trigger: Optional[str]
    wake_time: Optional[float]
    # audio_buffer 已移至 AudioQueueManager
    audio_bytes_received: int  # 累計接收的音訊位元組數
    audio_chunks_count: int    # 累計接收的音訊塊數
    last_audio_timestamp: Optional[float]  # 最後接收音訊的時間戳
    audio_format: Optional[AudioFormat]  # 音訊格式資訊
    audio_metadata: Optional[AudioMetadata]  # 前端發送的音訊 metadata
    conversion_strategy: Optional[ConversionStrategy]  # 轉換策略
    transcription: Optional[str]
    error: Optional[str]
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]


class SessionsState(TypedDict):
    """Sessions 域的完整狀態"""
    sessions: Dict[str, SessionState]
    active_session_id: Optional[str]
    max_sessions: int


def get_initial_sessions_state() -> SessionsState:
    """獲取初始的 Sessions 域狀態"""
    return SessionsState(
        sessions={},
        active_session_id=None,
        max_sessions=10
    )