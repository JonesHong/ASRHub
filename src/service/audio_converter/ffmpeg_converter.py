"""FFmpeg 音訊轉換器

使用 FFmpeg 處理各種音訊格式轉換，特別適合處理上傳的音訊檔案。
支援幾乎所有音訊格式。
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union
import shutil

from src.interface.audio import AudioChunk
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.interface.exceptions import ServiceError, ConversionError
from src.config.manager import ConfigManager


class FFmpegConverter(SingletonMixin):
    """FFmpeg 音訊轉換器。
    
    特性：
    - 支援幾乎所有音訊格式 (mp3, wav, flac, aac, ogg, m4a, wma 等)
    - 可處理檔案和二進位資料
    - 支援串流處理
    - 高品質轉換選項
    - 使用 SingletonMixin 確保單例
    """
    
    def __init__(self):
        """初始化 FFmpeg 轉換器。"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 載入配置
            config = ConfigManager()
            self.ffmpeg_config = config.services.audio_converter.ffmpeg
            self.defaults_config = config.services.audio_converter.defaults
            
            self.ffmpeg_path = self._find_ffmpeg()
            self.timeout = self.ffmpeg_config.timeout
            
            if self.ffmpeg_path:
                logger.info(f"FFmpegConverter initialized with: {self.ffmpeg_path}, timeout={self.timeout}s")
                self._log_ffmpeg_version()
            else:
                logger.warning("FFmpeg not found! Please install FFmpeg")
    
    def _find_ffmpeg(self) -> Optional[str]:
        """尋找 FFmpeg 執行檔。"""
        # 優先使用配置中的路徑
        configured_path = self.ffmpeg_config.path
        if configured_path and configured_path != 'ffmpeg':
            if os.path.exists(configured_path):
                return configured_path
            logger.warning(f"Configured FFmpeg path not found: {configured_path}")
        
        # 嘗試直接使用系統 ffmpeg
        if shutil.which('ffmpeg'):
            return 'ffmpeg'
        
        # Windows 常見位置
        windows_paths = [
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"D:\ffmpeg\bin\ffmpeg.exe",
        ]
        
        for path in windows_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _log_ffmpeg_version(self):
        """記錄 FFmpeg 版本資訊。"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                logger.debug(f"FFmpeg version: {version_line}")
        except Exception as e:
            logger.warning(f"Could not get FFmpeg version: {e}")
    
    def is_available(self) -> bool:
        """檢查 FFmpeg 是否可用。"""
        return self.ffmpeg_path is not None
    
    def convert_file(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        sample_rate: int = 16000,
        channels: int = 1,
        bit_depth: int = 16,
        format: Optional[str] = None
    ) -> bool:
        """轉換音訊檔案。
        
        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            sample_rate: 取樣率 (Hz)
            channels: 聲道數
            bit_depth: 位元深度
            format: 輸出格式 (從副檔名自動判斷)
            
        Returns:
            成功回傳 True
        """
        if not self.is_available():
            raise ServiceError("FFmpeg not available")
        
        # 建構 FFmpeg 命令
        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),          # 輸入檔案
            '-ar', str(sample_rate),         # 取樣率
            '-ac', str(channels),            # 聲道數
            '-y',                            # 覆寫輸出檔案
        ]
        
        # 設定輸出格式
        if format:
            cmd.extend(['-f', format])
        
        # 設定位元深度
        if bit_depth == 16:
            cmd.extend(['-sample_fmt', 's16'])
        elif bit_depth == 32:
            cmd.extend(['-sample_fmt', 'f32le'])
        
        # 加入輸出檔案
        cmd.append(str(output_path))
        
        try:
            logger.debug(f"FFmpeg command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Converted {input_path} to {output_path}")
                return True
            else:
                logger.error(f"FFmpeg error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timeout")
            return False
        except Exception as e:
            logger.error(f"FFmpeg conversion failed: {e}")
            return False
    
    def convert_chunk(
        self,
        chunk: AudioChunk,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> Optional[AudioChunk]:
        """轉換音訊片段。
        
        使用 FFmpeg 管道處理，避免寫入暫存檔案。
        
        Args:
            chunk: 原始音訊片段
            target_sample_rate: 目標取樣率
            target_channels: 目標聲道數
            target_format: 目標格式
            
        Returns:
            轉換後的音訊片段
        """
        if not self.is_available():
            logger.error("FFmpeg not available")
            return None
        
        if not chunk.data:
            return chunk
        
        # 準備輸入格式參數 - 預設為 PCM
        input_format = 's16le'  # 預設為 16-bit PCM
        
        # 建構 FFmpeg 命令 (使用管道)
        cmd = [
            self.ffmpeg_path,
            '-f', input_format,                    # 輸入格式
            '-ar', str(chunk.sample_rate),         # 輸入取樣率
            '-ac', str(chunk.channels),            # 輸入聲道
            '-i', 'pipe:0',                        # 從 stdin 讀取
            '-f', self._get_ffmpeg_format(target_format),  # 輸出格式
            '-ar', str(target_sample_rate),        # 輸出取樣率
            '-ac', str(target_channels),           # 輸出聲道
            'pipe:1'                                # 輸出到 stdout
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 送入資料並取得結果
            stdout, stderr = process.communicate(input=chunk.data, timeout=self.timeout)
            
            if process.returncode == 0:
                return AudioChunk(
                    data=stdout,
                    timestamp=chunk.timestamp,
                    sample_rate=target_sample_rate,
                    channels=target_channels
                )
            else:
                logger.error(f"FFmpeg pipe error: {stderr.decode('utf-8', errors='ignore')}")
                return None
                
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error("FFmpeg pipe timeout")
            return None
        except Exception as e:
            logger.error(f"FFmpeg pipe failed: {e}")
            return None
    
    def convert_stream(
        self,
        input_format: str,
        output_format: str,
        sample_rate: int = 16000,
        channels: int = 1,
        input_sample_rate: Optional[int] = None,
        input_channels: Optional[int] = None
    ) -> Optional[subprocess.Popen]:
        """建立 FFmpeg 串流轉換處理程序。
        
        Returns:
            FFmpeg process 用於串流處理
        """
        if not self.is_available():
            return None
        
        cmd = [
            self.ffmpeg_path,
            '-f', self._get_ffmpeg_format(input_format),
        ]
        
        # 加入輸入參數
        if input_sample_rate:
            cmd.extend(['-ar', str(input_sample_rate)])
        if input_channels:
            cmd.extend(['-ac', str(input_channels)])
        
        cmd.extend([
            '-i', 'pipe:0',                              # 從 stdin 讀取
            '-f', self._get_ffmpeg_format(output_format),
            '-ar', str(sample_rate),
            '-ac', str(channels),
            'pipe:1'                                      # 輸出到 stdout
        ])
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=4096
            )
            
            logger.info("FFmpeg stream converter started")
            return process
            
        except Exception as e:
            logger.error(f"Failed to start FFmpeg stream: {e}")
            return None
    
    def extract_metadata(self, file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """提取音訊檔案的 metadata。
        
        Returns:
            包含 duration, sample_rate, channels, codec 等資訊
        """
        if not self.is_available():
            return None
        
        cmd = [
            self.ffmpeg_path,
            '-i', str(file_path),
            '-f', 'null',
            '-'
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # 解析 stderr (FFmpeg 輸出資訊到 stderr)
            stderr = result.stderr
            metadata = {}
            
            # 尋找 Duration
            if 'Duration:' in stderr:
                duration_str = stderr.split('Duration:')[1].split(',')[0].strip()
                # 轉換 HH:MM:SS.ms 格式
                parts = duration_str.split(':')
                if len(parts) == 3:
                    hours, minutes, seconds = parts
                    duration = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
                    metadata['duration'] = duration
            
            # 尋找 Audio 資訊
            if 'Audio:' in stderr:
                audio_line = stderr.split('Audio:')[1].split('\n')[0]
                
                # 取樣率
                if 'Hz' in audio_line:
                    hz = audio_line.split('Hz')[0].split()[-1]
                    metadata['sample_rate'] = int(hz)
                
                # 聲道
                if 'stereo' in audio_line:
                    metadata['channels'] = 2
                elif 'mono' in audio_line:
                    metadata['channels'] = 1
                
                # Codec
                codec = audio_line.split(',')[0].strip()
                metadata['codec'] = codec
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
            return None
    
    def _get_ffmpeg_format(self, format_str: str) -> str:
        """轉換格式字串為 FFmpeg 格式名稱。"""
        format_map = {
            'pcm_s16le': 's16le',
            'pcm_f32le': 'f32le',
            'pcm': 's16le',
            'wav': 'wav',
            'mp3': 'mp3',
            'flac': 'flac',
            'ogg': 'ogg',
            'aac': 'aac',
            'm4a': 'mp4',
            'wma': 'asf',
        }
        
        return format_map.get(format_str.lower(), format_str.lower())
    
    def convert_uploaded_file(
        self,
        file_path: Union[str, Path],
        output_dir: Union[str, Path] = None
    ) -> Optional[Path]:
        """轉換上傳的音訊檔案為標準格式。
        
        Args:
            file_path: 上傳的檔案路徑
            output_dir: 輸出目錄 (預設為同目錄)
            
        Returns:
            轉換後的檔案路徑
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        # 提取 metadata
        metadata = self.extract_metadata(file_path)
        if not metadata:
            logger.error(f"Could not extract metadata from {file_path}")
            return None
        
        logger.info(f"Input file metadata: {metadata}")
        
        # 準備輸出路徑
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = file_path.parent
        
        output_path = output_dir / f"{file_path.stem}_converted.wav"
        
        # 轉換為標準格式 (16kHz, mono, WAV)
        success = self.convert_file(
            input_path=file_path,
            output_path=output_path,
            sample_rate=16000,
            channels=1,
            bit_depth=16,
            format='wav'
        )
        
        if success:
            return output_path
        else:
            return None


# 模組級單例實例
ffmpeg_converter: FFmpegConverter = FFmpegConverter()