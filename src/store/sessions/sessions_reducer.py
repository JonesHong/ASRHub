"""
Sessions Reducer for PyStoreX Store

處理所有 Session 相關的 Actions，更新 State。
使用 immutables.Map 確保狀態不可變性。
"""

import time
from typing import Dict, Any
from immutables import Map
from pystorex import create_reducer, on
from pystorex.map_utils import batch_update, to_immutable

from src.store.sessions.sessions_state import (
    sessions_initial_state,
    create_initial_session_state,
    SessionStatus,
    AudioConfig
)
from src.store.sessions.sessions_action import (
    create_session,
    delete_session,
    session_expired,
    reset_session,
    receive_audio_chunk,
    clear_audio_buffer,
    upload_started,
    upload_completed,
    start_listening,
    wake_activated,
    wake_deactivated,
    vad_speech_detected,
    vad_silence_detected,
    silence_timeout,
    record_started,
    record_stopped,
    start_asr_sound_effect,
    stop_asr_sound_effect,
    transcribe_started,
    transcribe_done,
    asr_stream_started,
    asr_stream_stopped,
    llm_reply_started,
    llm_replying,
    llm_reply_completed,
    llm_reply_timeout,
    tts_playback_started,
    tts_playing,
    tts_playback_completed,
    tts_playback_timeout,
    reply_interrupted,
    error_occurred,
    error_raised,
    error_reported
)
from src.utils.id_provider import new_id


# === Helper Functions ===

def get_session(state: Map, session_id: str) -> Map:
    """取得特定 session 的狀態"""
    sessions = state.get("sessions", {})
    if isinstance(sessions, Map):
        return sessions.get(session_id)
    return sessions.get(session_id) if session_id in sessions else None


def update_session(state: Map, session_id: str, updates: Dict[str, Any]) -> Map:
    """更新特定 session 的狀態"""
    sessions = state.get("sessions", {})
    session = get_session(state, session_id)
    
    if not session:
        return state
    
    # 更新 updated_at
    updates["updated_at"] = time.time()
    
    # 更新 session
    if isinstance(session, Map):
        updated_session = batch_update(session, updates)
    else:
        updated_session = {**session, **updates}
        updated_session = to_immutable(updated_session)
    
    # 更新 sessions
    if isinstance(sessions, Map):
        updated_sessions = sessions.set(session_id, updated_session)
    else:
        updated_sessions = {**sessions, session_id: updated_session}
        updated_sessions = to_immutable(updated_sessions)
    
    return state.set("sessions", updated_sessions)


def add_to_active(state: Map, session_id: str) -> Map:
    """將 session 加入活躍列表"""
    active_ids = state.get("active_session_ids", ())
    if session_id not in active_ids:
        # 如果 active_ids 是 tuple，轉換為 tuple 連接
        if isinstance(active_ids, tuple):
            new_active = active_ids + (session_id,)
        else:
            new_active = list(active_ids) + [session_id]
        return state.set("active_session_ids", to_immutable(new_active))
    return state


def remove_from_active(state: Map, session_id: str) -> Map:
    """從活躍列表移除 session"""
    active_ids = state.get("active_session_ids", ())
    if session_id in active_ids:
        # 如果 active_ids 是 tuple，使用 tuple comprehension
        if isinstance(active_ids, tuple):
            new_active = tuple(id for id in active_ids if id != session_id)
        else:
            new_active = [id for id in active_ids if id != session_id]
        return state.set("active_session_ids", to_immutable(new_active))
    return state


# === Action Handlers ===

def handle_create_session(state: Map, action) -> Map:
    """處理建立 session
    
    注意：FSM 實例的創建是在 SessionEffects 中處理，
    這裡只處理純粹的狀態更新。
    
    create_session action 只需要 strategy 參數
    audio_config 會在 START_LISTENING 時設定
    """
    session_id = new_id()
    
    # 從 payload 取得 strategy
    # create_session action 現在只傳送 strategy (不是 dict)
    strategy = action.payload if action.payload else "non_streaming"
    
    # 建立新 session
    new_session = create_initial_session_state(session_id, strategy)
    
    # audio_config 會在 START_LISTENING 時設定，這裡不處理
    
    new_session_map = to_immutable(new_session)
    
    # 更新 sessions
    sessions = state.get("sessions", Map())
    if not isinstance(sessions, Map):
        sessions = to_immutable(sessions)
    updated_sessions = sessions.set(session_id, new_session_map)
    
    # 更新統計
    total_created = state.get("total_created", 0) + 1
    
    return batch_update(state, {
        "sessions": updated_sessions,
        "total_created": total_created
    })


