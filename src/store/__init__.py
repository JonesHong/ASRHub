"""
ASR Hub Redux Store 主要入口點

提供基於 PyStoreX 的 Redux 狀態管理解決方案
"""

# Store 核心
from .store_config import (
    ASRHubStore,
    StoreConfig,
    get_hub_store,
    get_global_store,  # 兼容舊版 API
    configure_global_store,  # 兼容舊版 API
    reset_global_store
)

# 初始化
from .initialize import (
    initialize_asr_hub_store,
    create_operator_factories,
    create_provider_factories,
    preload_models,
    get_store_status
)

# Sessions 域 - 完整導出
from .sessions import (
    # State
    FSMStateEnum,
    FSMStrategy,
    SessionState,
    SessionsState,
    
    # Actions
    create_session,
    destroy_session,
    set_active_session,
    clear_active_session,
    start_listening,
    wake_triggered,
    start_recording,
    end_recording,
    start_asr_streaming,
    end_asr_streaming,
    begin_transcription,
    transcription_done,
    fsm_reset,
    audio_chunk_received,
    clear_audio_buffer,
    audio_metadata,
    session_error,
    clear_error,
    
    # Reducer
    sessions_reducer,
    
    # Selectors
    get_sessions_state,
    get_all_sessions,
    get_active_session_id,
    get_max_sessions,
    get_session,
    get_active_session,
    get_session_fsm_state,
    get_session_transcription,
    get_session_error,
    get_session_audio_buffer_size,
    get_active_sessions,
    get_idle_sessions,
    get_listening_sessions,
    get_recording_sessions,
    get_transcribing_sessions,
    get_error_sessions,
    get_session_count,
    get_active_session_count,
    get_sessions_by_state,
    get_session_states_summary,
    can_create_new_session,
    has_active_recording,
    get_oldest_session,
    get_newest_session,
    get_sessions_with_transcription,
    get_sessions_with_errors,
    
    # Effects
    SessionEffects,
    SessionTimerEffects
)

# Stats 域 - 完整導出
from .stats import (
    # State
    StatsState,
    
    # Actions
    reset_stats,
    initialize_stats,
    session_created_stat,
    session_destroyed_stat,
    update_active_sessions_peak,
    wake_word_detected_stat,
    wake_word_false_positive_stat,
    recording_started_stat,
    recording_completed_stat,
    recording_failed_stat,
    transcription_requested_stat,
    transcription_completed_stat,
    transcription_failed_stat,
    audio_chunk_received_stat,
    error_occurred_stat,
    update_response_time_stat,
    update_memory_usage_stat,
    
    # Reducer
    stats_reducer,
    
    # Selectors
    get_stats_state,
    get_sessions_created,
    get_sessions_destroyed,
    get_active_sessions_peak,
    get_wake_words_detected,
    get_wake_word_false_positives,
    get_recordings_completed,
    get_transcriptions_completed,
    get_total_errors,
    get_errors_by_type,
    get_current_active_sessions,
    get_wake_word_accuracy,
    get_wake_word_average_confidence,
    get_recording_success_rate,
    get_recording_failure_rate,
    get_transcription_success_rate,
    get_transcription_failure_rate,
    get_average_recording_duration,
    get_average_transcription_time,
    get_average_audio_chunk_size,
    get_system_health_score,
    get_most_common_error_type,
    get_error_distribution,
    get_top_error_types,
    get_stats_summary,
    get_performance_metrics,
    get_quality_metrics,
    get_usage_trends,
    get_uptime_seconds,
    get_uptime_hours,
    get_stats_started_at,
    get_last_updated_at,
    
    # Effects
    StatsEffects,
    StatsReportingEffects
)

__all__ = [
    # Store 核心 (8個)
    "ASRHubStore",
    "StoreConfig",
    "get_hub_store",
    "get_global_store",
    "configure_global_store",
    "reset_global_store",
    "initialize_asr_hub_store",
    "get_store_status",
    
    # Sessions 核心 Actions (10個)
    "FSMStateEnum",
    "SessionState",
    "create_session",
    "destroy_session",
    "start_listening",
    "wake_triggered",
    "start_recording",
    "end_recording",
    "transcription_done",
    "session_error",
    
    # Sessions 核心 Selectors (5個)
    "get_session",
    "get_active_session",
    "get_session_fsm_state",
    "get_sessions_by_state",
    "get_session_count",
    
    # Sessions Effects (1個)
    "SessionEffects",
    
    # Stats 核心 (5個)
    "StatsState",
    "initialize_stats",
    "get_stats_summary",
    "get_system_health_score",
    "StatsEffects",
]
# 總共：29 個核心導出項目（原本 260 個）