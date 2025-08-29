"""
TimerManager - 集中管理所有 session 的 TimerService 實例
符合 PyStoreX 的 Redux 原則，使用全域實例管理模式
支援 RxPy 響應式計時器管理

設計原則：
1. Session 管理 - 管理多個 session 的計時器服務
2. 生命週期管理 - 創建、銷毀和清理計時器
3. 資源限制 - 限制最大 session 數量
4. 統計追踪 - 提供計時器統計資訊
"""

import asyncio
from typing import Dict, Optional
from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.core.timer_service import TimerService


config_manager = ConfigManager()
class TimerManager:
    """
    管理所有 session 的 TimerService 實例
    使用全域實例管理，確保全域只有一個 TimerManager
    """
    _instance = None  # 單例實例

    def __new__(cls, *args, **kwargs): 
        """
        創建或返回單例實例。
        """
        if cls._instance is None: 
            cls._instance = super().__new__(cls) 
        return cls._instance
    
    def __init__(self, max_sessions: int = 1000):
        """
        初始化 TimerManager
        
        Args:
            max_sessions: 最大 session 數量
        """
        self.max_sessions = max_sessions
        self.timers: Dict[str, TimerService] = {}
        self._lock = asyncio.Lock()
        
        logger.info(f"TimerManager initialized with max_sessions={max_sessions}, instance_id={id(self)}")
    
    async def create_timer(self, session_id: str) -> TimerService:
        """
        為指定的 session 建立 timer
        
        Args:
            session_id: Session ID
            
        Returns:
            TimerService 實例
        """
        async with self._lock:
            if session_id in self.timers:
                logger.warning(f"Timer already exists for session: {session_id}")
                return self.timers[session_id]
            
            if len(self.timers) >= self.max_sessions:
                # 清理最舊的非活動計時器
                await self._cleanup_oldest_timer()
            
            try:
                timer = TimerService(session_id)
                self.timers[session_id] = timer
                logger.debug(f"Created timer for session: {session_id}")
                return timer
            except Exception as e:
                logger.error(f"Failed to create timer for session {session_id}: {e}")
                raise
    
    def get_timer(self, session_id: str) -> Optional[TimerService]:
        """
        取得指定 session 的 timer
        
        Args:
            session_id: Session ID
            
        Returns:
            TimerService 實例，如果不存在則返回 None
        """
        timer = self.timers.get(session_id)
        if not timer:
            logger.debug(f"No timer found for session: {session_id}")
        return timer
    
    async def destroy_timer(self, session_id: str) -> None:
        """
        銷毀指定 session 的 timer
        
        Args:
            session_id: Session ID
        """
        async with self._lock:
            if session_id not in self.timers:
                logger.warning(f"No timer to destroy for session: {session_id}")
                return
            
            try:
                timer = self.timers[session_id]
                # 清理 RxPy 計時器資源
                timer.cleanup()
                # 從管理器中移除
                del self.timers[session_id]
                logger.debug(f"Destroyed timer for session: {session_id}")
            except Exception as e:
                logger.error(f"Failed to destroy timer for session {session_id}: {e}")
                raise
    
    async def destroy_all_timers(self) -> None:
        """
        銷毀所有 timers（用於系統關閉時）
        """
        async with self._lock:
            session_ids = list(self.timers.keys())
            for session_id in session_ids:
                try:
                    timer = self.timers[session_id]
                    timer.cleanup()
                    logger.debug(f"Timer cleaned up for session: {session_id}")
                except Exception as e:
                    logger.error(f"Error cleaning up timer for session {session_id}: {e}")
            
            self.timers.clear()
            logger.info(f"Cleaned up all timers ({len(session_ids)} sessions)")
    
    def get_active_session_count(self) -> int:
        """
        取得活躍的 session 數量
        
        Returns:
            活躍 session 數量
        """
        return len(self.timers)
    
    def get_active_sessions(self) -> list[str]:
        """
        取得所有活躍的 session IDs
        
        Returns:
            Session ID 列表
        """
        return list(self.timers.keys())
    
    def has_timer(self, session_id: str) -> bool:
        """
        檢查指定 session 是否有 timer
        
        Args:
            session_id: Session ID
            
        Returns:
            是否存在 timer
        """
        return session_id in self.timers
    
    async def _cleanup_oldest_timer(self):
        """清理最舊的非活動計時器"""
        if not self.timers:
            return
        
        # 找出最舊的計時器 (可以根據創建時間或其他標準)
        # 這裡簡單地選擇第一個
        oldest_session = next(iter(self.timers.keys()))
        
        logger.info(f"Cleaning up oldest timer: {oldest_session}")
        await self.destroy_timer(oldest_session)
