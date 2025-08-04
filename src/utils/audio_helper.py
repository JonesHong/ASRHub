"""
音頻輔助工具
提供 WAV 格式處理、靜音檢測、音頻分析等輔助功能
"""

import numpy as np
from typing import Tuple, List, Dict, Optional
import io

from src.models.audio_format import AudioFormat
from src.core.exceptions import AudioFormatError
from src.utils.logger import logger

logger = logger


def create_wav_header(
    sample_rate: int,
    channels: int,
    bits_per_sample: int,
    data_size: int
) -> bytes:
    """
    建立 WAV 檔案標頭
    
    Args:
        sample_rate: 取樣率
        channels: 聲道數
        bits_per_sample: 每個樣本的位元數
        data_size: 音訊資料大小（位元組）
        
    Returns:
        WAV 標頭資料
    """
    # RIFF header
    header = b'RIFF'
    file_size = 36 + data_size  # 標頭大小 + 資料大小
    header += file_size.to_bytes(4, 'little')
    header += b'WAVE'
    
    # fmt chunk
    header += b'fmt '
    header += (16).to_bytes(4, 'little')  # Subchunk1Size
    header += (1).to_bytes(2, 'little')   # AudioFormat (PCM)
    header += channels.to_bytes(2, 'little')
    header += sample_rate.to_bytes(4, 'little')
    
    byte_rate = sample_rate * channels * bits_per_sample // 8
    header += byte_rate.to_bytes(4, 'little')
    
    block_align = channels * bits_per_sample // 8
    header += block_align.to_bytes(2, 'little')
    header += bits_per_sample.to_bytes(2, 'little')
    
    # data chunk
    header += b'data'
    header += data_size.to_bytes(4, 'little')
    
    return header


def pcm_to_wav(
    pcm_data: bytes,
    sample_rate: int,
    channels: int = 1,
    bits_per_sample: int = 16
) -> bytes:
    """
    將 PCM 資料轉換為 WAV 格式
    
    Args:
        pcm_data: PCM 音訊資料
        sample_rate: 取樣率
        channels: 聲道數
        bits_per_sample: 每個樣本的位元數
        
    Returns:
        WAV 格式資料
    """
    header = create_wav_header(
        sample_rate, channels, bits_per_sample, len(pcm_data)
    )
    return header + pcm_data


def detect_silence(
    audio_data: bytes,
    sample_rate: int,
    format: AudioFormat = AudioFormat.INT16,
    threshold: float = 0.01,
    min_duration: float = 0.1
) -> List[Tuple[float, float]]:
    """
    偵測音訊中的靜音片段
    
    Args:
        audio_data: 音訊資料
        sample_rate: 取樣率
        format: 音頻格式
        threshold: 靜音閾值 (0-1)
        min_duration: 最小靜音時長（秒）
        
    Returns:
        靜音片段列表 [(開始時間, 結束時間), ...]
    """
    # 轉換為 numpy array
    audio_array = np.frombuffer(audio_data, dtype=format.numpy_dtype)
    
    # 正規化到 -1.0 到 1.0
    if format == AudioFormat.INT16:
        audio_array = audio_array.astype(np.float32) / 32768.0
    elif format == AudioFormat.INT32:
        audio_array = audio_array.astype(np.float32) / 2147483648.0
    
    # 計算能量
    frame_size = int(sample_rate * 0.02)  # 20ms 的框架
    hop_size = frame_size // 2
    
    silence_regions = []
    current_silence_start = None
    
    for i in range(0, len(audio_array) - frame_size, hop_size):
        frame = audio_array[i:i + frame_size]
        energy = np.sqrt(np.mean(frame ** 2))
        
        time_pos = i / sample_rate
        
        if energy < threshold:
            # 靜音
            if current_silence_start is None:
                current_silence_start = time_pos
        else:
            # 非靜音
            if current_silence_start is not None:
                silence_duration = time_pos - current_silence_start
                if silence_duration >= min_duration:
                    silence_regions.append((current_silence_start, time_pos))
                current_silence_start = None
    
    # 處理最後的靜音片段
    if current_silence_start is not None:
        end_time = len(audio_array) / sample_rate
        silence_duration = end_time - current_silence_start
        if silence_duration >= min_duration:
            silence_regions.append((current_silence_start, end_time))
    
    return silence_regions


def trim_silence(
    audio_data: bytes,
    sample_rate: int,
    format: AudioFormat = AudioFormat.INT16,
    threshold: float = 0.01,
    margin: float = 0.1
) -> bytes:
    """
    修剪音訊開頭和結尾的靜音
    
    Args:
        audio_data: 音訊資料
        sample_rate: 取樣率
        format: 音頻格式
        threshold: 靜音閾值 (0-1)
        margin: 保留的邊界時長（秒）
        
    Returns:
        修剪後的音訊資料
    """
    # 偵測靜音
    silence_regions = detect_silence(
        audio_data, sample_rate, format, threshold, 0.05
    )
    
    if not silence_regions:
        return audio_data
    
    # 轉換為樣本索引
    bytes_per_sample = format.byte_width
    total_samples = len(audio_data) // bytes_per_sample
    
    # 找出開始和結束位置
    start_pos = 0
    end_pos = total_samples
    
    # 檢查開頭靜音
    if silence_regions[0][0] == 0:
        start_time = silence_regions[0][1] - margin
        start_pos = max(0, int(start_time * sample_rate))
    
    # 檢查結尾靜音
    audio_duration = total_samples / sample_rate
    if silence_regions[-1][1] >= audio_duration - 0.01:
        end_time = silence_regions[-1][0] + margin
        end_pos = min(total_samples, int(end_time * sample_rate))
    
    # 提取音訊片段
    start_byte = start_pos * bytes_per_sample
    end_byte = end_pos * bytes_per_sample
    
    return audio_data[start_byte:end_byte]


