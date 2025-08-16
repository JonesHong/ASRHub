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
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("fsm_state") if sessions.get(session_id) else None
    )


def get_session_transcription(session_id: str):
    """獲取特定會話的轉譯結果"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("transcription") if sessions.get(session_id) else None
    )


def get_session_error(session_id: str):
    """獲取特定會話的錯誤信息"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("error") if sessions.get(session_id) else None
    )


def get_session_audio_buffer_size(session_id: str):
    """獲取特定會話的音訊緩衝區大小"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: len(sessions.get(session_id, {}).get("audio_buffer", [])) if sessions.get(session_id) else 0
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


# ============================================================================
# 新增的 Selectors (取代 SessionManager 功能)
# ============================================================================

def get_session_state(session_id: str):
    """獲取特定會話的狀態 (IDLE, LISTENING, BUSY)"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("state", "IDLE") if sessions.get(session_id) else None
    )


def get_session_metadata(session_id: str):
    """獲取特定會話的 metadata"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("metadata", {}) if sessions.get(session_id) else {}
    )


def get_session_pipeline_config(session_id: str):
    """獲取特定會話的 pipeline 配置"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("pipeline_config", {}) if sessions.get(session_id) else {}
    )


def get_session_provider_config(session_id: str):
    """獲取特定會話的 provider 配置"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("provider_config", {}) if sessions.get(session_id) else {}
    )


def get_session_wake_info(session_id: str):
    """獲取特定會話的喚醒資訊"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: {
            "wake_source": sessions.get(session_id, {}).get("wake_source"),
            "wake_time": sessions.get(session_id, {}).get("wake_time"),
            "wake_timeout": sessions.get(session_id, {}).get("wake_timeout", 30.0),
            "is_wake_expired": _is_wake_expired(sessions.get(session_id)) if sessions.get(session_id) else False
        } if sessions.get(session_id) else None
    )


def get_session_priority(session_id: str):
    """獲取特定會話的優先級"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sessions.get(session_id, {}).get("priority", 0) if sessions.get(session_id) else 0
    )


def get_sessions_by_wake_source(source: str):
    """根據喚醒源獲取會話列表"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: [
            session for session in sessions.values()
            if session.get("wake_source") == source
        ]
    )


def get_active_wake_sessions():
    """獲取所有處於喚醒狀態且未超時的會話"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: [
            session for session in sessions.values()
            if session.get("wake_time") and not _is_wake_expired(session)
        ]
    )


def get_sessions_by_priority(min_priority: int = 0):
    """根據優先級獲取會話（降序排列）"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: sorted(
            [s for s in sessions.values() if s.get("priority", 0) >= min_priority],
            key=lambda s: s.get("priority", 0),
            reverse=True
        )
    )


def get_wake_stats():
    """獲取喚醒統計資訊"""
    return create_selector(
        get_all_sessions,
        get_active_wake_sessions,
        result_fn=lambda all_sessions, active_wake: {
            "total_sessions": len(all_sessions),
            "active_wake_sessions": len(active_wake),
            "wake_word_sessions": len([s for s in all_sessions.values() if s.get("wake_source") == "wake_word"]),
            "ui_wake_sessions": len([s for s in all_sessions.values() if s.get("wake_source") == "ui"]),
            "visual_wake_sessions": len([s for s in all_sessions.values() if s.get("wake_source") == "visual"]),
            "wake_expired_sessions": len([s for s in all_sessions.values() if _is_wake_expired(s)])
        }
    )


def get_session_by_state(state: str):
    """根據狀態獲取會話列表"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: [
            session for session in sessions.values()
            if session.get("state") == state
        ]
    )


def get_session_mode(session_id: str):
    """獲取特定會話的模式"""
    return create_selector(
        get_session(session_id),
        result_fn=lambda session: session.get("mode", "streaming") if session else None
    )


def list_sessions():
    """列出所有有效的會話（類似 SessionManager.list_sessions）"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: list(sessions.values())
    )


def session_exists(session_id: str):
    """檢查會話是否存在"""
    return create_selector(
        get_all_sessions,
        result_fn=lambda sessions: session_id in sessions
    )


# 輔助函數
def _is_wake_expired(session):
    """檢查喚醒是否已超時"""
    import time
    if not session or not session.get("wake_time"):
        return False
    wake_timeout = session.get("wake_timeout", 30.0)
    return (time.time() - session["wake_time"]) > wake_timeout