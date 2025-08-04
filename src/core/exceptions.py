"""
ASR Hub 自定義異常類別
定義系統專用的異常類型
"""


class ASRHubException(Exception):
    """ASR Hub 基礎異常類別"""
    pass


class ConfigurationError(ASRHubException):
    """配置相關錯誤"""
    pass


class PipelineError(ASRHubException):
    """Pipeline 處理相關錯誤"""
    pass


class ProviderError(ASRHubException):
    """ASR Provider 相關錯誤"""
    pass


class StreamError(ASRHubException):
    """串流處理相關錯誤"""
    pass


class SessionError(ASRHubException):
    """Session 管理相關錯誤"""
    pass


class APIError(ASRHubException):
    """API 相關錯誤"""
    pass


class ValidationError(ASRHubException):
    """資料驗證錯誤"""
    pass


class AudioFormatError(ASRHubException):
    """音訊格式相關錯誤"""
    pass


class TimeoutError(ASRHubException):
    """超時錯誤"""
    pass


class ResourceError(ASRHubException):
    """資源相關錯誤（記憶體、GPU 等）"""
    pass


class ModelError(ASRHubException):
    """模型載入或執行錯誤"""
    pass


class StateError(ASRHubException):
    """狀態機相關錯誤"""
    pass