def handle_delete_session(state: Map, action) -> Map:
    """處理刪除 session"""
    session_id = action.payload
    
    sessions = state.get("sessions", Map())
    if session_id not in sessions:
        return state
    
    # 移除 session
    if isinstance(sessions, Map):
        updated_sessions = sessions.delete(session_id)
    else:
        updated_sessions = {k: v for k, v in sessions.items() if k != session_id}
        updated_sessions = to_immutable(updated_sessions)
    
    # 從活躍列表移除
    state = remove_from_active(state, session_id)
    
    # 更新統計
    total_deleted = state.get("total_deleted", 0) + 1
    
    return batch_update(state, {
        "sessions": updated_sessions,
        "total_deleted": total_deleted
    })


def handle_receive_audio_chunk(state: Map, action) -> Map:
    """處理接收音訊塊"""
    payload = action.payload
    session_id = payload.get("session_id")
    
    session = get_session(state, session_id)
    if not session:
        return state
    
    # 更新統計
    chunks_received = session.get("audio_chunks_received", 0) + 1
    
    return update_session(state, session_id, {
        "audio_chunks_received": chunks_received
    })


def handle_start_listening(state: Map, action) -> Map:
    """處理開始監聽"""
    payload = action.payload
    session_id = payload.get("session_id")
    
    # 建立音訊配置
    audio_config = AudioConfig(
        sample_rate=payload.get("sample_rate", 16000),
        channels=payload.get("channels", 1),
        format=payload.get("format", "int16")
    )
    
    # 更新狀態
    state = update_session(state, session_id, {
        "status": SessionStatus.LISTENING,
        "audio_config": to_immutable(audio_config)
    })
    
    # 加入活躍列表
    return add_to_active(state, session_id)


def handle_wake_activated(state: Map, action) -> Map:
    """處理喚醒啟用"""
    payload = action.payload
    session_id = payload.get("session_id")
    wake_source = payload.get("source")
    wake_timestamp = payload.get("timestamp")  # 新增：喚醒時間戳
    
    state = update_session(state, session_id, {
        "is_wake_active": True,
        "wake_source": wake_source,
        "wake_timestamp": wake_timestamp,  # 儲存喚醒時間點
        "status": SessionStatus.LISTENING  # 更新狀態為監聽中
    })
    
    return add_to_active(state, session_id)


def handle_wake_deactivated(state: Map, action) -> Map:
    """處理喚醒停用"""
    payload = action.payload
    session_id = payload.get("session_id")
    
    return update_session(state, session_id, {
        "is_wake_active": False,
        "wake_source": None
    })


def handle_vad_speech_detected(state: Map, action) -> Map:
    """處理 VAD 偵測到語音"""
    session_id = action.payload
    
    return update_session(state, session_id, {
        "is_vad_speech": True
    })


def handle_vad_silence_detected(state: Map, action) -> Map:
    """處理 VAD 偵測到靜音"""
    payload = action.payload
    # 支援簡單的 session_id 字串或含有更多資訊的 payload
    if isinstance(payload, str):
        session_id = payload
        silence_start_timestamp = None
    else:
        session_id = payload.get("session_id")
        silence_start_timestamp = payload.get("timestamp")  # 靜音開始時間戳
    
    return update_session(state, session_id, {
        "is_vad_speech": False,
        "silence_start_timestamp": silence_start_timestamp
    })


def handle_record_started(state: Map, action) -> Map:
    """處理開始錄音"""
    payload = action.payload
    # 支援簡單的 session_id 字串或含有更多資訊的 payload
    if isinstance(payload, str):
        session_id = payload
        recording_start_timestamp = None
        recording_metadata = {}
    else:
        session_id = payload.get("session_id")
        recording_start_timestamp = payload.get("timestamp")  # 錄音開始時間戳
        recording_metadata = payload.get("metadata", {})
    
    return update_session(state, session_id, {
        "is_recording": True,
        "recording_start_timestamp": recording_start_timestamp,
        "recording_metadata": to_immutable(recording_metadata),
        "status": SessionStatus.PROCESSING
    })


def handle_record_stopped(state: Map, action) -> Map:
    """處理停止錄音"""
    payload = action.payload
    # 支援簡單的 session_id 字串或含有更多資訊的 payload
    if isinstance(payload, str):
        session_id = payload
        recording_end_timestamp = None
        recording_info = {}
    else:
        session_id = payload.get("session_id")
        recording_end_timestamp = payload.get("timestamp")  # 錄音結束時間戳
        recording_info = payload.get("info", {})
    
    return update_session(state, session_id, {
        "is_recording": False,
        "recording_end_timestamp": recording_end_timestamp,
        "last_recording_info": to_immutable(recording_info)
    })


def handle_transcribe_started(state: Map, action) -> Map:
    """處理開始轉譯"""
    session_id = action.payload
    
    return update_session(state, session_id, {
        "is_transcribing": True,
        "status": SessionStatus.TRANSCRIBING
    })


