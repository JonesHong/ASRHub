"""
ASR Hub Session 管理器
管理多個並行的 ASR session
"""

import uuid
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from src.utils.logger import logger
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
        
        # 喚醒詞相關欄位
        self.wake_timeout = 30.0  # 喚醒超時（秒）
        self.wake_source = None   # 喚醒源（wake_word, ui, visual）
        self.wake_time = None     # 喚醒時間
        self.wake_history = []    # 喚醒歷史記錄
        self.priority = 0         # Session 優先級（0=最低）
        
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
    
    def wake(self, source: str = "wake_word", wake_timeout: Optional[float] = None):
        """
        喚醒 Session
        
        Args:
            source: 喚醒源（wake_word, ui, visual）
            wake_timeout: 喚醒超時時間，如果不提供則使用預設值
        """
        self.wake_source = source
        self.wake_time = datetime.now()
        if wake_timeout is not None:
            self.wake_timeout = wake_timeout
        
        # 記錄喚醒歷史
        self.wake_history.append({
            "source": source,
            "time": self.wake_time.isoformat(),
            "timeout": self.wake_timeout
        })
        
        # 更新活動時間
        self.update_activity()
    
    def is_wake_expired(self) -> bool:
        """
        檢查喚醒是否已超時
        
        Returns:
            是否超時
        """
        if not self.wake_time:
            return False
        
        return datetime.now() - self.wake_time > timedelta(seconds=self.wake_timeout)
    
    def clear_wake(self):
        """清除喚醒狀態"""
        self.wake_source = None
        self.wake_time = None
    
    def to_dict(self) -> Dict:
        """轉換為字典格式"""
        return {
            "id": self.id,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "metadata": self.metadata,
            "pipeline_config": self.pipeline_config,
            "provider_config": self.provider_config,
            # 喚醒詞相關欄位
            "wake_timeout": self.wake_timeout,
            "wake_source": self.wake_source,
            "wake_time": self.wake_time.isoformat() if self.wake_time else None,
            "wake_history": self.wake_history,
            "priority": self.priority,
            "is_wake_expired": self.is_wake_expired()
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
        self.logger = logger
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
        
        # 喚醒詞相關參數
        if "wake_timeout" in kwargs:
            session.wake_timeout = kwargs["wake_timeout"]
        if "wake_source" in kwargs:
            session.wake_source = kwargs["wake_source"]
        if "priority" in kwargs:
            session.priority = kwargs["priority"]
        
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
    
    # 喚醒詞相關方法
    def wake_session(self, session_id: str, source: str = "wake_word", wake_timeout: Optional[float] = None) -> bool:
        """
        喚醒指定 Session
        
        Args:
            session_id: Session ID
            source: 喚醒源
            wake_timeout: 喚醒超時時間
            
        Returns:
            是否成功喚醒
        """
        session = self.get_session(session_id)
        if not session:
            self.logger.warning(f"嘗試喚醒不存在的 session: {session_id}")
            return False
        
        session.wake(source=source, wake_timeout=wake_timeout)
        self.logger.info(f"喚醒 session {session_id}，來源: {source}")
        return True
    
    def get_sessions_by_wake_source(self, source: str) -> List[Session]:
        """
        根據喚醒源獲取 Sessions
        
        Args:
            source: 喚醒源（wake_word, ui, visual）
            
        Returns:
            符合條件的 Session 列表
        """
        return [
            session for session in self.sessions.values()
            if session.wake_source == source and not session.is_expired(self.session_timeout)
        ]
    
    def get_active_wake_sessions(self) -> List[Session]:
        """
        獲取所有處於喚醒狀態且未超時的 Sessions
        
        Returns:
            活躍的喚醒 Session 列表
        """
        return [
            session for session in self.sessions.values()
            if session.wake_time and not session.is_wake_expired() and not session.is_expired(self.session_timeout)
        ]
    
    def get_sessions_by_priority(self, min_priority: int = 0) -> List[Session]:
        """
        根據優先級獲取 Sessions（降序排列）
        
        Args:
            min_priority: 最小優先級
            
        Returns:
            按優先級排序的 Session 列表
        """
        filtered_sessions = [
            session for session in self.sessions.values()
            if session.priority >= min_priority and not session.is_expired(self.session_timeout)
        ]
        
        return sorted(filtered_sessions, key=lambda s: s.priority, reverse=True)
    
    def cleanup_wake_expired_sessions(self):
        """清理喚醒超時的 sessions"""
        expired_count = 0
        
        for session in list(self.sessions.values()):
            if session.is_wake_expired():
                session.clear_wake()
                expired_count += 1
        
        if expired_count > 0:
            self.logger.debug(f"清理了 {expired_count} 個喚醒超時的 sessions")
    
    def get_wake_stats(self) -> Dict[str, int]:
        """
        獲取喚醒統計資訊
        
        Returns:
            統計資訊字典
        """
        all_sessions = list(self.sessions.values())
        
        stats = {
            "total_sessions": len(all_sessions),
            "active_wake_sessions": len(self.get_active_wake_sessions()),
            "wake_word_sessions": len(self.get_sessions_by_wake_source("wake_word")),
            "ui_wake_sessions": len(self.get_sessions_by_wake_source("ui")),
            "visual_wake_sessions": len(self.get_sessions_by_wake_source("visual")),
            "expired_sessions": len([s for s in all_sessions if s.is_expired(self.session_timeout)]),
            "wake_expired_sessions": len([s for s in all_sessions if s.is_wake_expired()])
        }
        
        return stats