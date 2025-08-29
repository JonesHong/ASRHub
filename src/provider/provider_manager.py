"""Provider Pool Manager - ASR Provider 實例池管理器

負責管理多個 ASR Provider 實例，支援：
1. 租借機制（Lease）- 按需分配 provider 給 session
2. 老化機制 - 防止飢餓
3. 配額管理 - 防止單一 session 壟斷資源
4. 健康檢查 - 自動移除不健康的 provider

設計原則：
- KISS: 從簡單開始，逐步增加功能
- Stateless: 每個 provider 獨立運作
- Direct calls: 直接調用，避免不必要的抽象
"""

from typing import Dict, List, Optional, Any, Tuple
from threading import Lock, Event
from contextlib import contextmanager
import time
import heapq

from src.interface.asr_provider import IASRProvider
from src.interface.provider_pool_interfaces import (
    PoolError,
    PoolConfig,
    LeaseRequest as BaseLeaseRequest,
    LeaseInfo,
    ProviderHealth
)
from src.config.manager import ConfigManager
from src.utils.id_provider import new_id
from src.utils.logger import logger


# 擴展 LeaseRequest 以加入額外功能
class LeaseRequest(BaseLeaseRequest):
    """擴展的租借請求（優先佇列）"""
    def __init__(self, session_id: str, requested_at: float, timeout: float = 10.0,
                 priority: int = 5, event: Optional[Event] = None,
                 result: Optional[IASRProvider] = None,
                 error: Optional[PoolError] = None,
                 request_id: Optional[str] = None):
        super().__init__(session_id, requested_at, timeout)
        self.priority = priority
        self.timestamp = requested_at  # 為了相容性
        self.event = event or Event()
        self.result = result
        self.error = error

        self.request_id = new_id(request_id)
    
    def effective_priority(self, current_time: float, aging_factor: float) -> float:
        """計算有效優先度（含老化）"""
        age_ms = (current_time - self.requested_at) * 1000
        aging_boost = age_ms * aging_factor
        return self.priority + aging_boost
    
    def __lt__(self, other):
        """用於優先佇列比較（高優先度在前）"""
        # 注意：heapq 是最小堆，所以要反轉
        return self.priority > other.priority


