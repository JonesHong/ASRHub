"""
ASR Hub Session 管理器
管理多個並行的 ASR session
"""

import uuid
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from src.utils.logger import get_logger
from src.core.exceptions import SessionError


class Session:
    """
    單個 ASR Session
    代表一個語音辨識會話
    """
    
    def __init__(self, session_id: Optional[str] = None):
        """
        初始化 Session
        
        Args:
            session_id: Session ID，如果不提供則自動生成
        """
        self.id = session_id or str(uuid.uuid4())
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.state = "IDLE"  # IDLE, LISTENING, BUSY
        self.metadata = {}
        self.pipeline_config = {}
        self.provider_config = {}
        
    def update_activity(self):
        """更新最後活動時間"""
        self.last_activity = datetime.now()
        
    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """
        檢查 Session 是否過期
        
        Args:
            timeout_seconds: 超時秒數，預設 1 小時
            
        Returns:
            是否過期
        """
        return datetime.now() - self.last_activity > timedelta(seconds=timeout_seconds)
    
    def to_dict(self) -> Dict:
        """轉換為字典格式"""
        return {
            "id": self.id,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "metadata": self.metadata,
            "pipeline_config": self.pipeline_config,
            "provider_config": self.provider_config
        }


class SessionManager:
    """
    Session 管理器
    負責建立、查詢、更新和刪除 session
    """
    
    def __init__(self, max_sessions: int = 1000, session_timeout: int = 3600):
        """
        初始化 SessionManager
        
        Args:
            max_sessions: 最大 session 數量
            session_timeout: Session 超時時間（秒）
        """
        self.logger = get_logger("session_manager")
        self.sessions: Dict[str, Session] = {}
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        
        self.logger.info(f"SessionManager 初始化完成，最大 sessions: {max_sessions}")
    
    def create_session(self, session_id: Optional[str] = None, **kwargs) -> Session:
        """
        建立新的 Session
        
        Args:
            session_id: 指定的 session ID
            **kwargs: 其他 session 參數
            
        Returns:
            新建立的 Session
            
        Raises:
            SessionError: 如果達到最大 session 數量限制
        """
        # 清理過期的 sessions
        self._cleanup_expired_sessions()
        
        # 檢查是否達到限制
        if len(self.sessions) >= self.max_sessions:
            raise SessionError(f"已達到最大 session 數量限制：{self.max_sessions}")
        
        # 建立新 session
        session = Session()
        if session_id:
            session.id = session_id
        
        # 設定額外參數
        if "metadata" in kwargs:
            session.metadata = kwargs["metadata"]
        if "pipeline_config" in kwargs:
            session.pipeline_config = kwargs["pipeline_config"]
        if "provider_config" in kwargs:
            session.provider_config = kwargs["provider_config"]
        
        # 儲存 session
        self.sessions[session.id] = session
        
        self.logger.info(f"建立新 session: {session.id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        獲取指定的 Session
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 實例，如果不存在則返回 None
        """
        session = self.sessions.get(session_id)
        if session and not session.is_expired(self.session_timeout):
            session.update_activity()
            return session
        elif session:
            # Session 已過期，移除它
            self.delete_session(session_id)
        return None
    
    def update_session_state(self, session_id: str, state: str):
        """
        更新 Session 狀態
        
        Args:
            session_id: Session ID
            state: 新狀態（IDLE, LISTENING, BUSY）
            
        Raises:
            SessionError: 如果 session 不存在
        """
        session = self.get_session(session_id)
        if not session:
            raise SessionError(f"Session {session_id} 不存在")
        
        old_state = session.state
        session.state = state
        session.update_activity()
        
        self.logger.debug(f"Session {session_id} 狀態變更：{old_state} -> {state}")
    
    def delete_session(self, session_id: str):
        """
        刪除指定的 Session
        
        Args:
            session_id: Session ID
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.logger.info(f"刪除 session: {session_id}")
    
    def list_sessions(self) -> List[Session]:
        """
        列出所有有效的 Sessions
        
        Returns:
            Session 列表
        """
        self._cleanup_expired_sessions()
        return list(self.sessions.values())
    
    def get_session_count(self) -> int:
        """
        獲取當前 session 數量
        
        Returns:
            Session 數量
        """
        self._cleanup_expired_sessions()
        return len(self.sessions)
    
    def _cleanup_expired_sessions(self):
        """清理過期的 sessions"""
        expired_ids = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(self.session_timeout)
        ]
        
        for sid in expired_ids:
            self.delete_session(sid)
        
        if expired_ids:
            self.logger.debug(f"清理了 {len(expired_ids)} 個過期的 sessions")
    
    def clear_all_sessions(self):
        """清除所有 sessions（謹慎使用）"""
        count = len(self.sessions)
        self.sessions.clear()
        self.logger.warning(f"清除了所有 {count} 個 sessions")