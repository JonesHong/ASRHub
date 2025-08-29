"""
Session Handlers 模組

提供所有 reducer 和 effect handlers 的統一匯出介面
"""

# 從 base 匯出共用工具
from .base import (
    format_session_id,
    ensure_state_dict,
    ensure_dict,
    extract_session_id,
    get_initial_state,
    get_session_from_state,
    update_session_timestamp,
    create_initial_session,
    BaseHandler,
    BaseEffect,
    BaseEffectHandler,
    EffectSubscriptionManager
)

# 從 session_lifecycle 匯出生命週期 handlers
from .session_lifecycle import (
    handle_create_session,
    handle_destroy_session,
    handle_set_active_session,
    handle_clear_active_session,
    handle_update_session_metadata,
    handle_session_error,
    handle_clear_error
)

# 從 fsm_transitions 匯出 FSM handlers
from .fsm_transitions import (
    handle_fsm_transition,
    map_action_to_event
)

# 從 audio_processing 匯出音訊 handlers
from .audio_processing import (
    handle_audio_chunk,
    handle_clear_audio_buffer,
    handle_audio_metadata,
    create_conversion_strategy
)

# 匯出 Effect handlers
from .transcription_handler import TranscriptionHandler
from .timer_handler import SessionTimerHandler
from .audio_handler import AudioProcessingHandler

__all__ = [
    # Base utilities
    'format_session_id',
    'ensure_state_dict',
    'ensure_dict',
    'extract_session_id',
    'get_initial_state',
    'get_session_from_state',
    'update_session_timestamp',
    'BaseHandler',
    'BaseEffect',
    'BaseEffectHandler',
    'EffectSubscriptionManager',
    
    # Session lifecycle
    'handle_create_session',
    'handle_destroy_session',
    'handle_set_active_session',
    'handle_clear_active_session',
    'handle_update_session_metadata',
    'handle_session_error',
    'handle_clear_error',
    
    # FSM transitions
    'handle_fsm_transition',
    'map_action_to_event',
    
    # Audio processing
    'handle_audio_chunk',
    'handle_clear_audio_buffer',
    'handle_audio_metadata',
    'create_conversion_strategy',
    
    # Effect handlers
    'OperatorManagementHandler',
    'TranscriptionHandler',
    'SessionTimerHandler',
    'AudioProcessingHandler',
]