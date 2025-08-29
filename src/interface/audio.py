"""音訊資料模型

定義音訊相關的資料結構。
"""

from dataclasses import dataclass
from typing import TypedDict, Union, Optional
import numpy as np
import time


@dataclass
class AudioChunk:
    """音訊片段資料結構。
    
    Attributes:
        data: 音訊資料（numpy array 或 bytes）
        sample_rate: 取樣率
        channels: 聲道數
        timestamp: 時間戳記
        metadata: 額外的中繼資料
    """
    data: Union[np.ndarray, bytes]
    sample_rate: int = 16000
    channels: int = 1
    timestamp: Optional[float] = None
    metadata: Optional[dict] = None
    
    def __post_init__(self):
        """初始化後處理。"""
        if self.timestamp is None:
            self.timestamp = time.time()
        
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def duration(self) -> float:
        """計算音訊時長（秒）。"""
        if isinstance(self.data, np.ndarray):
            return len(self.data) / self.sample_rate
        elif isinstance(self.data, bytes):
            # 假設 16-bit 音訊
            samples = len(self.data) // 2
            return samples / self.sample_rate
        return 0.0
    
    @property
    def shape(self) -> tuple:
        """取得資料形狀。"""
        if isinstance(self.data, np.ndarray):
            return self.data.shape
        elif isinstance(self.data, bytes):
            return (len(self.data) // 2,) if self.channels == 1 else (len(self.data) // 4, 2)
        return (0,)
    
    def to_numpy(self, preserve_dtype: bool = False) -> np.ndarray:
        """轉換為 numpy array。
        
        Args:
            preserve_dtype: 如果為 True，保持原始 dtype (int16)；
                           如果為 False，轉換為 float32 [-1, 1] (預設行為)
        """
        if isinstance(self.data, np.ndarray):
            return self.data
        elif isinstance(self.data, bytes):
            # 假設 16-bit PCM
            audio = np.frombuffer(self.data, dtype=np.int16)
            if self.channels == 2:
                audio = audio.reshape(-1, 2)
            
            if preserve_dtype:
                return audio  # 保持 int16 格式
            else:
                return audio.astype(np.float32) / 32768.0  # 歸一化到 [-1, 1]
        return np.array([])
    
    def to_bytes(self) -> bytes:
        """轉換為 bytes。"""
        if isinstance(self.data, bytes):
            return self.data
        elif isinstance(self.data, np.ndarray):
            # 轉換為 16-bit PCM
            if self.data.dtype == np.float32 or self.data.dtype == np.float64:
                audio = (self.data * 32768.0).astype(np.int16)
            else:
                audio = self.data.astype(np.int16)
            return audio.tobytes()
        return b''
    


class AudioMeta(TypedDict):
    """
    音訊元資料
    """
    sample_rate: int
    channels: int
    format: str