class ProviderPoolManager:
    """Provider Pool 管理器（含優先佇列與租借機制）
    
    核心理念：
    1. 維護一個 provider pool，按需租借
    2. 支援優先佇列和老化機制，避免飢餓
    3. 每個 session 有配額限制，防止壟斷
    4. 支援健康檢查和錯誤恢復
    5. 提供 Context Manager 介面確保安全釋放
    
    階段 1 實作：基本 Pool + 租借機制
    階段 2 加入：優先佇列 + 老化 + 配額
    階段 3 加入：健康檢查 + 監控
    """
    
    def __init__(self):
        # 從 ConfigManager 獲取配置
        config_manager = ConfigManager()
        self.config = config_manager.provider_pool
        self._lock = Lock()
        
        # 可用的 providers
        self._available: List[IASRProvider] = []
        
        # 等待佇列（優先佇列） - 階段 2 才啟用
        self._waiting_queue: List[LeaseRequest] = []  # heapq
        
        # 已租借的 providers
        self._leased: Dict[int, LeaseInfo] = {}
        
        # session 配額追蹤
        self._session_quotas: Dict[str, int] = {}
        
        # 所有 providers（用於管理生命週期）
        self._all_providers: Dict[int, IASRProvider] = {}
        
        # Provider 健康資訊
        self._health: Dict[int, ProviderHealth] = {}
        
        # 從配置載入參數
        self._aging_enabled = self.config.aging_prevention
        self._aging_factor = self.config.aging_factor
        self._default_priority = self.config.default_priority
        self._max_wait_time = self.config.max_wait_time
        
        # 統計資訊
        self._stats = {
            'total_created': 0,
            'total_leases': 0,
            'total_releases': 0,
            'total_timeouts': 0,
            'total_errors': 0,
            'queue_wait_times': [],  # 最近100次等待時間
        }
        
        # 預創建最小數量的 providers
        self._initialize_pool()
        
        logger.info(
            f"🚀 ProviderPoolManager 初始化: "
            f"min={self.config.min_size}, max={self.config.max_size}, "
            f"type={self.config.provider_type}"
        )
    
    def _initialize_pool(self):
        """初始化 pool"""
        for i in range(self.config.min_size):
            try:
                provider = self._create_provider()
                self._available.append(provider)
                logger.debug(f"✅ 預創建 provider #{i+1}/{self.config.min_size}")
            except Exception as e:
                logger.error(f"❌ 創建 provider 失敗: {e}")
                # 繼續嘗試創建其他的
    
    def _create_provider(self) -> IASRProvider:
        """創建新的 provider
        
        階段 1: 暫時只支援 whisper，使用 import 來避免循環依賴
        階段 2: 加入工廠模式支援多種 provider
        """
        if self.config.provider_type == "whisper":
            # 延遲 import 避免循環依賴
            # 優先使用 FasterWhisperProvider（更高效）
            try:
                from src.provider.whisper.faster_whisper_provider import FasterWhisperProvider
                # 創建非單例實例（為 pool 使用）
                provider = FasterWhisperProvider(singleton=False)
                logger.debug(f"創建新的 FasterWhisperProvider 實例 (非單例模式)")
            except ImportError as e:
                logger.warning(f"無法載入 FasterWhisperProvider: {e}")
                # 回退到原始 WhisperProvider
                from src.provider.whisper.whisper_provider import WhisperProvider
                provider = WhisperProvider(singleton=False)
                logger.debug(f"創建新的 WhisperProvider 實例 (非單例模式)")
            
        else:
            raise ValueError(f"未知的 provider 類型: {self.config.provider_type}")
        
        provider_id = id(provider)
        self._all_providers[provider_id] = provider
        
        # 初始化健康資訊
        self._health[provider_id] = ProviderHealth(
            consecutive_failures=0,
            total_successes=0,
            is_healthy=True,
            last_error=None
        )
        
        self._stats['total_created'] += 1
        
        logger.debug(
            f"📦 創建 provider #{self._stats['total_created']}, "
            f"pool 大小: {len(self._all_providers)}"
        )
        return provider
    
    def lease(self, session_id: str, 
              timeout: float = 5.0) -> Tuple[Optional[IASRProvider], Optional[PoolError]]:
        """租借一個 provider（含優先佇列）
        
        Args:
            session_id: Session ID
            timeout: 等待超時（秒）
            
        Returns:
            (Provider 實例, 錯誤碼) 元組
        """
        
        # Phase 2: 含優先佇列實作
        with self._lock:
            # 檢查 session 配額
            current_count = self._session_quotas.get(session_id, 0)
            if current_count >= self.config.per_session_quota:
                logger.warning(f"⚠️ Session {session_id} 達到配額上限 ({current_count}/{self.config.per_session_quota})")
                return None, PoolError.NO_CAPACITY_FOR_SESSION
            
            # 嘗試立即獲取可用 provider
            provider = self._try_get_available(session_id)
            if provider:
                return provider, None
            
            # 如果可以創建新 provider，立即創建
            if len(self._all_providers) < self.config.max_size:
                try:
                    provider = self._create_provider()
                    self._assign_to_session(provider, session_id)
                    return provider, None
                except Exception as e:
                    logger.error(f"❌ 創建 provider 失敗: {e}")
                    self._stats['total_errors'] += 1
                    # 繼續排隊等待
            
            # 需要排隊等待
            request = LeaseRequest(
                session_id=session_id,
                priority=self._default_priority,
                requested_at=time.time(),
                timeout=timeout
            )
            
            # 加入等待佇列
            heapq.heappush(self._waiting_queue, request)
            logger.info(f"⏳ Session {session_id} 加入等待佇列 (佇列長度: {len(self._waiting_queue)})")
            
        # 等待分配（釋放鎖）
        request.event.wait(timeout=timeout)
        
        # 檢查結果
        with self._lock:
            if request.result:
                return request.result, None
            elif request.error:
                return None, request.error
            else:
                # 超時
                self._stats['total_timeouts'] += 1
                # 從佇列中移除
                if request in self._waiting_queue:
                    self._waiting_queue.remove(request)
                    heapq.heapify(self._waiting_queue)
                logger.warning(f"⏱️ Session {session_id} 租借超時 (timeout={timeout}s)")
                return None, PoolError.TIMEOUT
    
    def _try_get_available(self, session_id: str) -> Optional[IASRProvider]:
        """嘗試獲取可用 provider（需要持有鎖）"""
        # Phase 4: 只選擇健康的 provider
        healthy_providers = []
        unhealthy_providers = []
        
        while self._available:
            provider = self._available.pop(0)
            provider_id = id(provider)
            
            # 檢查健康狀態
            if provider_id in self._health and self._health[provider_id].is_healthy:
                # 找到健康的 provider
                self._assign_to_session(provider, session_id)
                # 把剩餘健康的 provider 放回佇列前端
                self._available = healthy_providers + self._available
                # 不健康的放到佇列尾端（給它們恢復的機會）
                self._available.extend(unhealthy_providers)
                return provider
            elif provider_id in self._health and not self._health[provider_id].is_healthy:
                # 不健康的 provider，暫時跳過
                unhealthy_providers.append(provider)
                logger.debug(f"⚠️ 跳過不健康的 provider {provider_id}")
            else:
                # 新 provider 或沒有健康記錄，視為健康
                healthy_providers.append(provider)
        
        # 恢復佇列（健康的在前，不健康的在後）
        self._available = healthy_providers + unhealthy_providers
        
        # 如果有健康的 provider，使用第一個
        if healthy_providers:
            provider = self._available.pop(0)
            self._assign_to_session(provider, session_id)
            return provider
        
        # 沒有健康的 provider（但有不健康的）
        if unhealthy_providers:
            logger.warning(f"⚠️ 沒有健康的 provider 可用 ({len(unhealthy_providers)} 個不健康)")
        
        return None
    
    def _pick_best_waiter(self) -> Optional[LeaseRequest]:
        """選擇最佳等待者（考慮老化）"""
        if not self._waiting_queue:
            return None
        
        current_time = time.time()
        
        # 優化：只檢查前 N 個候選者，避免 O(n) 操作
        candidates_to_check = min(10, len(self._waiting_queue))
        
        best_request = None
        best_priority = -float('inf')
        
        # 從堆頂開始檢查候選者
        for i in range(candidates_to_check):
            if i >= len(self._waiting_queue):
                break
            
            request = self._waiting_queue[i]
            
            # 計算有效優先度（含老化）
            if self._aging_enabled:
                priority = request.effective_priority(current_time, self._aging_factor)
            else:
                priority = request.priority
            
            if priority > best_priority:
                best_priority = priority
                best_request = request
        
        # 從佇列中移除選中的請求
        if best_request:
            self._waiting_queue.remove(best_request)
            heapq.heapify(self._waiting_queue)
            logger.debug(f"🎯 選中等待請求: session={best_request.session_id}, priority={best_priority:.2f}")
        
        return best_request
    
    def _assign_to_session(self, provider: IASRProvider, session_id: str):
        """分配 provider 給 session（需要持有鎖）"""
        provider_id = id(provider)
        
        # 記錄租借資訊
        self._leased[provider_id] = LeaseInfo(
            session_id=session_id,
            provider_id=provider_id,
            lease_time=time.time()
        )
        
        # 更新配額
        self._session_quotas[session_id] = self._session_quotas.get(session_id, 0) + 1
        
        # 更新統計
        self._stats['total_leases'] += 1
        
        logger.debug(
            f"✅ 租借 provider 給 session {session_id} "
            f"(quota={self._session_quotas[session_id]}/{self.config.per_session_quota})"
        )
    
    def release(self, provider: IASRProvider):
        """歸還 provider（優先佇列版）
        
        Args:
            provider: 要歸還的 provider
        """
        if provider is None:
            return
        
        provider_id = id(provider)
        
        with self._lock:
            # 從租借記錄中移除
            if provider_id not in self._leased:
                logger.warning(f"⚠️ 嘗試歸還非租借的 provider")
                return
                
            lease_info = self._leased[provider_id]
            del self._leased[provider_id]
            
            # 更新配額
            session_id = lease_info.session_id
            if session_id in self._session_quotas:
                self._session_quotas[session_id] -= 1
                if self._session_quotas[session_id] <= 0:
                    del self._session_quotas[session_id]
            
            # 更新統計
            self._stats['total_releases'] += 1
            wait_time = time.time() - lease_info.lease_time
            self._record_wait_time(wait_time)
            
            logger.debug(
                f"♻️ 歸還 provider from session {session_id} "
                f"(使用時間: {wait_time:.2f}秒)"
            )
            
            # 檢查健康狀態
            health = self._health.get(provider_id)
            if health and not health.is_healthy:
                logger.warning(f"❌ 歸還不健康的 provider，關閉中...")
                provider.shutdown()
                del self._all_providers[provider_id]
                del self._health[provider_id]
                return
            
            # 檢查是否需要保留此 provider
            current_size = len(self._all_providers)
            if current_size > self.config.min_size:
                # 如果超過最小 size，可以考慮釋放
                if len(self._available) >= self.config.min_size and not self._waiting_queue:
                    # 已經有足夠的空閒 provider，且沒有等待者，釋放這個
                    provider.shutdown()
                    del self._all_providers[provider_id]
                    del self._health[provider_id]
                    logger.info(f"🗑️ 關閉多餘的 provider, pool 大小: {len(self._all_providers)}")
                    return
            
            # 檢查等待佇列
            if self._waiting_queue:
                # 選擇最佳等待者（考慮老化）
                best_request = self._pick_best_waiter()
                if best_request:
                    # 分配給等待者
                    self._assign_to_session(provider, best_request.session_id)
                    best_request.result = provider
                    best_request.event.set()
                    logger.info(f"🎯 分配 provider 給等待中的 session {best_request.session_id}")
                    return
            
            # 沒有等待者，歸還到可用池
            self._available.append(provider)
            logger.debug(f"📥 Provider 歸還到可用池 (可用數: {len(self._available)})")
    
    def _record_wait_time(self, wait_time: float):
        """記錄等待時間（用於監控）"""
        wait_times = self._stats['queue_wait_times']
        wait_times.append(wait_time)
        # 只保留最近 100 次
        if len(wait_times) > 100:
            wait_times.pop(0)
    
    @contextmanager
    def lease_context(self, session_id: str, timeout: float = 5.0):
        """Context manager 介面，確保 provider 被正確釋放
        
        使用範例:
            with provider_manager.lease_context(session_id) as (provider, error):
                if provider:
                    result = provider.transcribe_audio(audio)
                else:
                    logger.error(f"Failed to lease: {error}")
        """
        provider, error = self.lease(session_id, timeout)
        try:
            yield provider, error
        finally:
            if provider:
                self.release(provider)
    
    def release_all(self, session_id: str):
        """釋放某個 session 的所有 provider"""
        with self._lock:
            to_release = [
                (pid, self._all_providers[pid])
                for pid, lease in self._leased.items()
                if lease.session_id == session_id
            ]
        
        for provider_id, provider in to_release:
            self.release(provider)
        
        logger.info(f"🔄 釋放 session {session_id} 的所有 provider ({len(to_release)} 個)")
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取統計資訊（增強版）"""
        with self._lock:
            # 計算平均等待時間
            wait_times = self._stats['queue_wait_times']
            avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
            
            # 健康 provider 數量
            healthy_count = sum(1 for h in self._health.values() if h.is_healthy)
            unhealthy_count = sum(1 for h in self._health.values() if not h.is_healthy)
            
            return {
                "pool": {
                    "total": len(self._all_providers),
                    "available": len(self._available),
                    "leased": len(self._leased),
                    "healthy": healthy_count,
                    "unhealthy_providers": unhealthy_count,  # Phase 4: 添加不健康計數
                    "waiting": len(self._waiting_queue)
                },
                "stats": {
                    "total_created": self._stats['total_created'],
                    "total_leases": self._stats['total_leases'],
                    "total_releases": self._stats['total_releases'],
                    "total_timeouts": self._stats['total_timeouts'],
                    "total_errors": self._stats['total_errors'],
                    "avg_wait_time": avg_wait
                },
                "quotas": dict(self._session_quotas),
                "config": {
                    "min_size": self.config.min_size,
                    "max_size": self.config.max_size,
                    "per_session_quota": self.config.per_session_quota,
                    "aging_enabled": self._aging_enabled
                }
            }
    
    # === Phase 4: 健康檢查 (MVP) ===
    
    def mark_success(self, provider: IASRProvider):
        """標記 provider 成功執行
        
        MVP 實作：重置連續失敗計數
        """
        provider_id = id(provider)
        if provider_id in self._health:
            self._health[provider_id].consecutive_failures = 0
            self._health[provider_id].total_successes += 1
            self._health[provider_id].is_healthy = True
            logger.debug(f"✅ Provider {provider_id} 標記為成功")
    
    def mark_failure(self, provider: IASRProvider, error_msg: Optional[str] = None):
        """標記 provider 執行失敗
        
        MVP 實作：
        - 增加連續失敗計數
        - 超過閾值則標記為不健康
        - 自動從可用池移除
        """
        provider_id = id(provider)
        if provider_id not in self._health:
            return
        
        health = self._health[provider_id]
        health.consecutive_failures += 1
        health.last_error = error_msg
        
        # 檢查是否超過失敗閾值
        if health.consecutive_failures >= self.config.max_consecutive_failures:
            health.is_healthy = False
            logger.warning(
                f"⚠️ Provider {provider_id} 標記為不健康 "
                f"(連續失敗 {health.consecutive_failures} 次)"
            )
            
            # 從可用池移除（如果在的話）
            with self._lock:
                if provider in self._available:
                    self._available.remove(provider)
                    logger.info(f"🔴 從可用池移除不健康的 provider {provider_id}")
        else:
            logger.debug(
                f"⚠️ Provider {provider_id} 失敗 "
                f"({health.consecutive_failures}/{self.config.max_consecutive_failures})"
            )
    
    def is_provider_healthy(self, provider: IASRProvider) -> bool:
        """檢查 provider 是否健康"""
        provider_id = id(provider)
        if provider_id in self._health:
            return self._health[provider_id].is_healthy
        return True  # 預設為健康
    
    def get_health_stats(self) -> Dict[str, Any]:
        """獲取健康統計資訊"""
        healthy_count = sum(1 for h in self._health.values() if h.is_healthy)
        unhealthy_count = len(self._health) - healthy_count
        
        return {
            "healthy_providers": healthy_count,
            "unhealthy_providers": unhealthy_count,
            "total_providers": len(self._health),
            "details": [
                {
                    "provider_id": pid,
                    "is_healthy": h.is_healthy,
                    "consecutive_failures": h.consecutive_failures,
                    "total_successes": h.total_successes,
                    "last_error": h.last_error
                }
                for pid, h in self._health.items()
            ]
        }
    
    def shutdown(self):
        """關閉 pool，釋放所有資源"""
        with self._lock:
            logger.info(f"🛑 關閉 ProviderPoolManager，釋放 {len(self._all_providers)} 個 provider...")
            
            for provider in self._all_providers.values():
                try:
                    provider.shutdown()
                except Exception as e:
                    logger.error(f"關閉 provider 時發生錯誤: {e}")
            
            self._all_providers.clear()
            self._leased.clear()
            self._available.clear()
            self._waiting_queue.clear()
            self._session_quotas.clear()
            self._health.clear()
            
        logger.info("✅ ProviderPoolManager 已關閉")


# 模組級單例 - 按需創建以避免循環依賴
# 使用時應該通過 get_provider_manager() 函數取得
_provider_manager = None

def get_provider_manager():
    """獲取 provider manager 單例"""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderPoolManager()
    return _provider_manager