"""
統一音訊格式轉換器
整合所有格式轉換功能，簡化 API 介面
"""

import io
import tempfile
import os
import time
import subprocess
import json
from typing import Optional, Union, Dict, Any
import numpy as np

from .models import (
    AudioChunk, AudioMetadata, AudioSampleFormat, 
    AudioContainerFormat, AudioEncoding
)
from src.utils.logger import logger


class AudioConverter:
    """
    統一的音訊格式轉換器
    整合來自 audio_converter.py, audio_helper.py 和 packet_utils.py 的功能
    """
    
    def __init__(self, 
                 prefer_ffmpeg: bool = True,
                 ffmpeg_path: str = "ffmpeg",
                 ffprobe_path: str = "ffprobe"):
        """
        初始化音訊轉換器
        
        Args:
            prefer_ffmpeg: 是否優先使用 FFmpeg
            ffmpeg_path: FFmpeg 執行檔路徑
            ffprobe_path: FFprobe 執行檔路徑
        """
        self.prefer_ffmpeg = prefer_ffmpeg
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._pydub_available = self._check_pydub()
    
    def _check_pydub(self) -> bool:
        """檢查 pydub 是否可用"""
        try:
            import pydub
            return True
        except ImportError:
            return False
    
    def convert(self,
               data: Union[bytes, AudioChunk],
               to_format: AudioContainerFormat,
               to_metadata: Optional[AudioMetadata] = None,
               from_format: Optional[AudioContainerFormat] = None) -> AudioChunk:
        """
        通用格式轉換方法
        
        Args:
            data: 輸入音訊資料（bytes 或 AudioChunk）
            to_format: 目標格式
            to_metadata: 目標元資料（採樣率、聲道數等）
            from_format: 來源格式（如果 data 是 bytes）
            
        Returns:
            轉換後的 AudioChunk
        """
        # 處理輸入
        if isinstance(data, AudioChunk):
            source_data = data.data
            source_metadata = data.metadata
            source_format = data.metadata.container_format
        else:
            source_data = data
            source_format = from_format or self.detect_format(data)
            source_metadata = self.probe_metadata(data)
        
        # 設定目標元資料
        if to_metadata is None:
            to_metadata = source_metadata or AudioMetadata(
                sample_rate=16000,
                channels=1,
                format=AudioSampleFormat.INT16,
                container_format=to_format
            )
        else:
            to_metadata.container_format = to_format
        
        # 執行轉換
        if source_format == to_format and source_metadata == to_metadata:
            # 格式相同，不需要轉換
            converted_data = source_data
        else:
            converted_data = self._convert_internal(
                source_data,
                source_format,
                to_format,
                to_metadata
            )
        
        # 創建新的 AudioChunk
        return AudioChunk(
            data=converted_data,
            metadata=to_metadata
        )
    
    def to_pcm(self,
              data: Union[bytes, AudioChunk],
              target_metadata: Optional[AudioMetadata] = None) -> AudioChunk:
        """
        轉換為 PCM 格式
        
        Args:
            data: 輸入音訊資料
            target_metadata: 目標元資料
            
        Returns:
            PCM 格式的 AudioChunk
        """
        return self.convert(
            data,
            AudioContainerFormat.PCM,
            target_metadata
        )
    
    def to_wav(self,
              data: Union[bytes, AudioChunk],
              add_header: bool = True) -> bytes:
        """
        轉換為 WAV 格式
        
        Args:
            data: 輸入音訊資料
            add_header: 是否添加 WAV 標頭
            
        Returns:
            WAV 格式資料
        """
        # 先轉換為 PCM
        pcm_chunk = self.to_pcm(data)
        
        if not add_header:
            return pcm_chunk.data
        
        # 添加 WAV 標頭
        return self._add_wav_header(pcm_chunk.data, pcm_chunk.metadata)
    
    def to_numpy(self,
                data: Union[bytes, AudioChunk],
                dtype: Optional[np.dtype] = None) -> np.ndarray:
        """
        轉換為 numpy array
        
        Args:
            data: 輸入音訊資料
            dtype: 目標資料類型
            
        Returns:
            numpy array
        """
        if isinstance(data, AudioChunk):
            audio_data = data.data
            format = data.metadata.format
        else:
            audio_data = data
            format = AudioSampleFormat.INT16  # 預設
        
        # 根據格式選擇 dtype
        if dtype is None:
            dtype = format.numpy_dtype or np.int16
        
        # 特殊處理 INT24
        if format == AudioSampleFormat.INT24:
            samples = []
            for i in range(0, len(audio_data), 3):
                sample_bytes = audio_data[i:i+3]
                sample_int = int.from_bytes(
                    sample_bytes, 
                    byteorder='little', 
                    signed=True
                )
                samples.append(sample_int)
            return np.array(samples, dtype=np.int32)
        
        return np.frombuffer(audio_data, dtype=dtype)
    
    def from_numpy(self,
                  audio_np: np.ndarray,
                  metadata: AudioMetadata) -> AudioChunk:
        """
        從 numpy array 創建 AudioChunk
        
        Args:
            audio_np: numpy array
            metadata: 音訊元資料
            
        Returns:
            AudioChunk
        """
        # 特殊處理 INT24
        if metadata.format == AudioSampleFormat.INT24:
            result = bytearray()
            for sample in audio_np:
                sample_int = int(sample) & 0xFFFFFF
                result.extend(sample_int.to_bytes(3, byteorder='little', signed=True))
            audio_data = bytes(result)
        else:
            dtype = metadata.format.numpy_dtype
            if dtype is None:
                raise ValueError(f"不支援的格式: {metadata.format}")
            audio_data = audio_np.astype(dtype).tobytes()
        
        return AudioChunk(
            data=audio_data,
            metadata=metadata
        )
    
    def detect_format(self, data: bytes) -> AudioContainerFormat:
        """
        檢測音訊格式
        
        Args:
            data: 音訊資料
            
        Returns:
            檢測到的格式
        """
        if len(data) < 12:
            return AudioContainerFormat.PCM
        
        # WAV 格式
        if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
            return AudioContainerFormat.WAV
        
        # MP3 格式
        if (data[:3] == b'ID3' or 
            (len(data) >= 2 and data[:2] in [b'\xff\xfb', b'\xff\xfa'])):
            return AudioContainerFormat.MP3
        
        # OGG 格式
        if data[:4] == b'OggS':
            return AudioContainerFormat.OGG
        
        # WebM/Matroska 格式
        if data[:4] == b'\x1a\x45\xdf\xa3':
            return AudioContainerFormat.WEBM
        
        # FLAC 格式
        if data[:4] == b'fLaC':
            return AudioContainerFormat.FLAC
        
        # M4A 格式
        if len(data) >= 8 and data[4:8] == b'ftyp':
            return AudioContainerFormat.M4A
        
        # 預設為 PCM
        return AudioContainerFormat.PCM
    
    def probe_metadata(self, data: bytes) -> Optional[AudioMetadata]:
        """
        獲取音訊元資料
        
        Args:
            data: 音訊資料
            
        Returns:
            音訊元資料，失敗返回 None
        """
        if self.prefer_ffmpeg:
            metadata = self._probe_with_ffprobe(data)
            if metadata:
                return metadata
        
        if self._pydub_available:
            metadata = self._probe_with_pydub(data)
            if metadata:
                return metadata
        
        return None
    
    def _convert_internal(self,
                         data: bytes,
                         from_format: AudioContainerFormat,
                         to_format: AudioContainerFormat,
                         metadata: AudioMetadata) -> bytes:
        """
        內部轉換方法
        
        Args:
            data: 輸入資料
            from_format: 來源格式
            to_format: 目標格式
            metadata: 目標元資料
            
        Returns:
            轉換後的資料
        """
        # 優先使用 FFmpeg
        if self.prefer_ffmpeg:
            try:
                return self._convert_with_ffmpeg(
                    data, from_format, to_format, metadata
                )
            except Exception as e:
                logger.warning(f"FFmpeg 轉換失敗: {e}")
        
        # 使用 pydub
        if self._pydub_available:
            try:
                return self._convert_with_pydub(
                    data, from_format, to_format, metadata
                )
            except Exception as e:
                logger.warning(f"pydub 轉換失敗: {e}")
        
        raise ValueError(f"無法轉換格式: {from_format} -> {to_format}")
    
    def _convert_with_ffmpeg(self,
                            data: bytes,
                            from_format: AudioContainerFormat,
                            to_format: AudioContainerFormat,
                            metadata: AudioMetadata) -> bytes:
        """使用 FFmpeg 轉換"""
        temp_input_path = None
        temp_output_path = None
        
        try:
            # 創建臨時輸入檔案
            suffix = f'.{from_format.value}'
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_input:
                temp_input_path = temp_input.name
                temp_input.write(data)
                temp_input.flush()
                os.fsync(temp_input.fileno())
            
            # 構建 FFmpeg 命令
            cmd = [
                self.ffmpeg_path,
                '-y',  # 覆蓋輸出
                '-i', temp_input_path,
                '-ar', str(metadata.sample_rate),
                '-ac', str(metadata.channels),
            ]
            
            # 設定輸出格式
            if to_format == AudioContainerFormat.PCM:
                cmd.extend([
                    '-f', self._get_ffmpeg_format(metadata.format),
                    '-acodec', self._get_ffmpeg_codec(metadata.format),
                ])
            else:
                cmd.extend([
                    '-f', to_format.value,
                ])
            
            # 輸出到 stdout
            cmd.append('-')
            
            # 執行轉換
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )
            
            output_data, error = process.communicate()
            
            if process.returncode != 0:
                error_msg = error.decode('utf-8', errors='ignore')
                raise RuntimeError(f"FFmpeg 錯誤: {error_msg}")
            
            return output_data
            
        finally:
            # 清理臨時檔案
            if temp_input_path and os.path.exists(temp_input_path):
                self._safe_remove_file(temp_input_path)
            if temp_output_path and os.path.exists(temp_output_path):
                self._safe_remove_file(temp_output_path)
    
    def _convert_with_pydub(self,
                           data: bytes,
                           from_format: AudioContainerFormat,
                           to_format: AudioContainerFormat,
                           metadata: AudioMetadata) -> bytes:
        """使用 pydub 轉換"""
        from pydub import AudioSegment
        
        # 載入音訊
        audio = AudioSegment.from_file(
            io.BytesIO(data),
            format=from_format.value
        )
        
        # 設定參數
        audio = audio.set_frame_rate(metadata.sample_rate)
        audio = audio.set_channels(metadata.channels)
        
        # 設定採樣寬度
        if metadata.format == AudioSampleFormat.INT16:
            audio = audio.set_sample_width(2)
        elif metadata.format == AudioSampleFormat.INT32:
            audio = audio.set_sample_width(4)
        
        # 輸出
        if to_format == AudioContainerFormat.PCM:
            return audio.raw_data
        else:
            output = io.BytesIO()
            audio.export(output, format=to_format.value)
            return output.getvalue()
    
    def _add_wav_header(self, pcm_data: bytes, metadata: AudioMetadata) -> bytes:
        """添加 WAV 檔頭"""
        import struct
        
        # 計算大小
        data_size = len(pcm_data)
        file_size = data_size + 36  # 44 - 8
        
        # 建立標頭
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',  # ChunkID
            file_size,  # ChunkSize
            b'WAVE',  # Format
            b'fmt ',  # Subchunk1ID
            16,  # Subchunk1Size (PCM)
            1,  # AudioFormat (PCM)
            metadata.channels,  # NumChannels
            metadata.sample_rate,  # SampleRate
            metadata.sample_rate * metadata.channels * metadata.format.bytes_per_sample,  # ByteRate
            metadata.channels * metadata.format.bytes_per_sample,  # BlockAlign
            metadata.format.bytes_per_sample * 8,  # BitsPerSample
            b'data',  # Subchunk2ID
            data_size  # Subchunk2Size
        )
        
        return header + pcm_data
    
    def _parse_wav_header(self, data: bytes) -> tuple[bytes, AudioMetadata]:
        """解析 WAV 檔頭"""
        import struct
        
        if len(data) < 44:
            raise ValueError("WAV 資料太短")
        
        # 解析標頭
        (chunk_id, chunk_size, format_tag, subchunk1_id, subchunk1_size,
         audio_format, num_channels, sample_rate, byte_rate, block_align,
         bits_per_sample, subchunk2_id, subchunk2_size) = struct.unpack(
            '<4sI4s4sIHHIIHH4sI', data[:44]
        )
        
        # 驗證格式
        if chunk_id != b'RIFF' or format_tag != b'WAVE':
            raise ValueError("無效的 WAV 格式")
        
        # 建立元資料
        if bits_per_sample == 16:
            format = AudioSampleFormat.INT16
        elif bits_per_sample == 24:
            format = AudioSampleFormat.INT24
        elif bits_per_sample == 32:
            format = AudioSampleFormat.INT32
        else:
            format = AudioSampleFormat.INT16
        
        metadata = AudioMetadata(
            sample_rate=sample_rate,
            channels=num_channels,
            format=format,
            container_format=AudioContainerFormat.WAV
        )
        
        # 返回 PCM 資料和元資料
        pcm_data = data[44:44+subchunk2_size]
        return pcm_data, metadata
    
    def _get_ffmpeg_format(self, format: AudioSampleFormat) -> str:
        """獲取 FFmpeg 格式字串"""
        format_map = {
            AudioSampleFormat.INT16: 's16le',
            AudioSampleFormat.INT24: 's24le',
            AudioSampleFormat.INT32: 's32le',
            AudioSampleFormat.FLOAT32: 'f32le',
        }
        return format_map.get(format, 's16le')
    
    def _get_ffmpeg_codec(self, format: AudioSampleFormat) -> str:
        """獲取 FFmpeg 編解碼器"""
        codec_map = {
            AudioSampleFormat.INT16: 'pcm_s16le',
            AudioSampleFormat.INT24: 'pcm_s24le',
            AudioSampleFormat.INT32: 'pcm_s32le',
            AudioSampleFormat.FLOAT32: 'pcm_f32le',
        }
        return codec_map.get(format, 'pcm_s16le')
    
    def _probe_with_ffprobe(self, data: bytes) -> Optional[AudioMetadata]:
        """使用 FFprobe 獲取元資料"""
        temp_file_path = None
        
        try:
            # 創建臨時檔案
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            
            # 執行 FFprobe
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-show_entries', 'stream=codec_name,sample_rate,channels,bits_per_raw_sample',
                '-of', 'json',
                temp_file_path
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            output, error = process.communicate()
            
            if process.returncode == 0:
                info = json.loads(output.decode('utf-8'))
                stream = info.get('streams', [{}])[0]
                
                # 解析格式
                bits = stream.get('bits_per_raw_sample', 16)
                if bits == 16:
                    format = AudioSampleFormat.INT16
                elif bits == 24:
                    format = AudioSampleFormat.INT24
                elif bits == 32:
                    format = AudioSampleFormat.INT32
                else:
                    format = AudioSampleFormat.INT16
                
                return AudioMetadata(
                    sample_rate=int(stream.get('sample_rate', 16000)),
                    channels=int(stream.get('channels', 1)),
                    format=format
                )
            
        except Exception as e:
            logger.debug(f"FFprobe 失敗: {e}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                self._safe_remove_file(temp_file_path)
        
        return None
    
    def _probe_with_pydub(self, data: bytes) -> Optional[AudioMetadata]:
        """使用 pydub 獲取元資料"""
        try:
            from pydub import AudioSegment
            
            # 檢測格式
            format = self.detect_format(data)
            
            # 載入音訊
            audio = AudioSegment.from_file(
                io.BytesIO(data),
                format=format.value
            )
            
            # 確定格式
            if audio.sample_width == 2:
                sample_format = AudioSampleFormat.INT16
            elif audio.sample_width == 3:
                sample_format = AudioSampleFormat.INT24
            elif audio.sample_width == 4:
                sample_format = AudioSampleFormat.INT32
            else:
                sample_format = AudioSampleFormat.INT16
            
            return AudioMetadata(
                sample_rate=audio.frame_rate,
                channels=audio.channels,
                format=sample_format,
                container_format=format
            )
            
        except Exception as e:
            logger.debug(f"pydub 失敗: {e}")
        
        return None
    
    @staticmethod
    def convert_webm_to_pcm(data: bytes, 
                           sample_rate: int = 16000, 
                           channels: int = 1) -> bytes:
        """
        轉換 WebM/Opus 音訊為 PCM 格式
        
        Args:
            data: WebM/Opus 音訊資料
            sample_rate: 目標採樣率
            channels: 目標聲道數
            
        Returns:
            PCM 格式音訊資料
        """
        converter = AudioConverter(prefer_ffmpeg=True)
        
        try:
            # 檢測格式
            detected_format = converter.detect_format(data)
            logger.debug(f"檢測到音訊格式: {detected_format}")
            
            # 創建目標元資料
            target_metadata = AudioMetadata(
                sample_rate=sample_rate,
                channels=channels,
                format=AudioSampleFormat.INT16,
                container_format=AudioContainerFormat.PCM
            )
            
            # 轉換為 PCM
            pcm_chunk = converter.convert(
                data=data,
                to_format=AudioContainerFormat.PCM,
                to_metadata=target_metadata,
                from_format=detected_format
            )
            
            logger.info(f"WebM 轉 PCM 成功: {len(data)} → {len(pcm_chunk.data)} bytes")
            return pcm_chunk.data
            
        except Exception as e:
            logger.error(f"WebM 轉 PCM 失敗: {e}")
            raise ValueError(f"無法轉換 WebM/Opus 音訊: {e}")
    
    @staticmethod
    def convert_audio_file_to_pcm(data: bytes,
                                 sample_rate: int = 16000,
                                 channels: int = 1,
                                 target_format: AudioSampleFormat = AudioSampleFormat.INT16) -> bytes:
        """
        通用音訊檔案轉 PCM 格式
        
        Args:
            data: 音訊資料
            sample_rate: 目標採樣率
            channels: 目標聲道數
            target_format: 目標音訊格式
            
        Returns:
            PCM 格式音訊資料
        """
        converter = AudioConverter(prefer_ffmpeg=True)
        
        try:
            # 檢測格式
            detected_format = converter.detect_format(data)
            logger.debug(f"檢測到音訊格式: {detected_format}")
            
            # 創建目標元資料
            target_metadata = AudioMetadata(
                sample_rate=sample_rate,
                channels=channels,
                format=target_format,
                container_format=AudioContainerFormat.PCM
            )
            
            # 轉換為 PCM
            pcm_chunk = converter.convert(
                data=data,
                to_format=AudioContainerFormat.PCM,
                to_metadata=target_metadata,
                from_format=detected_format
            )
            
            logger.info(f"音訊轉 PCM 成功: {detected_format} → PCM ({len(data)} → {len(pcm_chunk.data)} bytes)")
            return pcm_chunk.data
            
        except Exception as e:
            logger.error(f"音訊轉 PCM 失敗: {e}")
            raise ValueError(f"無法轉換音訊檔案: {e}")
    
    @staticmethod
    def is_compressed_audio(data: bytes) -> bool:
        """
        檢測音訊是否為壓縮格式
        
        Args:
            data: 音訊資料
            
        Returns:
            True 如果是壓縮格式，否則 False
        """
        if len(data) < 12:
            return False
            
        # WebM/Matroska 格式 (包含 Opus)
        if data[:4] == b'\x1a\x45\xdf\xa3':
            return True
            
        # OGG 格式 (可能包含 Opus)
        if data[:4] == b'OggS':
            return True
            
        # MP3 格式
        if (data[:3] == b'ID3' or 
            (len(data) >= 2 and data[:2] in [b'\xff\xfb', b'\xff\xfa'])):
            return True
            
        # M4A/AAC 格式
        if len(data) >= 8 and data[4:8] == b'ftyp':
            return True
            
        # FLAC 格式
        if data[:4] == b'fLaC':
            return True
            
        # WAV 格式 - 通常未壓縮，但可能包含壓縮音訊
        if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
            # 簡單判斷：如果是標準 PCM WAV，不算壓縮
            # 但其他格式的 WAV 可能需要解碼
            try:
                # 檢查音訊格式代碼
                if len(data) >= 22:
                    import struct
                    audio_format = struct.unpack('<H', data[20:22])[0]
                    # 1 = PCM, 其他為壓縮格式
                    return audio_format != 1
            except:
                pass
                
        return False
    
    def _safe_remove_file(self, file_path: str, max_attempts: int = 5) -> bool:
        """安全刪除檔案"""
        for attempt in range(max_attempts):
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    return True
                return True
            except (OSError, PermissionError) as e:
                if attempt < max_attempts - 1:
                    time.sleep(0.1 * (2 ** attempt))  # 指數退避
                else:
                    logger.error(f"無法刪除檔案 {file_path}: {e}")
                    return False
        return False