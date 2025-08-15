"""
Sessions 域的狀態定義
"""

from typing import Dict, Any, Optional, List
from typing_extensions import TypedDict
from enum import Enum


class FSMStateEnum(str, Enum):
    """FSM 狀態枚舉"""
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


class SessionState(TypedDict):
    """單個會話狀態"""
    id: str
    fsm_state: FSMStateEnum
    previous_state: Optional[FSMStateEnum]
    strategy: FSMStrategy
    wake_trigger: Optional[str]
    wake_time: Optional[float]
    audio_buffer: List[bytes]
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