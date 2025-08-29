"""
音訊佇列類別
包含 AudioBuffer 和 SessionAudioQueue
管理音訊數據流的基礎組件

設計原則：
1. 數據信號分離 - 音訊數據走 AudioQueue，狀態信號走 Store
2. Session 隔離 - 每個 session 有獨立的音訊佇列
3. 環形緩衝 - 支援 pre-recording 功能
4. 異步處理 - 基於 asyncio.Queue 的非阻塞操作
"""

import asyncio
from typing import Dict, Optional, List, Tuple
from collections import deque
from datetime import datetime
import numpy as np
from src.utils.logger import logger


class AudioBuffer:
    """
    環形音訊緩衝區
    支援 pre-recording 和高效的數據管理
    """
    
    def __init__(self, max_size_seconds: float = 5.0, sample_rate: int = 16000, batch_mode: bool = False):
        """
        初始化環形緩衝區
        
        Args:
            max_size_seconds: 最大緩衝時長（秒）
            sample_rate: 採樣率
            batch_mode: 批次模式，不限制緩衝區大小
        """
        self.max_size_seconds = max_size_seconds
        self.sample_rate = sample_rate
        self.batch_mode = batch_mode
        
        if batch_mode:
            # 批次模式：無大小限制，保留所有音訊數據
            self.max_size_bytes = float('inf')
            self.buffer = deque()  # 無限制大小
            self.timestamps = deque()
            logger.info("AudioBuffer initialized in BATCH mode - unlimited buffer size")
        else:
            # 串流模式：限制大小的環形緩衝區
            self.max_size_bytes = int(max_size_seconds * sample_rate * 2)  # 16-bit audio
            self.buffer = deque(maxlen=1000)  # 最多1000個音訊塊
            self.timestamps = deque(maxlen=1000)  # 儲存時間戳記
            logger.debug(f"AudioBuffer initialized in STREAMING mode - max {self.max_size_bytes} bytes")
        
        self.total_bytes = 0  # 追踪總字節數
    
    def push(self, audio_chunk: bytes, timestamp: Optional[float] = None):
        """
        推送音訊數據到緩衝區
        
        Args:
            audio_chunk: 音訊數據
            timestamp: 時間戳記
        """
        
        if not self.batch_mode:
            # 串流模式：檢查是否超過最大緩衝大小
            while self.total_bytes + len(audio_chunk) > self.max_size_bytes and self.buffer:
                # 移除最舊的塊來釋放空間
                old_chunk = self.buffer.popleft()
                self.total_bytes -= len(old_chunk)
                if self.timestamps:
                    self.timestamps.popleft()
                # logger.info(f"AudioBuffer.push: removed old chunk of {len(old_chunk)} bytes")
        
        # 添加新的音訊塊（批次模式無大小限制）
        self.buffer.append(audio_chunk)
        self.total_bytes += len(audio_chunk)
        
        # logger.info(f"AudioBuffer.push: added chunk, new_total={self.total_bytes}, buffer_length={len(self.buffer)}")
        
        if timestamp is None:
            timestamp = asyncio.get_event_loop().time()
        self.timestamps.append(timestamp)
    
    def get_recent(self, seconds: float) -> bytes:
        """
        獲取最近 N 秒的音訊
        
        Args:
            seconds: 要獲取的秒數
            
        Returns:
            音訊數據
        """
        target_bytes = int(seconds * self.sample_rate * 2)
        
        # 從最新的塊開始收集數據，直到達到目標字節數
        collected_bytes = 0
        selected_chunks = []
        
        # 從後往前遍歷塊
        for chunk in reversed(self.buffer):
            selected_chunks.insert(0, chunk)  # 插入到前面保持順序
            collected_bytes += len(chunk)
            if collected_bytes >= target_bytes:
                break
        
        # 連接所有選中的塊
        if selected_chunks:
            all_data = b''.join(selected_chunks)
            # 如果數據太多，只返回最後的目標字節數
            if len(all_data) > target_bytes:
                return all_data[-target_bytes:]
            return all_data
        else:
            return b''
    
    def clear(self):
        """清空緩衝區"""
        self.buffer.clear()
        self.timestamps.clear()
        self.total_bytes = 0
    
    def size_seconds(self) -> float:
        """獲取當前緩衝區的時長（秒）"""
        return self.total_bytes / (self.sample_rate * 2)


