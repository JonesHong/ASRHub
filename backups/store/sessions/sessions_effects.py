"""
Sessions 域的 Effects 實現（重構版）

這是純事件驅動架構的核心，管理所有 session 相關的副作用。
通過組合多個專門的 handler 模組來實現功能分離。
"""

import asyncio
from typing import Dict, Optional, Any
from pystorex import create_effect, ofType
from reactivex import operators as ops

from src.utils.logger import logger
from src.utils.rxpy_async import async_flat_map
from src.core.audio_queue_manager import AudioQueueManager

# 導入新的 handler 模組
from .handlers import (
    BaseEffectHandler,
    EffectSubscriptionManager,
    OperatorManagementHandler,
    TranscriptionHandler,
    SessionTimerHandler,
    AudioProcessingHandler,
)

from .sessions_actions import (
    create_session,
    destroy_session,
    wake_triggered,
    start_recording,
    start_asr_streaming,
    end_asr_streaming,
    fsm_reset,
    session_error,
    transcription_done,
    begin_transcription,
    end_recording,
    audio_chunk_received,
    speech_detected,
    silence_started,
    audio_metadata,
    upload_file,
    upload_file_done,
    chunk_upload_start,
    chunk_upload_done,
)
from .sessions_state import FSMStrategy, FSMStateEnum


audio_queue_manager = AudioQueueManager()
# 模組級變數 - Provider Manager (為了向後相容)
provider_manager = None



class SessionEffects(BaseEffectHandler):
    """Session 相關的 Effects（重構版）

    通過組合多個專門的 handler 來管理所有 session 的副作用：
    1. OperatorManagementHandler - Operator 生命週期管理
    2. TranscriptionHandler - 轉譯處理
    3. AudioProcessingHandler - 音訊數據處理
    4. SessionTimerHandler - 計時器效果
    """

    def __init__(self, store=None):
        """初始化 SessionEffects

        Args:
            store: PyStoreX store 實例
            audio_queue_manager: 音訊隊列管理器
        """
        super().__init__(store, audio_queue_manager)


        # 初始化各個 handler
        self.transcription_handler = TranscriptionHandler(store)
        self.audio_handler = AudioProcessingHandler(store)
        self.timer_handler = SessionTimerHandler(store)


    # ============================================================================
    # FSM 狀態轉換 Effects
    # ============================================================================

    @create_effect
    def fsm_transition_effect(self, action_stream):
        """FSM 狀態轉換 Effect

        根據 FSM 狀態變化調整 operators 的行為。
        """
        return action_stream.pipe(
            ofType(
                wake_triggered,
                start_recording,
                end_recording,
                start_asr_streaming,
                end_asr_streaming,
                fsm_reset,
            ),
            async_flat_map(self._handle_fsm_transition),
        )

    async def _handle_fsm_transition(self, action):
        """處理 FSM 狀態轉換"""
        if not hasattr(action, "payload") or not action.payload:
            logger.error(f"Invalid action structure in _handle_fsm_transition: {type(action)}")
            return []

        session_id = action.payload.get("session_id")
        if not session_id:
            logger.error("Missing session_id in FSM transition action")
            return []

        # 記錄狀態轉換
        logger.debug(
            f"FSM transition for session {self.format_session_id(session_id)}: {action.type}"
        )

        # 特殊處理某些轉換
        if action.type == fsm_reset.type:
            # 重置時清理音訊緩衝區
            await self.audio_handler.clear_audio_buffer(session_id)

        return []

    # ============================================================================
    # 音訊處理 Effects
    # ============================================================================

    @create_effect
    def audio_processing_effect(self, action_stream):
        """音訊處理 Effect

        處理音訊數據流，包括格式轉換、VAD、喚醒詞檢測等。
        """

        return action_stream.pipe(
            ofType(audio_chunk_received),
            async_flat_map(self.audio_handler.process_audio_through_operators),
        )

    @create_effect
    def audio_metadata_effect(self, action_stream):
        """音訊元資料 Effect

        處理前端發送的音訊元資料。
        """
        return action_stream.pipe(
            ofType(audio_metadata),
            async_flat_map(self.audio_handler.handle_audio_metadata)
        )

    # ============================================================================
    # 轉譯處理 Effects
    # ============================================================================

    @create_effect
    def transcription_processing_effect(self, action_stream):
        """轉譯處理 Effect

        處理 ASR 轉譯請求。
        """
        return action_stream.pipe(
            ofType(begin_transcription),
            async_flat_map(self.transcription_handler.handle_transcription)
        )

    # ============================================================================
    # 檔案上傳 Effects
    # ============================================================================

    @create_effect
    def upload_file_effect(self, action_stream):
        """檔案上傳 Effect"""
        return action_stream.pipe(
            ofType(upload_file),
            async_flat_map(self._handle_upload_file),
        )

    async def _handle_upload_file(self, action):
        """處理檔案上傳"""
        session_id = action.payload.get("session_id")
        file_path = action.payload.get("file_path")

        logger.info(
            f"📁 Handling file upload for session {self.format_session_id(session_id)}: {file_path}"
        )

        # 實際的檔案處理邏輯可以在這裡實現
        # 目前僅記錄日誌

        return []

    @create_effect
    def upload_file_done_effect(self, action_stream):
        """檔案上傳完成 Effect"""
        return action_stream.pipe(
            ofType(upload_file_done),
            async_flat_map(self._handle_upload_file_done),
        )

    async def _handle_upload_file_done(self, action):
        """處理檔案上傳完成"""
        session_id = action.payload.get("session_id")
        audio_data = action.payload.get("audio_data")

        if audio_data:
            # 處理音訊轉譯
            await self.transcription_handler.process_audio_transcription(
                session_id, audio_data, "file_upload"
            )

        return []

    @create_effect
    def chunk_upload_start_effect(self, action_stream):
        """分塊上傳開始 Effect"""
        return action_stream.pipe(
            ofType(chunk_upload_start),
            async_flat_map(self._handle_chunk_upload_start),
        )

    async def _handle_chunk_upload_start(self, action):
        """處理分塊上傳開始"""
        session_id = action.payload.get("session_id")
        logger.info(f"📦 Chunk upload started for session {self.format_session_id(session_id)}")
        return []

    @create_effect
    def chunk_upload_done_effect(self, action_stream):
        """分塊上傳完成 Effect"""
        return action_stream.pipe(
            ofType(chunk_upload_done),
            async_flat_map(self._handle_chunk_upload_done),
        )

    async def _handle_chunk_upload_done(self, action):
        """處理分塊上傳完成"""
        session_id = action.payload.get("session_id")
        audio_data = action.payload.get("audio_data")

        if audio_data:
            # 處理音訊轉譯
            await self.transcription_handler.process_audio_transcription(
                session_id, audio_data, "chunk_upload"
            )

        return []

    # ============================================================================
    # 計時器 Effects（委派給 timer_handler）
    # ============================================================================

    def session_timeout(self, action_stream):
        """會話超時 Effect"""
        return self.timer_handler.session_timeout(action_stream)

    def recording_timeout(self, action_stream):
        """錄音超時 Effect"""
        return self.timer_handler.recording_timeout(action_stream)

    # ============================================================================
    # 清理和資源管理
    # ============================================================================

    def cleanup(self):
        """清理所有資源"""
        logger.info("Cleaning up SessionEffects...")


        # 清理各個 handler
        if hasattr(self.timer_handler, "cleanup"):
            self.timer_handler.cleanup()

        logger.info("SessionEffects cleanup completed")
