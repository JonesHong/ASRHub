"""
WebSocket 音訊串流管理器
處理音訊串流的接收、緩衝和分發
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from collections import defaultdict
import time
from dataclasses import dataclass

from src.utils.logger import logger
from src.models.audio import AudioChunk
from src.core.exceptions import StreamError


@dataclass
class AudioStreamBuffer:
    """音訊串流緩衝區"""
    session_id: str
    buffer: bytearray
    chunk_count: int = 0
    last_chunk_time: float = 0
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm"
    encoding: str = "linear16"
    bits_per_sample: int = 16
    
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
        

class WebSocketStreamManager:
    """
    WebSocket 音訊串流管理器
    管理多個 session 的音訊串流
    """
    
    def __init__(self, max_buffer_size: int = 1024 * 1024 * 10):  # 10MB
        """
        初始化串流管理器
        
        Args:
            max_buffer_size: 最大緩衝區大小（字節）
        """
        self.logger = logger
        self.max_buffer_size = max_buffer_size
        self.stream_buffers: Dict[str, AudioStreamBuffer] = {}
        self.stream_queues: Dict[str, asyncio.Queue] = {}
        self.active_streams: Dict[str, bool] = {}
        
    def create_stream(self, session_id: str, audio_params: Optional[Dict[str, Any]] = None) -> bool:
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
            
            # 檢查 audio_params 是否為 None
            if audio_params is None:
                raise ValueError("音訊參數不能為空")
                
            # 建立緩衝區
            # 處理 format 和 encoding 可能是枚舉或字符串的情況
            format_value = audio_params.get("format", "pcm")
            if hasattr(format_value, 'value'):
                format_value = format_value.value
                
            encoding_value = audio_params.get("encoding", "linear16")
            if hasattr(encoding_value, 'value'):
                encoding_value = encoding_value.value
                
            self.stream_buffers[session_id] = AudioStreamBuffer(
                session_id=session_id,
                buffer=bytearray(),
                sample_rate=audio_params.get("sample_rate", 16000),
                channels=audio_params.get("channels", 1),
                format=format_value,
                encoding=encoding_value,
                bits_per_sample=audio_params.get("bits_per_sample", 16)
            )
            
            # 建立串流佇列
            self.stream_queues[session_id] = asyncio.Queue()
            self.active_streams[session_id] = True
            
            self.logger.info(f"Created audio stream for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating stream: {e}")
            return False
            
    def add_audio_chunk(self, session_id: str, audio_data: bytes) -> bool:
        """
        添加音訊資料到串流
        
        Args:
            session_id: Session ID
            audio_data: 音訊資料
            
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
            
            # 創建 AudioChunk 物件
            from src.models.audio import AudioFormat, AudioEncoding
            
            # 轉換字符串為枚舉
            try:
                format_enum = AudioFormat(buffer.format)
            except ValueError:
                format_enum = AudioFormat.PCM
                
            try:
                encoding_enum = AudioEncoding(buffer.encoding)
            except ValueError:
                encoding_enum = AudioEncoding.LINEAR16
            
            audio_chunk = AudioChunk(
                data=audio_data,
                sample_rate=buffer.sample_rate,
                channels=buffer.channels,
                format=format_enum,
                encoding=encoding_enum,
                bits_per_sample=buffer.bits_per_sample,
                timestamp=time.time()
            )
            
            # 放入佇列
            if session_id in self.stream_queues:
                queue = self.stream_queues[session_id]
                if not queue.full():
                    queue.put_nowait(audio_chunk)
                else:
                    self.logger.warning(f"Queue full for session {session_id}, dropping chunk")
                    
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
        
        while True:
            try:
                # 等待音訊資料，超時 1 秒
                audio_chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                # 檢查是否為結束標記
                if audio_chunk is None:
                    self.logger.info(f"Received end marker for session {session_id}")
                    break
                    
                yield audio_chunk
                
            except asyncio.TimeoutError:
                # 檢查串流是否仍然活躍
                if not self.active_streams.get(session_id, False):
                    self.logger.info(f"Stream inactive for session {session_id}, ending")
                    break
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
            # 在佇列中放入結束標記
            if session_id in self.stream_queues:
                self.stream_queues[session_id].put_nowait(None)
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
            
        self.logger.info(f"Cleaned up stream for session {session_id}")
        
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
        
        # 導入枚舉類型
        from src.models.audio import AudioFormat, AudioEncoding
        
        # 確保 format 和 encoding 是枚舉類型
        format_enum = buffer.format
        if isinstance(format_enum, str):
            format_enum = AudioFormat(format_enum)
            
        encoding_enum = buffer.encoding
        if isinstance(encoding_enum, str):
            encoding_enum = AudioEncoding(encoding_enum)
        
        return {
            "session_id": session_id,
            "buffer_size": buffer.get_buffer_size(),
            "chunk_count": buffer.chunk_count,
            "last_chunk_time": buffer.last_chunk_time,
            "queue_size": queue.qsize() if queue else 0,
            "is_active": self.active_streams.get(session_id, False),
            "audio_params": {
                "sample_rate": buffer.sample_rate,
                "channels": buffer.channels,
                "format": format_enum,
                "encoding": encoding_enum,
                "bits_per_sample": buffer.bits_per_sample
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
            self.logger.warning(f"Backpressure triggered for session {session_id}: {usage_ratio:.2%}")
            return True
            
        return False