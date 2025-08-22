"""
Sessions 域的 Reducer 實現
"""

from typing import Dict, Optional, Any
from pystorex import create_reducer, on, to_dict
from src.utils.time_provider import TimeProvider

from .sessions_state import SessionState, SessionsState, FSMStateEnum, FSMStrategy, FSMEvent
from .fsm_config import get_next_state, get_strategy_config
from .sessions_actions import (
    create_session, destroy_session, set_active_session, clear_active_session,
    start_listening, wake_triggered, start_recording, end_recording,
    start_asr_streaming, end_asr_streaming, begin_transcription, transcription_done,
    llm_reply_started, llm_reply_finished,
    tts_playback_started, tts_playback_finished, interrupt_reply,
    timeout, error,
    fsm_reset, audio_chunk_received, clear_audio_buffer, audio_metadata,
    session_error, clear_error, update_session_metadata
)


# ============================================================================
# 工具函數
# ============================================================================



def map_action_to_event(action_type: str) -> Optional[FSMEvent]:
    """映射 action type 到 FSMEvent"""
    # 處理 PyStoreX action type 格式: "[Namespace] Action Name"
    if "] " in action_type:
        # 提取 "] " 後的部分，然後轉為 snake_case
        action_name = action_type.split("] ")[-1].lower().replace(" ", "_")
    else:
        # 提取 action 名稱（去除命名空間）
        action_name = action_type.split('.')[-1] if '.' in action_type else action_type
    
    # 映射表
    mapping = {
        "start_listening": FSMEvent.START_LISTENING,
        "wake_triggered": FSMEvent.WAKE_TRIGGERED,
        "start_recording": FSMEvent.START_RECORDING,
        "end_recording": FSMEvent.END_RECORDING,
        "begin_transcription": FSMEvent.BEGIN_TRANSCRIPTION,
        "transcription_done": FSMEvent.TRANSCRIPTION_DONE,
        "start_asr_streaming": FSMEvent.START_ASR_STREAMING,
        "end_asr_streaming": FSMEvent.END_ASR_STREAMING,
        "fsm_reset": FSMEvent.RESET,
        "reset_fsm": FSMEvent.RESET,
        "session_error": FSMEvent.ERROR,
        
        # 未來可能的事件
        "llm_reply_started": FSMEvent.LLM_REPLY_STARTED,
        "llm_reply_finished": FSMEvent.LLM_REPLY_FINISHED,
        "tts_playback_started": FSMEvent.TTS_PLAYBACK_STARTED,
        "tts_playback_finished": FSMEvent.TTS_PLAYBACK_FINISHED,
        "interrupt_reply": FSMEvent.INTERRUPT_REPLY,
        "timeout": FSMEvent.TIMEOUT,
        "recover": FSMEvent.RECOVER,
    }
    
    return mapping.get(action_name)


def create_initial_session(session_id: str, strategy: FSMStrategy) -> SessionState:
    """創建初始會話狀態"""
    current_time = TimeProvider.now()
    
    # 從 FSM 配置獲取初始狀態
    config = get_strategy_config(strategy)
    initial_state = config.initial_state
    
    return SessionState(
        id=session_id,
        fsm_state=initial_state,
        previous_state=None,
        strategy=strategy,
        wake_trigger=None,
        wake_time=None,
        # audio_buffer 已移至 AudioQueueManager 管理
        audio_bytes_received=0,  # 只記錄接收的位元組數
        audio_chunks_count=0,    # 音訊塊計數
        last_audio_timestamp=None,
        audio_format=None,  # 音訊格式將在 start_listening 時設定
        audio_metadata=None,  # 前端發送的音訊 metadata
        conversion_strategy=None,  # 轉換策略
        transcription=None,
        error=None,
        created_at=current_time,
        updated_at=current_time,
        metadata={}
    )


def update_session_timestamp(session: SessionState) -> SessionState:
    """更新會話時間戳"""
    return {
        **session,
        "updated_at": TimeProvider.now()
    }


