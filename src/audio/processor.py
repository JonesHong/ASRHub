"""
統一音訊處理器
整合特徵提取、靜音檢測、能量計算等功能
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass
from .models import AudioChunk, AudioMetadata, AudioSampleFormat


@dataclass
class AudioFeatures:
    """音訊特徵資料結構"""
    rms: float  # 均方根值
    energy: float  # 能量
    peak: float  # 峰值
    zero_crossing_rate: float  # 過零率
    is_silence: bool  # 是否為靜音
    duration: float  # 時長（秒）


class AudioProcessor:
    """
    統一的音訊處理器
    整合來自 audio_stream.py 和 audio_helper.py 的特徵提取功能
    """
    
    def __init__(self, 
                 silence_threshold: float = 0.01,
                 silence_duration: float = 0.5):
        """
        初始化音訊處理器
        
        Args:
            silence_threshold: 靜音 RMS 閾值
            silence_duration: 靜音持續時間（秒）
        """
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self._silence_samples = 0
    
    def extract_features(self, 
                        audio_chunk: AudioChunk,
                        reset_silence_counter: bool = False) -> AudioFeatures:
        """
        提取音訊特徵
        
        Args:
            audio_chunk: 音訊資料塊
            reset_silence_counter: 是否重置靜音計數器
            
        Returns:
            AudioFeatures 特徵物件
        """
        if reset_silence_counter:
            self._silence_samples = 0
        
        # 轉換為 numpy array
        audio_np = self.bytes_to_numpy(
            audio_chunk.data, 
            audio_chunk.metadata.format
        )
        
        # 正規化到 [-1, 1]
        audio_normalized = self.normalize(audio_np, audio_chunk.metadata.format)
        
        # 計算特徵
        rms = self.calculate_rms(audio_normalized)
        energy = self.calculate_energy(audio_normalized)
        peak = self.calculate_peak(audio_normalized)
        zcr = self.calculate_zero_crossing_rate(audio_normalized)
        
        # 檢測靜音
        is_silence = False
        if rms < self.silence_threshold:
            self._silence_samples += len(audio_np)
            silence_duration = self._silence_samples / audio_chunk.metadata.sample_rate
            if silence_duration > self.silence_duration:
                is_silence = True
        else:
            self._silence_samples = 0
        
        return AudioFeatures(
            rms=rms,
            energy=energy,
            peak=peak,
            zero_crossing_rate=zcr,
            is_silence=is_silence,
            duration=audio_chunk.duration
        )
    
    def detect_silence(self,
                      audio_chunk: AudioChunk,
                      threshold: Optional[float] = None) -> bool:
        """
        檢測音訊是否為靜音
        
        Args:
            audio_chunk: 音訊資料塊
            threshold: 可選的自定義閾值
            
        Returns:
            是否為靜音
        """
        threshold = threshold or self.silence_threshold
        
        audio_np = self.bytes_to_numpy(
            audio_chunk.data,
            audio_chunk.metadata.format
        )
        audio_normalized = self.normalize(audio_np, audio_chunk.metadata.format)
        rms = self.calculate_rms(audio_normalized)
        
        return rms < threshold
    
    def calculate_rms(self, audio_np: np.ndarray) -> float:
        """
        計算均方根值（RMS）
        
        Args:
            audio_np: 正規化的音訊陣列
            
        Returns:
            RMS 值
        """
        return float(np.sqrt(np.mean(audio_np ** 2)))
    
    def calculate_energy(self, audio_np: np.ndarray) -> float:
        """
        計算音訊能量
        
        Args:
            audio_np: 正規化的音訊陣列
            
        Returns:
            能量值
        """
        return float(np.sum(audio_np ** 2))
    
    def calculate_peak(self, audio_np: np.ndarray) -> float:
        """
        計算峰值
        
        Args:
            audio_np: 正規化的音訊陣列
            
        Returns:
            峰值
        """
        return float(np.max(np.abs(audio_np)))
    
    def calculate_zero_crossing_rate(self, audio_np: np.ndarray) -> float:
        """
        計算過零率
        
        Args:
            audio_np: 正規化的音訊陣列
            
        Returns:
            過零率
        """
        # 計算符號變化
        signs = np.sign(audio_np)
        signs[signs == 0] = 1  # 將零值視為正值
        
        # 計算過零次數
        zero_crossings = np.abs(np.diff(signs)) > 0
        zcr = np.sum(zero_crossings) / len(audio_np)
        
        return float(zcr)
    
    def normalize(self, 
                 audio_np: np.ndarray,
                 format: AudioSampleFormat) -> np.ndarray:
        """
        正規化音訊到 [-1, 1] 範圍
        
        Args:
            audio_np: 原始音訊陣列
            format: 音訊格式
            
        Returns:
            正規化的音訊陣列
        """
        audio_float = audio_np.astype(np.float32)
        
        if format == AudioSampleFormat.INT16:
            audio_float /= 32768.0
        elif format == AudioSampleFormat.INT32:
            audio_float /= 2147483648.0
        elif format == AudioSampleFormat.FLOAT32:
            # 已經是 float，不需要轉換
            pass
        else:
            # INT24 或其他格式
            # 假設已經在合理範圍內
            max_val = np.max(np.abs(audio_float))
            if max_val > 0:
                audio_float /= max_val
        
        return audio_float
    
    def bytes_to_numpy(self,
                      data: bytes,
                      format: AudioSampleFormat) -> np.ndarray:
        """
        將 bytes 轉換為 numpy array
        
        Args:
            data: 音訊資料
            format: 音訊格式
            
        Returns:
            numpy array
        """
        dtype = format.numpy_dtype
        if dtype is None:
            # INT24 特殊處理
            if format == AudioSampleFormat.INT24:
                # 將 3 bytes 轉換為 4 bytes (int32)
                samples = []
                for i in range(0, len(data), 3):
                    sample_bytes = data[i:i+3]
                    # 添加填充位元組（大端或小端取決於系統）
                    sample_int = int.from_bytes(sample_bytes, byteorder='little', signed=True)
                    samples.append(sample_int)
                return np.array(samples, dtype=np.int32)
            else:
                raise ValueError(f"不支援的格式: {format}")
        
        return np.frombuffer(data, dtype=dtype)
    
    def numpy_to_bytes(self,
                      audio_np: np.ndarray,
                      format: AudioSampleFormat) -> bytes:
        """
        將 numpy array 轉換為 bytes
        
        Args:
            audio_np: 音訊陣列
            format: 目標格式
            
        Returns:
            bytes 資料
        """
        if format == AudioSampleFormat.INT24:
            # INT24 特殊處理
            result = bytearray()
            for sample in audio_np:
                # 轉換為 24-bit 整數
                sample_int = int(sample) & 0xFFFFFF
                # 轉換為 3 bytes
                result.extend(sample_int.to_bytes(3, byteorder='little', signed=True))
            return bytes(result)
        
        dtype = format.numpy_dtype
        if dtype is None:
            raise ValueError(f"不支援的格式: {format}")
        
        return audio_np.astype(dtype).tobytes()
    
    def apply_gain(self,
                  audio_chunk: AudioChunk,
                  gain_db: float) -> AudioChunk:
        """
        應用增益到音訊
        
        Args:
            audio_chunk: 音訊資料塊
            gain_db: 增益（分貝）
            
        Returns:
            應用增益後的音訊資料塊
        """
        # 轉換為 numpy
        audio_np = self.bytes_to_numpy(
            audio_chunk.data,
            audio_chunk.metadata.format
        )
        
        # 轉換為 float 並正規化
        audio_normalized = self.normalize(audio_np, audio_chunk.metadata.format)
        
        # 應用增益
        gain_linear = 10 ** (gain_db / 20.0)
        audio_gained = audio_normalized * gain_linear
        
        # 限制到 [-1, 1]
        audio_gained = np.clip(audio_gained, -1.0, 1.0)
        
        # 轉換回原始格式
        if audio_chunk.metadata.format == AudioSampleFormat.INT16:
            audio_gained = (audio_gained * 32767).astype(np.int16)
        elif audio_chunk.metadata.format == AudioSampleFormat.INT32:
            audio_gained = (audio_gained * 2147483647).astype(np.int32)
        
        # 轉換回 bytes
        new_data = self.numpy_to_bytes(audio_gained, audio_chunk.metadata.format)
        
        # 創建新的 AudioChunk
        new_chunk = audio_chunk.clone()
        new_chunk.data = new_data
        
        return new_chunk
    
    def remove_dc_offset(self, audio_chunk: AudioChunk) -> AudioChunk:
        """
        移除直流偏移
        
        Args:
            audio_chunk: 音訊資料塊
            
        Returns:
            移除直流偏移後的音訊資料塊
        """
        # 轉換為 numpy
        audio_np = self.bytes_to_numpy(
            audio_chunk.data,
            audio_chunk.metadata.format
        )
        
        # 計算並移除直流偏移
        dc_offset = np.mean(audio_np)
        audio_corrected = audio_np - dc_offset
        
        # 轉換回 bytes
        new_data = self.numpy_to_bytes(
            audio_corrected.astype(audio_np.dtype),
            audio_chunk.metadata.format
        )
        
        # 創建新的 AudioChunk
        new_chunk = audio_chunk.clone()
        new_chunk.data = new_data
        
        return new_chunk
    
    def get_statistics(self, audio_chunk: AudioChunk) -> Dict[str, float]:
        """
        獲取音訊統計資訊
        
        Args:
            audio_chunk: 音訊資料塊
            
        Returns:
            統計資訊字典
        """
        audio_np = self.bytes_to_numpy(
            audio_chunk.data,
            audio_chunk.metadata.format
        )
        audio_normalized = self.normalize(audio_np, audio_chunk.metadata.format)
        
        return {
            "mean": float(np.mean(audio_normalized)),
            "std": float(np.std(audio_normalized)),
            "min": float(np.min(audio_normalized)),
            "max": float(np.max(audio_normalized)),
            "rms": self.calculate_rms(audio_normalized),
            "energy": self.calculate_energy(audio_normalized),
            "peak": self.calculate_peak(audio_normalized),
            "zero_crossing_rate": self.calculate_zero_crossing_rate(audio_normalized),
            "duration": audio_chunk.duration,
            "samples": len(audio_np)
        }