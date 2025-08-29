"""音訊轉換服務 (Stateless Service)

提供多種音訊轉換方式：
- ScipyConverter: 使用 SciPy/NumPy，支援 GPU 加速
- FFmpegConverter: 使用 FFmpeg，支援幾乎所有格式

這是無狀態服務，所有方法都是獨立的，可並行處理多個 session。
"""

from typing import Optional, Union
from pathlib import Path

from src.interface.audio import AudioChunk
from src.utils.logger import logger
from src.config.manager import ConfigManager


class AudioConverterService:
    """統一的音訊轉換服務 (Stateless)。
    
    自動選擇最適合的轉換器：
    - 檔案轉換優先使用 FFmpeg
    - 即時串流優先使用 SciPy
    - 自動 fallback
    """
    
    def __init__(self):
        """初始化可用的轉換器。"""
        self.config = ConfigManager()
        self.converter_config = self.config.services.audio_converter
        
        self.scipy_converter = None
        self.ffmpeg_converter = None
        
        # 根據配置載入 SciPy 轉換器
        if self.converter_config.scipy.enabled:
            try:
                from .scipy_converter import scipy_converter
                self.scipy_converter = scipy_converter
                logger.info("ScipyConverter loaded")
            except ImportError as e:
                logger.warning(f"ScipyConverter not available: {e}")
        
        # 根據配置載入 FFmpeg 轉換器
        if self.converter_config.ffmpeg.enabled:
            try:
                from .ffmpeg_converter import ffmpeg_converter
                if ffmpeg_converter.is_available():
                    self.ffmpeg_converter = ffmpeg_converter
                    logger.info("FFmpegConverter loaded")
                else:
                    logger.warning("FFmpeg not found in system")
            except Exception as e:
                logger.warning(f"FFmpegConverter not available: {e}")
        
        if not self.scipy_converter and not self.ffmpeg_converter:
            logger.error("No audio converter available!")
    
    def convert_chunk(
        self,
        chunk: AudioChunk,
        target_sample_rate: Optional[int] = None,
        target_channels: Optional[int] = None,
        target_format: Optional[str] = None,
        prefer_ffmpeg: bool = False
    ) -> Optional[AudioChunk]:
        """轉換音訊片段。
        
        Args:
            chunk: 原始音訊片段
            target_sample_rate: 目標取樣率 (None = 使用配置預設值)
            target_channels: 目標聲道數 (None = 使用配置預設值)
            target_format: 目標格式 (None = 使用配置預設值)
            prefer_ffmpeg: 是否優先使用 FFmpeg
            
        Returns:
            轉換後的音訊片段
        """
        # 使用配置預設值
        target_sample_rate = target_sample_rate or self.converter_config.defaults.target_sample_rate
        target_channels = target_channels or self.converter_config.defaults.target_channels
        target_format = target_format or self.converter_config.defaults.target_format
        
        # 選擇轉換器
        if prefer_ffmpeg and self.ffmpeg_converter:
            result = self.ffmpeg_converter.convert_chunk(
                chunk, 
                target_sample_rate=target_sample_rate, 
                target_channels=target_channels, 
                target_format=target_format
            )
            if result:
                return result
            logger.warning("FFmpeg conversion failed, trying SciPy")
        
        # 使用 SciPy
        if self.scipy_converter:
            return self.scipy_converter.convert_chunk(
                chunk, 
                target_sample_rate=target_sample_rate, 
                target_channels=target_channels, 
                target_format=target_format
            )
        
        # 最後嘗試 FFmpeg
        if self.ffmpeg_converter and not prefer_ffmpeg:
            return self.ffmpeg_converter.convert_chunk(
                chunk, 
                target_sample_rate=target_sample_rate, 
                target_channels=target_channels, 
                target_format=target_format
            )
        
        logger.error("No converter available for chunk conversion")
        return None
    
    def convert_file(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        bit_depth: int = 16
    ) -> bool:
        """轉換音訊檔案。
        
        優先使用 FFmpeg 處理檔案。
        """
        # 使用配置預設值
        sample_rate = sample_rate or self.converter_config.defaults.target_sample_rate
        channels = channels or self.converter_config.defaults.target_channels
        
        if self.ffmpeg_converter:
            return self.ffmpeg_converter.convert_file(
                input_path, output_path,
                sample_rate, channels, bit_depth
            )
        
        logger.error("FFmpeg not available for file conversion")
        return False
    
    def convert_for_session(
        self,
        session_id: str,
        target_sample_rate: Optional[int] = None,
        target_channels: Optional[int] = None,
        target_format: Optional[str] = None,
        max_chunks: int = 100
    ):
        """從 audio_queue 拉取並轉換。
        
        優先使用 SciPy (支援批次 GPU 加速)。
        """
        # 使用配置預設值
        target_sample_rate = target_sample_rate or self.converter_config.defaults.target_sample_rate
        target_channels = target_channels or self.converter_config.defaults.target_channels
        target_format = target_format or self.converter_config.defaults.target_format
        
        if self.scipy_converter:
            return self.scipy_converter.convert_for_session(
                session_id, target_sample_rate,
                target_channels, target_format, max_chunks
            )
        
        # Fallback: 用 FFmpeg 逐個處理
        if self.ffmpeg_converter:
            from src.core.audio_queue_manager import audio_queue
            
            chunks = audio_queue.pull(session_id, count=max_chunks)
            converted = []
            
            for chunk in chunks:
                result = self.ffmpeg_converter.convert_chunk(
                    chunk, target_sample_rate, target_channels, target_format
                )
                if result:
                    converted.append(result)
            
            return converted
        
        logger.error("No converter available for session conversion")
        return []
    
    def convert_uploaded_file(
        self,
        file_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None
    ) -> Optional[Path]:
        """轉換上傳的檔案。
        
        使用 FFmpeg 處理各種格式。
        """
        if self.ffmpeg_converter:
            return self.ffmpeg_converter.convert_uploaded_file(
                file_path, output_dir
            )
        
        logger.error("FFmpeg not available for uploaded file conversion")
        return None


# 匯出統一服務
audio_converter_service: AudioConverterService = AudioConverterService()

# 相容性匯出
audio_converter = audio_converter_service  # 簡短名稱

