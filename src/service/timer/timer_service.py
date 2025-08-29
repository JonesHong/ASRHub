"""
Timer Service for managing countdown timers

管理靜音超時倒數計時器的無狀態服務。
"""

import threading
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from src.utils.logger import logger


@dataclass
class TimerState:
    """計時器狀態"""
    timer: Optional[threading.Timer]
    duration: float
    callback: Optional[Callable]
    is_active: bool = False


class TimerService:
    """計時器服務 - 管理 session 的倒數計時"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._timers: Dict[str, TimerState] = {}
            logger.info("TimerService initialized")
    
    def start_countdown(self, 
                       session_id: str, 
                       duration: float, 
                       callback: Callable[[str], None]) -> bool:
        """開始倒數計時
        
        Args:
            session_id: Session ID
            duration: 倒數時間（秒）
            callback: 時間到時的回調函數
            
        Returns:
            是否成功啟動
        """
        # 先停止舊的計時器
        self.stop_timer(session_id)
        
        def timeout_handler():
            """超時處理"""
            if session_id in self._timers:
                self._timers[session_id].is_active = False
            callback(session_id)
            logger.debug(f"Timer expired for session {session_id}")
        
        # 創建新計時器
        timer = threading.Timer(duration, timeout_handler)
        self._timers[session_id] = TimerState(
            timer=timer,
            duration=duration,
            callback=callback,
            is_active=True
        )
        
        timer.start()
        logger.debug(f"Started {duration}s countdown for session {session_id}")
        return True
    
    def reset_timer(self, session_id: str) -> bool:
        """重置計時器（重新開始倒數）
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功重置
        """
        if session_id not in self._timers:
            logger.warning(f"No timer found for session {session_id}")
            return False
        
        timer_state = self._timers[session_id]
        if not timer_state.is_active:
            logger.warning(f"Timer for session {session_id} is not active")
            return False
        
        # 停止舊計時器
        if timer_state.timer:
            timer_state.timer.cancel()
        
        # 啟動新計時器
        return self.start_countdown(
            session_id, 
            timer_state.duration, 
            timer_state.callback
        )
    
    def pause_timer(self, session_id: str) -> bool:
        """暫停計時器
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功暫停
        """
        if session_id not in self._timers:
            return False
        
        timer_state = self._timers[session_id]
        if timer_state.timer and timer_state.is_active:
            timer_state.timer.cancel()
            timer_state.is_active = False
            logger.debug(f"Paused timer for session {session_id}")
            return True
        return False
    
    def resume_timer(self, session_id: str) -> bool:
        """恢復計時器
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功恢復
        """
        if session_id not in self._timers:
            return False
        
        timer_state = self._timers[session_id]
        if not timer_state.is_active and timer_state.callback:
            return self.start_countdown(
                session_id,
                timer_state.duration,
                timer_state.callback
            )
        return False
    
    def stop_timer(self, session_id: str) -> bool:
        """停止並移除計時器
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止
        """
        if session_id not in self._timers:
            return False
        
        timer_state = self._timers[session_id]
        if timer_state.timer:
            timer_state.timer.cancel()
        
        del self._timers[session_id]
        logger.debug(f"Stopped timer for session {session_id}")
        return True
    
    def is_active(self, session_id: str) -> bool:
        """檢查計時器是否活躍
        
        Args:
            session_id: Session ID
            
        Returns:
            是否活躍
        """
        if session_id not in self._timers:
            return False
        return self._timers[session_id].is_active
    
    def cleanup(self):
        """清理所有計時器"""
        for session_id in list(self._timers.keys()):
            self.stop_timer(session_id)
        logger.info("All timers cleaned up")


# 模組級單例
timer_service = TimerService()