"""
ASR Hub Provider Pool
提供 Provider 實例池化管理，解決並發處理瓶頸
"""

import asyncio
import time
from typing import Dict, Any, Optional, Type, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.providers.base import ProviderBase
from src.core.exceptions import ProviderError, ResourceError
from rich.table import Table
from rich.tree import Tree


config_manager = ConfigManager()
pool_config = config_manager.providers.pool_config


@dataclass
class PoolStatistics:
    """池統計資訊"""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_wait_time: float = 0.0
    max_wait_time: float = 0.0
    current_size: int = 0
    in_use_count: int = 0
    idle_count: int = 0
    created_count: int = 0
    destroyed_count: int = 0
    last_scale_time: Optional[datetime] = None

    @property
    def average_wait_time(self) -> float:
        """計算平均等待時間"""
        if self.total_requests == 0:
            return 0.0
        return self.total_wait_time / self.total_requests

    @property
    def utilization_rate(self) -> float:
        """計算使用率"""
        if self.current_size == 0:
            return 0.0
        return self.in_use_count / self.current_size

    @property
    def success_rate(self) -> float:
        """計算成功率"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "average_wait_time": self.average_wait_time,
            "max_wait_time": self.max_wait_time,
            "current_size": self.current_size,
            "in_use_count": self.in_use_count,
            "idle_count": self.idle_count,
            "utilization_rate": self.utilization_rate,
            "created_count": self.created_count,
            "destroyed_count": self.destroyed_count,
            "last_scale_time": self.last_scale_time.isoformat() if self.last_scale_time else None,
        }


@dataclass(frozen=False, eq=False)
class ProviderWrapper:
    """Provider 包裝器，追蹤實例狀態"""

    provider: ProviderBase
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    is_healthy: bool = True
    error_count: int = 0
    last_error: Optional[str] = None

    def __hash__(self):
        """使用 id 來計算 hash，讓物件可以放入 set"""
        return hash(id(self))

    def __eq__(self, other):
        """使用 id 來比較相等性"""
        return id(self) == id(other)

    def mark_used(self):
        """標記為已使用"""
        self.last_used_at = datetime.now()
        self.use_count += 1

    def mark_error(self, error: str):
        """標記錯誤"""
        self.error_count += 1
        self.last_error = error
        if self.error_count >= 3:  # 連續3次錯誤則標記為不健康
            self.is_healthy = False

    def reset_error(self):
        """重置錯誤計數"""
        self.error_count = 0
        self.last_error = None
        self.is_healthy = True


class ProviderPool:
    """
    Provider 池實現
    管理多個 Provider 實例，提供高效的並發處理能力
    """

    def __init__(
        self,
        provider_class: Type[ProviderBase],
        provider_type: str,
        min_size: int = None,
        max_size: int = None,
        acquire_timeout: float = None,
        idle_timeout: float = None,
        health_check_interval: float = None,
    ):
        """
        初始化 Provider Pool

        Args:
            provider_class: Provider 類別
            provider_type: Provider 類型名稱
            min_size: 最小池大小
            max_size: 最大池大小
            acquire_timeout: 獲取 Provider 的超時時間（秒）
            idle_timeout: 空閒 Provider 的超時時間（秒）
            health_check_interval: 健康檢查間隔（秒）
        """
        # 基本屬性
        self.provider_class = provider_class
        self.provider_type = provider_type
        # 用 getattr 安全取值
        self.min_size = min_size or getattr(pool_config, "min_size")
        self.max_size = max_size or getattr(pool_config, "max_size")
        self.acquire_timeout = acquire_timeout or getattr(pool_config, "acquire_timeout")
        self.idle_timeout = idle_timeout or getattr(pool_config, "idle_timeout")
        self.health_check_interval = health_check_interval or getattr(
            pool_config, "health_check_interval"
        )

        # 池管理
        self._available: asyncio.Queue[ProviderWrapper] = asyncio.Queue()
        self._in_use: Set[ProviderWrapper] = set()
        self._all_providers: Set[ProviderWrapper] = set()

        # 統計資訊
        self.stats = PoolStatistics()

        # 同步控制
        self._lock = asyncio.Lock()
        self._initialized = False
        self._closing = False

        # 背景任務
        self._health_check_task: Optional[asyncio.Task] = None
        self._scale_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """初始化池"""
        if self._initialized:
            logger.warning(f"{self.provider_type} 池已經初始化")
            return

        logger.info(f"初始化 {self.provider_type} 池...")

        try:
            # 創建最小數量的 Provider
            await self._ensure_min_size()

            # 啟動背景任務
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            self._scale_task = asyncio.create_task(self._auto_scale_loop())

            self._initialized = True

            # 記錄初始化資訊
            logger.success(
                f"{self.provider_type} 池初始化完成",
                extra={
                    "min_size": self.min_size,
                    "max_size": self.max_size,
                    "current_size": self.stats.current_size,
                },
            )

            # 顯示池狀態
            logger.info(
                f"{self.provider_type} Pool Status - "
                f"Size: {self.stats.current_size}/{self.max_size}, "
                f"Available: {self._available.qsize()}, "
                f"In Use: {len(self._in_use)}"
            )

        except Exception as e:
            logger.error(f"初始化池失敗：{e}")
            await self.cleanup()
            raise ResourceError(f"無法初始化 {self.provider_type} 池：{str(e)}")

    async def _ensure_min_size(self):
        """確保池中有最小數量的 Provider"""
        async with self._lock:
            while self.stats.current_size < self.min_size:
                wrapper = await self._create_provider()
                if wrapper:
                    await self._available.put(wrapper)

    async def _create_provider(self) -> Optional[ProviderWrapper]:
        """創建新的 Provider 實例"""
        try:
            # 創建 Provider 實例
            provider = self.provider_class()
            await provider.initialize()

            # 預熱
            await provider.warmup()

            # 包裝並加入池
            wrapper = ProviderWrapper(provider=provider)
            self._all_providers.add(wrapper)

            # 更新統計
            self.stats.current_size += 1
            self.stats.created_count += 1

            logger.debug(
                f"創建新的 {self.provider_type} 實例 (當前大小: {self.stats.current_size})"
            )

            return wrapper

        except Exception as e:
            logger.error(f"創建 Provider 失敗：{e}")
            return None

    async def _destroy_provider(self, wrapper: ProviderWrapper):
        """銷毀 Provider 實例"""
        try:
            await wrapper.provider.cleanup()
            self._all_providers.discard(wrapper)

            # 更新統計
            self.stats.current_size -= 1
            self.stats.destroyed_count += 1

            logger.debug(f"銷毀 {self.provider_type} 實例 (當前大小: {self.stats.current_size})")

        except Exception as e:
            logger.error(f"銷毀 Provider 失敗：{e}")

    @asynccontextmanager
    async def acquire(self):
        """
        獲取可用的 Provider 實例
        使用 async context manager 模式確保自動釋放

        Usage:
            async with pool.acquire() as provider:
                result = await provider.transcribe(audio_data)
        """
        start_time = time.time()
        wrapper = None

        try:
            # 更新請求統計
            self.stats.total_requests += 1

            # 嘗試獲取可用的 Provider
            try:
                wrapper = await asyncio.wait_for(
                    self._acquire_provider(), timeout=self.acquire_timeout
                )
            except asyncio.TimeoutError:
                self.stats.failed_requests += 1
                raise TimeoutError(f"獲取 {self.provider_type} 超時 ({self.acquire_timeout}秒)")

            # 記錄等待時間
            wait_time = time.time() - start_time
            self.stats.total_wait_time += wait_time
            self.stats.max_wait_time = max(self.stats.max_wait_time, wait_time)

            # 標記為使用中
            wrapper.mark_used()
            self._in_use.add(wrapper)
            self.stats.in_use_count = len(self._in_use)
            self.stats.idle_count = self._available.qsize()

            logger.trace(
                f"獲取 {self.provider_type} 實例",
                extra={"wait_time": wait_time, "in_use": self.stats.in_use_count},
            )

            # 返回 Provider 實例
            yield wrapper.provider

            # 成功完成
            self.stats.successful_requests += 1
            wrapper.reset_error()  # 重置錯誤計數

        except Exception as e:
            self.stats.failed_requests += 1
            if wrapper:
                wrapper.mark_error(str(e))
            raise

        finally:
            # 釋放 Provider
            if wrapper:
                await self.release(wrapper)

    async def _acquire_provider(self) -> ProviderWrapper:
        """內部方法：獲取可用的 Provider"""
        while not self._closing:
            # 嘗試從隊列獲取
            try:
                wrapper = self._available.get_nowait()

                # 檢查健康狀態
                if wrapper.is_healthy:
                    return wrapper
                else:
                    # 不健康的實例直接銷毀
                    await self._destroy_provider(wrapper)

            except asyncio.QueueEmpty:
                # 隊列為空，嘗試創建新實例
                async with self._lock:
                    if self.stats.current_size < self.max_size:
                        wrapper = await self._create_provider()
                        if wrapper:
                            return wrapper

                # 無法創建新實例，等待可用
                await asyncio.sleep(0.1)

        raise ResourceError(f"{self.provider_type} 池正在關閉")

    async def release(self, wrapper: ProviderWrapper):
        """
        釋放 Provider 實例（內部使用）

        Args:
            wrapper: Provider 包裝器
        """
        try:
            # 從使用中集合移除
            self._in_use.discard(wrapper)
            self.stats.in_use_count = len(self._in_use)

            # 檢查健康狀態
            if wrapper.is_healthy and not self._closing:
                # 放回可用隊列
                await self._available.put(wrapper)
                self.stats.idle_count = self._available.qsize()

                logger.trace(
                    f"釋放 {self.provider_type} 實例",
                    extra={"in_use": self.stats.in_use_count, "available": self.stats.idle_count},
                )
            else:
                # 不健康或正在關閉，銷毀實例
                await self._destroy_provider(wrapper)

        except Exception as e:
            logger.error(f"釋放 Provider 失敗：{e}")

    async def health_check(self) -> Dict[str, Any]:
        """
        執行健康檢查

        Returns:
            健康檢查結果
        """
        health_info = {
            "status": "healthy",
            "pool_size": self.stats.current_size,
            "in_use": self.stats.in_use_count,
            "available": self.stats.idle_count,
            "utilization": f"{self.stats.utilization_rate:.2%}",
            "healthy_providers": 0,
            "unhealthy_providers": 0,
            "issues": [],
        }

        # 檢查池大小
        if self.stats.current_size < self.min_size:
            health_info["issues"].append(
                f"池大小低於最小值 ({self.stats.current_size} < {self.min_size})"
            )

        # 檢查使用率
        if self.stats.utilization_rate > 0.9:
            health_info["issues"].append(f"高使用率警告 ({self.stats.utilization_rate:.2%})")

        # 檢查各個 Provider 健康狀態
        for wrapper in self._all_providers:
            if wrapper.is_healthy:
                health_info["healthy_providers"] += 1
            else:
                health_info["unhealthy_providers"] += 1

        # 判斷整體健康狀態
        if health_info["unhealthy_providers"] > 0:
            health_info["status"] = "degraded"
        if len(health_info["issues"]) > 0:
            health_info["status"] = "warning"
        if self.stats.current_size == 0:
            health_info["status"] = "critical"

        return health_info

    def get_pool_status_table(self) -> Table:
        """
        獲取池狀態的 Rich 表格

        Returns:
            Rich Table 對象
        """
        table = Table(title=f"{self.provider_type} Provider Pool Status")

        # 添加列
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        table.add_column("Status", style="green")

        # 添加行
        table.add_row(
            "Pool Size",
            f"{self.stats.current_size}/{self.max_size}",
            "✓" if self.stats.current_size >= self.min_size else "⚠",
        )
        table.add_row("In Use", str(self.stats.in_use_count), "✓")
        table.add_row("Available", str(self.stats.idle_count), "✓")
        table.add_row(
            "Utilization",
            f"{self.stats.utilization_rate:.2%}",
            "✓" if self.stats.utilization_rate < 0.9 else "⚠",
        )
        table.add_row("Total Requests", str(self.stats.total_requests), "✓")
        table.add_row(
            "Success Rate",
            f"{self.stats.success_rate:.2%}",
            "✓" if self.stats.success_rate > 0.95 else "⚠",
        )
        table.add_row(
            "Avg Wait Time",
            f"{self.stats.average_wait_time:.3f}s",
            "✓" if self.stats.average_wait_time < 1.0 else "⚠",
        )

        return table

    def log_pool_metrics(self):
        """
        使用 pretty-loguru 記錄池指標
        """
        # 創建狀態表格
        table = self.get_pool_status_table()

        # 使用 block 顯示整體狀態
        status_text = f"""
        Provider Type: {self.provider_type}
        Current Size: {self.stats.current_size}
        Utilization: {self.stats.utilization_rate:.2%}
        Success Rate: {self.stats.success_rate:.2%}
        """

        # 使用基本的 info 日誌替代 block
        logger.info(f"{self.provider_type} Pool Metrics:\n{status_text}")

        # 顯示表格 - 使用 info 輸出表格內容
        from rich.console import Console
        from io import StringIO

        # 使用 StringIO 捕獲表格輸出
        console = Console(file=StringIO(), force_terminal=True)
        console.print(table)
        table_output = console.file.getvalue()

        logger.info(f"Pool Status Table:\n{table_output}")

    async def _active_health_check(self):
        """
        主動健康檢查：定期測試空閒的 Provider
        """
        # 準備測試音訊（使用簡單的靜音數據）
        test_audio_data = b"\x00" * 16000  # 1秒的靜音，16kHz

        # 收集需要檢查的 Provider
        providers_to_check = []
        temp_queue = []

        # 只檢查前幾個空閒的 Provider（避免影響性能）
        max_check_count = min(3, self._available.qsize())
        checked_count = 0

        while checked_count < max_check_count and not self._available.empty():
            try:
                wrapper = self._available.get_nowait()
                providers_to_check.append(wrapper)
                checked_count += 1
            except asyncio.QueueEmpty:
                break

        # 檢查每個 Provider
        for wrapper in providers_to_check:
            try:
                # 執行簡單的健康檢查
                provider = wrapper.provider

                # 檢查是否有 transcribe 方法
                if hasattr(provider, "transcribe"):
                    # 嘗試處理測試音訊（設置短超時）
                    try:
                        await asyncio.wait_for(provider.transcribe(test_audio_data), timeout=5.0)
                        # 成功，重置錯誤計數
                        wrapper.reset_error()
                        logger.trace(f"{self.provider_type} Provider 健康檢查通過")
                    except asyncio.TimeoutError:
                        wrapper.mark_error("Health check timeout")
                        logger.warning(f"{self.provider_type} Provider 健康檢查超時")
                    except Exception as e:
                        wrapper.mark_error(f"Health check failed: {e}")
                        logger.warning(f"{self.provider_type} Provider 健康檢查失敗：{e}")

                # 如果 Provider 不健康，不放回隊列
                if wrapper.is_healthy:
                    temp_queue.append(wrapper)
                else:
                    # 銷毀不健康的 Provider
                    await self._destroy_provider(wrapper)
                    logger.info(f"移除不健康的 {self.provider_type} Provider")

                    # 嘗試創建替代實例
                    if self.stats.current_size < self.min_size:
                        new_wrapper = await self._create_provider()
                        if new_wrapper:
                            temp_queue.append(new_wrapper)

            except Exception as e:
                logger.error(f"主動健康檢查失敗：{e}")
                temp_queue.append(wrapper)  # 出錯時仍放回隊列

        # 放回所有檢查過的健康 Provider
        for wrapper in temp_queue:
            await self._available.put(wrapper)

    async def _health_check_loop(self):
        """背景健康檢查循環"""
        while not self._closing:
            try:
                await asyncio.sleep(self.health_check_interval)

                # 執行健康檢查
                health_info = await self.health_check()

                # 記錄健康狀態
                if health_info["status"] != "healthy":
                    logger.warning(f"{self.provider_type} 池健康檢查", extra=health_info)
                else:
                    # 定期輸出池狀態（每5次檢查輸出一次）
                    if not hasattr(self, "_health_check_count"):
                        self._health_check_count = 0
                    self._health_check_count += 1

                    if self._health_check_count % 5 == 0:
                        self.log_pool_metrics()

                # 執行主動健康檢查（檢查空閒的 Provider）
                await self._active_health_check()

                # 清理過期的空閒 Provider
                await self._cleanup_idle_providers()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康檢查失敗：{e}")

    async def _cleanup_idle_providers(self):
        """清理過期的空閒 Provider"""
        now = datetime.now()
        idle_timeout_delta = timedelta(seconds=self.idle_timeout)

        # 收集需要清理的 Provider
        to_cleanup = []
        temp_queue = []

        # 檢查隊列中的所有 Provider
        while not self._available.empty():
            try:
                wrapper = self._available.get_nowait()

                # 檢查是否過期
                if (
                    wrapper.last_used_at
                    and now - wrapper.last_used_at > idle_timeout_delta
                    and self.stats.current_size > self.min_size
                ):
                    to_cleanup.append(wrapper)
                else:
                    temp_queue.append(wrapper)

            except asyncio.QueueEmpty:
                break

        # 放回未過期的 Provider
        for wrapper in temp_queue:
            await self._available.put(wrapper)

        # 清理過期的 Provider
        for wrapper in to_cleanup:
            await self._destroy_provider(wrapper)
            logger.debug(f"清理過期的 {self.provider_type} 實例")

    async def scale(self, new_size: int):
        """
        動態調整池大小

        Args:
            new_size: 新的池大小
        """
        if new_size < self.min_size or new_size > self.max_size:
            raise ValueError(f"新大小必須在 {self.min_size} 和 {self.max_size} 之間")

        async with self._lock:
            current_size = self.stats.current_size

            if new_size > current_size:
                # 擴展池
                logger.info(f"擴展 {self.provider_type} 池: {current_size} -> {new_size}")

                for _ in range(new_size - current_size):
                    wrapper = await self._create_provider()
                    if wrapper:
                        await self._available.put(wrapper)

            elif new_size < current_size:
                # 縮減池
                logger.info(f"縮減 {self.provider_type} 池: {current_size} -> {new_size}")

                # 首先嘗試從可用隊列移除
                to_remove = current_size - new_size
                removed = 0

                while removed < to_remove and not self._available.empty():
                    try:
                        wrapper = self._available.get_nowait()
                        await self._destroy_provider(wrapper)
                        removed += 1
                    except asyncio.QueueEmpty:
                        break

                # 如果還需要移除更多，標記一些使用中的實例在釋放時銷毀
                # （這裡簡化處理，實際可能需要更複雜的邏輯）

            self.stats.last_scale_time = datetime.now()

    async def _auto_scale_loop(self):
        """自動縮放循環"""
        while not self._closing:
            try:
                await asyncio.sleep(60)  # 每分鐘檢查一次

                # 根據使用率自動調整
                utilization = self.stats.utilization_rate
                current_size = self.stats.current_size

                if utilization > 0.8 and current_size < self.max_size:
                    # 高使用率，擴展池
                    new_size = min(current_size + 1, self.max_size)
                    await self.scale(new_size)

                elif utilization < 0.2 and current_size > self.min_size:
                    # 低使用率，縮減池
                    new_size = max(current_size - 1, self.min_size)
                    await self.scale(new_size)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自動縮放失敗：{e}")

    async def cleanup(self):
        """清理所有資源"""
        logger.info(f"清理 {self.provider_type} 池...")

        self._closing = True

        # 取消背景任務
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._scale_task:
            self._scale_task.cancel()

        # 等待所有使用中的 Provider 釋放
        wait_time = 0
        while len(self._in_use) > 0 and wait_time < 30:
            logger.info(f"等待 {len(self._in_use)} 個 Provider 釋放...")
            await asyncio.sleep(1)
            wait_time += 1

        # 清理所有 Provider
        for wrapper in list(self._all_providers):
            await self._destroy_provider(wrapper)

        self._initialized = False
        logger.success(f"{self.provider_type} 池清理完成")

    def get_statistics(self) -> Dict[str, Any]:
        """
        獲取池統計資訊

        Returns:
            統計資訊字典
        """
        return self.stats.to_dict()

    def log_metrics(self):
        """記錄池指標"""
        metrics = self.get_statistics()

        logger.info(f"{self.provider_type} Pool Metrics", extra=metrics)

        # 使用表格顯示詳細資訊
        logger.table(
            [
                ["指標", "數值"],
                ["池大小", f"{metrics['current_size']}/{self.max_size}"],
                ["使用中", metrics["in_use_count"]],
                ["可用", metrics["idle_count"]],
                ["使用率", f"{metrics['utilization_rate']:.2%}"],
                ["總請求", metrics["total_requests"]],
                [
                    "成功率",
                    f"{metrics['successful_requests'] / max(metrics['total_requests'], 1):.2%}",
                ],
                ["平均等待時間", f"{metrics['average_wait_time']:.3f}s"],
                ["最大等待時間", f"{metrics['max_wait_time']:.3f}s"],
            ],
            title=f"{self.provider_type} 池統計",
        )
