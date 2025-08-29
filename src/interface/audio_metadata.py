"""音訊元資料介面

定義客戶端必須提供的音訊參數資訊
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class AudioFormat(Enum):
    """音訊格式枚舉"""
    PCM_S16LE = "pcm_s16le"  # 16-bit signed little-endian
    PCM_F32LE = "pcm_f32le"  # 32-bit float little-endian
    PCM_S24LE = "pcm_s24le"  # 24-bit signed little-endian
    OPUS = "opus"
    WEBM = "webm"
    OGG = "ogg"


@dataclass
class AudioMetadata:
    """音訊元資料
    
    客戶端必須提供這些資訊，系統才能正確處理音訊
    """
    sample_rate: int  # 採樣率 (Hz) - 必須由客戶端提供
    channels: int  # 聲道數 (1=mono, 2=stereo) - 必須由客戶端提供
    format: str  # 音訊格式 (pcm_s16le, pcm_f32le, etc.) - 必須由客戶端提供
    bits_per_sample: Optional[int] = None  # 每個樣本的位元數 (16, 24, 32)
    endianness: str = "little"  # 位元組順序 (little, big)
    
    # 可選的額外資訊
    device_info: Optional[Dict[str, Any]] = None  # 裝置資訊
    timestamp: Optional[float] = None  # 時間戳記
    duration_ms: Optional[int] = None  # 音訊片段長度（毫秒）
    
    def validate(self) -> bool:
        """驗證元資料是否有效"""
        # 檢查必要參數
        if not self.sample_rate or self.sample_rate <= 0:
            raise ValueError(f"Invalid sample_rate: {self.sample_rate}")
        
        if self.channels not in [1, 2]:
            raise ValueError(f"Invalid channels: {self.channels}, must be 1 or 2")
        
        if not self.format:
            raise ValueError("Audio format is required")
        
        # 檢查採樣率是否為常見值
        common_rates = [8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000, 192000]
        if self.sample_rate not in common_rates:
            # 警告但不拒絕
            from src.utils.logger import logger
            logger.warning(f"Unusual sample rate: {self.sample_rate}Hz")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'format': self.format,
            'bits_per_sample': self.bits_per_sample,
            'endianness': self.endianness,
            'device_info': self.device_info,
            'timestamp': self.timestamp,
            'duration_ms': self.duration_ms
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioMetadata':
        """從字典建立"""
        return cls(
            sample_rate=data.get('sample_rate', 16000),
            channels=data.get('channels', 1),
            format=data.get('format', 'pcm_s16le'),
            bits_per_sample=data.get('bits_per_sample'),
            endianness=data.get('endianness', 'little'),
            device_info=data.get('device_info'),
            timestamp=data.get('timestamp'),
            duration_ms=data.get('duration_ms')
        )