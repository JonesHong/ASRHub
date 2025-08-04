"""
音頻轉換工具
提供 WebM、WAV 等格式轉換為 PCM 的功能
替代原先的 audio_utils 模組
"""

import io
import tempfile
import os
import time
from typing import Optional, Tuple
import numpy as np

from src.models.audio_format import AudioFormat, AudioMetadata  
from src.core.exceptions import AudioFormatError
from src.utils.logger import logger


def convert_webm_to_pcm(
    webm_data: bytes,
    target_sample_rate: int = 16000,
    target_channels: int = 1,
    target_format: AudioFormat = AudioFormat.INT16
) -> bytes:
    """
    將 WebM 音頻轉換為 PCM 格式
    
    Args:
        webm_data: WebM 音頻數據
        target_sample_rate: 目標採樣率
        target_channels: 目標聲道數
        target_format: 目標音頻格式
        
    Returns:
        PCM 音頻數據
        
    Raises:
        AudioFormatError: 轉換失敗時拋出
    """
    return _convert_audio_to_pcm(
        webm_data, 
        "webm",
        target_sample_rate,
        target_channels,
        target_format
    )


def convert_audio_file_to_pcm(
    audio_data: bytes,
    source_format: str = "auto",
    target_sample_rate: int = 16000,
    target_channels: int = 1,
    target_format: AudioFormat = AudioFormat.INT16
) -> bytes:
    """
    將各種音頻格式轉換為 PCM 格式
    
    Args:
        audio_data: 音頻數據
        source_format: 源格式 (auto, wav, mp3, webm, ogg 等)
        target_sample_rate: 目標採樣率
        target_channels: 目標聲道數
        target_format: 目標音頻格式
        
    Returns:
        PCM 音頻數據
        
    Raises:
        AudioFormatError: 轉換失敗時拋出
    """
    return _convert_audio_to_pcm(
        audio_data,
        source_format,
        target_sample_rate,
        target_channels,
        target_format
    )


def _convert_audio_to_pcm(
    audio_data: bytes,
    source_format: str,
    target_sample_rate: int,
    target_channels: int,
    target_format: AudioFormat
) -> bytes:
    """
    內部音頻轉換函數
    優先使用 FFmpeg，備用 pydub
    """
    # 先嘗試使用 FFmpeg
    try:
        return _convert_with_ffmpeg(
            audio_data, source_format, target_sample_rate, target_channels, target_format
        )
    except Exception as ffmpeg_error:
        logger.warning(f"FFmpeg 轉換失敗，嘗試使用 pydub: {ffmpeg_error}")
        
        # 嘗試使用 pydub
        try:
            return _convert_with_pydub(
                audio_data, source_format, target_sample_rate, target_channels, target_format
            )
        except Exception as pydub_error:
            logger.error(f"pydub 轉換也失敗: {pydub_error}")
            raise AudioFormatError(
                f"音頻轉換失敗。FFmpeg 錯誤: {ffmpeg_error}; pydub 錯誤: {pydub_error}"
            )


def _convert_with_ffmpeg(
    audio_data: bytes,
    source_format: str,
    target_sample_rate: int,
    target_channels: int,
    target_format: AudioFormat
) -> bytes:
    """使用 FFmpeg 進行音頻轉換"""
    import subprocess
    import time
    
    temp_input_path = None
    try:
        # 創建臨時輸入文件
        with tempfile.NamedTemporaryFile(suffix=f'.{source_format}', delete=False) as temp_input:
            temp_input_path = temp_input.name
            temp_input.write(audio_data)
            temp_input.flush()
            # 確保文件完全寫入磁盤
            os.fsync(temp_input.fileno())
        
        # 構建 FFmpeg 命令
        cmd = [
            'ffmpeg',
            '-y',  # 覆蓋輸出文件
            '-i', temp_input_path,
            '-f', _get_ffmpeg_format(target_format),
            '-acodec', _get_ffmpeg_codec(target_format),
            '-ar', str(target_sample_rate),
            '-ac', str(target_channels),
            '-'  # 輸出到 stdout
        ]
        
        # 執行轉換
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE  # 添加 stdin 管道
        )
        
        # 等待進程完成並獲取輸出
        pcm_data, error = process.communicate()
        
        # 等待進程完全結束
        process.wait()
        
        if process.returncode != 0:
            error_msg = error.decode('utf-8', errors='ignore')
            raise AudioFormatError(f"FFmpeg 轉換失敗: {error_msg}")
        
        # 確保數據對齊
        bytes_per_sample = target_format.bytes_per_sample
        expected_alignment = bytes_per_sample * target_channels
        
        if len(pcm_data) % expected_alignment != 0:
            padding_needed = expected_alignment - (len(pcm_data) % expected_alignment)
            logger.warning(f"音頻數據未對齊，添加 {padding_needed} 字節填充")
            pcm_data += b'\x00' * padding_needed
        
        logger.debug(
            f"FFmpeg 轉換成功: {len(audio_data)} bytes -> {len(pcm_data)} bytes "
            f"({target_sample_rate}Hz, {target_channels}ch, {target_format.name})"
        )
        
        return pcm_data
        
    finally:
        # 安全地清理臨時文件
        if temp_input_path and os.path.exists(temp_input_path):
            _safe_remove_file(temp_input_path)


