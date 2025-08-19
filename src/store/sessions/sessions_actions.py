"""
Sessions 域的 Actions 定義
"""

from pystorex import create_action
from typing import Optional, Dict, Any

from .sessions_state import FSMEvent, FSMStrategy


# ============================================================================
# Session 生命週期 Actions
# ============================================================================

create_session = create_action(
    "[Session] Create",
    lambda session_id, strategy=FSMStrategy.NON_STREAMING: {
        "session_id": session_id,  # 統一使用 session_id
        "strategy": strategy
    }
)

destroy_session = create_action(
    "[Session] Destroy",
    lambda session_id: {
        "session_id": session_id  # 統一使用 session_id
    }
)

set_active_session = create_action(
    "[Session] Set Active",
    lambda session_id: {
        "session_id": session_id  # 統一使用 session_id
    }
)

clear_active_session = create_action(
    "[Session] Clear Active"
)


# ============================================================================
# FSM 狀態轉換 Actions
# ============================================================================
def enum2action_name(event: str) -> str:
    """
    將 FSM 事件名稱轉換為 Action 名稱
    
    Args:
        event: FSM 事件名稱
    
    Returns:
        Action 名稱
    """
    return f"[Session] {event.replace('_', ' ').title()}"


# 核心事件
start_listening = create_action(
    enum2action_name(FSMEvent.START_LISTENING),
    lambda session_id, audio_format=None: {
        "session_id": session_id,
        "audio_format": audio_format  # 包含 sample_rate, channels, encoding, bits_per_sample
    }
)

upload_file = create_action(
    enum2action_name(FSMEvent.UPLOAD_FILE),
    lambda session_id: {
        "session_id": session_id
    }
)

upload_file_done = create_action(
    enum2action_name(FSMEvent.UPLOAD_FILE_DONE),
    lambda session_id: {
        "session_id": session_id
    }
)

wake_triggered = create_action(
    enum2action_name(FSMEvent.WAKE_TRIGGERED),
    lambda session_id, confidence, trigger: {
        "session_id": session_id,
        "trigger": trigger,
        "confidence": confidence
    }
)

start_recording = create_action(
    enum2action_name(FSMEvent.START_RECORDING),
    lambda session_id, strategy: {
        "session_id": session_id,
        "strategy": strategy
    }
)

end_recording = create_action(
    enum2action_name(FSMEvent.END_RECORDING),
    lambda session_id, trigger, duration: {
        "session_id": session_id,
        "trigger": trigger,
        "duration": duration
    }
)


begin_transcription = create_action(
    enum2action_name(FSMEvent.BEGIN_TRANSCRIPTION),
    lambda session_id: {
        "session_id": session_id
    }
)

transcription_done = create_action(
    enum2action_name(FSMEvent.TRANSCRIPTION_DONE),
    lambda session_id, result: {
        "session_id": session_id,
        "result": result
    }
)

start_asr_streaming = create_action(
    enum2action_name(FSMEvent.START_ASR_STREAMING),
    lambda session_id: {
        "session_id": session_id
    }
)

end_asr_streaming = create_action(
    enum2action_name(FSMEvent.END_ASR_STREAMING),
    lambda session_id: {
        "session_id": session_id
    }
)

# LLM/TTS 事件 (Inbound)
llm_reply_started = create_action(
    enum2action_name(FSMEvent.LLM_REPLY_STARTED),
    lambda session_id: {
        "session_id": session_id
    }
)

llm_reply_finished = create_action(
    enum2action_name(FSMEvent.LLM_REPLY_FINISHED),
    lambda session_id: {
        "session_id": session_id
    }
)

tts_playback_started = create_action(
    enum2action_name(FSMEvent.TTS_PLAYBACK_STARTED),
    lambda session_id: {
        "session_id": session_id
    }
)

tts_playback_finished = create_action(
    enum2action_name(FSMEvent.TTS_PLAYBACK_FINISHED),
    lambda session_id: {
        "session_id": session_id
    }
)
# 打斷事件
interrupt_reply = create_action(
    enum2action_name(FSMEvent.INTERRUPT_REPLY),
    lambda session_id: {
        "session_id": session_id
    }
)

