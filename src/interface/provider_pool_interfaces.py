"""Provider Pool 介面定義"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any


class PoolError(Enum):
    """Pool 錯誤類型"""
    QUOTA_EXCEEDED = "quota_exceeded"
    TIMEOUT = "timeout"
    POOL_CLOSED = "pool_closed"
    INITIALIZATION_FAILED = "initialization_failed"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealth:
    """Provider 健康狀態"""
    consecutive_failures: int = 0
    total_successes: int = 0
    is_healthy: bool = True
    last_error: Optional[str] = None


@dataclass
class LeaseRequest:
    """租用請求"""
    session_id: str
    requested_at: float
    timeout: float = 10.0


@dataclass  
class LeaseInfo:
    """租用資訊"""
    session_id: str
    provider_id: int  # Provider 的 ID (使用 id() 函數)
    lease_time: float  # 租用時間戳


@dataclass
class PoolConfig:
    """Provider Pool 配置
    
    這個類別應該從 ConfigManager 取得配置，
    不應該包含硬編碼的預設值。
    """
    min_size: int
    max_size: int
    per_session_quota: int
    max_consecutive_failures: int
    health_check_enabled: bool = True
    initialization_timeout: float = 30.0
    lease_timeout: float = 10.0
    provider_type: str = "whisper"  # Provider 類型
    
    @classmethod
    def from_config(cls, config_manager):
        """從 ConfigManager 創建配置"""
        pool_config = config_manager.providers.pool
        provider_type = config_manager.providers.default  # 取得預設 provider
        return cls(
            min_size=pool_config.min_size,
            max_size=pool_config.max_size,
            per_session_quota=pool_config.per_session_quota,
            max_consecutive_failures=pool_config.max_consecutive_failures,
            health_check_enabled=pool_config.health_check_enabled,
            initialization_timeout=pool_config.initialization_timeout,
            lease_timeout=pool_config.lease_timeout,
            provider_type=provider_type
        )