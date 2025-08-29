"""
ASR Hub 日誌系統配置
使用 pretty-loguru 提供美化的日誌輸出
"""

import os
import sys
from pretty_loguru import create_logger, ConfigTemplates

try:
    from src.config.manager import ConfigManager
    config = ConfigManager()
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False

# 建立主要的 logger 實例
if HAS_CONFIG:
    # 根據環境選擇配置模板
    # yaml2py 會提供預設值，不需要 getattr
    mode = config.system.mode
    if mode == 'production':
        base_config = ConfigTemplates.production()
    elif mode == 'testing':
        base_config = ConfigTemplates.testing()
    else:
        base_config = ConfigTemplates.development()
    
    # 套用自定義配置（如果存在）
    kwargs = {}
    if hasattr(config, 'logging'):
        if hasattr(config.logging, 'path'):
            kwargs['log_path'] = config.logging.path
        if hasattr(config.logging, 'level'):
            kwargs['level'] = config.logging.level
        if hasattr(config.logging, 'rotation'):
            kwargs['rotation'] = config.logging.rotation
        if hasattr(config.logging, 'retention'):
            kwargs['retention'] = config.logging.retention
    
    # 使用基礎配置並套用自定義設定
    logger = create_logger("asr_hub",use_native_format=True, config=base_config, **kwargs)
else:
    # 沒有配置時使用預設值
    logger = create_logger(
        "asr_hub",
        log_path=os.getenv("LOG_PATH", "./logs"),
        level=os.getenv("LOG_LEVEL", "INFO")
    )


def setup_global_exception_handler():
    """
    設置全域異常處理器，確保未捕獲的異常都會被記錄
    """
    import sys
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
    
    sys.excepthook = handle_exception