# ============================================================================
# Reducer 處理函數
# ============================================================================

def handle_create_session(state: SessionsState, action) -> SessionsState:
    """處理創建會話"""
    from src.utils.logger import logger
    
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    session_id = action.payload.get("session_id") or action.payload.get("id")  # 支援兩種參數名稱
    strategy = FSMStrategy(action.payload.get("strategy", FSMStrategy.NON_STREAMING))
    
    logger.debug(f"Creating session {session_id} with strategy {strategy}")
    
    # 檢查是否超過最大會話數
    sessions = to_dict(state.get("sessions", {}))
    
    logger.debug(f"State before create: {list(sessions.keys())}")
    
    max_sessions = state.get("max_sessions", 10)
    if len(sessions) >= max_sessions:
        return state
    
    new_session = create_initial_session(session_id, strategy)
    
    new_state = {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }
    
    logger.debug(f"State after create: {list(new_state['sessions'].keys())}")
    
    return new_state


def handle_destroy_session(state: SessionsState, action) -> SessionsState:
    """處理銷毀會話"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    session_id = action.payload.get("session_id") or action.payload.get("id")  # 支援兩種參數名稱
    
    if session_id not in state["sessions"]:
        return state
    
    new_sessions = {**state["sessions"]}
    del new_sessions[session_id]
    
    # 如果刪除的是活躍會話，清除活躍會話 ID
    new_active_id = state["active_session_id"]
    if new_active_id == session_id:
        new_active_id = None
    
    return {
        **state,
        "sessions": new_sessions,
        "active_session_id": new_active_id
    }


def handle_set_active_session(state: SessionsState, action) -> SessionsState:
    """處理設置活躍會話"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    session_id = action.payload.get("session_id") or action.payload.get("id")  # 支援兩種參數名稱
    
    if session_id not in state["sessions"]:
        return state
    
    return {
        **state,
        "active_session_id": session_id
    }


