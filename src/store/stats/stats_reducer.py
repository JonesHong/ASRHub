"""
Stats 域的 Reducer 實現
"""

from typing import Dict
from pystorex import create_reducer, on
from src.utils.time_provider import TimeProvider

from .stats_state import StatsState
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


def _get_initial_stats_state() -> StatsState:
    """獲取初始統計狀態"""
    current_time = TimeProvider.now()
    return {
        # Session 相關統計
        "sessions_created": 0,
        "sessions_destroyed": 0,
        "active_sessions_peak": 0,
        
        # 喚醒詞統計
        "wake_words_detected": 0,
        "wake_word_false_positives": 0,
        "wake_word_confidence_total": 0.0,
        
        # 錄音統計
        "recordings_started": 0,
        "recordings_completed": 0,
        "recordings_failed": 0,
        "total_recording_duration": 0.0,
        
        # 轉譯統計
        "transcriptions_requested": 0,
        "transcriptions_completed": 0,
        "transcriptions_failed": 0,
        "total_transcription_time": 0.0,
        
        # 音訊統計
        "audio_chunks_received": 0,
        "total_audio_bytes": 0,
        
        # 錯誤統計
        "errors_total": 0,
        "errors_by_type": {},
        
        # 性能統計
        "average_response_time": 0.0,
        "peak_memory_usage": 0,
        
        # 時間戳
        "stats_started_at": current_time,
        "last_updated_at": current_time
    }


def _update_timestamp(state: StatsState) -> StatsState:
    """更新時間戳"""
    return {**state, "last_updated_at": TimeProvider.now()}


def _calculate_average_response_time(
    current_avg: float, 
    current_count: int, 
    new_duration: float
) -> float:
    """計算平均響應時間"""
    if current_count == 0:
        return new_duration
    return (current_avg * current_count + new_duration) / (current_count + 1)


def _calculate_wake_word_confidence_average(state: StatsState) -> float:
    """計算喚醒詞平均置信度"""
    total_detections = state.get("wake_words_detected", 0)
    if total_detections == 0:
        return 0.0
    return state.get("wake_word_confidence_total", 0) / total_detections


# ============================================================================
# Handler Functions
# ============================================================================

def handle_reset_stats(state: StatsState, action) -> StatsState:
    """處理重置統計"""
    return _get_initial_stats_state()


def handle_initialize_stats(state: StatsState, action) -> StatsState:
    """處理初始化統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp(state)


def handle_session_created(state: StatsState, action) -> StatsState:
    """處理會話創建統計"""
    # 確保狀態不為 None
    if state is None:
        state = _get_initial_stats_state()
    
    return _update_timestamp({
        **state,
        "sessions_created": state.get("sessions_created", 0) + 1
    })


def handle_session_destroyed(state: StatsState, action) -> StatsState:
    """處理會話銷毀統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "sessions_destroyed": state.get("sessions_destroyed", 0) + 1
    })


def handle_active_sessions_peak(state: StatsState, action) -> StatsState:
    """處理活躍會話峰值更新"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "active_sessions_peak": max(
            state.get("active_sessions_peak", 0),
            action.payload["count"]
        )
    })


def handle_wake_word_detected(state: StatsState, action) -> StatsState:
    """處理喚醒詞檢測統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "wake_words_detected": state.get("wake_words_detected", 0) + 1,
        "wake_word_confidence_total": state.get("wake_word_confidence_total", 0) + action.payload["confidence"]
    })


def handle_wake_word_false_positive(state: StatsState, action) -> StatsState:
    """處理喚醒詞誤報統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "wake_word_false_positives": state.get("wake_word_false_positives", 0) + 1
    })


def handle_recording_started(state: StatsState, action) -> StatsState:
    """處理錄音開始統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "recordings_started": state.get("recordings_started", 0) + 1
    })


