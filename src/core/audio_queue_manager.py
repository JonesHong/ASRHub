"""音訊佇列管理器服務

ASRHub 的簡單音訊佇列管理實作。
使用記憶體內佇列。
遵循 KISS 原則 - 簡單、清楚、可維護。
"""

import collections
import threading
import time
from dataclasses import dataclass
from typing import Dict, Deque, List, Optional, Tuple
from threading import Lock, Event
import numpy as np

from src.interface.audio_queue import IAudioQueueManager
from src.interface.audio import AudioChunk
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.config.manager import ConfigManager


@dataclass
class TimestampedAudio:
    """帶時間戳的音頻片段"""
    timestamp: float  # Unix timestamp (高精度)
    audio: AudioChunk  # 音頻數據
    duration: float  # 這個 chunk 的持續時間（秒）


class AudioQueueManager(SingletonMixin, IAudioQueueManager):
    """基於 session 的簡單音訊佇列管理器。
    
    特性：
    - Thread-safe 佇列操作
    - 首次推入時自動建立佇列
    - 可選的最大佇列大小，自動移除最舊的片段
    - 使用 SingletonMixin 確保單例
    """
    
    def __init__(self, max_queue_size: Optional[int] = None):
        """初始化 AudioQueueManager。
        
        Args:
            max_queue_size: 每個佇列的最大片段數 (None = 從 config.yaml 載入)
        """
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 從 ConfigManager 載入設定
            config = ConfigManager()
            queue_config = config.services.audio_queue
            
            # 使用提供的值或從配置載入
            self._max_queue_size = max_queue_size or queue_config.max_queue_size
            self._ttl_seconds = queue_config.ttl_seconds
            self._cleanup_interval = queue_config.queue_cleanup_interval
            self._blocking_timeout = queue_config.blocking_timeout
            self._blocking_sleep_interval = queue_config.blocking_sleep_interval
            
            # 原有的佇列（保持向後相容）
            self._queues: Dict[str, Deque[AudioChunk]] = {}
            
            # 新增：帶時間戳的佇列
            self._timestamped_queues: Dict[str, Deque[TimestampedAudio]] = {}
            
            # 每個 reader 的當前讀取位置（時間戳）
            self._reader_positions: Dict[str, Dict[str, float]] = {}
            
            # 每個 session 的開始時間
            self._session_start_times: Dict[str, float] = {}
            
            self._locks: Dict[str, threading.Lock] = {}
            
            # 等待新數據的事件
            self._new_data_events: Dict[str, Event] = {}
            
            # Global lock for queue registry operations
            self._registry_lock = threading.Lock()
            
            # 配置參數
            self._max_history_duration = 30.0  # 最多保留 30 秒歷史
            self._chunk_duration = 0.1  # 假設每個 chunk 是 100ms
            
            logger.debug(f"音訊佇列管理器已初始化 - 支援時間戳記 "
                        f"(最大容量={self._max_queue_size}, 歷史記錄={self._max_history_duration}秒)")
    
    def _create_queue(self, session_id: str) -> None:
        """為 session 建立新佇列 (必須在 registry lock 內呼叫)。"""
        self._queues[session_id] = collections.deque(maxlen=self._max_queue_size)
        self._timestamped_queues[session_id] = collections.deque()
        self._reader_positions[session_id] = {}
        self._session_start_times[session_id] = time.time()
        self._locks[session_id] = threading.Lock()
        self._new_data_events[session_id] = Event()
    
    def _ensure_queue(self, session_id: str) -> None:
        """確保 session 的佇列存在。"""
        with self._registry_lock:
            if session_id not in self._queues:
                self._create_queue(session_id)
                logger.debug(f"Created queue for session: {session_id}")

    def push(self, session_id: str, chunk: AudioChunk) -> float:
        """推入音訊片段到 session 佇列並返回時間戳。
        
        Returns:
            時間戳，失敗返回 -1
        """
        try:
            if not chunk:
                logger.warning(f"Empty chunk for session {session_id}")
                return -1
                
            current_time = time.time()
            self._ensure_queue(session_id)
            
            with self._locks[session_id]:
                # 原有佇列（向後相容）
                queue = self._queues[session_id]
                if self._max_queue_size and len(queue) >= self._max_queue_size:
                    logger.warning(
                        f"Queue full for session {session_id}, dropping oldest chunk"
                    )
                    queue.popleft()
                queue.append(chunk)
                
                # 新增：時間戳佇列
                timestamped = TimestampedAudio(
                    timestamp=current_time,
                    audio=chunk,
                    duration=self._chunk_duration
                )
                ts_queue = self._timestamped_queues[session_id]
                ts_queue.append(timestamped)
                
                # 清理過期數據
                self._cleanup_old_audio(session_id)
                
                # 通知等待的 readers
                self._new_data_events[session_id].set()
                
                queue_size = len(queue)
                logger.trace(f"Pushed chunk to {session_id} at {current_time:.3f} (size={queue_size})")
                return current_time
                
        except Exception as e:
            logger.error(f"Failed to push chunk: {e}", session_id=session_id)
            return -1
    
    def pull(self, session_id: str, count: int = 1) -> List[AudioChunk]:
        """從 session 佇列拉取音訊片段。
        
        Returns:
            音訊片段列表（可能為空）
        """
        try:
            # 確保佇列存在
            self._ensure_queue(session_id)
            
            if session_id not in self._queues:
                logger.debug(f"No queue for session {session_id}")
                return []
            
            if count <= 0:
                logger.warning(f"Invalid count {count} for session {session_id}")
                return []
            
            chunks: List[AudioChunk] = []
            with self._locks[session_id]:
                queue = self._queues[session_id]
                actual_count = min(count, len(queue))
                
                for _ in range(actual_count):
                    chunks.append(queue.popleft())
                
                if chunks:
                    logger.trace(f"Pulled {len(chunks)} chunks from {session_id} (remaining={len(queue)})")
            
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to pull chunks: {e}", session_id=session_id)
            return []
    
    def clear(self, session_id: str) -> bool:
        """清除 session 佇列中的所有片段。
        
        Returns:
            是否成功清除
        """
        try:
            if session_id not in self._queues:
                logger.debug(f"No queue to clear for session {session_id}")
                return True  # 不存在也視為成功
            
            with self._locks[session_id]:
                size = len(self._queues[session_id])
                self._queues[session_id].clear()
                logger.debug(f"Cleared {size} chunks from {session_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}", session_id=session_id)
            return False
    
    def size(self, session_id: str) -> int:
        """取得 session 佇列的當前大小。"""
        if session_id not in self._queues:
            return 0
        
        with self._locks[session_id]:
            return len(self._queues[session_id])
    
    def exists(self, session_id: str) -> bool:
        """檢查 session 是否存在佇列。"""
        with self._registry_lock:
            return session_id in self._queues
    
    def remove(self, session_id: str) -> None:
        """移除整個 session 佇列。"""
        with self._registry_lock:
            if session_id in self._queues:
                # Lock queue before removal to prevent concurrent access
                with self._locks[session_id]:
                    size = len(self._queues[session_id])
                    del self._queues[session_id]
                    
                    # 清理時間戳相關資料
                    if session_id in self._timestamped_queues:
                        del self._timestamped_queues[session_id]
                    if session_id in self._reader_positions:
                        del self._reader_positions[session_id]
                    if session_id in self._session_start_times:
                        del self._session_start_times[session_id]
                    if session_id in self._new_data_events:
                        del self._new_data_events[session_id]
                
                del self._locks[session_id]
                logger.info(f"Removed queue for {session_id} (had {size} chunks)")
    
    def get_stats(self) -> Dict:
        """取得所有佇列的統計資訊。"""
        with self._registry_lock:
            total_chunks = sum(len(q) for q in self._queues.values())
            return {
                'total_queues': len(self._queues),
                'total_chunks': total_chunks,
                'max_queue_size': self._max_queue_size,
                'queue_sizes': {
                    sid: len(q) for sid, q in self._queues.items()
                }
            }
    
    def pop_blocking(self, session_id: str, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """阻塞式取出單一音訊片段。
        
        Args:
            session_id: Session ID
            timeout: 超時時間（秒），None 使用配置預設值
            
        Returns:
            AudioChunk 或 None（超時或無資料）
        """
        import time
        
        try:
            if not session_id:
                logger.warning("Empty session_id for pop_blocking")
                return None
            
            # 使用配置的預設值或提供的值
            actual_timeout = timeout if timeout is not None else self._blocking_timeout
            
            if actual_timeout <= 0:
                logger.warning(f"Invalid timeout {actual_timeout}")
                return None
            
            start_time = time.time()
            
            while time.time() - start_time < actual_timeout:
                chunks = self.pull(session_id, count=1)
                if chunks:
                    return chunks[0]
                time.sleep(self._blocking_sleep_interval)  # 避免 busy waiting
            
            # 正常超時，不記錄錯誤
            return None
            
        except Exception as e:
            logger.error(f"Failed in pop_blocking: {e}", session_id=session_id)
            return None
    
    def register_reader(self, session_id: str, reader_id: str, start_timestamp: Optional[float] = None) -> None:
        """註冊一個新的讀者。
        
        Args:
            session_id: 會話 ID
            reader_id: 讀者 ID (例如: "wake_word", "vad", "recording")
            start_timestamp: 可選的起始時間戳，如果提供則從此時間開始讀取
        """
        self._ensure_queue(session_id)
        
        with self._locks[session_id]:
            if session_id not in self._reader_positions:
                self._reader_positions[session_id] = {}
            
            if start_timestamp is not None:
                # 使用提供的起始時間戳
                start_time = start_timestamp
                logger.debug(f"Reader '{reader_id}' registered for session '{session_id}' starting from specified timestamp {start_time:.3f}")
            elif session_id in self._timestamped_queues and len(self._timestamped_queues[session_id]) > 0:
                # 從佇列中第一個音訊的時間戳開始
                start_time = self._timestamped_queues[session_id][0].timestamp
                logger.debug(f"Reader '{reader_id}' registered for session '{session_id}' starting from earliest audio at {start_time:.3f}")
            else:
                # 佇列為空，從當前時間開始（稍微提前一點以確保不會錯過即將到來的音訊）
                start_time = time.time() - 0.1  # 提前 100ms
                logger.debug(f"Reader '{reader_id}' registered for session '{session_id}' at current time {start_time:.3f}")
            
            self._reader_positions[session_id][reader_id] = start_time
    
    def pull_from_timestamp(
        self, 
        session_id: str, 
        reader_id: str, 
        from_timestamp: Optional[float] = None,
        max_chunks: Optional[int] = None
    ) -> List[TimestampedAudio]:
        """從指定時間戳開始拉取音頻（非破壞性）。
        
        Args:
            session_id: 會話 ID
            reader_id: 讀者 ID
            from_timestamp: 開始時間戳，None 表示從上次讀取位置繼續
            max_chunks: 最多返回的 chunk 數量
            
        Returns:
            List[TimestampedAudio]: 音頻片段列表
        """
        if session_id not in self._timestamped_queues:
            return []
        
        with self._locks[session_id]:
            queue = self._timestamped_queues[session_id]
            
            # 確定起始時間戳
            if from_timestamp is None:
                # 使用上次讀取位置
                if reader_id in self._reader_positions.get(session_id, {}):
                    from_timestamp = self._reader_positions[session_id][reader_id]
                else:
                    # 新 reader 從當前時間開始
                    from_timestamp = time.time()
                    if session_id not in self._reader_positions:
                        self._reader_positions[session_id] = {}
                    self._reader_positions[session_id][reader_id] = from_timestamp
            
            # 收集符合條件的音頻
            result = []
            last_timestamp = from_timestamp
            
            for idx, item in enumerate(queue):
                if item.timestamp > from_timestamp:  # 使用 > 避免重複讀取
                    result.append(TimestampedAudio(
                        timestamp=item.timestamp,
                        audio=item.audio,  # AudioChunk 本身就是不可變的
                        duration=item.duration
                    ))
                    last_timestamp = item.timestamp
                    
                    if max_chunks and len(result) >= max_chunks:
                        break
            
            # 更新讀取位置為最後讀取的項目時間戳
            # 如果沒有讀取到新數據，保持原位置
            if result:
                if session_id not in self._reader_positions:
                    self._reader_positions[session_id] = {}
                self._reader_positions[session_id][reader_id] = last_timestamp
            
            return result
    
    def pull_blocking_timestamp(
        self,
        session_id: str,
        reader_id: str,
        from_timestamp: Optional[float] = None,
        timeout: float = 0.1
    ) -> Optional[TimestampedAudio]:
        """阻塞式拉取下一個音頻片段。
        
        Args:
            session_id: 會話 ID
            reader_id: 讀者 ID
            from_timestamp: 開始時間戳
            timeout: 等待超時（秒）
            
        Returns:
            Optional[TimestampedAudio]: 音頻片段或 None（超時）
        """
        if session_id not in self._new_data_events:
            return None
        
        event = self._new_data_events[session_id]
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # 嘗試拉取數據
            chunks = self.pull_from_timestamp(
                session_id, reader_id, from_timestamp, max_chunks=1
            )
            
            if chunks:
                return chunks[0]
            
            # 等待新數據
            event.wait(timeout=0.01)
            event.clear()
        
        return None
    
    def get_audio_between_timestamps(
        self,
        session_id: str,
        start_timestamp: float,
        end_timestamp: Optional[float] = None
    ) -> List[TimestampedAudio]:
        """獲取兩個時間戳之間的所有音頻。
        
        Args:
            session_id: 會話 ID
            start_timestamp: 開始時間戳
            end_timestamp: 結束時間戳（None 表示到最新）
            
        Returns:
            List[TimestampedAudio]: 時間範圍內的音頻片段
        """
        if session_id not in self._timestamped_queues:
            return []
        
        with self._locks[session_id]:
            queue = self._timestamped_queues[session_id]
            result = []
            
            for item in queue:
                if item.timestamp >= start_timestamp:
                    if end_timestamp is None or item.timestamp <= end_timestamp:
                        result.append(TimestampedAudio(
                            timestamp=item.timestamp,
                            audio=item.audio,
                            duration=item.duration
                        ))
            
            return result
    
    def reset_reader_position(
        self,
        session_id: str,
        reader_id: str,
        timestamp: Optional[float] = None
    ):
        """重置讀者的讀取位置。
        
        Args:
            session_id: 會話 ID
            reader_id: 讀者 ID
            timestamp: 新的讀取位置（None 表示最新）
        """
        if session_id not in self._reader_positions:
            self._reader_positions[session_id] = {}
        
        if timestamp is None:
            timestamp = time.time()
        
        self._reader_positions[session_id][reader_id] = timestamp
        logger.debug(f"Reset reader '{reader_id}' position to {timestamp:.3f}")
    
    def _cleanup_old_audio(self, session_id: str):
        """清理過期的音頻數據。"""
        if session_id not in self._timestamped_queues:
            return
            
        queue = self._timestamped_queues[session_id]
        current_time = time.time()
        cutoff_time = current_time - self._max_history_duration
        
        # 移除過期數據
        while queue and queue[0].timestamp < cutoff_time:
            removed = queue.popleft()
            logger.trace(f"Cleaned old audio at {removed.timestamp:.3f}")


# 模組級單例實例 (從 config.yaml 載入設定)
audio_queue: AudioQueueManager = AudioQueueManager()