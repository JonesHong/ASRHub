"""ProviderPoolManager 單元測試

測試 Provider Pool 管理器的核心功能：
1. 基本租借和歸還
2. 配額管理
3. Context Manager
4. 錯誤處理
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager

from src.provider.provider_manager import ProviderPoolManager
from src.interface.provider_pool_interfaces import (
    PoolConfig,
    PoolError,
    LeaseInfo,
    ProviderHealth
)


class TestProviderPoolManager:
    """測試 ProviderPoolManager 基本功能"""
    
    @pytest.fixture
    def mock_provider_factory(self):
        """創建 Provider 工廠，每次返回不同的 Mock"""
        def factory():
            provider = Mock()
            provider.shutdown = Mock()
            provider.transcribe_audio = Mock(return_value={"text": "test"})
            # 確保每個 mock 有不同的 id
            provider._unique_id = id(provider)
            return provider
        return factory
    
    @pytest.fixture
    def manager_config(self):
        """創建測試用的配置"""
        return PoolConfig(
            min_size=1,
            max_size=3,
            per_session_quota=2,
            max_consecutive_failures=3,
            health_check_enabled=True,
            initialization_timeout=30.0,
            lease_timeout=10.0,
            provider_type="whisper"
        )
    
    @pytest.fixture
    def manager(self, manager_config, mock_provider_factory):
        """創建測試用的 Manager，使用 mock provider"""
        # 先 patch _initialize_pool 來避免在 __init__ 時創建真實的 provider
        with patch.object(ProviderPoolManager, '_initialize_pool'):
            manager = ProviderPoolManager(manager_config)
            
            # 創建一個包裝函數來確保 provider 被正確註冊
            def create_and_register():
                provider = mock_provider_factory()
                provider_id = id(provider)
                # 這些是 _create_provider 應該做的事情
                manager._all_providers[provider_id] = provider
                manager._health[provider_id] = ProviderHealth(
                    consecutive_failures=0,
                    total_successes=0,
                    is_healthy=True,
                    last_error=None
                )
                manager._stats['total_created'] += 1
                return provider
            
            # Patch _create_provider 並保持它在整個測試期間有效
            with patch.object(manager, '_create_provider', side_effect=create_and_register):
                # 手動執行初始化 pool 的邏輯
                for i in range(manager.config.min_size):
                    provider = manager._create_provider()
                    manager._available.append(provider)
                
                # 在 patch 仍有效的情況下 yield manager
                yield manager
                manager.shutdown()
    
    def test_initialization(self, manager_config, mock_provider_factory):
        """測試 Manager 初始化"""
        # 創建一個包裝函數來確保 provider 被正確註冊
        def create_and_register():
            provider = mock_provider_factory()
            provider_id = id(provider)
            # 這些是 _create_provider 應該做的事情
            manager._all_providers[provider_id] = provider
            manager._health[provider_id] = ProviderHealth(
                consecutive_failures=0,
                total_successes=0,
                is_healthy=True,
                last_error=None
            )
            manager._stats['total_created'] += 1
            return provider
        
        # 先 patch _initialize_pool 來避免在 __init__ 時創建真實的 provider
        with patch.object(ProviderPoolManager, '_initialize_pool'):
            manager = ProviderPoolManager(manager_config)
            
            # 現在手動 patch _create_provider 並初始化 pool
            with patch.object(manager, '_create_provider', side_effect=create_and_register):
                # 手動執行初始化 pool 的邏輯
                for i in range(manager.config.min_size):
                    provider = manager._create_provider()
                    manager._available.append(provider)
            
            # 檢查初始化狀態
            assert manager.config.min_size == 1
            assert manager.config.max_size == 3
            assert len(manager._all_providers) >= manager.config.min_size
            
            # 確保統計資訊初始化
            stats = manager.get_stats()
            assert stats['pool']['total'] >= 1
            assert stats['stats']['total_created'] >= 1
            
            manager.shutdown()
    
    def test_lease_and_release(self, manager):
        """測試基本的租借和歸還"""
        session_id = "test_session_1"
        
        # 租借 provider
        provider, error = manager.lease(session_id)
        
        assert provider is not None
        assert error is None
        
        # 檢查租借狀態
        stats = manager.get_stats()
        assert stats['pool']['leased'] == 1
        assert session_id in stats['quotas']
        assert stats['quotas'][session_id] == 1
        
        # 歸還 provider
        manager.release(provider)
        
        # 檢查歸還後狀態
        stats = manager.get_stats()
        assert stats['pool']['leased'] == 0
        assert stats['pool']['available'] >= 1
    
    def test_session_quota_enforcement(self, manager):
        """測試 session 配額限制"""
        session_id = "test_session_quota"
        
        # 租借到配額上限
        providers = []
        for i in range(manager.config.per_session_quota):
            provider, error = manager.lease(session_id)
            assert provider is not None
            assert error is None
            providers.append(provider)
        
        # 嘗試超過配額
        provider, error = manager.lease(session_id)
        assert provider is None
        assert error == PoolError.NO_CAPACITY_FOR_SESSION
        
        # 歸還一個後應該可以再租借
        manager.release(providers[0])
        provider, error = manager.lease(session_id)
        assert provider is not None
        assert error is None
        
        # 清理
        for p in providers[1:]:
            manager.release(p)
        if provider:
            manager.release(provider)
    
    def test_pool_size_limit(self, mock_provider_factory):
        """測試 Pool 大小限制"""
        # 創建一個小的 pool
        small_config = PoolConfig(
            min_size=1,
            max_size=2,
            per_session_quota=3,
            max_consecutive_failures=3,
            health_check_enabled=True,
            initialization_timeout=30.0,
            lease_timeout=10.0,
            provider_type="whisper"
        )
        
        # 先 patch _initialize_pool 來避免在 __init__ 時創建真實的 provider
        with patch.object(ProviderPoolManager, '_initialize_pool'):
            manager = ProviderPoolManager(small_config)
            
            # 創建一個包裝函數來確保 provider 被正確註冊
            def create_and_register():
                provider = mock_provider_factory()
                provider_id = id(provider)
                # 這些是 _create_provider 應該做的事情
                manager._all_providers[provider_id] = provider
                manager._health[provider_id] = ProviderHealth(
                    consecutive_failures=0,
                    total_successes=0,
                    is_healthy=True,
                    last_error=None
                )
                manager._stats['total_created'] += 1
                return provider
            
            # 現在手動 patch _create_provider 並初始化 pool
            with patch.object(manager, '_create_provider', side_effect=create_and_register):
                # 手動執行初始化 pool 的邏輯
                for i in range(manager.config.min_size):
                    provider = manager._create_provider()
                    manager._available.append(provider)
                
                # 租借所有可用的
                providers = []
                for i in range(small_config.max_size):
                    provider, error = manager.lease(f"session_{i}")
                    assert provider is not None
                    providers.append(provider)
                
                # Pool 已滿，會進入等待佇列並超時
                provider, error = manager.lease("session_extra", timeout=0.1)
                assert provider is None
                assert error == PoolError.TIMEOUT  # Phase 2: 現在會等待而非立即返回 POOL_FULL
                
                # 清理
                for p in providers:
                    manager.release(p)
                manager.shutdown()
    
    def test_context_manager(self, manager):
        """測試 Context Manager 介面"""
        session_id = "test_context"
        
        # 使用 context manager
        with manager.lease_context(session_id) as (provider, error):
            assert provider is not None
            assert error is None
            
            # 在 context 內應該是租借狀態
            stats = manager.get_stats()
            assert stats['pool']['leased'] == 1
        
        # 離開 context 後應該自動歸還
        stats = manager.get_stats()
        assert stats['pool']['leased'] == 0
        assert stats['pool']['available'] >= 1
    
    def test_context_manager_with_error(self, manager):
        """測試 Context Manager 錯誤處理"""
        session_id = "test_context_error"
        
        # 先用完配額
        providers = []
        for i in range(manager.config.per_session_quota):
            p, _ = manager.lease(session_id)
            providers.append(p)
        
        # 使用 context manager 但會失敗
        with manager.lease_context(session_id) as (provider, error):
            assert provider is None
            assert error == PoolError.NO_CAPACITY_FOR_SESSION
        
        # 清理
        for p in providers:
            manager.release(p)
    
    def test_release_all(self, manager):
        """測試釋放 session 的所有 provider"""
        session_id = "test_release_all"
        
        # 租借多個
        providers = []
        for i in range(2):
            p, _ = manager.lease(session_id)
            providers.append(p)
        
        stats = manager.get_stats()
        assert stats['pool']['leased'] == 2
        
        # 釋放全部
        manager.release_all(session_id)
        
        stats = manager.get_stats()
        assert stats['pool']['leased'] == 0
        # 因為當 pool 超過 min_size 時，多餘的 provider 會被關閉
        # 所以這裡只檢查 available 至少有 min_size 個
        assert stats['pool']['available'] >= manager.config.min_size
    
    def test_report_error(self, manager):
        """測試錯誤報告和健康管理"""
        session_id = "test_error"
        provider, _ = manager.lease(session_id)
        
        # 報告錯誤（使用新的 mark_failure 方法）
        for i in range(2):  # max_failures 預設是 3
            manager.mark_failure(provider, f"Error {i}")
        
        # 檢查健康狀態（還未達到閾值）
        assert manager.is_provider_healthy(provider)
        
        # 再報告一次錯誤，應該標記為不健康
        manager.mark_failure(provider, "Final error")
        assert not manager.is_provider_healthy(provider)
        
        # 歸還不健康的 provider 應該被關閉
        initial_count = len(manager._all_providers)
        manager.release(provider)
        assert len(manager._all_providers) < initial_count
    
    def test_statistics(self, manager):
        """測試統計資訊收集"""
        session1 = "session_1"
        session2 = "session_2"
        
        # 執行一些操作
        p1, _ = manager.lease(session1)
        p2, _ = manager.lease(session2)
        time.sleep(0.1)  # 模擬使用時間
        manager.release(p1)
        manager.release(p2)
        
        # 檢查統計
        stats = manager.get_stats()
        
        assert stats['stats']['total_leases'] >= 2
        assert stats['stats']['total_releases'] >= 2
        assert stats['stats']['avg_wait_time'] >= 0  # 等待時間應該存在
    
    def test_shutdown(self, manager):
        """測試關閉功能"""
        # 租借一些 provider
        providers = []
        for i in range(2):
            p, _ = manager.lease(f"session_{i}")
            providers.append(p)
        
        # 記錄 provider 的 shutdown 方法，以便驗證
        for p in providers:
            assert hasattr(p, 'shutdown')
        
        # 關閉 manager
        manager.shutdown()
        
        # 檢查狀態清理
        assert len(manager._all_providers) == 0
        assert len(manager._leased) == 0
        assert len(manager._available) == 0
        assert len(manager._session_quotas) == 0
        
        # 檢查 provider 被正確關閉
        for p in providers:
            p.shutdown.assert_called_once()
    
    def test_waiting_queue(self, manager):
        """測試等待佇列機制"""
        import threading
        
        # 先租借到 pool 滿
        providers = []
        for i in range(manager.config.max_size):
            p, err = manager.lease(f"session_{i}")
            if p:
                providers.append(p)
        
        # 此時 pool 已滿，新請求應該進入等待佇列
        result = {}
        
        def lease_with_wait():
            p, err = manager.lease("waiting_session", timeout=2.0)
            result['provider'] = p
            result['error'] = err
        
        # 在另一個線程中請求
        thread = threading.Thread(target=lease_with_wait)
        thread.start()
        
        # 等待一下讓請求進入佇列
        time.sleep(0.1)
        
        # 檢查等待佇列
        stats = manager.get_stats()
        assert stats['pool']['waiting'] > 0
        
        # 釋放一個 provider
        manager.release(providers[0])
        
        # 等待線程完成
        thread.join(timeout=3.0)
        
        # 檢查是否成功獲得 provider
        assert result.get('provider') is not None
        assert result.get('error') is None
        
        # 清理
        if result.get('provider'):
            manager.release(result['provider'])
        for p in providers[1:]:
            manager.release(p)
    
    def test_timeout_handling(self, manager):
        """測試超時處理"""
        import threading
        
        # 租借所有 provider
        providers = []
        for i in range(manager.config.max_size):
            p, _ = manager.lease(f"session_{i}")
            if p:
                providers.append(p)
        
        # 嘗試租借，應該超時
        start_time = time.time()
        provider, error = manager.lease("timeout_session", timeout=0.5)
        elapsed = time.time() - start_time
        
        assert provider is None
        assert error == PoolError.TIMEOUT
        assert elapsed >= 0.5
        assert elapsed < 1.0  # 不應該等太久
        
        # 清理
        for p in providers:
            manager.release(p)
    
    def test_priority_with_aging(self, mock_provider_factory):
        """測試優先度與老化機制的綜合效果"""
        # 創建啟用老化的配置
        config = PoolConfig(
            min_size=1,
            max_size=1,
            per_session_quota=1,
            max_consecutive_failures=3,
            health_check_enabled=True,
            initialization_timeout=30.0,
            lease_timeout=10.0,
            provider_type="whisper"
        )
        
        with patch.object(ProviderPoolManager, '_initialize_pool'):
            manager = ProviderPoolManager(config)
            
            def create_and_register():
                provider = mock_provider_factory()
                provider_id = id(provider)
                manager._all_providers[provider_id] = provider
                manager._health[provider_id] = ProviderHealth(
                    consecutive_failures=0,
                    total_successes=0,
                    is_healthy=True,
                    last_error=None
                )
                manager._stats['total_created'] += 1
                return provider
            
            with patch.object(manager, '_create_provider', side_effect=create_and_register):
                provider = manager._create_provider()
                manager._available.append(provider)
                
                # 測試老化計算
                from src.provider.provider_manager import LeaseRequest
                
                # 創建兩個請求
                old_low_priority = LeaseRequest(
                    session_id="old_low",
                    priority=5,
                    timestamp=time.time() - 0.01  # 10ms 前
                )
                
                new_high_priority = LeaseRequest(
                    session_id="new_high",
                    priority=10,
                    timestamp=time.time()
                )
                
                # 計算有效優先度
                current_time = time.time()
                old_effective = old_low_priority.effective_priority(current_time, config.aging_factor)
                new_effective = new_high_priority.effective_priority(current_time, config.aging_factor)
                
                # 老請求因為等待了10ms，增加了 10 * 0.5 = 5 優先度
                # 所以應該是 5 + 5 = 10，與新的高優先度相等或略高
                assert old_effective >= 10.0
                assert 10.0 <= new_effective <= 10.1  # 新請求可能有微小的老化
                
                manager.shutdown()
    
    def test_health_check_mark_success(self, manager):
        """測試標記成功執行"""
        # 創建 provider
        provider, error = manager.lease("session1", timeout=0.1)
        assert provider is not None
        assert error is None
        
        # 標記成功
        manager.mark_success(provider)
        
        # 獲取健康統計
        stats = manager.get_health_stats()
        assert stats['healthy_providers'] == 1
        assert stats['unhealthy_providers'] == 0
        assert stats['total_providers'] == 1
        
        # 檢查詳細資訊
        details = stats['details'][0]
        assert details['provider_id'] == id(provider)
        assert details['is_healthy'] is True
        assert details['consecutive_failures'] == 0
        assert details['total_successes'] == 1
        
        # 釋放 provider
        manager.release(provider)
    
    def test_health_check_mark_failure(self, manager):
        """測試標記失敗執行"""
        # 創建 provider
        provider, error = manager.lease("session1", timeout=0.1)
        assert provider is not None
        
        # 標記失敗（但不到臨界值）
        manager.mark_failure(provider, "Test error 1")
        manager.mark_failure(provider, "Test error 2")
        
        # 檢查健康狀態（還是健康，因為默認 max_failures=3）
        stats = manager.get_health_stats()
        assert stats['healthy_providers'] == 1
        assert stats['unhealthy_providers'] == 0
        
        details = stats['details'][0]
        assert details['is_healthy'] is True
        assert details['consecutive_failures'] == 2
        
        # 再一次失敗達到臨界值
        manager.mark_failure(provider, "Test error 3")
        
        # 現在應該不健康
        stats = manager.get_health_stats()
        assert stats['healthy_providers'] == 0
        assert stats['unhealthy_providers'] == 1
        
        details = stats['details'][0]
        assert details['is_healthy'] is False
        assert details['consecutive_failures'] == 3
        
        # 釋放 provider
        manager.release(provider)
    
    def test_unhealthy_provider_skipped(self, manager):
        """測試不健康的 provider 被跳過"""
        # 創建並標記第一個 provider 為不健康
        provider1, _ = manager.lease("session1", timeout=0.1)
        assert provider1 is not None
        provider1_id = id(provider1)
        
        # 標記為不健康
        for _ in range(3):  # 達到 max_failures
            manager.mark_failure(provider1, "Error")
        
        # 釋放回池中（不健康的會被關閉）
        manager.release(provider1)
        
        # 租用新 provider，應該會創建新的而不是使用不健康的
        provider2, _ = manager.lease("session2", timeout=0.1)
        assert provider2 is not None
        assert id(provider2) != provider1_id  # 應該是不同的 provider
        
        # 檢查統計 - 不健康的 provider 已被移除
        stats = manager.get_stats()
        assert stats['pool']['total'] == 1  # 只有一個健康的 provider
        assert stats['pool']['unhealthy_providers'] == 0  # 不健康的已被移除
        
        # 清理
        manager.release(provider2)
    
    def test_health_recovery(self, manager):
        """測試健康恢復"""
        # 創建並標記 provider 為不健康
        provider, _ = manager.lease("session1", timeout=0.1)
        assert provider is not None
        
        # 標記為不健康
        for _ in range(3):
            manager.mark_failure(provider, "Error")
        
        # 檢查不健康狀態
        assert manager.is_provider_healthy(provider) is False
        
        # 標記成功執行（恢復健康）
        manager.mark_success(provider)
        
        # 檢查健康狀態
        assert manager.is_provider_healthy(provider) is True
        stats = manager.get_health_stats()
        assert stats['healthy_providers'] == 1
        assert stats['unhealthy_providers'] == 0
        
        details = stats['details'][0]
        assert details['consecutive_failures'] == 0  # 重置了
        assert details['total_successes'] == 1
        
        # 清理
        manager.release(provider)


class TestPoolConfig:
    """測試 PoolConfig 配置"""
    
    def test_config_structure(self):
        """測試配置結構"""
        config = PoolConfig(
            min_size=2,
            max_size=5,
            per_session_quota=3,
            max_consecutive_failures=3,
            health_check_enabled=True,
            initialization_timeout=30.0,
            lease_timeout=10.0,
            provider_type="whisper"
        )
        
        assert config.min_size == 2
        assert config.max_size == 5
        assert config.per_session_quota == 3
        assert config.max_consecutive_failures == 3
        assert config.health_check_enabled == True
        assert config.initialization_timeout == 30.0
        assert config.lease_timeout == 10.0
    
    @patch('src.config.ConfigManager')
    def test_from_config(self, mock_config_manager):
        """測試從 ConfigManager 創建配置"""
        # 模擬 ConfigManager
        mock_manager = MagicMock()
        mock_manager.providers.pool.min_size = 3
        mock_manager.providers.pool.max_size = 10
        mock_manager.providers.pool.per_session_quota = 2
        mock_manager.providers.pool.max_consecutive_failures = 5
        mock_manager.providers.pool.health_check_enabled = False
        mock_manager.providers.pool.initialization_timeout = 60.0
        mock_manager.providers.pool.lease_timeout = 20.0
        
        config = PoolConfig.from_config(mock_manager)
        
        assert config.min_size == 3
        assert config.max_size == 10
        assert config.per_session_quota == 2
        assert config.max_consecutive_failures == 5
        assert config.health_check_enabled == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])