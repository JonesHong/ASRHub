"""
Stats 域的 Selectors 定義
"""

from typing import Dict, Optional, List, Tuple
from pystorex import create_selector

from .stats_state import StatsState, get_initial_stats_state


# ============================================================================
# 基礎 Selectors
# ============================================================================

def get_stats_state(state) -> StatsState:
    """獲取 stats 狀態切片"""
    if not state:
        return get_initial_stats_state()
    return state.get("stats", get_initial_stats_state())


def get_sessions_created(state) -> int:
    """獲取創建的會話總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("sessions_created", 0) if stats_state else 0


def get_sessions_destroyed(state) -> int:
    """獲取銷毀的會話總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("sessions_destroyed", 0) if stats_state else 0


def get_active_sessions_peak(state) -> int:
    """獲取並發會話峰值"""
    stats_state = get_stats_state(state)
    return stats_state.get("active_sessions_peak", 0) if stats_state else 0


def get_wake_words_detected(state) -> int:
    """獲取檢測到的喚醒詞總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("wake_words_detected", 0) if stats_state else 0


def get_wake_word_false_positives(state) -> int:
    """獲取喚醒詞誤報總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("wake_word_false_positives", 0) if stats_state else 0


def get_recordings_completed(state) -> int:
    """獲取完成的錄音總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("recordings_completed", 0) if stats_state else 0


def get_transcriptions_completed(state) -> int:
    """獲取完成的轉譯總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("transcriptions_completed", 0) if stats_state else 0


def get_total_errors(state) -> int:
    """獲取錯誤總數"""
    stats_state = get_stats_state(state)
    return stats_state.get("errors_total", 0) if stats_state else 0


def get_errors_by_type(state) -> Dict[str, int]:
    """獲取按類型分組的錯誤統計"""
    stats_state = get_stats_state(state)
    return stats_state.get("errors_by_type", {}) if stats_state else {}


# ============================================================================
# 複合 Selectors
# ============================================================================

get_current_active_sessions = create_selector(
    get_sessions_created,
    get_sessions_destroyed,
    result_fn=lambda created, destroyed: created - destroyed
)


get_wake_word_accuracy = create_selector(
    get_wake_words_detected,
    get_wake_word_false_positives,
    result_fn=lambda detected, false_positives: (
        (detected - false_positives) / detected * 100 
        if detected > 0 else 0.0
    )
)


get_wake_word_average_confidence = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("wake_word_confidence_total", 0.0) / stats.get("wake_words_detected", 0)
        if stats.get("wake_words_detected", 0) > 0 else 0.0
    )
)


get_recording_success_rate = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("recordings_completed", 0) / stats.get("recordings_started", 0) * 100
        if stats.get("recordings_started", 0) > 0 else 0.0
    )
)


get_recording_failure_rate = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("recordings_failed", 0) / stats.get("recordings_started", 0) * 100
        if stats.get("recordings_started", 0) > 0 else 0.0
    )
)


get_transcription_success_rate = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("transcriptions_completed", 0) / stats.get("transcriptions_requested", 0) * 100
        if stats.get("transcriptions_requested", 0) > 0 else 0.0
    )
)


get_transcription_failure_rate = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("transcriptions_failed", 0) / stats.get("transcriptions_requested", 0) * 100
        if stats.get("transcriptions_requested", 0) > 0 else 0.0
    )
)


get_average_recording_duration = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("total_recording_duration", 0.0) / stats.get("recordings_completed", 0)
        if stats.get("recordings_completed", 0) > 0 else 0.0
    )
)


get_average_transcription_time = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("total_transcription_time", 0.0) / stats.get("transcriptions_completed", 0)
        if stats.get("transcriptions_completed", 0) > 0 else 0.0
    )
)


get_average_audio_chunk_size = create_selector(
    get_stats_state,
    result_fn=lambda stats: (
        stats.get("total_audio_bytes", 0) / stats.get("audio_chunks_received", 0)
        if stats.get("audio_chunks_received", 0) > 0 else 0
    )
)


# ============================================================================
# 業務邏輯 Selectors
# ============================================================================

get_system_health_score = create_selector(
    get_recording_success_rate,
    get_transcription_success_rate,
    get_wake_word_accuracy,
    result_fn=lambda rec_rate, trans_rate, wake_acc: (
        (rec_rate + trans_rate + wake_acc) / 3
    )
)


get_most_common_error_type = create_selector(
    get_errors_by_type,
    result_fn=lambda errors: (
        max(errors.items(), key=lambda x: x[1])[0] 
        if errors else None
    )
)


