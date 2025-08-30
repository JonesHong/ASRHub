"""麥克風擷取

從本地麥克風擷取音訊資料，支援即時串流和回調。
使用 pyaudio 或 sounddevice 作為後端。
"""

import threading
import queue
import time
from typing import Optional, Callable, List, Dict, Any
import numpy as np

from src.utils.singleton import SingletonMixin

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

from src.interface.microphone import IMicrophoneService
from src.utils.logger import logger
from src.config.manager import ConfigManager


class MicrophoneCapture(SingletonMixin,IMicrophoneService):
    """麥克風擷取實現。
    
    特性：
    - 支援 sounddevice 和 pyaudio 後端
    - 即時音訊串流
    - 回調機制
    - 線程安全
    - 自動選擇最佳後端
    """
    
    def __init__(self):
        """初始化麥克風服務。"""
        if not hasattr(self, '_initialized'):
            self._initialized = False
            
            # 載入配置
            config = ConfigManager()
            if hasattr(config, 'services') and hasattr(config.services, 'microphone'):
                self.mic_config = config.services.microphone
            else:
                logger.warning("麥克風配置不存在")
                return
            
            # 檢查是否啟用
            if not self.mic_config.enabled:
                logger.info("Microphone 服務已停用 (enabled: false)")
                return
            
            # 選擇後端
            backend_preference = self.mic_config.backend
            if backend_preference == 'auto':
                if HAS_SOUNDDEVICE:
                    self._backend = 'sounddevice'
                    logger.info("Using sounddevice backend for microphone")
                elif HAS_PYAUDIO:
                    self._backend = 'pyaudio'
                    self._pyaudio = pyaudio.PyAudio()
                    logger.info("Using PyAudio backend for microphone")
                else:
                    self._backend = None
                    logger.error("No audio backend available! Install sounddevice or pyaudio")
            elif backend_preference == 'sounddevice':
                if HAS_SOUNDDEVICE:
                    self._backend = 'sounddevice'
                    logger.info("Using sounddevice backend for microphone")
                else:
                    logger.error(f"Requested backend {backend_preference} not available")
                    self._backend = None
            elif backend_preference == 'pyaudio':
                if HAS_PYAUDIO:
                    self._backend = 'pyaudio'
                    self._pyaudio = pyaudio.PyAudio()
                    logger.info("Using PyAudio backend for microphone")
                else:
                    logger.error(f"Requested backend {backend_preference} not available")
                    self._backend = None
            
            # 音訊參數 - 使用統一後的欄位名稱（移除 mic_ 前綴）
            self._sample_rate = self.mic_config.sample_rate
            self._channels = self.mic_config.channels
            self._chunk_size = self.mic_config.chunk_size
            # 強制使用 int16 格式，提供更好的 OpenWakeWord 相容性
            self._dtype = np.int16
            logger.info(f"Microphone capture forced to use int16 format for optimal compatibility")
            
            # 狀態管理
            self._is_capturing = False
            self._capture_thread = None
            self._callback = None
            self._device_index = self.mic_config.device_index
            self._stream = None
            
            # 資料緩衝 - 從配置載入佇列大小
            self._audio_queue = queue.Queue(maxsize=self.mic_config.queue_size)
            self._lock = threading.Lock()
            
            self._initialized = True
            logger.info(f"MicrophoneCapture initialized with backend: {self._backend}")
    
    def start_capture(self, callback: Optional[Callable] = None) -> bool:
        """開始擷取麥克風音訊。
        
        Args:
            callback: 音訊資料回調函數，接收 (audio_data, sample_rate)
            
        Returns:
            是否成功開始擷取
        """
        with self._lock:
            if self._is_capturing:
                logger.warning("Already capturing audio")
                return False
            
            if self._backend is None:
                logger.error("No audio backend available")
                return False
            
            self._callback = callback
            self._is_capturing = True
            
            # 啟動擷取執行緒
            self._capture_thread = threading.Thread(
                target=self._capture_worker,
                name="microphone-capture"
            )
            self._capture_thread.daemon = True
            self._capture_thread.start()
            
            logger.info(f"🎤 [MIC_CAPTURE] Started microphone capture:")
            logger.info(f"   - Sample Rate: {self._sample_rate} Hz")
            logger.info(f"   - Channels: {self._channels}")
            logger.info(f"   - Chunk Size: {self._chunk_size} frames")
            logger.info(f"   - Data Type: {self._dtype} (int16)")
            logger.info(f"   - Backend: {self._backend}")
            return True
    
    def stop_capture(self) -> bool:
        """停止擷取。
        
        Returns:
            是否成功停止
        """
        with self._lock:
            if not self._is_capturing:
                logger.warning("Not capturing audio")
                return False
            
            self._is_capturing = False
            
            # 等待執行緒結束
            if self._capture_thread and self._capture_thread.is_alive():
                self._capture_thread.join(timeout=2.0)
            
            # 清理資源
            if self._stream:
                if self._backend == 'sounddevice':
                    self._stream.stop()
                    self._stream.close()
                elif self._backend == 'pyaudio' and self._stream.is_active():
                    self._stream.stop_stream()
                    self._stream.close()
                self._stream = None
            
            # 清空佇列
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break
            
            logger.info("Stopped microphone capture")
            return True
    
    def is_capturing(self) -> bool:
        """檢查是否正在擷取。
        
        Returns:
            是否正在擷取
        """
        return self._is_capturing
    
    def get_devices(self) -> List[Dict[str, Any]]:
        """取得可用的音訊裝置列表。
        
        Returns:
            裝置列表
        """
        devices = []
        
        if self._backend == 'sounddevice':
            device_list = sd.query_devices()
            for i, device in enumerate(device_list):
                if device['max_input_channels'] > 0:
                    devices.append({
                        'index': i,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': device['default_samplerate']
                    })
        
        elif self._backend == 'pyaudio':
            for i in range(self._pyaudio.get_device_count()):
                info = self._pyaudio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    devices.append({
                        'index': i,
                        'name': info['name'],
                        'channels': info['maxInputChannels'],
                        'sample_rate': info['defaultSampleRate']
                    })
        
        return devices
    
    def set_device(self, device_index: int) -> bool:
        """設定使用的音訊裝置。
        
        Args:
            device_index: 裝置索引
            
        Returns:
            是否設定成功
        """
        if self._is_capturing:
            logger.error("Cannot change device while capturing")
            return False
        
        self._device_index = device_index
        logger.info(f"Set audio device to index {device_index}")
        return True
    
    def read_chunk(self, frames: int = 1024) -> Optional[np.ndarray]:
        """讀取一個音訊片段（非阻塞）。
        
        Args:
            frames: 要讀取的幀數（未使用，為了相容性）
            
        Returns:
            音訊資料 numpy array，如果沒有資料返回 None
        """
        try:
            audio_data = self._audio_queue.get_nowait()
            return audio_data
        except queue.Empty:
            return None
    
    def set_parameters(self, sample_rate: int = None, channels: int = None, 
                      chunk_size: int = None):
        """設定音訊參數。
        
        Args:
            sample_rate: 取樣率 (None 使用配置預設值)
            channels: 聲道數 (None 使用配置預設值)
            chunk_size: 緩衝區大小 (None 使用配置預設值)
        """
        if self._is_capturing:
            logger.error("Cannot change parameters while capturing")
            return False
        
        # 使用配置預設值
        self._sample_rate = sample_rate or self.mic_config.sample_rate
        self._channels = channels or self.mic_config.channels
        self._chunk_size = chunk_size or self.mic_config.chunk_size
        
        # 確保 dtype 始終是 int16
        self._dtype = np.int16
        
        logger.info(f"Audio parameters set: rate={self._sample_rate}, channels={self._channels}, chunk={self._chunk_size}, dtype=int16")
        return True
    
    def _capture_worker(self):
        """擷取工作執行緒。"""
        try:
            if self._backend == 'sounddevice':
                self._capture_with_sounddevice()
            elif self._backend == 'pyaudio':
                self._capture_with_pyaudio()
        except Exception as e:
            logger.error(f"Capture error: {e}")
        finally:
            self._is_capturing = False
    
    def _capture_with_sounddevice(self):
        """使用 sounddevice 擷取音訊。"""
        def audio_callback(indata, frames, time_info, status):
            """sounddevice 回調函數。"""
            if status:
                logger.warning(f"Audio status: {status}")
            
            # 複製資料（避免修改原始緩衝區）
            audio_data = indata[:, 0].copy() if self._channels == 1 else indata.copy()
            
            # 放入佇列
            try:
                self._audio_queue.put_nowait(audio_data)
            except queue.Full:
                # 佇列滿了，丟棄最舊的
                try:
                    self._audio_queue.get_nowait()
                    self._audio_queue.put_nowait(audio_data)
                except queue.Empty:
                    pass
            
            # 執行回調
            if self._callback:
                try:
                    # 記錄發送的音訊格式（只記錄第一次）
                    # if not hasattr(self, '_first_callback_logged'):
                    #     self._first_callback_logged = True
                    #     logger.info(f"📤 [MIC_CAPTURE->CALLBACK] First audio sent: shape={audio_data.shape}, dtype={audio_data.dtype}, sample_rate={self._sample_rate}")
                    self._callback(audio_data, self._sample_rate)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
        
        # 開啟串流 - 強制使用 int16
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype=np.int16,  # 強制 int16
            blocksize=self._chunk_size,
            device=self._device_index,
            callback=audio_callback
        )
        
        self._stream.start()
        
        # 保持執行緒運行
        while self._is_capturing:
            time.sleep(0.1)
        
        self._stream.stop()
        self._stream.close()
    
    def _capture_with_pyaudio(self):
        """使用 PyAudio 擷取音訊。"""
        # 開啟串流 - 強制使用 int16
        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16,  # 強制 int16
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            input_device_index=self._device_index,
            frames_per_buffer=self._chunk_size
        )
        
        # 持續讀取
        while self._is_capturing:
            try:
                # 讀取音訊資料
                data = self._stream.read(self._chunk_size, exception_on_overflow=False)
                
                # 轉換為 numpy array (int16)
                audio_data = np.frombuffer(data, dtype=np.int16)
                if self._channels == 2:
                    audio_data = audio_data.reshape(-1, 2)
                
                # 放入佇列
                try:
                    self._audio_queue.put_nowait(audio_data)
                except queue.Full:
                    # 佇列滿了，丟棄最舊的
                    try:
                        self._audio_queue.get_nowait()
                        self._audio_queue.put_nowait(audio_data)
                    except queue.Empty:
                        pass
                
                # 執行回調
                if self._callback:
                    try:
                        self._callback(audio_data, self._sample_rate)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
                        
            except Exception as e:
                if self._is_capturing:  # 只在還在擷取時報錯
                    logger.error(f"Read error: {e}")
                    time.sleep(0.01)
        
        self._stream.stop_stream()
        self._stream.close()
    
    def __del__(self):
        """清理資源。"""
        if hasattr(self, '_stream') and self._stream:
            self.stop_capture()
        
        if hasattr(self, '_backend') and self._backend == 'pyaudio':
            if hasattr(self, '_pyaudio'):
                self._pyaudio.terminate()


# 模組級單例
microphone_capture: MicrophoneCapture = MicrophoneCapture()

# 相容性匯出
__all__ = ['microphone_capture', 'MicrophoneCapture']