"""
Store 配置和初始化
"""

from pystorex import Store, create_store
from typing import Optional, Any

from .sessions import SessionEffects, SessionTimerEffects
from .stats import StatsEffects, StatsReportingEffects


class ASRHubStore:
    """ASR Hub 應用程式 Store 封裝"""
    
    def __init__(self, logger=None, metrics_client=None):
        self.logger = logger
        self.metrics_client = metrics_client
        self._store: Optional[Store] = None
        self._effects_instances = {}
        
    def create_store(self) -> Store:
        """創建 PyStoreX Store 實例 - 使用正確的 API"""
        if self._store is None:
            # 1. 創建 store
            self._store = create_store()
            
            # 2. 使用 register_root 註冊 reducers - 這是 PyStoreX 的標準方式
            # 根據 PyStoreX 文檔，register_root 接受一個字典，其中包含所有域的 reducers
            from .sessions import sessions_reducer
            from .stats import stats_reducer
            
            self._store.register_root({
                "sessions": sessions_reducer,
                "stats": stats_reducer
            })
            
            # 3. 設置 Effects
            self._setup_effects()
            
        return self._store
    
    def _setup_effects(self):
        """設置所有 Effects"""
        if not self._store:
            return
            
        # Sessions Effects
        session_effects = SessionEffects(logger=self.logger)
        session_timer_effects = SessionTimerEffects()
        
        # Stats Effects  
        stats_effects = StatsEffects(
            logger=self.logger,
            metrics_client=self.metrics_client
        )
        stats_reporting_effects = StatsReportingEffects(logger=self.logger)
        
        # 儲存 Effects 實例供後續使用
        self._effects_instances = {
            'session': session_effects,
            'session_timer': session_timer_effects,
            'stats': stats_effects,
            'stats_reporting': stats_reporting_effects
        }
        
        # 註冊 Effects 到 Store（如果 PyStoreX 支持的話）
        self._register_effects()
    
    def _register_effects(self):
        """註冊 Effects 到 Store - 使用 PyStoreX 的標準方法"""
        if not self._store:
            return
            
        # 使用 PyStoreX 的 register_effects 方法註冊每個 Effect 實例
        for name, effects_instance in self._effects_instances.items():
            try:
                # PyStoreX 應該有 register_effects 方法
                if hasattr(self._store, 'register_effects'):
                    self._store.register_effects(effects_instance)
                else:
                    # 如果方法名稱不同，嘗試其他可能的名稱
                    if hasattr(self._store, 'add_effects'):
                        self._store.add_effects(effects_instance)
                    elif hasattr(self._store, 'effects'):
                        # 可能需要直接訪問 effects 管理器
                        self._store.effects.register(effects_instance)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"無法註冊 Effects {name}: {e}")
    
    @property
    def store(self) -> Store:
        """獲取 Store 實例"""
        if self._store is None:
            return self.create_store()
        return self._store
    
    def get_state(self) -> Any:
        """獲取當前狀態"""
        if self._store is None:
            self.create_store()
        # PyStoreX 使用 state 屬性來獲取當前狀態
        return self._store.state
    
    def dispatch(self, action):
        """派發 Action"""
        return self.store.dispatch(action)
    
    def subscribe(self, listener):
        """訂閱狀態變更 - 使用 PyStoreX 的標準方法"""
        # PyStoreX 提供 state_stream 或 select 方法來訂閱狀態變更
        if hasattr(self.store, 'state_stream'):
            # 使用 state_stream Observable 來訂閱
            return self.store.state_stream.subscribe(listener)
        elif hasattr(self.store, 'select'):
            # 使用 select 方法來訂閱整個狀態
            return self.store.select(lambda state: state).subscribe(listener)
        else:
            # 如果都沒有，嘗試直接訂閱
            if hasattr(self.store, 'subscribe'):
                return self.store.subscribe(listener)
            else:
                raise NotImplementedError("PyStoreX store 沒有提供訂閱方法")
    
    def get_effects_instance(self, effects_name: str):
        """獲取特定的 Effects 實例"""
        return self._effects_instances.get(effects_name)


# 全局 Store 實例（可選）
_global_store: Optional[ASRHubStore] = None


def get_global_store() -> ASRHubStore:
    """獲取全局 Store 實例"""
    global _global_store
    if _global_store is None:
        _global_store = ASRHubStore()
    return _global_store


def configure_global_store(logger=None, metrics_client=None) -> ASRHubStore:
    """配置全局 Store"""
    global _global_store
    _global_store = ASRHubStore(logger=logger, metrics_client=metrics_client)
    return _global_store


def reset_global_store():
    """重置全局 Store（主要用於測試）"""
    global _global_store
    _global_store = None