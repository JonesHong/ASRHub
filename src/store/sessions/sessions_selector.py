"""
Sessions Selectors for PyStoreX Store

提供各種狀態查詢功能，支援 memoization 優化效能。
所有 selector 都是純函數，不會修改狀態。
"""

from typing import List, Optional, Dict, Any, Union, Tuple
from pystorex.store_selectors import create_selector
from immutables import Map

from src.store.sessions.sessions_state import (
    SessionState,
    SessionStatus,
    WakeSource,
    TranscriptionStrategy
)


# === Base Selectors ===

def get_sessions_state(state: Any) -> Map:
    """取得整個 sessions 狀態"""
    # 處理 PyStoreX 的 (old, new) tuple 格式
    if isinstance(state, tuple) and len(state) == 2:
        _, new_state = state
    else:
        new_state = state
    return new_state.get("sessions", Map())


def get_all_sessions(state: Any) -> Dict[str, SessionState]:
    """取得所有 sessions 的字典"""
    # 處理 PyStoreX 的 (old, new) tuple 格式
    if isinstance(state, tuple) and len(state) == 2:
        state = state[1]
    sessions_state = get_sessions_state(state)
    sessions = sessions_state.get("sessions", {})
    
    # 如果是 immutables.Map，轉換為 dict
    if isinstance(sessions, Map):
        return dict(sessions.items())
    return sessions


def get_active_session_ids(state: Any) -> List[str]:
    """取得活躍的 session IDs"""
    # 處理 PyStoreX 的 (old, new) tuple 格式
    if isinstance(state, tuple) and len(state) == 2:
        state = state[1]
    sessions_state = get_sessions_state(state)
    active_ids = sessions_state.get("active_session_ids", [])
    return list(active_ids) if active_ids else []


def get_total_created(state: Any) -> int:
    """取得總建立的 session 數量"""
    # 處理 PyStoreX 的 (old, new) tuple 格式
    if isinstance(state, tuple) and len(state) == 2:
        state = state[1]
    sessions_state = get_sessions_state(state)
    return sessions_state.get("total_created", 0)


def get_total_deleted(state: Any) -> int:
    """取得總刪除的 session 數量"""
    # 處理 PyStoreX 的 (old, new) tuple 格式
    if isinstance(state, tuple) and len(state) == 2:
        state = state[1]
    sessions_state = get_sessions_state(state)
    return sessions_state.get("total_deleted", 0)


# === Session By ID Selectors ===

def get_session_by_id(session_id: str):
    """取得特定 session 的狀態（參數化選擇器）"""
    def selector(state):
        # 處理 PyStoreX 的 (old, new) tuple 格式
        if isinstance(state, tuple) and len(state) == 2:
            state = state[1]
        sessions_state = get_sessions_state(state)
        return _get_session_by_id_impl(sessions_state, session_id)
    return selector

def _get_session_by_id_impl(sessions_state: Map, session_id: str) -> Optional[SessionState]:
    """取得特定 session 的狀態"""
    sessions = sessions_state.get("sessions", {})
    
    if isinstance(sessions, Map):
        session = sessions.get(session_id)
    else:
        session = sessions.get(session_id)
    
    # 轉換為 dict（如果是 Map）
    if session and isinstance(session, Map):
        return dict(session.items())
    return session


# === Status-based Selectors ===

def get_sessions_by_status(status: SessionStatus):
    """取得特定狀態的 sessions（參數化選擇器）"""
    return create_selector(
        get_all_sessions,
        lambda sessions: [
            s for s in sessions.values() 
            if s.get("status") == status
        ]
    )

# 具體狀態的 selectors
get_idle_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("status") == SessionStatus.IDLE
    ]
)

get_listening_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("status") == SessionStatus.LISTENING
    ]
)

get_processing_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("status") == SessionStatus.PROCESSING
    ]
)

get_transcribing_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("status") == SessionStatus.TRANSCRIBING
    ]
)

get_error_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("status") == SessionStatus.ERROR
    ]
)


# === Activity-based Selectors ===

