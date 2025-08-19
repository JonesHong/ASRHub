"""
TimerManager - 集中管理所有 session 的 TimerService 實例
符合 PyStoreX 的 Redux 原則，使用單例模式確保全域唯一性
"""

import asyncio
from typing import Dict, Optional
from src.utils.logger import logger
from src.core.timer_service import TimerService


class TimerManager:
    """
    管理所有 session 的 TimerService 實例
    使用單例模式確保全域只有一個 TimerManager
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """實作單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化 TimerManager"""
        # 避免重複初始化
        if not self._initialized:
            self.timers: Dict[str, TimerService] = {}
            self._lock = asyncio.Lock()
            self.__class__._initialized = True
            logger.info("TimerManager 初始化完成")
    
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
            
            try:
                timer = TimerService(session_id)
                self.timers[session_id] = timer
                logger.info(f"✅ Timer created for session: {session_id}")
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
                # 取消所有計時器
                timer.cancel_all_timers()
                # 從管理器中移除
                del self.timers[session_id]
                logger.info(f"✅ Timer destroyed for session: {session_id}")
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
                    timer.cancel_all_timers()
                    logger.debug(f"Timer canceled for session: {session_id}")
                except Exception as e:
                    logger.error(f"Error canceling timer for session {session_id}: {e}")
            
            self.timers.clear()
            logger.info(f"✅ All timers destroyed ({len(session_ids)} sessions)")
    
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


# 模組級變數 - 全域唯一的 TimerManager 實例
timer_manager = TimerManager()