class SessionAudioQueue:
    """
    單個 Session 的音訊佇列
    管理該 session 的所有音訊數據流
    """
    
    def __init__(self, session_id: str, max_queue_size: int = 100, batch_mode: bool = False):
        """
        初始化 Session 音訊佇列
        
        Args:
            session_id: Session ID
            max_queue_size: 佇列最大長度
            batch_mode: 批次模式，用於文件上傳場景
        """
        self.session_id = session_id
        self.batch_mode = batch_mode
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        
        # 根據模式選擇緩衝區策略
        if batch_mode:
            self.pre_buffer = AudioBuffer(max_size_seconds=5.0, batch_mode=True)  # 無限制批次緩衝
            logger.info(f"SessionAudioQueue {session_id} initialized in BATCH mode")
        else:
            self.pre_buffer = AudioBuffer(max_size_seconds=5.0, batch_mode=False)  # 5秒 pre-recording
            logger.debug(f"SessionAudioQueue {session_id} initialized in STREAMING mode")
            
        self.wake_word_window = AudioBuffer(max_size_seconds=3.0)  # 3秒喚醒詞窗口
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # 統計資訊
        self.total_chunks = 0
        self.total_bytes = 0
    
    async def push(self, audio_chunk: bytes, timestamp: Optional[float] = None):
        """
        推送音訊數據
        
        Args:
            audio_chunk: 音訊數據
            timestamp: 時間戳記
        """
        self.last_activity = datetime.now()
        self.total_chunks += 1
        self.total_bytes += len(audio_chunk)
        
        # 總是推送到 pre-buffer（環形緩衝）
        self.pre_buffer.push(audio_chunk, timestamp)
        
        # 推送到喚醒詞窗口（環形緩衝）
        self.wake_word_window.push(audio_chunk, timestamp)
        
        # 推送到異步佇列供即時處理
        try:
            await self.queue.put(audio_chunk)
        except asyncio.QueueFull:
            logger.warning(f"Audio queue full for session {self.session_id}, dropping chunk")
    
    async def pull(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        拉取音訊數據
        
        Args:
            timeout: 超時時間（秒）
            
        Returns:
            音訊數據，如果超時則返回 None
        """
        try:
            if timeout:
                return await asyncio.wait_for(self.queue.get(), timeout)
            else:
                return await self.queue.get()
        except asyncio.TimeoutError:
            return None
    
    def get_pre_buffer_data(self, seconds: float = 2.0) -> bytes:
        """
        獲取 pre-buffer 數據（供 RecordingOperator 使用）
        
        Args:
            seconds: 要獲取的秒數
            
        Returns:
            pre-buffer 音訊數據
        """
        return self.pre_buffer.get_recent(seconds)
    
    def get_all_audio(self) -> bytes:
        """
        獲取所有推送的音訊數據（用於批次上傳模式）
        從 pre_buffer 中獲取所有可用數據
        
        Returns:
            所有推送的音訊數據
        """
        logger.info(f"SessionAudioQueue.get_all_audio: session={self.session_id}, pre_buffer.total_bytes={self.pre_buffer.total_bytes}, buffer_length={len(self.pre_buffer.buffer)}")
        
        # 從 pre_buffer 的 deque 中獲取所有數據並連接成 bytes
        if self.pre_buffer.buffer:
            # buffer 裡面存儲的是 bytes 塊列表，需要將它們連接起來
            audio_data = b''.join(self.pre_buffer.buffer)
            logger.info(f"SessionAudioQueue.get_all_audio: joined {len(self.pre_buffer.buffer)} chunks into {len(audio_data)} bytes")
        else:
            audio_data = b''
            logger.info(f"SessionAudioQueue.get_all_audio: pre_buffer.buffer is empty")
        
        logger.info(f"Retrieved all audio for session {self.session_id}, total {len(audio_data)} bytes")
        return audio_data
    
    def get_wake_word_audio(self) -> bytes:
        """
        獲取喚醒詞檢測窗口的音訊
        
        Returns:
            最近3秒的音訊數據
        """
        return self.wake_word_window.get_recent(3.0)
    
    def get_stats(self) -> Dict:
        """獲取統計資訊"""
        return {
            "session_id": self.session_id,
            "total_chunks": self.total_chunks,
            "total_bytes": self.total_bytes,
            "queue_size": self.queue.qsize(),
            "pre_buffer_seconds": self.pre_buffer.size_seconds(),
            "wake_word_window_seconds": self.wake_word_window.size_seconds(),
            "batch_mode": self.batch_mode,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat()
        }
    
    async def cleanup(self):
        """清理資源"""
        # 清空佇列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # 清空緩衝區
        self.pre_buffer.clear()
        self.wake_word_window.clear()
        
        logger.debug(f"Cleaned up audio queue for session {self.session_id}")