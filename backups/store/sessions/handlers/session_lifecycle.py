"""
Session 生命週期管理 Handlers

處理 session 的創建、銷毀、活躍狀態管理等
"""

from typing import Dict, Any
from pystorex import to_dict
from src.utils.logger import logger
from src.utils.time_provider import TimeProvider

from .base import (
    ensure_state_dict,
    format_session_id,
    get_session_from_state,
    update_session_timestamp,
    create_initial_session,
    BaseHandler
)
from ..sessions_state import FSMStrategy, SessionsState

def handle_create_session(state: SessionsState, action: Any) -> Dict[str, Any]:
    """處理創建會話"""
    state = ensure_state_dict(state)

    import uuid6
    u7 = uuid6.uuid7()
    session_id = u7
    strategy = FSMStrategy(action.payload.get("strategy", FSMStrategy.NON_STREAMING))

    logger.debug(f"Creating session {format_session_id(session_id)} with strategy {strategy}")

    sessions = to_dict(state.get("sessions", {}))
    max_sessions = state.get("max_sessions")
    if len(sessions) >= max_sessions:
        logger.warning(f"Maximum sessions ({max_sessions}) reached, cannot create new session")
        return state

    # ==== 原 create_initial_session 的內容搬到這裡 ====
    from src.store.sessions.sessions_state import SessionState, FSMStrategy
    from src.store.sessions.fsm_config import get_strategy_config
    from src.utils.time_provider import TimeProvider  # 假設這裡定義

    current_time = TimeProvider.now()
    config = get_strategy_config(strategy)
    initial_state = config.initial_state

    new_session = SessionState(
        id=session_id,
        fsm_state=initial_state,
        previous_state=None,
        strategy=strategy,
        wake_trigger=None,
        wake_time=None,
        audio_bytes_received=0,
        audio_chunks_count=0,
        last_audio_timestamp=None,
        audio_format=None,
        audio_metadata=None,
        conversion_strategy=None,
        transcription=None,
        error=None,
        created_at=current_time,
        updated_at=current_time,
        metadata={},
    )
    # ============================================

    new_state = {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }

    logger.debug(f"State after create: {list(new_state['sessions'].keys())}")
    logger.info(f"✅ Session {format_session_id(session_id)} created successfully")

    return new_state


def handle_destroy_session(state: Any, action: Any) -> Dict[str, Any]:
    """處理銷毀會話
    
    Args:
        state: 當前狀態
        action: destroy_session action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    session_id = action.payload.get("session_id") or action.payload.get("id")
    
    if session_id not in state["sessions"]:
        logger.warning(f"Session {format_session_id(session_id)} not found, cannot destroy")
        return state
    
    # 複製 sessions 並刪除指定的 session
    new_sessions = {**state["sessions"]}
    del new_sessions[session_id]
    
    # 如果刪除的是活躍會話，清除活躍會話 ID
    new_active_id = state["active_session_id"]
    if new_active_id == session_id:
        new_active_id = None
        logger.info(f"Active session {format_session_id(session_id)} destroyed, clearing active session")
    
    logger.info(f"🗑️ Session {format_session_id(session_id)} destroyed successfully")
    
    return {
        **state,
        "sessions": new_sessions,
        "active_session_id": new_active_id
    }


def handle_set_active_session(state: Any, action: Any) -> Dict[str, Any]:
    """處理設置活躍會話
    
    Args:
        state: 當前狀態
        action: set_active_session action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    session_id = action.payload.get("session_id") or action.payload.get("id")
    
    if session_id not in state["sessions"]:
        logger.warning(f"Session {format_session_id(session_id)} not found, cannot set as active")
        return state
    
    logger.info(f"🎯 Session {format_session_id(session_id)} set as active")
    
    return {
        **state,
        "active_session_id": session_id
    }


def handle_clear_active_session(state: Any, action: Any) -> Dict[str, Any]:
    """處理清除活躍會話
    
    Args:
        state: 當前狀態
        action: clear_active_session action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    logger.info("❌ Active session cleared")
    
    return {
        **state,
        "active_session_id": None
    }


def handle_update_session_metadata(state: Any, action: Any) -> Dict[str, Any]:
    """處理更新 session metadata
    
    用於更新 session 的 metadata 欄位，例如：
    - 音訊檔案的 metadata
    - 其他自定義的 metadata
    
    Args:
        state: 當前狀態
        action: update_session_metadata action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload.get("session_id")
    new_metadata = action.payload.get("metadata", {})
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found when updating metadata")
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
    updated_session = update_session_timestamp({
        **session,
        "metadata": updated_metadata
    })
    
    logger.info(f"📝 Updated metadata for session {format_session_id(session_id)}: {updated_metadata}")
    
    return {
        **state,
        "sessions": {**sessions, session_id: updated_session}
    }


def handle_session_error(state: Any, action: Any) -> Dict[str, Any]:
    """處理會話錯誤
    
    Args:
        state: 當前狀態
        action: session_error action
        
    Returns:
        更新後的狀態
    """
    from src.store.sessions.sessions_state import FSMStateEnum
    
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found when handling error")
        return state
    
    session = to_dict(sessions[session_id])
    error_msg = action.payload["error"]
    
    # 更新 session 狀態為 ERROR
    new_session = update_session_timestamp({
        **session,
        "fsm_state": FSMStateEnum.ERROR,
        "previous_state": session["fsm_state"],
        "error": error_msg
    })
    
    logger.error(f"❌ Session {format_session_id(session_id)} entered ERROR state: {error_msg}")
    
    return {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }


def handle_clear_error(state: Any, action: Any) -> Dict[str, Any]:
    """處理清除會話錯誤
    
    Args:
        state: 當前狀態
        action: clear_error action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found when clearing error")
        return state
    
    session = to_dict(sessions[session_id])
    
    # 清除錯誤
    new_session = update_session_timestamp({
        **session,
        "error": None
    })
    
    logger.info(f"✅ Error cleared for session {format_session_id(session_id)}")
    
    return {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }