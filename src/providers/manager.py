"""
ASR Hub Provider Manager
管理多個 ASR Provider 的建立、配置和執行
"""

from typing import Dict, Any, List, Optional, Type
from src.utils.logger import get_logger
from src.core.exceptions import ProviderError, ConfigurationError
from src.providers.base import ProviderBase
from src.providers.whisper.provider import WhisperProvider
from src.providers.provider_pool import ProviderPool
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
        
        # Provider 池快取
        self.provider_pools: Dict[str, ProviderPool] = {}
        
        # 池化啟用狀態
        self.pool_enabled: Dict[str, bool] = {}
        
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
        
        # 驗證是否有可用的 Provider
        if not self.providers and not self.provider_pools:
            raise ConfigurationError("沒有可用的 ASR Provider")
        
        # 驗證預設 Provider
        if self.default_provider not in self.providers and self.default_provider not in self.provider_pools:
            # 尋找可用的 Provider（單例或池化）
            available_singles = list(self.providers.keys())
            available_pools = list(self.provider_pools.keys())
            available = available_singles + available_pools
            
            if available:
                self.default_provider = available[0]
                self.logger.warning(
                    f"預設 Provider '{self.config_manager.providers.default}' 不可用，"
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
            # 檢查是否啟用池化（如果配置中有 pool 設定）
            pool_config = getattr(self.config_manager.providers.whisper, 'pool', None)
            if pool_config and getattr(pool_config, 'enabled', False):
                await self._create_provider_pool("whisper", pool_config)
            else:
                await self._create_provider("whisper")
        
        # TODO: 初始化其他 providers (FunASR, Vosk, Azure, etc.)
    
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
    
    async def _create_provider_pool(self, name: str, pool_config: Any):
        """
        建立並初始化 Provider Pool
        
        Args:
            name: Provider 名稱
            pool_config: 池化配置
        """
        if name not in self.provider_registry:
            self.logger.error(f"未知的 Provider 類型：{name}")
            return
        
        try:
            # 獲取池化配置參數
            min_size = getattr(pool_config, 'min_size', 1)
            max_size = getattr(pool_config, 'max_size', 5)
            acquire_timeout = getattr(pool_config, 'acquire_timeout', 30.0)
            idle_timeout = getattr(pool_config, 'idle_timeout', 300.0)
            health_check_interval = getattr(pool_config, 'health_check_interval', 60.0)
            
            # 建立 Provider Pool
            provider_class = self.provider_registry[name]
            pool = ProviderPool(
                provider_class=provider_class,
                provider_type=name,
                min_size=min_size,
                max_size=max_size,
                acquire_timeout=acquire_timeout,
                idle_timeout=idle_timeout,
                health_check_interval=health_check_interval
            )
            
            # 初始化池
            await pool.initialize()
            
            # 儲存到快取
            self.provider_pools[name] = pool
            self.pool_enabled[name] = True
            
            self.logger.info(
                f"Provider Pool '{name}' 初始化成功",
                extra={
                    "min_size": min_size,
                    "max_size": max_size,
                    "current_size": pool.stats.current_size
                }
            )
            
        except Exception as e:
            self.logger.error(f"初始化 Provider Pool '{name}' 失敗：{e}")
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
        
        # 如果使用池化，返回 None（需要使用 acquire 方法）
        if name in self.pool_enabled and self.pool_enabled[name]:
            return None
        
        return self.providers.get(name)
    
    async def remove_provider(self, name: str):
        """
        移除指定的 Provider
        
        Args:
            name: Provider 名稱
        """
        if name == self.default_provider:
            raise ProviderError("不能移除預設 Provider")
        
        # 移除池
        if name in self.provider_pools:
            pool = self.provider_pools[name]
            await pool.cleanup()
            del self.provider_pools[name]
            del self.pool_enabled[name]
            self.logger.info(f"Provider Pool '{name}' 已移除")
        
        # 移除單例
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
        # 合併單例和池化的 providers
        all_providers = set(self.providers.keys()) | set(self.provider_pools.keys())
        return list(all_providers)
    
    def get_provider_info(self, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        獲取 Provider 資訊
        
        Args:
            name: Provider 名稱，如果為 None 則返回預設 Provider 資訊
            
        Returns:
            Provider 資訊，如果不存在則返回 None
        """
        if name is None:
            name = self.default_provider
        
        # 檢查是否為池化 provider
        if name in self.provider_pools:
            pool = self.provider_pools[name]
            return {
                "name": name,
                "type": "pooled",
                "pool_size": pool.stats.current_size,
                "max_size": pool.max_size,
                "in_use": pool.stats.in_use_count,
                "statistics": pool.get_statistics()
            }
        
        # 檢查單例 provider
        provider = self.providers.get(name)
        if provider:
            info = provider.get_provider_info()
            info["type"] = "singleton"
            return info
        
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
        if provider_name is None:
            provider_name = self.default_provider
        
        # 檢查是否使用池化
        if provider_name in self.pool_enabled and self.pool_enabled[provider_name]:
            pool = self.provider_pools.get(provider_name)
            if not pool:
                raise ProviderError(f"Provider Pool '{provider_name}' 不存在")
            
            # 使用池化模式
            async with pool.acquire() as provider:
                return await provider.transcribe(audio_data, **kwargs)
        else:
            # 使用單例模式
            provider = self.providers.get(provider_name)
            if not provider:
                raise ProviderError(f"Provider '{provider_name}' 不存在")
            
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
        if provider_name is None:
            provider_name = self.default_provider
        
        # 檢查是否使用池化
        if provider_name in self.pool_enabled and self.pool_enabled[provider_name]:
            pool = self.provider_pools.get(provider_name)
            if not pool:
                raise ProviderError(f"Provider Pool '{provider_name}' 不存在")
            
            # 使用池化模式
            async with pool.acquire() as provider:
                async for result in provider.transcribe_stream(audio_stream, **kwargs):
                    yield result
        else:
            # 使用單例模式
            provider = self.providers.get(provider_name)
            if not provider:
                raise ProviderError(f"Provider '{provider_name}' 不存在")
            
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
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        獲取所有池的狀態資訊
        
        Returns:
            包含所有池狀態的字典
        """
        status = {}
        
        for provider_type, pool in self.provider_pools.items():
            if self.pool_enabled.get(provider_type, False):
                pool_status = {
                    "enabled": True,
                    "current_size": pool.stats.current_size,
                    "in_use": pool.stats.in_use_count,
                    "available": pool.stats.idle_count,
                    "utilization": pool.stats.utilization_rate,
                    "total_requests": pool.stats.total_requests,
                    "success_rate": pool.stats.success_rate,
                    "avg_wait_time": pool.stats.avg_wait_time
                }
            else:
                pool_status = {
                    "enabled": False,
                    "note": "使用單例模式"
                }
            
            status[provider_type] = pool_status
        
        return status
    
    def log_pool_metrics(self):
        """
        使用 pretty-loguru 記錄所有池的指標
        """
        # 創建樹狀結構顯示所有 Provider
        tree = Tree("🔧 ASR Provider Manager Status")
        
        # 添加每個 Provider 的狀態
        for provider_type in self.provider_registry.keys():
            # 檢查是否啟用
            provider_config = getattr(self.config_manager.providers, provider_type, None)
            if not provider_config or not provider_config.enabled:
                continue
            
            # 創建 Provider 節點
            if self.pool_enabled.get(provider_type, False):
                pool = self.provider_pools.get(provider_type)
                if pool:
                    status_emoji = "🟢" if pool.stats.utilization_rate < 0.8 else "🟡" if pool.stats.utilization_rate < 0.9 else "🔴"
                    provider_node = tree.add(f"{status_emoji} {provider_type.upper()} (Pooled)")
                    provider_node.add(f"Pool Size: {pool.stats.current_size}/{pool.max_size}")
                    provider_node.add(f"In Use: {pool.stats.in_use_count}")
                    provider_node.add(f"Available: {pool.stats.idle_count}")
                    provider_node.add(f"Utilization: {pool.stats.utilization_rate:.2%}")
                    provider_node.add(f"Success Rate: {pool.stats.success_rate:.2%}")
            else:
                provider_node = tree.add(f"🔵 {provider_type.upper()} (Singleton)")
                provider_node.add("Using single instance mode")
        
        # 顯示樹狀結構 - 使用 info 輸出
        from rich.console import Console
        from io import StringIO
        
        console = Console(file=StringIO(), force_terminal=True)
        console.print(tree)
        tree_output = console.file.getvalue()
        
        self.logger.info(f"Provider Status:\n{tree_output}")
        
        # 創建總覽表格
        table = Table(title="Provider Pool Summary")
        table.add_column("Provider", style="cyan")
        table.add_column("Mode", style="yellow")
        table.add_column("Size", style="green")
        table.add_column("Utilization", style="magenta")
        table.add_column("Requests", style="blue")
        table.add_column("Success Rate", style="green")
        
        for provider_type, pool in self.provider_pools.items():
            if self.pool_enabled.get(provider_type, False):
                table.add_row(
                    provider_type.upper(),
                    "Pooled",
                    f"{pool.stats.current_size}/{pool.max_size}",
                    f"{pool.stats.utilization_rate:.2%}",
                    str(pool.stats.total_requests),
                    f"{pool.stats.success_rate:.2%}"
                )
            else:
                table.add_row(
                    provider_type.upper(),
                    "Singleton",
                    "1/1",
                    "N/A",
                    "N/A",
                    "N/A"
                )
        
        # 顯示表格 - 使用上面已經導入的 Console
        console.file = StringIO()
        console.print(table)
        table_output = console.file.getvalue()
        
        self.logger.info(f"Pool Summary:\n{table_output}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        執行所有 Provider 池的健康檢查
        
        Returns:
            健康檢查結果
        """
        results = {
            "overall_status": "healthy",
            "providers": {},
            "issues": []
        }
        
        for provider_type, pool in self.provider_pools.items():
            if self.pool_enabled.get(provider_type, False):
                try:
                    health_info = await pool.health_check()
                    results["providers"][provider_type] = health_info
                    
                    # 更新整體狀態
                    if health_info["status"] == "critical":
                        results["overall_status"] = "critical"
                    elif health_info["status"] == "warning" and results["overall_status"] != "critical":
                        results["overall_status"] = "warning"
                    elif health_info["status"] == "degraded" and results["overall_status"] == "healthy":
                        results["overall_status"] = "degraded"
                    
                    # 收集問題
                    if health_info["issues"]:
                        results["issues"].extend([
                            f"{provider_type}: {issue}" 
                            for issue in health_info["issues"]
                        ])
                        
                except Exception as e:
                    self.logger.error(f"健康檢查失敗 ({provider_type}): {e}")
                    results["providers"][provider_type] = {
                        "status": "error",
                        "error": str(e)
                    }
                    results["overall_status"] = "critical"
            else:
                # 單例模式的簡單檢查
                provider = self.providers.get(provider_type)
                if provider:
                    results["providers"][provider_type] = {
                        "status": "healthy",
                        "mode": "singleton"
                    }
        
        return results
    
    async def cleanup(self):
        """清理所有資源"""
        self.logger.info("清理 Provider Manager...")
        
        # 停止所有 Provider Pools
        for name, pool in list(self.provider_pools.items()):
            try:
                await pool.cleanup()
                self.logger.debug(f"Provider Pool '{name}' 已停止")
            except Exception as e:
                self.logger.error(f"停止 Provider Pool '{name}' 時發生錯誤：{e}")
        
        # 停止所有單例 Providers
        for name, provider in list(self.providers.items()):
            try:
                await provider.cleanup()
                self.logger.debug(f"Provider '{name}' 已停止")
            except Exception as e:
                self.logger.error(f"停止 Provider '{name}' 時發生錯誤：{e}")
        
        self.provider_pools.clear()
        self.providers.clear()
        self.pool_enabled.clear()
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
            "pool_count": len(self.provider_pools),
            "default_provider": self.default_provider,
            "providers": {
                name: provider.get_provider_info()
                for name, provider in self.providers.items()
            },
            "pools": {
                name: {
                    "enabled": True,
                    "statistics": pool.get_statistics(),
                    "health": None  # health_check 是異步方法，需要通過 get_pool_status 獲取
                }
                for name, pool in self.provider_pools.items()
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
    
    async def get_pool_status(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        獲取池狀態資訊
        
        Args:
            name: Provider 名稱，如果為 None 則返回所有池的狀態
            
        Returns:
            池狀態資訊
        """
        if name:
            # 獲取特定池的狀態
            if name in self.provider_pools:
                pool = self.provider_pools[name]
                return {
                    "name": name,
                    "enabled": True,
                    "statistics": pool.get_statistics(),
                    "health": await pool.health_check()
                }
            else:
                return {
                    "name": name,
                    "enabled": False,
                    "message": f"Provider '{name}' 未使用池化"
                }
        else:
            # 獲取所有池的狀態
            pool_status = {}
            for pool_name, pool in self.provider_pools.items():
                pool_status[pool_name] = {
                    "enabled": True,
                    "statistics": pool.get_statistics(),
                    "health": await pool.health_check()
                }
            return pool_status
    
    def log_pool_metrics(self):
        """記錄所有池的指標"""
        if not self.provider_pools:
            self.logger.info("沒有啟用的 Provider 池")
            return
        
        self.logger.info("===== Provider Pool Metrics =====")
        
        for name, pool in self.provider_pools.items():
            # 獲取統計資訊
            stats = pool.get_statistics()
            
            # 記錄池指標
            self.logger.info(
                f"{name} Pool",
                extra={
                    "size": f"{stats['current_size']}/{pool.max_size}",
                    "in_use": stats['in_use_count'],
                    "utilization": f"{stats['utilization_rate']:.2%}",
                    "requests": stats['total_requests'],
                    "success_rate": f"{stats['successful_requests'] / max(stats['total_requests'], 1):.2%}"
                }
            )
            
            # 詳細指標
            pool.log_metrics()
    
    async def scale_pool(self, name: str, new_size: int):
        """
        動態調整池大小
        
        Args:
            name: Provider 名稱
            new_size: 新的池大小
            
        Raises:
            ProviderError: 如果 Provider 不存在或未使用池化
        """
        if name not in self.provider_pools:
            raise ProviderError(f"Provider '{name}' 未使用池化")
        
        pool = self.provider_pools[name]
        await pool.scale(new_size)
        
        self.logger.info(f"Provider Pool '{name}' 已調整大小至 {new_size}")
    
    def is_pool_enabled(self, name: str) -> bool:
        """
        檢查 Provider 是否啟用池化
        
        Args:
            name: Provider 名稱
            
        Returns:
            是否啟用池化
        """
        return self.pool_enabled.get(name, False)