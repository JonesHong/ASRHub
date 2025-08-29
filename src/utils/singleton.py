"""單例模式 Mixin 類別

提供通用的單例模式實作，確保類別只有一個實例。
"""

from typing import Dict, Any
import threading


class SingletonMixin:
    """通用單例 Mixin 類別
    
    使用方式：
        class MyService(SingletonMixin):
            def __init__(self):
                if not hasattr(self, '_initialized'):
                    self._initialized = True
                    # 初始化程式碼
    
    特性：
        - 執行緒安全
        - 支援繼承
        - 自動管理實例
    """
    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """建立或返回單例實例
        
        確保每個類別只有一個實例存在。
        使用執行緒鎖確保執行緒安全。
        """
        if cls not in cls._instances:
            with cls._lock:
                # 雙重檢查鎖定模式
                if cls not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[cls] = instance
        return cls._instances[cls]
    
    @classmethod
    def clear_instance(cls):
        """清除單例實例（主要用於測試）"""
        with cls._lock:
            if cls in cls._instances:
                del cls._instances[cls]
    
    @classmethod
    def get_instance(cls):
        """取得單例實例"""
        if cls not in cls._instances:
            return cls()
        return cls._instances[cls]
    
    @classmethod
    def has_instance(cls) -> bool:
        """檢查是否已有實例"""
        return cls in cls._instances