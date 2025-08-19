"""
Sessions 域的公共 API
"""

# State 定義
from .sessions_state import (
    FSMStateEnum,
    FSMStrategy,
    SessionState,
    SessionsState
)

# Actions
from .sessions_actions import (
    # Session 管理
    create_session,
    destroy_session,
    set_active_session,
    clear_active_session,
    
    # FSM 狀態轉換
    start_listening,
    wake_triggered,
    start_recording,
    end_recording,
    start_asr_streaming,
    end_asr_streaming,
    begin_transcription,
    transcription_done,
    fsm_reset,
    
    # 音訊處理
    audio_chunk_received,
    clear_audio_buffer,
    speech_detected,
    silence_detected,
    
    # 錯誤處理
    session_error,
    clear_session_error
)

# Reducer
from .sessions_reducer import sessions_reducer

# Selectors
from .sessions_selectors import (
    # 基礎 selectors
    get_sessions_state,
    get_all_sessions,
    get_active_session_id,
    get_max_sessions,
    
    # 複合 selectors
    get_session,
    get_active_session,
    get_session_fsm_state,
    get_session_transcription,
    get_session_error,
    get_session_audio_buffer_size,
    
    # 條件查詢 selectors
    get_active_sessions,
    get_idle_sessions,
    get_listening_sessions,
    get_recording_sessions,
    get_transcribing_sessions,
    get_error_sessions,
    
    # 統計 selectors
    get_session_count,
    get_active_session_count,
    get_sessions_by_state,
    get_session_states_summary,
    
    # 業務邏輯 selectors
    can_create_new_session,
    has_active_recording,
    get_oldest_session,
    get_newest_session,
    get_sessions_with_transcription,
    get_sessions_with_errors
)

# Effects
from .sessions_effects import (
    SessionEffects,
    SessionTimerEffects
)

__all__ = [
    # State
    "FSMStateEnum",
    "FSMStrategy", 
    "SessionState",
    "SessionsState",
    
    # Actions
    "create_session",
    "destroy_session",
    "set_active_session",
    "clear_active_session",
    "start_listening",
    "wake_triggered",
    "start_recording",
    "end_recording",
    "start_asr_streaming",
    "end_asr_streaming",
    "begin_transcription",
    "transcription_done",
    "fsm_reset",
    "audio_chunk_received",
    "clear_audio_buffer",
    "speech_detected",
    "silence_detected",
    "session_error",
    "clear_session_error",
    
    # Reducer
    "sessions_reducer",
    
    # Selectors
    "get_sessions_state",
    "get_all_sessions",
    "get_active_session_id",
    "get_max_sessions",
    "get_session",
    "get_active_session",
    "get_session_fsm_state",
    "get_session_transcription",
    "get_session_error",
    "get_session_audio_buffer_size",
    "get_active_sessions",
    "get_idle_sessions",
    "get_listening_sessions",
    "get_recording_sessions",
    "get_transcribing_sessions",
    "get_error_sessions",
    "get_session_count",
    "get_active_session_count",
    "get_sessions_by_state",
    "get_session_states_summary",
    "can_create_new_session",
    "has_active_recording",
    "get_oldest_session",
    "get_newest_session",
    "get_sessions_with_transcription",
    "get_sessions_with_errors",
    
    # Effects
    "SessionEffects",
    "SessionTimerEffects"
]