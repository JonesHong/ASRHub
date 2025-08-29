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


class ServiceError(ASRHubException):
    """服務相關錯誤"""
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


class ConnectionError(ASRHubException):
    """連線相關錯誤"""
    pass


class RouterError(ASRHubException):
    """路由相關錯誤"""
    pass


# Service-specific exceptions for unified error handling
class ServiceInitializationError(ServiceError):
    """服務初始化失敗"""
    pass


class ServiceConfigurationError(ServiceError):
    """服務配置錯誤"""
    pass


class ServiceExecutionError(ServiceError):
    """服務執行時錯誤"""
    pass


class ModelLoadError(ServiceError):
    """模型載入失敗"""
    pass


class AudioProcessingError(ServiceError):
    """音訊處理錯誤"""
    pass


class SessionManagementError(ServiceError):
    """Session 管理錯誤"""
    pass


class MonitoringError(ServiceError):
    """監控執行緒相關錯誤"""
    pass


class QueueOperationError(ServiceError):
    """佇列操作錯誤"""
    pass


class ConversionError(ServiceError):
    """音訊轉換錯誤"""
    pass


# Wakeword Service Exceptions
class WakewordError(ServiceError):
    """喚醒詞服務基礎錯誤"""
    pass


class WakewordModelError(WakewordError):
    """喚醒詞模型相關錯誤"""
    pass


class WakewordSessionError(WakewordError):
    """喚醒詞 Session 管理錯誤"""
    pass


class WakewordDetectionError(WakewordError):
    """喚醒詞偵測執行錯誤"""
    pass


class WakewordInitializationError(WakewordError):
    """喚醒詞服務初始化錯誤"""
    pass


class WakewordAudioError(WakewordError):
    """喚醒詞音訊處理錯誤"""
    pass


# VAD Service Exceptions
class VADError(ServiceError):
    """VAD 服務基礎錯誤"""
    pass


class VADModelError(VADError):
    """VAD 模型相關錯誤"""
    pass


class VADSessionError(VADError):
    """VAD Session 管理錯誤"""
    pass


class VADDetectionError(VADError):
    """VAD 偵測執行錯誤"""
    pass


class VADInitializationError(VADError):
    """VAD 服務初始化錯誤"""
    pass


class VADAudioError(VADError):
    """VAD 音訊處理錯誤"""
    pass


# Timer Service Exceptions
class TimerError(ServiceError):
    """計時器服務基礎錯誤"""
    pass


class TimerSessionError(TimerError):
    """計時器 Session 管理錯誤"""
    pass


class TimerConfigError(TimerError):
    """計時器配置錯誤"""
    pass


class TimerNotFoundError(TimerError):
    """計時器不存在錯誤"""
    pass