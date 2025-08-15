"""
ASR Hub 音訊緩衝區管理器
管理循環緩衝區、錄音緩衝區和喚醒詞窗口
"""

from typing import Optional, List, Deque
from collections import deque
import numpy as np
from datetime import datetime, timedelta

from src.utils.logger import logger
from src.models.audio import AudioChunk
from src.core.fsm import FSMController, FSMState


class RingBuffer:
    """循環緩衝區實現"""
    
    def __init__(self, size_seconds: int = 30, sample_rate: int = 16000):
        """
        初始化循環緩衝區
        
        Args:
            size_seconds: 緩衝區大小（秒）
            sample_rate: 採樣率
        """
        self.size_seconds = size_seconds
        self.sample_rate = sample_rate
        self.max_samples = size_seconds * sample_rate
        self.buffer: Deque[AudioChunk] = deque(maxlen=self.max_samples // 512)  # 假設每個 chunk 512 樣本
        self.total_samples = 0
        self.logger = logger
        
    def append(self, chunk: AudioChunk):
        """
        添加音訊塊到緩衝區
        
        Args:
            chunk: 音訊塊
        """
        self.buffer.append(chunk)
        self.total_samples += len(chunk.data)
        
        # 如果超過最大大小，自動丟棄最舊的數據（deque 的 maxlen 自動處理）
        if len(self.buffer) == self.buffer.maxlen:
            self.logger.debug(f"循環緩衝區已滿，丟棄最舊數據")
    
    def get_audio(self, duration_seconds: Optional[float] = None) -> bytes:
        """
        獲取緩衝區中的音訊
        
        Args:
            duration_seconds: 要獲取的時長（秒），如果為 None 則返回全部
            
        Returns:
            音訊數據
        """
        if not self.buffer:
            return b''
        
        if duration_seconds is None:
            # 返回全部數據
            return b''.join([chunk.data for chunk in self.buffer])
        else:
            # 計算需要的 chunk 數量
            chunks_needed = int(duration_seconds * self.sample_rate / 512)
            chunks_to_get = min(chunks_needed, len(self.buffer))
            
            # 從最新的數據開始獲取
            recent_chunks = list(self.buffer)[-chunks_to_get:]
            return b''.join([chunk.data for chunk in recent_chunks])
    
    def clear(self):
        """清空緩衝區"""
        self.buffer.clear()
        self.total_samples = 0
        self.logger.debug("循環緩衝區已清空")
    
    def get_size(self) -> int:
        """獲取緩衝區當前大小（樣本數）"""
        return sum(len(chunk.data) for chunk in self.buffer)


class SlidingWindow:
    """滑動窗口實現（用於喚醒詞檢測）"""
    
    def __init__(self, size: int = 3, sample_rate: int = 16000):
        """
        初始化滑動窗口
        
        Args:
            size: 窗口大小（秒）
            sample_rate: 採樣率
        """
        self.size = size
        self.sample_rate = sample_rate
        self.max_samples = size * sample_rate
        self.window: List[AudioChunk] = []
        self.logger = logger
        
    def update(self, chunk: AudioChunk):
        """
        更新滑動窗口
        
        Args:
            chunk: 音訊塊
        """
        self.window.append(chunk)
        
        # 移除過舊的數據
        while self.get_duration() > self.size:
            self.window.pop(0)
    
    def get_audio(self) -> bytes:
        """
        獲取窗口中的音訊
        
        Returns:
            音訊數據
        """
        if not self.window:
            return b''
        return b''.join([chunk.data for chunk in self.window])
    
    def get_duration(self) -> float:
        """
        獲取窗口當前時長（秒）
        
        Returns:
            時長
        """
        if not self.window:
            return 0.0
        
        total_samples = sum(len(chunk.data) // 2 for chunk in self.window)  # 假設 16-bit 音訊
        return total_samples / self.sample_rate
    
    def clear(self):
        """清空窗口"""
        self.window.clear()


class AudioBufferManager:
    """音訊緩衝區管理器"""
    
    def __init__(self, ring_buffer_size: int = 30, 
                 fsm_controller: Optional[FSMController] = None,
                 sample_rate: int = 16000):
        """
        初始化緩衝區管理器
        
        Args:
            ring_buffer_size: 循環緩衝區大小（秒）
            fsm_controller: FSM 控制器
            sample_rate: 採樣率
        """
        self.ring_buffer = RingBuffer(ring_buffer_size, sample_rate)
        self.recording_buffer: List[AudioChunk] = []
        self.wake_word_window = SlidingWindow(size=3, sample_rate=sample_rate)
        self.fsm = fsm_controller
        self.sample_rate = sample_rate
        self.logger = logger
        
        # 統計資訊
        self.total_chunks_received = 0
        self.total_bytes_processed = 0
        self.recording_start_time: Optional[datetime] = None
        
        # 串流緩衝區
        self.streaming_buffer: List[AudioChunk] = []
        
        self.logger.info(f"音訊緩衝區管理器初始化完成，循環緩衝區：{ring_buffer_size}秒")
    
    def add_chunk(self, chunk: AudioChunk):
        """
        添加音訊塊到緩衝區
        
        Args:
            chunk: 音訊塊
        """
        # 更新統計
        self.total_chunks_received += 1
        self.total_bytes_processed += len(chunk.data)
        
        # 添加到循環緩衝區
        self.ring_buffer.append(chunk)
        
        # 更新喚醒詞窗口
        self.wake_word_window.update(chunk)
        
        # 根據 FSM 狀態決定是否錄音
        if self.should_buffer_for_recording():
            if not self.recording_buffer and not self.recording_start_time:
                self.recording_start_time = datetime.now()
                self.logger.debug("開始錄音緩衝")
            self.recording_buffer.append(chunk)
        
        # 根據 FSM 狀態決定是否串流
        if self.should_stream():
            self.streaming_buffer.append(chunk)
    
    def should_buffer_for_recording(self) -> bool:
        """
        根據 FSM 狀態判斷是否需要緩衝錄音
        
        Returns:
            是否需要緩衝
        """
        return self.fsm and self.fsm.state == FSMState.RECORDING
    
    def should_stream(self) -> bool:
        """
        根據 FSM 狀態判斷是否需要串流
        
        Returns:
            是否需要串流
        """
        return self.fsm and self.fsm.state == FSMState.STREAMING
    
    def should_pause_for_reply(self) -> bool:
        """
        根據 FSM 狀態判斷是否需要暫停（半雙工）
        
        Returns:
            是否需要暫停
        """
        return self.fsm and self.fsm.state == FSMState.BUSY
    
    def get_wake_word_buffer(self) -> bytes:
        """
        獲取喚醒詞檢測窗口的音訊
        
        Returns:
            音訊數據
        """
        return self.wake_word_window.get_audio()
    
    def get_recording_buffer(self) -> bytes:
        """
        獲取完整的錄音緩衝
        
        Returns:
            音訊數據
        """
        if not self.recording_buffer:
            return b''
        return b''.join([chunk.data for chunk in self.recording_buffer])
    
    def get_streaming_buffer(self) -> bytes:
        """
        獲取並清空串流緩衝
        
        Returns:
            音訊數據
        """
        if not self.streaming_buffer:
            return b''
        
        data = b''.join([chunk.data for chunk in self.streaming_buffer])
        self.streaming_buffer.clear()
        return data
    
    def clear_recording_buffer(self):
        """清空錄音緩衝"""
        self.recording_buffer.clear()
        self.recording_start_time = None
        self.logger.debug("錄音緩衝已清空")
    
    def clear_streaming_buffer(self):
        """清空串流緩衝"""
        self.streaming_buffer.clear()
        self.logger.debug("串流緩衝已清空")
    
    def get_recording_duration(self) -> float:
        """
        獲取當前錄音時長（秒）
        
        Returns:
            錄音時長
        """
        if not self.recording_buffer:
            return 0.0
        
        total_samples = sum(len(chunk.data) // 2 for chunk in self.recording_buffer)
        return total_samples / self.sample_rate
    
    def get_recent_audio(self, duration_seconds: float = 5.0) -> bytes:
        """
        獲取最近的音訊數據
        
        Args:
            duration_seconds: 要獲取的時長（秒）
            
        Returns:
            音訊數據
        """
        return self.ring_buffer.get_audio(duration_seconds)
    
    def get_buffer_info(self) -> dict:
        """
        獲取緩衝區資訊
        
        Returns:
            緩衝區資訊字典
        """
        info = {
            "ring_buffer_size": self.ring_buffer.get_size(),
            "recording_buffer_size": len(self.recording_buffer),
            "streaming_buffer_size": len(self.streaming_buffer),
            "wake_word_window_duration": self.wake_word_window.get_duration(),
            "total_chunks_received": self.total_chunks_received,
            "total_bytes_processed": self.total_bytes_processed,
            "is_recording": bool(self.recording_buffer),
            "is_streaming": bool(self.streaming_buffer),
        }
        
        if self.recording_start_time:
            info["recording_duration"] = (datetime.now() - self.recording_start_time).total_seconds()
        
        return info
    
    def reset(self):
        """重置所有緩衝區"""
        self.ring_buffer.clear()
        self.recording_buffer.clear()
        self.streaming_buffer.clear()
        self.wake_word_window.clear()
        self.recording_start_time = None
        self.total_chunks_received = 0
        self.total_bytes_processed = 0
        self.logger.info("所有緩衝區已重置")