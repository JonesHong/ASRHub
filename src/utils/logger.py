"""
ASR Hub 日誌系統配置
使用 pretty-loguru 提供美化的日誌輸出
"""

import os
from typing import Optional
from pretty_loguru import create_logger, ConfigTemplates, LoggerConfig
from src.config.manager import ConfigManager

# 獲取配置管理器實例
config = ConfigManager()


def get_logger(module_name: str, custom_config: Optional[LoggerConfig] = None):
    """
    為特定模組建立 logger
    
    Args:
        module_name: 模組名稱，將作為 logger 名稱的一部分
        custom_config: 自定義的 LoggerConfig，如果不提供則使用預設配置
        
    Returns:
        配置好的 logger 實例
    """
    # 根據環境選擇配置模板
    if custom_config is None:
        if config.system.mode == "development":
            logger_config = ConfigTemplates.development()
        elif config.system.mode == "production":
            logger_config = ConfigTemplates.production()
        elif config.system.mode == "testing":
            logger_config = ConfigTemplates.testing()
        else:
            # 預設使用開發環境配置
            logger_config = ConfigTemplates.development()
        
        # 從 ConfigManager 自訂配置
        logger_config.log_path = config.logging.path
        logger_config.rotation = config.logging.rotation
        logger_config.retention = config.logging.retention
        logger_config.level = config.logging.level
        
        # 根據 format 設定調整輸出格式
        if config.logging.format == "simple":
            logger_config.format_string = "{time:HH:mm:ss} | {level} | {message}"
        elif config.logging.format == "json":
            logger_config.serialize = True
        # detailed 格式使用預設的完整格式
        
    else:
        logger_config = custom_config
    
    # 建立完整的 logger 名稱
    full_name = f"asr_hub.{module_name}"
    
    # 建立並返回 logger
    return create_logger(full_name, config=logger_config)


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