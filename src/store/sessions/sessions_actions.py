"""
Sessions 域的 Actions 定義
"""

from pystorex import create_action
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