"""
基礎工具和共用函數模組

提供所有 handler 共用的工具函數和基礎類別定義
"""

from typing import Dict, Optional, Any
from pystorex import to_dict
from src.core.audio_queue_manager import AudioQueueManager
from src.utils.time_provider import TimeProvider
from src.utils.logger import logger
audio_queue_manager = AudioQueueManager()

def format_session_id(session_id: str) -> str:
    """安全格式化 session_id 用於日誌顯示
    
    Args:
        session_id: Session ID
        
    Returns:
        格式化後的 session ID (前8個字元)
    """
    if session_id is None:
        return "[None]"
    return session_id[:8] if len(session_id) > 8 else session_id


def ensure_state_dict(state: Any) -> Dict[str, Any]:
    """確保 state 轉換為字典格式
    
    處理各種可能的 state 格式，統一轉換為字典
    
    Args:
        state: 任意格式的 state
        
    Returns:
        字典格式的 state
    """
    from ..sessions_state import SessionsState
    
    # 確保 state 不是 None
    if state is None:
        return get_initial_state().__dict__
    
    # 確保轉換為字典格式
    if hasattr(state, "__dict__"):
        state = to_dict(state)
    elif not isinstance(state, dict):
        state = dict(state) if state else get_initial_state().__dict__
    
    return state


def get_initial_state():
    """獲取初始狀態
    
    Returns:
        初始的 SessionsState
    """
    from ..sessions_state import SessionsState
    return SessionsState(
        sessions={},
        active_session_id=None,
        max_sessions=10
    )


def get_session_from_state(state: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
    """從 state 中安全獲取 session
    
    Args:
        state: State 字典
        session_id: Session ID
        
    Returns:
        Session 字典，如果不存在則返回 None
    """
    sessions = to_dict(state.get("sessions", {}))
    
    if session_id not in sessions:
        logger.debug(f"Session {format_session_id(session_id)} not found in state")
        return None
    
    return to_dict(sessions[session_id])


def update_session_timestamp(session: Dict[str, Any]) -> Dict[str, Any]:
    """更新會話時間戳
    
    Args:
        session: Session 字典
        
    Returns:
        更新後的 session 字典
    """
    return {**session, "updated_at": TimeProvider.now()}


class BaseHandler:
    """Handler 基礎類別
    
    提供共用的錯誤處理和日誌記錄功能
    """
    
    @staticmethod
    def log_action(action_type: str, session_id: str, **kwargs):
        """記錄 action
        
        Args:
            action_type: Action 類型
            session_id: Session ID
            **kwargs: 額外的日誌參數
        """
        logger.debug(
            f"[{action_type}] Session: {format_session_id(session_id)}, "
            f"Params: {kwargs}"
        )
    
    @staticmethod
    def validate_session_id(session_id: Optional[str]) -> bool:
        """驗證 session ID
        
        Args:
            session_id: Session ID
            
        Returns:
            是否有效
        """
        if not session_id:
            logger.warning("Missing or invalid session_id")
            return False
        return True


class BaseEffect:
    """Effect 基礎類別
    
    提供共用的 effect 處理功能
    """
    
    def __init__(self, store=None):
        """初始化
        
        Args:
            store: PyStoreX store 實例
        """
        self.store = store
    
    def format_session_id(self, session_id: str) -> str:
        """格式化 session ID
        
        Args:
            session_id: Session ID
            
        Returns:
            格式化後的 session ID
        """
        return format_session_id(session_id)
    
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """獲取 session 狀態
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 狀態字典，如果不存在則返回 None
        """
        if not self.store:
            return None
            
        state = self.store.state
        sessions_state = state.get('sessions', {})
        
        # 處理不同的狀態結構
        if hasattr(sessions_state, 'get'):
            all_sessions = sessions_state.get('sessions', {})
        else:
            all_sessions = {}
            
        if hasattr(all_sessions, 'get'):
            return all_sessions.get(session_id)
        
        return None
    
    def dispatch_error(self, session_id: str, error_msg: str):
        """分發錯誤 action
        
        Args:
            session_id: Session ID
            error_msg: 錯誤訊息
        """
        if self.store:
            from ..sessions_actions import session_error
            self.store.dispatch(session_error(session_id, error_msg))
        # 明確不返回任何值，避免 action 物件被錯誤使用
        return None


class BaseEffectHandler(BaseEffect):
    """Effect Handler 基礎類別
    
    提供完整的 effect 處理功能，包含音訊隊列管理和依賴注入
    """
    
    def __init__(self, store=None):
        """初始化
        
        Args:
            store: PyStoreX store 實例
            audio_queue_manager: 音訊隊列管理器
        """
        super().__init__(store)
        
        # Provider manager 應該通過注入而非全域變數
        self.provider_manager = None
        
        # Operator 和 Provider factories
        self.operator_factories = {}
        self.provider_factories = {}
    
    def set_provider_manager(self, provider_manager):
        """設置 provider manager
        
        Args:
            provider_manager: Provider 管理器實例
        """
        self.provider_manager = provider_manager
    
    def dispatch_action(self, action):
        """分發 action
        
        Args:
            action: 要分發的 action
        """
        if self.store:
            self.store.dispatch(action)
        # 明確不返回任何值，避免 action 物件被錯誤使用
        return None
    
    async def safe_async_call(self, coro, error_msg: str = "Async operation failed"):
        """安全地執行異步操作
        
        Args:
            coro: 協程對象
            error_msg: 錯誤訊息
            
        Returns:
            協程的返回值，或在錯誤時返回 None
        """
        try:
            return await coro
        except Exception as e:
            logger.error(f"{error_msg}: {e}")
            return None


class EffectSubscriptionManager:
    """Effect 訂閱管理器
    
    管理所有 effect 的訂閱和生命週期
    """
    
    def __init__(self):
        """初始化"""
        self.subscriptions = {}
    
    def subscribe(self, name: str, subscription):
        """添加訂閱
        
        Args:
            name: 訂閱名稱
            subscription: RxPy 訂閱對象
        """
        if name in self.subscriptions:
            logger.warning(f"Subscription {name} already exists, replacing")
            self.unsubscribe(name)
        
        self.subscriptions[name] = subscription
        logger.debug(f"Added subscription: {name}")
    
    def unsubscribe(self, name: str):
        """取消訂閱
        
        Args:
            name: 訂閱名稱
        """
        if name in self.subscriptions:
            try:
                self.subscriptions[name].dispose()
                del self.subscriptions[name]
                logger.debug(f"Removed subscription: {name}")
            except Exception as e:
                logger.error(f"Error unsubscribing {name}: {e}")
    
    def unsubscribe_all(self):
        """取消所有訂閱"""
        for name in list(self.subscriptions.keys()):
            self.unsubscribe(name)
        
        logger.info("All effect subscriptions removed")


# 額外的工具函數
def ensure_dict(obj: Any) -> Dict[str, Any]:
    """確保對象為字典格式
    
    Args:
        obj: 任意對象
        
    Returns:
        字典格式的對象
    """
    if hasattr(obj, "__dict__"):
        return to_dict(obj)
    elif isinstance(obj, dict):
        return obj
    else:
        return {}


def extract_session_id(action: Any) -> Optional[str]:
    """從 action 中提取 session_id
    
    Args:
        action: Action 對象
        
    Returns:
        Session ID 或 None
    """
    if hasattr(action, 'payload'):
        payload = action.payload
        if isinstance(payload, dict):
            return payload.get('session_id') or payload.get('id')
        elif hasattr(payload, 'session_id'):
            return payload.session_id
        elif hasattr(payload, 'id'):
            return payload.id
    
    return None