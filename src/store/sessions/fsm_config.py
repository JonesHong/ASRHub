"""
FSM 配置定義模組
使用聲明式配置定義狀態機行為
"""

from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from .sessions_state import FSMStateEnum, FSMStrategy


# ============================================================================
# 事件定義
# ============================================================================

class FSMEvent(str, Enum):
    """FSM 事件枚舉"""
    # 核心事件
    START_LISTENING = "start_listening"
    WAKE_TRIGGERED = "wake_triggered"
    START_RECORDING = "start_recording"
    END_RECORDING = "end_recording"
    BEGIN_TRANSCRIPTION = "begin_transcription"
    START_ASR_STREAMING = "start_asr_streaming"
    END_ASR_STREAMING = "end_asr_streaming"
    UPLOAD_FILE = "upload_file"
    TRANSCRIPTION_DONE = "transcription_done"
    
    # LLM/TTS 事件 (Inbound)
    LLM_REPLY_STARTED = "llm_reply_started"
    LLM_REPLY_FINISHED = "llm_reply_finished"
    TTS_PLAYBACK_STARTED = "tts_playback_started"
    TTS_PLAYBACK_FINISHED = "tts_playback_finished"
    
    # 打斷事件
    INTERRUPT_REPLY = "interrupt_reply"
    
    # 系統事件
    TIMEOUT = "timeout"
    RESET = "reset"
    ERROR = "error"
    RECOVER = "recover"


# ============================================================================
# 轉換規則定義
# ============================================================================

@dataclass
class StateTransition:
    """狀態轉換定義"""
    from_state: FSMStateEnum
    event: FSMEvent
    to_state: FSMStateEnum
    condition: Optional[str] = None  # 條件表達式（可選）
    priority: int = 0  # 優先級（數字越大優先級越高）


@dataclass
class FSMStrategyConfig:
    """FSM 策略配置"""
    strategy: FSMStrategy
    initial_state: FSMStateEnum
    transitions: List[StateTransition]
    allowed_events: Set[FSMEvent]  # 此策略關心的事件集合
    timeout_configs: Dict[FSMStateEnum, int] = field(default_factory=dict)  # 狀態超時配置（毫秒）


# ============================================================================
# 通用規則（所有策略共享）
# ============================================================================

COMMON_TRANSITIONS = [
    # RESET 最高優先級
    StateTransition(
        from_state=FSMStateEnum.IDLE,  # 任何狀態都可以 RESET
        event=FSMEvent.RESET,
        to_state=FSMStateEnum.IDLE,
        priority=100
    ),
    
    # ERROR 處理
    StateTransition(
        from_state=FSMStateEnum.IDLE,  # 任何狀態都可能 ERROR
        event=FSMEvent.ERROR,
        to_state=FSMStateEnum.ERROR,
        priority=90
    ),
    StateTransition(
        from_state=FSMStateEnum.ERROR,
        event=FSMEvent.RECOVER,
        to_state=FSMStateEnum.RECOVERING,
        priority=90
    ),
    StateTransition(
        from_state=FSMStateEnum.RECOVERING,
        event=FSMEvent.RESET,
        to_state=FSMStateEnum.IDLE,
        priority=90
    ),
    
    # LLM/TTS 回覆 → BUSY
    StateTransition(
        from_state=FSMStateEnum.ACTIVATED,
        event=FSMEvent.LLM_REPLY_STARTED,
        to_state=FSMStateEnum.BUSY,
        priority=50
    ),
    StateTransition(
        from_state=FSMStateEnum.ACTIVATED,
        event=FSMEvent.TTS_PLAYBACK_STARTED,
        to_state=FSMStateEnum.BUSY,
        priority=50
    ),
    
    # BUSY 狀態處理
    StateTransition(
        from_state=FSMStateEnum.BUSY,
        event=FSMEvent.INTERRUPT_REPLY,
        to_state=FSMStateEnum.ACTIVATED,
        priority=60
    ),
    StateTransition(
        from_state=FSMStateEnum.BUSY,
        event=FSMEvent.TTS_PLAYBACK_FINISHED,
        to_state=FSMStateEnum.ACTIVATED,  # 預設保持喚醒
        condition="keep_awake_after_reply",
        priority=40
    ),
    StateTransition(
        from_state=FSMStateEnum.BUSY,
        event=FSMEvent.TTS_PLAYBACK_FINISHED,
        to_state=FSMStateEnum.LISTENING,
        condition="not keep_awake_after_reply",
        priority=40
    ),
    
    # TIMEOUT 處理
    StateTransition(
        from_state=FSMStateEnum.ACTIVATED,
        event=FSMEvent.TIMEOUT,
        to_state=FSMStateEnum.LISTENING,
        priority=30
    ),
    StateTransition(
        from_state=FSMStateEnum.RECORDING,
        event=FSMEvent.TIMEOUT,
        to_state=FSMStateEnum.TRANSCRIBING,
        priority=30
    ),
    StateTransition(
        from_state=FSMStateEnum.STREAMING,
        event=FSMEvent.TIMEOUT,
        to_state=FSMStateEnum.ACTIVATED,
        priority=30
    ),
]


