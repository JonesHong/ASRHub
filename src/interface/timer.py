"""計時器服務介面定義

定義計時器服務的抽象介面。
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Any, Dict, List
from dataclasses import dataclass
from enum import Enum


class TimerStatus(Enum):
    """計時器狀態。"""
    PENDING = "pending"      # 等待開始
    RUNNING = "running"      # 運行中
    PAUSED = "paused"       # 暫停
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


@dataclass
class TimerInfo:
    """計時器資訊。"""
    timer_id: str
    session_id: str
    purpose: str
    duration: float  # 秒
    remaining: float  # 剩餘秒數
    status: TimerStatus
    created_at: float
    started_at: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class ITimerService(ABC):
    """計時器服務介面。"""
    
    @abstractmethod
    def create_timer(
        self,
        session_id: str,
        purpose: str,
        duration: float,
        callback: Optional[Callable[[], None]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """創建新的倒數計時器。
        
        Args:
            session_id: Session ID
            purpose: 用途說明（如 'vad_timeout', 'session_idle'）
            duration: 倒數時間（秒）
            callback: 倒數結束時的回調函數
            metadata: 額外的元數據
            
        Returns:
            timer_id: 計時器 ID
        """
        pass
    
    @abstractmethod
    def start_timer(self, timer_id: str) -> bool:
        """啟動計時器。
        
        Args:
            timer_id: 計時器 ID
            
        Returns:
            是否成功啟動
        """
        pass
    
    @abstractmethod
    def pause_timer(self, timer_id: str) -> bool:
        """暫停計時器。
        
        Args:
            timer_id: 計時器 ID
            
        Returns:
            是否成功暫停
        """
        pass
    
    @abstractmethod
    def resume_timer(self, timer_id: str) -> bool:
        """恢復計時器。
        
        Args:
            timer_id: 計時器 ID
            
        Returns:
            是否成功恢復
        """
        pass
    
    @abstractmethod
    def reset_timer(self, timer_id: str, new_duration: Optional[float] = None) -> bool:
        """重置計時器。
        
        Args:
            timer_id: 計時器 ID
            new_duration: 新的倒數時間（秒），None 表示使用原始時間
            
        Returns:
            是否成功重置
        """
        pass
    
    @abstractmethod
    def cancel_timer(self, timer_id: str) -> bool:
        """取消計時器。
        
        Args:
            timer_id: 計時器 ID
            
        Returns:
            是否成功取消
        """
        pass
    
    @abstractmethod
    def update_timer(
        self,
        timer_id: str,
        duration: Optional[float] = None,
        callback: Optional[Callable[[], None]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新計時器設定。
        
        Args:
            timer_id: 計時器 ID
            duration: 新的倒數時間（秒）
            callback: 新的回調函數
            metadata: 新的元數據
            
        Returns:
            是否成功更新
        """
        pass
    
    @abstractmethod
    def get_timer_info(self, timer_id: str) -> Optional[TimerInfo]:
        """取得計時器資訊。
        
        Args:
            timer_id: 計時器 ID
            
        Returns:
            計時器資訊
        """
        pass
    
    @abstractmethod
    def get_session_timers(self, session_id: str) -> List[TimerInfo]:
        """取得特定 session 的所有計時器。
        
        Args:
            session_id: Session ID
            
        Returns:
            計時器資訊列表
        """
        pass
    
    @abstractmethod
    def get_timers_by_purpose(self, purpose: str) -> List[TimerInfo]:
        """取得特定用途的所有計時器。
        
        Args:
            purpose: 用途說明
            
        Returns:
            計時器資訊列表
        """
        pass
    
    @abstractmethod
    def clear_session_timers(self, session_id: str) -> int:
        """清除特定 session 的所有計時器。
        
        Args:
            session_id: Session ID
            
        Returns:
            清除的計時器數量
        """
        pass
    
    @abstractmethod
    def clear_all_timers(self) -> int:
        """清除所有計時器。
        
        Returns:
            清除的計時器數量
        """
        pass