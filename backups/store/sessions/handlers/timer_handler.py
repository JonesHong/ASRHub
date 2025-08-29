"""
計時器效果處理模組

使用 TimerService 處理會話超時、錄音超時等計時相關的效果
"""

from typing import Optional
from src.utils.logger import logger
from .base import BaseEffectHandler
from src.core.timer_manager import get_timer_manager

timer_manager = get_timer_manager()

class SessionTimerHandler(BaseEffectHandler):
    """Session 計時器相關的 Effects Handler
    
    使用 TimerService 管理會話和錄音的超時處理
    """
    
    def __init__(self, store=None, audio_queue_manager=None, session_id=None):
        """初始化
        
        Args:
            store: PyStoreX store 實例
            audio_queue_manager: 音訊隊列管理器（如果未提供會自動獲取）
            session_id: Session ID
        """
        super().__init__(store, audio_queue_manager)
        
        # 保存 session_id 和 timer_manager 參考
        self.session_id = session_id
        
        # 如果沒有提供 audio_queue_manager，自動獲取
        if not self.audio_queue_manager:
            from src.core.audio_queue_manager import get_audio_queue_manager
            self.audio_queue_manager = get_audio_queue_manager()
    
    def get_or_create_timer_service(self, session_id):
        """獲取或創建 TimerService
        
        Args:
            session_id: Session ID
            
        Returns:
            TimerService 實例
        """
        timer_service = timer_manager.get_timer(session_id)
        if not timer_service:
            # 如果不存在，創建新的
            import asyncio
            timer_service = asyncio.run(timer_manager.create_timer(session_id))
        return timer_service
    
    def session_timeout(self, action_stream):
        """會話超時 Effect
        
        使用 TimerService 處理長時間未活動的會話自動重置
        
        Args:
            action_stream: RxPy action stream
            
        Returns:
            Observable stream
        """
        # 為每個 session 使用對應的 TimerService
        # 這裡使用通用處理，因為 session_timeout 處理所有 sessions
        # 創建一個臨時的 TimerService 用於通用處理
        from src.core.timer_service import TimerService
        temp_service = TimerService(session_id="global")
        timeout_handler = temp_service.create_session_timeout(timeout_seconds=300.0)
        return timeout_handler(action_stream)
    
    def recording_timeout(self, action_stream):
        """錄音超時 Effect
        
        使用 TimerService 處理錄音時間過長時自動結束錄音
        
        Args:
            action_stream: RxPy action stream
            
        Returns:
            Observable stream
        """
        # 創建一個臨時的 TimerService 用於通用處理
        from src.core.timer_service import TimerService
        temp_service = TimerService(session_id="global")
        timeout_handler = temp_service.create_recording_timeout(
            get_session_state=self.get_session_state
        )
        return timeout_handler(action_stream)
    
    def silence_timeout(self, action_stream):
        """靜音超時 Effect
        
        使用 TimerService 檢測到長時間靜音時結束錄音
        
        Args:
            action_stream: RxPy action stream
            
        Returns:
            Observable stream
        """
        # 創建一個臨時的 TimerService 用於通用處理
        from src.core.timer_service import TimerService
        temp_service = TimerService(session_id="global")
        timeout_handler = temp_service.create_silence_timeout(
            get_session_state=self.get_session_state,
            default_timeout=2.0
        )
        return timeout_handler(action_stream)
    
    def cleanup(self):
        """清理資源
        
        使用 TimerManager 進行清理
        """
        # 如果有特定的 session_id，清理對應的 timer
        if self.session_id:
            import asyncio
            asyncio.run(timer_manager.destroy_timer(self.session_id))
        logger.debug("Timer handler cleanup completed")