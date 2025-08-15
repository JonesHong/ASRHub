"""
Stats 域的 Actions 定義
"""

from pystorex import create_action


# ============================================================================
# 統計重置和初始化 Actions
# ============================================================================

reset_stats = create_action("[Stats] Reset")

initialize_stats = create_action("[Stats] Initialize")


# ============================================================================
# Session 統計 Actions
# ============================================================================

session_created_stat = create_action(
    "[Stats] Session Created",
    lambda session_id: {
        "session_id": session_id
    }
)

session_destroyed_stat = create_action(
    "[Stats] Session Destroyed", 
    lambda session_id: {
        "session_id": session_id
    }
)

update_active_sessions_peak = create_action(
    "[Stats] Update Active Sessions Peak",
    lambda count: {
        "count": count
    }
)


# ============================================================================
# 喚醒詞統計 Actions
# ============================================================================

wake_word_detected_stat = create_action(
    "[Stats] Wake Word Detected",
    lambda session_id, confidence, trigger_type: {
        "session_id": session_id,
        "confidence": confidence,
        "trigger_type": trigger_type
    }
)

wake_word_false_positive_stat = create_action(
    "[Stats] Wake Word False Positive",
    lambda session_id, confidence: {
        "session_id": session_id,
        "confidence": confidence
    }
)


# ============================================================================
# 錄音統計 Actions
# ============================================================================

recording_started_stat = create_action(
    "[Stats] Recording Started",
    lambda session_id, strategy: {
        "session_id": session_id,
        "strategy": strategy
    }
)

recording_completed_stat = create_action(
    "[Stats] Recording Completed",
    lambda session_id, duration, trigger: {
        "session_id": session_id,
        "duration": duration,
        "trigger": trigger
    }
)

recording_failed_stat = create_action(
    "[Stats] Recording Failed",
    lambda session_id, error: {
        "session_id": session_id,
        "error": error
    }
)


# ============================================================================
# 轉譯統計 Actions
# ============================================================================

transcription_requested_stat = create_action(
    "[Stats] Transcription Requested",
    lambda session_id, provider: {
        "session_id": session_id,
        "provider": provider
    }
)

transcription_completed_stat = create_action(
    "[Stats] Transcription Completed",
    lambda session_id, duration, result_length: {
        "session_id": session_id,
        "duration": duration,
        "result_length": result_length
    }
)

transcription_failed_stat = create_action(
    "[Stats] Transcription Failed",
    lambda session_id, error: {
        "session_id": session_id,
        "error": error
    }
)


# ============================================================================
# 音訊統計 Actions
# ============================================================================

audio_chunk_received_stat = create_action(
    "[Stats] Audio Chunk Received",
    lambda session_id, chunk_size: {
        "session_id": session_id,
        "chunk_size": chunk_size
    }
)


# ============================================================================
# 錯誤統計 Actions
# ============================================================================

error_occurred_stat = create_action(
    "[Stats] Error Occurred",
    lambda session_id, error_type, error_message: {
        "session_id": session_id,
        "error_type": error_type,
        "error_message": error_message
    }
)


# ============================================================================
# 性能統計 Actions
# ============================================================================

update_response_time_stat = create_action(
    "[Stats] Update Response Time",
    lambda operation, duration: {
        "operation": operation,
        "duration": duration
    }
)

update_memory_usage_stat = create_action(
    "[Stats] Update Memory Usage",
    lambda usage: {
        "usage": usage
    }
)