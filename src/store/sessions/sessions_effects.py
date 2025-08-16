"""
Sessions 域的 Effects 實現

這是純事件驅動架構的核心，管理所有 session 相關的副作用，
包括 operator 生命週期、音訊處理和狀態轉換。
"""

import asyncio
import time
from typing import Dict, Optional, Any
from weakref import WeakValueDictionary
from pystorex import create_effect
from reactivex import timer, Subject
from reactivex import operators as ops

from src.models.session_mode import SessionMode
from src.utils.logger import logger
from src.utils.rxpy_async import async_flat_map
from .sessions_actions import (
    create_session, destroy_session, session_created, session_destroyed,
    wake_triggered, start_recording, start_streaming, reset_fsm,
    session_error, transcription_done, begin_transcription, end_recording,
    audio_chunk_received, speech_detected, silence_detected,
    recording_started, recording_stopped, countdown_started, countdown_cancelled,
    mode_switched, switch_mode, end_streaming
)


class SessionEffects:
    """Session 相關的 Effects
    
    管理所有 session 的副作用，包括：
    1. Operator 生命週期管理
    2. 音訊數據處理
    3. FSM 狀態轉換
    4. 錯誤處理和重試
    """
    
    def __init__(self, store=None, audio_queue_manager=None):
        """
        初始化 SessionEffects
        
        Args:
            store: PyStoreX store 實例
            audio_queue_manager: 音訊隊列管理器
            logger: 日誌記錄器
        """
        self.store = store
        self.audio_queue_manager = audio_queue_manager
        
        # 使用 WeakValueDictionary 自動管理生命週期
        # 管理每個 session 的 operators
        self.session_operators: Dict[str, WeakValueDictionary] = {
            'wakeword': WeakValueDictionary(),
            'vad': WeakValueDictionary(),
            'recording': WeakValueDictionary()
        }
        
        # 管理每個 session 的 providers
        self.session_providers: WeakValueDictionary = WeakValueDictionary()
        
        # 管理每個 session 的模式
        self.session_modes: Dict[str, SessionMode] = {}
    
    # ============================================================================
    # Session 生命週期 Effects
    # ============================================================================
    
    @create_effect
    def create_session_effect(self, action_stream):
        """創建 Session Effect
        
        監聽 create_session action，初始化該 session 的所有 operators 和資源。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == create_session.type),
            ops.flat_map(async_flat_map(self._handle_create_session))
        )
    
    async def _handle_create_session(self, action):
        """處理 session 創建邏輯"""
        session_id = action.payload.get("session_id") or action.payload.get("id")
        mode_str = action.payload.get("mode", "streaming")
        mode = SessionMode(mode_str) if isinstance(mode_str, str) else mode_str
        client_info = action.payload.get("client_info", {})
        
        logger.info(f"Creating session {session_id} with mode {mode}")
        
        try:
            # 儲存 session 模式
            self.session_modes[session_id] = mode
            
            # 根據模式初始化不同的 operators
            if mode == SessionMode.BATCH:
                await self._setup_batch_mode(session_id)
            elif mode == SessionMode.NON_STREAMING:
                await self._setup_non_streaming_mode(session_id)
            else:  # STREAMING
                await self._setup_streaming_mode(session_id)
            
            # 初始化該 session 的音訊隊列
            if self.audio_queue_manager:
                await self.audio_queue_manager.create_queue(session_id)
            
            # Dispatch session_created action
            if self.store:
                self.store.dispatch(session_created(session_id))
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            # Dispatch 錯誤 action
            if self.store:
                self.store.dispatch(session_error(session_id, str(e)))
            return []
    
    @create_effect
    def destroy_session_effect(self, action_stream):
        """銷毀 Session Effect
        
        監聽 destroy_session action，清理該 session 的所有資源。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == destroy_session.type),
            ops.flat_map(async_flat_map(self._handle_destroy_session))
        )
    
    async def _handle_destroy_session(self, action):
        """處理 session 銷毀邏輯"""
        session_id = action.payload.get("session_id") or action.payload.get("id")
        
        logger.info(f"Destroying session {session_id}")
        
        try:
            # 清理 operators (WeakValueDictionary 會自動清理)
            for operator_type in self.session_operators:
                if session_id in self.session_operators[operator_type]:
                    operator = self.session_operators[operator_type].get(session_id)
                    if operator and hasattr(operator, 'cleanup'):
                        await operator.cleanup()
                    self.session_operators[operator_type].pop(session_id, None)
            
            # 清理音訊隊列
            if self.audio_queue_manager:
                await self.audio_queue_manager.destroy_queue(session_id)
            
            # 清理 providers
            self.session_providers.pop(session_id, None)
            
            # 清理模式記錄
            self.session_modes.pop(session_id, None)
            
            # Dispatch session_destroyed action
            if self.store:
                self.store.dispatch(session_destroyed(session_id))
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to destroy session {session_id}: {e}")
            return []
    
    async def _setup_batch_mode(self, session_id: str):
        """批次模式：收集完整音訊
        
        配置：
        - 不啟動實時 VAD，只做事後分析
        - Recording operator 持續錄製直到手動停止  
        - 完整音訊送入 Whisper 一次轉譯
        """
        # Phase 1.2 基礎實現：創建 operator 配置但不實例化
        # 實際的 Operator 類別將在 Phase 2 實現
        
        # 儲存 operator 配置
        operator_config = {
            'recording': {
                'enabled': True,
                'vad_controlled': False,  # 關閉 VAD 控制
                'max_duration': 300,  # 5 分鐘上限
                'continuous': True  # 持續錄製
            },
            'vad': {
                'enabled': False  # 批次模式不需要實時 VAD
            },
            'wakeword': {
                'enabled': False  # 批次模式不需要喚醒詞
            }
        }
        
        # 儲存配置（Phase 2 時會用來初始化實際的 operators）
        if not hasattr(self, 'session_operator_configs'):
            self.session_operator_configs = {}
        self.session_operator_configs[session_id] = operator_config
        
        logger.info(f"Session {session_id} 配置為批次模式")
        return session_id
    
    async def _setup_non_streaming_mode(self, session_id: str):
        """非串流實時模式：逐塊處理但等待完整結果
        
        配置：
        - 啟動 VAD 進行實時偵測
        - Recording 根據 VAD 自動分段
        - 每段完成後送 Whisper，但等待完整結果
        """
        # Phase 1.2 基礎實現：創建 operator 配置但不實例化
        
        operator_config = {
            'recording': {
                'enabled': True,
                'vad_controlled': True,  # VAD 控制錄製
                'silence_countdown_duration': 1.8,  # 靜音倒數時間
                'max_duration': 30,  # 單段最大時長
                'continuous': False  # 分段錄製
            },
            'vad': {
                'enabled': True,
                'min_silence_duration': 1.8,  # 最小靜音時長
                'min_speech_duration': 0.5,  # 最小語音時長
                'threshold': 0.5  # VAD 閾值
            },
            'wakeword': {
                'enabled': False  # 非串流模式可選喚醒詞
            }
        }
        
        # 儲存配置
        if not hasattr(self, 'session_operator_configs'):
            self.session_operator_configs = {}
        self.session_operator_configs[session_id] = operator_config
        
        # 設定 operator 之間的聯動關係（Phase 2 實現）
        # VAD 檢測到語音 -> 開始錄音
        # VAD 檢測到靜音 -> 啟動倒數
        # 倒數結束 -> 停止錄音並觸發轉譯
        
        logger.info(f"Session {session_id} 配置為非串流實時模式")
        return session_id
    
    async def _setup_streaming_mode(self, session_id: str):
        """串流實時模式：逐塊處理並串流輸出
        
        配置：
        - 啟動所有 operators（VAD, WakeWord, Recording）
        - 使用較短的靜音閾值快速分段
        - 支援部分結果串流輸出
        """
        # Phase 1.2 基礎實現：創建完整的 operator 配置
        
        operator_config = {
            'recording': {
                'enabled': True,
                'vad_controlled': True,  # VAD 控制錄製
                'silence_countdown_duration': 1.0,  # 更快的分段
                'segment_duration': 10,  # 10 秒自動分段
                'max_duration': 30,  # 單段最大時長
                'continuous': False,  # 分段錄製
                'streaming': True  # 支援串流
            },
            'vad': {
                'enabled': True,
                'min_silence_duration': 0.5,  # 更短的靜音閾值
                'min_speech_duration': 0.3,  # 更短的語音閾值
                'threshold': 0.5,  # VAD 閾值
                'streaming': True  # 串流模式
            },
            'wakeword': {
                'enabled': True,
                'models': ['alexa', 'hey_jarvis'],  # 喚醒詞模型
                'threshold': 0.5,  # 喚醒詞閾值
                'pre_buffer_seconds': 2.0  # 預錄音秒數
            }
        }
        
        # 儲存配置
        if not hasattr(self, 'session_operator_configs'):
            self.session_operator_configs = {}
        self.session_operator_configs[session_id] = operator_config
        
        # 設定串流模式的聯動關係（Phase 2 實現）
        # 喚醒詞檢測 -> 啟動 VAD
        # VAD 檢測到語音 -> 開始錄音
        # VAD 檢測到靜音 -> 啟動倒數（較短）
        # 分段完成 -> 觸發部分轉譯
        # 結果串流輸出
        
        logger.info(f"Session {session_id} 配置為串流實時模式")
        return session_id
    
    async def _setup_streaming_callbacks(self, session_id, wakeword, vad, recording):
        """配置串流模式的回調鏈"""
        # TODO: Phase 2 實現
        pass
    
    # ============================================================================
    # FSM 狀態轉換 Effects
    # ============================================================================
    
    @create_effect
    def fsm_transition_effect(self, action_stream):
        """FSM 狀態轉換 Effect
        
        監聽所有會導致 FSM 狀態變化的 actions，管理相應的 operators。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                wake_triggered.type, 
                start_recording.type,
                end_recording.type,
                start_streaming.type,
                end_streaming.type,
                reset_fsm.type
            ]),
            ops.flat_map(async_flat_map(self._handle_fsm_transition))
        )
    
    async def _handle_fsm_transition(self, action):
        """處理 FSM 狀態轉換"""
        session_id = action.payload.get("session_id")
        print(f"Handling FSM transition for session {session_id} with action {action.type}")
        if not session_id or session_id not in self.session_operators:
            return []
        
        operators = self.session_operators[session_id]
        
        # 根據不同的 action 類型啟用/停用相應的 operators
        if action.type == wake_triggered.type:
            # 喚醒後啟動 VAD
            if 'vad' in operators:
                await operators['vad'].start()
                
        elif action.type == start_recording.type:
            # 開始錄音
            if 'recording' in operators:
                await operators['recording'].start()
                
        elif action.type == end_recording.type:
            # 結束錄音
            if 'recording' in operators:
                await operators['recording'].stop()
                
        elif action.type == reset_fsm.type:
            # 重置所有 operators
            for operator in operators.values():
                if hasattr(operator, 'reset'):
                    await operator.reset()
        
        return []
    
    # ============================================================================
    # Operator 管理 Effects
    # ============================================================================
    
    @create_effect
    def wake_word_detection_effect(self, action_stream):
        """喚醒詞檢測 Effect
        
        管理 OpenWakeWord operator 的生命週期。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == create_session.type),
            ops.flat_map(async_flat_map(self._setup_wake_word_operator))
        )
    
    async def _setup_wake_word_operator(self, action):
        """設置喚醒詞 operator"""
        session_id = action.payload.get("id") or action.payload.get("session_id")
        
        # Phase 1.2 基礎實現：檢查配置並準備初始化
        if hasattr(self, 'session_operator_configs') and session_id in self.session_operator_configs:
            config = self.session_operator_configs[session_id].get('wakeword', {})
            if config.get('enabled', False):
                logger.debug(f"Wake word operator enabled for session {session_id}")
                # Phase 2 將在此處初始化實際的 OpenWakeWordOperator
                # operator = OpenWakeWordOperator(
                #     models=config.get('models', ['alexa']),
                #     threshold=config.get('threshold', 0.5),
                #     store=self.store
                # )
                # await operator.initialize()
                # self.session_operators['wakeword'][session_id] = operator
            else:
                logger.debug(f"Wake word operator disabled for session {session_id}")
        
        return []
    
    @create_effect
    def vad_processing_effect(self, action_stream):
        """VAD 處理 Effect
        
        管理 VAD operator 狀態，觸發錄音開始/結束。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == wake_triggered.type),
            ops.flat_map(async_flat_map(self._setup_vad_operator))
        )
    
    async def _setup_vad_operator(self, action):
        """設置 VAD operator"""
        session_id = action.payload.get("session_id")
        
        # Phase 1.2 基礎實現：檢查配置並準備初始化
        if hasattr(self, 'session_operator_configs') and session_id in self.session_operator_configs:
            config = self.session_operator_configs[session_id].get('vad', {})
            if config.get('enabled', False):
                logger.debug(f"VAD operator enabled for session {session_id}")
                # Phase 2 將在此處初始化實際的 SileroVADOperator
                # operator = SileroVADOperator(
                #     min_silence_duration=config.get('min_silence_duration', 1.8),
                #     min_speech_duration=config.get('min_speech_duration', 0.5),
                #     threshold=config.get('threshold', 0.5),
                #     store=self.store
                # )
                # await operator.initialize()
                # await operator.start()
                # self.session_operators['vad'][session_id] = operator
                
                # 模擬 VAD 啟動成功
                if self.store:
                    self.store.dispatch(speech_detected(session_id, confidence=0.95))
            else:
                logger.debug(f"VAD operator disabled for session {session_id}")
        
        return []
    
    @create_effect
    def recording_control_effect(self, action_stream):
        """錄音控制 Effect
        
        管理錄音 operator 和音訊緩衝處理。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == start_recording.type),
            ops.flat_map(async_flat_map(self._setup_recording_operator))
        )
    
    async def _setup_recording_operator(self, action):
        """設置錄音 operator"""
        session_id = action.payload.get("session_id")
        
        # Phase 1.2 基礎實現：檢查配置並準備初始化
        if hasattr(self, 'session_operator_configs') and session_id in self.session_operator_configs:
            config = self.session_operator_configs[session_id].get('recording', {})
            if config.get('enabled', False):
                logger.debug(f"Recording operator enabled for session {session_id}")
                # Phase 2 將在此處初始化實際的 RecordingOperator
                # operator = RecordingOperator(
                #     vad_controlled=config.get('vad_controlled', True),
                #     silence_countdown_duration=config.get('silence_countdown_duration', 1.8),
                #     max_duration=config.get('max_duration', 30),
                #     continuous=config.get('continuous', False),
                #     store=self.store,
                #     audio_queue_manager=self.audio_queue_manager
                # )
                # await operator.initialize()
                # await operator.start()
                # self.session_operators['recording'][session_id] = operator
                
                # 啟動音訊隊列的錄音功能
                if self.audio_queue_manager:
                    queue = self.audio_queue_manager.get_queue(session_id)
                    if queue:
                        include_pre_buffer = config.get('wakeword', {}).get('enabled', False)
                        pre_buffer_seconds = config.get('wakeword', {}).get('pre_buffer_seconds', 2.0)
                        queue.start_recording(include_pre_buffer, pre_buffer_seconds)
                        
                # 通知錄音已開始
                if self.store:
                    self.store.dispatch(recording_started(session_id, trigger="vad"))
            else:
                logger.debug(f"Recording operator disabled for session {session_id}")
        
        return []
    
    @create_effect
    def countdown_management_effect(self, action_stream):
        """倒數管理 Effect
        
        管理靜音倒數計時，用於自動停止錄音。
        當檢測到靜音時啟動計時器，如果在倒數期間檢測到語音則取消計時器。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == silence_detected.type),
            ops.flat_map(lambda action: self._handle_countdown(action, action_stream))
        )
    
    def _handle_countdown(self, action, action_stream):
        """處理倒數計時邏輯"""
        session_id = action.payload.get("session_id")
        duration = action.payload.get("duration", 1.8)  # 預設 1.8 秒
        
        logger.info(f"Starting countdown for session {session_id}, duration: {duration}s")
        
        # Dispatch countdown_started
        if self.store:
            self.store.dispatch(countdown_started(session_id, duration))
        
        # 創建倒數計時器，但可以被 speech_detected 或 recording_stopped 取消
        return timer(duration).pipe(
            ops.map(lambda _: recording_stopped(session_id, "silence_timeout")),
            ops.take_until(
                action_stream.pipe(
                    ops.filter(lambda b: 
                        b.payload.get("session_id") == session_id and
                        b.type in [
                            speech_detected.type,  # 檢測到語音，取消倒數
                            recording_stopped.type,  # 已經停止錄音
                            reset_fsm.type  # FSM 重置
                        ]
                    ),
                    ops.do_action(lambda b: self._log_countdown_cancelled(session_id, b.type))
                )
            )
        )
    
    def _log_countdown_cancelled(self, session_id: str, cancel_reason: str):
        """記錄倒數取消"""
        logger.debug(f"Countdown cancelled for session {session_id}, reason: {cancel_reason}")
        if self.store:
            self.store.dispatch(countdown_cancelled(session_id))
    
    @create_effect
    def transcription_processing_effect(self, action_stream):
        """轉譯處理 Effect
        
        調用 Whisper provider 進行語音轉譯。
        
        取代原有的 mock_transcription_result。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == begin_transcription.type),
            ops.flat_map(async_flat_map(self._handle_transcription))
        )
    
    async def _handle_transcription(self, action):
        """處理轉譯請求"""
        session_id = action.payload.get("session_id")
        
        try:
            # TODO: Phase 3 實現真實的 Whisper provider 調用
            # 目前保留模擬實現
            await asyncio.sleep(1.0)  # 模擬轉譯延遲
            
            if self.store:
                self.store.dispatch(transcription_done(
                    session_id,
                    f"真實轉譯結果 (session: {session_id})"
                ))
            
        except Exception as e:
            if logger:
                logger.error(f"Transcription failed for session {session_id}: {e}")
            if self.store:
                self.store.dispatch(session_error(session_id, str(e)))
        
        return []
    
    # ============================================================================
    # 原有的 Effects (保留用於兼容)
    # ============================================================================
    
    @create_effect
    def wake_window_timer(self, action_stream):
        """喚醒視窗計時器 Effect
        
        當檢測到喚醒詞後，啟動30秒計時器。
        如果在30秒內沒有開始錄音或串流，則重置 FSM。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == wake_triggered.type),
            ops.flat_map(lambda action: 
                timer(30.0).pipe(  # 30秒超時
                    ops.map(lambda _: reset_fsm(action.payload["session_id"])),
                    ops.take_until(
                        action_stream.pipe(
                            ops.filter(lambda b: 
                                b.type in [start_recording.type, start_streaming.type, reset_fsm.type] and
                                b.payload.get("session_id") == action.payload["session_id"]
                            )
                        )
                    )
                )
            )
        )
    
    @create_effect
    def auto_transcription_trigger(self, action_stream):
        """自動轉譯觸發 Effect
        
        當錄音結束時，自動開始轉譯流程。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == end_recording.type),
            ops.delay(0.1),  # 小延遲確保狀態已更新
            ops.map(lambda a: begin_transcription(a.payload["session_id"]))
        )
    
    @create_effect
    def mock_transcription_result(self, action_stream):
        """模擬轉譯結果 Effect
        
        為了演示目的，模擬轉譯過程並返回結果。
        在實際系統中，這應該被真實的 ASR provider Effect 替代。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == begin_transcription.type),
            ops.delay(1.0),  # 模擬1秒轉譯時間
            ops.map(lambda a: transcription_done(
                a.payload["session_id"],
                f"模擬轉譯結果 (時間: {asyncio.get_event_loop().time():.1f})"
            ))
        )
    
    @create_effect(dispatch=False)
    def session_logging(self, action_stream):
        """Session 事件日誌 Effect
        
        記錄所有 Session 相關的重要事件。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type.startswith("[Session]")),
            ops.do_action(lambda action: self._log_action(action))
        )
    
    @create_effect(dispatch=False)
    def session_metrics(self, action_stream):
        """Session 指標收集 Effect
        
        收集 Session 相關的業務指標。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                wake_triggered.type,
                transcription_done.type,
                session_error.type
            ]),
            ops.do_action(lambda action: self._collect_metrics(action))
        )
    
    def _log_action(self, action):
        """記錄 Action 到日誌"""
        if logger:
            logger.info(f"Session Event: {action.type} | Payload: {action.payload}")
        else:
            print(f"Session Event: {action.type} | Session: {action.payload.get('session_id', 'N/A')}")
    
    def _collect_metrics(self, action):
        """收集業務指標"""
        if action.type == wake_triggered.type:
            # 記錄喚醒詞檢測指標
            confidence = action.payload.get("confidence", 0)
            trigger_type = action.payload.get("trigger", "unknown")
            if logger:
                logger.info(f"Wake word detected: {trigger_type} (confidence: {confidence})")
        
        elif action.type == transcription_done.type:
            # 記錄轉譯完成指標
            result_length = len(action.payload.get("result", ""))
            if logger:
                logger.info(f"Transcription completed: {result_length} characters")
        
        elif action.type == session_error.type:
            # 記錄錯誤指標
            error = action.payload.get("error", "unknown")
            if logger:
                logger.error(f"Session error: {error}")


class SessionTimerEffects:
    """Session 計時器相關的 Effects"""
    
    @create_effect
    def session_timeout(self, action_stream):
        """會話超時 Effect
        
        長時間未活動的會話將被自動重置。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [wake_triggered.type, start_recording.type]),
            ops.group_by(lambda a: a.payload["session_id"]),
            ops.flat_map(lambda group: group.pipe(
                ops.debounce(300.0),  # 5分鐘無活動
                ops.map(lambda a: reset_fsm(a.payload["session_id"]))
            ))
        )
    
    @create_effect
    def recording_timeout(self, action_stream):
        """錄音超時 Effect
        
        錄音時間過長時自動結束錄音。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [start_recording.type, start_streaming.type]),
            ops.flat_map(lambda action:
                timer(30.0).pipe(  # 30秒錄音超時
                    ops.map(lambda _: end_recording(
                        action.payload["session_id"],
                        "timeout",
                        30.0
                    )),
                    ops.take_until(
                        action_stream.pipe(
                            ops.filter(lambda b:
                                b.type in [end_recording.type, reset_fsm.type] and
                                b.payload.get("session_id") == action.payload["session_id"]
                            )
                        )
                    )
                )
            )
        )