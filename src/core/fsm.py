"""
ASR Hub 有限狀態機實作
管理系統和 Session 的狀態轉換
"""

from enum import Enum
from typing import Dict, List, Callable, Optional, Any
from src.utils.logger import get_logger
from src.core.exceptions import StateError


class State(Enum):
    """系統狀態定義"""
    IDLE = "IDLE"            # 閒置狀態
    LISTENING = "LISTENING"  # 監聽狀態（接收音訊）
    BUSY = "BUSY"           # 忙碌狀態（處理中）


class Event(Enum):
    """狀態轉換事件"""
    START = "START"          # 開始監聽
    STOP = "STOP"           # 停止監聽
    BUSY_START = "BUSY_START"  # 進入忙碌狀態
    BUSY_END = "BUSY_END"    # 結束忙碌狀態
    ERROR = "ERROR"          # 發生錯誤
    TIMEOUT = "TIMEOUT"      # 超時
    
    # 喚醒詞相關事件
    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"  # 偵測到喚醒詞
    WAKE_TIMEOUT = "WAKE_TIMEOUT"              # 喚醒超時
    UI_WAKE = "UI_WAKE"                        # UI 喚醒
    VISUAL_WAKE = "VISUAL_WAKE"                # 視覺喚醒
    SLEEP = "SLEEP"                            # 手動休眠