get_active_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("status") != SessionStatus.IDLE
    ]
)

get_wake_active_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("is_wake_active", False)
    ]
)

get_recording_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("is_recording", False)
    ]
)

get_vad_active_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("is_vad_speech", False)
    ]
)

get_streaming_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("is_streaming", False)
    ]
)


# === Strategy-based Selectors ===

def get_sessions_by_strategy(strategy: TranscriptionStrategy):
    """取得特定策略的 sessions（參數化選擇器）"""
    return create_selector(
        get_all_sessions,
        lambda sessions: [
            s for s in sessions.values() 
            if s.get("strategy") == strategy
        ]
    )

get_batch_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("strategy") == TranscriptionStrategy.BATCH
    ]
)

get_non_streaming_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("strategy") == TranscriptionStrategy.NON_STREAMING
    ]
)

get_streaming_strategy_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("strategy") == TranscriptionStrategy.STREAMING
    ]
)


# === Wake Source Selectors ===

def get_sessions_by_wake_source(source: WakeSource):
    """取得特定喚醒來源的 sessions（參數化選擇器）"""
    return create_selector(
        get_all_sessions,
        lambda sessions: [
            s for s in sessions.values() 
            if s.get("wake_source") == source
        ]
    )

get_ui_wake_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("wake_source") == WakeSource.UI
    ]
)

get_keyword_wake_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("wake_source") == WakeSource.KEYWORD
    ]
)


# === Upload Selectors ===

get_uploading_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("upload_file") and s.get("upload_progress", 1.0) < 1.0
    ]
)

get_upload_completed_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("upload_file") and s.get("upload_progress", 0) >= 1.0
    ]
)


# === Error Selectors ===

get_sessions_with_errors = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values() 
        if s.get("error_count", 0) > 0
    ]
)

def get_sessions_by_error_threshold(threshold: int):
    """取得錯誤次數超過閾值的 sessions（參數化選擇器）"""
    return create_selector(
        get_all_sessions,
        lambda sessions: [
            s for s in sessions.values() 
            if s.get("error_count", 0) >= threshold
        ]
    )


# === Statistics Selectors ===

get_session_statistics = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: {
        "total": len(sessions),
        "active": len([s for s in sessions.values() if s.get("status") != SessionStatus.IDLE]),
        "idle": len([s for s in sessions.values() if s.get("status") == SessionStatus.IDLE]),
        "recording": len([s for s in sessions.values() if s.get("is_recording", False)]),
        "transcribing": len([s for s in sessions.values() if s.get("is_transcribing", False)]),
        "errors": len([s for s in sessions.values() if s.get("error_count", 0) > 0]),
        "wake_active": len([s for s in sessions.values() if s.get("is_wake_active", False)]),
        "total_chunks_received": sum(s.get("audio_chunks_received", 0) for s in sessions.values()),
        "total_transcriptions": sum(s.get("transcriptions_count", 0) for s in sessions.values())
    }
)

get_strategy_distribution = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: {
        TranscriptionStrategy.BATCH: len([
            s for s in sessions.values() 
            if s.get("strategy") == TranscriptionStrategy.BATCH
        ]),
        TranscriptionStrategy.NON_STREAMING: len([
            s for s in sessions.values() 
            if s.get("strategy") == TranscriptionStrategy.NON_STREAMING
        ]),
        TranscriptionStrategy.STREAMING: len([
            s for s in sessions.values() 
            if s.get("strategy") == TranscriptionStrategy.STREAMING
        ])
    }
)


# === Expired Sessions Selector ===

get_expired_sessions = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: _get_expired_sessions_impl(sessions)
)

def _get_expired_sessions_impl(sessions: Dict[str, SessionState]) -> List[SessionState]:
    """取得已過期的 sessions"""
    import time
    current_time = time.time()
    
    return [
        s for s in sessions.values()
        if s.get("expires_at") and s.get("expires_at") < current_time
    ]


# === Recent Activity Selectors ===

