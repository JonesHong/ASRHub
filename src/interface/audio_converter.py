"""音訊轉換器介面

定義音訊格式轉換的標準介面。
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from src.interface.audio import AudioChunk


class IAudioConverter(ABC):
    """音訊轉換器介面。
    
    負責將各種格式的音訊轉換為 VAD、Wake Word、ASR 所需的格式。
    """
    
    @abstractmethod
    def convert_chunk(
        self,
        chunk: AudioChunk,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> AudioChunk:
        """轉換單一音訊片段。
        
        Args:
            chunk: 原始音訊片段
            target_sample_rate: 目標取樣率 (預設 16000 Hz)
            target_channels: 目標聲道數 (預設 1 單聲道)
            target_format: 目標格式 (預設 pcm_s16le)
            
        Returns:
            轉換後的音訊片段
        """
        pass
    
    @abstractmethod
    def convert_batch(
        self,
        chunks: List[AudioChunk],
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> List[AudioChunk]:
        """批次轉換音訊片段。
        
        Args:
            chunks: 原始音訊片段列表
            target_sample_rate: 目標取樣率
            target_channels: 目標聲道數
            target_format: 目標格式
            
        Returns:
            轉換後的音訊片段列表
        """
        pass
    
    @abstractmethod
    def needs_conversion(
        self,
        chunk: AudioChunk,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> bool:
        """檢查是否需要轉換。
        
        Args:
            chunk: 音訊片段
            target_sample_rate: 目標取樣率
            target_channels: 目標聲道數
            target_format: 目標格式
            
        Returns:
            需要轉換回傳 True，否則 False
        """
        pass