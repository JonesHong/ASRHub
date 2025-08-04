"""
Socket.io 音訊串流管理器
處理音訊串流的接收、緩衝和分發
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
import time
from dataclasses import dataclass

from src.utils.logger import logger
from src.models.audio import AudioChunk
from src.core.exceptions import StreamError


@dataclass
class SocketIOAudioBuffer:
    """Socket.io 音訊緩衝區"""
    session_id: str
    buffer: bytearray
    chunk_count: int = 0
    last_chunk_time: float = 0
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm"
    encoding: str = "signed-integer"
    bits: int = 16
    
    def add_chunk(self, data: bytes):
        """添加音訊 chunk"""
        self.buffer.extend(data)
        self.chunk_count += 1
        self.last_chunk_time = time.time()
        
    def get_buffer_size(self) -> int:
        """獲取緩衝區大小"""
        return len(self.buffer)
        
    def clear(self):
        """清空緩衝區"""
        self.buffer.clear()
        self.chunk_count = 0
        

class SocketIOStreamManager:
    """
    Socket.io 音訊串流管理器
    管理多個 session 的音訊串流，支援分塊傳輸和序號管理
    """
    
    def __init__(self, max_buffer_size: int = 1024 * 1024 * 10):  # 10MB
        """
        初始化串流管理器
        
        Args:
            max_buffer_size: 最大緩衝區大小（字節）
        """
        self.logger = logger
        self.max_buffer_size = max_buffer_size
        self.stream_buffers: Dict[str, SocketIOAudioBuffer] = {}
        self.stream_queues: Dict[str, asyncio.Queue] = {}
        self.active_streams: Dict[str, bool] = {}
        self.chunk_sequences: Dict[str, int] = {}  # 追蹤 chunk 序號
        
    def create_stream(self, session_id: str, audio_params: Dict[str, Any]) -> bool:
        """
        建立新的音訊串流
        
        Args:
            session_id: Session ID
            audio_params: 音訊參數
            
        Returns:
            是否成功建立
        """
        try:
            if session_id in self.stream_buffers:
                self.logger.warning(f"Stream already exists for session {session_id}")
                return False
                
            # 建立緩衝區
            self.stream_buffers[session_id] = SocketIOAudioBuffer(
                session_id=session_id,
                buffer=bytearray(),
                sample_rate=audio_params.get("sample_rate", 16000),
                channels=audio_params.get("channels", 1),
                format=audio_params.get("format", "pcm"),
                encoding=audio_params.get("encoding", "signed-integer"),
                bits=audio_params.get("bits", 16)
            )
            
            # 建立串流佇列
            self.stream_queues[session_id] = asyncio.Queue(maxsize=100)
            self.active_streams[session_id] = True
            self.chunk_sequences[session_id] = 0
            
            self.logger.info(f"Created audio stream for session {session_id} with params: {audio_params}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating stream: {e}")
            return False
            
    def add_audio_chunk(self, session_id: str, audio_data: bytes, 
                       chunk_id: Optional[int] = None) -> bool:
        """
        添加音訊資料到串流
        
        Args:
            session_id: Session ID
            audio_data: 音訊資料
            chunk_id: Chunk 序號（可選）
            
        Returns:
            是否成功添加
        """
        try:
            if session_id not in self.stream_buffers:
                self.logger.error(f"No stream found for session {session_id}")
                return False
                
            buffer = self.stream_buffers[session_id]
            
            # 檢查緩衝區大小
            if buffer.get_buffer_size() + len(audio_data) > self.max_buffer_size:
                raise StreamError(f"Buffer overflow for session {session_id}")
                
            # 添加到緩衝區
            buffer.add_chunk(audio_data)
            
            # 更新序號
            if chunk_id is not None:
                expected_id = self.chunk_sequences[session_id]
                if chunk_id != expected_id:
                    self.logger.warning(
                        f"Chunk sequence mismatch for session {session_id}: "
                        f"expected {expected_id}, got {chunk_id}"
                    )
                self.chunk_sequences[session_id] = chunk_id + 1
            
            # 創建 AudioChunk 物件
            audio_chunk = AudioChunk(
                data=audio_data,
                sample_rate=buffer.sample_rate,
                channels=buffer.channels,
                format=buffer.format,
                timestamp=time.time()
            )
            
            # 放入佇列
            if session_id in self.stream_queues:
                queue = self.stream_queues[session_id]
                if not queue.full():
                    queue.put_nowait(audio_chunk)
                else:
                    self.logger.warning(f"Queue full for session {session_id}, dropping chunk")
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding audio chunk: {e}")
            return False
            
    async def get_audio_stream(self, session_id: str) -> AsyncGenerator[AudioChunk, None]:
        """
        獲取音訊串流
        
        Args:
            session_id: Session ID
            
        Yields:
            AudioChunk 物件
        """
        if session_id not in self.stream_queues:
            raise StreamError(f"No stream found for session {session_id}")
            
        queue = self.stream_queues[session_id]
        
        while self.active_streams.get(session_id, False):
            try:
                # 等待音訊資料，超時 1 秒
                audio_chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield audio_chunk
            except asyncio.TimeoutError:
                # 超時繼續等待
                continue
            except Exception as e:
                self.logger.error(f"Error in audio stream: {e}")
                break
                
    def stop_stream(self, session_id: str):
        """
        停止音訊串流
        
        Args:
            session_id: Session ID
        """
        if session_id in self.active_streams:
            self.active_streams[session_id] = False
            self.logger.info(f"Stopped stream for session {session_id}")
            
    def cleanup_stream(self, session_id: str):
        """
        清理串流資源
        
        Args:
            session_id: Session ID
        """
        # 停止串流
        self.stop_stream(session_id)
        
        # 清理緩衝區
        if session_id in self.stream_buffers:
            del self.stream_buffers[session_id]
            
        # 清理佇列
        if session_id in self.stream_queues:
            del self.stream_queues[session_id]
            
        # 清理狀態
        if session_id in self.active_streams:
            del self.active_streams[session_id]
            
        # 清理序號
        if session_id in self.chunk_sequences:
            del self.chunk_sequences[session_id]
            
        self.logger.info(f"Cleaned up stream for session {session_id}")
        
    def is_stream_active(self, session_id: str) -> bool:
        """
        檢查串流是否活躍
        
        Args:
            session_id: Session ID
            
        Returns:
            是否活躍
        """
        return self.active_streams.get(session_id, False)
        
    def get_stream_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取串流統計資訊
        
        Args:
            session_id: Session ID
            
        Returns:
            統計資訊
        """
        if session_id not in self.stream_buffers:
            return None
            
        buffer = self.stream_buffers[session_id]
        queue = self.stream_queues.get(session_id)
        
        return {
            "session_id": session_id,
            "buffer_size": buffer.get_buffer_size(),
            "chunk_count": buffer.chunk_count,
            "last_chunk_time": buffer.last_chunk_time,
            "queue_size": queue.qsize() if queue else 0,
            "is_active": self.is_stream_active(session_id),
            "current_sequence": self.chunk_sequences.get(session_id, 0),
            "audio_params": {
                "sample_rate": buffer.sample_rate,
                "channels": buffer.channels,
                "format": buffer.format,
                "encoding": buffer.encoding,
                "bits": buffer.bits
            }
        }
        
    def implement_backpressure(self, session_id: str, threshold: float = 0.8) -> bool:
        """
        實作背壓控制
        
        Args:
            session_id: Session ID
            threshold: 緩衝區使用率閾值（0-1）
            
        Returns:
            是否需要背壓控制
        """
        if session_id not in self.stream_buffers:
            return False
            
        buffer = self.stream_buffers[session_id]
        usage_ratio = buffer.get_buffer_size() / self.max_buffer_size
        
        if usage_ratio > threshold:
            self.logger.warning(
                f"Backpressure triggered for session {session_id}: "
                f"{usage_ratio:.2%} buffer usage"
            )
            return True
            
        # 也檢查佇列
        if session_id in self.stream_queues:
            queue = self.stream_queues[session_id]
            if queue.qsize() > queue.maxsize * threshold:
                self.logger.warning(
                    f"Backpressure triggered for session {session_id}: "
                    f"queue near capacity ({queue.qsize()}/{queue.maxsize})"
                )
                return True
                
        return False