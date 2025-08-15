"""
ASR Hub 實時 Pipeline 編排器
協調喚醒詞檢測、VAD 和 ASR 的並行處理
"""

import asyncio
from typing import Optional, AsyncGenerator, Dict, Any
from datetime import datetime

from src.utils.logger import logger
from src.models.audio import AudioChunk
from src.core.fsm import (
    FSMController, FSMState, FSMEvent, 
    FSMWakeTrigger, FSMEndTrigger
)
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
        self.logger = logger
    
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
                 fcm_controller: FSMController,
                 buffer_manager: AudioBufferManager,
                 timer_service: TimerService):
        """
        初始化實時 Pipeline
        
        Args:
            fcm_controller: FSM 控制器
            buffer_manager: 緩衝區管理器
            timer_service: 計時器服務
        """
        super().__init__()
        
        self.fcm = fcm_controller
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
        
        self.logger.info("實時 Pipeline 初始化完成")
    
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
                except ImportError as e:
                    self.logger.warning(f"無法載入喚醒詞檢測模組：{e}")
                    self.wake_word_branch = None
            
            # VAD 分支
            if self.config.operators.vad.enabled:
                try:
                    from src.pipeline.operators.vad.silero_vad import SileroVADOperator
                    self.vad_branch = PipelineBranch([SileroVADOperator()])
                except ImportError as e:
                    self.logger.warning(f"無法載入 VAD 模組：{e}")
                    self.vad_branch = None
            
            self.logger.info("Pipeline 分支初始化完成")
            
        except Exception as e:
            self.logger.error(f"初始化 Operators 失敗：{e}")
            raise
    
    async def process_stream(self, 
                           audio_stream: AsyncGenerator[bytes, None],
                           **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """
        處理音訊流
        
        Args:
            audio_stream: 音訊流生成器
            **kwargs: 額外參數
            
        Yields:
            處理結果字典
        """
        self.logger.info("開始處理實時音訊流")
        
        async for audio_data in audio_stream:
            try:
                # 創建 AudioChunk - 需要提供所有必要參數
                from src.models.audio import AudioFormat, AudioEncoding
                
                chunk = AudioChunk(
                    data=audio_data,
                    sample_rate=kwargs.get('sample_rate', 16000),  # 預設 16kHz
                    channels=kwargs.get('channels', 1),  # 預設單聲道
                    format=kwargs.get('format', AudioFormat.PCM),
                    encoding=kwargs.get('encoding', AudioEncoding.LINEAR16),
                    bits_per_sample=kwargs.get('bits_per_sample', 16),
                    timestamp=datetime.now().timestamp(),
                    metadata=kwargs.get('metadata', {})
                )
                
                # 處理音訊塊
                result = await self.process_chunk(chunk, **kwargs)
                
                if result:
                    yield result
                    
            except Exception as e:
                self.logger.error(f"處理音訊流錯誤：{e}")
                yield {
                    'type': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
    
    async def process_chunk(self, chunk: AudioChunk, **kwargs) -> Optional[Dict[str, Any]]:
        """
        處理單個音訊塊
        
        Args:
            chunk: 音訊塊
            **kwargs: 額外參數
            
        Returns:
            處理結果字典
        """
        # 更新統計
        self.stats['chunks_processed'] += 1
        
        # 1. 格式檢查與轉換
        if self.format_branch:
            formatted_chunk = await self.format_branch.process(chunk)
            if formatted_chunk is None:
                return None
        else:
            formatted_chunk = chunk
        
        # 2. 加入緩衝區
        self.buffer_manager.add_chunk(formatted_chunk)
        
        # 3. 檢查是否需要暫停 ASR（半雙工）
        if self.buffer_manager.should_pause_for_reply():
            if not self.asr_paused:
                await self._pause_asr()
            return None
        elif self.asr_paused:
            await self._resume_asr()
        
        # 4. 根據狀態決定處理邏輯
        result = None
        
        if self.fcm.state == FSMState.LISTENING:
            result = await self._process_listening(formatted_chunk)
            
        elif self.fcm.state == FSMState.ACTIVATED:
            result = await self._process_activated(formatted_chunk)
            
        elif self.fcm.state in [FSMState.RECORDING, FSMState.STREAMING]:
            result = await self._process_active(formatted_chunk)
        
        return result
    
    async def _process_listening(self, chunk: AudioChunk) -> Optional[Dict[str, Any]]:
        """
        監聽狀態處理：檢測喚醒詞
        
        Args:
            chunk: 音訊塊
            
        Returns:
            處理結果
        """
        if not self.wake_word_branch:
            return None
        
        # 獲取喚醒詞檢測窗口
        wake_word_audio = self.buffer_manager.get_wake_word_buffer()
        
        if not wake_word_audio:
            return None
        
        # 檢測喚醒詞
        wake_word_result = await self.wake_word_branch.process(wake_word_audio)
        
        if wake_word_result and getattr(wake_word_result, 'detected', False):
            self.stats['wake_words_detected'] += 1
            
            # 觸發喚醒事件
            await self.fcm.handle_event(
                FSMEvent.WAKE_TRIGGERED,
                trigger=FSMWakeTrigger.WAKE_WORD,
                confidence=getattr(wake_word_result, 'confidence', 0.0),
                wake_word=getattr(wake_word_result, 'word', 'unknown')
            )
            
            # 啟動喚醒視窗計時器
            await self.timer_service.start_awake_timer()
            
            return {
                'type': 'wake_word_detected',
                'wake_word': getattr(wake_word_result, 'word', 'unknown'),
                'confidence': getattr(wake_word_result, 'confidence', 0.0),
                'timestamp': datetime.now().isoformat()
            }
        
        return None
    
    async def _process_activated(self, chunk: AudioChunk) -> Optional[Dict[str, Any]]:
        """
        喚醒視窗處理：檢測是否開始說話
        
        Args:
            chunk: 音訊塊
            
        Returns:
            處理結果
        """
        if not self.vad_branch:
            # 如果沒有 VAD，直接開始錄音/串流
            if self.fcm.strategy.__class__.__name__ == 'NonStreamingStrategy':
                await self.fcm.handle_event(FSMEvent.START_RECORDING)
                await self.timer_service.start_recording_timer()
            elif self.fcm.strategy.__class__.__name__ == 'StreamingStrategy':
                await self.fcm.handle_event(FSMEvent.START_ASR_STREAMING)
                await self.timer_service.start_streaming_timer()
            return None
        
        # VAD 檢測是否已經開始說話
        vad_result = await self.vad_branch.process(chunk)
        
        if vad_result and getattr(vad_result, 'speech_detected', False):
            if not self.vad_speech_detected:
                self.vad_speech_detected = True
                self.stats['vad_triggers'] += 1
                
                # 檢測到語音，開始錄音/串流
                if self.fcm.strategy.__class__.__name__ == 'NonStreamingStrategy':
                    await self.fcm.handle_event(FSMEvent.START_RECORDING)
                    await self.timer_service.start_recording_timer()
                    
                    return {
                        'type': 'recording_started',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                elif self.fcm.strategy.__class__.__name__ == 'StreamingStrategy':
                    await self.fcm.handle_event(FSMEvent.START_ASR_STREAMING)
                    await self.timer_service.start_streaming_timer()
                    
                    return {
                        'type': 'streaming_started',
                        'timestamp': datetime.now().isoformat()
                    }
        
        return None
    
    async def _process_active(self, chunk: AudioChunk) -> Optional[Dict[str, Any]]:
        """
        活躍狀態處理：VAD 檢測結束
        
        Args:
            chunk: 音訊塊
            
        Returns:
            處理結果
        """
        if not self.vad_branch:
            return None
        
        # VAD 檢測
        vad_result = await self.vad_branch.process(chunk)
        
        if vad_result:
            speech_detected = getattr(vad_result, 'speech_detected', False)
            
            if not speech_detected:
                # 檢測到靜音
                if self.vad_silence_start is None:
                    self.vad_silence_start = datetime.now()
                
                # 計算靜音時長
                self.vad_silence_duration = (datetime.now() - self.vad_silence_start).total_seconds()
                
                # 檢查是否超過閾值
                threshold = self.config.operators.vad.silero.min_silence_duration
                
                if self.vad_silence_duration >= threshold:
                    # 結束錄音/串流
                    if self.fcm.state == FSMState.RECORDING:
                        self.stats['recordings_completed'] += 1
                        
                        await self.fcm.handle_event(
                            FSMEvent.END_RECORDING,
                            trigger=FSMEndTrigger.VAD_TIMEOUT,
                            silence_duration=self.vad_silence_duration
                        )
                        
                        # 取消錄音計時器
                        self.timer_service.cancel_timer('recording')
                        
                        return {
                            'type': 'recording_stopped',
                            'trigger': 'vad_timeout',
                            'silence_duration': self.vad_silence_duration,
                            'timestamp': datetime.now().isoformat()
                        }
                        
                    elif self.fcm.state == FSMState.STREAMING:
                        self.stats['streams_completed'] += 1
                        
                        await self.fcm.handle_event(
                            FSMEvent.END_ASR_STREAMING,
                            trigger=FSMEndTrigger.VAD_TIMEOUT,
                            silence_duration=self.vad_silence_duration
                        )
                        
                        # 取消串流計時器
                        self.timer_service.cancel_timer('streaming')
                        
                        return {
                            'type': 'streaming_stopped',
                            'trigger': 'vad_timeout',
                            'silence_duration': self.vad_silence_duration,
                            'timestamp': datetime.now().isoformat()
                        }
            else:
                # 檢測到語音，重置靜音計時
                self.vad_silence_start = None
                self.vad_silence_duration = 0.0
                self.vad_speech_detected = True
        
        return None
    
    async def _pause_asr(self):
        """暫停 ASR 處理（半雙工）"""
        self.asr_paused = True
        self.logger.info("ASR 處理已暫停（系統回覆中）")
        
        # 發送暫停事件
        if self.fcm.event_dispatcher:
            await self.fcm.event_dispatcher.dispatch('asr_paused', {
                'timestamp': datetime.now().isoformat()
            })
    
    async def _resume_asr(self):
        """恢復 ASR 處理"""
        self.asr_paused = False
        self.logger.info("ASR 處理已恢復")
        
        # 重置 VAD 狀態
        self.vad_speech_detected = False
        self.vad_silence_start = None
        self.vad_silence_duration = 0.0
        
        # 發送恢復事件
        if self.fcm.event_dispatcher:
            await self.fcm.event_dispatcher.dispatch('asr_resumed', {
                'timestamp': datetime.now().isoformat()
            })
    
    def get_stats(self) -> Dict[str, Any]:
        """
        獲取統計資訊
        
        Returns:
            統計資訊字典
        """
        return {
            **self.stats,
            'asr_paused': self.asr_paused,
            'vad_speech_detected': self.vad_speech_detected,
            'vad_silence_duration': self.vad_silence_duration,
            'buffer_info': self.buffer_manager.get_buffer_info(),
            'timer_info': self.timer_service.get_timer_info(),
            'fcm_state': self.fcm.get_state_info()
        }
    
    async def reset(self):
        """重置 Pipeline 狀態"""
        self.asr_paused = False
        self.vad_speech_detected = False
        self.vad_silence_start = None
        self.vad_silence_duration = 0.0
        
        # 重置緩衝區
        self.buffer_manager.reset()
        
        # 取消所有計時器
        self.timer_service.cancel_all_timers()
        
        # 重置統計
        self.stats = {
            'chunks_processed': 0,
            'wake_words_detected': 0,
            'vad_triggers': 0,
            'recordings_completed': 0,
            'streams_completed': 0,
        }
        
        self.logger.info("實時 Pipeline 已重置")