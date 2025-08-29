"""
FSM 狀態轉換 Handlers

處理所有 FSM 相關的狀態轉換邏輯
"""

from typing import Dict, Any, Optional
from pystorex import to_dict
from src.utils.logger import logger
from src.utils.time_provider import TimeProvider

from .base import (
    ensure_state_dict,
    format_session_id,
    get_session_from_state,
    update_session_timestamp,
    BaseHandler
)
from ..sessions_state import FSMStateEnum, FSMStrategy, FSMEvent
from ..fsm_config import get_next_state, get_strategy_config


def map_action_to_event(action_type: str) -> Optional[FSMEvent]:
    """映射 action type 到 FSMEvent
    
    Args:
        action_type: Action 類型字串
        
    Returns:
        對應的 FSMEvent，如果沒有映射則返回 None
    """
    # 處理 PyStoreX action type 格式: "[Namespace] Action Name"
    if "] " in action_type:
        # 提取 "] " 後的部分，然後轉為 snake_case
        action_name = action_type.split("] ")[-1].lower().replace(" ", "_")
    else:
        # 提取 action 名稱（去除命名空間）
        action_name = action_type.split(".")[-1] if "." in action_type else action_type
    
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


def handle_fsm_transition(state: Any, action: Any) -> Dict[str, Any]:
    """處理 FSM 狀態轉換 - 使用聲明式配置
    
    Phase 3.1 優化：
    1. 增強狀態轉換日誌
    2. 確保 END_RECORDING 後自動觸發 TRANSCRIBING
    3. 改進異常狀態恢復
    
    Args:
        state: 當前狀態
        action: FSM 轉換 action
        
    Returns:
        更新後的狀態
    """
    # Phase 3.2: 狀態轉換視覺化日誌
    logger.block(
        "FSM State Transition",
        [
            f"Session: {action.payload.get('session_id', 'unknown')[:8]}...",
            f"Action: {action.type}",
            f"Current State: {state.get('fsm_state', 'unknown')}",
            f"Strategy: {state.get('strategy', 'unknown')}",
        ],
    )
    
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    session_id = action.payload.get("session_id")
    
    # 確保 sessions 字典存在
    sessions = to_dict(state.get("sessions", {}))
    
    logger.info(f"Sessions in state: {list(sessions.keys())}")
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found in state")
        logger.debug(f"Available sessions: {list(sessions.keys())}")
        return state
    
    session = to_dict(sessions[session_id])
    logger.info(
        f"Session before transition: fsm_state={session.get('fsm_state')}, "
        f"strategy={session.get('strategy')}"
    )
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
            logger.info(f"Session {format_session_id(session_id)} audio format updated: {audio_format}")
    
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
        context=context,
    )
    
    logger.info(
        f"FSM: strategy={session['strategy']}, current={session['fsm_state']}, "
        f"event={event}, next={next_state}"
    )
    
    # 如果有有效的狀態轉換
    if next_state:
        # 更新前一狀態
        new_session["previous_state"] = session["fsm_state"]
        new_session["fsm_state"] = next_state
        
        # Phase 3.2: 增強的狀態轉換日誌
        logger.block(
            "State Transition Successful",
            [
                f"Session: {format_session_id(session_id)}...",
                f"Previous State: {session['fsm_state']}",
                f"Event: {event}",
                f"New State: {next_state}",
                f"Strategy: {session['strategy']}",
            ],
        )
        
        # Phase 3.1: 特殊處理 - END_RECORDING 後自動觸發 BEGIN_TRANSCRIPTION
        if event == FSMEvent.END_RECORDING and next_state != FSMStateEnum.TRANSCRIBING:
            # 注意：END_RECORDING 不直接進入 TRANSCRIBING
            # 而是由 auto_transcription_trigger effect 處理
            logger.debug("END_RECORDING detected - transcription will be triggered by effect")
    else:
        # 沒有有效轉換時的日誌
        logger.block(
            "State Transition Failed",
            [
                f"Session: {format_session_id(session_id)}...",
                f"Current State: {session['fsm_state']}",
                f"Event: {event}",
                f"Strategy: {session['strategy']}",
            ]
        )
    
    # 根據特定事件處理額外的資料更新（無論是否有狀態轉換）
    _handle_event_specific_updates(new_session, event, action, session_id)
    
    # 更新時間戳
    new_session = update_session_timestamp(new_session)
    
    return {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }


def _handle_event_specific_updates(session: Dict[str, Any], event: FSMEvent, action: Any, session_id: str):
    """處理特定事件的資料更新
    
    Args:
        session: Session 字典（會被直接修改）
        event: FSM 事件
        action: Action 物件
        session_id: Session ID
    """
    if event == FSMEvent.WAKE_TRIGGERED:
        session["wake_trigger"] = action.payload.get("trigger")
        session["wake_time"] = TimeProvider.now()
        logger.info(f"🎯 Wake word triggered for session {format_session_id(session_id)}")
    
    elif event == FSMEvent.TRANSCRIPTION_DONE:
        session["transcription"] = action.payload.get("result")
        logger.info(f"📝 Transcription completed for session {format_session_id(session_id)}")
    
    elif event == FSMEvent.RESET:
        # Phase 3.1: 改進的重置邏輯
        logger.info(f"🔄 Resetting session {format_session_id(session_id)} to initial state")
        session["wake_trigger"] = None
        session["wake_time"] = None
        session["transcription"] = None
        session["error"] = None
        session["audio_bytes_received"] = 0  # 重置音訊統計
        session["audio_chunks_count"] = 0
    
    elif event == FSMEvent.ERROR:
        # Phase 3.1: 改進的錯誤處理
        error_msg = action.payload.get("error")
        session["error"] = error_msg
        logger.error(f"❌ Session {format_session_id(session_id)} entered ERROR state: {error_msg}")
    
    elif event == FSMEvent.RECOVER:
        # Phase 3.1: 恢復機制
        logger.info(f"♻️ Session {format_session_id(session_id)} recovering from error")
        session["error"] = None