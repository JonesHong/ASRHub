"""
音訊串流處理器
處理即時音訊串流的緩衝、格式轉換和音訊特徵提取
"""

import asyncio
from typing import Optional, Callable, Dict, Any
import numpy as np
from collections import deque
from src.utils.logger import get_logger


class AudioStreamProcessor:
    """
    音訊串流處理器
    
    負責：
    - 音訊串流緩衝管理
    - 格式轉換（bytes <-> numpy）
    - 音訊特徵提取（RMS、能量等）
    - 串流事件處理
    """
    
    def __init__(self, 
                 buffer_size: int = 16384,
                 sample_rate: int = 16000,
                 channels: int = 1,
                 dtype: str = "int16"):
        """
        初始化音訊串流處理器
        
        Args:
            buffer_size: 緩衝區大小（樣本數）
            sample_rate: 採樣率
            channels: 聲道數
            dtype: 音訊資料類型
        """
        self.logger = get_logger("stream.audioprocessor")
        
        # 音訊參數
        self.buffer_size = buffer_size
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        
        # 緩衝區
        self.buffer = deque(maxlen=buffer_size)
        self._lock = asyncio.Lock()
        
        # 串流狀態
        self.is_active = False
        self.total_samples = 0
        self.total_bytes = 0
        
        # 回呼函數
        self.on_audio_callback: Optional[Callable] = None
        self.on_silence_callback: Optional[Callable] = None
        
        # 音訊特徵
        self.silence_threshold = 0.01  # RMS 閾值
        self.silence_duration = 0.5  # 靜音持續時間（秒）
        self._silence_samples = 0
        
        self.logger.info(
            f"音訊串流處理器初始化 - "
            f"採樣率: {sample_rate}Hz, "
            f"聲道: {channels}, "
            f"緩衝區: {buffer_size} 樣本"
        )
    
    async def start(self):
        """啟動串流處理器"""
        async with self._lock:
            if self.is_active:
                self.logger.warning("串流處理器已經在運行")
                return
            
            self.is_active = True
            self.buffer.clear()
            self.total_samples = 0
            self.total_bytes = 0
            self._silence_samples = 0
            
            self.logger.info("音訊串流處理器已啟動")
    
    async def stop(self):
        """停止串流處理器"""
        async with self._lock:
            if not self.is_active:
                self.logger.warning("串流處理器未在運行")
                return
            
            self.is_active = False
            self.buffer.clear()
            
            self.logger.info(
                f"音訊串流處理器已停止 - "
                f"處理樣本: {self.total_samples}, "
                f"總位元組: {self.total_bytes}"
            )
    
    async def process_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """
        處理音訊資料
        
        Args:
            audio_data: 音訊資料（bytes）
            
        Returns:
            處理結果字典，包含音訊特徵
        """
        if not self.is_active:
            return {"error": "串流處理器未啟動"}
        
        async with self._lock:
            # 轉換為 numpy array
            audio_np = self._bytes_to_numpy(audio_data)
            
            # 更新統計
            self.total_samples += len(audio_np)
            self.total_bytes += len(audio_data)
            
            # 添加到緩衝區
            self.buffer.extend(audio_np)
            
            # 計算音訊特徵
            features = self._extract_features(audio_np)
            
            # 檢測靜音
            if features["rms"] < self.silence_threshold:
                self._silence_samples += len(audio_np)
                silence_duration = self._silence_samples / self.sample_rate
                
                if silence_duration > self.silence_duration:
                    features["is_silence"] = True
                    if self.on_silence_callback:
                        await self._trigger_callback(
                            self.on_silence_callback,
                            {"duration": silence_duration}
                        )
            else:
                self._silence_samples = 0
                features["is_silence"] = False
            
            # 觸發音訊回呼
            if self.on_audio_callback:
                await self._trigger_callback(
                    self.on_audio_callback,
                    {"audio": audio_data, "features": features}
                )
            
            return features
    
    def _bytes_to_numpy(self, audio_data: bytes) -> np.ndarray:
        """將 bytes 轉換為 numpy array"""
        if self.dtype == "int16":
            return np.frombuffer(audio_data, dtype=np.int16)
        elif self.dtype == "float32":
            return np.frombuffer(audio_data, dtype=np.float32)
        else:
            raise ValueError(f"不支援的資料類型: {self.dtype}")
    
    def _numpy_to_bytes(self, audio_np: np.ndarray) -> bytes:
        """將 numpy array 轉換為 bytes"""
        return audio_np.astype(self.dtype).tobytes()
    
    def _extract_features(self, audio_np: np.ndarray) -> Dict[str, Any]:
        """
        提取音訊特徵
        
        Args:
            audio_np: 音訊資料（numpy array）
            
        Returns:
            特徵字典
        """
        # 轉換為 float32 進行計算
        audio_float = audio_np.astype(np.float32)
        
        # 正規化
        if self.dtype == "int16":
            audio_float /= 32768.0
        
        # 計算 RMS（均方根）
        rms = np.sqrt(np.mean(audio_float ** 2))
        
        # 計算能量
        energy = np.sum(audio_float ** 2)
        
        # 計算峰值
        peak = np.max(np.abs(audio_float))
        
        return {
            "rms": float(rms),
            "energy": float(energy),
            "peak": float(peak),
            "samples": len(audio_np),
            "duration": len(audio_np) / self.sample_rate
        }
    
    async def _trigger_callback(self, callback: Callable, data: Dict[str, Any]):
        """觸發回呼函數"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            self.logger.error(f"回呼執行錯誤: {e}")
    
    def set_audio_callback(self, callback: Callable):
        """設定音訊回呼函數"""
        self.on_audio_callback = callback
    
    def set_silence_callback(self, callback: Callable):
        """設定靜音回呼函數"""
        self.on_silence_callback = callback
    
    def get_buffer_content(self) -> bytes:
        """獲取緩衝區內容"""
        if not self.buffer:
            return b""
        
        audio_np = np.array(list(self.buffer), dtype=self.dtype)
        return self._numpy_to_bytes(audio_np)
    
    def clear_buffer(self):
        """清空緩衝區"""
        self.buffer.clear()
        self._silence_samples = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取串流統計資訊"""
        return {
            "is_active": self.is_active,
            "total_samples": self.total_samples,
            "total_bytes": self.total_bytes,
            "total_duration": self.total_samples / self.sample_rate,
            "buffer_usage": len(self.buffer) / self.buffer_size,
            "silence_threshold": self.silence_threshold,
            "silence_duration": self.silence_duration
        }
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        if "silence_threshold" in config:
            self.silence_threshold = config["silence_threshold"]
            self.logger.info(f"更新靜音閾值: {self.silence_threshold}")
        
        if "silence_duration" in config:
            self.silence_duration = config["silence_duration"]
            self.logger.info(f"更新靜音持續時間: {self.silence_duration}秒")
        
        if "buffer_size" in config:
            self.buffer_size = config["buffer_size"]
            self.buffer = deque(maxlen=self.buffer_size)
            self.logger.info(f"更新緩衝區大小: {self.buffer_size}")