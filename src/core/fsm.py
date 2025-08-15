"""
ASR Hub FSM（Finite State Machine）增強版實作
統一的狀態管理系統，支援批次、非串流和串流三種模式
"""

from enum import Enum, auto
from abc import ABC, abstractmethod
from collections import defaultdict
import asyncio
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime

from src.utils.logger import logger
from src.core.exceptions import StateError
from src.config.manager import ConfigManager


class FSMState(Enum):
    """FSM 統一狀態定義"""
    IDLE = auto()                 # 閒置等待
    LISTENING = auto()           # 等待喚醒詞
    ACTIVATED = auto()           # 喚醒視窗（連續對話）
    RECORDING = auto()           # 錄音中（非串流）
    STREAMING = auto()           # 串流中（串流模式）
    TRANSCRIBING = auto()        # 轉譯中（非串流）
    PROCESSING = auto()          # 批次處理中
    BUSY = auto()                # 系統回覆中（LLM/TTS）
    ERROR = auto()               # 錯誤狀態
    RECOVERING = auto()          # 恢復中


class FSMEvent(Enum):
    """FSM 統一事件定義"""
    # Core Events
    START_LISTENING = auto()        # 進入 LISTENING 狀態
    WAKE_TRIGGERED = auto()         # 喚醒成功（語音/按鍵/視覺）
    START_RECORDING = auto()        # 開始錄音（非串流）
    END_RECORDING = auto()          # 錄音結束（VAD/按鍵/視覺）
    BEGIN_TRANSCRIPTION = auto()    # 進入轉譯
    START_ASR_STREAMING = auto()    # 開始 ASR 串流
    END_ASR_STREAMING = auto()      # 結束 ASR 串流
    UPLOAD_FILE = auto()            # 批次上傳
    TRANSCRIPTION_DONE = auto()     # 轉譯完成
    
    # LLM/TTS Events (Inbound)
    LLM_REPLY_STARTED = auto()      # LLM 開始生成回覆
    LLM_REPLY_FINISHED = auto()     # LLM 完成生成
    TTS_PLAYBACK_STARTED = auto()   # TTS 開始播放
    TTS_PLAYBACK_FINISHED = auto()  # TTS 播放完成
    
    # Interrupt Event
    INTERRUPT_REPLY = auto()        # 打斷回覆事件
    
    # System Events
    TIMEOUT = auto()                # 各種超時
    RESET = auto()                  # 重置到 IDLE
    ERROR = auto()                  # 錯誤事件
    RECOVER = auto()                # 恢復事件


class FSMEndTrigger(Enum):
    """結束觸發類型"""
    VAD_TIMEOUT = auto()     # VAD 檢測到靜音超時
    BUTTON = auto()          # 使用者按鈕
    VISION = auto()          # 視覺觸發（未來擴展）
    TIMEOUT = auto()         # 超時觸發


class FSMWakeTrigger(Enum):
    """喚醒觸發類型"""
    WAKE_WORD = auto()       # 喚醒詞觸發
    BUTTON = auto()          # 使用者按鈕
    VISION = auto()          # 視覺觸發（未來擴展）


class InterruptSource(Enum):
    """打斷來源"""
    UI = auto()              # UI 介面觸發
    VISION = auto()          # 視覺檢測觸發
    VOICE = auto()           # 語音檢測觸發


class InterruptTarget(Enum):
    """打斷目標"""
    TTS = auto()             # 僅停止 TTS
    LLM = auto()             # 僅停止 LLM
    BOTH = auto()            # 停止 LLM 和 TTS


class EventDirection(Enum):
    """事件方向定義"""
    INBOUND = auto()         # 外部 → FSM
    INTERNAL = auto()        # ASRHub 內部
    OUTBOUND = auto()        # FSM → 外部


class OutboundEvent(Enum):
    """對外事件類型"""
    ASR_CAPTURE_STARTED = auto()    # ASR 開始擷取
    ASR_CAPTURE_ENDED = auto()      # ASR 結束擷取
    STATE_CHANGED = auto()          # 狀態變更通知


