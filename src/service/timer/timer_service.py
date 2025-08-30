"""
Timer Service for managing countdown timers

管理靜音超時倒數計時器的無狀態服務。
"""

import threading
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from src.utils.logger import logger
from src.config.manager import ConfigManager


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
            
            # 載入配置
            config = ConfigManager()
            if hasattr(config, 'services') and hasattr(config.services, 'timer'):
                self.timer_config = config.services.timer
            else:
                logger.warning("Timer 配置不存在")
                return
            
            # 檢查是否啟用
            if not self.timer_config.enabled:
                logger.info("Timer 服務已停用 (enabled: false)")
                return
            
            # 初始化計時器存儲
            self._timers: Dict[str, TimerState] = {}
            
            # 載入配置參數（不使用 getattr，直接從 yaml 獲取）
            self._max_timers_per_session = self.timer_config.max_timers_per_session
            self._max_total_timers = self.timer_config.max_total_timers
            self._cleanup_interval = self.timer_config.cleanup_interval
            self._auto_cleanup = self.timer_config.auto_cleanup
            self._default_timeout = self.timer_config.default_timeout
            self._min_duration = self.timer_config.min_duration
            self._max_duration = self.timer_config.max_duration
            self._precision = self.timer_config.precision
            
            logger.info(f"TimerService 已初始化 - max_timers: {self._max_total_timers}, auto_cleanup: {self._auto_cleanup}")
    
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
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            logger.debug("Timer 服務未啟用，跳過倒數計時")
            return False
        
        # 檢查計時器數量限制
        if len(self._timers) >= self._max_total_timers:
            logger.warning(f"計時器數量已達上限 {self._max_total_timers}")
            return False
        
        # 檢查持續時間範圍
        if duration < self._min_duration or duration > self._max_duration:
            logger.warning(f"計時器持續時間 {duration} 超出範圍 [{self._min_duration}, {self._max_duration}]")
            return False
        
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
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            return False
        
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
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            return False
        
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
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            return False
        
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
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            return False
        
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
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            return False
        
        if session_id not in self._timers:
            return False
        return self._timers[session_id].is_active
    
    def cleanup(self):
        """清理所有計時器"""
        # 檢查服務是否啟用
        if not self.timer_config.enabled:
            return
        
        for session_id in list(self._timers.keys()):
            self.stop_timer(session_id)
        logger.info("All timers cleaned up")


# 模組級單例
timer_service = TimerService()