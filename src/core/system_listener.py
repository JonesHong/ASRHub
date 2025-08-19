"""
系統層監聽器實作
Always-on 監聽，獨立於用戶層 Pipeline，最小資源消耗設計
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import numpy as np

from src.operators.wakeword import OpenWakeWordOperator
# from src.stream.audio_stream import AudioStreamProcessor  # 已移除，改用新的音訊處理器
from src.store import get_global_store
from src.store.sessions import sessions_actions
from src.store.sessions.sessions_state import  FSMStateEnum
from src.utils.logger import logger
from src.config.manager import ConfigManager

# 模組級變數
config_manager = ConfigManager()


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
    
    def __init__(self, session_id: Optional[str] = None):
        """初始化系統監聽器"""
        
        # PyStoreX 整合
        self.session_id = session_id
        self.store = get_global_store() if session_id else None
        
        # 狀態管理
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
        if hasattr(config_manager, 'wake_word_detection') and config_manager.wake_word_detection.enabled:
            self.wake_timeout = config_manager.wake_word_detection.wake_timeout
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
            logger.warning("系統監聽器已在運行")
            return
        
        logger.info("啟動系統監聽器...")
        
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
            
            logger.info("✓ 系統監聽器啟動成功")
            
        except Exception as e:
            logger.error(f"系統監聽器啟動失敗: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止系統監聽器"""
        if not self.is_running:
            return
        
        logger.info("停止系統監聽器...")
        
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
        
        # 重置狀態 (透過 PyStoreX)
        if self.store and self.session_id:
            self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
        
        # 取消訂閱
        if hasattr(self, 'state_subscription'):
            self.state_subscription.dispose()
        
        logger.info("✓ 系統監聽器已停止")
    
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
                    logger.info("系統監聽器被配置禁用")
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
        # TODO: 這裡需要實作新的音訊流處理器
        # 暫時設為 None，待新的音訊處理架構實作
        self.audio_stream = None
        logger.warning("音訊流處理器尚未實作，SystemListener 暫時禁用")
    
    def _setup_fsm_callbacks(self):
        """設定 FSM 回呼 (PyStoreX 版本)"""
        # 在 PyStoreX 中，我們透過訂閱 _state_subject 來監聽狀態變化
        if self.store and self.session_id:
            # 訂閱狀態變化
            self.state_subscription = self.store._state_subject.subscribe(
                lambda state: asyncio.create_task(self._handle_state_change(state))
            )
            logger.debug("已設定 PyStoreX 狀態訂閱")
    
    async def _audio_processing_loop(self):
        """音訊處理主迴圈"""
        try:
            while self.is_running:
                # 只在 IDLE 狀態且啟用時處理音訊
                if self._is_idle() and self.is_enabled and self.audio_stream:
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
            logger.debug("音訊處理迴圈被取消")
        except Exception as e:
            logger.error(f"音訊處理錯誤: {e}")
            await self._emit_event("error", {"error": str(e)})
    
    async def _on_wakeword_detected(self, detection: Dict[str, Any]):
        """喚醒詞偵測回呼"""
        if not self._can_wake():
            logger.debug("系統不在 IDLE 狀態，忽略喚醒詞")
            return
        
        logger.info(f"🎯 系統層偵測到喚醒詞: {detection}")
        
        # 更新統計
        self.stats["total_wakes"] += 1
        self.stats["wake_word_wakes"] += 1
        
        # 記錄喚醒資訊
        self.last_wake_time = datetime.now()
        self.wake_source = "wake_word"
        
        # 觸發狀態轉換 (透過 PyStoreX)
        if self.store and self.session_id:
            self.store.dispatch(
                sessions_actions.wake_triggered(
                    self.session_id,
                    confidence=detection.get('confidence', 0.5),
                    trigger="wake_word"
                )
            )
        
        # 發送事件
        await self._emit_event("wake_detected", {
            "source": "wake_word",
            "detection": detection,
            "timestamp": self.last_wake_time.isoformat()
        })
    
    async def wake_from_ui(self):
        """從 UI 喚醒"""
        if not self._can_wake():
            logger.warning("系統不在 IDLE 狀態，無法從 UI 喚醒")
            return False
        
        logger.info("從 UI 喚醒系統")
        
        # 更新統計
        self.stats["total_wakes"] += 1
        self.stats["ui_wakes"] += 1
        
        # 記錄喚醒資訊
        self.last_wake_time = datetime.now()
        self.wake_source = "ui"
        
        # 觸發狀態轉換 (透過 PyStoreX)
        if self.store and self.session_id:
            self.store.dispatch(
                sessions_actions.wake_triggered(
                    self.session_id,
                    confidence=1.0,
                    trigger="ui"
                )
            )
        
        # 發送事件
        await self._emit_event("wake_detected", {
            "source": "ui",
            "timestamp": self.last_wake_time.isoformat()
        })
        
        return True
    
    async def sleep(self):
        """手動休眠"""
        if self._is_idle():
            logger.debug("系統已在 IDLE 狀態")
            return
        
        logger.info("手動休眠系統")
        
        # 觸發狀態轉換 (透過 PyStoreX)
        if self.store and self.session_id:
            self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
    
    async def _handle_state_change(self, state):
        """處理 PyStoreX 狀態變化"""
        if not self.session_id or not hasattr(state, 'sessions'):
            return
        
        sessions = state.sessions.get('sessions', {})
        session = sessions.get(self.session_id)
        if not session:
            return
        
        new_state = session.get('fsm_state')
        old_state = session.get('previous_state')
        
        # 進入 ACTIVATED 狀態時啟動超時計時器
        if new_state == FSMStateEnum.ACTIVATED and old_state != FSMStateEnum.ACTIVATED:
            logger.debug(f"進入 ACTIVATED 狀態，啟動 {self.wake_timeout}秒 超時計時器")
            if self.wake_timeout_task:
                self.wake_timeout_task.cancel()
            self.wake_timeout_task = asyncio.create_task(self._wake_timeout_handler())
        
        # 離開 ACTIVATED 狀態時取消超時計時器
        elif old_state == FSMStateEnum.ACTIVATED and new_state != FSMStateEnum.ACTIVATED:
            logger.debug("離開 ACTIVATED 狀態，取消超時計時器")
            if self.wake_timeout_task:
                self.wake_timeout_task.cancel()
                self.wake_timeout_task = None
        
        # 狀態轉換通知
        if old_state != new_state:
            await self._emit_event("state_changed", {
                "old_state": old_state.value if old_state else None,
                "new_state": new_state.value if new_state else None,
                "timestamp": datetime.now().isoformat()
            })
    
    async def _wake_timeout_handler(self):
        """喚醒超時處理"""
        try:
            await asyncio.sleep(self.wake_timeout)
            
            if self._is_activated():
                logger.info("喚醒超時，返回 IDLE 狀態")
                
                # 更新統計
                self.stats["timeouts"] += 1
                
                # 觸發超時事件 (透過 PyStoreX)
                if self.store and self.session_id:
                    self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
                
        except asyncio.CancelledError:
            logger.debug("超時計時器被取消")
    
    def _is_idle(self) -> bool:
        """檢查是否在 IDLE 狀態"""
        if not self.store or not self.session_id:
            return True  # 預設為 IDLE
        
        state = self.store.state
        if hasattr(state, 'sessions') and state.sessions:
            sessions = state.sessions.get('sessions', {})
            session = sessions.get(self.session_id)
            if session:
                return session.get('fsm_state') == FSMStateEnum.IDLE
        return True
    
    def _is_activated(self) -> bool:
        """檢查是否在 ACTIVATED 狀態"""
        if not self.store or not self.session_id:
            return False
        
        state = self.store.state
        if hasattr(state, 'sessions') and state.sessions:
            sessions = state.sessions.get('sessions', {})
            session = sessions.get(self.session_id)
            if session:
                return session.get('fsm_state') == FSMStateEnum.ACTIVATED
        return False
    
    def _can_wake(self) -> bool:
        """檢查是否可以喚醒"""
        return self._is_idle()
    
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
        logger.debug(f"註冊事件處理器: {event_type}")
    
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
                logger.error(f"事件處理器錯誤 ({event_type}): {e}")
    
    def get_state(self) -> str:
        """獲取當前狀態"""
        if not self.store or not self.session_id:
            return FSMStateEnum.IDLE.value
        
        state = self.store.state
        if hasattr(state, 'sessions') and state.sessions:
            sessions = state.sessions.get('sessions', {})
            session = sessions.get(self.session_id)
            if session:
                fsm_state = session.get('fsm_state', FSMStateEnum.IDLE)
                return fsm_state.value
        return FSMStateEnum.IDLE.value
    
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
        logger.info(f"設定喚醒超時: {timeout}秒")
    
    def enable(self):
        """啟用系統監聽"""
        self.is_enabled = True
        logger.info("系統監聽已啟用")
    
    def disable(self):
        """禁用系統監聽"""
        self.is_enabled = False
        logger.info("系統監聽已禁用")