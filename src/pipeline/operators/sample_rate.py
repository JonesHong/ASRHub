"""
ASR Hub Sample Rate Adjustment Operator
處理音訊取樣率轉換
"""

from typing import Optional, Dict, Any, Tuple
import numpy as np
from scipy import signal
from src.pipeline.operators.base import BufferingOperator
from src.utils.logger import get_logger
from src.core.exceptions import PipelineError, AudioFormatError
from src.models.audio import AudioChunk, AudioFormat, AudioEncoding


class SampleRateOperator(BufferingOperator):
    """
    取樣率調整 Operator
    將音訊轉換為目標取樣率
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Sample Rate Operator
        
        Args:
            config: 配置參數
                - target_rate: 目標取樣率（預設 16000）
                - quality: 轉換品質 "low", "medium", "high"（預設 "high"）
                - buffer_size: 緩衝區大小（預設 8192）
        """
        super().__init__(config)
        self.logger = get_logger("operator.sample_rate")
        
        # 配置參數
        self.target_rate = self.config.get("target_rate", 16000)
        self.quality = self.config.get("quality", "high")
        
        # 支援的取樣率
        self.supported_rates = [8000, 16000, 22050, 44100, 48000]
        
        # 重採樣器快取（避免重複建立）
        self._resampler_cache: Dict[Tuple[int, int], Any] = {}
        
        # 內部狀態
        self._last_input_rate = None
        self._residual_samples = None  # 處理不完整的樣本
    
    async def _initialize(self):
        """初始化資源"""
        await super()._initialize()
        
        # 驗證目標取樣率
        if self.target_rate not in self.supported_rates:
            raise AudioFormatError(
                f"不支援的目標取樣率：{self.target_rate}。"
                f"支援的取樣率：{self.supported_rates}"
            )
        
        self.logger.info(
            f"Sample Rate Operator 初始化完成 - "
            f"目標取樣率：{self.target_rate} Hz，"
            f"品質：{self.quality}"
        )
    
    async def _cleanup(self):
        """清理資源"""
        self._resampler_cache.clear()
        self._residual_samples = None
        await super()._cleanup()
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊資料，轉換取樣率
        
        Args:
            audio_data: 輸入音訊資料（PCM 格式）
            **kwargs: 額外參數
                - input_rate: 輸入取樣率（必需）
                - channels: 聲道數（預設 1）
                - encoding: 編碼格式（預設 LINEAR16）
                
        Returns:
            轉換後的音訊資料，如果輸入取樣率已經是目標取樣率則直接返回
            
        Raises:
            PipelineError: 如果處理失敗
        """
        if not self.enabled:
            return audio_data
        
        if not self.validate_audio_params(audio_data):
            return None
        
        try:
            # 獲取音訊參數
            input_rate = kwargs.get("input_rate", self.sample_rate)
            channels = kwargs.get("channels", self.channels)
            encoding = kwargs.get("encoding", "linear16")
            
            # 如果輸入取樣率已經是目標取樣率，直接返回
            if input_rate == self.target_rate:
                self.logger.debug(f"輸入取樣率已經是 {self.target_rate} Hz，無需轉換")
                return audio_data
            
            # 將位元組轉換為 numpy 陣列
            audio_array = self._bytes_to_numpy(audio_data, encoding)
            
            # 如果是多聲道，需要分別處理每個聲道
            if channels > 1:
                audio_array = audio_array.reshape(-1, channels)
                resampled_channels = []
                
                for ch in range(channels):
                    channel_data = audio_array[:, ch]
                    resampled = self._resample_audio(
                        channel_data, input_rate, self.target_rate
                    )
                    resampled_channels.append(resampled)
                
                # 合併聲道
                resampled_array = np.column_stack(resampled_channels)
            else:
                # 單聲道直接處理
                resampled_array = self._resample_audio(
                    audio_array, input_rate, self.target_rate
                )
            
            # 轉換回位元組
            resampled_bytes = self._numpy_to_bytes(resampled_array, encoding)
            
            # 記錄統計
            self.logger.debug(
                f"取樣率轉換完成：{input_rate} Hz -> {self.target_rate} Hz，"
                f"輸入大小：{len(audio_data)} bytes，"
                f"輸出大小：{len(resampled_bytes)} bytes"
            )
            
            return resampled_bytes
            
        except Exception as e:
            self.logger.error(f"取樣率轉換失敗：{e}")
            raise PipelineError(f"取樣率轉換失敗：{str(e)}")
    
    def _resample_audio(self, 
                       audio_data: np.ndarray,
                       input_rate: int,
                       output_rate: int) -> np.ndarray:
        """
        執行音訊重採樣
        
        Args:
            audio_data: 音訊資料陣列
            input_rate: 輸入取樣率
            output_rate: 輸出取樣率
            
        Returns:
            重採樣後的音訊資料
        """
        # 檢查快取
        cache_key = (input_rate, output_rate)
        
        # 根據品質選擇不同的重採樣方法
        if self.quality == "low":
            # 使用簡單的線性插值
            return self._resample_linear(audio_data, input_rate, output_rate)
        elif self.quality == "medium":
            # 使用 scipy 的 resample
            return self._resample_scipy(audio_data, input_rate, output_rate)
        else:  # high
            # 使用多相濾波器（polyphase filter）
            return self._resample_polyphase(audio_data, input_rate, output_rate)
    
    def _resample_linear(self,
                        audio_data: np.ndarray,
                        input_rate: int,
                        output_rate: int) -> np.ndarray:
        """
        使用線性插值進行重採樣（低品質但快速）
        
        Args:
            audio_data: 音訊資料
            input_rate: 輸入取樣率
            output_rate: 輸出取樣率
            
        Returns:
            重採樣後的資料
        """
        # 計算重採樣比例
        ratio = output_rate / input_rate
        
        # 計算輸出長度
        output_length = int(len(audio_data) * ratio)
        
        # 建立輸入和輸出的索引
        input_indices = np.arange(len(audio_data))
        output_indices = np.linspace(0, len(audio_data) - 1, output_length)
        
        # 線性插值
        resampled = np.interp(output_indices, input_indices, audio_data)
        
        return resampled.astype(audio_data.dtype)
    
    def _resample_scipy(self,
                       audio_data: np.ndarray,
                       input_rate: int,
                       output_rate: int) -> np.ndarray:
        """
        使用 scipy.signal.resample 進行重採樣（中等品質）
        
        Args:
            audio_data: 音訊資料
            input_rate: 輸入取樣率
            output_rate: 輸出取樣率
            
        Returns:
            重採樣後的資料
        """
        # 計算輸出樣本數
        num_samples = int(len(audio_data) * output_rate / input_rate)
        
        # 使用 scipy 的 resample（基於 FFT）
        resampled = signal.resample(audio_data, num_samples)
        
        return resampled.astype(audio_data.dtype)
    
    def _resample_polyphase(self,
                          audio_data: np.ndarray,
                          input_rate: int,
                          output_rate: int) -> np.ndarray:
        """
        使用多相濾波器進行高品質重採樣
        
        Args:
            audio_data: 音訊資料
            input_rate: 輸入取樣率
            output_rate: 輸出取樣率
            
        Returns:
            重採樣後的資料
        """
        # 計算最大公約數和上/下採樣因子
        from math import gcd
        g = gcd(input_rate, output_rate)
        up = output_rate // g
        down = input_rate // g
        
        # 如果比例太大，使用 scipy 的方法
        if up > 100 or down > 100:
            return self._resample_scipy(audio_data, input_rate, output_rate)
        
        # 設計低通濾波器
        # 截止頻率為 min(input_rate, output_rate) / 2 的 80%
        cutoff_freq = min(input_rate, output_rate) * 0.4
        nyquist_freq = input_rate * up / 2
        normalized_cutoff = cutoff_freq / nyquist_freq
        
        # 濾波器階數
        filter_order = 64 if self.quality == "high" else 32
        
        # 設計濾波器
        filter_coeffs = signal.firwin(
            filter_order,
            normalized_cutoff,
            window='hamming'
        )
        
        # 執行重採樣
        # 1. 上採樣（插零）
        if up > 1:
            upsampled = np.zeros(len(audio_data) * up)
            upsampled[::up] = audio_data
        else:
            upsampled = audio_data
        
        # 2. 濾波
        filtered = signal.convolve(upsampled, filter_coeffs * up, mode='same')
        
        # 3. 下採樣
        resampled = filtered[::down]
        
        return resampled.astype(audio_data.dtype)
    
    def _bytes_to_numpy(self, audio_bytes: bytes, encoding: str) -> np.ndarray:
        """
        將位元組轉換為 numpy 陣列
        
        Args:
            audio_bytes: 音訊位元組
            encoding: 編碼格式
            
        Returns:
            numpy 陣列
        """
        if encoding == "linear16":
            return np.frombuffer(audio_bytes, dtype=np.int16)
        elif encoding == "linear32":
            return np.frombuffer(audio_bytes, dtype=np.int32)
        elif encoding == "float32":
            return np.frombuffer(audio_bytes, dtype=np.float32)
        else:
            raise AudioFormatError(f"不支援的編碼格式：{encoding}")
    
    def _numpy_to_bytes(self, audio_array: np.ndarray, encoding: str) -> bytes:
        """
        將 numpy 陣列轉換為位元組
        
        Args:
            audio_array: numpy 陣列
            encoding: 編碼格式
            
        Returns:
            音訊位元組
        """
        if encoding == "linear16":
            return audio_array.astype(np.int16).tobytes()
        elif encoding == "linear32":
            return audio_array.astype(np.int32).tobytes()
        elif encoding == "float32":
            return audio_array.astype(np.float32).tobytes()
        else:
            raise AudioFormatError(f"不支援的編碼格式：{encoding}")
    
    def get_info(self) -> Dict[str, Any]:
        """獲取 Operator 資訊"""
        info = super().get_info()
        info.update({
            "target_rate": self.target_rate,
            "quality": self.quality,
            "supported_rates": self.supported_rates,
            "cache_size": len(self._resampler_cache)
        })
        return info
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        super().update_config(config)
        
        # 更新特定參數
        if "target_rate" in config:
            new_rate = config["target_rate"]
            if new_rate in self.supported_rates:
                self.target_rate = new_rate
                self.logger.info(f"目標取樣率更新為：{self.target_rate} Hz")
            else:
                self.logger.warning(f"不支援的取樣率：{new_rate}")
        
        if "quality" in config:
            if config["quality"] in ["low", "medium", "high"]:
                self.quality = config["quality"]
                self.logger.info(f"轉換品質更新為：{self.quality}")
    
    async def flush(self):
        """清空緩衝區"""
        await super().flush()
        self._residual_samples = None
        self.logger.debug("Sample Rate Operator 緩衝區已清空")