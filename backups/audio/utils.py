"""
音訊工具函數
整合常用的輔助功能
"""

import struct
from typing import Optional, Tuple, List
import numpy as np
from .models import AudioChunk, AudioMetadata, AudioSampleFormat


def create_audio_chunk(data: bytes,
                      sample_rate: int = 16000,
                      channels: int = 1,
                      format: AudioSampleFormat = AudioSampleFormat.INT16) -> AudioChunk:
    """
    快速創建 AudioChunk 的工廠函數
    
    Args:
        data: 音訊資料
        sample_rate: 採樣率
        channels: 聲道數
        format: 音訊格式
        
    Returns:
        AudioChunk 實例
    """
    metadata = AudioMetadata(
        sample_rate=sample_rate,
        channels=channels,
        format=format
    )
    
    return AudioChunk(
        data=data,
        metadata=metadata
    )


def split_audio_chunk(chunk: AudioChunk, 
                     chunk_size_ms: int = 100) -> List[AudioChunk]:
    """
    將音訊分割成固定大小的塊
    
    Args:
        chunk: 原始音訊塊
        chunk_size_ms: 每塊的大小（毫秒）
        
    Returns:
        分割後的音訊塊列表
    """
    # 計算每塊的字節數
    bytes_per_ms = (chunk.metadata.sample_rate * 
                   chunk.metadata.channels * 
                   chunk.metadata.format.bytes_per_sample) // 1000
    chunk_size_bytes = bytes_per_ms * chunk_size_ms
    
    # 分割音訊
    chunks = []
    data = chunk.data
    offset = 0
    
    while offset < len(data):
        end = min(offset + chunk_size_bytes, len(data))
        sub_data = data[offset:end]
        
        sub_chunk = AudioChunk(
            data=sub_data,
            metadata=chunk.metadata,
            timestamp=chunk.timestamp + (offset / bytes_per_ms / 1000),
            sequence_number=(chunk.sequence_number or 0) + len(chunks)
        )
        
        chunks.append(sub_chunk)
        offset = end
    
    return chunks


def merge_audio_chunks(chunks: List[AudioChunk]) -> AudioChunk:
    """
    合併多個音訊塊
    
    Args:
        chunks: 音訊塊列表
        
    Returns:
        合併後的音訊塊
    """
    if not chunks:
        raise ValueError("沒有音訊塊可合併")
    
    # 使用第一個塊的元資料
    metadata = chunks[0].metadata
    
    # 合併資料
    merged_data = b''.join(chunk.data for chunk in chunks)
    
    # 創建新塊
    return AudioChunk(
        data=merged_data,
        metadata=metadata,
        timestamp=chunks[0].timestamp,
        sequence_number=chunks[0].sequence_number,
        is_final=chunks[-1].is_final
    )


def resample_audio(chunk: AudioChunk, 
                   target_sample_rate: int) -> AudioChunk:
    """
    重新採樣音訊
    簡單的線性插值實現
    
    Args:
        chunk: 原始音訊塊
        target_sample_rate: 目標採樣率
        
    Returns:
        重新採樣後的音訊塊
    """
    if chunk.metadata.sample_rate == target_sample_rate:
        return chunk
    
    # 轉換為 numpy
    dtype = chunk.metadata.format.numpy_dtype
    if dtype is None:
        raise ValueError(f"不支援的格式: {chunk.metadata.format}")
    
    audio_np = np.frombuffer(chunk.data, dtype=dtype)
    
    # 計算重採樣比率
    ratio = target_sample_rate / chunk.metadata.sample_rate
    
    # 簡單的線性插值
    old_length = len(audio_np)
    new_length = int(old_length * ratio)
    
    old_indices = np.arange(old_length)
    new_indices = np.linspace(0, old_length - 1, new_length)
    
    # 對每個聲道重採樣
    if chunk.metadata.channels > 1:
        audio_np = audio_np.reshape(-1, chunk.metadata.channels)
        resampled = np.zeros((new_length, chunk.metadata.channels), dtype=dtype)
        for ch in range(chunk.metadata.channels):
            resampled[:, ch] = np.interp(new_indices, old_indices, audio_np[:, ch])
        resampled = resampled.flatten()
    else:
        resampled = np.interp(new_indices, old_indices, audio_np)
    
    # 轉換回 bytes
    resampled_data = resampled.astype(dtype).tobytes()
    
    # 創建新的元資料
    new_metadata = AudioMetadata(
        sample_rate=target_sample_rate,
        channels=chunk.metadata.channels,
        format=chunk.metadata.format
    )
    
    return AudioChunk(
        data=resampled_data,
        metadata=new_metadata,
        timestamp=chunk.timestamp,
        sequence_number=chunk.sequence_number,
        is_final=chunk.is_final
    )


