"""
ASR Hub 日誌系統配置
使用 pretty-loguru 提供美化的日誌輸出
"""

from typing import Optional
from pretty_loguru import create_logger, ConfigTemplates, LoggerConfig
from src.config.manager import ConfigManager

# 獲取配置管理器實例
config = ConfigManager()

# 全域配置實例，確保所有 logger 共享相同的配置和文件
_global_config: Optional[LoggerConfig] = None
_shared_logger = None


def _get_shared_logger():
    """獲取或創建共享的 logger 實例"""
    global _global_config, _shared_logger
    
    if _shared_logger is None:
        # 根據環境選擇配置模板
        if config.system.mode == "development":
            _global_config = ConfigTemplates.development()
        elif config.system.mode == "production":
            _global_config = ConfigTemplates.production()
        elif config.system.mode == "testing":
            _global_config = ConfigTemplates.testing()
        else:
            # 預設使用開發環境配置
            _global_config = ConfigTemplates.development()
        
        # 從 ConfigManager 自訂配置
        _global_config.log_path = config.logging.path
        _global_config.rotation = config.logging.rotation
        _global_config.retention = config.logging.retention
        _global_config.level = config.logging.level
        
        # 根據 format 設定調整輸出格式
        if config.logging.format == "simple":
            _global_config.format_string = "{time:HH:mm:ss} | {level} | {name} | {message}"
        elif config.logging.format == "json":
            _global_config.serialize = True
        elif config.logging.format == "pretty":
            # Pretty 格式保持預設（已經很漂亮了）
            pass
        # standard 格式使用預設的完整格式
        
        # 創建共享的 logger 實例
        _shared_logger = create_logger("asr_hub", config=_global_config)
        
    return _shared_logger


def get_logger(module_name: str, custom_config: Optional[LoggerConfig] = None):
    """
    為特定模組建立 logger
    
    Args:
        module_name: 模組名稱，將作為日誌的模組標識
        custom_config: 自定義的 LoggerConfig，如果不提供則使用預設配置
        
    Returns:
        配置好的 logger 實例
    """
    if custom_config is not None:
        # 如果提供了自定義配置，創建獨立的 logger
        full_name = f"asr_hub.{module_name}"
        return create_logger(full_name, config=custom_config)
    
    # 使用共享的 logger，透過綁定 context 來區分模組
    shared_logger = _get_shared_logger()
    # 綁定模組名稱作為 context，這樣在日誌中可以看到是哪個模組
    return shared_logger.bind(module=module_name)


def setup_global_exception_handler():
    """
    設置全域異常處理器，確保未捕獲的異常都會被記錄
    """
    import sys
    from loguru import logger
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
    
    sys.excepthook = handle_exception


# 建立一個預設的 logger 供整個應用程式使用
default_logger = get_logger("main")


# 匯出常用的 logger 方法作為模組級別函式
def trace(message, *args, **kwargs):
    """追蹤級別日誌"""
    default_logger.trace(message, *args, **kwargs)


def debug(message, *args, **kwargs):
    """除錯級別日誌"""
    default_logger.debug(message, *args, **kwargs)


def info(message, *args, **kwargs):
    """資訊級別日誌"""
    default_logger.info(message, *args, **kwargs)


def success(message, *args, **kwargs):
    """成功級別日誌"""
    default_logger.success(message, *args, **kwargs)


def warning(message, *args, **kwargs):
    """警告級別日誌"""
    default_logger.warning(message, *args, **kwargs)


def error(message, *args, **kwargs):
    """錯誤級別日誌"""
    default_logger.error(message, *args, **kwargs)


def critical(message, *args, **kwargs):
    """嚴重錯誤級別日誌"""
    default_logger.critical(message, *args, **kwargs)


def exception(message, *args, **kwargs):
    """異常日誌（自動包含堆疊追蹤）"""
    default_logger.exception(message, *args, **kwargs)


# 視覺化日誌方法
def block(title, content, **kwargs):
    """顯示 Rich 區塊"""
    default_logger.block(title, content, **kwargs)


def ascii_header(text, **kwargs):
    """顯示 ASCII 藝術標題"""
    default_logger.ascii_header(text, **kwargs)


def table(data, **kwargs):
    """顯示表格"""
    default_logger.table(data, **kwargs)


def tree(data, **kwargs):
    """顯示樹狀結構"""
    default_logger.tree(data, **kwargs)


def progress(iterable, **kwargs):
    """顯示進度條"""
    return default_logger.progress(iterable, **kwargs)