def normalize_audio(
    audio_data: bytes,
    format: AudioFormat = AudioFormat.INT16,
    target_level: float = 0.9
) -> bytes:
    """
    正規化音訊音量
    
    Args:
        audio_data: 音訊資料
        format: 音頻格式
        target_level: 目標音量等級 (0-1)
        
    Returns:
        正規化後的音訊資料
    """
    # 轉換為 numpy array
    audio_array = np.frombuffer(audio_data, dtype=format.numpy_dtype)
    
    # 轉換為 float 進行處理
    if format == AudioFormat.INT16:
        float_array = audio_array.astype(np.float32) / 32768.0
    elif format == AudioFormat.INT32:
        float_array = audio_array.astype(np.float32) / 2147483648.0
    else:
        float_array = audio_array.astype(np.float32)
    
    # 計算最大值
    max_val = np.max(np.abs(float_array))
    
    if max_val > 0:
        # 正規化
        scale_factor = target_level / max_val
        float_array = float_array * scale_factor
    
    # 轉換回原始格式
    if format == AudioFormat.INT16:
        output_array = (float_array * 32767).astype(np.int16)
    elif format == AudioFormat.INT32:
        output_array = (float_array * 2147483647).astype(np.int32)
    else:
        output_array = float_array.astype(format.numpy_dtype)
    
    return output_array.tobytes()


def split_audio_channels(
    audio_data: bytes,
    channels: int,
    format: AudioFormat = AudioFormat.INT16
) -> List[bytes]:
    """
    分離多聲道音訊
    
    Args:
        audio_data: 多聲道音訊資料
        channels: 聲道數
        format: 音頻格式
        
    Returns:
        每個聲道的音訊資料列表
        
    Raises:
        AudioFormatError: 如果格式錯誤
    """
    if channels == 1:
        return [audio_data]
    
    # 轉換為 numpy 陣列
    audio_array = np.frombuffer(audio_data, dtype=format.numpy_dtype)
    
    # 重塑為多聲道格式
    try:
        audio_array = audio_array.reshape(-1, channels)
    except ValueError:
        raise AudioFormatError(
            f"音訊資料大小不符合 {channels} 聲道格式"
        )
    
    # 分離聲道
    channel_data = []
    for ch in range(channels):
        channel_array = audio_array[:, ch]
        channel_data.append(channel_array.tobytes())
    
    return channel_data


def merge_audio_channels(
    channel_data: List[bytes],
    format: AudioFormat = AudioFormat.INT16
) -> bytes:
    """
    合併多個單聲道音訊為多聲道
    
    Args:
        channel_data: 單聲道音訊資料列表
        format: 音頻格式
        
    Returns:
        多聲道音訊資料
        
    Raises:
        AudioFormatError: 如果格式錯誤
    """
    if len(channel_data) == 1:
        return channel_data[0]
    
    # 轉換每個聲道為 numpy 陣列
    channels = []
    for data in channel_data:
        channel = np.frombuffer(data, dtype=format.numpy_dtype)
        channels.append(channel)
    
    # 確保所有聲道長度相同
    min_length = min(len(ch) for ch in channels)
    channels = [ch[:min_length] for ch in channels]
    
    # 合併聲道
    merged = np.column_stack(channels)
    
    return merged.tobytes()


def estimate_speech_rate(
    text: str,
    duration: float,
    language: str = "en"
) -> Dict[str, float]:
    """
    估算語速
    
    Args:
        text: 轉譯文字
        duration: 音訊時長（秒）
        language: 語言代碼
        
    Returns:
        包含各種語速指標的字典
    """
    # 計算字數
    words = text.split()
    word_count = len(words)
    
    # 計算字元數（不含空格）
    char_count = len(text.replace(" ", ""))
    
    # 計算語速
    words_per_minute = (word_count / duration) * 60 if duration > 0 else 0
    chars_per_second = char_count / duration if duration > 0 else 0
    
    # 根據語言調整
    if language.startswith("zh"):
        # 中文以字元計算更準確
        chars_per_minute = chars_per_second * 60
        return {
            "chars_per_minute": chars_per_minute,
            "chars_per_second": chars_per_second,
            "duration": duration,
            "char_count": char_count
        }
    else:
        # 其他語言以詞計算
        return {
            "words_per_minute": words_per_minute,
            "words_per_second": words_per_minute / 60,
            "duration": duration,
            "word_count": word_count
        }


def calculate_audio_duration(
    audio_data: bytes,
    sample_rate: int,
    channels: int = 1,
    format: AudioFormat = AudioFormat.INT16
) -> float:
    """
    計算音訊時長
    
    Args:
        audio_data: 音訊資料
        sample_rate: 取樣率
        channels: 聲道數
        format: 音頻格式
        
    Returns:
        音訊時長（秒）
    """
    bytes_per_sample = format.byte_width
    total_samples = len(audio_data) // (bytes_per_sample * channels)
    duration = total_samples / sample_rate
    return duration