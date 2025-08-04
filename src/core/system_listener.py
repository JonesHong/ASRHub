"""
系統層監聽器實作
Always-on 監聽，獨立於用戶層 Pipeline，最小資源消耗設計
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import numpy as np

from src.pipeline.operators.wakeword import OpenWakeWordOperator
from src.stream.audio_stream import AudioStreamProcessor
from src.core.fsm import StateMachine, State, Event
from src.utils.logger import logger
from src.config.manager import ConfigManager


class SystemListener:
    """
    系統層監聽器
    
    特點：
    - Always-on 持續監聽
    - 獨立於用戶層 Pipeline
    - 最小資源消耗設計
    - 支援多種喚醒源
    - 事件驅動架構
    """
    
    def __init__(self):
        """初始化系統監聽器"""
        self.logger = logger
        self.config_manager = ConfigManager()
        
        # 狀態管理
        self.fsm = StateMachine(initial_state=State.IDLE)
        self.is_running = False
        self.is_enabled = True
        
        # 喚醒詞偵測器
        self.wakeword_operator = None
        self.audio_stream = None
        
        # 事件處理
        self.event_handlers: Dict[str, List[Callable]] = {
            "wake_detected": [],
            "state_changed": [],
            "error": []
        }
        
        # 喚醒超時管理
        # 從配置讀取超時時間
        if hasattr(self.config_manager, 'wake_word_detection') and self.config_manager.wake_word_detection.enabled:
            self.wake_timeout = self.config_manager.wake_word_detection.wake_timeout
        else:
            self.wake_timeout = 30.0  # 預設 30 秒
        self.wake_timeout_task = None
        self.last_wake_time = None
        self.wake_source = None
        
        # 音訊處理任務
        self.audio_task = None
        
        # 統計資訊
        self.stats = {
            "total_wakes": 0,
            "wake_word_wakes": 0,
            "ui_wakes": 0,
            "visual_wakes": 0,
            "timeouts": 0,
            "errors": 0
        }
    
    async def start(self):
        """啟動系統監聽器"""
        if self.is_running:
            self.logger.warning("系統監聽器已在運行")
            return
        
        self.logger.info("啟動系統監聽器...")
        
        try:
            # 初始化喚醒詞偵測器
            await self._init_wakeword_detector()
            
            # 初始化音訊流
            await self._init_audio_stream()
            
            # 設定 FSM 回呼
            self._setup_fsm_callbacks()
            
            self.is_running = True
            
            # 啟動音訊處理任務
            self.audio_task = asyncio.create_task(self._audio_processing_loop())
            
            self.logger.info("✓ 系統監聽器啟動成功")
            
        except Exception as e:
            self.logger.error(f"系統監聽器啟動失敗: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止系統監聽器"""
        if not self.is_running:
            return
        
        self.logger.info("停止系統監聽器...")
        
        self.is_running = False
        
        # 取消超時任務
        if self.wake_timeout_task:
            self.wake_timeout_task.cancel()
        
        # 停止音訊處理
        if self.audio_task:
            self.audio_task.cancel()
            try:
                await self.audio_task
            except asyncio.CancelledError:
                pass
        
        # 清理資源
        if self.wakeword_operator:
            await self.wakeword_operator.stop()
        
        if self.audio_stream:
            await self.audio_stream.stop()
        
        # 重置狀態
        self.fsm.reset()
        
        self.logger.info("✓ 系統監聽器已停止")
    
    async def _init_wakeword_detector(self):
        """初始化喚醒詞偵測器"""
        # 從配置讀取設定
        if hasattr(self.config_manager, 'wake_word_detection'):
            wake_config = self.config_manager.wake_word_detection
            self.is_enabled = wake_config.enabled
            self.wake_timeout = wake_config.wake_timeout
            
            # 如果系統監聽器被禁用，直接返回
            if hasattr(wake_config, 'system_listener'):
                if not wake_config.system_listener.enabled:
                    self.logger.info("系統監聽器被配置禁用")
                    self.is_enabled = False
                    return
        
        # 建立喚醒詞偵測器
        self.wakeword_operator = OpenWakeWordOperator()
        
        # 設定偵測回呼
        self.wakeword_operator.set_detection_callback(self._on_wakeword_detected)
        
        # 啟動偵測器
        await self.wakeword_operator.start()
    
    async def _init_audio_stream(self):
        """初始化音訊流"""
        # 這裡使用簡化的音訊流處理器
        # 實際實作可能需要更複雜的音訊輸入管理
        self.audio_stream = AudioStreamProcessor()
        await self.audio_stream.start()
    
    def _setup_fsm_callbacks(self):
        """設定 FSM 回呼"""
        # 進入 LISTENING 狀態時啟動超時計時器
        self.fsm.add_on_enter_callback(State.LISTENING, self._on_enter_listening)
        
        # 離開 LISTENING 狀態時取消超時計時器
        self.fsm.add_on_exit_callback(State.LISTENING, self._on_exit_listening)
        
        # 狀態轉換回呼
        self.fsm.add_on_transition_callback(self._on_state_transition)
    
    async def _audio_processing_loop(self):
        """音訊處理主迴圈"""
        try:
            while self.is_running:
                # 只在 IDLE 狀態且啟用時處理音訊
                if self.fsm.is_idle() and self.is_enabled:
                    # 讀取音訊資料
                    audio_data = await self.audio_stream.read(1280)
                    
                    if audio_data:
                        # 處理音訊（偵測喚醒詞）
                        await self.wakeword_operator.process(
                            audio_data,
                            sample_rate=16000,
                            session_id="system"
                        )
                    else:
                        # 沒有音訊資料時短暫休眠
                        await asyncio.sleep(0.01)
                else:
                    # 非監聽狀態，休眠以節省資源
                    await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            self.logger.debug("音訊處理迴圈被取消")
        except Exception as e:
            self.logger.error(f"音訊處理錯誤: {e}")
            await self._emit_event("error", {"error": str(e)})
    
    async def _on_wakeword_detected(self, detection: Dict[str, Any]):
        """喚醒詞偵測回呼"""
        if not self.fsm.can_wake():
            self.logger.debug("系統不在 IDLE 狀態，忽略喚醒詞")
            return
        
        self.logger.info(f"🎯 系統層偵測到喚醒詞: {detection}")
        
        # 更新統計
        self.stats["total_wakes"] += 1
        self.stats["wake_word_wakes"] += 1
        
        # 記錄喚醒資訊
        self.last_wake_time = datetime.now()
        self.wake_source = "wake_word"
        
        # 觸發狀態轉換
        self.fsm.wake(wake_source="wake_word")
        
        # 發送事件
        await self._emit_event("wake_detected", {
            "source": "wake_word",
            "detection": detection,
            "timestamp": self.last_wake_time.isoformat()
        })
    
    async def wake_from_ui(self):
        """從 UI 喚醒"""
        if not self.fsm.can_wake():
            self.logger.warning("系統不在 IDLE 狀態，無法從 UI 喚醒")
            return False
        
        self.logger.info("從 UI 喚醒系統")
        
        # 更新統計
        self.stats["total_wakes"] += 1
        self.stats["ui_wakes"] += 1
        
        # 記錄喚醒資訊
        self.last_wake_time = datetime.now()
        self.wake_source = "ui"
        
        # 觸發狀態轉換
        self.fsm.wake(wake_source="ui")
        
        # 發送事件
        await self._emit_event("wake_detected", {
            "source": "ui",
            "timestamp": self.last_wake_time.isoformat()
        })
        
        return True
    
    async def sleep(self):
        """手動休眠"""
        if self.fsm.is_idle():
            self.logger.debug("系統已在 IDLE 狀態")
            return
        
        self.logger.info("手動休眠系統")
        
        # 觸發狀態轉換
        self.fsm.sleep()
    
    def _on_enter_listening(self, old_state: State, new_state: State, **kwargs):
        """進入 LISTENING 狀態的回呼"""
        self.logger.debug(f"進入 LISTENING 狀態，啟動 {self.wake_timeout}秒 超時計時器")
        
        # 啟動超時任務
        if self.wake_timeout_task:
            self.wake_timeout_task.cancel()
        
        self.wake_timeout_task = asyncio.create_task(self._wake_timeout_handler())
    
    def _on_exit_listening(self, old_state: State, new_state: State, **kwargs):
        """離開 LISTENING 狀態的回呼"""
        self.logger.debug("離開 LISTENING 狀態，取消超時計時器")
        
        # 取消超時任務
        if self.wake_timeout_task:
            self.wake_timeout_task.cancel()
            self.wake_timeout_task = None
    
    async def _wake_timeout_handler(self):
        """喚醒超時處理"""
        try:
            await asyncio.sleep(self.wake_timeout)
            
            if self.fsm.is_listening():
                self.logger.info("喚醒超時，返回 IDLE 狀態")
                
                # 更新統計
                self.stats["timeouts"] += 1
                
                # 觸發超時事件
                self.fsm.trigger(Event.WAKE_TIMEOUT)
                
        except asyncio.CancelledError:
            self.logger.debug("超時計時器被取消")
    
    def _on_state_transition(self, old_state: State, new_state: State, **kwargs):
        """狀態轉換回呼"""
        self.logger.info(f"系統狀態轉換: {old_state.value} -> {new_state.value}")
        
        # 非同步發送事件
        asyncio.create_task(self._emit_event("state_changed", {
            "old_state": old_state.value,
            "new_state": new_state.value,
            "event": kwargs.get("event", "").value if kwargs.get("event") else None
        }))
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """
        註冊事件處理器
        
        Args:
            event_type: 事件類型（wake_detected, state_changed, error）
            handler: 處理函數
        """
        if event_type not in self.event_handlers:
            raise ValueError(f"未知的事件類型: {event_type}")
        
        self.event_handlers[event_type].append(handler)
        self.logger.debug(f"註冊事件處理器: {event_type}")
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """發送事件"""
        handlers = self.event_handlers.get(event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                self.logger.error(f"事件處理器錯誤 ({event_type}): {e}")
    
    def get_state(self) -> str:
        """獲取當前狀態"""
        return self.fsm.current_state.value
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取統計資訊"""
        return {
            **self.stats,
            "current_state": self.get_state(),
            "is_enabled": self.is_enabled,
            "last_wake_time": self.last_wake_time.isoformat() if self.last_wake_time else None,
            "wake_source": self.wake_source
        }
    
    def set_wake_timeout(self, timeout: float):
        """
        設定喚醒超時時間
        
        Args:
            timeout: 超時秒數
        """
        self.wake_timeout = timeout
        self.logger.info(f"設定喚醒超時: {timeout}秒")
    
    def enable(self):
        """啟用系統監聽"""
        self.is_enabled = True
        self.logger.info("系統監聽已啟用")
    
    def disable(self):
        """禁用系統監聽"""
        self.is_enabled = False
        self.logger.info("系統監聽已禁用")