# 事件方向映射
EVENT_DIRECTIONS = {
    # Inbound Events
    FSMEvent.LLM_REPLY_STARTED: EventDirection.INBOUND,
    FSMEvent.LLM_REPLY_FINISHED: EventDirection.INBOUND,
    FSMEvent.TTS_PLAYBACK_STARTED: EventDirection.INBOUND,
    FSMEvent.TTS_PLAYBACK_FINISHED: EventDirection.INBOUND,
    FSMEvent.INTERRUPT_REPLY: EventDirection.INBOUND,
    
    # Internal Events
    FSMEvent.WAKE_TRIGGERED: EventDirection.INTERNAL,
    FSMEvent.START_RECORDING: EventDirection.INTERNAL,
    FSMEvent.START_ASR_STREAMING: EventDirection.INTERNAL,
    FSMEvent.END_RECORDING: EventDirection.INTERNAL,
    FSMEvent.END_ASR_STREAMING: EventDirection.INTERNAL,
    FSMEvent.TRANSCRIPTION_DONE: EventDirection.INTERNAL,
    
    # System Events
    FSMEvent.RESET: EventDirection.INTERNAL,
    FSMEvent.ERROR: EventDirection.INTERNAL,
    FSMEvent.RECOVER: EventDirection.INTERNAL,
}


class FSMStrategy(ABC):
    """FSM 策略抽象基類"""
    
    @abstractmethod
    async def transition(self, state: FSMState, event: FSMEvent, **kwargs) -> Optional[FSMState]:
        """
        根據當前狀態和事件決定下一個狀態
        
        Args:
            state: 當前狀態
            event: 觸發事件
            **kwargs: 額外參數
            
        Returns:
            下一個狀態，如果返回 None 表示保持當前狀態
        """
        pass


class BatchModeStrategy(FSMStrategy):
    """批次模式策略"""
    
    async def transition(self, state: FSMState, event: FSMEvent, **kwargs) -> Optional[FSMState]:
        transitions = {
            (FSMState.IDLE, FSMEvent.UPLOAD_FILE): FSMState.PROCESSING,
            (FSMState.PROCESSING, FSMEvent.TRANSCRIPTION_DONE): FSMState.IDLE,
        }
        return transitions.get((state, event))


class NonStreamingStrategy(FSMStrategy):
    """非串流實時模式策略（如 Whisper）"""
    
    async def transition(self, state: FSMState, event: FSMEvent, **kwargs) -> Optional[FSMState]:
        transitions = {
            (FSMState.IDLE, FSMEvent.START_LISTENING): FSMState.LISTENING,
            (FSMState.LISTENING, FSMEvent.WAKE_TRIGGERED): FSMState.ACTIVATED,
            (FSMState.ACTIVATED, FSMEvent.START_RECORDING): FSMState.RECORDING,
            (FSMState.RECORDING, FSMEvent.END_RECORDING): FSMState.TRANSCRIBING,
            (FSMState.TRANSCRIBING, FSMEvent.TRANSCRIPTION_DONE): FSMState.ACTIVATED,
            # BUSY 狀態轉換由通用規則處理
        }
        return transitions.get((state, event))


class StreamingStrategy(FSMStrategy):
    """串流實時模式策略（如 Google STT、Vosk）"""
    
    async def transition(self, state: FSMState, event: FSMEvent, **kwargs) -> Optional[FSMState]:
        transitions = {
            (FSMState.IDLE, FSMEvent.START_LISTENING): FSMState.LISTENING,
            (FSMState.LISTENING, FSMEvent.WAKE_TRIGGERED): FSMState.ACTIVATED,
            (FSMState.ACTIVATED, FSMEvent.START_ASR_STREAMING): FSMState.STREAMING,
            (FSMState.STREAMING, FSMEvent.END_ASR_STREAMING): FSMState.ACTIVATED,
            # BUSY 狀態轉換由通用規則處理
        }
        return transitions.get((state, event))


