"""
統一音訊處理模組
整合所有音訊相關功能，減少重複程式碼
"""

from .models import (
    AudioChunk, 
    AudioMetadata, 
    AudioSampleFormat,
    AudioContainerFormat,
    AudioEncoding,
    COMMON_FORMATS
)
from .processor import AudioProcessor, AudioFeatures
from .converter import AudioConverter
from .utils import (
    create_audio_chunk, create_audio_chunk_from_params,
    AudioPacket, create_audio_packet, parse_audio_packet
)

__all__ = [
    # 資料模型
    'AudioChunk',
    'AudioMetadata', 
    'AudioSampleFormat',
    'AudioContainerFormat',
    'AudioEncoding',
    'AudioFeatures',
    'COMMON_FORMATS',
    # 處理器
    'AudioProcessor',
    'AudioConverter',
    # 工具函數
    'create_audio_chunk',
    'create_audio_chunk_from_params',
    'AudioPacket',
    'create_audio_packet', 
    'parse_audio_packet',
]