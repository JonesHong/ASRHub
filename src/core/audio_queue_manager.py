"""
音訊佇列管理器
管理音訊數據流，與 PyStoreX 信號分離

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
    
    def __init__(self, max_size_seconds: float = 5.0, sample_rate: int = 16000):
        """
        初始化環形緩衝區
        
        Args:
            max_size_seconds: 最大緩衝時長（秒）
            sample_rate: 採樣率
        """
        self.max_size_seconds = max_size_seconds
        self.sample_rate = sample_rate
        self.max_size_bytes = int(max_size_seconds * sample_rate * 2)  # 16-bit audio
        
        # 使用 deque 實現環形緩衝
        self.buffer = deque(maxlen=self.max_size_bytes)
        self.timestamps = deque(maxlen=1000)  # 儲存時間戳記
    
    def push(self, audio_chunk: bytes, timestamp: Optional[float] = None):
        """
        推送音訊數據到緩衝區
        
        Args:
            audio_chunk: 音訊數據
            timestamp: 時間戳記
        """
        # 如果緩衝區滿了，舊數據會自動被移除
        self.buffer.extend(audio_chunk)
        
        if timestamp is None:
            timestamp = asyncio.get_event_loop().time()
        self.timestamps.append((len(self.buffer), timestamp))
    
    def get_recent(self, seconds: float) -> bytes:
        """
        獲取最近 N 秒的音訊
        
        Args:
            seconds: 要獲取的秒數
            
        Returns:
            音訊數據
        """
        num_bytes = int(seconds * self.sample_rate * 2)
        num_bytes = min(num_bytes, len(self.buffer))
        
        # 從緩衝區末尾取數據
        recent_data = bytes(list(self.buffer)[-num_bytes:]) if num_bytes > 0 else b''
        return recent_data
    
    def clear(self):
        """清空緩衝區"""
        self.buffer.clear()
        self.timestamps.clear()
    
    def size_seconds(self) -> float:
        """獲取當前緩衝區的時長（秒）"""
        return len(self.buffer) / (self.sample_rate * 2)


class SessionAudioQueue:
    """
    單個 Session 的音訊佇列
    管理該 session 的所有音訊數據流
    """
    
    def __init__(self, session_id: str, max_queue_size: int = 100):
        """
        初始化 Session 音訊佇列
        
        Args:
            session_id: Session ID
            max_queue_size: 佇列最大長度
        """
        self.session_id = session_id
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.pre_buffer = AudioBuffer(max_size_seconds=5.0)  # 5秒 pre-recording
        self.recording_buffer = []  # 當前錄音緩衝
        self.is_recording = False
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
        
        # 如果正在錄音，也推送到錄音緩衝
        if self.is_recording:
            self.recording_buffer.append(audio_chunk)
        
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
    
    def start_recording(self, include_pre_buffer: bool = True, pre_buffer_seconds: float = 2.0):
        """
        開始錄音
        
        Args:
            include_pre_buffer: 是否包含 pre-buffer 數據
            pre_buffer_seconds: 要包含的 pre-buffer 秒數
        """
        self.is_recording = True
        self.recording_buffer = []
        
        # 如果需要，包含 pre-buffer 數據
        if include_pre_buffer:
            pre_data = self.pre_buffer.get_recent(pre_buffer_seconds)
            if pre_data:
                self.recording_buffer.append(pre_data)
                logger.debug(f"Included {len(pre_data)} bytes of pre-buffer for session {self.session_id}")
    
    def stop_recording(self) -> bytes:
        """
        停止錄音並返回錄音數據
        
        Returns:
            完整的錄音數據
        """
        self.is_recording = False
        recording_data = b''.join(self.recording_buffer)
        self.recording_buffer = []
        
        logger.info(f"Stopped recording for session {self.session_id}, captured {len(recording_data)} bytes")
        return recording_data
    
    def get_stats(self) -> Dict:
        """獲取統計資訊"""
        return {
            "session_id": self.session_id,
            "total_chunks": self.total_chunks,
            "total_bytes": self.total_bytes,
            "queue_size": self.queue.qsize(),
            "pre_buffer_seconds": self.pre_buffer.size_seconds(),
            "is_recording": self.is_recording,
            "recording_buffer_size": sum(len(chunk) for chunk in self.recording_buffer),
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
        self.recording_buffer = []
        
        logger.debug(f"Cleaned up audio queue for session {self.session_id}")


class AudioQueueManager:
    """
    音訊佇列管理器
    管理所有 session 的音訊數據流
    """
    
    def __init__(self, max_sessions: int = 1000):
        """
        初始化音訊佇列管理器
        
        Args:
            max_sessions: 最大 session 數量
        """
        self.max_sessions = max_sessions
        self.queues: Dict[str, SessionAudioQueue] = {}
        
        logger.info(f"AudioQueueManager initialized with max_sessions={max_sessions}")
    
    async def create_queue(self, session_id: str) -> SessionAudioQueue:
        """
        為 session 創建音訊佇列
        
        Args:
            session_id: Session ID
            
        Returns:
            SessionAudioQueue 實例
        """
        if session_id in self.queues:
            logger.warning(f"Audio queue already exists for session {session_id}")
            return self.queues[session_id]
        
        if len(self.queues) >= self.max_sessions:
            # 清理最舊的非活動佇列
            await self._cleanup_oldest_queue()
        
        queue = SessionAudioQueue(session_id)
        self.queues[session_id] = queue
        
        logger.debug(f"Created audio queue for session {session_id}")
        return queue
    
    async def destroy_queue(self, session_id: str):
        """
        銷毀 session 的音訊佇列
        
        Args:
            session_id: Session ID
        """
        if session_id not in self.queues:
            return
        
        queue = self.queues[session_id]
        await queue.cleanup()
        del self.queues[session_id]
        
        logger.debug(f"Destroyed audio queue for session {session_id}")
    
    async def push(self, session_id: str, audio_chunk: bytes, timestamp: Optional[float] = None):
        """
        推送音訊數據到指定 session
        
        Args:
            session_id: Session ID
            audio_chunk: 音訊數據
            timestamp: 時間戳記
        """
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}, creating one")
            await self.create_queue(session_id)
        
        queue = self.queues[session_id]
        await queue.push(audio_chunk, timestamp)
    
    async def pull(self, session_id: str, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        從指定 session 拉取音訊數據
        
        Args:
            session_id: Session ID
            timeout: 超時時間
            
        Returns:
            音訊數據
        """
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}")
            return None
        
        queue = self.queues[session_id]
        return await queue.pull(timeout)
    
    def start_recording(self, session_id: str, include_pre_buffer: bool = True, pre_buffer_seconds: float = 2.0):
        """
        開始錄音
        
        Args:
            session_id: Session ID
            include_pre_buffer: 是否包含 pre-buffer
            pre_buffer_seconds: pre-buffer 秒數
        """
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}")
            return
        
        queue = self.queues[session_id]
        queue.start_recording(include_pre_buffer, pre_buffer_seconds)
    
    def stop_recording(self, session_id: str) -> Optional[bytes]:
        """
        停止錄音
        
        Args:
            session_id: Session ID
            
        Returns:
            錄音數據
        """
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}")
            return None
        
        queue = self.queues[session_id]
        return queue.stop_recording()
    
    def get_queue(self, session_id: str) -> Optional[SessionAudioQueue]:
        """
        獲取指定 session 的佇列
        
        Args:
            session_id: Session ID
            
        Returns:
            SessionAudioQueue 實例
        """
        return self.queues.get(session_id)
    
    def get_all_stats(self) -> List[Dict]:
        """獲取所有佇列的統計資訊"""
        return [queue.get_stats() for queue in self.queues.values()]
    
    def get_session_stats(self, session_id: str) -> Optional[Dict]:
        """獲取指定 session 的統計資訊"""
        queue = self.queues.get(session_id)
        return queue.get_stats() if queue else None
    
    async def _cleanup_oldest_queue(self):
        """清理最舊的非活動佇列"""
        if not self.queues:
            return
        
        # 找出最舊的佇列
        oldest_session = min(
            self.queues.keys(),
            key=lambda sid: self.queues[sid].last_activity
        )
        
        logger.info(f"Cleaning up oldest queue: {oldest_session}")
        await self.destroy_queue(oldest_session)
    
    async def cleanup_all(self):
        """清理所有佇列"""
        session_ids = list(self.queues.keys())
        for session_id in session_ids:
            await self.destroy_queue(session_id)
        
        logger.info("Cleaned up all audio queues")


# 全域音訊佇列管理器實例
_audio_queue_manager: Optional[AudioQueueManager] = None


def get_audio_queue_manager() -> AudioQueueManager:
    """獲取全域音訊佇列管理器實例"""
    global _audio_queue_manager
    if _audio_queue_manager is None:
        _audio_queue_manager = AudioQueueManager()
    return _audio_queue_manager


def configure_audio_queue_manager(max_sessions: int = 1000) -> AudioQueueManager:
    """配置並獲取音訊佇列管理器"""
    global _audio_queue_manager
    _audio_queue_manager = AudioQueueManager(max_sessions=max_sessions)
    return _audio_queue_manager