"""
ASR Hub 實時 Pipeline 編排器
協調喚醒詞檢測、VAD 和 ASR 的並行處理
"""

import asyncio
from typing import Optional, AsyncGenerator, Dict, Any
from datetime import datetime

from src.utils.logger import logger
from src.models.audio import AudioChunk
from src.store import get_global_store
from src.store.sessions import sessions_actions
from src.store.sessions.sessions_state import FSMStateEnum
from src.stream.buffer_manager import AudioBufferManager
from src.core.timer_service import TimerService
from src.pipeline.base import PipelineBase
from src.pipeline.operators.base import OperatorBase


class PipelineBranch:
    """Pipeline 分支，管理一組 Operators"""
    
    def __init__(self, operators: list[OperatorBase]):
        """
        初始化分支
        
        Args:
            operators: Operator 列表
        """
        self.operators = operators
    
    async def process(self, data: Any) -> Any:
        """
        處理數據通過所有 Operators
        
        Args:
            data: 輸入數據
            
        Returns:
            處理後的數據
        """
        result = data
        for operator in self.operators:
            result = await operator.process(result)
            if result is None:
                break
        return result


class RealtimePipeline(PipelineBase):
    """實時 Pipeline 編排器"""
    
    def __init__(self, 
                 session_id: str,
                 buffer_manager: AudioBufferManager,
                 timer_service: TimerService):
        """
        初始化實時 Pipeline
        
        Args:
            session_id: 會話 ID
            buffer_manager: 緩衝區管理器
            timer_service: 計時器服務
        """
        super().__init__()
        
        self.session_id = session_id
        self.store = get_global_store()
        self.buffer_manager = buffer_manager
        self.timer_service = timer_service
        
        # Pipeline 分支
        self.wake_word_branch: Optional[PipelineBranch] = None
        self.vad_branch: Optional[PipelineBranch] = None
        self.format_branch: Optional[PipelineBranch] = None
        
        # ASR 狀態
        self.asr_paused = False
        
        # VAD 狀態
        self.vad_speech_detected = False
        self.vad_silence_start: Optional[datetime] = None
        self.vad_silence_duration = 0.0
        
        # 統計資訊
        self.stats = {
            'chunks_processed': 0,
            'wake_words_detected': 0,
            'vad_triggers': 0,
            'recordings_completed': 0,
            'streams_completed': 0,
        }
        
        logger.info("實時 Pipeline 初始化完成")
    
    def _initialize_operators(self):
        """初始化 Pipeline 中的 Operators"""
        # 從配置初始化各個分支
        try:
            # 格式轉換分支
            from src.pipeline.operators.audio_format.scipy_operator import ScipyAudioFormatOperator
            self.format_branch = PipelineBranch([ScipyAudioFormatOperator()])
            
            # 喚醒詞檢測分支
            if self.config.operators.wakeword.enabled:
                try:
                    from src.pipeline.operators.wakeword.openwakeword import OpenWakeWordOperator
                    self.wake_word_branch = PipelineBranch([OpenWakeWordOperator()])
                    logger.info("喚醒詞檢測分支初始化成功")
                except ImportError as e:
                    logger.warning(f"無法初始化喚醒詞檢測：{e}")
            
            # VAD 分支
            if self.config.operators.vad.enabled:
                try:
                    from src.pipeline.operators.vad.silero_vad import SileroVADOperator
                    self.vad_branch = PipelineBranch([SileroVADOperator()])
                    logger.info("VAD 分支初始化成功")
                except ImportError as e:
                    logger.warning(f"無法初始化 VAD：{e}")
            
        except Exception as e:
            logger.error(f"初始化 Operators 失敗：{e}")
    
    def get_session_state(self) -> Optional[FSMStateEnum]:
        """獲取當前 session 的 FSM 狀態"""
        if not self.store or not self.session_id:
            return None
        
        state = self.store.state
        if hasattr(state, 'sessions') and state.sessions:
            sessions = state.sessions.get('sessions', {})
            session = sessions.get(self.session_id)
            if session:
                return session.get('fsm_state')
        return None
    
    async def process(self, audio_chunk: AudioChunk) -> Optional[Dict[str, Any]]:
        """
        處理音訊塊通過所有並行分支
        
        Args:
            audio_chunk: 音訊塊
            
        Returns:
            處理結果
        """
        self.stats['chunks_processed'] += 1
        
        # 將音訊加入緩衝區
        self.buffer_manager.add_chunk(audio_chunk)
        
        # 檢查當前 FSM 狀態
        current_state = self.get_session_state()
        
        # 半雙工模式：系統回應時暫停 ASR
        if current_state == FSMStateEnum.BUSY:
            self.asr_paused = True
            logger.debug("系統回應中，暫停 ASR 處理")
            return None
        else:
            self.asr_paused = False
        
        # 並行處理各個分支
        tasks = []
        
        # 格式轉換（總是執行）
        if self.format_branch:
            tasks.append(self._process_format(audio_chunk))
        
        # 喚醒詞檢測（IDLE 或 ACTIVATED 狀態）
        if self.wake_word_branch and current_state in [FSMStateEnum.IDLE, FSMStateEnum.ACTIVATED]:
            tasks.append(self._process_wake_word(audio_chunk))
        
        # VAD 處理（ACTIVATED、RECORDING、STREAMING 狀態）
        if self.vad_branch and current_state in [
            FSMStateEnum.ACTIVATED, FSMStateEnum.RECORDING, FSMStateEnum.STREAMING
        ]:
            tasks.append(self._process_vad(audio_chunk))
        
        # 執行並行任務
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 處理結果
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Pipeline 處理錯誤：{result}")
                elif result and isinstance(result, dict):
                    # 處理特定結果類型
                    if result.get('type') == 'wake_word':
                        await self._handle_wake_word_detection(result)
                    elif result.get('type') == 'vad':
                        await self._handle_vad_result(result)
        
        return {
            'chunk_id': audio_chunk.id,
            'processed': True,
            'state': current_state,
            'stats': self.stats.copy()
        }
    
    async def _process_format(self, audio_chunk: AudioChunk) -> Optional[Dict]:
        """格式轉換處理"""
        try:
            if self.format_branch:
                result = await self.format_branch.process(audio_chunk)
                return {'type': 'format', 'result': result}
        except Exception as e:
            logger.error(f"格式轉換錯誤：{e}")
        return None
    
    async def _process_wake_word(self, audio_chunk: AudioChunk) -> Optional[Dict]:
        """喚醒詞檢測處理"""
        try:
            if self.wake_word_branch:
                result = await self.wake_word_branch.process(audio_chunk)
                if result and result.get('detected'):
                    self.stats['wake_words_detected'] += 1
                    return {'type': 'wake_word', 'result': result}
        except Exception as e:
            logger.error(f"喚醒詞檢測錯誤：{e}")
        return None
    
    async def _process_vad(self, audio_chunk: AudioChunk) -> Optional[Dict]:
        """VAD 處理"""
        try:
            if self.vad_branch:
                result = await self.vad_branch.process(audio_chunk)
                if result:
                    return {'type': 'vad', 'result': result}
        except Exception as e:
            logger.error(f"VAD 處理錯誤：{e}")
        return None
    
    async def _handle_wake_word_detection(self, detection_result: Dict):
        """處理喚醒詞檢測結果"""
        wake_data = detection_result.get('result', {})
        
        if wake_data.get('detected'):
            logger.info(f"檢測到喚醒詞：{wake_data.get('model')}")
            
            # Dispatch wake_triggered action
            if self.store and self.session_id:
                self.store.dispatch(
                    sessions_actions.wake_triggered(
                        self.session_id,
                        confidence=wake_data.get('confidence', 0.5),
                        trigger="wake_word"
                    )
                )
            
            # 啟動喚醒視窗計時器
            if self.timer_service:
                await self.timer_service.start_awake_timer()
    
    async def _handle_vad_result(self, vad_result: Dict):
        """處理 VAD 結果"""
        vad_data = vad_result.get('result', {})
        
        if vad_data.get('speech_detected'):
            # 檢測到語音
            if not self.vad_speech_detected:
                self.vad_speech_detected = True
                self.vad_silence_start = None
                self.vad_silence_duration = 0.0
                self.stats['vad_triggers'] += 1
                
                logger.debug("VAD 檢測到語音開始")
                
                # Dispatch speech_detected action
                if self.store and self.session_id:
                    self.store.dispatch(
                        sessions_actions.speech_detected(
                            self.session_id,
                            confidence=vad_data.get('confidence', 0.5)
                        )
                    )
                
                # 取消 VAD 計時器
                if self.timer_service:
                    await self.timer_service.on_speech_detected()
                
                # 根據 FSM 狀態決定動作
                current_state = self.get_session_state()
                if current_state == FSMStateEnum.ACTIVATED:
                    # 開始錄音或串流
                    if self.config.asr.streaming_mode:
                        await self._start_streaming()
                    else:
                        await self._start_recording()
        else:
            # 檢測到靜音
            if self.vad_speech_detected:
                if self.vad_silence_start is None:
                    self.vad_silence_start = datetime.now()
                    logger.debug("VAD 檢測到靜音開始")
                    
                    # Dispatch silence_detected action
                    if self.store and self.session_id:
                        self.store.dispatch(
                            sessions_actions.silence_detected(
                                self.session_id,
                                duration=1.8  # 預設靜音時長
                            )
                        )
                    
                    # 啟動 VAD 靜音計時器
                    if self.timer_service:
                        await self.timer_service.on_silence_detected()
                else:
                    # 計算靜音持續時間
                    self.vad_silence_duration = (
                        datetime.now() - self.vad_silence_start
                    ).total_seconds()
                    
                    # 檢查是否超過靜音閾值
                    silence_threshold = self.config.operators.vad.min_silence_duration
                    if self.vad_silence_duration >= silence_threshold:
                        logger.info(f"VAD 靜音超過閾值 {silence_threshold}s")
                        
                        # 結束錄音或串流
                        current_state = self.get_session_state()
                        if current_state == FSMStateEnum.RECORDING:
                            await self._end_recording("vad_timeout")
                        elif current_state == FSMStateEnum.STREAMING:
                            await self._end_streaming("vad_timeout")
                        
                        # 重置 VAD 狀態
                        self.vad_speech_detected = False
                        self.vad_silence_start = None
                        self.vad_silence_duration = 0.0
    
    async def _start_recording(self):
        """開始錄音"""
        if self.store and self.session_id:
            logger.info("開始錄音")
            self.store.dispatch(
                sessions_actions.start_recording(
                    self.session_id,
                    strategy="vad_controlled"
                )
            )
            
            # 啟動錄音計時器
            if self.timer_service:
                await self.timer_service.start_recording_timer()
    
    async def _start_streaming(self):
        """開始串流"""
        if self.store and self.session_id:
            logger.info("開始串流")
            self.store.dispatch(
                sessions_actions.start_streaming(self.session_id)
            )
            
            # 啟動串流計時器
            if self.timer_service:
                await self.timer_service.start_streaming_timer()
    
    async def _end_recording(self, trigger: str):
        """結束錄音"""
        if self.store and self.session_id:
            logger.info(f"結束錄音：{trigger}")
            self.stats['recordings_completed'] += 1
            
            # 獲取錄音數據
            recording_data = self.buffer_manager.get_recording_buffer()
            duration = len(recording_data) / self.buffer_manager.sample_rate
            
            self.store.dispatch(
                sessions_actions.end_recording(
                    self.session_id,
                    trigger=trigger,
                    duration=duration
                )
            )
            
            # 取消錄音計時器
            if self.timer_service:
                self.timer_service.cancel_timer('recording')
    
    async def _end_streaming(self, trigger: str):
        """結束串流"""
        if self.store and self.session_id:
            logger.info(f"結束串流：{trigger}")
            self.stats['streams_completed'] += 1
            
            self.store.dispatch(
                sessions_actions.end_streaming(self.session_id)
            )
            
            # 取消串流計時器
            if self.timer_service:
                self.timer_service.cancel_timer('streaming')
    
    async def process_stream(
        self, 
        audio_stream: AsyncGenerator[AudioChunk, None]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        處理音訊流
        
        Args:
            audio_stream: 音訊流
            
        Yields:
            處理結果
        """
        async for audio_chunk in audio_stream:
            result = await self.process(audio_chunk)
            if result:
                yield result
    
    async def stop(self):
        """停止 Pipeline"""
        logger.info("停止實時 Pipeline")
        
        # 取消所有計時器
        if self.timer_service:
            self.timer_service.cancel_all_timers()
        
        # 清理緩衝區
        if self.buffer_manager:
            self.buffer_manager.clear_all_buffers()
        
        await super().stop()
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取統計資訊"""
        return {
            **self.stats,
            'buffer_stats': self.buffer_manager.get_stats() if self.buffer_manager else {},
            'current_state': self.get_session_state()
        }