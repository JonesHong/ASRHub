"""
DenoiseService 單元測試
測試音訊降噪功能，包括基礎降噪和智慧降噪系統
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
import warnings

# 由於可能沒有安裝 PyTorch/DeepFilterNet，使用條件導入
pytest_skip_reason = None
try:
    from src.service.denoise import DenoiseService
    denoise_available = True
except ImportError as e:
    denoise_available = False
    pytest_skip_reason = f"DenoiseService dependencies not available: {e}"


@pytest.mark.skipif(not denoise_available, reason=pytest_skip_reason)
class TestDenoiseService:
    """DenoiseService 基礎測試"""
    
    @pytest.fixture
    def denoiser(self):
        """建立 DenoiseService 實例（模擬模式）"""
        with patch('src.service.denoise.denoise_service.torch') as mock_torch:
            # 模擬 PyTorch 可用
            mock_torch.cuda.is_available.return_value = False
            
            # 創建實例但不初始化模型
            service = DenoiseService()
            service._model_initialized = False  # 確保不會嘗試載入真實模型
            service.enabled = True
            return service
    
    @pytest.fixture
    def sample_audio(self):
        """建立測試音訊 - 16kHz, 0.1秒 (1600 samples)"""
        duration = 0.1
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration))
        frequency = 440  # A4 音符
        audio = 0.3 * np.sin(2 * np.pi * frequency * t)  # 0.3 振幅
        return audio.astype(np.float32)
    
    @pytest.fixture
    def noisy_audio(self):
        """建立含噪音的測試音訊"""
        duration = 0.1
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 440Hz 信號 + 隨機噪音
        signal = 0.2 * np.sin(2 * np.pi * 440 * t)
        noise = np.random.normal(0, 0.05, len(t))
        
        return (signal + noise).astype(np.float32)
    
    def test_singleton(self, denoiser):
        """測試單例模式"""
        with patch('src.service.denoise.denoise_service.torch'):
            denoiser2 = DenoiseService()
            assert denoiser is denoiser2
    
    def test_config_loading(self, denoiser):
        """測試配置載入"""
        assert hasattr(denoiser, 'enabled')
        assert hasattr(denoiser, 'type')
        assert hasattr(denoiser, 'strength')
        assert hasattr(denoiser, 'model_base_dir')
        assert hasattr(denoiser, 'device')
        assert hasattr(denoiser, 'post_filter')
        
        # 檢查預設值
        assert isinstance(denoiser.strength, float)
        assert 0.0 <= denoiser.strength <= 1.0
        assert denoiser.device in ['cpu', 'cuda', 'auto']
    
    @patch('src.service.denoise.denoise_service.init_df')
    def test_model_initialization_success(self, mock_init_df, denoiser):
        """測試模型初始化成功情況"""
        # 模擬 DeepFilterNet 初始化
        mock_model = MagicMock()
        mock_df_state = MagicMock()
        mock_init_df.return_value = (mock_model, mock_df_state, "suffix", 1)
        
        # 執行初始化
        denoiser._initialize_model()
        
        # 驗證
        assert denoiser._model_initialized
        assert denoiser._model is not None
        assert denoiser._df_state is not None
        mock_init_df.assert_called_once()
    
    def test_model_initialization_import_error(self, denoiser):
        """測試缺少 DeepFilterNet 依賴時的錯誤處理"""
        with patch('src.service.denoise.denoise_service.init_df', side_effect=ImportError("DeepFilterNet not installed")):
            with pytest.raises(ImportError, match="DeepFilterNet 未安裝"):
                denoiser._initialize_model()
    
    def test_bytes_audio_conversion(self, denoiser, sample_audio):
        """測試 bytes 和 audio 轉換"""
        # 轉換為 bytes
        audio_bytes = denoiser._audio_to_bytes(sample_audio)
        assert isinstance(audio_bytes, bytes)
        assert len(audio_bytes) == len(sample_audio) * 2  # int16 = 2 bytes per sample
        
        # 轉換回 audio
        converted_audio = denoiser._bytes_to_audio(audio_bytes)
        assert isinstance(converted_audio, np.ndarray)
        assert len(converted_audio) == len(sample_audio)
        assert converted_audio.dtype == np.float32
        
        # 檢查轉換精度（由於 int16 量化，會有小誤差）
        np.testing.assert_allclose(converted_audio, sample_audio, atol=1/32768.0)
    
    @patch('src.service.denoise.denoise_service.enhance')
    def test_process_with_deepfilternet(self, mock_enhance, denoiser, sample_audio):
        """測試 DeepFilterNet 處理"""
        # 設定模擬
        denoiser._model_initialized = True
        denoiser._model = MagicMock()
        denoiser._df_state = MagicMock()
        denoiser.device = 'cpu'
        
        # 模擬 enhance 函數
        enhanced_tensor = MagicMock()
        enhanced_tensor.squeeze.return_value.cpu.return_value.numpy.return_value = sample_audio * 0.8
        mock_enhance.return_value = enhanced_tensor
        
        # 執行處理
        result = denoiser._process_with_deepfilternet(sample_audio, strength=0.7)
        
        # 驗證
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result) == len(sample_audio)
        mock_enhance.assert_called_once()
    
    def test_analyze_audio(self, denoiser, sample_audio, noisy_audio):
        """測試音訊分析功能"""
        # 測試乾淨音訊
        clean_analysis = denoiser._analyze_audio(sample_audio)
        
        required_keys = ['rms', 'snr_db', 'noise_level', 'spectral_centroid', 
                        'zcr', 'needs_denoising', 'expected_snr_gain']
        
        for key in required_keys:
            assert key in clean_analysis
        
        # 檢查分析結果合理性
        assert 0 <= clean_analysis['rms'] <= 1
        assert clean_analysis['noise_level'] in ['low', 'medium', 'high']
        assert clean_analysis['spectral_centroid'] > 0
        assert 0 <= clean_analysis['zcr'] <= 1
        assert isinstance(clean_analysis['needs_denoising'], bool)
        
        # 測試含噪音音訊
        noisy_analysis = denoiser._analyze_audio(noisy_audio)
        
        # 含噪音的音訊應該有更低的 SNR
        assert noisy_analysis['snr_db'] <= clean_analysis['snr_db']
        
        # 含噪音音訊更可能需要降噪
        if noisy_analysis['snr_db'] < 15.0:
            assert noisy_analysis['needs_denoising'] is True
    
    def test_determine_denoise_strategy(self, denoiser):
        """測試降噪策略決定"""
        # 測試不同用途的策略
        test_analysis = {
            'rms': 0.15, 'snr_db': 8.0, 'noise_level': 'high',
            'spectral_centroid': 2000, 'zcr': 0.1,
            'needs_denoising': True, 'expected_snr_gain': 8.0
        }
        
        # ASR 用途 - 應該積極降噪
        asr_strategy = denoiser._determine_denoise_strategy(test_analysis, "asr")
        assert asr_strategy['apply_denoising'] is True
        assert asr_strategy['aggressive'] is True
        assert asr_strategy['strength'] > denoiser.strength  # 更強的降噪
        
        # VAD 用途 - 保守降噪
        vad_strategy = denoiser._determine_denoise_strategy(test_analysis, "vad")
        assert vad_strategy['apply_denoising'] is True
        assert asr_strategy['strength'] >= vad_strategy['strength']  # ASR 比 VAD 更強
        
        # Recording 用途 - 最保守
        rec_strategy = denoiser._determine_denoise_strategy(test_analysis, "recording")
        if rec_strategy['apply_denoising']:
            assert rec_strategy['strength'] <= vad_strategy['strength']
        
        # 測試不需要降噪的情況
        clean_analysis = test_analysis.copy()
        clean_analysis['needs_denoising'] = False
        
        clean_strategy = denoiser._determine_denoise_strategy(clean_analysis, "asr")
        assert clean_strategy['apply_denoising'] is False
        assert clean_strategy['strength'] == 0.0
    
    def test_execute_denoise_pipeline(self, denoiser, sample_audio):
        """測試降噪管線執行"""
        # 模擬設定
        denoiser._model_initialized = True
        
        with patch.object(denoiser, '_process_with_deepfilternet') as mock_process:
            mock_process.return_value = sample_audio * 0.9
            
            # 測試執行降噪
            decisions = {
                'apply_denoising': True,
                'strength': 0.5,
                'aggressive': False,
                'preserve_quality': True
            }
            
            processed_audio, applied_steps = denoiser._execute_denoise_pipeline(
                sample_audio, decisions
            )
            
            # 驗證
            assert isinstance(processed_audio, np.ndarray)
            assert len(applied_steps) > 0
            assert any("DeepFilterNet" in step for step in applied_steps)
            mock_process.assert_called_once_with(sample_audio, 0.5)
            
            # 測試不降噪的情況
            no_denoise_decisions = {'apply_denoising': False}
            processed_audio, applied_steps = denoiser._execute_denoise_pipeline(
                sample_audio, no_denoise_decisions
            )
            
            assert "無需降噪處理" in applied_steps
    
    def test_denoise_disabled_service(self, denoiser, sample_audio):
        """測試服務未啟用時的行為"""
        denoiser.enabled = False
        
        with pytest.raises(RuntimeError, match="DenoiseService 未啟用"):
            denoiser.denoise(sample_audio)
    
    def test_denoise_empty_audio(self, denoiser):
        """測試空音訊處理"""
        denoiser.enabled = True
        denoiser._model_initialized = True
        
        empty_audio = np.array([], dtype=np.float32)
        result = denoiser.denoise(empty_audio)
        
        # 空音訊應該直接返回
        np.testing.assert_array_equal(result, empty_audio)
    
    def test_denoise_invalid_dimensions(self, denoiser):
        """測試無效音訊維度"""
        denoiser.enabled = True
        denoiser._model_initialized = True
        
        # 多聲道音訊
        stereo_audio = np.random.randn(1600, 2).astype(np.float32)
        
        with pytest.raises(ValueError, match="目前只支援單聲道音訊"):
            denoiser.denoise(stereo_audio)
    
    @patch.object(DenoiseService, '_process_with_deepfilternet')
    def test_denoise_with_bytes_input(self, mock_process, denoiser, sample_audio):
        """測試使用 bytes 輸入的降噪"""
        denoiser.enabled = True
        denoiser._model_initialized = True
        mock_process.return_value = sample_audio * 0.8
        
        # 轉換為 bytes
        audio_bytes = denoiser._audio_to_bytes(sample_audio)
        
        # 執行降噪
        result = denoiser.denoise(audio_bytes)
        
        # 驗證返回格式
        assert isinstance(result, bytes)
        assert len(result) == len(audio_bytes)
        
        # 驗證處理被調用
        mock_process.assert_called_once()
    
    def test_model_info_property(self, denoiser):
        """測試模型資訊屬性"""
        # 未初始化狀態
        info = denoiser.model_info
        assert info['status'] == 'not_initialized'
        
        # 模擬初始化完成
        denoiser._model_initialized = True
        info = denoiser.model_info
        
        assert info['status'] == 'ready'
        assert 'model_type' in info
        assert 'device' in info
        assert 'post_filter' in info
        assert 'default_strength' in info
    
    def test_is_available_property(self, denoiser):
        """測試服務可用性檢查"""
        # 服務未啟用
        denoiser.enabled = False
        assert denoiser.is_available is False
        
        # 服務啟用但模型未初始化
        denoiser.enabled = True
        
        with patch.object(denoiser, '_ensure_model_ready', side_effect=Exception("Model failed")):
            assert denoiser.is_available is False
        
        # 服務正常
        with patch.object(denoiser, '_ensure_model_ready'):
            assert denoiser.is_available is True


@pytest.mark.skipif(not denoise_available, reason=pytest_skip_reason)
class TestAutoDenoiseSystem:
    """測試智慧降噪系統"""
    
    @pytest.fixture
    def denoiser(self):
        """建立模擬的 DenoiseService"""
        with patch('src.service.denoise.denoise_service.torch') as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            
            service = DenoiseService()
            service._model_initialized = True  # 模擬初始化完成
            service.enabled = True
            service._model = MagicMock()
            service._df_state = MagicMock()
            return service
    
    @pytest.fixture
    def test_audio(self):
        """建立測試音訊"""
        duration = 0.1
        sample_rate = 16000
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples)
        
        # 建立含噪音的音訊
        signal = 0.15 * np.sin(2 * np.pi * 440 * t)
        noise = np.random.normal(0, 0.03, samples)
        
        return (signal + noise).astype(np.float32)
    
    @patch.object(DenoiseService, '_process_with_deepfilternet')
    def test_auto_denoise_asr_mode(self, mock_process, denoiser, test_audio):
        """測試 ASR 模式的智慧降噪"""
        mock_process.return_value = test_audio * 0.85
        
        # 執行智慧降噪
        processed_audio, report = denoiser.auto_denoise(test_audio, purpose="asr")
        
        # 檢查報告結構
        assert report['purpose'] == 'asr'
        assert 'analysis' in report
        assert 'decisions' in report
        assert 'applied_steps' in report
        assert 'performance' in report
        
        # 檢查分析結果
        analysis = report['analysis']
        assert 'snr_estimate' in analysis
        assert 'noise_level' in analysis
        assert 'needs_denoising' in analysis
        
        # 檢查處理結果
        assert isinstance(processed_audio, np.ndarray)
        assert len(processed_audio) == len(test_audio)
        
        if mock_process.called:
            # 如果需要降噪，應該有相應的報告
            assert len(report['applied_steps']) > 0
    
    @patch.object(DenoiseService, '_process_with_deepfilternet')
    def test_auto_denoise_vad_mode(self, mock_process, denoiser, test_audio):
        """測試 VAD 模式的保守降噪"""
        mock_process.return_value = test_audio * 0.9
        
        processed_audio, report = denoiser.auto_denoise(test_audio, purpose="vad")
        
        assert report['purpose'] == 'vad'
        assert isinstance(processed_audio, np.ndarray)
        
        # VAD 模式應該比 ASR 更保守
        # (具體檢查取決於測試音訊的特性)
    
    def test_auto_denoise_with_bytes(self, denoiser, test_audio):
        """測試使用 bytes 輸入的智慧降噪"""
        with patch.object(denoiser, '_process_with_deepfilternet') as mock_process:
            mock_process.return_value = test_audio * 0.9
            
            audio_bytes = denoiser._audio_to_bytes(test_audio)
            
            # 執行智慧降噪
            processed_bytes, report = denoiser.auto_denoise(audio_bytes, purpose="general")
            
            # 檢查返回格式
            assert isinstance(processed_bytes, bytes)
            assert len(processed_bytes) == len(audio_bytes)
            assert report['purpose'] == 'general'
    
    def test_auto_denoise_empty_audio(self, denoiser):
        """測試空音訊的智慧降噪"""
        empty_audio = np.array([], dtype=np.float32)
        
        processed_audio, report = denoiser.auto_denoise(empty_audio)
        
        # 空音訊應該直接返回
        np.testing.assert_array_equal(processed_audio, empty_audio)
        assert report['applied_steps'] == []
        assert 'error' in report['analysis']
    
    def test_auto_denoise_error_handling(self, denoiser, test_audio):
        """測試智慧降噪的錯誤處理"""
        with patch.object(denoiser, '_analyze_audio', side_effect=Exception("Analysis failed")):
            
            processed_audio, report = denoiser.auto_denoise(test_audio)
            
            # 錯誤時應該返回原始音訊
            np.testing.assert_array_equal(processed_audio, test_audio)
            assert 'error' in report['analysis']
    
    def test_performance_metrics(self, denoiser, test_audio):
        """測試性能指標記錄"""
        with patch.object(denoiser, '_process_with_deepfilternet') as mock_process:
            mock_process.return_value = test_audio
            
            processed_audio, report = denoiser.auto_denoise(test_audio)
            
            # 檢查性能指標
            perf = report['performance']
            assert 'processing_time_ms' in perf
            assert float(perf['processing_time_ms'].split()[0]) >= 0  # 處理時間 >= 0


@pytest.mark.skipif(denoise_available, reason="Testing fallback when dependencies are missing")
def test_import_fallback():
    """測試缺少依賴時的降級處理"""
    # 這個測試只在實際缺少依賴時運行
    with pytest.raises(ImportError):
        from src.service.denoise import DenoiseService