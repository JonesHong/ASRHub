"""服務載入器 - 條件式載入服務

根據配置動態載入服務，避免載入停用的服務。
使用 Null Object Pattern 為停用的服務提供空物件。
"""

from typing import Optional, Any, Type
from src.utils.logger import logger
from src.config.manager import ConfigManager


class DisabledService:
    """停用服務的空物件實現
    
    當服務被停用時，返回這個物件而不是真實的服務實例。
    所有方法調用都會返回 None 或 False。
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        logger.debug(f"{service_name} 服務已停用，使用空物件")
    
    def __getattr__(self, name):
        """任何方法調用都返回 None 或 False"""
        def disabled_method(*args, **kwargs):
            # 對於檢查狀態的方法返回 False
            if name.startswith('is_') or name == 'enabled' or name == '_enabled':
                return False
            # 其他方法返回 None
            return None
        return disabled_method
    
    def __bool__(self):
        """布林值為 False"""
        return False


def load_service(
    service_path: str,
    class_name: str,
    instance_name: str,
    config_path: str
) -> Any:
    """條件式載入服務
    
    Args:
        service_path: 服務模組路徑 (如 'src.service.vad.silero_vad')
        class_name: 服務類別名稱 (如 'SileroVAD')
        instance_name: 實例名稱 (如 'silero_vad')
        config_path: 配置路徑 (如 'services.vad')
        
    Returns:
        服務實例或 DisabledService 空物件
    """
    try:
        # 獲取配置
        config = ConfigManager()
        
        # 動態獲取配置節點
        config_node = config
        for part in config_path.split('.'):
            if hasattr(config_node, part):
                config_node = getattr(config_node, part)
            else:
                logger.warning(f"找不到配置 {config_path}")
                return DisabledService(class_name)
        
        # 檢查是否啟用
        if hasattr(config_node, 'enabled') and not config_node.enabled:
            logger.info(f"{class_name} 服務已停用 (enabled: false)")
            return DisabledService(class_name)
        
        # 動態載入模組
        logger.info(f"載入 {class_name} 服務...")
        module = __import__(service_path, fromlist=[class_name])
        
        # 獲取類別和實例
        service_class = getattr(module, class_name)
        
        # 檢查是否已有模組級單例
        if hasattr(module, instance_name):
            instance = getattr(module, instance_name)
            logger.info(f"{class_name} 服務已載入（使用現有實例）")
        else:
            # 創建新實例
            instance = service_class()
            logger.info(f"{class_name} 服務已載入（創建新實例）")
        
        return instance
        
    except ImportError as e:
        logger.error(f"無法載入 {class_name}: {e}")
        return DisabledService(class_name)
    except Exception as e:
        logger.error(f"載入 {class_name} 時發生錯誤: {e}")
        return DisabledService(class_name)


def lazy_load_service(
    service_path: str,
    class_name: str,
    instance_name: str,
    config_path: str
):
    """延遲載入服務的裝飾器
    
    返回一個代理物件，只在第一次使用時才真正載入服務。
    """
    class LazyServiceProxy:
        def __init__(self):
            self._service = None
            self._loaded = False
        
        def _load(self):
            """載入實際的服務"""
            if not self._loaded:
                self._service = load_service(
                    service_path, class_name, instance_name, config_path
                )
                self._loaded = True
            return self._service
        
        def __getattr__(self, name):
            """轉發屬性存取到實際服務"""
            service = self._load()
            return getattr(service, name)
        
        def __bool__(self):
            """檢查服務是否可用"""
            service = self._load()
            return bool(service) if hasattr(service, '__bool__') else service is not None
    
    return LazyServiceProxy()