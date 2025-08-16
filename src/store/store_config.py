"""
Store 配置和初始化 - 最小化封裝設計
只提供必要的初始化、配置和測試隔離功能
"""

from pystorex import Store, create_store
from typing import Any, Dict, Optional

from .sessions import sessions_reducer, SessionEffects, SessionTimerEffects
from .stats import stats_reducer, StatsEffects, StatsReportingEffects

# 全局 Store 實例
_global_store: Optional[Store[Dict[str, Any]]]=None

def get_global_store() -> Store[Dict[str, Any]]:
    """
    獲取全局 Store 實例（延遲初始化）
    
    Returns:
        PyStoreX Store 實例
    """
    global _global_store
    if _global_store is None:
        _global_store = _create_configured_store()
    return _global_store


def _create_configured_store( metrics_client=None) ->  Store[Dict[str, Any]]:
    """
    創建並配置 Store 實例
    
    Args:
        logger: 日誌實例
        metrics_client: 指標客戶端
    
    Returns:
        配置好的 Store 實例
    """
    # 1. 創建 store
    store = create_store()
    # 2. 註冊 reducers
    store.register_root({
        "sessions": sessions_reducer,
        "stats": stats_reducer
    })
    # 3. 註冊 effects
    _register_effects(store, metrics_client)
    
    return store


def _register_effects(store: Store, metrics_client=None):
    """
    註冊所有 Effects
    
    Args:
        store: PyStoreX Store 實例
        logger: 日誌實例
        metrics_client: 指標客戶端
    """
    # 創建 Effects 實例
    effects = [
        SessionEffects(),
        SessionTimerEffects(),
        StatsEffects( metrics_client=metrics_client),
        StatsReportingEffects()
    ]
    
    # 註冊到 Store
    for effect in effects:
        store.register_effects(effect)


def configure_global_store( metrics_client=None) -> Store:
    """
    配置全局 Store（用於應用初始化）
    
    Args:
        logger: 日誌實例
        metrics_client: 指標客戶端
    
    Returns:
        配置好的 Store 實例
    """
    global _global_store
    _global_store = _create_configured_store( metrics_client)
    return _global_store


def reset_global_store():
    """
    重置全局 Store（用於測試隔離）
    """
    global _global_store
    _global_store = None
