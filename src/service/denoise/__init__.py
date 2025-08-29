"""音訊降噪服務 (Stateless Service)

提供多種音訊降噪方式：
- DeepFilterNetDenoiser: 使用 DeepFilterNet 深度學習降噪
- (未來) WebRTCDenoiser: 使用 WebRTC 降噪
- (未來) RNNoiseDenoiser: 使用 RNNoise 降噪

這是無狀態服務，所有方法都是獨立的，可並行處理多個 session。
"""

from typing import Optional, Union, Dict, Any, Tuple
import numpy as np

from src.utils.logger import logger
from src.config.manager import ConfigManager


class DenoiseService:
    """統一的音訊降噪服務 (Stateless)。
    
    自動選擇最適合的降噪器：
    - DeepFilterNet: 48kHz 高品質深度學習降噪
    - WebRTC: 16kHz 輕量級實時降噪 (未來)
    - RNNoise: 48kHz RNN 降噪 (未來)
    - 自動 fallback
    """
    
    def __init__(self):
        """初始化可用的降噪器。"""
        self.config = ConfigManager()
        self.denoiser_config = self.config.services.denoiser
        
        self.deepfilternet_denoiser = None
        self.webrtc_denoiser = None
        self.rnnoise_denoiser = None
        
        # 根據配置載入 DeepFilterNet 降噪器
        if (self.denoiser_config.enabled and 
            self.denoiser_config.type == "deepfilternet"):
            try:
                from .deepfilternet_denoiser import deepfilternet_denoiser
                self.deepfilternet_denoiser = deepfilternet_denoiser
                logger.info("DeepFilterNet 降噪器載入完成")
            except ImportError as e:
                logger.warning(f"DeepFilterNet 不可用: {e}")
        
        # 未來的其他降噪器
        # if self.denoiser_config.webrtc.enabled:
        #     try:
        #         from .webrtc_denoiser import webrtc_denoiser
        #         self.webrtc_denoiser = webrtc_denoiser
        #         logger.info("WebRTC 降噪器載入完成")
        #     except ImportError as e:
        #         logger.warning(f"WebRTC 不可用: {e}")
        
        if not self.deepfilternet_denoiser:
            logger.error("無可用的降噪器!")
    
    def denoise(
        self,
        audio_data: Union[bytes, np.ndarray],
        strength: Optional[float] = None,
        sample_rate: int = 16000,
        prefer_engine: Optional[str] = None
    ) -> Union[bytes, np.ndarray]:
        """降噪音訊。
        
        Args:
            audio_data: 原始音訊資料
            strength: 降噪強度 (0.0-1.0, None = 使用配置預設值)
            sample_rate: 取樣率
            prefer_engine: 偏好的降噪引擎 ("deepfilternet", "webrtc", "rnnoise")
            
        Returns:
            降噪後的音訊資料
        """
        # 使用配置預設值
        strength = strength if strength is not None else self.denoiser_config.strength
        
        # 選擇降噪器
        engine = prefer_engine or self.denoiser_config.type
        
        if engine == "deepfilternet" and self.deepfilternet_denoiser:
            return self.deepfilternet_denoiser.denoise(
                audio_data, strength=strength, sample_rate=sample_rate
            )
        
        # 未來的其他引擎
        # elif engine == "webrtc" and self.webrtc_denoiser:
        #     return self.webrtc_denoiser.denoise(
        #         audio_data, strength=strength, sample_rate=sample_rate
        #     )
        
        # Fallback 到可用的降噪器
        if self.deepfilternet_denoiser:
            logger.warning(f"引擎 {engine} 不可用，改用 DeepFilterNet")
            return self.deepfilternet_denoiser.denoise(
                audio_data, strength=strength, sample_rate=sample_rate
            )
        
        logger.error("無可用的降噪器")
        return audio_data  # 返回原始音訊
    
    def auto_denoise(
        self,
        audio_data: Union[bytes, np.ndarray],
        purpose: str = "asr",
        sample_rate: int = 16000,
        prefer_engine: Optional[str] = None
    ) -> Tuple[Union[bytes, np.ndarray], Dict[str, Any]]:
        """智慧音訊降噪。
        
        根據用途和音訊特性自動決定最佳降噪策略。
        
        Args:
            audio_data: 原始音訊資料
            purpose: 用途 ("asr", "vad", "wakeword", "recording", "general")
            sample_rate: 取樣率
            prefer_engine: 偏好的降噪引擎
            
        Returns:
            (降噪後的音訊資料, 處理報告)
        """
        # 選擇降噪器
        engine = prefer_engine or self.denoiser_config.type
        
        if engine == "deepfilternet" and self.deepfilternet_denoiser:
            return self.deepfilternet_denoiser.auto_denoise(
                audio_data, purpose=purpose, sample_rate=sample_rate
            )
        
        # Fallback 到可用的降噪器
        if self.deepfilternet_denoiser:
            logger.warning(f"引擎 {engine} 不可用，改用 DeepFilterNet")
            return self.deepfilternet_denoiser.auto_denoise(
                audio_data, purpose=purpose, sample_rate=sample_rate
            )
        
        # 無降噪器可用
        logger.error("無可用的降噪器")
        report = {
            "purpose": purpose,
            "analysis": {"error": "無可用的降噪器"},
            "decisions": {"apply_denoising": False},
            "applied_steps": [],
            "performance": {"processing_time_ms": 0.0}
        }
        return audio_data, report
    
    def select_optimal_engine(
        self,
        input_sample_rate: int,
        target_sample_rate: int = 16000,
        prefer_quality: bool = True
    ) -> str:
        """選擇最佳降噪引擎。
        
        根據採樣率和品質偏好自動選擇引擎。
        
        Args:
            input_sample_rate: 輸入採樣率
            target_sample_rate: 目標採樣率
            prefer_quality: 是否偏好品質 (否則偏好性能)
            
        Returns:
            推薦的引擎名稱
        """
        # 如果輸入已經是 16kHz 且有 WebRTC，優先 WebRTC (未來)
        if input_sample_rate == 16000 and self.webrtc_denoiser and not prefer_quality:
            return "webrtc"
        
        # 48kHz 系列優先 DeepFilterNet
        if input_sample_rate in [48000, 44100] and self.deepfilternet_denoiser:
            return "deepfilternet"
        
        # 預設選擇
        if self.deepfilternet_denoiser:
            return "deepfilternet"
        elif self.webrtc_denoiser:
            return "webrtc"
        else:
            return "none"
    
    @property
    def is_available(self) -> bool:
        """檢查是否有可用的降噪器。"""
        return (self.deepfilternet_denoiser is not None or 
                self.webrtc_denoiser is not None or 
                self.rnnoise_denoiser is not None)
    
    @property
    def available_engines(self) -> list:
        """取得可用的降噪引擎列表。"""
        engines = []
        if self.deepfilternet_denoiser:
            engines.append("deepfilternet")
        if self.webrtc_denoiser:
            engines.append("webrtc")
        if self.rnnoise_denoiser:
            engines.append("rnnoise")
        return engines


# 匯出統一服務
denoise_service: DenoiseService = DenoiseService()

# 相容性匯出
denoiser = denoise_service  # 簡短名稱

__all__ = [
    'denoise_service',
    'denoiser',
    'DenoiseService'
]