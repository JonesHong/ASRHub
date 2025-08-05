"""
ASR Hub 音訊資料模型
定義音訊相關的資料結構
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class AudioFormat(Enum):
    """支援的音訊格式"""
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
class AudioChunk:
    """
    音訊資料塊
    表示一段音訊資料及其相關資訊
    所有音訊參數都是必要的，不提供預設值
    """
    
    # 音訊資料（原始位元組）
    data: bytes
    
    # 音訊參數（全部必要）
    sample_rate: int  # Hz
    channels: int  # 1=單聲道, 2=立體聲
    format: AudioFormat
    encoding: AudioEncoding
    bits_per_sample: int  # 8, 16, 24, 32
    
    # 時間資訊
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    duration: Optional[float] = None  # 音訊時長（秒）
    
    # 位置資訊（用於串流）
    sequence_number: Optional[int] = None  # 在串流中的序號
    is_final: bool = False  # 是否為串流的最後一塊
    
    # 元資料
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_info: Optional[Dict[str, Any]] = None  # 來源資訊
    
    def __post_init__(self):
        """初始化後處理"""
        # 如果未提供時長，嘗試計算
        if self.duration is None and self.data:
            self.duration = self._calculate_duration()
    
    def _calculate_duration(self) -> float:
        """
        計算音訊時長
        
        Returns:
            時長（秒）
        """
        if self.format != AudioFormat.PCM:
            # 非 PCM 格式無法直接計算
            return 0.0
        
        # 根據位元深度計算每個樣本的位元組數
        bytes_per_sample = self.bits_per_sample // 8
        
        # 計算總樣本數
        total_bytes = len(self.data)
        total_samples = total_bytes / (bytes_per_sample * self.channels)
        
        # 計算時長
        duration = total_samples / self.sample_rate
        return duration
    
    def get_size(self) -> int:
        """獲取資料大小（位元組）"""
        return len(self.data)
    
    def is_empty(self) -> bool:
        """檢查是否為空資料"""
        return len(self.data) == 0
    
    def __len__(self) -> int:
        """返回音訊資料的長度（位元組）"""
        return len(self.data)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format.value,
            "encoding": self.encoding.value,
            "bits_per_sample": self.bits_per_sample,
            "timestamp": self.timestamp,
            "duration": self.duration,
            "sequence_number": self.sequence_number,
            "is_final": self.is_final,
            "size": self.get_size(),
            "metadata": self.metadata
        }
        if self.source_info:
            result["source_info"] = self.source_info
        return result
    
    def clone(self) -> 'AudioChunk':
        """
        建立副本
        
        Returns:
            新的 AudioChunk 實例
        """
        return AudioChunk(
            data=self.data[:],  # 複製資料
            sample_rate=self.sample_rate,
            channels=self.channels,
            format=self.format,
            encoding=self.encoding,
            bits_per_sample=self.bits_per_sample,
            timestamp=self.timestamp,
            duration=self.duration,
            sequence_number=self.sequence_number,
            is_final=self.is_final,
            metadata=self.metadata.copy(),
            source_info=self.source_info.copy() if self.source_info else None
        )


@dataclass
class AudioConfig:
    """音訊配置 - 所有參數都是必要的"""
    sample_rate: int
    channels: int
    format: AudioFormat
    encoding: AudioEncoding
    bits_per_sample: int
    
    def validate(self) -> bool:
        """
        驗證配置是否有效
        
        Returns:
            是否有效
        """
        # 驗證取樣率
        valid_sample_rates = [8000, 16000, 22050, 44100, 48000]
        if self.sample_rate not in valid_sample_rates:
            return False
        
        # 驗證聲道數
        if self.channels not in [1, 2]:
            return False
        
        # 驗證位元深度
        if self.bits_per_sample not in [8, 16, 24, 32]:
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format.value,
            "encoding": self.encoding.value,
            "bits_per_sample": self.bits_per_sample
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioConfig':
        """
        從字典建立實例
        
        Args:
            data: 配置字典
            
        Returns:
            AudioConfig 實例
            
        Raises:
            KeyError: 如果缺少必要參數
            ValueError: 如果參數值無效
        """
        required_keys = ["sample_rate", "channels", "format", "encoding", "bits_per_sample"]
        missing_keys = [k for k in required_keys if k not in data]
        
        if missing_keys:
            raise KeyError(f"配置缺少必要參數：{', '.join(missing_keys)}")
        
        return cls(
            sample_rate=data["sample_rate"],
            channels=data["channels"],
            format=AudioFormat(data["format"]),
            encoding=AudioEncoding(data["encoding"]),
            bits_per_sample=data["bits_per_sample"]
        )