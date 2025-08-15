"""
Sessions 域的 Selectors 定義
"""

from typing import List, Optional
from pystorex import create_selector

from .sessions_state import SessionState, SessionsState, FSMStateEnum, get_initial_sessions_state


# ============================================================================
# 基礎 Selectors
# ============================================================================

def get_sessions_state(state) -> SessionsState:
    """獲取 sessions 狀態切片"""
    if not state:
        return get_initial_sessions_state()
    return state.get("sessions", get_initial_sessions_state())


def get_all_sessions(state) -> dict:
    """獲取所有會話"""
    sessions_state = get_sessions_state(state)
    return sessions_state.get("sessions", {}) if sessions_state else {}


def get_active_session_id(state) -> Optional[str]:
    """獲取活躍會話 ID"""
    sessions_state = get_sessions_state(state)
    return sessions_state.get("active_session_id") if sessions_state else None


def get_max_sessions(state) -> int:
    """獲取最大會話數限制"""
    sessions_state = get_sessions_state(state)
    return sessions_state.get("max_sessions", 10) if sessions_state else 10


# ============================================================================
# 複合 Selectors
# ============================================================================

def get_session(session_id: str):
    """獲取特定會話"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id)
    )


def get_active_session():
    """獲取當前活躍會話"""
    return create_selector(
        get_all_sessions,
        get_active_session_id,
        result_fn=lambda sessions, active_id: sessions.get(active_id) if active_id else None
    )


def get_session_fsm_state(session_id: str):
    """獲取特定會話的 FSM 狀態"""
    return create_selector(
        get_session(session_id),
        result_fn=lambda session: session["fsm_state"] if session else None
    )


def get_session_transcription(session_id: str):
    """獲取特定會話的轉譯結果"""
    return create_selector(
        get_session(session_id),
        result_fn=lambda session: session["transcription"] if session else None
    )


def get_session_error(session_id: str):
    """獲取特定會話的錯誤信息"""
    return create_selector(
        get_session(session_id),
        result_fn=lambda session: session["error"] if session else None
    )


def get_session_audio_buffer_size(session_id: str):
    """獲取特定會話的音訊緩衝區大小"""
    return create_selector(
        get_session(session_id),
        result_fn=lambda session: len(session["audio_buffer"]) if session else 0
    )


# ============================================================================
# 條件查詢 Selectors
# ============================================================================

get_active_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        session for session in sessions.values()
        if session["fsm_state"] not in [FSMStateEnum.IDLE, FSMStateEnum.ERROR]
    ]
)


get_idle_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        session for session in sessions.values()
        if session["fsm_state"] == FSMStateEnum.IDLE
    ]
)


get_listening_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        session for session in sessions.values()
        if session["fsm_state"] == FSMStateEnum.LISTENING
    ]
)


get_recording_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        session for session in sessions.values()
        if session["fsm_state"] in [FSMStateEnum.RECORDING, FSMStateEnum.STREAMING]
    ]
)


get_transcribing_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        session for session in sessions.values()
        if session["fsm_state"] == FSMStateEnum.TRANSCRIBING
    ]
)


get_error_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        session for session in sessions.values()
        if session["fsm_state"] == FSMStateEnum.ERROR
    ]
)


# ============================================================================
# 統計 Selectors
# ============================================================================

get_session_count = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: len(sessions)
)


get_active_session_count = create_selector(
    get_active_sessions,
    result_fn=lambda active_sessions: len(active_sessions)
)


get_sessions_by_state = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: {
        state.value: [
            session for session in sessions.values()
            if session["fsm_state"] == state
        ]
        for state in FSMStateEnum
    }
)


get_session_states_summary = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: {
        state.value: len([
            session for session in sessions.values()
            if session["fsm_state"] == state
        ])
        for state in FSMStateEnum
    }
)


# ============================================================================
# 業務邏輯 Selectors
# ============================================================================

def can_create_new_session():
    """檢查是否可以創建新會話"""
    return create_selector(
        get_session_count,
        get_max_sessions,
        result_fn=lambda current_count, max_sessions: current_count < max_sessions
    )


def has_active_recording():
    """檢查是否有正在錄音的會話"""
    return create_selector(
        get_recording_sessions,
        result_fn=lambda recording_sessions: len(recording_sessions) > 0
    )


def get_oldest_session():
    """獲取最舊的會話"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: min(
            sessions.values(),
            key=lambda s: s["created_at"],
            default=None
        ) if sessions else None
    )


def get_newest_session():
    """獲取最新的會話"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: max(
            sessions.values(),
            key=lambda s: s["created_at"],
            default=None
        ) if sessions else None
    )


def get_sessions_with_transcription():
    """獲取有轉譯結果的會話"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: [
            session for session in sessions.values()
            if session["transcription"] is not None
        ]
    )


def get_sessions_with_errors():
    """獲取有錯誤的會話"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: [
            session for session in sessions.values()
            if session["error"] is not None
        ]
    )