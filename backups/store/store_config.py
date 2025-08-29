"""
Store 配置和初始化
簡化設計，減少全局變量和複雜度
"""

from pystorex import Store, create_store
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass, field

from .sessions import sessions_reducer, SessionEffects
from .stats import stats_reducer, StatsEffects, StatsReportingEffects
from src.core.audio_queue_manager import AudioQueueManager, get_audio_queue_manager, configure_audio_queue_manager
from src.utils.logger import logger


@dataclass
class StoreConfig:
    """Store 配置容器"""
    audio_queue_manager: Optional[AudioQueueManager] = None
    # pipeline_manager removed - functionality moved to SessionEffects
    provider_manager: Optional[Any] = None
    metrics_client: Optional[Any] = None
    operator_factories: Dict[str, Callable] = field(default_factory=dict)
    provider_factories: Dict[str, Callable] = field(default_factory=dict)

class ASRHubStore:
    """
    ASRHub Store 管理器
    單一責任：管理 PyStoreX Store 實例和相關配置
    """
    
    def __init__(self, config: Optional[StoreConfig] = None):
        """
        初始化 Store
        
        Args:
            config: Store 配置
        """
        self.config = config or StoreConfig()
        self._store: Optional[Store] = None
        self._session_effects: Optional[SessionEffects] = None
        
    @property
    def store(self) -> Store:
        """獲取 Store 實例（延遲初始化）"""
        if self._store is None:
            self._initialize()
        return self._store
    
    def _initialize(self):
        """初始化 Store 和 Effects"""
        # 1. 創建 Store
        self._store = create_store()
        
        # 2. 註冊 Reducers
        self._store.register_root({
            "sessions": sessions_reducer,
            "stats": stats_reducer
        })
        
        # 3. 創建並註冊 Effects
        self._register_effects()
        
        logger.info("✓ Store initialized")
    
    def _register_effects(self):
        """註冊 Effects"""
        # 確保有 AudioQueueManager
        if self.config.audio_queue_manager is None:
            self.config.audio_queue_manager = get_audio_queue_manager()
        
        # 創建 SessionEffects 並保存引用
        self._session_effects = SessionEffects(
            store=self._store,
            audio_queue_manager=self.config.audio_queue_manager
        )
        
        # 注入管理器
        # Pipeline functionality now handled by SessionEffects internally
        if self.config.provider_manager:
            self._session_effects.provider_manager = self.config.provider_manager
            
        # 注入工廠函數
        if self.config.operator_factories:
            self._session_effects.operator_factories = self.config.operator_factories
        if self.config.provider_factories:
            self._session_effects.provider_factories = self.config.provider_factories
        
        # 註冊所有 Effects
        effects = [
            self._session_effects,
        ]
        
        for effect in effects:
            self._store.register_effects(effect)
            
        logger.info(f"✓ {len(effects)} Effects registered")
    
    def update_config(self, **kwargs):
        """
        更新配置
        
        Args:
            **kwargs: 要更新的配置項
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                
                # 如果 Store 已初始化，同步更新到 Effects
                if self._session_effects:
                    if key in ['provider_manager']:
                        setattr(self._session_effects, key, value)
                    elif key == 'operator_factories':
                        self._session_effects.operator_factories = value
                    elif key == 'provider_factories':
                        self._session_effects.provider_factories = value
    
    def dispatch(self, action: Dict[str, Any]):
        """分發 Action"""
        return self.store.dispatch(action)
    
    def get_state(self) -> Dict[str, Any]:
        """獲取當前狀態"""
        return self.store.state
    
    def subscribe(self, callback: Callable):
        """訂閱狀態變化"""
        return self.store.subscribe(callback)
    
    def reset(self):
        """重置 Store（用於測試）"""
        self._store = None
        self._session_effects = None
        logger.debug("Store reset")

# 全局 Store 實例
_global_hub_store: Optional[ASRHubStore] = None


def get_global_store() -> Store[Dict[str, Any]]:
    """
    獲取全局 Store 實例（兼容舊版 API）
    
    Returns:
        PyStoreX Store 實例
    """
    hub_store = get_hub_store()
    return hub_store.store


def get_hub_store(config: Optional[StoreConfig] = None) -> ASRHubStore:
    """
    獲取全局 Hub Store 實例
    
    Args:
        config: Store 配置（僅在首次初始化時使用）
    
    Returns:
        ASRHubStore 實例
    """
    global _global_hub_store
    
    if _global_hub_store is None:
        _global_hub_store = ASRHubStore(config)
        
    return _global_hub_store


def configure_global_store(metrics_client=None,
                          provider_manager=None,
                          audio_queue_manager=None) -> Store:
    """
    配置全局 Store（兼容舊版 API）
    
    Args:
        metrics_client: 指標客戶端
        provider_manager: Provider 管理器 (可選)
        audio_queue_manager: 音訊佇列管理器 (可選，會自動創建)
    
    Returns:
        配置好的 Store 實例
    """
    # 如果沒有提供 AudioQueueManager，創建一個
    if audio_queue_manager is None:
        audio_queue_manager = configure_audio_queue_manager()
        logger.info("✓ AudioQueueManager created automatically")
    
    # 創建配置
    config = StoreConfig(
        audio_queue_manager=audio_queue_manager,
        provider_manager=provider_manager,
        metrics_client=metrics_client
    )
    
    # 獲取或創建 Hub Store
    hub_store = get_hub_store(config)
    
    logger.info("✓ Global Store configured successfully")
    return hub_store.store


def reset_global_store():
    """
    重置全局 Store（用於測試隔離）
    """
    global _global_hub_store
    if _global_hub_store:
        _global_hub_store.reset()
    _global_hub_store = None
