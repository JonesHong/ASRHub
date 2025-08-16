"""
Sessions 域的 Actions 定義
"""

from pystorex import create_action
from typing import Optional, Dict, Any
from .sessions_state import FSMStrategy


# ============================================================================
# Session 管理 Actions
# ============================================================================

create_session = create_action(
    "[Session] Create",
    lambda session_id, strategy=FSMStrategy.NON_STREAMING: {
        "id": session_id,
        "strategy": strategy
    }
)

destroy_session = create_action(
    "[Session] Destroy",
    lambda session_id: {
        "id": session_id
    }
)

set_active_session = create_action(
    "[Session] Set Active",
    lambda session_id: {
        "id": session_id
    }
)

clear_active_session = create_action(
    "[Session] Clear Active"
)


# ============================================================================
# FSM 狀態轉換 Actions
# ============================================================================

start_listening = create_action(
    "[Session] Start Listening",
    lambda session_id: {
        "session_id": session_id
    }
)

wake_triggered = create_action(
    "[Session] Wake Triggered",
    lambda session_id, confidence, trigger: {
        "session_id": session_id,
        "trigger": trigger,
        "confidence": confidence
    }
)

start_recording = create_action(
    "[Session] Start Recording",
    lambda session_id, strategy: {
        "session_id": session_id,
        "strategy": strategy
    }
)

end_recording = create_action(
    "[Session] End Recording",
    lambda session_id, trigger, duration: {
        "session_id": session_id,
        "trigger": trigger,
        "duration": duration
    }
)

start_streaming = create_action(
    "[Session] Start Streaming",
    lambda session_id: {
        "session_id": session_id
    }
)

end_streaming = create_action(
    "[Session] End Streaming",
    lambda session_id: {
        "session_id": session_id
    }
)

begin_transcription = create_action(
    "[Session] Begin Transcription",
    lambda session_id: {
        "session_id": session_id
    }
)

transcription_done = create_action(
    "[Session] Transcription Done",
    lambda session_id, result: {
        "session_id": session_id,
        "result": result
    }
)

reset_fsm = create_action(
    "[Session] Reset FSM",
    lambda session_id: {
        "session_id": session_id
    }
)


# ============================================================================
# 音訊處理 Actions（Session 相關）
# ============================================================================

audio_chunk_received = create_action(
    "[Session] Audio Chunk Received",
    lambda session_id, chunk_size: {
        "session_id": session_id,
        "chunk_size": chunk_size
    }
)

clear_audio_buffer = create_action(
    "[Session] Clear Audio Buffer",
    lambda session_id: {
        "session_id": session_id
    }
)


# ============================================================================
# 錯誤處理 Actions
# ============================================================================

session_error = create_action(
    "[Session] Error",
    lambda session_id, error: {
        "session_id": session_id,
        "error": error
    }
)

clear_session_error = create_action(
    "[Session] Clear Error",
    lambda session_id: {
        "session_id": session_id
    }
)


# ============================================================================
# 新增的 Session 管理 Actions (取代 SessionManager 功能)
# ============================================================================

update_session_state = create_action(
    "[Session] Update State",
    lambda session_id, state: {
        "session_id": session_id,
        "state": state  # IDLE, LISTENING, BUSY
    }
)

update_session_metadata = create_action(
    "[Session] Update Metadata",
    lambda session_id, metadata: {
        "session_id": session_id,
        "metadata": metadata
    }
)

update_session_config = create_action(
    "[Session] Update Config",
    lambda session_id, pipeline_config=None, provider_config=None: {
        "session_id": session_id,
        "pipeline_config": pipeline_config,
        "provider_config": provider_config
    }
)

# 喚醒詞相關 Actions
wake_session = create_action(
    "[Session] Wake",
    lambda session_id, source="wake_word", wake_timeout=None: {
        "session_id": session_id,
        "source": source,  # wake_word, ui, visual
        "wake_timeout": wake_timeout
    }
)

clear_wake_state = create_action(
    "[Session] Clear Wake State",
    lambda session_id: {
        "session_id": session_id
    }
)

update_session_priority = create_action(
    "[Session] Update Priority",
    lambda session_id, priority: {
        "session_id": session_id,
        "priority": priority
    }
)

# 模式相關 Actions
switch_mode = create_action(
    "[Session] Switch Mode",
    lambda session_id, new_mode: {
        "session_id": session_id,
        "new_mode": new_mode
    }
)

mode_switched = create_action(
    "[Session] Mode Switched",
    lambda session_id, new_mode: {
        "session_id": session_id,
        "new_mode": new_mode
    }
)

# 生命週期 Actions
session_created = create_action(
    "[Session] Created",
    lambda session_id: {
        "session_id": session_id
    }
)

session_destroyed = create_action(
    "[Session] Destroyed",
    lambda session_id: {
        "session_id": session_id
    }
)

# VAD 相關 Actions
speech_detected = create_action(
    "[Session] Speech Detected",
    lambda session_id, confidence=None, timestamp=None: {
        "session_id": session_id,
        "confidence": confidence,
        "timestamp": timestamp
    }
)

silence_detected = create_action(
    "[Session] Silence Detected",
    lambda session_id, duration=None, timestamp=None: {
        "session_id": session_id,
        "duration": duration,
        "timestamp": timestamp
    }
)

# 錄音控制 Actions
recording_started = create_action(
    "[Session] Recording Started",
    lambda session_id, trigger=None: {
        "session_id": session_id,
        "trigger": trigger
    }
)

recording_stopped = create_action(
    "[Session] Recording Stopped",
    lambda session_id, reason=None: {
        "session_id": session_id,
        "reason": reason
    }
)

countdown_started = create_action(
    "[Session] Countdown Started",
    lambda session_id, duration: {
        "session_id": session_id,
        "duration": duration
    }
)

countdown_cancelled = create_action(
    "[Session] Countdown Cancelled",
    lambda session_id: {
        "session_id": session_id
    }
)

# 部分轉譯 Action
request_partial_transcription = create_action(
    "[Session] Request Partial Transcription",
    lambda session_id, audio_segment: {
        "session_id": session_id,
        "audio_segment": audio_segment
    }
)