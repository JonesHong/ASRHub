"""測試 Whisper Provider 單例/非單例模式"""

import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock whisper module
sys.modules['whisper'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()


def test_whisper_provider_singleton_mode():
    """測試 WhisperProvider 單例模式"""
    from src.provider.whisper.whisper_provider import WhisperProvider
    
    # 重置單例
    WhisperProvider.reset_singleton()
    
    # 單例模式（預設）
    provider1 = WhisperProvider(singleton=True)
    provider2 = WhisperProvider(singleton=True)
    assert provider1 is provider2, "單例模式應該返回相同實例"
    
    # 使用 get_singleton()
    provider3 = WhisperProvider.get_singleton()
    assert provider1 is provider3, "get_singleton() 應該返回相同實例"


def test_whisper_provider_non_singleton_mode():
    """測試 WhisperProvider 非單例模式"""
    from src.provider.whisper.whisper_provider import WhisperProvider
    
    # 非單例模式（為 pool 使用）
    provider1 = WhisperProvider(singleton=False)
    provider2 = WhisperProvider(singleton=False)
    assert provider1 is not provider2, "非單例模式應該返回不同實例"
    
    # 非單例模式不影響單例
    singleton = WhisperProvider(singleton=True)
    assert singleton is not provider1
    assert singleton is not provider2


def test_faster_whisper_provider_singleton_mode():
    """測試 FasterWhisperProvider 單例模式"""
    from src.provider.whisper.faster_whisper_provider import FasterWhisperProvider
    
    # 重置單例
    FasterWhisperProvider.reset_singleton()
    
    # 單例模式（預設）
    provider1 = FasterWhisperProvider(singleton=True)
    provider2 = FasterWhisperProvider(singleton=True)
    assert provider1 is provider2, "單例模式應該返回相同實例"
    
    # 使用 get_singleton()
    provider3 = FasterWhisperProvider.get_singleton()
    assert provider1 is provider3, "get_singleton() 應該返回相同實例"


def test_faster_whisper_provider_non_singleton_mode():
    """測試 FasterWhisperProvider 非單例模式"""
    from src.provider.whisper.faster_whisper_provider import FasterWhisperProvider
    
    # 非單例模式（為 pool 使用）
    provider1 = FasterWhisperProvider(singleton=False)
    provider2 = FasterWhisperProvider(singleton=False)
    assert provider1 is not provider2, "非單例模式應該返回不同實例"
    
    # 非單例模式不影響單例
    singleton = FasterWhisperProvider(singleton=True)
    assert singleton is not provider1
    assert singleton is not provider2


def test_module_level_singletons():
    """測試模組層級單例"""
    # 從 __init__.py 導入
    from src.provider.whisper import whisper_provider, faster_whisper_provider
    from src.provider.whisper.whisper_provider import WhisperProvider
    from src.provider.whisper.faster_whisper_provider import FasterWhisperProvider
    
    # 模組層級單例應該是對應類別的實例
    assert isinstance(whisper_provider, WhisperProvider)
    assert isinstance(faster_whisper_provider, FasterWhisperProvider)
    
    # 確認類別有必要的方法
    assert hasattr(WhisperProvider, 'get_singleton')
    assert hasattr(WhisperProvider, 'reset_singleton')
    assert hasattr(FasterWhisperProvider, 'get_singleton')
    assert hasattr(FasterWhisperProvider, 'reset_singleton')
    
    # 確認模組層級單例是正確的實例
    assert whisper_provider.__class__.__name__ == 'WhisperProvider'
    assert faster_whisper_provider.__class__.__name__ == 'FasterWhisperProvider'