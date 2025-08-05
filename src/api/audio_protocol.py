"""
音訊協議定義
定義各種 API 如何傳遞音訊格式資訊（嚴格模式）
"""

from typing import Dict, Any
from dataclasses import dataclass
from enum import Enum

from src.models.audio import AudioFormat, AudioEncoding


class AudioProtocolError(Exception):
    """音訊協議錯誤"""
    pass


@dataclass
class AudioProtocolConfig:
    """音訊協議配置 - 所有參數必要"""
    sample_rate: int
    channels: int
    format: AudioFormat
    encoding: AudioEncoding
    bits_per_sample: int
    
    def validate(self):
        """驗證配置有效性"""
        # 驗證取樣率
        valid_rates = [8000, 16000, 22050, 24000, 32000, 44100, 48000]
        if self.sample_rate not in valid_rates:
            raise AudioProtocolError(f"無效的取樣率：{self.sample_rate}")
        
        # 驗證聲道數
        if self.channels not in [1, 2]:
            raise AudioProtocolError(f"無效的聲道數：{self.channels}")
        
        # 驗證位元深度
        if self.bits_per_sample not in [8, 16, 24, 32]:
            raise AudioProtocolError(f"無效的位元深度：{self.bits_per_sample}")
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format.value,
            "encoding": self.encoding.value,
            "bits_per_sample": self.bits_per_sample
        }


class HTTPAudioProtocol:
    """HTTP 音訊協議 - 使用 headers 傳遞參數"""
    
    # 標準 header 名稱
    HEADER_SAMPLE_RATE = "X-Audio-Sample-Rate"
    HEADER_CHANNELS = "X-Audio-Channels"
    HEADER_FORMAT = "X-Audio-Format"
    HEADER_ENCODING = "X-Audio-Encoding"
    HEADER_BITS = "X-Audio-Bits"
    
    @classmethod
    def create_headers(cls, config: AudioProtocolConfig) -> Dict[str, str]:
        """創建 HTTP headers"""
        return {
            cls.HEADER_SAMPLE_RATE: str(config.sample_rate),
            cls.HEADER_CHANNELS: str(config.channels),
            cls.HEADER_FORMAT: config.format.value,
            cls.HEADER_ENCODING: config.encoding.value,
            cls.HEADER_BITS: str(config.bits_per_sample)
        }


class WebSocketAudioProtocol:
    """WebSocket 音訊協議 - 首次發送配置消息"""
    
    @staticmethod
    def create_config_message(config: AudioProtocolConfig) -> Dict[str, Any]:
        """創建配置消息"""
        return {
            "type": "audio_config",
            "config": config.to_dict()
        }
    
    @staticmethod
    def create_data_message(audio_data: bytes, sequence: int) -> Dict[str, Any]:
        """創建數據消息"""
        import base64
        return {
            "type": "audio_data",
            "data": base64.b64encode(audio_data).decode('utf-8'),
            "sequence": sequence
        }


class GRPCAudioProtocol:
    """gRPC 音訊協議 - 使用 protobuf 消息"""
    
    @staticmethod
    def validate_audio_config(audio_config: Any) -> AudioProtocolConfig:
        """驗證並轉換 gRPC AudioConfig"""
        # 假設 audio_config 是 protobuf 消息
        return AudioProtocolConfig(
            sample_rate=audio_config.sample_rate_hertz,
            channels=audio_config.audio_channel_count or 1,
            format=AudioFormat.PCM,  # gRPC 通常使用 PCM
            encoding=AudioEncoding.LINEAR16,  # 根據 encoding 欄位映射
            bits_per_sample=16  # gRPC 標準
        )