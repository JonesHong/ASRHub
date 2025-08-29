"""
轉譯處理模組

管理 ASR 轉譯請求、音訊格式處理和結果處理
"""

from typing import Dict, Optional, Any, Set
from src.utils.logger import logger
from .base import BaseEffectHandler
import asyncio


class TranscriptionHandler(BaseEffectHandler):
    """轉譯處理 Handler
    
    負責處理所有轉譯相關的操作
    """
    
    def __init__(self, store=None, audio_queue_manager=None):
        """初始化
        
        Args:
            store: PyStoreX store 實例
            audio_queue_manager: 音訊隊列管理器
        """
        super().__init__(store, audio_queue_manager)
        
        # 去重機制：追蹤正在處理的轉譯
        self._transcription_processing: Set[str] = set()
    
    async def handle_transcription(self, action) -> list:
        """處理轉譯請求
        
        Args:
            action: 轉譯 action
            
        Returns:
            後續 actions 列表
        """
        session_id = action.payload.get("session_id")
        
        # 去重機制 - 檢查是否已經在處理這個 session 的轉譯
        if session_id in self._transcription_processing:
            logger.warning(
                f"⚠️ Transcription already in progress for session {self.format_session_id(session_id)}, "
                "skipping duplicate request"
            )
            return []
        
        # 標記為正在處理
        self._transcription_processing.add(session_id)
        
        try:
            # 執行轉譯
            result = await self._execute_transcription(session_id)
            
            if result:
                # 發送轉譯完成 action
                from src.store.sessions.sessions_actions import transcription_done
                self.dispatch_action(transcription_done(session_id, result))
                
                logger.info(f"✅ Transcription completed for session {self.format_session_id(session_id)}")
            
            return []
            
        except Exception as e:
            logger.error(f"Transcription error for session {self.format_session_id(session_id)}: {e}")
            
            # 發送錯誤 action
            from src.store.sessions.sessions_actions import session_error
            self.dispatch_action(session_error(session_id, str(e)))
            
            return []
            
        finally:
            # 移除處理標記
            self._transcription_processing.discard(session_id)
    
    async def _execute_transcription(self, session_id: str) -> Optional[str]:
        """執行轉譯
        
        Args:
            session_id: Session ID
            
        Returns:
            轉譯結果文字，失敗返回 None
        """
        # 獲取 Whisper provider
        if 'whisper' not in self.provider_factories:
            logger.error("Whisper provider not available")
            return None
        
        # 創建 Whisper provider 實例
        whisper = self.provider_factories['whisper']()
        
        # 初始化 provider
        await whisper.initialize()
        
        # 獲取音訊數據
        audio_data = await self._get_audio_for_transcription(session_id)
        
        if not audio_data:
            logger.warning(f"No audio data available for session {self.format_session_id(session_id)}")
            return None
        
        # 處理音訊格式
        processed_audio = await self._process_audio_format(session_id, audio_data)
        
        if not processed_audio:
            return None
        
        # 執行轉譯
        try:
            logger.info(f"📝 Starting transcription for session {self.format_session_id(session_id)}")
            result = await whisper.transcribe(processed_audio)
            
            if result and hasattr(result, 'text'):
                logger.info(f"✅ Transcription result: {result.text}")
                return result.text
            else:
                logger.warning(f"Unexpected transcription result format: {result}")
                return str(result) if result else None
                
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
    
    async def _get_audio_for_transcription(self, session_id: str) -> Optional[bytes]:
        """獲取用於轉譯的音訊數據
        
        Args:
            session_id: Session ID
            
        Returns:
            音訊數據，如果沒有則返回 None
        """
        if not self.audio_queue_manager:
            logger.error("Audio queue manager not available")
            return None
        
        # 獲取 session 資訊
        session = self.get_session_state(session_id)
        if not session:
            logger.error(f"Session {self.format_session_id(session_id)} not found")
            return None
        
        # 根據策略選擇正確的方法
        from src.store.sessions.sessions_state import FSMStrategy
        strategy = session.get('strategy')
        
        logger.info(f"Session {self.format_session_id(session_id)} strategy: {strategy}")
        
        # Check if it's a BATCH strategy
        is_batch = (
            strategy == FSMStrategy.BATCH or 
            strategy == 'batch' or
            (hasattr(strategy, 'value') and strategy.value == 'batch')
        )
        
        if is_batch:
            logger.info(f"Using get_all_audio for BATCH strategy session {self.format_session_id(session_id)}")
            return self.audio_queue_manager.get_all_audio(session_id)
        else:
            # 優先嘗試從 RecordingOperator 獲取數據
            logger.info(f"Trying to get recording data from RecordingOperator for session {self.format_session_id(session_id)}")
            
            # 嘗試從 operator_factories 獲取 RecordingOperator
            if 'recording' in self.operator_factories:
                try:
                    recording_operator = self.operator_factories['recording']()
                    audio_data = await recording_operator.get_recording_data(session_id, stop_if_recording=True)
                    if audio_data:
                        logger.info(f"Got recording data from RecordingOperator: {len(audio_data)} bytes")
                        return audio_data
                except Exception as e:
                    logger.warning(f"Failed to get recording data from RecordingOperator: {e}")
            
            # 降級到舊方法（deprecated）
            logger.warning(f"Falling back to deprecated AudioQueueManager.stop_recording for session {self.format_session_id(session_id)}")
            return self.audio_queue_manager.stop_recording(session_id)
    
    async def _process_audio_format(self, session_id: str, audio_data: bytes) -> Optional[bytes]:
        """處理音訊格式
        
        Args:
            session_id: Session ID
            audio_data: 原始音訊數據
            
        Returns:
            處理後的音訊數據，失敗返回 None
        """
        from src.utils.audio_format_detector import detect_and_prepare_audio_for_whisper
        
        logger.info(f"🔍 開始音訊格式分析 - Session: {self.format_session_id(session_id)}")
        logger.info(f"📊 原始音訊大小: {len(audio_data)} bytes")
        
        # 獲取 session 的音訊元資料
        session = self.get_session_state(session_id)
        stored_metadata = self._get_audio_metadata(session)
        
        if not stored_metadata:
            error_msg = "❌ 未提供音訊元資料，無法處理音訊。請確保客戶端傳送 audio_metadata"
            logger.error(error_msg)
            self.dispatch_error(session_id, error_msg)
            return None
        
        # 映射前端 camelCase 欄位到後端 snake_case
        mapped_metadata = self._map_audio_metadata(stored_metadata)
        
        # 檢查必要欄位
        if not mapped_metadata.get('format') or not mapped_metadata.get('sample_rate'):
            error_msg = (
                f"❌ 缺少必要的音訊元資料: format={mapped_metadata.get('format')}, "
                f"sample_rate={mapped_metadata.get('sample_rate')}"
            )
            logger.error(error_msg)
            self.dispatch_error(session_id, error_msg)
            return None
        
        logger.info(f"📋 使用客戶端提供的音訊元資料:")
        logger.info(f"   格式: {mapped_metadata.get('format', 'unknown')}")
        logger.info(f"   取樣率: {mapped_metadata.get('sample_rate', 'unknown')} Hz")
        logger.info(f"   聲道數: {mapped_metadata.get('channels', 'unknown')}")
        
        # 使用元資料進行處理
        processed_audio, processing_info = detect_and_prepare_audio_for_whisper(
            audio_data, 
            metadata=mapped_metadata
        )
        
        # 記錄處理信息
        self._log_processing_info(processing_info, audio_data)
        
        # 為 Whisper 進行最終格式轉換
        if processing_info.get('needs_conversion') or processing_info.get('needs_final_conversion', True):
            final_audio = await self._convert_for_whisper(processed_audio, session_id)
            if final_audio:
                return final_audio
        
        return processed_audio
    
    async def _convert_for_whisper(self, audio_data: bytes, session_id: str) -> Optional[bytes]:
        """為 Whisper 進行最終格式轉換 (INT16 → FLOAT32)
        
        Args:
            audio_data: 音訊數據
            session_id: Session ID
            
        Returns:
            轉換後的音訊數據
        """
        if 'format_conversion' not in self.operator_factories:
            logger.warning("Format conversion operator not available")
            return audio_data
        
        logger.info(f"🔄 為 Whisper 進行最終格式轉換 - Session: {self.format_session_id(session_id)}")
        
        format_converter = self.operator_factories['format_conversion'](
            target_format="float32",
            sample_rate=16000,
            channels=1
        )
        
        try:
            final_audio = await format_converter.process(audio_data)
            if final_audio:
                logger.info(f"✅ Whisper 最終格式轉換成功 - 大小: {len(final_audio)} bytes")
                return final_audio
        except Exception as e:
            logger.error(f"❌ Whisper 最終格式轉換失敗: {e}")
        
        return audio_data
    
    def _get_audio_metadata(self, session: Optional[Dict]) -> Optional[Dict]:
        """獲取音訊元資料
        
        Args:
            session: Session 字典
            
        Returns:
            音訊元資料字典
        """
        if not session:
            return None
        
        # 檢查 audio_metadata 欄位
        metadata = session.get('audio_metadata')
        
        # 如果沒有，檢查 metadata.audio_metadata
        if not metadata and session.get('metadata'):
            metadata = session.get('metadata', {}).get('audio_metadata')
        
        return metadata
    
    def _map_audio_metadata(self, metadata: Dict) -> Dict:
        """映射前端 camelCase 欄位到後端 snake_case
        
        Args:
            metadata: 原始元資料
            
        Returns:
            映射後的元資料
        """
        return {
            'format': metadata.get('detectedFormat', metadata.get('format')),
            'sample_rate': metadata.get('sampleRate', metadata.get('sample_rate')),
            'channels': metadata.get('channels'),
            'mime_type': metadata.get('mimeType', metadata.get('mime_type')),
            'file_extension': metadata.get('fileExtension', metadata.get('file_extension')),
            'duration': metadata.get('duration'),
            'is_silent': metadata.get('isSilent', metadata.get('is_silent')),
            'is_low_volume': metadata.get('isLowVolume', metadata.get('is_low_volume'))
        }
    
    def _log_processing_info(self, processing_info: Dict, original_audio: bytes):
        """記錄音訊處理信息
        
        Args:
            processing_info: 處理信息字典
            original_audio: 原始音訊數據
        """
        format_info = processing_info.get('detected_format', {})
        logger.info(
            f"🎵 檢測結果: {format_info.get('format', 'unknown')} "
            f"({format_info.get('encoding', 'unknown')}) "
            f"- 信心度: {format_info.get('confidence', 0):.2f}"
        )
        
        if format_info.get('needs_decompression_attempt', False):
            logger.warning(
                f"🚨 格式檢測信心度低 ({format_info.get('confidence', 0):.2f})，"
                "強制嘗試解壓縮"
            )
        
        if processing_info.get('needs_conversion'):
            steps = processing_info.get('conversion_steps', [])
            logger.info(f"🔄 執行音訊轉換: {' → '.join(steps)}")
            logger.info(
                f"📈 處理結果: {len(original_audio)} → "
                f"{processing_info.get('final_size', 0)} bytes"
            )
        else:
            logger.info("✨ 音訊格式無需轉換，直接使用")
    
    async def process_audio_transcription(self, session_id: str, audio_data: bytes, source: str):
        """處理音訊轉譯（供外部調用）
        
        Args:
            session_id: Session ID
            audio_data: 音訊數據
            source: 音訊來源
        """
        logger.info(
            f"Processing audio transcription for session {self.format_session_id(session_id)} "
            f"from {source} ({len(audio_data)} bytes)"
        )
        
        # 將音訊數據添加到隊列
        if self.audio_queue_manager:
            self.audio_queue_manager.add_to_pre_buffer(session_id, audio_data)
        
        # 發送開始轉譯事件
        from src.store.sessions.sessions_actions import begin_transcription
        self.dispatch_action(begin_transcription(session_id))