# ============================================================================
# 策略配置
# ============================================================================

# 批次模式配置
BATCH_MODE_CONFIG = FSMStrategyConfig(
    strategy=FSMStrategy.BATCH,
    initial_state=FSMStateEnum.IDLE,
    transitions=[
        StateTransition(
            from_state=FSMStateEnum.IDLE,
            event=FSMEvent.UPLOAD_FILE,
            to_state=FSMStateEnum.PROCESSING
        ),
        StateTransition(
            from_state=FSMStateEnum.PROCESSING,
            event=FSMEvent.TRANSCRIPTION_DONE,
            to_state=FSMStateEnum.IDLE
        ),
    ],
    allowed_events={
        FSMEvent.UPLOAD_FILE,
        FSMEvent.TRANSCRIPTION_DONE,
        FSMEvent.ERROR,
        FSMEvent.RESET,
    },
    timeout_configs={}
)

# 非串流模式配置（如 Whisper）
NON_STREAMING_CONFIG = FSMStrategyConfig(
    strategy=FSMStrategy.NON_STREAMING,
    initial_state=FSMStateEnum.IDLE,
    transitions=[
        StateTransition(
            from_state=FSMStateEnum.IDLE,
            event=FSMEvent.START_LISTENING,
            to_state=FSMStateEnum.LISTENING
        ),
        StateTransition(
            from_state=FSMStateEnum.LISTENING,
            event=FSMEvent.WAKE_TRIGGERED,
            to_state=FSMStateEnum.ACTIVATED
        ),
        StateTransition(
            from_state=FSMStateEnum.ACTIVATED,
            event=FSMEvent.START_RECORDING,
            to_state=FSMStateEnum.RECORDING
        ),
        StateTransition(
            from_state=FSMStateEnum.RECORDING,
            event=FSMEvent.END_RECORDING,
            to_state=FSMStateEnum.TRANSCRIBING
        ),
        StateTransition(
            from_state=FSMStateEnum.TRANSCRIBING,
            event=FSMEvent.TRANSCRIPTION_DONE,
            to_state=FSMStateEnum.ACTIVATED
        ),
    ],
    allowed_events={
        FSMEvent.START_LISTENING,
        FSMEvent.WAKE_TRIGGERED,
        FSMEvent.START_RECORDING,
        FSMEvent.END_RECORDING,
        FSMEvent.BEGIN_TRANSCRIPTION,
        FSMEvent.TRANSCRIPTION_DONE,
        FSMEvent.LLM_REPLY_STARTED,
        FSMEvent.LLM_REPLY_FINISHED,
        FSMEvent.TTS_PLAYBACK_STARTED,
        FSMEvent.TTS_PLAYBACK_FINISHED,
        FSMEvent.INTERRUPT_REPLY,
        FSMEvent.TIMEOUT,
        FSMEvent.ERROR,
        FSMEvent.RESET,
        FSMEvent.RECOVER,
    },
    timeout_configs={
        FSMStateEnum.ACTIVATED: 5000,  # 5秒喚醒視窗
        FSMStateEnum.RECORDING: 10000,  # 10秒最大錄音時間
        FSMStateEnum.TRANSCRIBING: 5000,  # 5秒轉譯超時
    }
)

# 串流模式配置（如 Google STT、Vosk）
STREAMING_CONFIG = FSMStrategyConfig(
    strategy=FSMStrategy.STREAMING,
    initial_state=FSMStateEnum.IDLE,
    transitions=[
        StateTransition(
            from_state=FSMStateEnum.IDLE,
            event=FSMEvent.START_LISTENING,
            to_state=FSMStateEnum.LISTENING
        ),
        StateTransition(
            from_state=FSMStateEnum.LISTENING,
            event=FSMEvent.WAKE_TRIGGERED,
            to_state=FSMStateEnum.ACTIVATED
        ),
        StateTransition(
            from_state=FSMStateEnum.ACTIVATED,
            event=FSMEvent.START_ASR_STREAMING,
            to_state=FSMStateEnum.STREAMING
        ),
        StateTransition(
            from_state=FSMStateEnum.STREAMING,
            event=FSMEvent.END_ASR_STREAMING,
            to_state=FSMStateEnum.ACTIVATED
        ),
    ],
    allowed_events={
        FSMEvent.START_LISTENING,
        FSMEvent.WAKE_TRIGGERED,
        FSMEvent.START_ASR_STREAMING,
        FSMEvent.END_ASR_STREAMING,
        FSMEvent.LLM_REPLY_STARTED,
        FSMEvent.LLM_REPLY_FINISHED,
        FSMEvent.TTS_PLAYBACK_STARTED,
        FSMEvent.TTS_PLAYBACK_FINISHED,
        FSMEvent.INTERRUPT_REPLY,
        FSMEvent.TIMEOUT,
        FSMEvent.ERROR,
        FSMEvent.RESET,
        FSMEvent.RECOVER,
    },
    timeout_configs={
        FSMStateEnum.ACTIVATED: 5000,  # 5秒喚醒視窗
        FSMStateEnum.STREAMING: 30000,  # 30秒最大串流時間
    }
)


