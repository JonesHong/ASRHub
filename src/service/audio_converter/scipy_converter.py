"""音訊轉換器服務

處理各種音訊格式轉換，確保 VAD、Wake Word、ASR 能正確處理。
支援 SciPy 高品質重新取樣和可選的 GPU 加速。
"""

import numpy as np
from typing import List, Optional, Tuple, Union
import io
import wave
import struct

try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    
try:
    import cupy as cp
    from cupyx.scipy import signal as cp_signal
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

from src.interface.audio_converter import IAudioConverter
from src.interface.audio import AudioChunk
from src.core.audio_queue_manager import audio_queue
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.interface.exceptions import ServiceError, ConversionError
from src.config.manager import ConfigManager


class ScipyConverter(SingletonMixin, IAudioConverter):
    """音訊格式轉換器。
    
    主要功能：
    - 從 audio_queue 拉取指定 session 的音訊
    - 轉換取樣率 (resample)
    - 轉換聲道數 (mono/stereo)
    - 轉換音訊格式 (pcm/float32 等)
    - 使用 SingletonMixin 確保單例
    """
    
    def __init__(self):
        """初始化轉換器。"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 載入配置
            config = ConfigManager()
            self.scipy_config = config.services.audio_converter.scipy
            self.defaults_config = config.services.audio_converter.defaults
            
            # 根據配置決定是否使用 GPU
            self.use_gpu = self.scipy_config.use_gpu and GPU_AVAILABLE
            self.use_scipy = SCIPY_AVAILABLE
            self.batch_size = self.scipy_config.batch_size
            self.quality = self.scipy_config.quality
            
            # 初始化訊息
            backends = []
            if self.use_gpu:
                backends.append("GPU (CuPy)")
            if self.use_scipy:
                backends.append("SciPy")
            else:
                backends.append("NumPy (fallback)")
                
            # 簡化日誌輸出
            backend_info = "GPU (CuPy)" if GPU_AVAILABLE and self.scipy_config.use_gpu else "CPU"
            logger.debug(f"ScipyConverter: {backend_info}, quality={self.quality}")
    
    def convert_for_session(
        self,
        session_id: str,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le',
        max_chunks: int = 100
    ) -> List[AudioChunk]:
        """從 audio_queue 拉取並轉換 session 的音訊。
        
        Args:
            session_id: Session ID
            target_sample_rate: 目標取樣率
            target_channels: 目標聲道數
            target_format: 目標格式
            max_chunks: 最大拉取片段數
            
        Returns:
            轉換後的音訊片段列表
        """
        # 從 audio_queue 拉取
        chunks = audio_queue.pull(session_id, count=max_chunks)
        
        if not chunks:
            return []
        
        logger.debug(f"Converting {len(chunks)} chunks for session {session_id}")
        
        # 批次轉換
        converted = self.convert_batch(
            chunks,
            target_sample_rate,
            target_channels,
            target_format
        )
        
        return converted
    
    def convert_chunk(
        self,
        chunk: AudioChunk,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> AudioChunk:
        """轉換單一音訊片段。"""
        
        # 不需要轉換就直接回傳
        if not self.needs_conversion(chunk, target_sample_rate, target_channels, target_format):
            return chunk
        
        # 先解碼成 numpy array
        audio_data = self._decode_audio(chunk)
        
        # 轉換聲道
        if chunk.channels != target_channels:
            audio_data = self._convert_channels(audio_data, chunk.channels, target_channels)
        
        # 轉換取樣率
        if chunk.sample_rate != target_sample_rate:
            audio_data = self._resample(audio_data, chunk.sample_rate, target_sample_rate)
        
        # 編碼成目標格式
        converted_bytes = self._encode_audio(audio_data, target_format)
        
        # 建立新的 AudioChunk
        return AudioChunk(
            data=converted_bytes,
            sample_rate=target_sample_rate,
            channels=target_channels,
            timestamp=chunk.timestamp,
            metadata={'format': target_format}
        )
    
    def convert_batch(
        self,
        chunks: List[AudioChunk],
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> List[AudioChunk]:
        """批次轉換音訊片段。
        
        GPU 模式下會批次處理以提高效率。
        """
        if not chunks:
            return []
        
        # GPU 批次處理
        if self.use_gpu and len(chunks) > 1:
            try:
                return self._convert_batch_gpu(
                    chunks, target_sample_rate, target_channels, target_format
                )
            except Exception as e:
                logger.warning(f"GPU batch conversion failed, falling back to sequential: {e}")
        
        # CPU 逐個處理
        converted = []
        for chunk in chunks:
            try:
                converted_chunk = self.convert_chunk(
                    chunk,
                    target_sample_rate,
                    target_channels,
                    target_format
                )
                converted.append(converted_chunk)
            except Exception as e:
                logger.error(f"Failed to convert chunk: {e}")
                continue
        
        return converted
    
    def _convert_batch_gpu(
        self,
        chunks: List[AudioChunk],
        target_sample_rate: int,
        target_channels: int,
        target_format: str
    ) -> List[AudioChunk]:
        """GPU 批次轉換 - 一次處理多個音訊片段。"""
        converted_chunks = []
        
        # 按照來源格式分組 (相同參數的一起處理)
        groups = {}
        for chunk in chunks:
            key = (chunk.sample_rate, chunk.channels, chunk.format)
            if key not in groups:
                groups[key] = []
            groups[key].append(chunk)
        
        # 批次處理每個群組
        for (src_rate, src_channels, src_format), group_chunks in groups.items():
            # 檢查是否需要轉換
            if (src_rate == target_sample_rate and 
                src_channels == target_channels and 
                src_format == target_format):
                converted_chunks.extend(group_chunks)
                continue
            
            # 解碼所有音訊
            audio_arrays = [self._decode_audio(chunk) for chunk in group_chunks]
            
            # 找出最大長度 (用於 padding)
            max_length = max(len(audio) for audio in audio_arrays)
            
            # Padding 並堆疊成批次
            padded_batch = np.zeros((len(audio_arrays), max_length), dtype=np.float32)
            original_lengths = []
            
            for i, audio in enumerate(audio_arrays):
                padded_batch[i, :len(audio)] = audio
                original_lengths.append(len(audio))
            
            # 轉換到 GPU
            batch_gpu = cp.asarray(padded_batch)
            
            # 批次聲道轉換
            if src_channels != target_channels:
                batch_gpu = self._convert_channels_batch_gpu(
                    batch_gpu, src_channels, target_channels
                )
            
            # 批次重新取樣
            if src_rate != target_sample_rate:
                batch_gpu = self._resample_batch_gpu(
                    batch_gpu, src_rate, target_sample_rate, original_lengths
                )
            
            # 轉回 CPU
            batch_cpu = cp.asnumpy(batch_gpu)
            
            # 編碼並建立新的 chunks
            for i, chunk in enumerate(group_chunks):
                # 計算新長度
                if src_rate != target_sample_rate:
                    new_length = int(original_lengths[i] * target_sample_rate / src_rate)
                else:
                    new_length = original_lengths[i]
                
                # 取出實際音訊 (去除 padding)
                audio_data = batch_cpu[i, :new_length]
                
                # 編碼
                encoded = self._encode_audio(audio_data, target_format)
                
                # 建立新 chunk
                converted_chunks.append(AudioChunk(
                    data=encoded,
                    timestamp=chunk.timestamp,
                    sample_rate=target_sample_rate,
                    channels=target_channels,
                    metadata={'format': target_format}
                ))
        
        return converted_chunks
    
    def _convert_channels_batch_gpu(
        self, 
        batch_gpu: 'cp.ndarray', 
        src_channels: int, 
        target_channels: int
    ) -> 'cp.ndarray':
        """GPU 批次聲道轉換。"""
        if src_channels == 2 and target_channels == 1:
            # Stereo to Mono - 取平均
            # 假設交錯格式 [L, R, L, R, ...]
            left = batch_gpu[:, 0::2]
            right = batch_gpu[:, 1::2]
            return (left + right) / 2.0
        elif src_channels == 1 and target_channels == 2:
            # Mono to Stereo - 複製
            return cp.repeat(batch_gpu, 2, axis=1)
        else:
            return batch_gpu
    
    def _resample_batch_gpu(
        self,
        batch_gpu: 'cp.ndarray',
        src_rate: int,
        target_rate: int,
        original_lengths: List[int]
    ) -> 'cp.ndarray':
        """GPU 批次重新取樣。"""
        batch_size, max_length = batch_gpu.shape
        target_max_length = int(max_length * target_rate / src_rate)
        
        # 建立輸出批次
        resampled_batch = cp.zeros((batch_size, target_max_length), dtype=cp.float32)
        
        # 批次 FFT 重新取樣
        for i in range(batch_size):
            audio = batch_gpu[i, :original_lengths[i]]
            target_length = int(original_lengths[i] * target_rate / src_rate)
            
            # 使用 FFT 方法重新取樣
            if target_rate < src_rate:
                # Downsampling
                nyquist = 0.5 * target_rate
                cutoff = nyquist / src_rate
                
                fft = cp.fft.rfft(audio)
                freqs = cp.fft.rfftfreq(len(audio))
                fft[freqs > cutoff] = 0
                filtered = cp.fft.irfft(fft, n=len(audio))
                
                x_old = cp.arange(len(filtered))
                x_new = cp.linspace(0, len(filtered) - 1, target_length)
                resampled = cp.interp(x_new, x_old, filtered)
            else:
                # Upsampling
                x_old = cp.arange(len(audio))
                x_new = cp.linspace(0, len(audio) - 1, target_length)
                resampled = cp.interp(x_new, x_old, audio)
            
            resampled_batch[i, :target_length] = resampled
        
        return resampled_batch
    
    def needs_conversion(
        self,
        chunk: AudioChunk,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_format: str = 'pcm_s16le'
    ) -> bool:
        """檢查是否需要轉換。"""
        current_format = chunk.metadata.get('format', 'pcm_s16le') if chunk.metadata else 'pcm_s16le'
        return (
            chunk.sample_rate != target_sample_rate or
            chunk.channels != target_channels or
            current_format != target_format
        )
    
    def _decode_audio(self, chunk: AudioChunk) -> np.ndarray:
        """解碼音訊資料為 numpy array。"""
        # 如果已經是 numpy array 直接返回
        if isinstance(chunk.data, np.ndarray):
            return chunk.data.astype(np.float32) if chunk.data.dtype != np.float32 else chunk.data
        
        if chunk.data is None or (isinstance(chunk.data, (np.ndarray, bytes)) and len(chunk.data) == 0):
            return np.array([], dtype=np.float32)
        
        # 從 metadata 取得格式
        current_format = chunk.metadata.get('format', 'pcm_s16le') if chunk.metadata else 'pcm_s16le'
        
        # PCM S16 LE
        if current_format in ['pcm_s16le', 'pcm', 's16le']:
            audio = np.frombuffer(chunk.data, dtype=np.int16)
            return audio.astype(np.float32) / 32768.0
        
        # PCM F32 LE
        elif current_format in ['pcm_f32le', 'f32le', 'float32']:
            return np.frombuffer(chunk.data, dtype=np.float32)
        
        # WAV
        elif current_format == 'wav':
            with io.BytesIO(chunk.data) as wav_io:
                with wave.open(wav_io, 'rb') as wav:
                    frames = wav.readframes(wav.getnframes())
                    audio = np.frombuffer(frames, dtype=np.int16)
                    return audio.astype(np.float32) / 32768.0
        
        else:
            raise ConversionError(f"Unsupported format: {current_format}")
    
    def _encode_audio(self, audio: np.ndarray, target_format: str) -> bytes:
        """編碼 numpy array 為目標格式。"""
        # PCM S16 LE
        if target_format in ['pcm_s16le', 'pcm', 's16le']:
            audio_int16 = (audio * 32768.0).clip(-32768, 32767).astype(np.int16)
            return audio_int16.tobytes()
        
        # PCM F32 LE
        elif target_format in ['pcm_f32le', 'f32le', 'float32']:
            return audio.astype(np.float32).tobytes()
        
        else:
            raise ConversionError(f"Unsupported target format: {target_format}")
    
    def _convert_channels(self, audio: np.ndarray, source_channels: int, target_channels: int) -> np.ndarray:
        """轉換聲道數。"""
        # Stereo to Mono
        if source_channels == 2 and target_channels == 1:
            # 假設是交錯的立體聲資料
            left = audio[0::2]
            right = audio[1::2]
            return (left + right) / 2.0
        
        # Mono to Stereo
        elif source_channels == 1 and target_channels == 2:
            # 複製單聲道到兩個聲道
            return np.repeat(audio, 2)
        
        else:
            return audio
    
    def _resample(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        """重新取樣音訊。
        
        優先順序：
        1. GPU (CuPy) - 最快，需要 CUDA
        2. SciPy - 高品質，使用 polyphase filtering
        3. NumPy - 簡單線性內插 (fallback)
        """
        if source_rate == target_rate:
            return audio
        
        # GPU 加速 (CuPy)
        if self.use_gpu:
            try:
                return self._resample_gpu(audio, source_rate, target_rate)
            except Exception as e:
                logger.warning(f"GPU resample failed, falling back to CPU: {e}")
        
        # SciPy 高品質重新取樣
        if self.use_scipy:
            try:
                return self._resample_scipy(audio, source_rate, target_rate)
            except Exception as e:
                logger.warning(f"SciPy resample failed, falling back to NumPy: {e}")
        
        # NumPy fallback
        return self._resample_numpy(audio, source_rate, target_rate)
    
    def _resample_gpu(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        """使用 GPU (CuPy) 重新取樣。"""
        # 轉換到 GPU
        audio_gpu = cp.asarray(audio)
        
        # 計算新長度
        target_length = int(len(audio) * target_rate / source_rate)
        
        # 使用 CuPy 的 FFT 重新取樣 (Fourier method)
        if target_rate < source_rate:
            # Downsampling - 需要低通濾波
            # 設計抗鋸齒濾波器
            nyquist = 0.5 * target_rate
            cutoff = nyquist / source_rate
            
            # 使用 FFT 方法
            fft = cp.fft.rfft(audio_gpu)
            freqs = cp.fft.rfftfreq(len(audio_gpu))
            
            # 低通濾波
            fft[freqs > cutoff] = 0
            
            # 反 FFT 並重新取樣
            filtered = cp.fft.irfft(fft, n=len(audio_gpu))
            
            # 使用 CuPy 的內插
            x_old = cp.arange(len(filtered))
            x_new = cp.linspace(0, len(filtered) - 1, target_length)
            resampled = cp.interp(x_new, x_old, filtered)
        else:
            # Upsampling - 直接內插
            x_old = cp.arange(len(audio_gpu))
            x_new = cp.linspace(0, len(audio_gpu) - 1, target_length)
            resampled = cp.interp(x_new, x_old, audio_gpu)
        
        # 轉回 CPU
        return cp.asnumpy(resampled).astype(np.float32)
    
    def _resample_scipy(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        """使用 SciPy 高品質重新取樣。"""
        # 使用 scipy.signal.resample_poly 進行高品質重新取樣
        # 這個方法使用 polyphase filtering，品質很好
        
        # 計算最大公約數簡化比例
        from math import gcd
        divisor = gcd(target_rate, source_rate)
        up = target_rate // divisor
        down = source_rate // divisor
        
        # 限制比例避免記憶體爆炸
        max_ratio = 100
        if up > max_ratio or down > max_ratio:
            # 使用 resample 替代
            target_length = int(len(audio) * target_rate / source_rate)
            return signal.resample(audio, target_length).astype(np.float32)
        
        # 使用 polyphase filtering
        resampled = signal.resample_poly(audio, up, down)
        return resampled.astype(np.float32)
    
    def _resample_numpy(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        """使用 NumPy 簡單線性內插 (fallback)。"""
        # 計算目標長度
        target_length = int(len(audio) * target_rate / source_rate)
        
        # 使用 NumPy 的內插
        x_old = np.arange(len(audio))
        x_new = np.linspace(0, len(audio) - 1, target_length)
        
        # 線性內插
        resampled = np.interp(x_new, x_old, audio)
        
        return resampled.astype(np.float32)


# 模組級單例實例
scipy_converter: ScipyConverter = ScipyConverter()