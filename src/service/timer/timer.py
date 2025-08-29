"""計時器服務實作
核心職責：
1. 為每個 session 提供倒數計時功能
2. 倒數歸零時觸發 callback
3. 支援重置和停止計時
"""

import time
import threading
from typing import Callable, Optional, Dict, Any

from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.interface.timer import TimerInfo, TimerStatus
from src.interface.exceptions import (
    TimerError,
    TimerSessionError,
    TimerConfigError,
    TimerNotFoundError
)

# 取得配置管理器
config_manager = ConfigManager()


class Timer(SingletonMixin):
    """計時器服務實作
    
    核心功能：
    - 為每個 session 提供獨立的倒數計時
    - 倒數歸零時觸發 callback
    - 支援重置和停止計時
    - 簡單的 session-based 架構
    """
    
    def __init__(self):
        """初始化計時器服務"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # Session 管理
            self._sessions: Dict[str, Dict[str, Any]] = {}
            self._session_lock = threading.Lock()
            
            # 載入預設配置
            self._default_duration = self._load_default_duration()
            
            logger.info("Timer 服務初始化完成")
    
    def _load_default_duration(self) -> float:
        """從 ConfigManager 載入預設倒數時間
        
        Returns:
            預設倒數時間（秒）
        """
        try:
            if hasattr(config_manager, 'services') and hasattr(config_manager.services, 'timer'):
                timer_config = config_manager.services.timer
                if hasattr(timer_config, 'default_duration'):
                    return float(timer_config.default_duration)
            return 60.0  # 預設 60 秒
        except Exception as e:
            logger.warning(f"載入預設倒數時間失敗: {e}")
            return 60.0
    
    def start_countdown(
        self,
        session_id: str,
        callback: Callable[[str], None],
        duration: Optional[float] = None
    ) -> bool:
        """開始倒數計時
        
        為指定 session 開始倒數計時，時間歸零時觸發 callback。
        
        Args:
            session_id: Session ID
            callback: 倒數歸零時的回調函數，接收 session_id 作為參數
            duration: 倒數時間（秒），None 使用預設值
            
        Returns:
            是否成功開始倒數
            
        Raises:
            TimerSessionError: Session 參數錯誤
            TimerConfigError: 倒數時間設定錯誤
            
        Example:
            # 定義 callback
            def on_timer_complete(session_id):
                print(f"⏰ Session {session_id} 倒數結束！")
            
            # 開始倒數（使用預設時間）
            timer.start_countdown("user_123", on_timer_complete)
            
            # 開始倒數（指定 30 秒）
            timer.start_countdown("user_456", on_timer_complete, duration=30)
            
        Note:
            - 每個 session 只能有一個計時器
            - 如果 session 已有計時器在執行，會先停止舊的再開始新的
            - Callback 在倒數歸零時觸發一次
        """
        # 參數驗證
        if not session_id:
            raise TimerSessionError("Session ID 不能為空")
        
        if not callable(callback):
            raise TimerSessionError("必須提供有效的回調函數")
        
        # 決定倒數時間
        countdown_duration = duration if duration is not None else self._default_duration
        
        # 驗證倒數時間
        if countdown_duration <= 0:
            raise TimerConfigError(f"倒數時間必須大於 0，收到: {countdown_duration}")
        
        if countdown_duration > 86400:  # 最多 24 小時
            raise TimerConfigError(f"倒數時間不能超過 24 小時，收到: {countdown_duration}")
        
        # 如果已有計時器在執行，忽略請求
        with self._session_lock:
            if session_id in self._sessions and self._sessions[session_id]["active"]:
                logger.warning(f"Session {session_id} 已有計時器")
                return True

        # 建立計時器執行緒
        timer_thread = threading.Timer(
            countdown_duration,
            self._on_countdown_complete,
            args=(session_id, callback)
        )
        timer_thread.daemon = True
        
        # 註冊 session
        with self._session_lock:
            self._sessions[session_id] = {
                "active": True,
                "thread": timer_thread,
                "callback": callback,
                "duration": countdown_duration,
                "remaining": countdown_duration,
                "started_at": time.time()
            }
        
        # 啟動計時器
        timer_thread.start()
        logger.info(f"開始倒數 [{session_id}]: {countdown_duration} 秒")
        
        return True
    
    def _on_countdown_complete(self, session_id: str, callback: Callable):
        """倒數完成時的處理
        
        Args:
            session_id: Session ID
            callback: 回調函數
        """
        # 更新狀態
        with self._session_lock:
            if session_id in self._sessions:
                self._sessions[session_id]["active"] = False
                self._sessions[session_id]["remaining"] = 0
        
        logger.info(f"倒數完成 [{session_id}]")
        
        # 觸發 callback（在鎖外執行避免死鎖）
        try:
            callback(session_id)
        except Exception as e:
            logger.error(f"計時器 callback 執行錯誤 [{session_id}]: {e}")
    
    def reset_countdown(
        self,
        session_id: str,
        duration: Optional[float] = None
    ) -> bool:
        """重置倒數計時
        
        重新開始倒數，使用原本的 callback。
        
        Args:
            session_id: Session ID
            duration: 新的倒數時間（秒），None 使用原本的時間
            
        Returns:
            是否成功重置
            
        Raises:
            TimerNotFoundError: Session 沒有計時器
            
        Example:
            # 重置為原本的時間
            timer.reset_countdown("user_123")
            
            # 重置為新的時間
            timer.reset_countdown("user_123", duration=45)
        """
        with self._session_lock:
            if session_id not in self._sessions:
                raise TimerNotFoundError(f"Session {session_id} 沒有計時器")
            
            session_data = self._sessions[session_id]
            
            # 停止現有計時器
            if session_data["active"] and session_data["thread"]:
                session_data["thread"].cancel()
            
            # 決定新的倒數時間
            new_duration = duration if duration is not None else session_data["duration"]
            
            # 建立新的計時器
            timer_thread = threading.Timer(
                new_duration,
                self._on_countdown_complete,
                args=(session_id, session_data["callback"])
            )
            timer_thread.daemon = True
            
            # 更新 session 資料
            session_data["active"] = True
            session_data["thread"] = timer_thread
            session_data["duration"] = new_duration
            session_data["remaining"] = new_duration
            session_data["started_at"] = time.time()
        
        # 啟動新計時器
        timer_thread.start()
        logger.info(f"重置倒數 [{session_id}]: {new_duration} 秒")
        
        return True
    
    def stop_countdown(self, session_id: str) -> bool:
        """停止倒數計時
        
        停止指定 session 的倒數計時。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止（False 表示沒有計時器）
            
        Example:
            if timer.stop_countdown("user_123"):
                print("成功停止倒數")
            else:
                print("沒有計時器在執行")
        """
        with self._session_lock:
            return self._stop_timer_internal(session_id)
    
    def _stop_timer_internal(self, session_id: str) -> bool:
        """內部停止計時器方法（需在鎖內呼叫）
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止
        """
        if session_id not in self._sessions:
            logger.warning(f"Session {session_id} 沒有計時器")
            return False
        
        session_data = self._sessions[session_id]
        
        # 取消計時器執行緒
        if session_data["active"] and session_data["thread"]:
            session_data["thread"].cancel()
            session_data["active"] = False
            
            # 計算剩餘時間
            if session_data["started_at"]:
                elapsed = time.time() - session_data["started_at"]
                session_data["remaining"] = max(0, session_data["duration"] - elapsed)
            
            logger.info(f"停止倒數 [{session_id}]，剩餘: {session_data['remaining']:.1f} 秒")
            return True
        
        return False
    
    def clear_countdown(self, session_id: str) -> bool:
        """清除倒數計時
        
        停止並移除指定 session 的計時器。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功清除
            
        Example:
            timer.clear_countdown("user_123")
        """
        with self._session_lock:
            if session_id not in self._sessions:
                return False
            
            # 先停止
            self._stop_timer_internal(session_id)
            
            # 移除 session 資料
            del self._sessions[session_id]
            logger.info(f"清除計時器 [{session_id}]")
            
            return True
    
    def get_remaining_time(self, session_id: str) -> Optional[float]:
        """取得剩餘時間
        
        Args:
            session_id: Session ID
            
        Returns:
            剩餘秒數，如果沒有計時器返回 None
            
        Example:
            remaining = timer.get_remaining_time("user_123")
            if remaining is not None:
                print(f"剩餘 {remaining:.1f} 秒")
        """
        with self._session_lock:
            if session_id not in self._sessions:
                return None
            
            session_data = self._sessions[session_id]
            
            if not session_data["active"]:
                return session_data["remaining"]
            
            # 計算實時剩餘時間
            elapsed = time.time() - session_data["started_at"]
            remaining = max(0, session_data["duration"] - elapsed)
            
            return remaining
    
    def get_timer_info(self, session_id: str) -> Optional[TimerInfo]:
        """取得計時器資訊
        
        Args:
            session_id: Session ID
            
        Returns:
            計時器資訊，如果沒有計時器返回 None
            
        Example:
            info = timer.get_timer_info("user_123")
            if info:
                print(f"剩餘: {info.remaining:.1f}/{info.duration:.1f} 秒")
        """
        with self._session_lock:
            if session_id not in self._sessions:
                return None
            
            session_data = self._sessions[session_id]
            
            # 計算實時剩餘時間
            if session_data["active"]:
                elapsed = time.time() - session_data["started_at"]
                remaining = max(0, session_data["duration"] - elapsed)
            else:
                remaining = session_data["remaining"]
            
            return TimerInfo(
                timer_id=f"timer_{session_id}",  # 生成 timer_id
                session_id=session_id,
                purpose="countdown",  # 預設用途
                duration=session_data["duration"],
                remaining=remaining,
                status=TimerStatus.RUNNING if session_data["active"] else TimerStatus.PAUSED,
                created_at=session_data.get("started_at", time.time()),
                started_at=session_data["started_at"],
                metadata={"callback": session_data.get("callback") is not None}
            )
    
    def is_counting_down(self, session_id: str) -> bool:
        """檢查是否正在倒數
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在倒數
            
        Example:
            if timer.is_counting_down("user_123"):
                print("計時器執行中")
        """
        with self._session_lock:
            if session_id not in self._sessions:
                return False
            return self._sessions[session_id]["active"]
    
    def clear_all(self) -> int:
        """清除所有計時器
        
        Returns:
            清除的計時器數量
        """
        with self._session_lock:
            session_ids = list(self._sessions.keys())
        
        count = 0
        for session_id in session_ids:
            if self.clear_countdown(session_id):
                count += 1
        
        if count > 0:
            logger.info(f"清除了 {count} 個計時器")
        
        return count
    
    def shutdown(self):
        """關閉服務"""
        logger.info("關閉 Timer 服務")
        
        # 停止所有計時器
        count = self.clear_all()
        
        logger.info(f"Timer 服務已關閉，清除了 {count} 個計時器")


# 模組級單例
timer: Timer = Timer()

__all__ = ['Timer', 'timer', 'TimerInfo']