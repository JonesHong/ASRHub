"""
音訊增強服務 - Phase 3 完整版本
包含智慧處理系統和進階工具
"""
import numpy as np
from typing import Optional, Dict, Any
from src.utils.logger import logger
from src.config.manager import ConfigManager
from src.utils.singleton import SingletonMixin


class AudioEnhancer(SingletonMixin):
    """音訊增強工具箱 - 提供完整的音訊處理功能
    
    Phase 3 完整版本功能：
    - 基礎工具：DC offset、高通濾波、增益調整
    - 進階工具：動態壓縮、軟限幅器、噪音門、均衡器
    - 智慧處理系統：auto_enhance() 自動分析並決定處理流程
    - 音訊分析：RMS、峰值、SNR、動態範圍分析
    - 多種預設配方：VAD、ASR、WakeWord、Recording
    - 完整配置管理整合
    
    使用方式：
    # 新手模式：一行搞定
    processed, report = audio_enhancer.auto_enhance(audio_bytes, "asr")
    
    # 專家模式：直接使用工具
    audio = audio_enhancer.apply_compression(audio, threshold=-20, ratio=2.5)
    """
    
    def __init__(self):
        """初始化"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_config()
            logger.info("🎛️ AudioEnhancer 服務初始化完成")
    
    def _load_config(self):
        """載入配置"""
        config = ConfigManager()
        
        # 檢查是否啟用
        if not config.services.audio_enhancer.enabled:
            logger.warning("⚠️ AudioEnhancer 服務已停用")
            self.enabled = False
            return
        
        self.enabled = True
        
        # 音訊增強配置 - 現在直接在 audio_enhancer 層級
        enhancer_config = config.services.audio_enhancer
        self.min_rms_threshold = enhancer_config.min_rms_threshold
        self.target_rms = enhancer_config.target_rms
        self.max_gain = enhancer_config.max_gain
        self.highpass_alpha = enhancer_config.highpass_alpha
        self.limiter_threshold = enhancer_config.limiter_threshold
        
        # 預設配置 - 現在是 vad_enhancer 和 asr_enhancer
        self.vad_preset = enhancer_config.vad_enhancer
        self.asr_preset = enhancer_config.asr_enhancer
        
        logger.debug(f"AudioEnhancer 配置載入: target_rms={self.target_rms}, max_gain={self.max_gain}")
    
    # ========== MVP 基礎工具 ==========
    
    def remove_dc_offset(self, audio: np.ndarray) -> np.ndarray:
        """移除直流偏移
        
        Args:
            audio: 輸入音訊 (float32, -1.0 to 1.0)
            
        Returns:
            處理後音訊
        """
        mean_value = np.mean(audio)
        if abs(mean_value) > 0.01:  # 只在偏移明顯時處理
            logger.debug(f"移除 DC 偏移: {mean_value:.4f}")
            return audio - mean_value
        return audio
    
    def apply_highpass_simple(self, audio: np.ndarray, alpha: Optional[float] = None) -> np.ndarray:
        """簡單高通濾波器 - 使用一階差分
        
        這是最簡單的實作，不依賴 scipy
        
        Args:
            audio: 輸入音訊
            alpha: 濾波係數 (0.9-0.99, 越大截止頻率越低)，None 則使用配置值
            
        Returns:
            濾波後音訊
        """
        if alpha is None:
            alpha = self.highpass_alpha
            
        # 簡單的一階高通濾波器
        filtered = np.zeros_like(audio)
        filtered[0] = audio[0]
        
        for i in range(1, len(audio)):
            filtered[i] = alpha * (filtered[i-1] + audio[i] - audio[i-1])
        
        return filtered
    
    def apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        """應用增益
        
        Args:
            audio: 輸入音訊
            gain_db: 增益值 (dB)，正值放大，負值衰減
            
        Returns:
            處理後音訊
        """
        # 限制增益範圍避免極端值
        gain_db = np.clip(gain_db, -40, 20)
        gain_linear = 10 ** (gain_db / 20.0)
        
        logger.debug(f"應用增益: {gain_db:.1f} dB (x{gain_linear:.2f})")
        return audio * gain_linear
    
    def apply_hard_limiter(self, audio: np.ndarray, threshold: Optional[float] = None) -> np.ndarray:
        """硬限幅器 - 最簡單的削波防護
        
        Args:
            audio: 輸入音訊
            threshold: 限幅閾值 (0.0-1.0)，None 則使用配置值
            
        Returns:
            限幅後音訊
        """
        if threshold is None:
            threshold = self.limiter_threshold
            
        # 計算削波前的狀況
        clipping_count = np.sum(np.abs(audio) > threshold)
        
        if clipping_count > 0:
            clipping_rate = clipping_count / len(audio) * 100
            if clipping_rate > 1.0:
                logger.warning(f"⚠️ 削波率: {clipping_rate:.1f}%")
        
        # 硬限幅
        return np.clip(audio, -threshold, threshold)
    
    def calculate_rms(self, audio: np.ndarray) -> float:
        """計算 RMS (Root Mean Square)
        
        Args:
            audio: 輸入音訊
            
        Returns:
            RMS 值
        """
        return np.sqrt(np.mean(audio ** 2))
    
    def normalize_rms(self, audio: np.ndarray, target_rms: Optional[float] = None) -> np.ndarray:
        """標準化 RMS 到目標值
        
        Args:
            audio: 輸入音訊  
            target_rms: 目標 RMS，None 則使用配置值
            
        Returns:
            標準化後音訊
        """
        if target_rms is None:
            target_rms = self.target_rms
            
        current_rms = self.calculate_rms(audio)
        
        # 避免除零
        if current_rms < 0.0001:
            logger.debug("音訊太安靜，跳過標準化")
            return audio
        
        # 計算增益
        gain = target_rms / current_rms
        
        # 限制最大增益避免過度放大
        gain = min(gain, self.max_gain)
        
        logger.debug(f"RMS 標準化: {current_rms:.4f} → {target_rms:.4f} (增益 x{gain:.2f})")
        
        return audio * gain
    
    # ========== 簡單預設組合 (MVP) ==========
    
    def enhance_for_vad(self, audio_bytes: bytes) -> bytes:
        """VAD 處理預設 - 最小處理
        
        只做最基本的清理，保持原始特徵
        
        Args:
            audio_bytes: 16kHz, mono, int16 格式
            
        Returns:
            處理後的音訊
        """
        if not self.enabled:
            return audio_bytes
            
        # 轉換為 float32
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # 根據配置處理
        if self.vad_preset.dc_remove:
            audio = self.remove_dc_offset(audio)
        if self.vad_preset.highpass:
            audio = self.apply_highpass_simple(audio)
        if self.vad_preset.normalize:
            audio = self.normalize_rms(audio)
        if self.vad_preset.limit:
            audio = self.apply_hard_limiter(audio)
        
        # 轉回 int16
        return (audio * 32768).astype(np.int16).tobytes()
    
    def enhance_for_asr(self, audio_bytes: bytes) -> bytes:
        """ASR 處理預設 - 智能增強
        
        包含標準化和限幅保護，根據音量決定是否處理
        
        Args:
            audio_bytes: 16kHz, mono, int16 格式
            
        Returns:
            處理後的音訊
        """
        if not self.enabled:
            return audio_bytes
            
        # 轉換為 float32
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # 檢查是否需要增強
        current_rms = self.calculate_rms(audio)
        
        # 如果音量已經足夠，跳過處理
        if current_rms >= self.min_rms_threshold:
            logger.debug(f"音量足夠 (RMS={current_rms:.3f})，跳過增強")
            return audio_bytes
        
        # 根據配置處理
        if self.asr_preset.dc_remove:
            audio = self.remove_dc_offset(audio)
        if self.asr_preset.highpass:
            audio = self.apply_highpass_simple(audio)
        if self.asr_preset.normalize:
            audio = self.normalize_rms(audio)
        if self.asr_preset.limit:
            audio = self.apply_hard_limiter(audio)
        
        # 轉回 int16
        return (audio * 32768).astype(np.int16).tobytes()
    
    def enhance_for_wakeword(self, audio_bytes: bytes) -> bytes:
        """WakeWord 處理預設 - 與 VAD 相同"""
        return self.enhance_for_vad(audio_bytes)
    
    def enhance_for_recording(self, audio_bytes: bytes) -> bytes:
        """Recording 處理預設 - 保持原始品質
        
        只做最小清理，保留動態範圍
        """
        if not self.enabled:
            return audio_bytes
            
        # 轉換為 float32
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # 只做 DC 移除
        audio = self.remove_dc_offset(audio)
        
        # 轉回 int16
        return (audio * 32768).astype(np.int16).tobytes()
    
    # ========== 進階處理工具 ==========
    
    def apply_compression(self, 
                         audio: np.ndarray, 
                         threshold: float = -20,
                         ratio: float = 2.5,
                         attack_ms: float = 5,
                         release_ms: float = 50) -> np.ndarray:
        """動態範圍壓縮
        
        簡化實作，適合即時處理
        
        Args:
            audio: 輸入音訊
            threshold: 壓縮閾值 (dBFS)
            ratio: 壓縮比 (例如 2.5:1)
            attack_ms: 起音時間 (毫秒)，目前未實作
            release_ms: 釋放時間 (毫秒)，目前未實作
            
        Returns:
            壓縮後音訊
        """
        # 轉換閾值到線性值
        threshold_linear = 10 ** (threshold / 20.0)
        
        # 計算音訊包絡 (簡化版，使用滑動RMS)
        window_size = min(512, len(audio) // 4)
        envelope = np.zeros_like(audio)
        
        for i in range(len(audio)):
            start = max(0, i - window_size // 2)
            end = min(len(audio), i + window_size // 2)
            envelope[i] = np.sqrt(np.mean(audio[start:end] ** 2))
        
        # 計算增益縮減
        gain_reduction = np.ones_like(audio)
        over_threshold = envelope > threshold_linear
        
        if np.any(over_threshold):
            # 對超過閾值的部分應用壓縮
            over_amount = envelope[over_threshold] / threshold_linear
            compressed_gain = (over_amount ** (1/ratio - 1))
            gain_reduction[over_threshold] = compressed_gain
            
            logger.debug(f"壓縮器: 閾值={threshold}dBFS, 比例={ratio}:1, 影響樣本={np.sum(over_threshold)}")
        
        return audio * gain_reduction
    
    def apply_limiter(self, 
                     audio: np.ndarray,
                     ceiling: float = 0.891,  # -1 dBFS
                     lookahead_ms: float = 5,
                     release_ms: float = 50) -> np.ndarray:
        """限幅器 - 防止削波
        
        簡化實作，適合即時處理。未來可實作真正的 lookahead。
        
        Args:
            audio: 輸入音訊
            ceiling: 峰值上限
            lookahead_ms: 前瞻時間 (目前未實作)
            release_ms: 釋放時間 (目前未實作)
            
        Returns:
            限幅後音訊
        """
        # 檢測削波情況
        peaks_over = np.abs(audio) > ceiling
        clipping_rate = np.sum(peaks_over) / len(audio)
        
        if clipping_rate > 0.01:  # 超過 1%
            logger.warning(f"⚠️ 限幅器介入，削波率: {clipping_rate:.1%}")
        
        # 軟限幅 - 使用 tanh 避免硬削波的失真
        limited = np.where(
            np.abs(audio) > ceiling,
            ceiling * np.tanh(audio / ceiling),
            audio
        )
        
        return limited
    
    def apply_gate(self, audio: np.ndarray, threshold: float = -40) -> np.ndarray:
        """噪音門 - 低於閾值時衰減
        
        Args:
            audio: 輸入音訊
            threshold: 門檻值 (dBFS)
            
        Returns:
            處理後音訊
        """
        # 計算滑動 RMS
        window_size = min(1024, len(audio) // 8)
        rms_envelope = np.zeros_like(audio)
        
        for i in range(len(audio)):
            start = max(0, i - window_size // 2)
            end = min(len(audio), i + window_size // 2)
            rms_envelope[i] = np.sqrt(np.mean(audio[start:end] ** 2))
        
        # 轉換閾值到線性值
        threshold_linear = 10 ** (threshold / 20.0)
        
        # 應用門限，使用平滑過渡避免突變
        gate_gain = np.where(
            rms_envelope > threshold_linear,
            1.0,  # 開門
            0.1   # 關門 (衰減而非完全靜音)
        )
        
        # 平滑增益變化
        smoothed_gain = np.copy(gate_gain)
        for i in range(1, len(smoothed_gain)):
            smoothed_gain[i] = 0.9 * smoothed_gain[i-1] + 0.1 * gate_gain[i]
        
        gated_samples = np.sum(gate_gain < 0.5)
        if gated_samples > 0:
            gate_ratio = gated_samples / len(audio)
            logger.debug(f"噪音門: 閾值={threshold}dBFS, 門控比例={gate_ratio:.1%}")
        
        return audio * smoothed_gain
    
    def apply_eq(self, audio: np.ndarray, bands: Dict[float, float]) -> np.ndarray:
        """簡易均衡器
        
        Args:
            audio: 輸入音訊
            bands: {freq_hz: gain_db} 頻段調整
            
        Returns:
            均衡後音訊
        """
        # TODO: 實作多頻段 EQ
        # 這需要 FFT 或濾波器組，目前先返回原始音訊
        logger.debug(f"EQ 處理: {len(bands)} 個頻段 (簡化實作)")
        return audio
    
    # ========== 智慧處理系統 (Auto Intelligent Processing) ==========
    
    def auto_enhance(self, audio_bytes: bytes, purpose: str = "asr") -> tuple[bytes, dict]:
        """智慧音訊處理 - 根據音訊特徵自動決定處理流程
        
        這個功能專為不熟悉音訊處理的開發者設計，
        自動分析音訊並選擇最佳處理組合。
        
        Args:
            audio_bytes: 輸入音訊（16kHz, mono, int16）
            purpose: 用途 - "asr", "vad", "wakeword", "recording", "general"
        
        Returns:
            (processed_audio, analysis_report) 處理後音訊與分析報告
        """
        if not self.enabled:
            return audio_bytes, {"analysis": {}, "decisions": {}, "applied_steps": [], "purpose": purpose}
            
        # 轉換為浮點數進行分析
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # ========== Step 1: 音訊特徵分析 ==========
        analysis = self._analyze_audio(audio)
        
        # ========== Step 2: 決定處理策略 ==========
        pipeline = self._determine_pipeline(analysis, purpose)
        
        # ========== Step 3: 依序執行處理 ==========
        processed = audio.copy()
        applied_steps = []
        
        for step in pipeline:
            try:
                if step['name'] == 'dc_offset':
                    processed = self.remove_dc_offset(processed)
                    applied_steps.append("DC Offset 移除")
                    
                elif step['name'] == 'highpass':
                    processed = self.apply_highpass_simple(processed)
                    applied_steps.append(f"高通濾波")
                    
                elif step['name'] == 'gate':
                    if analysis['rms_db'] < step['threshold']:
                        processed = self.apply_gate(processed, threshold=step['threshold'])
                        applied_steps.append(f"噪音門 (閾值: {step['threshold']}dB)")
                        
                elif step['name'] == 'gain':
                    if analysis['needs_gain']:
                        gain_db = step['gain_db']
                        processed = self.apply_gain(processed, gain_db=gain_db)
                        applied_steps.append(f"增益調整 (+{gain_db:.1f}dB)")
                        
                elif step['name'] == 'normalize':
                    if analysis['needs_normalization']:
                        processed = self.normalize_rms(processed, target_rms=step['target_rms'])
                        applied_steps.append(f"RMS 標準化 (目標: {step['target_rms']:.3f})")
                        
                elif step['name'] == 'compression':
                    if analysis['needs_compression']:
                        processed = self.apply_compression(
                            processed,
                            threshold=step['threshold'],
                            ratio=step['ratio']
                        )
                        applied_steps.append(f"動態壓縮 ({step['ratio']}:1)")
                        
                elif step['name'] == 'limiter':
                    if analysis['peak_level'] > 0.8 or analysis['needs_limiting']:
                        processed = self.apply_limiter(processed, ceiling=step['ceiling'])
                        applied_steps.append(f"峰值限制 ({step['ceiling']:.3f})")
                        
            except Exception as e:
                logger.warning(f"⚠️ 處理步驟失敗 {step['name']}: {e}")
                continue
        
        # ========== Step 4: 生成分析報告 ==========
        report = {
            'analysis': {
                'rms': f"{analysis['rms']:.4f}",
                'rms_db': f"{analysis['rms_db']:.1f} dBFS",
                'peak_level': f"{analysis['peak_level']:.3f}",
                'dc_offset': f"{analysis['dc_offset']:.5f}",
                'snr_estimate': f"{analysis['snr_db']:.1f} dB",
                'clipping_detected': bool(analysis['has_clipping'])  # 確保是 Python bool
            },
            'decisions': {
                'needs_gain': bool(analysis['needs_gain']),
                'needs_compression': bool(analysis['needs_compression']),
                'needs_limiting': bool(analysis['needs_limiting']),
                'needs_normalization': bool(analysis['needs_normalization']),
                'needs_denoising': bool(analysis['needs_denoising'])
            },
            'applied_steps': applied_steps,
            'purpose': purpose
        }
        
        # 轉回 int16
        processed_bytes = (processed * 32768).astype(np.int16).tobytes()
        
        return processed_bytes, report
    
    def _analyze_audio(self, audio: np.ndarray) -> dict:
        """分析音訊特徵"""
        # RMS 能量
        rms = np.sqrt(np.mean(audio ** 2))
        rms_db = 20 * np.log10(rms + 1e-10)
        
        # 峰值
        peak_level = np.max(np.abs(audio))
        
        # DC 偏移
        dc_offset = np.mean(audio)
        
        # 簡易 SNR 估計（使用靜音段估計噪聲）
        sorted_rms = np.sort(np.abs(audio))
        noise_floor = np.mean(sorted_rms[:len(sorted_rms)//10])  # 最小 10% 作為噪聲
        snr_db = 20 * np.log10((rms + 1e-10) / (noise_floor + 1e-10))
        
        # 檢測削波
        has_clipping = np.any(np.abs(audio) >= 0.99)
        
        # 動態範圍
        dynamic_range = peak_level / (rms + 1e-10)
        
        # 決策邏輯（調整為較保守的閾值）
        needs_gain = rms < 0.01  # < -40 dBFS（只在極小聲時增益）
        needs_compression = dynamic_range > 20  # 動態範圍過大（提高閾值）
        needs_limiting = peak_level > 0.95 or has_clipping  # 只在接近削波時限幅
        needs_normalization = rms < 0.03  # < -30 dBFS（更保守的正規化）
        needs_denoising = snr_db < 10  # SNR 太低（更保守的降噪閾值）
        
        return {
            'rms': rms,
            'rms_db': rms_db,
            'peak_level': peak_level,
            'dc_offset': dc_offset,
            'snr_db': snr_db,
            'has_clipping': has_clipping,
            'dynamic_range': dynamic_range,
            'needs_gain': needs_gain,
            'needs_compression': needs_compression,
            'needs_limiting': needs_limiting,
            'needs_normalization': needs_normalization,
            'needs_denoising': needs_denoising
        }
    
    def _determine_pipeline(self, analysis: dict, purpose: str) -> list:
        """根據分析結果決定處理管線
        
        處理順序很重要！一般順序：
        1. DC Offset 移除（基礎清理）
        2. 高通濾波（移除低頻噪音）
        3. 噪音門（移除背景噪音）
        4. 增益/標準化（調整音量）
        5. 壓縮（控制動態範圍）
        6. 限幅（防止削波）
        """
        pipeline = []
        
        # 基礎清理（所有用途都需要）
        pipeline.append({'name': 'dc_offset'})
        
        if purpose in ['asr', 'vad', 'wakeword']:
            pipeline.append({'name': 'highpass'})
        
        # 根據用途決定處理強度
        if purpose == 'vad' or purpose == 'wakeword':
            # VAD/WakeWord：最小處理，保持原始特徵
            pass  # 只做基礎清理
            
        elif purpose == 'asr':
            # ASR：保守處理，避免失真
            
            # 噪音門（只在噪音太大時）
            if analysis['snr_db'] < 10:  # 更保守的閾值
                pipeline.append({
                    'name': 'gate',
                    'threshold': -45  # 更低的閾值，避免切斷語音
                })
            
            # 增益調整（只在極小聲時）
            if analysis['needs_normalization']:
                if analysis['rms'] < 0.01:  # 極小聲（< -40 dBFS）
                    pipeline.append({
                        'name': 'gain',
                        'gain_db': min(10, -analysis['rms_db'] - 25)  # 目標 -25 dBFS，最大增益 10dB
                    })
                elif analysis['rms'] < 0.03:  # 小聲（< -30 dBFS）
                    pipeline.append({
                        'name': 'normalize',
                        'target_rms': 0.08  # -22 dBFS，更保守的目標
                    })
            
            # 動態壓縮（只在動態範圍極大時）
            if analysis['needs_compression'] and analysis['dynamic_range'] > 25:  # 提高閾值
                pipeline.append({
                    'name': 'compression',
                    'threshold': -25,  # 更低的閾值
                    'ratio': 2.0  # 更輕的壓縮比
                })
            
            # 限幅器（只在接近削波時）
            if analysis['needs_limiting'] or analysis['peak_level'] > 0.9:  # 更高的閾值
                pipeline.append({
                    'name': 'limiter',
                    'ceiling': 0.95  # -0.4 dBFS，更寬鬆的上限
                })
                
        elif purpose == 'recording':
            # 錄音：保持原始品質，只做必要保護
            if analysis['has_clipping']:
                pipeline.append({
                    'name': 'limiter',
                    'ceiling': 0.95  # 較高的上限，保留動態
                })
                
        elif purpose == 'general':
            # 一般用途：平衡處理
            
            # 適度增益
            if analysis['rms'] < 0.05:
                pipeline.append({
                    'name': 'normalize',
                    'target_rms': 0.1  # -20 dBFS，較保守
                })
            
            # 適度壓縮
            if analysis['dynamic_range'] > 20:
                pipeline.append({
                    'name': 'compression',
                    'threshold': -24,
                    'ratio': 2.0  # 較輕的壓縮
                })
            
            # 防止削波
            if analysis['peak_level'] > 0.85:
                pipeline.append({
                    'name': 'limiter',
                    'ceiling': 0.95
                })
        
        return pipeline


# 模組級單例
audio_enhancer = AudioEnhancer()