"""
簡化的音訊資料模型
整合 AudioChunk, AudioMetadata, AudioConfig 為統一的資料結構
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import numpy as np


class AudioSampleFormat(Enum):
    """音頻取樣格式枚舉"""
    INT16 = "int16"
    INT24 = "int24"
    INT32 = "int32"
    FLOAT32 = "float32"
    
    @property
    def bytes_per_sample(self) -> int:
        """每個樣本的字節數"""
        return {
            AudioSampleFormat.INT16: 2,
            AudioSampleFormat.INT24: 3,
            AudioSampleFormat.INT32: 4,
            AudioSampleFormat.FLOAT32: 4
        }[self]
    
    @property
    def numpy_dtype(self):
        """對應的 numpy 數據類型"""
        return {
            AudioSampleFormat.INT16: np.int16,
            AudioSampleFormat.INT24: None,  # numpy 沒有原生 int24
            AudioSampleFormat.INT32: np.int32,
            AudioSampleFormat.FLOAT32: np.float32
        }[self]


class AudioContainerFormat(Enum):
    """支援的音訊容器格式"""
    PCM = "pcm"
    WAV = "wav"
    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    WEBM = "webm"
    M4A = "m4a"


class AudioEncoding(Enum):
    """音訊編碼格式"""
    LINEAR16 = "linear16"  # 16-bit PCM
    LINEAR32 = "linear32"  # 32-bit PCM
    MULAW = "mulaw"
    ALAW = "alaw"
    FLOAT32 = "float32"


@dataclass
class AudioMetadata:
    """
    統一的音頻元數據
    整合了原本的 AudioMetadata 和 AudioConfig
    """
    sample_rate: int
    channels: int
    format: AudioSampleFormat
    container_format: AudioContainerFormat = AudioContainerFormat.PCM
    encoding: AudioEncoding = AudioEncoding.LINEAR16
    
    @property
    def bytes_per_frame(self) -> int:
        """每幀（所有聲道的一個採樣點）的字節數"""
        return self.channels * self.format.bytes_per_sample
    
    def calculate_duration(self, byte_size: int) -> float:
        """從字節大小計算時長（秒）"""
        total_frames = byte_size / self.bytes_per_frame
        return total_frames / self.sample_rate
    
    def calculate_byte_size(self, duration: float) -> int:
        """從時長計算字節大小"""
        total_frames = int(duration * self.sample_rate)
        return total_frames * self.bytes_per_frame
    
    def validate(self) -> bool:
        """驗證配置是否有效"""
        # 驗證取樣率
        valid_sample_rates = [8000, 16000, 22050, 44100, 48000]
        if self.sample_rate not in valid_sample_rates:
            return False
        
        # 驗證聲道數
        if self.channels not in [1, 2]:
            return False
        
        return True
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'format': self.format.value,
            'container_format': self.container_format.value,
            'encoding': self.encoding.value
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AudioMetadata':
        """從字典創建"""
        return cls(
            sample_rate=data['sample_rate'],
            channels=data['channels'],
            format=AudioSampleFormat(data['format']),
            container_format=AudioContainerFormat(data.get('container_format', 'pcm')),
            encoding=AudioEncoding(data.get('encoding', 'linear16'))
        )


@dataclass
class AudioChunk:
    """
    簡化的音訊資料塊
    使用組合模式整合 AudioMetadata
    """
    data: bytes
    metadata: AudioMetadata
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    sequence_number: Optional[int] = None
    is_final: bool = False
    
    # 額外資訊（可選）
    source_info: Optional[Dict[str, Any]] = None
    
    @property
    def duration(self) -> float:
        """計算音訊時長"""
        return self.metadata.calculate_duration(len(self.data))
    
    @property
    def size(self) -> int:
        """獲取資料大小（位元組）"""
        return len(self.data)
    
    def is_empty(self) -> bool:
        """檢查是否為空資料"""
        return len(self.data) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "metadata": self.metadata.to_dict(),
            "timestamp": self.timestamp,
            "duration": self.duration,
            "sequence_number": self.sequence_number,
            "is_final": self.is_final,
            "size": self.size
        }
        if self.source_info:
            result["source_info"] = self.source_info
        return result
    
    def clone(self) -> 'AudioChunk':
        """建立副本"""
        return AudioChunk(
            data=self.data[:],  # 複製資料
            metadata=AudioMetadata(
                sample_rate=self.metadata.sample_rate,
                channels=self.metadata.channels,
                format=self.metadata.format,
                container_format=self.metadata.container_format,
                encoding=self.metadata.encoding
            ),
            timestamp=self.timestamp,
            sequence_number=self.sequence_number,
            is_final=self.is_final,
            source_info=self.source_info.copy() if self.source_info else None
        )


# 預定義的常用格式
COMMON_FORMATS = {
    'cd_quality': AudioMetadata(44100, 2, AudioSampleFormat.INT16),
    'dvd_quality': AudioMetadata(48000, 2, AudioSampleFormat.INT16),
    'hifi_quality': AudioMetadata(48000, 2, AudioSampleFormat.INT24),
    'telephone': AudioMetadata(8000, 1, AudioSampleFormat.INT16),
    'voip': AudioMetadata(16000, 1, AudioSampleFormat.INT16),
    'broadcast': AudioMetadata(48000, 2, AudioSampleFormat.INT16),
    'podcast': AudioMetadata(44100, 1, AudioSampleFormat.INT16),
}