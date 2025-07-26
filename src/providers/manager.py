"""
ASR Hub Provider Manager
管理多個 ASR Provider 的建立、配置和執行
"""

from typing import Dict, Any, List, Optional, Type
from src.utils.logger import get_logger
from src.core.exceptions import ProviderError, ConfigurationError
from src.providers.base import ProviderBase
from src.providers.whisper.provider import WhisperProvider
from src.config.manager import ConfigManager


class ProviderManager:
    """
    Provider 管理器
    負責建立、管理和協調多個 ASR Provider 實例
    """
    
    def __init__(self):
        """
        初始化 Provider Manager
        使用 ConfigManager 獲取配置
        """
        self.config_manager = ConfigManager()
        self.logger = get_logger("provider.manager")
        
        # Provider 實例快取
        self.providers: Dict[str, ProviderBase] = {}
        
        # 可用的 Provider 類型註冊
        self.provider_registry: Dict[str, Type[ProviderBase]] = {
            "whisper": WhisperProvider,
            # TODO: 註冊其他 providers
        }
        
        # 預設 Provider
        self.default_provider = self.config_manager.providers.default
        
        self._initialized = False
    
    async def initialize(self):
        """初始化 Provider Manager"""
        if self._initialized:
            self.logger.warning("Provider Manager 已經初始化")
            return
        
        self.logger.info("初始化 Provider Manager...")
        
        # 初始化已啟用的 Providers
        await self._initialize_enabled_providers()
        
        # 驗證預設 Provider
        if self.default_provider not in self.providers:
            available = list(self.providers.keys())
            if available:
                self.default_provider = available[0]
                self.logger.warning(
                    f"預設 Provider '{self.default_provider}' 不可用，"
                    f"使用 '{self.default_provider}' 作為預設"
                )
            else:
                raise ConfigurationError("沒有可用的 ASR Provider")
        
        self._initialized = True
        self.logger.success("Provider Manager 初始化完成")
    
    async def _initialize_enabled_providers(self):
        """初始化所有已啟用的 Providers"""
        # Whisper Provider
        if self.config_manager.providers.whisper.enabled:
            await self._create_provider("whisper")
        
        # TODO: 初始化其他 providers (FunASR, Vosk, Azure, etc.)
        
        if not self.providers:
            raise ConfigurationError("至少需要啟用一個 ASR Provider")
    
    async def _create_provider(self, name: str):
        """
        建立並初始化 Provider
        
        Args:
            name: Provider 名稱
        """
        if name not in self.provider_registry:
            self.logger.error(f"未知的 Provider 類型：{name}")
            return
        
        try:
            # 建立 Provider 實例 (Provider 會自己從 ConfigManager 獲取配置)
            provider_class = self.provider_registry[name]
            provider = provider_class()
            
            # 初始化 Provider
            await provider.initialize()
            
            # 儲存到快取
            self.providers[name] = provider
            
            self.logger.info(f"Provider '{name}' 初始化成功")
            
        except Exception as e:
            self.logger.error(f"初始化 Provider '{name}' 失敗：{e}")
            # 繼續初始化其他 providers，不要因為一個失敗就停止
    
    async def create_provider(self,
                            name: str,
                            provider_type: str) -> ProviderBase:
        """
        建立新的 Provider
        
        Args:
            name: Provider 名稱（用於識別）
            provider_type: Provider 類型（如 whisper, funasr）
            
        Returns:
            建立的 Provider 實例
            
        Raises:
            ProviderError: 如果建立失敗
        """
        if name in self.providers:
            raise ProviderError(f"Provider '{name}' 已存在")
        
        if provider_type not in self.provider_registry:
            raise ProviderError(f"未知的 Provider 類型：{provider_type}")
        
        try:
            # 建立 Provider (Provider 會自己從 ConfigManager 獲取配置)
            provider_class = self.provider_registry[provider_type]
            provider = provider_class()
            
            # 初始化
            await provider.initialize()
            
            # 儲存到快取
            self.providers[name] = provider
            
            self.logger.info(f"Provider '{name}' (類型：{provider_type}) 建立成功")
            return provider
            
        except Exception as e:
            self.logger.error(f"建立 Provider '{name}' 失敗：{e}")
            raise ProviderError(f"無法建立 Provider：{str(e)}")
    
    def get_provider(self, name: Optional[str] = None) -> Optional[ProviderBase]:
        """
        獲取指定的 Provider
        
        Args:
            name: Provider 名稱，如果為 None 則返回預設 Provider
            
        Returns:
            Provider 實例，如果不存在則返回 None
        """
        if name is None:
            name = self.default_provider
        
        return self.providers.get(name)
    
    async def remove_provider(self, name: str):
        """
        移除指定的 Provider
        
        Args:
            name: Provider 名稱
        """
        if name == self.default_provider:
            raise ProviderError("不能移除預設 Provider")
        
        if name in self.providers:
            provider = self.providers[name]
            await provider.cleanup()
            del self.providers[name]
            self.logger.info(f"Provider '{name}' 已移除")
    
    def list_providers(self) -> List[str]:
        """
        列出所有 Provider 名稱
        
        Returns:
            Provider 名稱列表
        """
        return list(self.providers.keys())
    
    def get_provider_info(self, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        獲取 Provider 資訊
        
        Args:
            name: Provider 名稱，如果為 None 則返回預設 Provider 資訊
            
        Returns:
            Provider 資訊，如果不存在則返回 None
        """
        provider = self.get_provider(name)
        if provider:
            return provider.get_provider_info()
        return None
    
    def register_provider(self, provider_type: str, provider_class: Type[ProviderBase]):
        """
        註冊新的 Provider 類型
        
        Args:
            provider_type: Provider 類型名稱
            provider_class: Provider 類別
        """
        if not issubclass(provider_class, ProviderBase):
            raise ValueError(f"{provider_class} 必須繼承自 ProviderBase")
        
        self.provider_registry[provider_type] = provider_class
        self.logger.info(f"註冊 Provider 類型：{provider_type}")
    
    def get_registered_providers(self) -> List[str]:
        """
        獲取已註冊的 Provider 類型列表
        
        Returns:
            Provider 類型名稱列表
        """
        return list(self.provider_registry.keys())
    
    async def transcribe(self,
                        audio_data: bytes,
                        provider_name: Optional[str] = None,
                        **kwargs) -> Any:
        """
        使用指定的 Provider 進行轉譯
        
        Args:
            audio_data: 音訊資料
            provider_name: Provider 名稱，如果為 None 則使用預設
            **kwargs: 額外參數
            
        Returns:
            轉譯結果
            
        Raises:
            ProviderError: 如果轉譯失敗
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ProviderError(
                f"Provider '{provider_name or self.default_provider}' 不存在"
            )
        
        return await provider.transcribe(audio_data, **kwargs)
    
    async def transcribe_stream(self,
                              audio_stream: Any,
                              provider_name: Optional[str] = None,
                              **kwargs) -> Any:
        """
        使用指定的 Provider 進行串流轉譯
        
        Args:
            audio_stream: 音訊串流
            provider_name: Provider 名稱，如果為 None 則使用預設
            **kwargs: 額外參數
            
        Returns:
            串流轉譯結果
            
        Raises:
            ProviderError: 如果轉譯失敗
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ProviderError(
                f"Provider '{provider_name or self.default_provider}' 不存在"
            )
        
        async for result in provider.transcribe_stream(audio_stream, **kwargs):
            yield result
    
    async def warmup_providers(self):
        """預熱所有 Providers"""
        self.logger.info("開始預熱所有 Providers...")
        
        for name, provider in self.providers.items():
            try:
                await provider.warmup()
                self.logger.debug(f"Provider '{name}' 預熱完成")
            except Exception as e:
                self.logger.warning(f"Provider '{name}' 預熱失敗：{e}")
    
    async def cleanup(self):
        """清理所有資源"""
        self.logger.info("清理 Provider Manager...")
        
        # 停止所有 Providers
        for name, provider in list(self.providers.items()):
            try:
                await provider.cleanup()
                self.logger.debug(f"Provider '{name}' 已停止")
            except Exception as e:
                self.logger.error(f"停止 Provider '{name}' 時發生錯誤：{e}")
        
        self.providers.clear()
        self._initialized = False
        self.logger.info("Provider Manager 清理完成")
    
    def get_status(self) -> Dict[str, Any]:
        """
        獲取 Provider Manager 狀態
        
        Returns:
            狀態資訊
        """
        return {
            "initialized": self._initialized,
            "provider_count": len(self.providers),
            "default_provider": self.default_provider,
            "providers": {
                name: provider.get_provider_info()
                for name, provider in self.providers.items()
            },
            "registered_types": self.get_registered_providers()
        }
    
    def set_default_provider(self, name: str):
        """
        設定預設 Provider
        
        Args:
            name: Provider 名稱
            
        Raises:
            ProviderError: 如果 Provider 不存在
        """
        if name not in self.providers:
            raise ProviderError(f"Provider '{name}' 不存在")
        
        self.default_provider = name
        self.logger.info(f"預設 Provider 設定為：{name}")
    
    async def reload_provider(self, name: str):
        """
        重新載入 Provider
        
        Args:
            name: Provider 名稱
        """
        if name not in self.providers:
            raise ProviderError(f"Provider '{name}' 不存在")
        
        self.logger.info(f"重新載入 Provider '{name}'...")
        
        # 獲取現有 provider
        provider = self.providers[name]
        
        # 清理舊的實例
        await provider.cleanup()
        
        # 重新建立
        provider_type = None
        for ptype, pclass in self.provider_registry.items():
            if isinstance(provider, pclass):
                provider_type = ptype
                break
        
        if provider_type:
            await self._create_provider(name)
            self.logger.success(f"Provider '{name}' 重新載入完成")
        else:
            self.logger.error(f"無法確定 Provider '{name}' 的類型")