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
        # logger.info(f"AudioBuffer.push: chunk_size={len(audio_chunk)}, current_total={self.total_bytes}, max_size={self.max_size_bytes}, batch_mode={self.batch_mode}")
        
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
            
        self.recording_buffer = []  # 當前錄音緩衝
        self.wake_word_window = AudioBuffer(max_size_seconds=3.0)  # 3秒喚醒詞窗口
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
        # logger.info(f"SessionAudioQueue.push: session={self.session_id}, chunk_size={len(audio_chunk)}")
        self.last_activity = datetime.now()
        self.total_chunks += 1
        self.total_bytes += len(audio_chunk)
        
        # 總是推送到 pre-buffer（環形緩衝）
        self.pre_buffer.push(audio_chunk, timestamp)
        # logger.info(f"SessionAudioQueue.push: pushed to pre_buffer, new total_bytes={self.pre_buffer.total_bytes}")
        
        # 推送到喚醒詞窗口（環形緩衝）
        self.wake_word_window.push(audio_chunk, timestamp)
        
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
        
        logger.info(f"AudioQueueManager initialized with max_sessions={max_sessions}, instance_id={id(self)}")
    
    async def create_queue(self, session_id: str, batch_mode: bool = False) -> SessionAudioQueue:
        """
        為 session 創建音訊佇列
        
        Args:
            session_id: Session ID
            batch_mode: 是否為批次模式
            
        Returns:
            SessionAudioQueue 實例
        """
        if session_id in self.queues:
            logger.warning(f"Audio queue already exists for session {session_id}")
            return self.queues[session_id]
        
        if len(self.queues) >= self.max_sessions:
            # 清理最舊的非活動佇列
            await self._cleanup_oldest_queue()
        
        queue = SessionAudioQueue(session_id, batch_mode=batch_mode)
        self.queues[session_id] = queue
        
        logger.debug(f"Created audio queue for session {session_id} (batch_mode={batch_mode})")
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
    
    async def push(self, session_id: str, audio_chunk: bytes, timestamp: Optional[float] = None, batch_mode: bool = False):
        """
        推送音訊數據到指定 session
        
        Args:
            session_id: Session ID
            audio_chunk: 音訊數據
            timestamp: 時間戳記
            batch_mode: 是否為批次模式（用於文件上傳）
        """
        # logger.info(f"AudioQueueManager.push: session={session_id}, chunk_size={len(audio_chunk)}, batch_mode={batch_mode}")
        
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}, creating one with batch_mode={batch_mode}")
            await self.create_queue(session_id, batch_mode=batch_mode)
        
        # logger.info(f"AudioQueueManager.push: about to call queue.push for session={session_id}")
        queue = self.queues[session_id]
        await queue.push(audio_chunk, timestamp)
        # logger.info(f"AudioQueueManager.push: completed queue.push for session={session_id}")
    
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
    
    def get_all_audio(self, session_id: str) -> Optional[bytes]:
        """
        獲取所有推送的音訊數據（用於批次上傳模式）
        
        Args:
            session_id: Session ID
            
        Returns:
            所有音訊數據
        """
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}")
            return None
        
        queue = self.queues[session_id]
        # logger.info(f"AudioQueueManager.get_all_audio: session={session_id}, queue exists, calling queue.get_all_audio()")
        result = queue.get_all_audio()
        # logger.info(f"AudioQueueManager.get_all_audio: session={session_id}, result length={len(result) if result else 0}")
        return result
    
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
        # If no instance exists, create one with default settings
        # This should normally be configured via configure_audio_queue_manager()
        logger.warning("AudioQueueManager not configured, creating with default settings")
        _audio_queue_manager = AudioQueueManager()
    logger.debug(f"get_audio_queue_manager returning instance_id={id(_audio_queue_manager)}")
    return _audio_queue_manager


def configure_audio_queue_manager(max_sessions: int = 1000) -> AudioQueueManager:
    """配置並獲取音訊佇列管理器"""
    global _audio_queue_manager
    if _audio_queue_manager is None:
        _audio_queue_manager = AudioQueueManager(max_sessions=max_sessions)
        logger.debug(f"configure_audio_queue_manager created instance_id={id(_audio_queue_manager)}")
    else:
        logger.warning(f"AudioQueueManager already exists (instance_id={id(_audio_queue_manager)}), not creating new instance. Use existing instance.")
    return _audio_queue_manager