class StateMachine:
    """
    有限狀態機
    負責管理狀態轉換邏輯
    """
    
    def __init__(self, initial_state: State = State.IDLE):
        """
        初始化狀態機
        
        Args:
            initial_state: 初始狀態
        """
        self.logger = get_logger("fsm")
        self.current_state = initial_state
        self.previous_state = None
        
        # 狀態轉換規則
        self.transitions: Dict[State, Dict[Event, State]] = {
            State.IDLE: {
                Event.START: State.LISTENING,
                Event.BUSY_START: State.BUSY,
                # 喚醒詞相關轉換
                Event.WAKE_WORD_DETECTED: State.LISTENING,
                Event.UI_WAKE: State.LISTENING,
                Event.VISUAL_WAKE: State.LISTENING,
            },
            State.LISTENING: {
                Event.STOP: State.IDLE,
                Event.BUSY_START: State.BUSY,
                Event.ERROR: State.IDLE,
                Event.TIMEOUT: State.IDLE,
                # 喚醒詞相關轉換
                Event.WAKE_TIMEOUT: State.IDLE,
                Event.SLEEP: State.IDLE,
            },
            State.BUSY: {
                Event.BUSY_END: State.LISTENING,
                Event.STOP: State.IDLE,
                Event.ERROR: State.IDLE,
                # 處理完成後可以回到 IDLE 或 LISTENING
                Event.SLEEP: State.IDLE,
            }
        }
        
        # 狀態進入/退出回調
        self.on_enter_callbacks: Dict[State, List[Callable]] = {
            state: [] for state in State
        }
        self.on_exit_callbacks: Dict[State, List[Callable]] = {
            state: [] for state in State
        }
        
        # 轉換回調
        self.on_transition_callbacks: List[Callable] = []
        
        self.logger.debug(f"狀態機初始化，初始狀態：{initial_state.value}")
    
    def trigger(self, event: Event, **kwargs) -> State:
        """
        觸發狀態轉換事件
        
        Args:
            event: 觸發的事件
            **kwargs: 傳遞給回調函式的額外參數
            
        Returns:
            轉換後的狀態
            
        Raises:
            StateError: 如果轉換無效
        """
        # 檢查轉換是否有效
        if event not in self.transitions.get(self.current_state, {}):
            raise StateError(
                f"無效的狀態轉換：{self.current_state.value} -> {event.value}"
            )
        
        # 獲取目標狀態
        target_state = self.transitions[self.current_state][event]
        
        # 執行轉換
        self._transition_to(target_state, event=event, **kwargs)
        
        return self.current_state
    
    def _transition_to(self, target_state: State, **kwargs):
        """
        執行狀態轉換
        
        Args:
            target_state: 目標狀態
            **kwargs: 傳遞給回調函式的額外參數
        """
        if target_state == self.current_state:
            self.logger.debug(f"狀態未改變：{self.current_state.value}")
            return
        
        old_state = self.current_state
        
        # 執行退出回調
        for callback in self.on_exit_callbacks[old_state]:
            try:
                callback(old_state, target_state, **kwargs)
            except Exception as e:
                self.logger.error(f"執行退出回調時發生錯誤：{e}")
        
        # 更新狀態
        self.previous_state = self.current_state
        self.current_state = target_state
        
        # 執行進入回調
        for callback in self.on_enter_callbacks[target_state]:
            try:
                callback(old_state, target_state, **kwargs)
            except Exception as e:
                self.logger.error(f"執行進入回調時發生錯誤：{e}")
        
        # 執行轉換回調
        for callback in self.on_transition_callbacks:
            try:
                callback(old_state, target_state, **kwargs)
            except Exception as e:
                self.logger.error(f"執行轉換回調時發生錯誤：{e}")
        
        self.logger.info(f"狀態轉換：{old_state.value} -> {target_state.value}")
    
    def add_on_enter_callback(self, state: State, callback: Callable):
        """
        添加進入狀態的回調函式
        
        Args:
            state: 狀態
            callback: 回調函式
        """
        self.on_enter_callbacks[state].append(callback)
    
    def add_on_exit_callback(self, state: State, callback: Callable):
        """
        添加退出狀態的回調函式
        
        Args:
            state: 狀態
            callback: 回調函式
        """
        self.on_exit_callbacks[state].append(callback)
    
    def add_on_transition_callback(self, callback: Callable):
        """
        添加狀態轉換的回調函式
        
        Args:
            callback: 回調函式
        """
        self.on_transition_callbacks.append(callback)
    
    def can_trigger(self, event: Event) -> bool:
        """
        檢查是否可以觸發指定事件
        
        Args:
            event: 事件
            
        Returns:
            是否可以觸發
        """
        return event in self.transitions.get(self.current_state, {})
    
    def get_available_events(self) -> List[Event]:
        """
        獲取當前狀態下可用的事件
        
        Returns:
            可用事件列表
        """
        return list(self.transitions.get(self.current_state, {}).keys())
    
    def reset(self):
        """重置狀態機到初始狀態"""
        self.logger.debug(f"重置狀態機：{self.current_state.value} -> {State.IDLE.value}")
        self.previous_state = self.current_state
        self.current_state = State.IDLE
    
    def get_state_info(self) -> Dict[str, Any]:
        """
        獲取狀態機資訊
        
        Returns:
            狀態機資訊字典
        """
        return {
            "current_state": self.current_state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "available_events": [e.value for e in self.get_available_events()]
        }
    
    def is_idle(self) -> bool:
        """檢查是否處於 IDLE 狀態"""
        return self.current_state == State.IDLE
    
    def is_listening(self) -> bool:
        """檢查是否處於 LISTENING 狀態"""
        return self.current_state == State.LISTENING
    
    def is_busy(self) -> bool:
        """檢查是否處於 BUSY 狀態"""
        return self.current_state == State.BUSY
    
    def can_wake(self) -> bool:
        """檢查是否可以接受喚醒"""
        return self.current_state == State.IDLE
    
    def wake(self, wake_source: str = "wake_word") -> State:
        """
        喚醒系統
        
        Args:
            wake_source: 喚醒源（wake_word, ui, visual）
            
        Returns:
            轉換後的狀態
        """
        if wake_source == "wake_word":
            return self.trigger(Event.WAKE_WORD_DETECTED)
        elif wake_source == "ui":
            return self.trigger(Event.UI_WAKE)
        elif wake_source == "visual":
            return self.trigger(Event.VISUAL_WAKE)
        else:
            raise ValueError(f"未知的喚醒源：{wake_source}")
    
    def sleep(self) -> State:
        """
        休眠系統
        
        Returns:
            轉換後的狀態
        """
        return self.trigger(Event.SLEEP)