"""
Sessions 域的 Reducer 實現

重構後的版本，使用模組化的 handlers
"""

from pystorex import create_reducer, on

# 匯入 handlers
from .handlers import (
    # Session 生命週期
    handle_create_session,
    handle_destroy_session,
    handle_set_active_session,
    handle_clear_active_session,
    handle_update_session_metadata,
    handle_session_error,
    handle_clear_error,
    # FSM 轉換
    handle_fsm_transition,
    # 音訊處理
    handle_audio_chunk,
    handle_clear_audio_buffer,
    handle_audio_metadata,
    # 工具函數
    get_initial_state
)

# 匯入 actions
from .sessions_actions import (
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
    llm_reply_started,
    llm_reply_finished,
    tts_playback_started,
    tts_playback_finished,
    interrupt_reply,
    timeout,
    error,
    fsm_reset,
    audio_chunk_received,
    clear_audio_buffer,
    audio_metadata,
    session_error,
    clear_error,
    update_session_metadata,
)


# ============================================================================
# Sessions Reducer
# ============================================================================

sessions_reducer = create_reducer(
    # 初始狀態
    get_initial_state(),
    # Session 管理
    on(create_session.type, handle_create_session),
    on(destroy_session.type, handle_destroy_session),
    on(set_active_session.type, handle_set_active_session),
    on(clear_active_session.type, handle_clear_active_session),
    # FSM 狀態轉換
    on(start_listening.type, handle_fsm_transition),
    on(wake_triggered.type, handle_fsm_transition),
    on(start_recording.type, handle_fsm_transition),
    on(end_recording.type, handle_fsm_transition),
    on(start_asr_streaming.type, handle_fsm_transition),
    on(end_asr_streaming.type, handle_fsm_transition),
    on(begin_transcription.type, handle_fsm_transition),
    on(transcription_done.type, handle_fsm_transition),
    on(fsm_reset.type, handle_fsm_transition),
    on(llm_reply_started.type, handle_fsm_transition),
    on(llm_reply_finished.type, handle_fsm_transition),
    on(tts_playback_started.type, handle_fsm_transition),
    on(tts_playback_finished.type, handle_fsm_transition),
    on(interrupt_reply.type, handle_fsm_transition),
    # 音訊處理
    on(audio_chunk_received.type, handle_audio_chunk),
    on(clear_audio_buffer.type, handle_clear_audio_buffer),
    on(audio_metadata.type, handle_audio_metadata),
    # Metadata 更新
    on(update_session_metadata.type, handle_update_session_metadata),
    # 錯誤處理
    on(session_error.type, handle_session_error),
    on(clear_error.type, handle_clear_error),
)