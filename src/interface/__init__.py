"""Interface 定義模組"""

from .asr_provider import IASRProvider
from .provider_pool_interfaces import (
    PoolError,
    PoolConfig,
    ProviderHealth,
    LeaseRequest,
    LeaseInfo
)

__all__ = [
    'IASRProvider',
    'PoolError',
    'PoolConfig',
    'ProviderHealth',
    'LeaseRequest',
    'LeaseInfo'
]