"""
Recording Operator
音訊錄製和緩衝管理
"""

import io
import time
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
import wave
import numpy as np
from datetime import datetime

from src.operators.base import OperatorBase
from src.core.exceptions import PipelineError
from src.utils.logger import logger

# 模組級變數 - 直接導入和實例化
from src.config.manager import ConfigManager
from src.store import get_global_store
from src.core.audio_queue_manager import get_audio_queue_manager
from src.core.timer_manager import timer_manager

config_manager = ConfigManager()
store = get_global_store()
audio_queue_manager = get_audio_queue_manager()



class RecordingOperator(OperatorBase):
    """音訊錄製和緩衝管理"""
    
    def __init__(self):
        """
        初始化 Recording Operator
        使用模組級變數提供統一的依賴項
        """
        super().__init__()
        
        # 使用模組級全域實例（繼承自 OperatorBase）
        # self.config_manager, self.store, self.audio_queue_manager 已在基類中設定
        
        self.buffer = io.BytesIO()
        self.is_recording = False
        self.start_time = None
        
        # 嘗試從配置中獲取設定，使用 yaml2py 正確方式
        try:
            # 直接存取屬性，讓 yaml2py 處理預設值
            recording_config = self.config_manager.pipeline.operators.recording
            
            self.max_duration = recording_config.max_duration
            self.format = recording_config.format
            self.silence_countdown_duration = recording_config.silence_countdown
            self.vad_controlled = recording_config.vad_controlled
            
            # 音訊參數
            self.sample_rate = recording_config.sample_rate
            self.channels = recording_config.channels
            
            # 儲存設定
            self.storage_type = recording_config.storage.type
            self.storage_path = Path(recording_config.storage.path)
            
            # 分段錄音
            self.segment_duration = recording_config.segment_duration
            
            # VAD 控制設定
            self.pre_speech_buffer_duration = recording_config.vad_control.pre_speech_buffer
            self.post_speech_buffer_duration = recording_config.vad_control.post_speech_buffer
            
        except AttributeError:
            # 如果配置不存在，使用硬編碼預設值
            self.max_duration = 60  # 秒
            self.format = 'wav'
            self.silence_countdown_duration = 1.8  # 秒
            self.vad_controlled = False
            
            # 音訊參數
            self.sample_rate = 16000
            self.channels = 1
            
            # 儲存設定
            self.storage_type = 'memory'
            self.storage_path = Path('/tmp/recordings')
            
            # 分段錄音
            self.segment_duration = 0  # 0 表示不分段
            
            # VAD 控制設定
            self.pre_speech_buffer_duration = 0.3
            self.post_speech_buffer_duration = 0.2
        
        # 固定設定
        self.sample_width = 2  # 16-bit
        
        # VAD 控制相關狀態 (使用 TimerManager 取代本地計時器)
        # 移除本地計時器，改由 TimerManager 統一管理
        
        # 分段相關狀態
        self.current_segment = 0
        self.segments = []
        
        # 緩衝設定已在上面處理
        self.pre_speech_buffer = io.BytesIO()
        
        # 統計資訊
        self.total_bytes_recorded = 0
        self.recording_session_id = None
        
        # 回調函數
        self.recording_complete_callback = None
        self.segment_complete_callback = None
    
    async def _initialize(self):
        """初始化錄音資源"""
        logger.info("初始化 Recording Operator...")
        
        # 確保儲存目錄存在
        if self.storage_type == 'file':
            self.storage_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"錄音儲存路徑: {self.storage_path}")
        
        # 重置緩衝區
        self.buffer = io.BytesIO()
        self.pre_speech_buffer = io.BytesIO()
        
        logger.info("✓ Recording Operator 初始化完成")
    
    async def _cleanup(self):
        """清理資源"""
        logger.info("清理 Recording Operator 資源...")
        
        # 如果還在錄音，先停止
        if self.is_recording:
            await self.stop_recording()
        
        # 清空緩衝區
        self.buffer.close()
        self.pre_speech_buffer.close()
        
        # 取消倒數計時器
        if self.countdown_timer and not self.countdown_timer.done():
            self.countdown_timer.cancel()
        
        logger.info("✓ Recording Operator 資源清理完成")
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊資料
        
        Args:
            audio_data: 輸入音訊資料
            **kwargs: 額外參數
            
        Returns:
            audio_data: 透傳音訊資料
        """
        if not self.enabled or not self._initialized:
            return audio_data
        
        if not self.validate_audio_params(audio_data):
            return None
        
        # 獲取 session_id
        session_id = kwargs.get('session_id', self.recording_session_id)
        
        try:
            # 如果有 AudioQueueManager，音訊會自動進入佇列
            # 這裡我們只處理錄音邏輯
            
            # 如果正在錄音，將音訊加入緩衝區
            if self.is_recording:
                self.buffer.write(audio_data)
                self.total_bytes_recorded += len(audio_data)
                
                # 檢查是否超過最大時長
                if self.start_time:
                    duration = time.time() - self.start_time
                    if duration >= self.max_duration:
                        logger.warning(f"錄音已達最大時長 {self.max_duration}s，自動停止")
                        await self.stop_recording()
                
                # 檢查是否需要分段
                if self.segment_duration > 0 and duration >= self.segment_duration * (self.current_segment + 1):
                    await self._save_segment()
            
            else:
                # 如果啟用了預語音緩衝，保存最近的音訊
                if self.pre_speech_buffer_duration > 0:
                    self._update_pre_speech_buffer(audio_data)
            
            # 透傳音訊資料
            return audio_data
            
        except Exception as e:
            logger.error(f"錄音處理錯誤: {e}")
            raise PipelineError(f"錄音處理失敗: {e}")
    
    async def start_recording(self, session_id: str = None):
        """
        開始錄音
        
        Args:
            session_id: 錄音會話 ID
        """
        if self.is_recording:
            logger.warning("已經在錄音中")
            return
        
        logger.info(f"開始錄音 (session_id: {session_id})")
        
        # 重置狀態
        self.buffer = io.BytesIO()
        self.is_recording = True
        self.start_time = time.time()
        self.recording_session_id = session_id or f"recording_{int(time.time())}"
        self.total_bytes_recorded = 0
        self.current_segment = 0
        self.segments = []
        
        # 如果有 AudioQueueManager，獲取 pre-recording
        if self.audio_queue_manager and session_id:
            try:
                # 檢查佇列是否存在
                if session_id in self.audio_queue_manager.queues:
                    queue = self.audio_queue_manager.queues[session_id]
                    # 獲取 pre-recording（例如最後 0.5 秒）
                    pre_recording = queue.get_pre_recording(seconds=self.pre_speech_buffer_duration)
                    if pre_recording:
                        self.buffer.write(pre_recording)
                        self.total_bytes_recorded += len(pre_recording)
                        logger.debug(f"從 AudioQueueManager 獲取 pre-recording: {len(pre_recording)} bytes")
                    # 開始佇列錄音
                    await queue.start_recording()
            except Exception as e:
                logger.warning(f"無法從 AudioQueueManager 獲取 pre-recording: {e}")
        else:
            # 如果沒有 AudioQueueManager，使用本地預語音緩衝
            if self.pre_speech_buffer_duration > 0:
                pre_buffer_data = self.pre_speech_buffer.getvalue()
                if pre_buffer_data:
                    self.buffer.write(pre_buffer_data)
                    self.total_bytes_recorded += len(pre_buffer_data)
                    logger.debug(f"已加入本地預語音緩衝: {len(pre_buffer_data)} bytes")
        
        # 優先使用 Store dispatch，否則保持原有邏輯
        if self.store:
            from src.store.sessions.sessions_actions import recording_started
            self.store.dispatch(recording_started(
                session_id=self.recording_session_id,
                timestamp=self.start_time
            ))
    
    async def stop_recording(self, session_id: str = None) -> bytes:
        """
        停止錄音並返回音訊資料
        
        Args:
            session_id: 錄音會話 ID（用於驗證）
            
        Returns:
            錄製的音訊資料
        """
        if not self.is_recording:
            logger.warning("沒有正在進行的錄音")
            return b''
        
        # 驗證 session_id
        if session_id and session_id != self.recording_session_id:
            logger.warning(f"Session ID 不匹配: {session_id} != {self.recording_session_id}")
            return b''
        
        logger.info(f"停止錄音 (session_id: {self.recording_session_id})")
        
        # 停止錄音
        self.is_recording = False
        duration = time.time() - self.start_time if self.start_time else 0
        
        # 如果有 AudioQueueManager，停止佇列錄音
        if self.audio_queue_manager and self.recording_session_id:
            try:
                if self.recording_session_id in self.audio_queue_manager.queues:
                    queue = self.audio_queue_manager.queues[self.recording_session_id]
                    queue_recording = await queue.stop_recording()
                    if queue_recording:
                        # 合併佇列錄音與本地緩衝
                        logger.debug(f"從 AudioQueueManager 獲取錄音: {len(queue_recording)} bytes")
            except Exception as e:
                logger.warning(f"無法從 AudioQueueManager 停止錄音: {e}")
        
        # 獲取錄製的音訊
        audio_data = self.buffer.getvalue()
        
        # 儲存錄音
        if audio_data:
            file_path = await self._save_recording(audio_data)
            logger.info(f"錄音完成: 時長 {duration:.2f}s, 大小 {len(audio_data)} bytes")
            
            # 優先使用 Store dispatch
            if self.store:
                from src.store.sessions.sessions_actions import recording_stopped
                self.store.dispatch(recording_stopped(
                    session_id=self.recording_session_id,
                    duration=duration,
                    audio_data=audio_data,
                    reason="manual_stop"
                ))
            elif self.recording_complete_callback:
                # 保留回呼介面（向後相容）
                await self.recording_complete_callback({
                    'session_id': self.recording_session_id,
                    'duration': duration,
                    'size': len(audio_data),
                    'file_path': str(file_path) if file_path else None,
                    'segments': self.segments
                })
        
        # 重置狀態
        self.buffer = io.BytesIO()
        self.start_time = None
        self.recording_session_id = None
        
        # TimerManager 會自動管理計時器，不需要手動取消
        
        return audio_data
    
    async def pause_recording(self, session_id: str = None):
        """暫停錄音"""
        if not self.is_recording:
            logger.warning("沒有正在進行的錄音")
            return
        
        if session_id and session_id != self.recording_session_id:
            logger.warning(f"Session ID 不匹配")
            return
        
        logger.info("暫停錄音")
        self.is_recording = False
    
    async def resume_recording(self, session_id: str = None):
        """恢復錄音"""
        if self.is_recording:
            logger.warning("錄音已經在進行中")
            return
        
        if session_id and session_id != self.recording_session_id:
            logger.warning(f"Session ID 不匹配")
            return
        
        if not self.recording_session_id:
            logger.warning("沒有可恢復的錄音會話")
            return
        
        logger.info("恢復錄音")
        self.is_recording = True
    
    async def on_vad_result(self, vad_result: dict):
        """
        處理 VAD 結果並控制錄音
        
        Args:
            vad_result: VAD 結果字典
        """
        if not self.vad_controlled or not self.is_recording:
            return
        
        # 使用 TimerManager 管理的 timer
        timer = timer_manager.get_timer(self.recording_session_id)
        if not timer:
            logger.warning(f"No timer found for session: {self.recording_session_id}")
            return
        
        if vad_result.get('speech_detected', False):
            # 檢測到語音，通知 timer
            await timer.on_speech_detected()
            
            # 如果有 Store，dispatch 事件
            if self.store:
                from src.store.sessions.sessions_actions import countdown_cancelled
                self.store.dispatch(countdown_cancelled(
                    session_id=self.recording_session_id,
                    reason="speech_detected"
                ))
        else:
            # 檢測到靜音，通知 timer
            await timer.on_silence_detected()
            
            # 如果有 Store，dispatch 事件
            if self.store:
                from src.store.sessions.sessions_actions import countdown_started
                self.store.dispatch(countdown_started(
                    session_id=self.recording_session_id,
                    duration=self.silence_countdown_duration
                ))
    
    # 移除本地倒數計時方法，改由 TimerManager 統一管理
    # _start_countdown, _countdown_task, _cancel_countdown 已移至 TimerService
    
    def _update_pre_speech_buffer(self, audio_data: bytes):
        """更新預語音緩衝區"""
        # 計算緩衝區應保留的最大大小
        max_buffer_size = int(
            self.pre_speech_buffer_duration * 
            self.sample_rate * 
            self.channels * 
            self.sample_width
        )
        
        # 寫入新數據
        current_pos = self.pre_speech_buffer.tell()
        self.pre_speech_buffer.write(audio_data)
        
        # 如果超過最大大小，只保留最新的數據
        buffer_data = self.pre_speech_buffer.getvalue()
        if len(buffer_data) > max_buffer_size:
            self.pre_speech_buffer = io.BytesIO()
            self.pre_speech_buffer.write(buffer_data[-max_buffer_size:])
    
    async def _save_recording(self, audio_data: bytes) -> Optional[Path]:
        """
        儲存錄音
        
        Args:
            audio_data: 音訊資料
            
        Returns:
            儲存的文件路徑（如果適用）
        """
        if self.storage_type == 'memory':
            # 記憶體儲存，不寫入文件
            return None
        
        elif self.storage_type == 'file':
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.recording_session_id}_{timestamp}.{self.format}"
            file_path = self.storage_path / filename
            
            # 儲存音訊文件
            if self.format == 'wav':
                await self._save_wav(file_path, audio_data)
            else:
                # 其他格式暫時直接儲存原始數據
                with open(file_path, 'wb') as f:
                    f.write(audio_data)
            
            logger.info(f"錄音已儲存: {file_path}")
            return file_path
        
        else:
            logger.warning(f"不支援的儲存類型: {self.storage_type}")
            return None
    
    async def _save_wav(self, file_path: Path, audio_data: bytes):
        """儲存為 WAV 格式"""
        with wave.open(str(file_path), 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data)
    
    async def _save_segment(self):
        """儲存當前段落"""
        segment_data = self.buffer.getvalue()
        if not segment_data:
            return
        
        # 儲存段落
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        segment_filename = f"{self.recording_session_id}_segment_{self.current_segment}_{timestamp}.{self.format}"
        
        if self.storage_type == 'file':
            segment_path = self.storage_path / segment_filename
            await self._save_recording(segment_data)
            self.segments.append(str(segment_path))
            
            logger.info(f"段落 {self.current_segment} 已儲存: {segment_path}")
        
        # 觸發段落完成回調
        if self.segment_complete_callback:
            await self.segment_complete_callback({
                'session_id': self.recording_session_id,
                'segment_index': self.current_segment,
                'segment_duration': self.segment_duration,
                'segment_size': len(segment_data)
            })
        
        # 準備下一個段落
        self.current_segment += 1
        self.buffer = io.BytesIO()
    
    def set_callbacks(self, 
                     recording_complete_callback=None,
                     segment_complete_callback=None):
        """
        設置回調函數
        
        Args:
            recording_complete_callback: 錄音完成回調
            segment_complete_callback: 段落完成回調
        """
        self.recording_complete_callback = recording_complete_callback
        self.segment_complete_callback = segment_complete_callback
    
    async def process_from_queue(self, session_id: str):
        """
        從 AudioQueueManager 處理音訊（串流模式）
        
        Args:
            session_id: Session ID
        """
        if not self.audio_queue_manager:
            logger.warning("RecordingOperator: No AudioQueueManager configured")
            return
        
        logger.info(f"RecordingOperator: Starting queue processing for session {session_id}")
        
        # 確保佇列存在
        if session_id not in self.audio_queue_manager.queues:
            await self.audio_queue_manager.create_queue(session_id)
        
        # 開始錄音
        await self.start_recording(session_id)
        
        try:
            while self.is_recording and self.enabled:
                try:
                    # 從佇列拉取音訊
                    audio_data = await self.audio_queue_manager.pull(session_id, timeout=0.1)
                    
                    if audio_data:
                        # 處理音訊
                        await self.process(audio_data, session_id=session_id)
                    else:
                        # 沒有音訊時短暫等待
                        await asyncio.sleep(0.01)
                        
                except asyncio.TimeoutError:
                    # 超時是正常的，繼續等待
                    continue
                except Exception as e:
                    logger.error(f"RecordingOperator queue processing error: {e}")
                    break
                    
        finally:
            # 停止錄音
            if self.is_recording:
                await self.stop_recording(session_id)
            logger.info(f"RecordingOperator: Stopped queue processing for session {session_id}")
    
    def get_recording_info(self) -> Dict[str, Any]:
        """
        獲取當前錄音資訊
        
        Returns:
            錄音資訊字典
        """
        info = {
            'is_recording': self.is_recording,
            'session_id': self.recording_session_id,
            'duration': time.time() - self.start_time if self.start_time and self.is_recording else 0,
            'bytes_recorded': self.total_bytes_recorded,
            'current_segment': self.current_segment,
            'segments_count': len(self.segments),
            'storage_type': self.storage_type
        }
        
        return info