def handle_recording_completed(state: StatsState, action) -> StatsState:
    """處理錄音完成統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "recordings_completed": state.get("recordings_completed", 0) + 1,
        "total_recording_duration": state.get("total_recording_duration", 0) + action.payload["duration"]
    })


def handle_recording_failed(state: StatsState, action) -> StatsState:
    """處理錄音失敗統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "recordings_failed": state.get("recordings_failed", 0) + 1
    })


def handle_transcription_requested(state: StatsState, action) -> StatsState:
    """處理轉譯請求統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "transcriptions_requested": state.get("transcriptions_requested", 0) + 1
    })


def handle_transcription_completed(state: StatsState, action) -> StatsState:
    """處理轉譯完成統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "transcriptions_completed": state.get("transcriptions_completed", 0) + 1,
        "total_transcription_time": state.get("total_transcription_time", 0) + action.payload["duration"]
    })


def handle_transcription_failed(state: StatsState, action) -> StatsState:
    """處理轉譯失敗統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "transcriptions_failed": state.get("transcriptions_failed", 0) + 1
    })


def handle_audio_chunk_received(state: StatsState, action) -> StatsState:
    """處理音訊資料接收統計"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "audio_chunks_received": state.get("audio_chunks_received", 0) + 1,
        "total_audio_bytes": state.get("total_audio_bytes", 0) + action.payload["chunk_size"]
    })


def handle_error_occurred(state: StatsState, action) -> StatsState:
    """處理錯誤發生統計"""
    if state is None:
        state = _get_initial_stats_state()
    error_type = action.payload["error_type"]
    errors_by_type = state.get("errors_by_type", {})
    
    return _update_timestamp({
        **state,
        "errors_total": state.get("errors_total", 0) + 1,
        "errors_by_type": {
            **errors_by_type,
            error_type: errors_by_type.get(error_type, 0) + 1
        }
    })


def handle_update_response_time(state: StatsState, action) -> StatsState:
    """處理響應時間更新"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "average_response_time": _calculate_average_response_time(
            state.get("average_response_time", 0),
            # 使用總操作數作為計數
            state.get("transcriptions_completed", 0) + state.get("recordings_completed", 0),
            action.payload["duration"]
        )
    })


def handle_update_memory_usage(state: StatsState, action) -> StatsState:
    """處理記憶體使用更新"""
    if state is None:
        state = _get_initial_stats_state()
    return _update_timestamp({
        **state,
        "peak_memory_usage": max(
            state.get("peak_memory_usage", 0),
            action.payload["usage"]
        )
    })


# ============================================================================
# Reducer 實現
# ============================================================================

stats_reducer = create_reducer(
    _get_initial_stats_state(),
    
    # 統計重置和初始化
    on(reset_stats.type, handle_reset_stats),
    on(initialize_stats.type, handle_initialize_stats),
    
    # Session 統計
    on(session_created_stat.type, handle_session_created),
    on(session_destroyed_stat.type, handle_session_destroyed),
    on(update_active_sessions_peak.type, handle_active_sessions_peak),
    
    # 喚醒詞統計
    on(wake_word_detected_stat.type, handle_wake_word_detected),
    on(wake_word_false_positive_stat.type, handle_wake_word_false_positive),
    
    # 錄音統計
    on(recording_started_stat.type, handle_recording_started),
    on(recording_completed_stat.type, handle_recording_completed),
    on(recording_failed_stat.type, handle_recording_failed),
    
    # 轉譯統計
    on(transcription_requested_stat.type, handle_transcription_requested),
    on(transcription_completed_stat.type, handle_transcription_completed),
    on(transcription_failed_stat.type, handle_transcription_failed),
    
    # 音訊統計
    on(audio_chunk_received_stat.type, handle_audio_chunk_received),
    
    # 錯誤統計
    on(error_occurred_stat.type, handle_error_occurred),
    
    # 性能統計
    on(update_response_time_stat.type, handle_update_response_time),
    on(update_memory_usage_stat.type, handle_update_memory_usage)
)