def _convert_with_pydub(
    audio_data: bytes,
    source_format: str,
    target_sample_rate: int,
    target_channels: int,
    target_format: AudioFormat
) -> bytes:
    """使用 pydub 進行音頻轉換"""
    try:
        from pydub import AudioSegment
    except ImportError:
        raise AudioFormatError("需要安裝 pydub 來進行音頻轉換: pip install pydub")
    
    # 自動檢測格式
    if source_format == "auto":
        source_format = _detect_audio_format(audio_data)
    
    # 從 bytes 創建 AudioSegment，使用多種格式嘗試
    audio = None
    format_attempts = []
    
    if source_format == "webm":
        # WebM 格式可能包含 Opus 或 Vorbis 編碼
        format_attempts = ["webm", "ogg", "matroska"]
    else:
        format_attempts = [source_format, "ogg", "wav"]
    
    last_error = None
    for fmt in format_attempts:
        try:
            logger.debug(f"嘗試使用格式 '{fmt}' 載入音頻數據")
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format=fmt)
            logger.debug(f"成功使用格式 '{fmt}' 載入音頻")
            break
        except Exception as e:
            logger.debug(f"格式 '{fmt}' 載入失敗: {e}")
            last_error = e
            continue
    
    if audio is None:
        raise AudioFormatError(f"pydub 無法載入音頻數據，最後錯誤: {last_error}")
    
    # 轉換參數
    audio = audio.set_frame_rate(target_sample_rate)
    audio = audio.set_channels(target_channels)
    
    # 設置採樣寬度
    if target_format == AudioFormat.INT16:
        audio = audio.set_sample_width(2)
    elif target_format == AudioFormat.INT32:
        audio = audio.set_sample_width(4)
    elif target_format == AudioFormat.FLOAT32:
        # pydub 不直接支持 float32，需要特殊處理
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        if audio.channels == 2:
            samples = samples.reshape((-1, 2))
        samples = samples / (2 ** (audio.sample_width * 8 - 1))
        return samples.tobytes()
    
    # 導出為 PCM
    pcm_data = audio.raw_data
    
    logger.debug(
        f"pydub 轉換成功: {len(audio_data)} bytes -> {len(pcm_data)} bytes "
        f"({target_sample_rate}Hz, {target_channels}ch, {target_format.name})"
    )
    
    return pcm_data


def _get_ffmpeg_format(audio_format: AudioFormat) -> str:
    """獲取 FFmpeg 格式名稱"""
    format_map = {
        AudioFormat.INT16: 's16le',
        AudioFormat.INT24: 's24le', 
        AudioFormat.INT32: 's32le',
        AudioFormat.FLOAT32: 'f32le',
    }
    return format_map.get(audio_format, 's16le')


def _get_ffmpeg_codec(audio_format: AudioFormat) -> str:
    """獲取 FFmpeg 編解碼器名稱"""
    codec_map = {
        AudioFormat.INT16: 'pcm_s16le',
        AudioFormat.INT24: 'pcm_s24le',
        AudioFormat.INT32: 'pcm_s32le', 
        AudioFormat.FLOAT32: 'pcm_f32le',
    }
    return codec_map.get(audio_format, 'pcm_s16le')