# ============================================================================
# 配置註冊表
# ============================================================================

FSM_CONFIGS: Dict[FSMStrategy, FSMStrategyConfig] = {
    FSMStrategy.BATCH: BATCH_MODE_CONFIG,
    FSMStrategy.NON_STREAMING: NON_STREAMING_CONFIG,
    FSMStrategy.STREAMING: STREAMING_CONFIG,
}


# ============================================================================
# 輔助函數
# ============================================================================

def get_strategy_config(strategy: FSMStrategy) -> FSMStrategyConfig:
    """獲取指定策略的配置"""
    return FSM_CONFIGS.get(strategy, NON_STREAMING_CONFIG)


def get_valid_transitions(
    strategy: FSMStrategy,
    current_state: FSMStateEnum,
    event: FSMEvent
) -> List[StateTransition]:
    """
    獲取有效的狀態轉換
    
    Args:
        strategy: FSM 策略
        current_state: 當前狀態
        event: 觸發事件
        
    Returns:
        有效的狀態轉換列表（按優先級排序）
    """
    config = get_strategy_config(strategy)
    
    # 檢查事件是否被此策略關心
    if event not in config.allowed_events:
        return []
    
    # 收集所有可能的轉換（策略特定 + 通用）
    all_transitions = config.transitions + COMMON_TRANSITIONS
    
    # 過濾出適用的轉換
    valid_transitions = []
    for transition in all_transitions:
        # 檢查狀態和事件是否匹配
        # 注意：from_state == FSMStateEnum.IDLE 可以表示 "任何狀態"（用於通用規則）
        if transition.event == event:
            if transition.from_state == current_state or \
               (transition.from_state == FSMStateEnum.IDLE and 
                transition.event in [FSMEvent.RESET, FSMEvent.ERROR]):
                valid_transitions.append(transition)
    
    # 按優先級排序（高優先級優先）
    valid_transitions.sort(key=lambda t: t.priority, reverse=True)
    
    return valid_transitions


def evaluate_condition(condition: Optional[str], context: Dict[str, Any]) -> bool:
    """
    評估條件表達式
    
    Args:
        condition: 條件表達式字符串
        context: 評估上下文
        
    Returns:
        條件是否滿足
    """
    if not condition:
        return True
    
    # 簡單的條件評估實現
    # 實際使用時可以根據需要擴展
    try:
        # 注意：這裡使用簡單的字符串匹配，生產環境應該使用更安全的方式
        if condition == "keep_awake_after_reply":
            return context.get("keep_awake_after_reply", True)
        elif condition == "not keep_awake_after_reply":
            return not context.get("keep_awake_after_reply", True)
        else:
            # 其他條件可以在這裡添加
            return True
    except Exception:
        return False


def get_next_state(
    strategy: FSMStrategy,
    current_state: FSMStateEnum,
    event: FSMEvent,
    context: Optional[Dict[str, Any]] = None
) -> Optional[FSMStateEnum]:
    """
    根據配置獲取下一個狀態
    
    Args:
        strategy: FSM 策略
        current_state: 當前狀態
        event: 觸發事件
        context: 評估上下文
        
    Returns:
        下一個狀態，如果沒有有效轉換則返回 None
    """
    if context is None:
        context = {}
    
    # 獲取有效的轉換（已按優先級排序）
    valid_transitions = get_valid_transitions(strategy, current_state, event)
    
    # 找到第一個滿足條件的轉換
    for transition in valid_transitions:
        if evaluate_condition(transition.condition, context):
            return transition.to_state
    
    return None


# ============================================================================
# 配置驗證
# ============================================================================

def validate_config(config: FSMStrategyConfig) -> List[str]:
    """
    驗證 FSM 配置的完整性和一致性
    
    Args:
        config: FSM 策略配置
        
    Returns:
        錯誤訊息列表
    """
    errors = []
    
    # 檢查初始狀態
    if not config.initial_state:
        errors.append("未定義初始狀態")
    
    # 檢查轉換規則
    if not config.transitions:
        errors.append("未定義任何轉換規則")
    
    # 檢查是否有孤立狀態
    reachable_states = {config.initial_state}
    for transition in config.transitions:
        reachable_states.add(transition.to_state)
    
    # 檢查所有狀態是否都可達
    all_states = set(FSMStateEnum)
    unreachable = all_states - reachable_states - {FSMStateEnum.ERROR, FSMStateEnum.RECOVERING}
    if unreachable and config.strategy != FSMStrategy.BATCH:
        errors.append(f"存在不可達狀態: {unreachable}")
    
    return errors


# 驗證所有配置
if __name__ == "__main__":
    for strategy, config in FSM_CONFIGS.items():
        errors = validate_config(config)
        if errors:
            print(f"❌ {strategy.value} 配置錯誤:")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"✅ {strategy.value} 配置有效")