class FSMController:
    """FSM 主控制器"""
    
    def __init__(self, strategy: FSMStrategy, config_manager: Optional[ConfigManager] = None):
        """
        初始化 FSM 控制器
        
        Args:
            strategy: FSM 策略
            config_manager: 配置管理器
        """
        self.state = FSMState.IDLE
        self.previous_state = None
        self.strategy = strategy
        self.event_dispatcher = None
        self.logger = logger
        
        # 從 ConfigManager 獲取配置
        self.config = config_manager or ConfigManager()
        
        # 狀態轉換 Hook
        self.state_hooks = defaultdict(lambda: {'enter': [], 'exit': []})
        
        # 計時器管理
        self.timers = {}
        
        # 會話狀態
        self.session_data = {}
        
        # 狀態歷史
        self.state_history = []
        self.max_history = 100
        
        self.logger.info(f"FSM 控制器初始化，策略：{strategy.__class__.__name__}")

    async def add_hook(self, state: FSMState, hook_type: str, callback: Callable):
        """
        添加狀態鉤子（enter/exit）
        
        Args:
            state: 狀態
            hook_type: 鉤子類型（'enter' 或 'exit'）
            callback: 回調函數
        """
        if hook_type in ['enter', 'exit']:
            self.state_hooks[state][hook_type].append(callback)
            self.logger.debug(f"添加 {state.name} 狀態的 {hook_type} 鉤子")

    async def handle_event(self, event: FSMEvent, **kwargs) -> FSMState:
        """
        處理事件（加入通用規則）
        
        Args:
            event: 事件
            **kwargs: 額外參數
            
        Returns:
            當前狀態
        """
        old_state = self.state
        
        try:
            # 記錄事件
            self.logger.debug(f"處理事件：{event.name}，當前狀態：{old_state.name}")
            
            # 1. 先處理通用規則（優先序）
            new_state = await self._apply_common_rules(event, **kwargs)
            
            # 2. 如果通用規則沒有處理，則使用策略
            if new_state is None:
                new_state = await self.strategy.transition(self.state, event, **kwargs)
            
            # 3. 執行狀態轉換
            if new_state and new_state != old_state:
                await self._run_hooks(old_state, new_state)
                self.previous_state = old_state
                self.state = new_state
                
                # 記錄狀態歷史
                self._add_to_history(old_state, new_state, event)
                
                self.logger.info(f"狀態轉換：{old_state.name} -> {new_state.name}")
                
                # 4. 發送狀態變更事件
                if self.event_dispatcher:
                    await self.event_dispatcher.dispatch(OutboundEvent.STATE_CHANGED, {
                        'old_state': old_state.name,
                        'new_state': new_state.name,
                        'event': event.name,
                        'session_id': kwargs.get('session_id'),
                        'timestamp': datetime.now().isoformat()
                    })
                    
        except Exception as e:
            self.logger.error(f"狀態轉換錯誤: {e}")
            # 錯誤時進入 ERROR 狀態
            self.state = FSMState.ERROR
            raise StateError(f"FSM 狀態轉換失敗：{str(e)}")
        
        return self.state

    async def _apply_common_rules(self, event: FSMEvent, **kwargs) -> Optional[FSMState]:
        """
        套用通用轉換規則
        
        Args:
            event: 事件
            **kwargs: 額外參數
            
        Returns:
            下一個狀態，如果返回 None 表示沒有通用規則適用
        """
        current = self.state
        
        # RESET 最高優先級
        if event == FSMEvent.RESET:
            self.logger.debug("執行 RESET，返回 IDLE")
            return FSMState.IDLE
        
        # ERROR/RECOVER
        if event == FSMEvent.ERROR:
            self.logger.debug("進入 ERROR 狀態")
            return FSMState.ERROR
        if event == FSMEvent.RECOVER and current == FSMState.ERROR:
            self.logger.debug("從 ERROR 恢復到 RECOVERING")
            return FSMState.RECOVERING
        
        # TIMEOUT 處理
        if event == FSMEvent.TIMEOUT:
            if current == FSMState.ACTIVATED:
                self.logger.debug("喚醒視窗超時，返回 LISTENING")
                return FSMState.LISTENING
            elif current in [FSMState.RECORDING, FSMState.STREAMING]:
                # 超時結束錄音/串流
                self.logger.debug(f"{current.name} 超時")
                return FSMState.TRANSCRIBING if current == FSMState.RECORDING else FSMState.IDLE
        
        # LLM/TTS 回覆開始 → BUSY
        if event in [FSMEvent.LLM_REPLY_STARTED, FSMEvent.TTS_PLAYBACK_STARTED]:
            if current not in [FSMState.ERROR, FSMState.RECOVERING]:
                self.logger.debug(f"進入 BUSY 狀態：{event.name}")
                return FSMState.BUSY
        
        # BUSY 狀態收斂
        if current == FSMState.BUSY:
            if event == FSMEvent.INTERRUPT_REPLY:
                # 打斷回覆
                target = kwargs.pop('target', InterruptTarget.BOTH)  # 使用 pop 避免重複傳遞
                await self._handle_interrupt(target, **kwargs)
                
                # 如果是語音打斷且已檢測到說話，可直接跳到錄音/串流
                if kwargs.get('source') == InterruptSource.VOICE and kwargs.get('speech_detected'):
                    if self.strategy.__class__.__name__ == 'NonStreamingStrategy':
                        return FSMState.RECORDING
                    elif self.strategy.__class__.__name__ == 'StreamingStrategy':
                        return FSMState.STREAMING
                
                return FSMState.ACTIVATED
            
            elif event == FSMEvent.TTS_PLAYBACK_FINISHED:
                # 檢查配置決定是否保持喚醒
                # 注意：這裡需要確保配置中有相應的設定
                try:
                    # 嘗試從配置中獲取，如果沒有則使用預設值
                    keep_awake = getattr(self.config, 'realtime', {}).get('fcm', {}).get('keepAwakeAfterReply', True)
                except:
                    keep_awake = True  # 預設保持喚醒
                
                if keep_awake:
                    self.logger.debug("TTS 播放完成，保持喚醒視窗")
                    return FSMState.ACTIVATED
                else:
                    self.logger.debug("TTS 播放完成，返回 LISTENING")
                    return FSMState.LISTENING
            
            elif event == FSMEvent.LLM_REPLY_FINISHED:
                # 等待 TTS 接手（由計時器處理）
                self.logger.debug("LLM 完成，等待 TTS 接手")
                await self._start_timer('tts_claim', 3000)  # 預設 3 秒
                return None  # 保持 BUSY 狀態
        
        return None  # 沒有通用規則適用
    
    async def _handle_interrupt(self, target: InterruptTarget, **kwargs):
        """
        處理打斷邏輯
        
        Args:
            target: 打斷目標
            **kwargs: 額外參數
        """
        self.logger.info(f"處理打斷，目標：{target.name}")
        
        if target in [InterruptTarget.TTS, InterruptTarget.BOTH]:
            # 停止 TTS
            await self._stop_tts(**kwargs)
        
        if target in [InterruptTarget.LLM, InterruptTarget.BOTH]:
            # 取消 LLM 串流
            await self._cancel_llm_stream(**kwargs)
    
    async def _stop_tts(self, **kwargs):
        """停止 TTS 播放"""
        # 實際實現會調用 TTS 服務
        self.logger.debug("停止 TTS 播放")
        # TODO: 實際實現時需要調用 TTS 服務的停止方法
    
    async def _cancel_llm_stream(self, **kwargs):
        """取消 LLM 串流"""
        # 實際實現會調用 LLM 服務
        self.logger.debug("取消 LLM 串流")
        # TODO: 實際實現時需要調用 LLM 服務的取消方法
    
    async def _start_timer(self, timer_name: str, timeout_ms: int):
        """
        啟動計時器
        
        Args:
            timer_name: 計時器名稱
            timeout_ms: 超時時間（毫秒）
        """
        if timer_name in self.timers:
            self.timers[timer_name].cancel()
            self.logger.debug(f"取消現有計時器：{timer_name}")
        
        async def timeout_handler():
            await asyncio.sleep(timeout_ms / 1000)
            self.logger.debug(f"計時器 {timer_name} 超時")
            await self.handle_event(FSMEvent.TIMEOUT, timer=timer_name)
        
        self.timers[timer_name] = asyncio.create_task(timeout_handler())
        self.logger.debug(f"啟動計時器：{timer_name}，超時：{timeout_ms}ms")
    
    async def _run_hooks(self, old_state: FSMState, new_state: FSMState):
        """
        執行 Hook，錯誤不影響主流程
        
        Args:
            old_state: 舊狀態
            new_state: 新狀態
        """
        # 執行退出鉤子
        for callback in self.state_hooks[old_state]['exit']:
            try:
                await callback(old_state, new_state)
            except Exception as e:
                self.logger.error(f"Exit hook 錯誤 ({old_state.name}): {e}")
        
        # 執行進入鉤子
        for callback in self.state_hooks[new_state]['enter']:
            try:
                await callback(old_state, new_state)
            except Exception as e:
                self.logger.error(f"Enter hook 錯誤 ({new_state.name}): {e}")
    
    def _add_to_history(self, old_state: FSMState, new_state: FSMState, event: FSMEvent):
        """
        添加到狀態歷史
        
        Args:
            old_state: 舊狀態
            new_state: 新狀態
            event: 觸發事件
        """
        history_entry = {
            'timestamp': datetime.now().isoformat(),
            'old_state': old_state.name,
            'new_state': new_state.name,
            'event': event.name
        }
        
        self.state_history.append(history_entry)
        
        # 限制歷史記錄大小
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)
    
    def cancel_timer(self, name: str):
        """
        取消計時器
        
        Args:
            name: 計時器名稱
        """
        if name in self.timers:
            self.timers[name].cancel()
            del self.timers[name]
            self.logger.debug(f"取消計時器：{name}")
    
    def cancel_all_timers(self):
        """取消所有計時器"""
        for timer in self.timers.values():
            timer.cancel()
        self.timers.clear()
        self.logger.debug("取消所有計時器")
    
    def get_state_info(self) -> Dict[str, Any]:
        """
        獲取狀態資訊
        
        Returns:
            狀態資訊字典
        """
        return {
            "current_state": self.state.name,
            "previous_state": self.previous_state.name if self.previous_state else None,
            "strategy": self.strategy.__class__.__name__,
            "active_timers": list(self.timers.keys()),
            "session_data": self.session_data,
            "history_count": len(self.state_history)
        }
    
    def reset(self):
        """重置到初始狀態"""
        self.logger.info(f"重置 FSM：{self.state.name} -> IDLE")
        self.previous_state = self.state
        self.state = FSMState.IDLE
        self.cancel_all_timers()
        self.session_data.clear()
    
    # 狀態檢查輔助方法
    def is_idle(self) -> bool:
        """檢查是否處於 IDLE 狀態"""
        return self.state == FSMState.IDLE
    
    def is_listening(self) -> bool:
        """檢查是否處於 LISTENING 狀態"""
        return self.state == FSMState.LISTENING
    
    def is_activated(self) -> bool:
        """檢查是否處於 ACTIVATED（喚醒視窗）狀態"""
        return self.state == FSMState.ACTIVATED
    
    def is_busy(self) -> bool:
        """檢查是否處於 BUSY 狀態"""
        return self.state == FSMState.BUSY
    
    def is_recording(self) -> bool:
        """檢查是否處於 RECORDING 狀態"""
        return self.state == FSMState.RECORDING
    
    def is_streaming(self) -> bool:
        """檢查是否處於 STREAMING 狀態"""
        return self.state == FSMState.STREAMING
    
    def can_accept_audio(self) -> bool:
        """檢查是否可以接受音訊輸入"""
        return self.state in [FSMState.LISTENING, FSMState.ACTIVATED, 
                              FSMState.RECORDING, FSMState.STREAMING]
    
    def can_wake(self) -> bool:
        """檢查是否可以接受喚醒"""
        return self.state == FSMState.LISTENING


def select_strategy(provider_type: str) -> FSMStrategy:
    """
    根據 Provider 類型選擇策略
    
    Args:
        provider_type: Provider 類型
        
    Returns:
        對應的策略實例
    """
    strategy_map = {
        'batch': BatchModeStrategy,
        'whisper': NonStreamingStrategy,
        'funasr': NonStreamingStrategy,
        'google_stt': StreamingStrategy,
        'vosk': StreamingStrategy,
        'azure': StreamingStrategy,
    }
    
    strategy_class = strategy_map.get(provider_type.lower(), NonStreamingStrategy)
    return strategy_class()