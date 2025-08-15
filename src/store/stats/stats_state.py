"""
Stats 域的狀態定義
"""

from typing_extensions import TypedDict
from typing import Dict


class StatsState(TypedDict):
    """統計數據狀態"""
    # Session 相關統計
    sessions_created: int
    sessions_destroyed: int
    active_sessions_peak: int
    
    # 喚醒詞統計
    wake_words_detected: int
    wake_word_false_positives: int
    wake_word_confidence_total: float
    
    # 錄音統計
    recordings_started: int
    recordings_completed: int
    recordings_failed: int
    total_recording_duration: float
    
    # 轉譯統計
    transcriptions_requested: int
    transcriptions_completed: int
    transcriptions_failed: int
    total_transcription_time: float
    
    # 音訊統計
    audio_chunks_received: int
    total_audio_bytes: int
    
    # 錯誤統計
    errors_total: int
    errors_by_type: Dict[str, int]
    
    # 性能統計
    average_response_time: float
    peak_memory_usage: int
    
    # 時間戳
    stats_started_at: float
    last_updated_at: float


def get_initial_stats_state() -> StatsState:
    """獲取初始的 Stats 域狀態"""
    from src.utils.time_provider import TimeProvider
    current_time = TimeProvider.now()
    
    return StatsState(
        sessions_created=0,
        sessions_destroyed=0,
        active_sessions_peak=0,
        wake_words_detected=0,
        wake_word_false_positives=0,
        wake_word_confidence_total=0.0,
        recordings_started=0,
        recordings_completed=0,
        recordings_failed=0,
        total_recording_duration=0.0,
        transcriptions_requested=0,
        transcriptions_completed=0,
        transcriptions_failed=0,
        total_transcription_time=0.0,
        audio_chunks_received=0,
        total_audio_bytes=0,
        errors_total=0,
        errors_by_type={},
        average_response_time=0.0,
        peak_memory_usage=0,
        stats_started_at=current_time,
        last_updated_at=current_time
    )