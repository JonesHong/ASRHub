"""
AudioEnhancer 單元測試 - Phase 3 完整版本
測試智慧處理系統和進階工具
"""
import pytest
import numpy as np
from src.service.audio_enhancer import AudioEnhancer


class TestAudioEnhancer:
    """AudioEnhancer 基礎測試"""
    
    @pytest.fixture
    def enhancer(self):
        """建立 AudioEnhancer 實例"""
        return AudioEnhancer()
    
    @pytest.fixture
    def sample_audio(self):
        """建立測試音訊
        
        16kHz, 0.1秒 (1600 samples)
        """
        # 建立 440Hz 正弦波
        duration = 0.1
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration))
        frequency = 440  # A4 音符
        audio = 0.3 * np.sin(2 * np.pi * frequency * t)  # 0.3 振幅
        return audio.astype(np.float32)
    
    @pytest.fixture
    def quiet_audio(self):
        """建立安靜的測試音訊"""
        duration = 0.1
        sample_rate = 16000
        samples = int(sample_rate * duration)
        # 很小的雜訊
        audio = np.random.normal(0, 0.01, samples)
        return audio.astype(np.float32)
    
    @pytest.fixture
    def loud_audio(self):
        """建立大聲的測試音訊"""
        duration = 0.1
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration))
        # 接近削波的音訊
        audio = 0.9 * np.sin(2 * np.pi * 440 * t)
        return audio.astype(np.float32)
    
    def test_singleton(self, enhancer):
        """測試單例模式"""
        enhancer2 = AudioEnhancer()
        assert enhancer is enhancer2
    
    def test_remove_dc_offset(self, enhancer, sample_audio):
        """測試 DC offset 移除"""
        # 加入 DC offset
        audio_with_dc = sample_audio + 0.1
        
        # 移除 DC offset
        result = enhancer.remove_dc_offset(audio_with_dc)
        
        # 檢查平均值接近 0
        assert abs(np.mean(result)) < 0.01
    
    def test_apply_gain(self, enhancer, sample_audio):
        """測試增益調整"""
        # 測試放大 6dB (約 2 倍)
        result = enhancer.apply_gain(sample_audio, 6.0)
        
        # 檢查 RMS 增加
        original_rms = np.sqrt(np.mean(sample_audio ** 2))
        result_rms = np.sqrt(np.mean(result ** 2))
        
        # 6dB 約等於 2 倍
        assert result_rms / original_rms > 1.9
        assert result_rms / original_rms < 2.1
    
    def test_apply_hard_limiter(self, enhancer, loud_audio):
        """測試硬限幅器"""
        # 放大音訊使其削波
        clipping_audio = loud_audio * 1.5
        
        # 應用限幅器
        result = enhancer.apply_hard_limiter(clipping_audio, threshold=0.95)
        
        # 檢查沒有超過閾值
        assert np.max(np.abs(result)) <= 0.95
    
    def test_calculate_rms(self, enhancer, sample_audio):
        """測試 RMS 計算"""
        rms = enhancer.calculate_rms(sample_audio)
        
        # 0.3 振幅的正弦波 RMS 約為 0.3 / sqrt(2) ≈ 0.212
        expected_rms = 0.3 / np.sqrt(2)
        assert abs(rms - expected_rms) < 0.01
    
    def test_normalize_rms(self, enhancer, quiet_audio):
        """測試 RMS 標準化"""
        target_rms = 0.1
        
        # 標準化
        result = enhancer.normalize_rms(quiet_audio, target_rms)
        
        # 檢查 RMS 有增加（但可能因為最大增益限制無法達到目標）
        original_rms = enhancer.calculate_rms(quiet_audio)
        result_rms = enhancer.calculate_rms(result)
        
        # 檢查增益被限制在 5 倍
        gain = result_rms / original_rms
        assert gain <= 5.1  # 最大增益 5 倍 + 一點誤差
        assert result_rms > original_rms  # 確實有增強
    
    
    def test_max_gain_limit(self, enhancer):
        """測試最大增益限制"""
        # 建立非常安靜的音訊
        very_quiet = np.random.normal(0, 0.001, 1600).astype(np.float32)
        
        # 標準化到很高的目標
        result = enhancer.normalize_rms(very_quiet, target_rms=0.5)
        
        # 檢查增益有被限制
        gain = enhancer.calculate_rms(result) / enhancer.calculate_rms(very_quiet)
        assert gain <= 5.1  # 最大增益 5 倍 + 一點誤差

    # ========== 進階工具測試 ==========
    
    def test_apply_compression(self, enhancer, sample_audio):
        """測試動態壓縮"""
        # 建立動態範圍很大的音訊
        dynamic_audio = np.concatenate([
            sample_audio * 0.05,  # 小聲部分
            sample_audio * 0.8   # 大聲部分  
        ])
        
        # 應用壓縮
        compressed = enhancer.apply_compression(dynamic_audio, threshold=-25, ratio=3.0)
        
        # 檢查處理效果 - 壓縮器主要影響大聲部分，使整體更均勻
        assert len(compressed) == len(dynamic_audio)
        assert np.max(np.abs(compressed)) <= np.max(np.abs(dynamic_audio))  # 不會增加峰值
    
    def test_apply_limiter(self, enhancer, loud_audio):
        """測試軟限幅器"""
        # 放大音訊使其超過限制
        over_limit = loud_audio * 1.2
        
        # 應用限幅器
        limited = enhancer.apply_limiter(over_limit, ceiling=0.9)
        
        # 檢查軟限幅效果
        assert len(limited) == len(over_limit)
        # 軟限幅會將超過閾值的部分用 tanh 處理，不會完全削波
        assert np.max(np.abs(limited)) <= 1.0  # 合理的上限
    
    def test_apply_gate(self, enhancer):
        """測試噪音門"""
        # 建立包含噪音段和信號段的音訊
        noise = np.random.normal(0, 0.01, 800).astype(np.float32)  # 安靜噪音
        signal = 0.3 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.05, 800))  # 信號
        mixed_audio = np.concatenate([noise, signal])
        
        # 應用噪音門
        gated = enhancer.apply_gate(mixed_audio, threshold=-30)
        
        # 檢查噪音段被衰減，信號段保持
        noise_section_rms = np.sqrt(np.mean(gated[:800] ** 2))
        signal_section_rms = np.sqrt(np.mean(gated[800:] ** 2))
        
        assert signal_section_rms > noise_section_rms * 2  # 信號明顯大於噪音
        assert len(gated) == len(mixed_audio)
    
    def test_apply_eq(self, enhancer, sample_audio):
        """測試均衡器 (簡化版)"""
        eq_bands = {100: 3, 1000: -2, 10000: 1}
        
        # 應用均衡器
        eq_result = enhancer.apply_eq(sample_audio, eq_bands)
        
        # 目前是簡化實作，應該返回原始音訊
        np.testing.assert_array_equal(eq_result, sample_audio)
    
    # ========== 智慧處理系統測試 ==========
    
    def test_auto_enhance_asr_quiet(self, enhancer):
        """測試 ASR 模式對安靜音訊的智慧處理"""
        # 建立安靜音訊
        quiet_audio = 0.02 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600))
        audio_bytes = (quiet_audio * 32768).astype(np.int16).tobytes()
        
        # 使用智慧處理
        processed_bytes, report = enhancer.auto_enhance(audio_bytes, purpose="asr")
        
        # 檢查報告
        assert report['purpose'] == 'asr'
        assert len(report['applied_steps']) > 0
        assert report['decisions']['needs_gain'] == True or report['decisions']['needs_normalization'] == True
        
        # 檢查音訊有被處理
        assert processed_bytes != audio_bytes
        assert len(processed_bytes) == len(audio_bytes)
    
    def test_auto_enhance_asr_loud(self, enhancer):
        """測試 ASR 模式對大聲音訊的智慧處理"""
        # 建立音量足夠的音訊
        loud_audio = 0.2 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600))
        audio_bytes = (loud_audio * 32768).astype(np.int16).tobytes()
        
        # 使用智慧處理
        processed_bytes, report = enhancer.auto_enhance(audio_bytes, purpose="asr")
        
        # 檢查報告
        assert report['purpose'] == 'asr'
        assert report['decisions']['needs_gain'] == False
        assert report['decisions']['needs_normalization'] == False
        
        # 基本清理還是會做
        assert len(report['applied_steps']) >= 1  # 至少 DC offset
    
    def test_auto_enhance_vad(self, enhancer, sample_audio):
        """測試 VAD 模式的最小處理"""
        audio_bytes = (sample_audio * 32768).astype(np.int16).tobytes()
        
        # 使用智慧處理
        processed_bytes, report = enhancer.auto_enhance(audio_bytes, purpose="vad")
        
        # 檢查報告
        assert report['purpose'] == 'vad'
        # VAD 只做基礎清理
        expected_steps = ['DC Offset 移除', '高通濾波']
        for step in expected_steps:
            assert any(step in applied_step for applied_step in report['applied_steps'])
    
    def test_auto_enhance_recording(self, enhancer, sample_audio):
        """測試錄音模式的保守處理"""
        audio_bytes = (sample_audio * 32768).astype(np.int16).tobytes()
        
        # 使用智慧處理
        processed_bytes, report = enhancer.auto_enhance(audio_bytes, purpose="recording")
        
        # 檢查報告
        assert report['purpose'] == 'recording'
        # 錄音模式處理最少
        assert 'DC Offset 移除' in report['applied_steps']
    
    def test_auto_enhance_general(self, enhancer):
        """測試一般用途的平衡處理"""
        # 建立需要多種處理的音訊 - 更極端的動態範圍
        quiet_part = 0.005 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.05, 800))  # 非常安靜
        loud_part = 0.95 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.05, 800))   # 接近削波
        problematic_audio = np.concatenate([quiet_part, loud_part]) + 0.05  # 加入 DC offset
        
        audio_bytes = (problematic_audio * 32768).astype(np.int16).tobytes()
        
        # 使用智慧處理
        processed_bytes, report = enhancer.auto_enhance(audio_bytes, purpose="general")
        
        # 檢查報告
        assert report['purpose'] == 'general'
        assert len(report['applied_steps']) > 0
        
        # 檢查 DC offset 一定會被處理
        assert 'DC Offset 移除' in report['applied_steps']
        
        # 檢查至少有基本處理
        assert len(report['applied_steps']) >= 1
    
    def test_audio_analysis(self, enhancer, sample_audio, quiet_audio, loud_audio):
        """測試音訊分析功能"""
        # 測試正常音訊
        analysis = enhancer._analyze_audio(sample_audio)
        
        required_keys = ['rms', 'rms_db', 'peak_level', 'dc_offset', 'snr_db', 
                        'has_clipping', 'dynamic_range', 'needs_gain', 
                        'needs_compression', 'needs_limiting', 'needs_normalization']
        
        for key in required_keys:
            assert key in analysis
        
        # 檢查分析結果的合理性
        assert 0 <= analysis['rms'] <= 1
        assert -100 <= analysis['rms_db'] <= 0
        assert 0 <= analysis['peak_level'] <= 1
        assert isinstance(analysis['has_clipping'], (bool, np.bool_))  # 允許 numpy bool
        assert analysis['dynamic_range'] > 0
        
        # 測試安靜音訊
        quiet_analysis = enhancer._analyze_audio(quiet_audio)
        assert quiet_analysis['needs_gain'] == True
        assert quiet_analysis['needs_normalization'] == True
        
        # 測試大聲音訊
        loud_analysis = enhancer._analyze_audio(loud_audio)
        assert loud_analysis['peak_level'] > 0.5
    
    def test_determine_pipeline(self, enhancer):
        """測試處理管線決策"""
        # 建立測試分析結果
        test_analysis = {
            'rms': 0.03, 'rms_db': -30, 'peak_level': 0.9, 'snr_db': 25,
            'has_clipping': False, 'dynamic_range': 20,
            'needs_gain': True, 'needs_compression': True,
            'needs_limiting': True, 'needs_normalization': True,
            'needs_denoising': False
        }
        
        # 測試不同用途的管線
        asr_pipeline = enhancer._determine_pipeline(test_analysis, "asr")
        vad_pipeline = enhancer._determine_pipeline(test_analysis, "vad")
        recording_pipeline = enhancer._determine_pipeline(test_analysis, "recording")
        
        # ASR 管線應該最完整
        asr_steps = [step['name'] for step in asr_pipeline]
        assert 'dc_offset' in asr_steps
        assert 'highpass' in asr_steps
        assert len(asr_pipeline) >= 2
        
        # VAD 管線應該最簡單
        vad_steps = [step['name'] for step in vad_pipeline]
        assert 'dc_offset' in vad_steps
        assert 'highpass' in vad_steps
        assert len(vad_pipeline) <= 3
        
        # 錄音管線在此例中應該很簡單（沒有削波）
        rec_steps = [step['name'] for step in recording_pipeline]
        assert 'dc_offset' in rec_steps
    
    def test_auto_enhance_disabled(self, enhancer):
        """測試 AudioEnhancer 停用時的智慧處理"""
        # 暫時停用
        original_enabled = enhancer.enabled
        enhancer.enabled = False
        
        try:
            audio_bytes = b'\x00' * 3200  # 1600 samples
            processed_bytes, report = enhancer.auto_enhance(audio_bytes, "asr")
            
            # 應該返回原始音訊和空報告
            assert processed_bytes == audio_bytes
            assert report['applied_steps'] == []
            assert report['purpose'] == 'asr'
            
        finally:
            enhancer.enabled = original_enabled