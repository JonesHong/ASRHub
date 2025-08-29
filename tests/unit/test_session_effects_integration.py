"""測試 SessionEffects 與 Provider Pool 的整合 (Phase 3)"""

import pytest
import threading
import time
import numpy as np
from unittest.mock import Mock, MagicMock, patch, call
from concurrent.futures import Future

# Mock whisper module before importing SessionEffects
import sys
sys.modules['whisper'] = MagicMock()

# 現在可以安全地導入
from src.provider.provider_manager import PoolError
from src.store.sessions.sessions_effect import SessionEffects


class TestSessionEffectsProviderPoolIntegration:
    """測試 Phase 3: PyStoreX Effects 整合"""
    
    @pytest.fixture
    def mock_whisper_provider(self):
        """Mock WhisperProvider"""
        provider = Mock()
        provider.transcribe = Mock(return_value={"text": "測試轉譯結果"})
        provider.shutdown = Mock()
        return provider
    
    @pytest.fixture
    def mock_audio_queue(self):
        """Mock audio_queue"""
        with patch('src.store.sessions.sessions_effect.audio_queue') as mock_queue:
            # 模擬音訊數據
            audio_chunks = [
                np.random.randn(1600).astype(np.float32),  # 100ms at 16kHz
                np.random.randn(1600).astype(np.float32),
                None  # 結束標記
            ]
            mock_queue.pop = Mock(side_effect=audio_chunks)
            mock_queue.clear = Mock()
            yield mock_queue
    
    @pytest.fixture
    def session_effects(self, mock_whisper_provider):
        """創建 SessionEffects 實例"""
        # Patch WhisperProvider 在它被 import 的地方
        with patch('src.provider.whisper.whisper_provider.WhisperProvider') as MockWhisperProvider:
            MockWhisperProvider.return_value = mock_whisper_provider
            
            # 初始化 SessionEffects
            effects = SessionEffects()
            yield effects
            
            # 清理
            effects.shutdown()
    
    def test_provider_pool_initialization(self, session_effects):
        """測試 Provider Pool 初始化"""
        # 檢查 pool 是否正確初始化
        assert hasattr(session_effects, '_provider_pool')
        assert session_effects._provider_pool is not None
        
        # 檢查 ThreadPoolExecutor 初始化
        assert hasattr(session_effects, '_executor')
        assert session_effects._executor is not None
        
        # 檢查配置
        pool_config = session_effects._provider_pool.config
        assert pool_config.min_size == 2
        assert pool_config.max_size == 5
        assert pool_config.per_session_quota == 2
    
    def test_transcription_with_pool(self, session_effects, mock_whisper_provider, mock_audio_queue):
        """測試使用 Provider Pool 進行轉譯"""
        session_id = "test_session_1"
        
        with patch.object(session_effects._provider_pool, 'lease') as mock_lease, \
             patch.object(session_effects._provider_pool, 'release') as mock_release:
            
            # 設置 mock
            mock_lease.return_value = (mock_whisper_provider, None)
            
            # 執行轉譯
            result = session_effects._do_transcription(session_id)
            
            # 驗證 lease 被調用
            mock_lease.assert_called_once_with(session_id, timeout=10.0)
            
            # 驗證 provider 被使用
            assert mock_whisper_provider.transcribe.called
            
            # 驗證 release 被調用
            mock_release.assert_called_once_with(mock_whisper_provider)
            
            # 驗證結果
            assert result == {"text": "測試轉譯結果"}
    
    def test_transcription_lease_failure(self, session_effects, mock_audio_queue):
        """測試租用 Provider 失敗的情況"""
        session_id = "test_session_2"
        
        with patch.object(session_effects._provider_pool, 'lease') as mock_lease:
            # 模擬租用失敗
            mock_lease.return_value = (None, PoolError.TIMEOUT)
            
            # 執行轉譯
            result = session_effects._do_transcription(session_id)
            
            # 驗證返回 None
            assert result is None
            
            # 驗證 lease 被調用
            mock_lease.assert_called_once_with(session_id, timeout=10.0)
    
    def test_transcription_error_handling(self, session_effects, mock_whisper_provider, mock_audio_queue):
        """測試轉譯錯誤處理"""
        session_id = "test_session_3"
        
        with patch.object(session_effects._provider_pool, 'lease') as mock_lease, \
             patch.object(session_effects._provider_pool, 'release') as mock_release:
            
            # 設置 mock
            mock_lease.return_value = (mock_whisper_provider, None)
            mock_whisper_provider.transcribe.side_effect = Exception("轉譯錯誤")
            
            # 執行轉譯
            result = session_effects._do_transcription(session_id)
            
            # 驗證返回 None
            assert result is None
            
            # Phase 4: mark_unhealthy 待實作
            # mock_mark_unhealthy.assert_called_once_with(mock_whisper_provider)
            
            # 驗證 release 仍然被調用（在 finally 中）
            mock_release.assert_called_once_with(mock_whisper_provider)
    
    def test_async_transcription_execution(self, session_effects, mock_whisper_provider, mock_audio_queue):
        """測試異步轉譯執行"""
        session_id = "test_session_4"
        
        with patch.object(session_effects._provider_pool, 'lease') as mock_lease, \
             patch.object(session_effects._provider_pool, 'release') as mock_release:
            
            # 設置 mock
            mock_lease.return_value = (mock_whisper_provider, None)
            
            # 模擬 action
            action = Mock()
            action.payload = session_id
            
            # 執行異步轉譯
            result_action = session_effects._start_transcription(action)
            
            # 驗證立即返回開始 action
            assert result_action is not None, f"result_action is None"
            # 實際應該檢查是否為 transcribe_started action
            
            # 驗證 future 被創建（應該立即就有）
            print(f"Futures dict: {session_effects._transcription_futures}")
            assert session_id in session_effects._transcription_futures, f"session_id {session_id} not in futures dict"
            future = session_effects._transcription_futures[session_id]
            assert isinstance(future, Future)
            
            # 等待異步完成
            time.sleep(0.5)
            
            # 驗證轉譯被執行
            assert future.done()
    
    def test_session_cleanup_cancels_transcription(self, session_effects):
        """測試 session 清理會取消進行中的轉譯"""
        session_id = "test_session_5"
        
        # 創建一個 mock future
        mock_future = Mock()
        mock_future.done.return_value = False
        mock_future.cancel = Mock()
        
        # 添加到追蹤
        session_effects._transcription_futures[session_id] = mock_future
        
        # 創建 action
        action = Mock()
        action.payload = session_id
        
        # 執行清理
        session_effects._cleanup_session(action)
        
        # 驗證 future 被取消
        mock_future.cancel.assert_called_once()
        
        # 驗證從追蹤中移除
        assert session_id not in session_effects._transcription_futures
    
    def test_concurrent_transcriptions(self, session_effects, mock_whisper_provider, mock_audio_queue):
        """測試並發轉譯"""
        sessions = ["session_1", "session_2", "session_3"]
        
        with patch.object(session_effects._provider_pool, 'lease') as mock_lease, \
             patch.object(session_effects._provider_pool, 'release') as mock_release, \
             patch('src.store.sessions.sessions_effect.audio_queue') as mock_queue:
            
            # 設置音訊數據（每個 session 需要獨立的數據）
            def pop_side_effect(session_id):
                # 每個 session 返回音訊數據然後 None
                if not hasattr(pop_side_effect, 'call_count'):
                    pop_side_effect.call_count = {}
                if session_id not in pop_side_effect.call_count:
                    pop_side_effect.call_count[session_id] = 0
                
                pop_side_effect.call_count[session_id] += 1
                if pop_side_effect.call_count[session_id] <= 2:
                    return np.random.randn(1600).astype(np.float32)
                return None  # 結束標記
            
            mock_queue.pop = Mock(side_effect=pop_side_effect)
            mock_queue.clear = Mock()
            
            # 為每個 session 創建不同的 provider
            providers = [Mock() for _ in sessions]
            for i, provider in enumerate(providers):
                provider.transcribe = Mock(return_value={"text": f"結果 {i+1}"})
            
            # 設置 lease 返回不同的 provider
            mock_lease.side_effect = [(p, None) for p in providers]
            
            # 並發執行轉譯
            results = []
            threads = []
            for session_id in sessions:
                def do_transcribe(sid):
                    result = session_effects._do_transcription(sid)
                    results.append(result)
                
                thread = threading.Thread(target=lambda s=session_id: do_transcribe(s))
                thread.start()
                threads.append(thread)
            
            # 等待所有執行緒完成
            for thread in threads:
                thread.join(timeout=2)
            
            # 驗證所有 session 都成功轉譯
            assert len(results) == 3
            assert all(r is not None for r in results)
            
            # 驗證 lease 被調用 3 次
            assert mock_lease.call_count == 3
            
            # 驗證 release 被調用 3 次
            assert mock_release.call_count == 3
    
    def test_shutdown_cleanup(self, session_effects):
        """測試 shutdown 清理"""
        # 添加一些測試數據
        session_effects._transcription_futures["session_1"] = Mock(spec=Future)
        session_effects._vad_sessions["session_2"] = True
        session_effects._wakeword_sessions["session_3"] = True
        session_effects._recording_sessions["session_4"] = True
        
        with patch.object(session_effects._executor, 'shutdown') as mock_executor_shutdown, \
             patch.object(session_effects._provider_pool, 'shutdown') as mock_pool_shutdown:
            
            # 執行 shutdown
            session_effects.shutdown()
            
            # 驗證 executor 關閉
            mock_executor_shutdown.assert_called_once_with(wait=True)
            
            # 驗證 pool 關閉
            mock_pool_shutdown.assert_called_once()
            
            # 驗證所有資源被清理
            assert len(session_effects._transcription_futures) == 0
            assert len(session_effects._vad_sessions) == 0
            assert len(session_effects._wakeword_sessions) == 0
            assert len(session_effects._recording_sessions) == 0