get_error_distribution = create_selector(
    get_errors_by_type,
    get_total_errors,
    result_fn=lambda errors_by_type, total_errors: {
        error_type: (count / total_errors * 100) if total_errors > 0 else 0
        for error_type, count in errors_by_type.items()
    }
)


get_top_error_types = create_selector(
    get_errors_by_type,
    result_fn=lambda errors: sorted(
        errors.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]  # 前5名錯誤類型
)


def get_stats_summary():
    """獲取統計摘要"""
    return create_selector(
        get_stats_state,
        get_current_active_sessions,
        get_system_health_score,
        get_most_common_error_type,
        result_fn=lambda stats, active_sessions, health_score, top_error: {
            "uptime_hours": (
                (stats.get("last_updated_at", 0) - stats.get("stats_started_at", 0)) / 3600
                if stats.get("stats_started_at", 0) > 0 else 0
            ),
            "active_sessions": active_sessions,
            "total_sessions": stats.get("sessions_created", 0),
            "health_score": round(health_score, 2),
            "wake_words_detected": stats.get("wake_words_detected", 0),
            "transcriptions_completed": stats.get("transcriptions_completed", 0),
            "total_errors": stats.get("errors_total", 0),
            "most_common_error": top_error,
            "average_response_time": stats.get("average_response_time", 0.0),
            "peak_memory_usage_mb": stats.get("peak_memory_usage", 0) / (1024 * 1024) if stats.get("peak_memory_usage", 0) > 0 else 0
        }
    )


def get_performance_metrics():
    """獲取性能指標"""
    return create_selector(
        get_stats_state,
        get_average_recording_duration,
        get_average_transcription_time,
        result_fn=lambda stats, avg_rec_duration, avg_trans_time: {
            "average_response_time": stats.get("average_response_time", 0.0),
            "average_recording_duration": avg_rec_duration,
            "average_transcription_time": avg_trans_time,
            "peak_memory_usage": stats.get("peak_memory_usage", 0),
            "audio_throughput_chunks_per_minute": (
                stats.get("audio_chunks_received", 0) / (
                    (stats.get("last_updated_at", 0) - stats.get("stats_started_at", 0)) / 60
                ) if stats.get("last_updated_at", 0) > stats.get("stats_started_at", 0) else 0
            )
        }
    )


def get_quality_metrics():
    """獲取品質指標"""
    return create_selector(
        get_wake_word_accuracy,
        get_recording_success_rate,
        get_transcription_success_rate,
        get_wake_word_average_confidence,
        result_fn=lambda wake_acc, rec_rate, trans_rate, avg_conf: {
            "wake_word_accuracy": wake_acc,
            "recording_success_rate": rec_rate,
            "transcription_success_rate": trans_rate,
            "wake_word_average_confidence": avg_conf,
            "overall_quality_score": (wake_acc + rec_rate + trans_rate) / 3
        }
    )


def get_usage_trends():
    """獲取使用趨勢"""
    return create_selector(
        get_stats_state,
        result_fn=lambda stats: {
            "sessions_per_hour": (
                stats.get("sessions_created", 0) / (
                    (stats.get("last_updated_at", 0) - stats.get("stats_started_at", 0)) / 3600
                ) if stats.get("last_updated_at", 0) > stats.get("stats_started_at", 0) else 0
            ),
            "transcriptions_per_hour": (
                stats.get("transcriptions_completed", 0) / (
                    (stats.get("last_updated_at", 0) - stats.get("stats_started_at", 0)) / 3600
                ) if stats.get("last_updated_at", 0) > stats.get("stats_started_at", 0) else 0
            ),
            "errors_per_hour": (
                stats.get("errors_total", 0) / (
                    (stats.get("last_updated_at", 0) - stats.get("stats_started_at", 0)) / 3600
                ) if stats.get("last_updated_at", 0) > stats.get("stats_started_at", 0) else 0
            ),
            "peak_concurrent_sessions": stats.get("active_sessions_peak", 0)
        }
    )


# ============================================================================
# 時間相關 Selectors
# ============================================================================

get_uptime_seconds = create_selector(
    get_stats_state,
    result_fn=lambda stats: stats.get("last_updated_at", 0) - stats.get("stats_started_at", 0)
)


get_uptime_hours = create_selector(
    get_uptime_seconds,
    result_fn=lambda uptime_seconds: uptime_seconds / 3600
)


get_stats_started_at = create_selector(
    get_stats_state,
    result_fn=lambda stats: stats.get("stats_started_at", 0)
)


get_last_updated_at = create_selector(
    get_stats_state,
    result_fn=lambda stats: stats.get("last_updated_at", 0)
)