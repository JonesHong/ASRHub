"""
音訊佇列管理器
管理所有 session 的音訊數據流

設計原則：
1. Session 管理 - 管理多個 session 的音訊佇列
2. 生命週期管理 - 創建、銷毀和清理佇列
3. 資源限制 - 限制最大 session 數量
4. 統計追踪 - 提供佇列統計資訊
"""

from typing import Dict, Optional, List
from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.core.audio_queue import SessionAudioQueue

config_manager = ConfigManager()
audio_queue_manager = config_manager.audio_queue_manager


class AudioQueueManager:
    """
    音訊佇列管理器
    管理所有 session 的音訊數據流
    """

    _instance = None  # 單例實例

    def __new__(cls, *args, **kwargs):
        """
        創建或返回單例實例。
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化音訊佇列管理器

        Args:
            max_sessions: 最大 session 數量
        """
        self.max_sessions = audio_queue_manager.max_sessions
        self.queues: Dict[str, SessionAudioQueue] = {}

        logger.info(
            f"AudioQueueManager initialized with max_sessions={self.max_sessions}, instance_id={id(self)}"
        )

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

    async def push(
        self,
        session_id: str,
        audio_chunk: bytes,
        timestamp: Optional[float] = None,
        batch_mode: bool = False,
    ):
        """
        推送音訊數據到指定 session

        Args:
            session_id: Session ID
            audio_chunk: 音訊數據
            timestamp: 時間戳記
            batch_mode: 是否為批次模式（用於文件上傳）
        """

        if session_id not in self.queues:
            logger.warning(
                f"No audio queue for session {session_id}, creating one with batch_mode={batch_mode}"
            )
            await self.create_queue(session_id, batch_mode=batch_mode)

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

    def start_recording(
        self, session_id: str, include_pre_buffer: bool = True, pre_buffer_seconds: float = 2.0
    ):
        """
        [DEPRECATED] 開始錄音 - 請使用 RecordingOperator.start_recording

        Args:
            session_id: Session ID
            include_pre_buffer: 是否包含 pre-buffer
            pre_buffer_seconds: pre-buffer 秒數
        """
        logger.warning(
            f"AudioQueueManager.start_recording is deprecated. "
            f"Please use RecordingOperator.start_recording for session {session_id}"
        )
        # 暫時保留空實現，避免破壞現有調用

    def stop_recording(self, session_id: str) -> Optional[bytes]:
        """
        [DEPRECATED] 停止錄音 - 請使用 RecordingOperator.stop_recording

        Args:
            session_id: Session ID

        Returns:
            錄音數據
        """
        logger.warning(
            f"AudioQueueManager.stop_recording is deprecated. "
            f"Please use RecordingOperator.stop_recording for session {session_id}"
        )
        # 暫時返回空數據，避免破壞現有調用
        return b''

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
        result = queue.get_all_audio()
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

    def get_pre_buffer_data(self, session_id: str, seconds: float = 2.0) -> Optional[bytes]:
        """
        獲取 pre-buffer 數據

        Args:
            session_id: Session ID
            seconds: 要獲取的秒數

        Returns:
            pre-buffer 音訊數據
        """
        if session_id not in self.queues:
            logger.warning(f"No audio queue for session {session_id}")
            return None
        
        queue = self.queues[session_id]
        return queue.get_pre_buffer_data(seconds)

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
        oldest_session = min(self.queues.keys(), key=lambda sid: self.queues[sid].last_activity)

        logger.info(f"Cleaning up oldest queue: {oldest_session}")
        await self.destroy_queue(oldest_session)

    async def cleanup_all(self):
        """清理所有佇列"""
        session_ids = list(self.queues.keys())
        for session_id in session_ids:
            await self.destroy_queue(session_id)

        logger.info("Cleaned up all audio queues")