def get_recently_active_sessions(minutes: int = 5):
    """取得最近活動的 sessions（參數化選擇器）"""
    return create_selector(
        get_all_sessions,
        lambda sessions: _get_recent_sessions_impl(sessions, minutes)
    )

def _get_recent_sessions_impl(sessions: Dict[str, SessionState], minutes: int = 5) -> List[SessionState]:
    """取得最近活動的 sessions"""
    import time
    current_time = time.time()
    threshold = current_time - (minutes * 60)
    
    return [
        s for s in sessions.values()
        if s.get("updated_at", 0) > threshold
    ]


# === Audio Configuration Selectors ===

def get_session_audio_config(session_id: str):
    """取得特定 session 的音訊配置（參數化選擇器）"""
    def selector(state):
        # 處理 PyStoreX 的 (old, new) tuple 格式
        if isinstance(state, tuple) and len(state) == 2:
            state = state[1]
        sessions_state = get_sessions_state(state)
        return _get_session_audio_config_impl(sessions_state, session_id)
    return selector

def _get_session_audio_config_impl(sessions_state: Map, session_id: str) -> Optional[Dict[str, Any]]:
    """取得特定 session 的音訊配置"""
    session = _get_session_by_id_impl(sessions_state, session_id)
    
    if not session:
        return None
    
    audio_config = session.get("audio_config")
    
    # 如果是 Map，轉換為 dict
    if audio_config and isinstance(audio_config, Map):
        return dict(audio_config.items())
    
    return audio_config

get_sessions_with_audio_config = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values()
        if s.get("audio_config") is not None
    ]
)

# === Audio Processing Selectors ===

get_sessions_needing_processing = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: [
        s for s in sessions.values()
        if (s.get("audio_chunks_received", 0) > s.get("audio_chunks_processed", 0))
    ]
)

get_audio_queue_stats = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: {
        "total_received": sum(s.get("audio_chunks_received", 0) for s in sessions.values()),
        "total_processed": sum(s.get("audio_chunks_processed", 0) for s in sessions.values()),
        "pending": sum(
            s.get("audio_chunks_received", 0) - s.get("audio_chunks_processed", 0)
            for s in sessions.values()
        ),
        "sessions_with_pending": len([
            s for s in sessions.values()
            if s.get("audio_chunks_received", 0) > s.get("audio_chunks_processed", 0)
        ])
    }
)


# === Combined Selectors ===

def get_session_summary(session_id: str):
    """取得 session 的摘要資訊（參數化選擇器）"""
    def selector(state):
        # 處理 PyStoreX 的 (old, new) tuple 格式
        if isinstance(state, tuple) and len(state) == 2:
            state = state[1]
        sessions_state = get_sessions_state(state)
        return _get_session_summary_impl(sessions_state, session_id)
    return selector

def _get_session_summary_impl(sessions_state: Map, session_id: str) -> Optional[Dict[str, Any]]:
    """取得 session 的摘要資訊"""
    session = _get_session_by_id_impl(sessions_state, session_id)
    
    if not session:
        return None
    
    return {
        "session_id": session.get("session_id"),
        "strategy": session.get("strategy"),
        "status": session.get("status"),
        "is_active": session.get("status") != SessionStatus.IDLE,
        "is_wake": session.get("is_wake_active", False),
        "is_recording": session.get("is_recording", False),
        "has_errors": session.get("error_count", 0) > 0,
        "chunks_pending": session.get("audio_chunks_received", 0) - session.get("audio_chunks_processed", 0),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at")
    }


# === Health Check Selectors ===

get_system_health = create_selector(
    get_all_sessions,
    result_fn=lambda sessions: {
        "healthy": all(s.get("error_count", 0) < 5 for s in sessions.values()),
        "sessions_count": len(sessions),
        "error_sessions": len([s for s in sessions.values() if s.get("error_count", 0) > 0]),
        "critical_errors": len([s for s in sessions.values() if s.get("error_count", 0) >= 10]),
        "active_percentage": (
            len([s for s in sessions.values() if s.get("status") != SessionStatus.IDLE]) / 
            max(len(sessions), 1) * 100
        )
    }
)