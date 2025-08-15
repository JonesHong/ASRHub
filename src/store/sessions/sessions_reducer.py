"""
Sessions 域的 Reducer 實現
"""

from typing import Dict
from pystorex import create_reducer, on
from src.utils.time_provider import TimeProvider

from .sessions_state import SessionState, SessionsState, FSMStateEnum, FSMStrategy
from .sessions_actions import (
    create_session, destroy_session, set_active_session, clear_active_session,
    start_listening, wake_triggered, start_recording, end_recording,
    start_streaming, end_streaming, begin_transcription, transcription_done,
    reset_fsm, audio_chunk_received, clear_audio_buffer,
    session_error, clear_session_error
)


# ============================================================================
# 工具函數
# ============================================================================

def create_initial_session(session_id: str, strategy: FSMStrategy) -> SessionState:
    """創建初始會話狀態"""
    current_time = TimeProvider.now()
    return SessionState(
        id=session_id,
        fsm_state=FSMStateEnum.IDLE,
        previous_state=None,
        strategy=strategy,
        wake_trigger=None,
        wake_time=None,
        audio_buffer=[],
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
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload["id"]
    strategy = FSMStrategy(action.payload.get("strategy", FSMStrategy.NON_STREAMING))
    
    # 檢查是否超過最大會話數
    sessions = state.get("sessions", {})
    max_sessions = state.get("max_sessions", 10)
    if len(sessions) >= max_sessions:
        return state
    
    new_session = create_initial_session(session_id, strategy)
    
    return {
        **state,
        "sessions": {
            **sessions,
            session_id: new_session
        }
    }


def handle_destroy_session(state: SessionsState, action) -> SessionsState:
    """處理銷毀會話"""
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload["id"]
    
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
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload["id"]
    
    if session_id not in state["sessions"]:
        return state
    
    return {
        **state,
        "active_session_id": session_id
    }


def handle_clear_active_session(state: SessionsState, action) -> SessionsState:
    """處理清除活躍會話"""
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    return {
        **state,
        "active_session_id": None
    }


def handle_fsm_transition(state: SessionsState, action) -> SessionsState:
    """處理 FSM 狀態轉換"""
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload.get("session_id")
    
    if session_id not in state["sessions"]:
        return state
    
    session = state["sessions"][session_id]
    new_session = {**session}
    
    # 更新前一狀態
    new_session["previous_state"] = session["fsm_state"]
    
    # 根據 action 類型處理狀態轉換
    if action.type == start_listening.type:
        new_session["fsm_state"] = FSMStateEnum.LISTENING
        
    elif action.type == wake_triggered.type:
        new_session["fsm_state"] = FSMStateEnum.ACTIVATED
        new_session["wake_trigger"] = action.payload["trigger"]
        new_session["wake_time"] = TimeProvider.now()
        
    elif action.type == start_recording.type:
        if session["strategy"] == FSMStrategy.NON_STREAMING:
            new_session["fsm_state"] = FSMStateEnum.RECORDING
            
    elif action.type == start_streaming.type:
        if session["strategy"] == FSMStrategy.STREAMING:
            new_session["fsm_state"] = FSMStateEnum.STREAMING
            
    elif action.type == end_recording.type or action.type == end_streaming.type:
        new_session["fsm_state"] = FSMStateEnum.TRANSCRIBING
        
    elif action.type == begin_transcription.type:
        new_session["fsm_state"] = FSMStateEnum.TRANSCRIBING
        
    elif action.type == transcription_done.type:
        new_session["fsm_state"] = FSMStateEnum.ACTIVATED
        new_session["transcription"] = action.payload["result"]
        
    elif action.type == reset_fsm.type:
        new_session["fsm_state"] = FSMStateEnum.IDLE
        new_session["wake_trigger"] = None
        new_session["wake_time"] = None
        new_session["transcription"] = None
        new_session["error"] = None
    
    # 更新時間戳
    new_session = update_session_timestamp(new_session)
    
    return {
        **state,
        "sessions": {
            **state["sessions"],
            session_id: new_session
        }
    }


def handle_audio_chunk(state: SessionsState, action) -> SessionsState:
    """處理音訊資料"""
    session_id = action.payload["session_id"]
    
    if session_id not in state["sessions"]:
        return state
    
    session = state["sessions"][session_id]
    
    # 處理 immutable 的情況
    current_buffer = session["audio_buffer"]
    if isinstance(current_buffer, (tuple, list)):
        buffer = list(current_buffer)
    else:
        buffer = []
    
    buffer.append(action.payload["data"])
    
    # 限制緩衝區大小（保留最新的 100 個 chunks）
    if len(buffer) > 100:
        buffer = buffer[-100:]
    
    new_session = update_session_timestamp({
        **session,
        "audio_buffer": buffer
    })
    
    return {
        **state,
        "sessions": {
            **state["sessions"],
            session_id: new_session
        }
    }


def handle_clear_audio_buffer(state: SessionsState, action) -> SessionsState:
    """處理清除音訊緩衝"""
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload["session_id"]
    
    if session_id not in state["sessions"]:
        return state
    
    session = state["sessions"][session_id]
    new_session = update_session_timestamp({
        **session,
        "audio_buffer": []
    })
    
    return {
        **state,
        "sessions": {
            **state["sessions"],
            session_id: new_session
        }
    }


def handle_session_error(state: SessionsState, action) -> SessionsState:
    """處理會話錯誤"""
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload["session_id"]
    
    if session_id not in state["sessions"]:
        return state
    
    session = state["sessions"][session_id]
    new_session = update_session_timestamp({
        **session,
        "fsm_state": FSMStateEnum.ERROR,
        "previous_state": session["fsm_state"],
        "error": action.payload["error"]
    })
    
    return {
        **state,
        "sessions": {
            **state["sessions"],
            session_id: new_session
        }
    }


def handle_clear_session_error(state: SessionsState, action) -> SessionsState:
    """處理清除會話錯誤"""
    # 處理初始狀態
    if state is None or not isinstance(state, dict):
        from .sessions_state import get_initial_sessions_state
        state = get_initial_sessions_state()
    
    session_id = action.payload["session_id"]
    
    if session_id not in state["sessions"]:
        return state
    
    session = state["sessions"][session_id]
    new_session = update_session_timestamp({
        **session,
        "error": None
    })
    
    return {
        **state,
        "sessions": {
            **state["sessions"],
            session_id: new_session
        }
    }


# ============================================================================
# Sessions Reducer
# ============================================================================

sessions_reducer = create_reducer(
    # 初始狀態
    SessionsState(
        sessions={},
        active_session_id=None,
        max_sessions=10
    ),
    
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
    on(start_streaming.type, handle_fsm_transition),
    on(end_streaming.type, handle_fsm_transition),
    on(begin_transcription.type, handle_fsm_transition),
    on(transcription_done.type, handle_fsm_transition),
    on(reset_fsm.type, handle_fsm_transition),
    
    # 音訊處理
    on(audio_chunk_received.type, handle_audio_chunk),
    on(clear_audio_buffer.type, handle_clear_audio_buffer),
    
    # 錯誤處理
    on(session_error.type, handle_session_error),
    on(clear_session_error.type, handle_clear_session_error),
)