def mix_audio_chunks(chunks: List[AudioChunk], 
                    weights: Optional[List[float]] = None) -> AudioChunk:
    """
    混合多個音訊塊
    
    Args:
        chunks: 音訊塊列表
        weights: 每個音訊的權重（可選）
        
    Returns:
        混合後的音訊塊
    """
    if not chunks:
        raise ValueError("沒有音訊塊可混合")
    
    # 設定權重
    if weights is None:
        weights = [1.0 / len(chunks)] * len(chunks)
    elif len(weights) != len(chunks):
        raise ValueError("權重數量與音訊塊數量不符")
    
    # 確保所有音訊有相同的元資料
    metadata = chunks[0].metadata
    for chunk in chunks[1:]:
        if (chunk.metadata.sample_rate != metadata.sample_rate or
            chunk.metadata.channels != metadata.channels or
            chunk.metadata.format != metadata.format):
            raise ValueError("所有音訊塊必須有相同的格式")
    
    # 轉換為 numpy 並混合
    dtype = metadata.format.numpy_dtype
    if dtype is None:
        raise ValueError(f"不支援的格式: {metadata.format}")
    
    # 找出最短的長度
    min_length = min(len(chunk.data) for chunk in chunks)
    
    # 混合音訊
    mixed = np.zeros(min_length // dtype.itemsize, dtype=np.float32)
    
    for chunk, weight in zip(chunks, weights):
        audio_np = np.frombuffer(chunk.data[:min_length], dtype=dtype)
        mixed += audio_np.astype(np.float32) * weight
    
    # 限制範圍並轉換回原始類型
    if dtype == np.int16:
        mixed = np.clip(mixed, -32768, 32767)
    elif dtype == np.int32:
        mixed = np.clip(mixed, -2147483648, 2147483647)
    
    mixed_data = mixed.astype(dtype).tobytes()
    
    return AudioChunk(
        data=mixed_data,
        metadata=metadata,
        timestamp=chunks[0].timestamp
    )


def calculate_db(chunk: AudioChunk, reference: float = 1.0) -> float:
    """
    計算音訊的分貝值
    
    Args:
        chunk: 音訊塊
        reference: 參考值
        
    Returns:
        分貝值
    """
    # 轉換為 numpy
    dtype = chunk.metadata.format.numpy_dtype
    if dtype is None:
        raise ValueError(f"不支援的格式: {chunk.metadata.format}")
    
    audio_np = np.frombuffer(chunk.data, dtype=dtype)
    
    # 正規化到 [-1, 1]
    if dtype == np.int16:
        audio_np = audio_np.astype(np.float32) / 32768.0
    elif dtype == np.int32:
        audio_np = audio_np.astype(np.float32) / 2147483648.0
    
    # 計算 RMS
    rms = np.sqrt(np.mean(audio_np ** 2))
    
    # 避免 log(0)
    if rms == 0:
        return -float('inf')
    
    # 計算分貝
    db = 20 * np.log10(rms / reference)
    
    return float(db)


def apply_fade(chunk: AudioChunk,
              fade_in_ms: int = 0,
              fade_out_ms: int = 0) -> AudioChunk:
    """
    應用淡入淡出效果
    
    Args:
        chunk: 音訊塊
        fade_in_ms: 淡入時間（毫秒）
        fade_out_ms: 淡出時間（毫秒）
        
    Returns:
        應用效果後的音訊塊
    """
    # 轉換為 numpy
    dtype = chunk.metadata.format.numpy_dtype
    if dtype is None:
        raise ValueError(f"不支援的格式: {chunk.metadata.format}")
    
    audio_np = np.frombuffer(chunk.data, dtype=dtype).astype(np.float32)
    
    # 計算樣本數
    samples_per_ms = chunk.metadata.sample_rate // 1000
    fade_in_samples = fade_in_ms * samples_per_ms * chunk.metadata.channels
    fade_out_samples = fade_out_ms * samples_per_ms * chunk.metadata.channels
    
    # 應用淡入
    if fade_in_samples > 0:
        fade_in_samples = min(fade_in_samples, len(audio_np))
        fade_in_curve = np.linspace(0, 1, fade_in_samples)
        audio_np[:fade_in_samples] *= fade_in_curve
    
    # 應用淡出
    if fade_out_samples > 0:
        fade_out_samples = min(fade_out_samples, len(audio_np))
        fade_out_curve = np.linspace(1, 0, fade_out_samples)
        audio_np[-fade_out_samples:] *= fade_out_curve
    
    # 轉換回原始類型
    faded_data = audio_np.astype(dtype).tobytes()
    
    return AudioChunk(
        data=faded_data,
        metadata=chunk.metadata,
        timestamp=chunk.timestamp,
        sequence_number=chunk.sequence_number,
        is_final=chunk.is_final
    )


def trim_silence(chunk: AudioChunk,
                threshold_db: float = -40,
                min_silence_ms: int = 100) -> AudioChunk:
    """
    修剪音訊開頭和結尾的靜音
    
    Args:
        chunk: 音訊塊
        threshold_db: 靜音閾值（分貝）
        min_silence_ms: 最小靜音時長（毫秒）
        
    Returns:
        修剪後的音訊塊
    """
    # 轉換為 numpy
    dtype = chunk.metadata.format.numpy_dtype
    if dtype is None:
        raise ValueError(f"不支援的格式: {chunk.metadata.format}")
    
    audio_np = np.frombuffer(chunk.data, dtype=dtype)
    
    # 正規化
    if dtype == np.int16:
        audio_normalized = audio_np.astype(np.float32) / 32768.0
    elif dtype == np.int32:
        audio_normalized = audio_np.astype(np.float32) / 2147483648.0
    else:
        audio_normalized = audio_np.astype(np.float32)
    
    # 計算能量閾值
    threshold_linear = 10 ** (threshold_db / 20.0)
    
    # 計算每個樣本的能量
    energy = np.abs(audio_normalized)
    
    # 找出非靜音區域
    non_silent = energy > threshold_linear
    
    # 計算最小靜音樣本數
    samples_per_ms = chunk.metadata.sample_rate // 1000
    min_silence_samples = min_silence_ms * samples_per_ms * chunk.metadata.channels
    
    # 找出開始和結束位置
    non_silent_indices = np.where(non_silent)[0]
    
    if len(non_silent_indices) == 0:
        # 全部是靜音
        return AudioChunk(
            data=b'',
            metadata=chunk.metadata,
            timestamp=chunk.timestamp,
            sequence_number=chunk.sequence_number,
            is_final=chunk.is_final
        )
    
    start = non_silent_indices[0]
    end = non_silent_indices[-1] + 1
    
    # 修剪音訊
    trimmed_audio = audio_np[start:end]
    trimmed_data = trimmed_audio.tobytes()
    
    return AudioChunk(
        data=trimmed_data,
        metadata=chunk.metadata,
        timestamp=chunk.timestamp + (start / chunk.metadata.sample_rate / chunk.metadata.channels),
        sequence_number=chunk.sequence_number,
        is_final=chunk.is_final
    )


def generate_silence(duration_ms: int,
                    sample_rate: int = 16000,
                    channels: int = 1,
                    format: AudioSampleFormat = AudioSampleFormat.INT16) -> AudioChunk:
    """
    生成靜音音訊
    
    Args:
        duration_ms: 時長（毫秒）
        sample_rate: 採樣率
        channels: 聲道數
        format: 音訊格式
        
    Returns:
        靜音音訊塊
    """
    # 計算樣本數
    samples = (duration_ms * sample_rate * channels) // 1000
    
    # 生成靜音資料
    dtype = format.numpy_dtype
    if dtype is None:
        raise ValueError(f"不支援的格式: {format}")
    
    silence = np.zeros(samples, dtype=dtype)
    silence_data = silence.tobytes()
    
    metadata = AudioMetadata(
        sample_rate=sample_rate,
        channels=channels,
        format=format
    )
    
    return AudioChunk(
        data=silence_data,
        metadata=metadata
    )


def generate_tone(frequency: float,
                 duration_ms: int,
                 amplitude: float = 0.5,
                 sample_rate: int = 16000,
                 channels: int = 1,
                 format: AudioSampleFormat = AudioSampleFormat.INT16) -> AudioChunk:
    """
    生成純音（正弦波）
    
    Args:
        frequency: 頻率（Hz）
        duration_ms: 時長（毫秒）
        amplitude: 振幅（0-1）
        sample_rate: 採樣率
        channels: 聲道數
        format: 音訊格式
        
    Returns:
        純音音訊塊
    """
    # 計算樣本數
    duration_s = duration_ms / 1000.0
    samples = int(duration_s * sample_rate)
    
    # 生成時間軸
    t = np.linspace(0, duration_s, samples, endpoint=False)
    
    # 生成正弦波
    tone = amplitude * np.sin(2 * np.pi * frequency * t)
    
    # 如果是立體聲，複製到所有聲道
    if channels > 1:
        tone = np.tile(tone, channels)
    
    # 轉換為目標格式
    if format == AudioSampleFormat.INT16:
        tone = (tone * 32767).astype(np.int16)
    elif format == AudioSampleFormat.INT32:
        tone = (tone * 2147483647).astype(np.int32)
    elif format == AudioSampleFormat.FLOAT32:
        tone = tone.astype(np.float32)
    else:
        raise ValueError(f"不支援的格式: {format}")
    
    tone_data = tone.tobytes()
    
    metadata = AudioMetadata(
        sample_rate=sample_rate,
        channels=channels,
        format=format
    )
    
    return AudioChunk(
        data=tone_data,
        metadata=metadata
    )


def create_audio_chunk_from_params(audio_data: bytes,
                                  sample_rate: int,
                                  channels: int,
                                  format: AudioSampleFormat = AudioSampleFormat.INT16,
                                  source_type: str = "unknown") -> AudioChunk:
    """
    從參數創建 AudioChunk（替代 AudioChunkFactory）
    
    Args:
        audio_data: 音訊資料
        sample_rate: 採樣率
        channels: 聲道數
        format: 音訊格式
        source_type: 來源類型
        
    Returns:
        AudioChunk 實例
    """
    metadata = AudioMetadata(
        sample_rate=sample_rate,
        channels=channels,
        format=format
    )
    
    return AudioChunk(
        data=audio_data,
        metadata=metadata,
        source_info={"type": source_type}
    )


# 音訊數據包功能（整合自 packet_utils.py）
class AudioPacket:
    """
    包含元數據的音頻數據包
    格式: [header][audio_data]
    """
    
    MAGIC = b'ASRH'  # ASRHub
    VERSION = 1
    HEADER_FORMAT = '>4sBBBII'  # magic(4) version(1) format(1) channels(1) rate(4) size(4)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    def __init__(self, audio_data: bytes, metadata: AudioMetadata):
        self.audio_data = audio_data
        self.metadata = metadata
    
    def pack(self) -> bytes:
        """打包為二進制數據"""
        format_code = {
            AudioSampleFormat.INT16: 1,
            AudioSampleFormat.INT24: 2,
            AudioSampleFormat.INT32: 3,
            AudioSampleFormat.FLOAT32: 4
        }[self.metadata.format]
        
        header = struct.pack(
            self.HEADER_FORMAT,
            self.MAGIC,
            self.VERSION,
            format_code,
            self.metadata.channels,
            self.metadata.sample_rate,
            len(self.audio_data)
        )
        
        return header + self.audio_data
    
    @classmethod
    def unpack(cls, packet_data: bytes) -> 'AudioPacket':
        """從二進制數據解包"""
        if len(packet_data) < cls.HEADER_SIZE:
            raise ValueError("Packet data too small")
        
        # 解析頭部
        magic, version, format_code, channels, sample_rate, data_size = struct.unpack(
            cls.HEADER_FORMAT,
            packet_data[:cls.HEADER_SIZE]
        )
        
        # 驗證魔數
        if magic != cls.MAGIC:
            raise ValueError(f"Invalid magic: {magic}")
        
        # 驗證版本
        if version != cls.VERSION:
            raise ValueError(f"Unsupported version: {version}")
        
        # 解析格式
        format_map = {
            1: AudioSampleFormat.INT16,
            2: AudioSampleFormat.INT24,
            3: AudioSampleFormat.INT32,
            4: AudioSampleFormat.FLOAT32
        }
        
        if format_code not in format_map:
            raise ValueError(f"Invalid format code: {format_code}")
        
        audio_format = format_map[format_code]
        
        # 驗證數據大小
        expected_size = cls.HEADER_SIZE + data_size
        if len(packet_data) < expected_size:
            raise ValueError(f"Packet data incomplete: expected {expected_size}, got {len(packet_data)}")
        
        # 提取音頻數據
        audio_data = packet_data[cls.HEADER_SIZE:cls.HEADER_SIZE + data_size]
        
        if len(audio_data) != data_size:
            raise ValueError(f"Data size mismatch: expected {data_size}, got {len(audio_data)}")
        
        # 創建元數據
        metadata = AudioMetadata(
            sample_rate=sample_rate,
            channels=channels,
            format=audio_format
        )
        
        return cls(audio_data, metadata)


def create_audio_packet(audio_data: bytes, metadata: AudioMetadata) -> bytes:
    """
    創建音頻數據包的便捷函數
    
    Args:
        audio_data: 音頻數據
        metadata: 音頻元數據
        
    Returns:
        打包後的二進制數據
    """
    packet = AudioPacket(audio_data, metadata)
    return packet.pack()


def parse_audio_packet(packet_data: bytes) -> Tuple[bytes, AudioMetadata]:
    """
    解析音頻數據包的便捷函數
    
    Args:
        packet_data: 二進制數據包
        
    Returns:
        (音頻數據, 元數據) 的元組
    """
    packet = AudioPacket.unpack(packet_data)
    return packet.audio_data, packet.metadata