def handle_clear_active_session(state: SessionsState, action) -> SessionsState:
    """處理清除活躍會話"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    return {
        **state,
        "active_session_id": None
    }


def handle_update_session_metadata(state: SessionsState, action) -> SessionsState:
    """處理更新 session metadata
    
    用於更新 session 的 metadata 欄位，例如：
    - 音訊檔案的 metadata
    - 其他自定義的 metadata
    """
    from src.utils.logger import logger
    
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload.get("session_id")
    new_metadata = action.payload.get("metadata", {})
    
    if session_id not in sessions:
        logger.warning(f"Session {session_id} not found when updating metadata")
        return state
    
    session = to_dict(sessions[session_id])
    
    # 合併現有的 metadata 和新的 metadata
    existing_metadata = session.get("metadata", {})
    if isinstance(existing_metadata, dict):
        updated_metadata = {**existing_metadata, **new_metadata}
    else:
        updated_metadata = new_metadata
    
    # 如果 metadata 中包含 audio_metadata，同時更新 session 的 audio_metadata 欄位
    if "audio_metadata" in new_metadata:
        session["audio_metadata"] = new_metadata["audio_metadata"]
    
    # 更新 session
    updated_session = {
        **session,
        "metadata": updated_metadata,
        "updated_at": TimeProvider.now()
    }
    
    logger.info(f"Updated metadata for session {session_id}: {updated_metadata}")
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: updated_session
        }
    }


def handle_fsm_transition(state: SessionsState, action) -> SessionsState:
    """處理 FSM 狀態轉換 - 使用聲明式配置
    
    Phase 3.1 優化：
    1. 增強狀態轉換日誌
    2. 確保 END_RECORDING 後自動觸發 TRANSCRIBING
    3. 改進異常狀態恢復
    """
    from src.utils.logger import logger
    
    # Phase 3.2: 狀態轉換視覺化日誌
    logger.block("FSM State Transition", [
        f"Session: {action.payload.get('session_id', 'unknown')[:8]}...",
        f"Action: {action.type}",
        f"Current State: {state.get('fsm_state', 'unknown')}",
        f"Strategy: {state.get('strategy', 'unknown')}"
    ])
    
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    session_id = action.payload.get("session_id")
    
    # 確保 sessions 字典存在
    sessions = to_dict(state.get("sessions", {}))
    
    logger.info(f"Sessions in state: {list(sessions.keys())}")
    
    if session_id not in sessions:
        logger.warning(f"Session {session_id} not found in state")
        logger.debug(f"Available sessions: {list(sessions.keys())}")
        return state
    
    session = to_dict(sessions[session_id])
    logger.info(f"Session before transition: fsm_state={session.get('fsm_state')}, strategy={session.get('strategy')}")
    new_session = {**session}
    
    # 映射 action 到 FSMEvent
    event = map_action_to_event(action.type)
    logger.info(f"Mapped action {action.type} to event: {event}")
    if not event:
        # 如果沒有對應的事件，返回原狀態
        logger.warning(f"No FSM event mapping for action: {action.type}")
        return state
    
    # 處理 START_LISTENING 事件的 audio_format
    if event == FSMEvent.START_LISTENING:
        audio_format = action.payload.get("audio_format")
        if audio_format:
            new_session["audio_format"] = audio_format
            logger.info(f"Session {session_id} audio format updated: {audio_format}")
    
    # 構建上下文（用於條件評估）
    context = {
        "keep_awake_after_reply": action.payload.get("keep_awake_after_reply"),
        "session": session,
        "action": action,
    }
    
    # 使用 FSM 配置獲取下一個狀態
    next_state = get_next_state(
        strategy=session["strategy"],
        current_state=session["fsm_state"],
        event=event,
        context=context
    )
    
    logger.info(f"FSM: strategy={session['strategy']}, current={session['fsm_state']}, event={event}, next={next_state}")
    
    # 如果有有效的狀態轉換
    if next_state:
        # 更新前一狀態
        new_session["previous_state"] = session["fsm_state"]
        new_session["fsm_state"] = next_state
        
        # Phase 3.2: 增強的狀態轉換日誌
        logger.block("State Transition Successful", [
            f"Session: {session_id[:8]}...",
            f"Previous State: {session['fsm_state']}",
            f"Event: {event}",
            f"New State: {next_state}",
            f"Strategy: {session['strategy']}"
        ])
        
        # Phase 3.1: 特殊處理 - END_RECORDING 後自動觸發 BEGIN_TRANSCRIPTION
        if event == FSMEvent.END_RECORDING and next_state != FSMStateEnum.TRANSCRIBING:
            # 注意：END_RECORDING 不直接進入 TRANSCRIBING
            # 而是由 auto_transcription_trigger effect 處理
            logger.debug("END_RECORDING detected - transcription will be triggered by effect")
    else:
        # 沒有有效轉換時的日誌
        logger.warning("┌" + "─" * 70 + "┐")
        logger.warning(f"│ ⚠️ NO VALID STATE TRANSITION")
        logger.warning(f"│ 🔸 Current State: {session['fsm_state']}")
        logger.warning(f"│ 🔸 Event: {event}")
        logger.warning(f"│ 🔸 Strategy: {session['strategy']}")
        logger.warning("└" + "─" * 70 + "┘")
    
    # 根據特定事件處理額外的資料更新（無論是否有狀態轉換）
    if event == FSMEvent.WAKE_TRIGGERED:
        new_session["wake_trigger"] = action.payload.get("trigger")
        new_session["wake_time"] = TimeProvider.now()
        
    elif event == FSMEvent.TRANSCRIPTION_DONE:
        new_session["transcription"] = action.payload.get("result")
        
    elif event == FSMEvent.RESET:
        # Phase 3.1: 改進的重置邏輯
        logger.info(f"🔄 Resetting session {session_id} to initial state")
        new_session["wake_trigger"] = None
        new_session["wake_time"] = None
        new_session["transcription"] = None
        new_session["error"] = None
        new_session["audio_bytes_received"] = 0  # 重置音訊統計
        new_session["audio_chunks_count"] = 0
        
    elif event == FSMEvent.ERROR:
        # Phase 3.1: 改進的錯誤處理
        error_msg = action.payload.get("error")
        new_session["error"] = error_msg
        logger.error(f"❌ Session {session_id} entered ERROR state: {error_msg}")
        
    elif event == FSMEvent.RECOVER:
        # Phase 3.1: 恢復機制
        logger.info(f"♻️ Session {session_id} recovering from error")
        new_session["error"] = None
    
    # 更新時間戳
    new_session = update_session_timestamp(new_session)
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def handle_audio_chunk(state: SessionsState, action) -> SessionsState:
    """處理音訊資料 - 只更新統計信息，實際音訊由 AudioQueueManager 管理"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    sessions = to_dict(state.get("sessions", {}))
    
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        return state
    
    session = to_dict(sessions[session_id])
    
    # 只更新統計信息
    chunk_size = action.payload.get("chunk_size", 0)  # 音訊塊大小
    timestamp = action.payload.get("timestamp")
    
    new_session = update_session_timestamp({
        **session,
        "audio_bytes_received": session.get("audio_bytes_received", 0) + chunk_size,
        "audio_chunks_count": session.get("audio_chunks_count", 0) + 1,
        "last_audio_timestamp": timestamp
    })
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def handle_clear_audio_buffer(state: SessionsState, action) -> SessionsState:
    """處理清除音訊統計 - 實際音訊清除由 AudioQueueManager 處理"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    sessions = to_dict(state.get("sessions", {}))
    
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        return state
    
    session = to_dict(sessions[session_id])
    new_session = update_session_timestamp({
        **session,
        "audio_bytes_received": 0,
        "audio_chunks_count": 0,
        "last_audio_timestamp": None
    })
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def handle_session_error(state: SessionsState, action) -> SessionsState:
    """處理會話錯誤"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    sessions = to_dict(state.get("sessions", {}))
    
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        return state
    
    session = to_dict(sessions[session_id])
    new_session = update_session_timestamp({
        **session,
        "fsm_state": FSMStateEnum.ERROR,
        "previous_state": session["fsm_state"],
        "error": action.payload["error"]
    })
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def handle_clear_error(state: SessionsState, action) -> SessionsState:
    """處理清除會話錯誤"""
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    sessions = to_dict(state.get("sessions", {}))
    
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        return state
    
    session = to_dict(sessions[session_id])
    new_session = update_session_timestamp({
        **session,
        "error": None
    })
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def handle_audio_metadata(state: SessionsState, action) -> SessionsState:
    """處理音訊 metadata
    
    當前端分析音訊檔案並發送 metadata 時：
    1. 儲存音訊 metadata
    2. 根據 metadata 制定轉換策略
    3. 儲存策略供後續使用
    """
    from src.utils.logger import logger
    
    # 確保 state 不是 None
    if state is None:
        state = get_initial_state()
    
    # 確保轉換為字典格式
    if hasattr(state, '__dict__'):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    sessions = to_dict(state.get("sessions", {}))
    
    session_id = action.payload["session_id"]
    received_metadata = action.payload["audio_metadata"]
    
    if session_id not in sessions:
        logger.warning(f"Session {session_id} not found when processing audio metadata")
        return state
    
    session = to_dict(sessions[session_id])
    
    # 記錄接收到的 metadata
    logger.block("Audio Metadata Received", [
        f"Session: {session_id[:8]}...",
        f"File: {received_metadata.get('filename', 'unknown')}",
        f"Format: {received_metadata.get('detectedFormat', 'unknown')}",
        f"Sample Rate: {received_metadata.get('sampleRate', 0)} Hz",
        f"Channels: {received_metadata.get('channels', 0)}",
        f"Duration: {received_metadata.get('duration', 0):.1f}s",
        f"Needs Conversion: {received_metadata.get('needsConversion', False)}"
    ])
    
    # 制定轉換策略
    conversion_strategy = _create_conversion_strategy(received_metadata)
    
    # 記錄轉換策略
    logger.block("Conversion Strategy Created", [
        f"Session: {session_id[:8]}...",
        f"Target Sample Rate: {conversion_strategy['targetSampleRate']} Hz",
        f"Target Channels: {conversion_strategy['targetChannels']} ch",
        f"Target Format: {conversion_strategy['targetFormat']}",
        f"Priority: {conversion_strategy['priority']}",
        f"Estimated Processing Time: {conversion_strategy['estimatedProcessingTime']:.1f}s",
        f"Conversion Steps: {' → '.join(conversion_strategy['conversionSteps']) if conversion_strategy['conversionSteps'] else 'None'}"
    ])
    
    # 更新 session 狀態
    new_session = update_session_timestamp({
        **session,
        "audio_metadata": received_metadata,
        "conversion_strategy": conversion_strategy
    })
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def _create_conversion_strategy(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """根據音訊 metadata 制定轉換策略
    
    Args:
        metadata: 前端發送的音訊 metadata
        
    Returns:
        轉換策略字典
    """
    # 目標格式（Whisper 的最佳參數）
    target_sample_rate = 16000
    target_channels = 1
    target_format = "pcm_float32"
    
    # 獲取當前格式參數
    current_sample_rate = metadata.get('sampleRate', 44100)
    current_channels = metadata.get('channels', 2)
    current_format = metadata.get('detectedFormat', 'MP3').lower()
    needs_conversion = metadata.get('needsConversion', True)
    
    # 計算轉換步驟
    conversion_steps = []
    
    # 1. 格式解碼（如果需要）
    if current_format in ['mp3', 'aac', 'm4a', 'flac', 'ogg']:
        conversion_steps.append(f"解碼 {current_format.upper()}")
    
    # 2. 採樣率轉換
    if current_sample_rate != target_sample_rate:
        conversion_steps.append(f"降採樣 {current_sample_rate}Hz → {target_sample_rate}Hz")
    
    # 3. 聲道轉換
    if current_channels != target_channels:
        if current_channels > target_channels:
            conversion_steps.append(f"混音 {current_channels}ch → {target_channels}ch")
        else:
            conversion_steps.append(f"複製聲道 {current_channels}ch → {target_channels}ch")
    
    # 4. 格式轉換
    conversion_steps.append(f"轉換為 {target_format}")
    
    # 估算處理時間（基於檔案時長和複雜度）
    duration = metadata.get('duration', 0.0)
    file_size = metadata.get('fileSize', 0)
    
    # 基礎處理時間（通常是實際時長的 10-30%）
    base_time = duration * 0.2
    
    # 根據轉換複雜度調整
    complexity_factor = len(conversion_steps) * 0.1
    size_factor = (file_size / (1024 * 1024)) * 0.05  # 每 MB 增加 0.05 秒
    
    estimated_time = max(0.5, base_time + complexity_factor + size_factor)
    
    # 確定優先級
    if duration > 300:  # 超過 5 分鐘
        priority = "low"
    elif needs_conversion and len(conversion_steps) > 2:
        priority = "medium"  
    else:
        priority = "high"
    
    return {
        "needsConversion": needs_conversion or len(conversion_steps) > 1,
        "targetSampleRate": target_sample_rate,
        "targetChannels": target_channels,
        "targetFormat": target_format,
        "conversionSteps": conversion_steps,
        "estimatedProcessingTime": estimated_time,
        "priority": priority
    }


# ============================================================================
# Sessions Reducer
# ============================================================================

# 創建初始狀態函數
def get_initial_state():
    """獲取初始狀態"""
    return SessionsState(
        sessions={},
        active_session_id=None,
        max_sessions=10
    )

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