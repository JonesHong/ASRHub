"""
音訊處理效果模組

處理音訊數據流、格式轉換、VAD、喚醒詞檢測等
"""

from typing import Dict, Optional, Any, List
from src.utils.logger import logger
from .base import BaseEffectHandler
from src.store.sessions.sessions_state import FSMStateEnum
from src.store.sessions.sessions_actions import (
    wake_triggered, speech_detected, silence_started, session_error
)
from src.audio.converter import AudioConverter
from src.audio.models import AudioContainerFormat, AudioMetadata


class AudioProcessingHandler(BaseEffectHandler):
    """音訊處理 Handler
    
    負責處理音訊數據流的所有操作
    """
    
    def __init__(self, store=None):
        """初始化
        
        Args:
            store: PyStoreX store 實例
        """
        super().__init__(store)
        
        # Session operators 存儲（引用 operator_handler 的存儲）
        self.session_operators = {}
        
        # 初始化音訊轉換器
        self.audio_converter = AudioConverter()
    
    def set_session_operators(self, operators: Dict):
        """設置 session operators 引用
        
        Args:
            operators: Session operators 字典
        """
        self.session_operators = operators
    
    async def process_audio_through_operators(self, action) -> List:
        """處理音訊通過運算子
        
        音訊處理流程：
        1. 格式轉換 - 統一音訊格式 (PCM, 16kHz, mono)
        2. WakeWord 檢測 - 在 LISTENING 狀態檢測喚醒詞
        3. VAD 處理 - 在 RECORDING 狀態檢測語音/靜音
        4. AudioQueue - 儲存處理後的音訊數據
        
        注意：新架構中音訊數據直接推送到 AudioQueueManager
              
        Args:
            action: 音訊 action (來自 audio_chunk_received)
            
        Returns:
            後續 actions 列表
        """
        session_id = action.payload.get("session_id")
        audio_data = action.payload.get("audio_data")  # 從 server 來的原始數據
        content_type = action.payload.get("content_type", "")
        
        if not session_id:
            logger.warning(f"Missing session_id in audio_chunk_received payload")
            return []
        
        if audio_data is None:
            logger.warning(f"No audio data in audio_chunk_received payload")
            return []
        
        try:
            # 獲取當前 session 狀態
            session_state = self.get_session_state(session_id)
            if not session_state:
                logger.debug(f"Session {self.format_session_id(session_id)} not found or not initialized")
                return []
            
            current_fsm_state = session_state.get('fsm_state')
            logger.debug(f"Processing audio for session {self.format_session_id(session_id)} in state {current_fsm_state}")
            
            # 執行音訊處理管線
            processed_audio = await self._run_audio_pipeline(
                session_id, 
                audio_data, 
                current_fsm_state
            )
            
            # 存入 AudioQueue (總是執行)
            if self.audio_queue_manager and processed_audio:
                try:
                    await self.audio_queue_manager.push(session_id, processed_audio)
                    logger.debug(
                        f"Audio pushed to queue for session {self.format_session_id(session_id)}: "
                        f"{len(processed_audio)} bytes"
                    )
                except Exception as e:
                    logger.error(f"Failed to push audio to queue: {e}")
            
            return []
            
        except Exception as e:
            logger.error(f"Operator processing failed for session {self.format_session_id(session_id)}: {e}")
            self.dispatch_error(session_id, str(e))
            return []
    
    async def _run_audio_pipeline(
        self, 
        session_id: str, 
        audio_data: bytes, 
        fsm_state: FSMStateEnum
    ) -> Optional[bytes]:
        """執行音訊處理管線
        
        Args:
            session_id: Session ID
            audio_data: 原始音訊數據
            fsm_state: 當前 FSM 狀態
            
        Returns:
            處理後的音訊數據
        """
        # 1. 格式轉換 (總是執行)
        audio_data = await self._apply_format_conversion(session_id, audio_data)
        
        # 2. WakeWord 檢測 (只在 LISTENING 狀態)
        if fsm_state == FSMStateEnum.LISTENING:
            await self._apply_wakeword_detection(session_id, audio_data)
        
        # 3. VAD 處理 (只在 RECORDING 狀態)
        elif fsm_state == FSMStateEnum.RECORDING or fsm_state == FSMStateEnum.STREAMING:
            await self._apply_vad_processing(session_id, audio_data)
        
        return audio_data
    
    async def _apply_format_conversion(self, session_id: str, audio_data: bytes) -> bytes:
        """應用格式轉換 - 使用 AudioConverter
        
        將任意格式的音訊轉換為 PCM 16kHz mono
        
        Args:
            session_id: Session ID
            audio_data: 原始音訊數據
            
        Returns:
            轉換後的音訊數據 (PCM格式)
        """
        try:
            # 檢測輸入格式
            input_format = self.audio_converter.detect_format(audio_data)
            
            # 如果已經是 PCM 格式，檢查是否需要重採樣
            if input_format == AudioContainerFormat.RAW:
                # 假設已經是正確的格式
                return audio_data
            
            # 設定目標格式：PCM 16kHz mono
            target_metadata = AudioMetadata(
                sample_rate=16000,
                channels=1,
                container_format=AudioContainerFormat.RAW
            )
            
            # 執行轉換
            converted_chunk = self.audio_converter.convert(
                data=audio_data,
                to_format=AudioContainerFormat.RAW,
                to_metadata=target_metadata,
                from_format=input_format
            )
            
            logger.debug(
                f"Audio converted for session {self.format_session_id(session_id)}: "
                f"{input_format} -> PCM (16kHz, mono)"
            )
            
            return converted_chunk.data
            
        except Exception as e:
            logger.error(f"Format conversion failed: {e}")
            # 返回原始數據，讓後續處理決定如何處理
            return audio_data
    
    async def _apply_wakeword_detection(self, session_id: str, audio_data: bytes):
        """應用喚醒詞檢測
        
        Args:
            session_id: Session ID
            audio_data: 音訊數據
        """
        if session_id in self.session_operators.get('wakeword', {}):
            try:
                wakeword = self.session_operators['wakeword'][session_id]
                if hasattr(wakeword, 'process'):
                    detection = await wakeword.process(audio_data)
                    if detection and hasattr(detection, 'confidence'):
                        if detection.confidence > 0.7:  # 閾值可配置
                            # Phase 3.2: 喚醒詞檢測日誌
                            logger.block("Wake Word Detected", [
                                f"🎆 WAKE WORD DETECTED!",
                                f"🔹 Session: {self.format_session_id(session_id)}...",
                                f"🎯 Confidence: {detection.confidence:.2f}",
                                f"🔊 Trigger: {getattr(detection, 'trigger', 'unknown')}"
                            ])
                            
                            self.dispatch_action(wake_triggered(
                                session_id, 
                                detection.confidence, 
                                getattr(detection, 'trigger', 'unknown')
                            ))
            except Exception as e:
                logger.error(f"WakeWord detection failed: {e}")
    
    async def _apply_vad_processing(self, session_id: str, audio_data: bytes):
        """應用 VAD 處理
        
        Args:
            session_id: Session ID
            audio_data: 音訊數據
        """
        if session_id in self.session_operators.get('vad', {}):
            try:
                vad = self.session_operators['vad'][session_id]
                if hasattr(vad, 'process'):
                    vad_result = await vad.process(audio_data)
                    if vad_result:
                        if getattr(vad_result, 'is_speech', False):
                            logger.debug(f"Speech detected for session {self.format_session_id(session_id)}")
                            self.dispatch_action(speech_detected(
                                session_id, 
                                getattr(vad_result, 'confidence', 0.5)
                            ))
                        else:
                            silence_duration = getattr(vad_result, 'silence_duration', 0)
                            if silence_duration > 0:
                                logger.debug(
                                    f"Silence detected for session {self.format_session_id(session_id)}: "
                                    f"{silence_duration}s"
                                )
                                self.dispatch_action(silence_started(
                                    session_id, 
                                    silence_duration
                                ))
            except Exception as e:
                logger.error(f"VAD processing failed: {e}")
    
    async def handle_audio_metadata(self, action) -> List:
        """處理音訊元資料
        
        Args:
            action: 音訊元資料 action
            
        Returns:
            後續 actions 列表
        """
        session_id = action.payload.get("session_id")
        audio_metadata = action.payload.get("audio_metadata")
        
        if not session_id or not audio_metadata:
            logger.warning("Missing session_id or audio_metadata in payload")
            return []
        
        logger.info(
            f"📋 Received audio metadata for session {self.format_session_id(session_id)}: "
            f"{audio_metadata}"
        )
        
        # 這裡可以根據元資料調整處理策略
        # 例如：根據音訊格式動態配置格式轉換器
        
        return []
    
    async def clear_audio_buffer(self, session_id: str):
        """清除音訊緩衝區
        
        Args:
            session_id: Session ID
        """
        if self.audio_queue_manager:
            try:
                self.audio_queue_manager.clear_buffer(session_id)
                logger.info(f"🗑️ Audio buffer cleared for session {self.format_session_id(session_id)}")
            except Exception as e:
                logger.error(f"Failed to clear audio buffer: {e}")