# 系統事件
timeout = create_action(
    enum2action_name(FSMEvent.TIMEOUT),
    lambda session_id: {
        "session_id": session_id
    }
)

reset = create_action(
    enum2action_name(FSMEvent.RESET),
    lambda session_id: {
        "session_id": session_id
    }
)

error = create_action(
    enum2action_name(FSMEvent.ERROR),
    lambda session_id, error=None: {
        "session_id": session_id,
        "error": error  # 統一錯誤處理
    }
)

recover = create_action(
    enum2action_name(FSMEvent.RECOVER),
    lambda session_id: {
        "session_id": session_id
    }
)


# ============================================================================
# 音訊處理 Actions（Session 相關）
# ============================================================================

audio_chunk_received = create_action(
    "[Session] Audio Chunk Received",
    lambda session_id, chunk_size=0, timestamp=None: {
        "session_id": session_id,
        "chunk_size": chunk_size,  # 只傳遞大小，不傳遞實際音訊數據
        "timestamp": timestamp
    }
)

clear_audio_buffer = create_action(
    "[Session] Clear Audio Buffer",
    lambda session_id: {
        "session_id": session_id
    }
)


# ============================================================================
# 錯誤處理 Actions (已整合到系統事件)
# ============================================================================

# 保留 clear_error 功能
clear_error = create_action(
    "[Session] Clear Error",
    lambda session_id: {
        "session_id": session_id
    }
)


# ============================================================================
# Session 狀態管理 Actions
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

# ============================================================================
# 喚醒詞 (Wake Word) Actions  
# ============================================================================

# 注意：wake_triggered 已在 FSM 事件中定義
# 這是額外的喚醒管理 action
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

# ============================================================================
# 模式切換 (Mode Switching) Actions
# ============================================================================

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

# 移除重複的生命週期 Actions（已在頂部定義）

# ============================================================================
# VAD (Voice Activity Detection) Actions
# ============================================================================
speech_detected = create_action(
    "[Session] Speech Detected",
    lambda session_id, confidence=None, timestamp=None: {
        "session_id": session_id,
        "confidence": confidence,
        "timestamp": timestamp
    }
)

# 語音結束，靜音開始（VAD 偵測到從語音變為靜音）
silence_started = create_action(
    "[Session] Silence Started",  
    lambda session_id, timestamp=None: {
        "session_id": session_id,
        "timestamp": timestamp
    }
)

# ============================================================================
# 錄音控制 Actions
# ============================================================================

# 注意：start_recording 和 end_recording 已在 FSM 事件中定義
# 這裡是額外的狀態通知 actions
recording_status_changed = create_action(
    "[Session] Recording Status Changed",
    lambda session_id, status, trigger=None, reason=None: {
        "session_id": session_id,
        "status": status,  # "started" or "stopped"
        "trigger": trigger,
        "reason": reason
    }
)

# ============================================================================
# 倒數計時 (Countdown) Actions
# ============================================================================

# 開始倒數（通常在 silence_started 後觸發）
countdown_started = create_action(
    "[Session] Countdown Started",
    lambda session_id, duration: {
        "session_id": session_id,
        "duration": duration
    }
)

# 倒數取消（偵測到語音恢復時）
countdown_cancelled = create_action(
    "[Session] Countdown Cancelled",
    lambda session_id, reason="speech_detected": {
        "session_id": session_id,
        "reason": reason  # "speech_detected", "manual", etc.
    }
)

# 倒數結束（達到設定的靜音閾值時間）
countdown_finished = create_action(
    "[Session] Countdown Finished",
    lambda session_id: {
        "session_id": session_id
    }
)

# ============================================================================
# 轉譯 (Transcription) Actions
# ============================================================================

# 注意：begin_transcription 和 transcription_done 已在 FSM 事件中定義
request_partial_transcription = create_action(
    "[Session] Request Partial Transcription",
    lambda session_id, audio_segment: {
        "session_id": session_id,
        "audio_segment": audio_segment
    }
)