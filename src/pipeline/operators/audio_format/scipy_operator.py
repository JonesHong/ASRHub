#!/usr/bin/env python3
"""
基於 SciPy 的音頻格式轉換 Operator
使用 SciPy 和 NumPy 進行高品質音頻轉換
"""

import numpy as np
from scipy import signal
from typing import Optional

from .base import AudioFormatOperatorBase
from src.models.audio_format import AudioMetadata, AudioFormat
from src.core.exceptions import AudioFormatError
from src.utils.logger import logger


class ScipyAudioFormatOperator(AudioFormatOperatorBase):
    """
    使用 SciPy 進行音頻格式轉換的 Operator
    適合高品質音頻處理和科學計算應用
    """
    
    def __init__(self, operator_id: str = 'scipy', target_metadata: Optional[AudioMetadata] = None):
        """
        初始化 SciPy 音頻格式轉換 Operator
        
        Args:
            operator_id: 操作器識別ID
            target_metadata: 目標音頻格式元數據
        """
        super().__init__(operator_id, target_metadata)
        
        # SciPy 特定的配置
        self.resample_method = 'fft'  # 'fft' 或 'polyphase'
        self.filter_window = 'hamming'  # 濾波器窗口類型
        
        self.logger.info(f"ScipyAudioFormatOperator[{self.operator_id}] 初始化完成")
    
    async def _convert_format(self, audio_data: bytes, 
                            from_metadata: AudioMetadata,
                            to_metadata: AudioMetadata) -> bytes:
        """
        使用 SciPy 執行音頻格式轉換
        
        Args:
            audio_data: 原始音頻數據
            from_metadata: 來源音頻元數據
            to_metadata: 目標音頻元數據
            
        Returns:
            轉換後的音頻數據
        """
        try:
            # 轉換為 numpy array
            samples = self._to_numpy(audio_data, from_metadata)
            
            # 處理聲道轉換
            if from_metadata.channels != to_metadata.channels:
                samples = self._convert_channels(
                    samples, 
                    from_metadata.channels, 
                    to_metadata.channels
                )
            
            # 處理採樣率轉換
            if from_metadata.sample_rate != to_metadata.sample_rate:
                samples = self._resample(
                    samples,
                    from_metadata.sample_rate,
                    to_metadata.sample_rate
                )
            
            # 處理位元深度轉換
            if from_metadata.format != to_metadata.format:
                samples = self._convert_bit_depth(
                    samples,
                    from_metadata.format,
                    to_metadata.format
                )
            
            # 轉換回 bytes
            return self._from_numpy(samples, to_metadata.format)
            
        except Exception as e:
            self.logger.error(f"[{self.operator_id}] SciPy 音頻轉換失敗: {e}")
            raise AudioFormatError(f"SciPy 音頻轉換失敗: {str(e)}")
    
    def _convert_channels(self, samples: np.ndarray, 
                         from_channels: int, 
                         to_channels: int) -> np.ndarray:
        """轉換聲道數"""
        if from_channels == to_channels:
            return samples
        
        if from_channels == 2 and to_channels == 1:
            # 立體聲轉單聲道：取平均
            samples = samples.reshape(-1, 2)
            return samples.mean(axis=1).astype(samples.dtype)
        
        elif from_channels == 1 and to_channels == 2:
            # 單聲道轉立體聲：複製
            return np.repeat(samples, 2)
        
        else:
            raise ValueError(f"不支援的聲道轉換: {from_channels} -> {to_channels}")
    
    def _resample(self, samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """重採樣音頻數據"""
        if orig_sr == target_sr:
            return samples
        
        # 計算重採樣因子
        resample_ratio = target_sr / orig_sr
        
        if self.resample_method == 'fft':
            # 使用 FFT 方法（高品質）
            new_length = int(len(samples) * resample_ratio)
            resampled = signal.resample(samples, new_length)
        else:
            # 使用多相濾波器方法（更快）
            resampled = signal.resample_poly(samples, target_sr, orig_sr)
        
        return resampled
    
    def _convert_bit_depth(self, samples: np.ndarray, 
                          from_format: AudioFormat, 
                          to_format: AudioFormat) -> np.ndarray:
        """轉換位元深度"""
        if from_format == to_format:
            return samples
        
        # 先正規化到 float32 [-1, 1]
        if from_format == AudioFormat.INT16:
            samples_float = samples.astype(np.float32) / 32768.0
        elif from_format == AudioFormat.INT24:
            samples_float = samples.astype(np.float32) / 8388608.0
        elif from_format == AudioFormat.INT32:
            samples_float = samples.astype(np.float32) / 2147483648.0
        elif from_format == AudioFormat.FLOAT32:
            samples_float = samples
        else:
            raise ValueError(f"不支援的輸入格式: {from_format}")
        
        # 轉換到目標格式
        if to_format == AudioFormat.INT16:
            # 確保在有效範圍內並轉換
            samples_float = np.clip(samples_float, -1.0, 1.0)
            return (samples_float * 32767).astype(np.int16)
        elif to_format == AudioFormat.INT24:
            # 24-bit 需要特殊處理
            samples_float = np.clip(samples_float, -1.0, 1.0)
            return (samples_float * 8388607).astype(np.int32)
        elif to_format == AudioFormat.INT32:
            samples_float = np.clip(samples_float, -1.0, 1.0)
            return (samples_float * 2147483647).astype(np.int32)
        elif to_format == AudioFormat.FLOAT32:
            return samples_float.astype(np.float32)
        else:
            raise ValueError(f"不支援的輸出格式: {to_format}")
    
    def update_config(self, config: dict):
        """更新配置"""
        super().update_config(config)
        
        # 更新 SciPy 特定配置
        if 'resample_method' in config:
            if config['resample_method'] in ['fft', 'polyphase']:
                self.resample_method = config['resample_method']
                self.logger.info(f"[{self.operator_id}] 重採樣方法更新為: {self.resample_method}")
        
        if 'filter_window' in config:
            self.filter_window = config['filter_window']
            self.logger.info(f"[{self.operator_id}] 濾波器窗口更新為: {self.filter_window}")
    
    def get_info(self) -> dict:
        """獲取 Operator 信息"""
        info = super().get_info()
        info.update({
            "resample_method": self.resample_method,
            "filter_window": self.filter_window,
            "backend": "scipy"
        })
        return info