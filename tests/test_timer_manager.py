"""
TimerManager 單元測試
測試 TimerManager 的基本功能
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.core.timer_manager import TimerManager, timer_manager
from src.core.timer_service import TimerService


class TestTimerManager:
    """TimerManager 測試類別"""
    
    @pytest.fixture
    def clean_timer_manager(self):
        """清理 TimerManager 狀態"""
        # 清空現有的 timers
        timer_manager.timers.clear()
        yield timer_manager
        # 測試後清理
        timer_manager.timers.clear()
    
    def test_singleton_pattern(self):
        """測試單例模式"""
        manager1 = TimerManager()
        manager2 = TimerManager()
        
        # 兩個實例應該是同一個對象
        assert manager1 is manager2
        assert manager1 is timer_manager
    
    @pytest.mark.asyncio
    async def test_create_timer(self, clean_timer_manager):
        """測試建立 timer"""
        session_id = "test_session_123"
        
        # 建立 timer
        timer = await clean_timer_manager.create_timer(session_id)
        
        # 驗證
        assert timer is not None
        assert isinstance(timer, TimerService)
        assert timer.session_id == session_id
        assert session_id in clean_timer_manager.timers
    
    @pytest.mark.asyncio
    async def test_create_duplicate_timer(self, clean_timer_manager):
        """測試建立重複的 timer"""
        session_id = "test_session_456"
        
        # 建立第一個 timer
        timer1 = await clean_timer_manager.create_timer(session_id)
        
        # 嘗試建立重複的 timer
        timer2 = await clean_timer_manager.create_timer(session_id)
        
        # 應該返回同一個 timer
        assert timer1 is timer2
        assert len(clean_timer_manager.timers) == 1
    
    def test_get_timer(self, clean_timer_manager):
        """測試取得 timer"""
        session_id = "test_session_789"
        
        # 直接加入 timer 到管理器
        mock_timer = MagicMock(spec=TimerService)
        mock_timer.session_id = session_id
        clean_timer_manager.timers[session_id] = mock_timer
        
        # 取得 timer
        retrieved_timer = clean_timer_manager.get_timer(session_id)
        
        # 驗證
        assert retrieved_timer is mock_timer
    
    def test_get_nonexistent_timer(self, clean_timer_manager):
        """測試取得不存在的 timer"""
        timer = clean_timer_manager.get_timer("nonexistent_session")
        assert timer is None
    
    @pytest.mark.asyncio
    async def test_destroy_timer(self, clean_timer_manager):
        """測試銷毀 timer"""
        session_id = "test_session_destroy"
        
        # 建立並銷毀 timer
        timer = await clean_timer_manager.create_timer(session_id)
        
        # Mock cancel_all_timers 方法
        timer.cancel_all_timers = MagicMock()
        
        await clean_timer_manager.destroy_timer(session_id)
        
        # 驗證
        assert session_id not in clean_timer_manager.timers
        timer.cancel_all_timers.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_destroy_nonexistent_timer(self, clean_timer_manager):
        """測試銷毀不存在的 timer"""
        # 應該不會拋出異常
        await clean_timer_manager.destroy_timer("nonexistent_session")
    
    @pytest.mark.asyncio
    async def test_destroy_all_timers(self, clean_timer_manager):
        """測試銷毀所有 timers"""
        # 建立多個 timers
        session_ids = ["session1", "session2", "session3"]
        
        for session_id in session_ids:
            timer = await clean_timer_manager.create_timer(session_id)
            # Mock cancel_all_timers 方法
            timer.cancel_all_timers = MagicMock()
        
        # 銷毀所有 timers
        await clean_timer_manager.destroy_all_timers()
        
        # 驗證
        assert len(clean_timer_manager.timers) == 0
    
    def test_get_active_session_count(self, clean_timer_manager):
        """測試取得活躍 session 數量"""
        # 加入幾個 timers
        for i in range(3):
            clean_timer_manager.timers[f"session_{i}"] = MagicMock()
        
        count = clean_timer_manager.get_active_session_count()
        assert count == 3
    
    def test_get_active_sessions(self, clean_timer_manager):
        """測試取得活躍 session IDs"""
        session_ids = ["session_a", "session_b", "session_c"]
        
        for session_id in session_ids:
            clean_timer_manager.timers[session_id] = MagicMock()
        
        active_sessions = clean_timer_manager.get_active_sessions()
        assert set(active_sessions) == set(session_ids)
    
    def test_has_timer(self, clean_timer_manager):
        """測試檢查是否有 timer"""
        session_id = "test_session_has"
        
        # 初始應該沒有
        assert not clean_timer_manager.has_timer(session_id)
        
        # 加入 timer
        clean_timer_manager.timers[session_id] = MagicMock()
        
        # 現在應該有
        assert clean_timer_manager.has_timer(session_id)
    
    @pytest.mark.asyncio
    async def test_concurrent_create(self, clean_timer_manager):
        """測試並發建立 timers"""
        session_ids = [f"concurrent_session_{i}" for i in range(10)]
        
        # 並發建立 timers
        tasks = [clean_timer_manager.create_timer(sid) for sid in session_ids]
        timers = await asyncio.gather(*tasks)
        
        # 驗證
        assert len(timers) == 10
        assert len(clean_timer_manager.timers) == 10
        
        for i, timer in enumerate(timers):
            assert timer.session_id == session_ids[i]
    
    @pytest.mark.asyncio
    async def test_concurrent_destroy(self, clean_timer_manager):
        """測試並發銷毀 timers"""
        session_ids = [f"concurrent_destroy_{i}" for i in range(10)]
        
        # 先建立 timers
        for session_id in session_ids:
            timer = await clean_timer_manager.create_timer(session_id)
            timer.cancel_all_timers = MagicMock()
        
        # 並發銷毀 timers
        tasks = [clean_timer_manager.destroy_timer(sid) for sid in session_ids]
        await asyncio.gather(*tasks)
        
        # 驗證
        assert len(clean_timer_manager.timers) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])