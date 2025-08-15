"""
Stats 域的公共 API
"""

# State 定義
from .stats_state import StatsState

# Actions
from .stats_actions import (
    # 統計重置和初始化
    reset_stats,
    initialize_stats,
    
    # Session 統計
    session_created_stat,
    session_destroyed_stat,
    update_active_sessions_peak,
    
    # 喚醒詞統計
    wake_word_detected_stat,
    wake_word_false_positive_stat,
    
    # 錄音統計
    recording_started_stat,
    recording_completed_stat,
    recording_failed_stat,
    
    # 轉譯統計
    transcription_requested_stat,
    transcription_completed_stat,
    transcription_failed_stat,
    
    # 音訊統計
    audio_chunk_received_stat,
    
    # 錯誤統計
    error_occurred_stat,
    
    # 性能統計
    update_response_time_stat,
    update_memory_usage_stat
)

# Reducer
from .stats_reducer import stats_reducer

# Selectors
from .stats_selectors import (
    # 基礎 selectors
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
    
    # 複合 selectors
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
    
    # 業務邏輯 selectors
    get_system_health_score,
    get_most_common_error_type,
    get_error_distribution,
    get_top_error_types,
    get_stats_summary,
    get_performance_metrics,
    get_quality_metrics,
    get_usage_trends,
    
    # 時間相關 selectors
    get_uptime_seconds,
    get_uptime_hours,
    get_stats_started_at,
    get_last_updated_at
)

# Effects
from .stats_effects import (
    StatsEffects,
    StatsReportingEffects
)

__all__ = [
    # State
    "StatsState",
    
    # Actions
    "reset_stats",
    "initialize_stats",
    "session_created_stat",
    "session_destroyed_stat",
    "update_active_sessions_peak",
    "wake_word_detected_stat",
    "wake_word_false_positive_stat",
    "recording_started_stat",
    "recording_completed_stat",
    "recording_failed_stat",
    "transcription_requested_stat",
    "transcription_completed_stat",
    "transcription_failed_stat",
    "audio_chunk_received_stat",
    "error_occurred_stat",
    "update_response_time_stat",
    "update_memory_usage_stat",
    
    # Reducer
    "stats_reducer",
    
    # Selectors
    "get_stats_state",
    "get_sessions_created",
    "get_sessions_destroyed",
    "get_active_sessions_peak",
    "get_wake_words_detected",
    "get_wake_word_false_positives",
    "get_recordings_completed",
    "get_transcriptions_completed",
    "get_total_errors",
    "get_errors_by_type",
    "get_current_active_sessions",
    "get_wake_word_accuracy",
    "get_wake_word_average_confidence",
    "get_recording_success_rate",
    "get_recording_failure_rate",
    "get_transcription_success_rate",
    "get_transcription_failure_rate",
    "get_average_recording_duration",
    "get_average_transcription_time",
    "get_average_audio_chunk_size",
    "get_system_health_score",
    "get_most_common_error_type",
    "get_error_distribution",
    "get_top_error_types",
    "get_stats_summary",
    "get_performance_metrics",
    "get_quality_metrics",
    "get_usage_trends",
    "get_uptime_seconds",
    "get_uptime_hours",
    "get_stats_started_at",
    "get_last_updated_at",
    
    # Effects
    "StatsEffects",
    "StatsReportingEffects"
]