def _detect_audio_format(audio_data: bytes) -> str:
    """
    簡單的音頻格式檢測
    根據文件頭部的魔術字節判斷格式
    """
    if len(audio_data) < 12:
        return "raw"
    
    # WAV 格式檢測
    if audio_data[:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
        return "wav"
    
    # MP3 格式檢測 - 檢查 ID3 標籤或 MP3 frame header
    if audio_data[:3] == b'ID3' or (len(audio_data) >= 2 and (audio_data[:2] == b'\xff\xfb' or audio_data[:2] == b'\xff\xfa')):
        return "mp3"
    
    # OGG 格式檢測
    if audio_data[:4] == b'OggS':
        return "ogg"
    
    # WebM/Matroska 格式檢測 - EBML header
    if audio_data[:4] == b'\x1a\x45\xdf\xa3':
        return "webm"
    
    # 默認當作 raw PCM
    logger.warning("無法檢測音頻格式，當作 raw PCM 處理")
    return "raw"


def probe_audio_metadata(audio_data: bytes) -> Optional[AudioMetadata]:
    """
    獲取音頻元數據信息
    
    Args:
        audio_data: 音頻數據
        
    Returns:
        音頻元數據，如果獲取失敗則返回 None
    """
    try:
        # 嘗試使用 FFprobe
        return _probe_with_ffprobe(audio_data)
    except Exception as e:
        logger.warning(f"FFprobe 獲取元數據失敗: {e}")
        
        try:
            # 嘗試使用 pydub
            return _probe_with_pydub(audio_data)
        except Exception as e:
            logger.warning(f"pydub 獲取元數據失敗: {e}")
            return None


def _probe_with_ffprobe(audio_data: bytes) -> AudioMetadata:
    """使用 FFprobe 獲取音頻元數據"""
    import subprocess
    import json
    
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(audio_data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'stream=codec_name,sample_rate,channels,bits_per_raw_sample',
            '-of', 'json',
            temp_file_path
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        process.wait()
        
        if process.returncode == 0:
            info = json.loads(output.decode('utf-8'))
            stream = info.get('streams', [{}])[0]
            
            # 解析音頻格式
            bits_per_sample = stream.get('bits_per_raw_sample', 16)
            if bits_per_sample == 16:
                audio_format = AudioFormat.INT16
            elif bits_per_sample == 24:
                audio_format = AudioFormat.INT24
            elif bits_per_sample == 32:
                audio_format = AudioFormat.INT32
            else:
                audio_format = AudioFormat.INT16
            
            return AudioMetadata(
                sample_rate=int(stream.get('sample_rate', 16000)),
                channels=int(stream.get('channels', 1)),
                format=audio_format
            )
        else:
            error_msg = error.decode('utf-8', errors='ignore')
            raise AudioFormatError(f"FFprobe 執行失敗: {error_msg}")
            
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            _safe_remove_file(temp_file_path)


def _probe_with_pydub(audio_data: bytes) -> AudioMetadata:
    """使用 pydub 獲取音頻元數據"""
    try:
        from pydub import AudioSegment
    except ImportError:
        raise AudioFormatError("需要安裝 pydub")
    
    # 自動檢測並載入
    source_format = _detect_audio_format(audio_data)
    audio = AudioSegment.from_file(io.BytesIO(audio_data), format=source_format)
    
    # 確定音頻格式
    if audio.sample_width == 2:
        audio_format = AudioFormat.INT16
    elif audio.sample_width == 3:
        audio_format = AudioFormat.INT24
    elif audio.sample_width == 4:
        audio_format = AudioFormat.INT32
    else:
        audio_format = AudioFormat.INT16
    
    return AudioMetadata(
        sample_rate=audio.frame_rate,
        channels=audio.channels,
        format=audio_format
    )


def _safe_remove_file(file_path: str, max_attempts: int = 5, delay: float = 0.1) -> bool:
    """
    安全地刪除文件，處理 Windows 文件鎖定問題
    
    Args:
        file_path: 要刪除的文件路径
        max_attempts: 最大重試次數
        delay: 重試間隔（秒）
        
    Returns:
        是否成功刪除文件
    """
    for attempt in range(max_attempts):
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"成功刪除臨時文件: {file_path}")
                return True
            else:
                logger.debug(f"文件已不存在: {file_path}")
                return True
        except (OSError, PermissionError) as e:
            if attempt < max_attempts - 1:
                logger.warning(f"刪除文件失敗 (嘗試 {attempt + 1}/{max_attempts}): {e}")
                time.sleep(delay)
                delay *= 2  # 指數退避
            else:
                logger.error(f"無法刪除臨時文件 {file_path}: {e}")
                return False
    
    return False