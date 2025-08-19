#!/usr/bin/env python3
"""
基於 FFmpeg 的音頻格式轉換 Operator
使用 FFmpeg 進行全格式支援的音頻轉換
"""

import subprocess
import tempfile
import os
import io
from typing import Optional, Dict, Any
import numpy as np

from .base import AudioFormatOperatorBase
from src.audio import AudioContainerFormat, AudioMetadata, AudioSampleFormat
from src.core.exceptions import AudioFormatError
from src.utils.logger import logger


class FFmpegAudioFormatOperator(AudioFormatOperatorBase):
    """
    使用 FFmpeg 進行音頻格式轉換的 Operator
    支援更多的音頻格式和編碼器
    """
    
    def __init__(self, operator_id: str = 'ffmpeg', target_metadata: Optional[AudioMetadata] = None):
        """
        初始化 FFmpeg 音頻格式轉換 Operator
        
        Args:
            operator_id: 操作器識別ID
            target_metadata: 目標音頻格式元數據
        """
        super().__init__(operator_id, target_metadata)
        
        # FFmpeg 特定的配置
        self.ffmpeg_path = 'ffmpeg'
        self.ffprobe_path = 'ffprobe'
        self.additional_args = []  # 額外的 ffmpeg 參數
        self.use_pydub_fallback = True  # 是否使用 pydub 作為備份
        
        # 檢查 FFmpeg 是否可用
        self._check_ffmpeg_available()
        
        logger.info(f"FFmpegAudioFormatOperator[{self.operator_id}] 初始化完成")
    
    def _check_ffmpeg_available(self):
        """檢查 FFmpeg 是否可用"""
        try:
            subprocess.run([self.ffmpeg_path, '-version'], 
                         capture_output=True, check=True)
            self.ffmpeg_available = True
            logger.debug(f"[{self.operator_id}] FFmpeg 可用")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.ffmpeg_available = False
            logger.warning(f"[{self.operator_id}] FFmpeg 不可用")
            if not self.use_pydub_fallback:
                raise AudioFormatError("FFmpeg 未安裝且未啟用 pydub 備份")
    
    async def _convert_format(self, audio_data: bytes, 
                            from_metadata: AudioMetadata,
                            to_metadata: AudioMetadata) -> bytes:
        """
        使用 FFmpeg 執行音頻格式轉換
        
        Args:
            audio_data: 原始音頻數據
            from_metadata: 來源音頻元數據
            to_metadata: 目標音頻元數據
            
        Returns:
            轉換後的音頻數據
        """
        if self.ffmpeg_available:
            return await self._convert_with_ffmpeg(audio_data, from_metadata, to_metadata)
        elif self.use_pydub_fallback:
            return await self._convert_with_pydub(audio_data, from_metadata, to_metadata)
        else:
            raise AudioFormatError("無可用的音頻轉換後端")
    
    async def _convert_with_ffmpeg(self, audio_data: bytes,
                                  from_metadata: AudioMetadata,
                                  to_metadata: AudioMetadata) -> bytes:
        """使用 FFmpeg 進行轉換"""
        try:
            # 創建臨時文件
            with tempfile.NamedTemporaryFile(suffix=self._get_file_extension(from_metadata), 
                                           delete=False) as temp_input:
                temp_input.write(audio_data)
                temp_input.flush()
                
                # 構建 FFmpeg 命令
                cmd = self._build_ffmpeg_command(
                    temp_input.name,
                    from_metadata,
                    to_metadata
                )
                
                # 執行轉換
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                pcm_data, error = process.communicate()
                
                # 清理臨時文件
                os.unlink(temp_input.name)
                
                if process.returncode != 0:
                    error_msg = error.decode('utf-8', errors='ignore')
                    raise AudioFormatError(f"FFmpeg 轉換失敗: {error_msg}")
                
                # 確保音頻數據長度正確
                if to_metadata.format in [AudioSampleFormat.INT16, AudioSampleFormat.INT32]:
                    bytes_per_sample = 2 if to_metadata.format == AudioSampleFormat.INT16 else 4
                    expected_alignment = bytes_per_sample * to_metadata.channels
                    if len(pcm_data) % expected_alignment != 0:
                        padding_needed = expected_alignment - (len(pcm_data) % expected_alignment)
                        logger.warning(f"音頻數據未對齊，添加 {padding_needed} 字節填充")
                        pcm_data += b'\x00' * padding_needed
                
                logger.debug(
                    f"[{self.operator_id}] FFmpeg 轉換成功: "
                    f"{len(audio_data)} bytes -> {len(pcm_data)} bytes"
                )
                
                return pcm_data
                
        except Exception as e:
            logger.error(f"[{self.operator_id}] FFmpeg 轉換失敗: {e}")
            raise AudioFormatError(f"FFmpeg 轉換失敗: {str(e)}")
    
    async def _convert_with_pydub(self, audio_data: bytes,
                                 from_metadata: AudioMetadata,
                                 to_metadata: AudioMetadata) -> bytes:
        """使用 pydub 作為備份進行轉換"""
        try:
            import pydub
            from pydub import AudioSegment
            
            # 將 bytes 轉換為 AudioSegment
            audio = AudioSegment.from_file(
                io.BytesIO(audio_data),
                format=self._get_format_name(from_metadata)
            )
            
            # 轉換參數
            audio = audio.set_frame_rate(to_metadata.sample_rate)
            audio = audio.set_channels(to_metadata.channels)
            
            # 設置採樣寬度
            if to_metadata.format == AudioSampleFormat.INT16:
                audio = audio.set_sample_width(2)
            elif to_metadata.format == AudioSampleFormat.INT32:
                audio = audio.set_sample_width(4)
            elif to_metadata.format == AudioSampleFormat.FLOAT32:
                # pydub 不直接支持 float32，需要特殊處理
                samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
                samples = samples / (2 ** (audio.sample_width * 8 - 1))
                return samples.tobytes()
            
            # 導出為 PCM
            pcm_data = audio.raw_data
            
            logger.debug(
                f"[{self.operator_id}] pydub 轉換成功: "
                f"{len(audio_data)} bytes -> {len(pcm_data)} bytes"
            )
            
            return pcm_data
            
        except ImportError:
            raise AudioFormatError("需要安裝 pydub 來使用備份轉換")
        except Exception as e:
            raise AudioFormatError(f"pydub 轉換失敗: {str(e)}")
    
    def _build_ffmpeg_command(self, input_file: str,
                             from_metadata: AudioMetadata,
                             to_metadata: AudioMetadata) -> list:
        """構建 FFmpeg 命令"""
        cmd = [
            self.ffmpeg_path,
            '-i', input_file,
            '-f', self._get_ffmpeg_format(to_metadata.format),
            '-acodec', self._get_ffmpeg_codec(to_metadata.format),
            '-ar', str(to_metadata.sample_rate),
            '-ac', str(to_metadata.channels),
        ]
        
        # 添加品質相關參數
        if self.quality == 'high':
            cmd.extend(['-af', 'aresample=resampler=soxr'])
        
        # 添加額外參數
        cmd.extend(self.additional_args)
        
        # 輸出到 stdout
        cmd.append('-')
        
        return cmd
    
    def _get_ffmpeg_format(self, audio_format: AudioSampleFormat) -> str:
        """獲取 FFmpeg 格式名稱"""
        format_map = {
            AudioSampleFormat.INT16: 's16le',
            AudioSampleFormat.INT24: 's24le',
            AudioSampleFormat.INT32: 's32le',
            AudioSampleFormat.FLOAT32: 'f32le',
        }
        return format_map.get(audio_format, 's16le')
    
    def _get_ffmpeg_codec(self, audio_format: AudioSampleFormat) -> str:
        """獲取 FFmpeg 編解碼器名稱"""
        codec_map = {
            AudioSampleFormat.INT16: 'pcm_s16le',
            AudioSampleFormat.INT24: 'pcm_s24le',
            AudioSampleFormat.INT32: 'pcm_s32le',
            AudioSampleFormat.FLOAT32: 'pcm_f32le',
        }
        return codec_map.get(audio_format, 'pcm_s16le')
    
    def _get_file_extension(self, metadata: AudioMetadata) -> str:
        """根據元數據獲取文件擴展名"""
        # 簡單映射，實際可能需要更複雜的邏輯
        if metadata.format == AudioSampleFormat.FLOAT32:
            return '.wav'
        return '.pcm'
    
    def _get_format_name(self, metadata: AudioMetadata) -> str:
        """獲取 pydub 格式名稱"""
        # 簡單映射
        if metadata.format in [AudioSampleFormat.INT16, AudioSampleFormat.INT32]:
            return 'raw'
        return 'wav'
    
    async def probe_audio_info(self, audio_data: bytes) -> Dict[str, Any]:
        """
        使用 ffprobe 獲取音頻信息
        
        Args:
            audio_data: 音頻數據
            
        Returns:
            音頻信息字典
        """
        if not self.ffmpeg_available:
            return {}
        
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file.flush()
                
                cmd = [
                    self.ffprobe_path,
                    '-v', 'error',
                    '-show_entries', 'stream=codec_name,sample_rate,channels,bits_per_raw_sample',
                    '-of', 'json',
                    temp_file.name
                ]
                
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, _ = process.communicate()
                
                os.unlink(temp_file.name)
                
                if process.returncode == 0:
                    import json
                    info = json.loads(output.decode('utf-8'))
                    return info.get('streams', [{}])[0]
                
        except Exception as e:
            logger.error(f"ffprobe 失敗: {e}")
        
        return {}
    
    def update_config(self, config: dict):
        """更新配置"""
        super().update_config(config)
        
        # 更新 FFmpeg 特定配置
        if 'ffmpeg_path' in config:
            self.ffmpeg_path = config['ffmpeg_path']
            self._check_ffmpeg_available()
        
        if 'ffprobe_path' in config:
            self.ffprobe_path = config['ffprobe_path']
        
        if 'additional_args' in config:
            self.additional_args = config['additional_args']
            logger.info(f"[{self.operator_id}] FFmpeg 額外參數更新: {self.additional_args}")
        
        if 'use_pydub_fallback' in config:
            self.use_pydub_fallback = config['use_pydub_fallback']
    
    def get_info(self) -> dict:
        """獲取 Operator 信息"""
        info = super().get_info()
        info.update({
            "backend": "ffmpeg",
            "ffmpeg_available": self.ffmpeg_available,
            "use_pydub_fallback": self.use_pydub_fallback,
            "additional_args": self.additional_args
        })
        return info