def handle_transcribe_done(state: Map, action) -> Map:
    """處理轉譯完成"""
    session_id = action.payload
    session = get_session(state, session_id)
    
    if not session:
        return state
    
    # 更新統計
    transcriptions_count = session.get("transcriptions_count", 0) + 1
    
    return update_session(state, session_id, {
        "is_transcribing": False,
        "status": SessionStatus.IDLE,
        "transcriptions_count": transcriptions_count
    })


def handle_upload_started(state: Map, action) -> Map:
    """處理開始上傳"""
    payload = action.payload
    session_id = payload.get("session_id")
    
    # 建立音訊配置
    audio_config = AudioConfig(
        sample_rate=payload.get("sample_rate", 16000),
        channels=payload.get("channels", 1),
        format=payload.get("format", "int16")
    )
    
    return update_session(state, session_id, {
        "upload_file": payload.get("file_name"),
        "upload_progress": 0.0,
        "audio_config": to_immutable(audio_config),
        "status": SessionStatus.PROCESSING
    })


def handle_upload_completed(state: Map, action) -> Map:
    """處理上傳完成"""
    payload = action.payload
    session_id = payload.get("session_id")
    
    return update_session(state, session_id, {
        "upload_progress": 1.0,
        "status": SessionStatus.IDLE
    })


def handle_error_raised(state: Map, action) -> Map:
    """處理錯誤發生"""
    payload = action.payload
    session_id = payload.get("session_id")
    error = payload.get("error")
    
    session = get_session(state, session_id)
    if not session:
        return state
    
    # 更新錯誤資訊
    error_count = session.get("error_count", 0) + 1
    
    return update_session(state, session_id, {
        "error_count": error_count,
        "last_error": str(error),
        "status": SessionStatus.ERROR
    })


def handle_reset_session(state: Map, action) -> Map:
    """處理重置 session
    
    注意：FSM 狀態的重置是在 SessionEffects 中處理，
    這裡只重置 PyStoreX 的狀態。
    """
    session_id = action.payload
    session = get_session(state, session_id)
    
    if not session:
        return state
    
    # 保留基本資訊，重置其他狀態
    strategy = session.get("strategy", "non_streaming")
    
    return update_session(state, session_id, {
        "status": SessionStatus.IDLE,
        "is_wake_active": False,
        "wake_source": None,
        "is_recording": False,
        "is_vad_speech": False,
        "is_transcribing": False,
        "upload_file": None,
        "upload_progress": 0.0,
        "error_count": 0,
        "last_error": None
    })


def handle_asr_stream_started(state: Map, action) -> Map:
    """處理 ASR 串流開始"""
    session_id = action.payload
    
    return update_session(state, session_id, {
        "is_streaming": True,
        "status": SessionStatus.TRANSCRIBING
    })


def handle_asr_stream_stopped(state: Map, action) -> Map:
    """處理 ASR 串流停止"""
    session_id = action.payload
    
    return update_session(state, session_id, {
        "is_streaming": False
    })


def handle_llm_reply_started(state: Map, action) -> Map:
    """處理 LLM 回覆開始"""
    session_id = action.payload
    
    return update_session(state, session_id, {
        "status": SessionStatus.REPLYING
    })


def handle_tts_playback_started(state: Map, action) -> Map:
    """處理 TTS 播放開始"""
    session_id = action.payload
    
    return update_session(state, session_id, {
        "status": SessionStatus.REPLYING
    })


# === 建立 Reducer ===

# 轉換初始狀態為 immutables.Map
initial_state_map = to_immutable(sessions_initial_state)

# 建立 reducer
sessions_reducer = create_reducer(
    initial_state_map,
    # Session 生命週期
    on(create_session, handle_create_session),
    on(delete_session, handle_delete_session),
    on(reset_session, handle_reset_session),
    # 音訊處理
    on(receive_audio_chunk, handle_receive_audio_chunk),
    on(start_listening, handle_start_listening),
    
    # 喚醒相關
    on(wake_activated, handle_wake_activated),
    on(wake_deactivated, handle_wake_deactivated),
    
    # VAD 相關
    on(vad_speech_detected, handle_vad_speech_detected),
    on(vad_silence_detected, handle_vad_silence_detected),
    
    # 錄音相關
    on(record_started, handle_record_started),
    on(record_stopped, handle_record_stopped),
    
    # 轉譯相關
    on(transcribe_started, handle_transcribe_started),
    on(transcribe_done, handle_transcribe_done),
    on(asr_stream_started, handle_asr_stream_started),
    on(asr_stream_stopped, handle_asr_stream_stopped),
    
    # 上傳相關
    on(upload_started, handle_upload_started),
    on(upload_completed, handle_upload_completed),
    
    # LLM 相關
    on(llm_reply_started, handle_llm_reply_started),
    
    # TTS 相關  
    on(tts_playback_started, handle_tts_playback_started),
    
    # 錯誤處理
    on(error_raised, handle_error_raised)
)