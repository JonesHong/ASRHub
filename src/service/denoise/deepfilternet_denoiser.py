#!/usr/bin/env python3
"""
DeepFilterNet - 音訊降噪服務
使用 DeepFilterNet 進行深度學習音訊降噪處理

設計原則:
- KISS: Keep It Simple, Stupid - 簡單有效的設計
- 無狀態: 所有方法都是純函數，無內部狀態依賴  
- 單一職責: 專門負責音訊降噪處理
- 單例模式: 實現模組級單例
- 直接調用: 可被 Effects 直接調用
"""

import numpy as np
from typing import Optional, Tuple, Union, Dict, Any, TYPE_CHECKING
from threading import Lock
import warnings

from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin

# 讓 torch 變為可選依賴
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("PyTorch not installed. DeepFilterNet will not be available.")

# 用於類型提示
if TYPE_CHECKING:
    import torch


class DeepFilterNetDenoiser(SingletonMixin):
    """
    DeepFilterNet 降噪器 - 基於 DeepFilterNet 的深度學習降噪
    
    特色:
    - 🧠 智慧降噪 - auto_denoise() 自動分析音訊並決定降噪強度
    - 🎯 精準控制 - denoise() 提供精確的降噪強度控制
    - ⚡ 高效能 - 基於 DeepFilterNet 的最新深度學習技術
    - 🔧 靈活配置 - 支援多種降噪模式和參數調整
    - 📊 詳細報告 - 提供降噪處理的詳細分析報告
    """
    
    _init_lock = Lock()
    
    def _get_device(self, requested_device: str = 'auto') -> str:
        """
        獲取最佳可用設備
        
        參考 DeepFilterNet utils.py:20-29
        
        Args:
            requested_device: 請求的設備 ('auto', 'cuda', 'cpu')
            
        Returns:
            設備字符串 ('cuda' 或 'cpu')
        """
        if not HAS_TORCH:
            return 'cpu'
            
        # 根據配置決定設備
        if requested_device == 'cpu':
            return 'cpu'
        elif requested_device == 'cuda':
            if torch.cuda.is_available():
                return 'cuda'
            else:
                logger.warning("請求使用 CUDA 但不可用，回退到 CPU")
                return 'cpu'
        else:  # auto
            if torch.cuda.is_available():
                logger.debug(f"自動選擇 CUDA 設備: {torch.cuda.get_device_name(0)}")
                return 'cuda'
            else:
                logger.debug("自動選擇 CPU 設備")
                return 'cpu'
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        with self._init_lock:
            if hasattr(self, '_initialized'):
                return
                
            self._initialized = True
            self._model = None
            self._df_state = None
            self.internal_sample_rate = 48000  # DeepFilterNet 內部處理採樣率
            self.supports_16khz_io = True  # 支援 16kHz 輸入/輸出，內部自動轉換
            self._model_initialized = False
            
            # 載入配置
            self._load_config()
            
            # 初始化 DeepFilterNet 模型 (延遲初始化)
            if self.enabled and self.auto_init and HAS_TORCH:
                try:
                    self._initialize_model()
                except Exception as e:
                    logger.warning(f"🔧 DeepFilterNet 模型初始化失敗，將在首次使用時重試: {e}")
            elif self.enabled and not HAS_TORCH:
                logger.warning("⚠️ DeepFilterNet 需要 PyTorch，但 PyTorch 未安裝。降噪功能將被停用。")
                self.enabled = False
                    
            logger.info("🔇 DeepFilterNet 服務初始化完成")
    
    def _load_config(self):
        """載入降噪服務配置"""
        config = ConfigManager()
        denoiser_config = config.services.denoiser
        
        self.enabled = denoiser_config.enabled
        self.type = denoiser_config.type
        self.strength = denoiser_config.strength
        
        # 擴展配置以支援 DeepFilterNet
        if hasattr(denoiser_config, 'deepfilternet'):
            dfn_config = denoiser_config.deepfilternet
            self.model_base_dir = dfn_config.model_base_dir if hasattr(dfn_config, 'model_base_dir') else "DeepFilterNet3"
            self.post_filter = dfn_config.post_filter if hasattr(dfn_config, 'post_filter') else True
            self.auto_init = dfn_config.auto_init if hasattr(dfn_config, 'auto_init') else True
            self.device = dfn_config.device if hasattr(dfn_config, 'device') else 'auto'  # auto, cpu, cuda
            self.chunk_size = dfn_config.chunk_size if hasattr(dfn_config, 'chunk_size') else 16000  # 1秒音訊塊
        else:
            # 預設配置
            self.model_base_dir = "DeepFilterNet3"
            self.post_filter = True
            self.auto_init = True
            self.device = 'auto'
            self.chunk_size = 16000
            
        # 使用改進的設備選擇邏輯
        # 保存原始配置值
        requested_device = self.device
        # 獲取實際使用的設備
        self.device = self._get_device(requested_device)
            
        logger.debug(f"DeepFilterNet 配置載入: enabled={self.enabled}, type={self.type}, device={self.device}")
    
    def _initialize_model(self):
        """初始化 DeepFilterNet 模型"""
        if self._model_initialized:
            return
        
        if not HAS_TORCH:
            logger.warning("Cannot initialize DeepFilterNet model: PyTorch not installed")
            self.enabled = False
            return
            
        try:
            # 動態導入 DeepFilterNet (避免在未安裝時出錯)
            from df.enhance import init_df
            
            logger.info(f"🔧 正在初始化 DeepFilterNet 模型: {self.model_base_dir}")
            
            # 初始化模型
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # 抑制 DeepFilterNet 的警告
                
                # init_df 返回 3 個值：model, df_state, sample_rate
                self._model, self._df_state, self._sr = init_df(
                    model_base_dir=self.model_base_dir,
                    post_filter=self.post_filter,
                    log_level="WARNING"
                )
            
            # 設定設備
            if self.device == 'cuda' and torch.cuda.is_available():
                self._model = self._model.cuda()
                logger.info("🚀 DeepFilterNet 模型已載入到 GPU")
            else:
                self._model = self._model.cpu()
                logger.info("💻 DeepFilterNet 模型已載入到 CPU")
                
            self._model_initialized = True
            logger.info("✅ DeepFilterNet 模型初始化完成")
            
        except ImportError:
            raise ImportError(
                "DeepFilterNet 未安裝。請使用 'pip install deepfilternet' 安裝"
            )
        except Exception as e:
            logger.error(f"❌ DeepFilterNet 模型初始化失敗: {e}")
            raise
    
    def _ensure_model_ready(self):
        """確保模型已準備就緒"""
        if not self.enabled:
            raise RuntimeError("DeepFilterNet 未啟用")
            
        if not self._model_initialized:
            self._initialize_model()
    
    def denoise(self, audio_data: Union[bytes, np.ndarray], 
               strength: Optional[float] = None,
               sample_rate: int = 16000) -> Union[bytes, np.ndarray]:
        """
        音訊降噪處理
        
        Args:
            audio_data: 音訊資料 (bytes 或 numpy array)
            strength: 降噪強度 (0.0-1.0)，None 則使用配置值
            sample_rate: 取樣率，預設 16kHz
            
        Returns:
            降噪後的音訊資料，與輸入格式相同
            
        Raises:
            RuntimeError: 當服務未啟用或模型初始化失敗時
            ValueError: 當音訊資料格式不正確時
        """
        self._ensure_model_ready()
        
        # 處理輸入格式
        input_is_bytes = isinstance(audio_data, bytes)
        if input_is_bytes:
            audio = self._bytes_to_audio(audio_data)
        else:
            audio = audio_data.astype(np.float32)
            
        # 驗證音訊格式
        if audio.ndim != 1:
            raise ValueError("目前只支援單聲道音訊")
            
        if len(audio) == 0:
            logger.warning("收到空的音訊資料")
            return audio_data
            
        # 使用指定強度或配置值
        if strength is None:
            strength = self.strength
        strength = max(0.0, min(1.0, strength))  # 限制在 0-1 範圍
        
        try:
            # 使用 DeepFilterNet 處理 (自動處理採樣率轉換)
            enhanced_audio = self._process_with_deepfilternet(audio, strength, sample_rate)
            
            # 返回相同格式
            if input_is_bytes:
                return self._audio_to_bytes(enhanced_audio)
            else:
                return enhanced_audio
                
        except Exception as e:
            logger.error(f"❌ 降噪處理失敗: {e}")
            # 降噪失敗時返回原始音訊
            return audio_data
    
    def auto_denoise(self, audio_data: Union[bytes, np.ndarray],
                    purpose: str = "asr",
                    sample_rate: int = 16000) -> Tuple[Union[bytes, np.ndarray], Dict[str, Any]]:
        """
        智慧音訊降噪 - 自動分析音訊並決定最佳降噪策略
        
        Args:
            audio_data: 音訊資料 (bytes 或 numpy array)
            purpose: 用途 ("asr", "vad", "wakeword", "recording", "general")
            sample_rate: 取樣率，預設 16kHz
            
        Returns:
            Tuple[處理後音訊, 分析報告]
            
        分析報告包含:
        - purpose: 處理用途
        - analysis: 音訊分析結果
        - decisions: 降噪決策
        - applied_steps: 執行的處理步驟
        - performance: 效能指標
        """
        self._ensure_model_ready()
        
        # 處理輸入格式
        input_is_bytes = isinstance(audio_data, bytes)
        if input_is_bytes:
            audio = self._bytes_to_audio(audio_data)
        else:
            audio = audio_data.astype(np.float32)
            
        # 驗證音訊格式
        if len(audio) == 0:
            return audio_data, self._empty_report(purpose)
            
        import time
        start_time = time.time()
        
        try:
            # 1. 音訊分析
            analysis = self._analyze_audio(audio)
            
            # 2. 決定處理策略
            decisions = self._determine_denoise_strategy(analysis, purpose)
            
            # 3. 執行降噪處理
            processed_audio, applied_steps = self._execute_denoise_pipeline(
                audio, decisions, sample_rate
            )
            
            # 4. 性能統計
            processing_time = (time.time() - start_time) * 1000  # 毫秒
            
            # 5. 生成報告
            report = {
                'purpose': purpose,
                'analysis': {
                    'snr_estimate': f"{analysis['snr_db']:.1f} dB",
                    'noise_level': analysis['noise_level'],
                    'spectral_centroid': f"{analysis['spectral_centroid']:.0f} Hz",
                    'zero_crossing_rate': f"{analysis['zcr']:.3f}",
                    'rms_energy': f"{analysis['rms']:.4f}",
                    'needs_denoising': analysis['needs_denoising']
                },
                'decisions': decisions,
                'applied_steps': applied_steps,
                'performance': {
                    'processing_time_ms': f"{processing_time:.2f}",
                    'enhancement_strength': decisions.get('strength', 0.0),
                    'snr_improvement': f"{analysis.get('expected_snr_gain', 0):.1f} dB"
                }
            }
            
            # 返回結果
            result = self._audio_to_bytes(processed_audio) if input_is_bytes else processed_audio
            return result, report
            
        except Exception as e:
            logger.error(f"❌ 智慧降噪處理失敗: {e}")
            return audio_data, self._error_report(purpose, str(e))
    
    def _as_numpy(self, tensor) -> np.ndarray:
        """安全地將 PyTorch tensor 轉換為 numpy array
        
        根據 DeepFilterNet 官方實現，使用 cpu().detach().numpy() 序列
        參考: evaluation_utils.py:622-625
        
        Args:
            tensor: PyTorch tensor 或 numpy array
            
        Returns:
            numpy array
        """
        if HAS_TORCH and torch is not None:
            if isinstance(tensor, torch.Tensor):
                # 根據 DeepFilterNet 官方: 先 cpu() 再 detach() 最後 numpy()
                return tensor.cpu().detach().numpy()
        return tensor
    
    def _process_with_deepfilternet(self, audio: np.ndarray, strength: float, 
                                  input_sample_rate: int = 16000) -> np.ndarray:
        """使用 DeepFilterNet 處理音訊
        
        Args:
            audio: 輸入音訊 (16kHz)
            strength: 降噪強度 (0.0-1.0)
            input_sample_rate: 輸入採樣率，預設 16kHz
            
        Returns:
            處理後的音訊，保持與輸入相同的採樣率
        """
        try:
            from df.enhance import enhance
            from df.io import resample
            
            # 轉換為 PyTorch 張量
            audio_tensor = torch.from_numpy(audio).unsqueeze(0)  # 加入 batch 維度
            
            # === 1. 上採樣到 48kHz (如果需要) ===
            if input_sample_rate != self.internal_sample_rate:
                logger.debug(f"上採樣音訊: {input_sample_rate}Hz → {self.internal_sample_rate}Hz")
                # 使用新的重採樣方法避免棄用警告
                audio_tensor = resample(
                    audio_tensor, 
                    orig_sr=input_sample_rate, 
                    new_sr=self.internal_sample_rate,
                    method="sinc_fast"  # 使用 sinc_fast 以獲得最佳的速度與品質平衡
                )
            
            # if self.device == 'cuda':
            #     audio_tensor = audio_tensor.cuda()
                
            # === 2. DeepFilterNet 增強處理 (48kHz) ===
            with torch.no_grad():
                enhanced_tensor = enhance(self._model, self._df_state, audio_tensor, pad=True)
            
            # 確保 enhanced_tensor 在 CPU 上（enhance 可能返回 CUDA tensor）
            # 使用 isinstance 檢查更可靠
            if torch is not None and isinstance(enhanced_tensor, torch.Tensor):
                if enhanced_tensor.is_cuda:
                    enhanced_tensor = enhanced_tensor.cpu()
                
            # === 3. 下採樣回原始採樣率 (如果需要) ===
            if input_sample_rate != self.internal_sample_rate:
                logger.debug(f"下採樣音訊: {self.internal_sample_rate}Hz → {input_sample_rate}Hz")
                enhanced_tensor = resample(
                    enhanced_tensor, 
                    orig_sr=self.internal_sample_rate, 
                    new_sr=input_sample_rate,
                    method="sinc_fast"  # 使用 sinc_fast 以獲得最佳的速度與品質平衡
                )
                
                # resample 後可能又返回 CUDA tensor，需要再次檢查
                if torch is not None and isinstance(enhanced_tensor, torch.Tensor):
                    if enhanced_tensor.is_cuda:
                        enhanced_tensor = enhanced_tensor.cpu()
            
            # 轉換回 numpy (使用 _as_numpy utility function)
            # 這會自動處理任何剩餘的 CUDA tensors 和計算圖分離
            enhanced_audio = self._as_numpy(enhanced_tensor).squeeze(0)
            
            # 根據強度混合原始和降噪音訊
            if strength < 1.0:
                enhanced_audio = audio * (1 - strength) + enhanced_audio * strength
                
            return enhanced_audio.astype(np.float32)
            
        except RuntimeError as e:
            # 特別處理 CUDA 相關錯誤
            if "cuda" in str(e).lower() or "gpu" in str(e).lower():
                logger.error(f"DeepFilterNet CUDA 錯誤: {e}")
                logger.info("嘗試回退到 CPU 處理...")
                # 可以在這裡實現 CPU 回退邏輯
            else:
                logger.error(f"DeepFilterNet 運行時錯誤: {e}")
            return audio
        except Exception as e:
            logger.error(f"DeepFilterNet 處理失敗: {e}")
            import traceback
            logger.debug(f"錯誤追蹤:\n{traceback.format_exc()}")
            return audio
    
    def _analyze_audio(self, audio: np.ndarray) -> Dict[str, Any]:
        """分析音訊特徵，判斷降噪需求"""
        # 計算基本音訊特徵
        rms = np.sqrt(np.mean(audio ** 2))
        
        # 估算 SNR (簡化版本)
        # 使用前 10% 作為噪音基線估算
        noise_segment = audio[:len(audio)//10]
        noise_rms = np.sqrt(np.mean(noise_segment ** 2))
        signal_rms = rms
        
        if noise_rms > 0:
            snr_db = 20 * np.log10(signal_rms / noise_rms)
        else:
            snr_db = 60.0  # 假設高 SNR
            
        # 噪音等級評估
        if snr_db > 20:
            noise_level = "low"
        elif snr_db > 10:
            noise_level = "medium"
        else:
            noise_level = "high"
            
        # 頻譜重心 (簡化計算)
        fft = np.abs(np.fft.rfft(audio))
        freqs = np.linspace(0, 8000, len(fft))  # 16kHz 採樣率，奈奎斯特頻率 8kHz
        spectral_centroid = np.sum(freqs * fft) / (np.sum(fft) + 1e-10)
        
        # 過零率
        zero_crossings = np.where(np.diff(np.signbit(audio)))[0]
        zcr = len(zero_crossings) / len(audio)
        
        # 判斷是否需要降噪
        needs_denoising = snr_db < 15.0 or noise_level in ["medium", "high"]
        
        return {
            'rms': rms,
            'snr_db': snr_db,
            'noise_level': noise_level,
            'spectral_centroid': spectral_centroid,
            'zcr': zcr,
            'needs_denoising': needs_denoising,
            'expected_snr_gain': min(10.0, max(0.0, 20.0 - snr_db))  # 預期 SNR 改善
        }
    
    def _determine_denoise_strategy(self, analysis: Dict[str, Any], purpose: str) -> Dict[str, Any]:
        """根據分析結果和用途決定降噪策略"""
        decisions = {
            'apply_denoising': False,
            'strength': 0.0,
            'aggressive': False,
            'preserve_quality': True
        }
        
        if not analysis['needs_denoising']:
            return decisions
            
        # 根據用途調整策略
        if purpose == "asr":
            # ASR 需要最乾淨的音訊
            if analysis['noise_level'] == "high":
                decisions.update({
                    'apply_denoising': True,
                    'strength': min(0.8, self.strength + 0.2),
                    'aggressive': True,
                    'preserve_quality': False
                })
            elif analysis['noise_level'] == "medium":
                decisions.update({
                    'apply_denoising': True,
                    'strength': self.strength,
                    'aggressive': False,
                    'preserve_quality': True
                })
                
        elif purpose in ["vad", "wakeword"]:
            # VAD 和 WakeWord 需要保持特徵
            if analysis['noise_level'] == "high":
                decisions.update({
                    'apply_denoising': True,
                    'strength': max(0.3, self.strength - 0.2),
                    'aggressive': False,
                    'preserve_quality': True
                })
                
        elif purpose == "recording":
            # 錄音保持最少處理
            if analysis['noise_level'] == "high":
                decisions.update({
                    'apply_denoising': True,
                    'strength': max(0.2, self.strength - 0.3),
                    'aggressive': False,
                    'preserve_quality': True
                })
                
        else:  # general
            # 一般用途平衡處理
            if analysis['needs_denoising']:
                decisions.update({
                    'apply_denoising': True,
                    'strength': self.strength,
                    'aggressive': analysis['noise_level'] == "high",
                    'preserve_quality': True
                })
                
        return decisions
    
    def _execute_denoise_pipeline(self, audio: np.ndarray, decisions: Dict[str, Any], 
                                 sample_rate: int = 16000) -> Tuple[np.ndarray, list]:
        """執行降噪處理管線
        
        Args:
            audio: 輸入音訊
            decisions: 降噪決策
            sample_rate: 採樣率
            
        Returns:
            Tuple[處理後音訊, 應用步驟列表]
        """
        applied_steps = []
        processed_audio = audio.copy()
        
        if decisions['apply_denoising']:
            # 使用 DeepFilterNet 降噪 (自動處理採樣率轉換)
            processed_audio = self._process_with_deepfilternet(
                processed_audio, decisions['strength'], sample_rate
            )
            applied_steps.append(
                f"DeepFilterNet 降噪 (強度: {decisions['strength']:.2f}, "
                f"{sample_rate}Hz→{self.internal_sample_rate}Hz→{sample_rate}Hz)"
            )
            
            # 如果需要積極處理，可以加入額外的後處理
            if decisions['aggressive']:
                applied_steps.append("積極降噪模式")
                
        if not applied_steps:
            applied_steps.append("無需降噪處理")
            
        return processed_audio, applied_steps
    
    def _bytes_to_audio(self, audio_bytes: bytes) -> np.ndarray:
        """將 bytes 轉換為 float32 音訊陣列"""
        return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    
    def _audio_to_bytes(self, audio: np.ndarray) -> bytes:
        """將 float32 音訊陣列轉換為 bytes"""
        return (np.clip(audio, -1.0, 1.0) * 32768).astype(np.int16).tobytes()
    
    def _empty_report(self, purpose: str) -> Dict[str, Any]:
        """生成空音訊的報告"""
        return {
            'purpose': purpose,
            'analysis': {'error': '空音訊資料'},
            'decisions': {'apply_denoising': False},
            'applied_steps': [],
            'performance': {'processing_time_ms': '0.00'}
        }
    
    def _error_report(self, purpose: str, error: str) -> Dict[str, Any]:
        """生成錯誤報告"""
        return {
            'purpose': purpose,
            'analysis': {'error': error},
            'decisions': {'apply_denoising': False},
            'applied_steps': [],
            'performance': {'processing_time_ms': '0.00'}
        }
    
    @property
    def is_available(self) -> bool:
        """檢查服務是否可用"""
        if not self.enabled:
            return False
            
        try:
            self._ensure_model_ready()
            return True
        except Exception:
            return False
    
    @property
    def model_info(self) -> Dict[str, Any]:
        """獲取模型資訊"""
        if not self._model_initialized:
            return {'status': 'not_initialized'}
            
        return {
            'status': 'ready',
            'model_type': self.model_base_dir,
            'device': self.device,
            'post_filter': self.post_filter,
            'default_strength': self.strength
        }


# 模組級單例實例
deepfilternet_denoiser = DeepFilterNetDenoiser()

__all__ = ['DeepFilterNetDenoiser', 'deepfilternet_denoiser']