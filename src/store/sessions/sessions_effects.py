"""
Sessions 域的 Effects 實現

這是純事件驅動架構的核心，管理所有 session 相關的副作用，
包括 operator 生命週期、音訊處理和狀態轉換。
"""

import asyncio
from typing import Dict, Optional, Any
from weakref import WeakValueDictionary
from pystorex import create_effect,ofType
from reactivex import timer
from reactivex import operators as ops

from .sessions_state import FSMStrategy
from src.utils.logger import logger
from src.utils.rxpy_async import async_flat_map
from src.core.audio_queue_manager import get_audio_queue_manager, AudioQueueManager
from src.core.timer_manager import timer_manager
from .fsm_config import get_strategy_config
from .sessions_state import FSMStateEnum, FSMStrategy
from .sessions_actions import (
    create_session, destroy_session, session_created, session_destroyed,
    wake_triggered, start_recording, start_asr_streaming, fsm_reset,
    session_error, transcription_done, begin_transcription, end_recording,
    audio_chunk_received, speech_detected, silence_detected,
    recording_started, countdown_started, countdown_cancelled,
    mode_switched, switch_mode, end_asr_streaming
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
        self.audio_queue_manager = audio_queue_manager or get_audio_queue_manager()
        
        # 使用 WeakValueDictionary 自動管理生命週期
        # 註：雖然 operators 共享模型（類別層級），但為了簡化狀態管理，
        # 我們仍為每個 session 創建獨立的 operator 實例。
        # 這些實例很輕量，只包含狀態，不包含模型。
        self.session_operators: Dict[str, WeakValueDictionary] = {
            'format_conversion': WeakValueDictionary(),  # session_id -> format converter
            'wakeword': WeakValueDictionary(),   # session_id -> operator instance (state only)
            'vad': WeakValueDictionary(),        # session_id -> operator instance (state only)
            'recording': WeakValueDictionary()   # session_id -> operator instance (state only)
        }
        
        # 管理每個 session 的 providers
        self.session_providers: WeakValueDictionary = WeakValueDictionary()
        
        # 管理每個 session 的模式
        self.session_strategies: Dict[str, FSMStrategy] = {}
        
        # Operator 和 Provider 工廠函數（將由 inject_xxx_factory 注入）
        self.operator_factories = {}
        self.provider_factories = {}
        
        # Pipeline 和 Provider 管理器（可選）
        # Pipeline functionality now handled internally by SessionEffects
        self.provider_manager = None
        
        # Pipeline 執行順序配置
        self.pipeline_order = [
            'format_conversion',  # 1. 格式轉換
            'wakeword',          # 2. 喚醒詞檢測
            'vad',               # 3. VAD 處理
            'recording'          # 4. 錄音管理
        ]
    
    def _format_session_id(self, session_id: str) -> str:
        """安全格式化 session_id 用於日誌顯示"""
        if session_id is None:
            return "[None]"
        return session_id[:8] if len(session_id) > 8 else session_id
    
    
    # ============================================================================
    # Session 生命週期 Effects
    # ============================================================================
    
    @create_effect
    def create_session_effect(self, action_stream):
        """創建 Session Effect
        
        監聽 create_session action，初始化該 session 的所有 operators 和資源。
        """
        return action_stream.pipe(
            ofType(create_session),
            async_flat_map(self._handle_create_session)
        )
    
    async def _handle_create_session(self, action):
        """處理 session 創建邏輯"""
        payload = action.payload
        session_id = payload["id"]
        
        # 從 strategy 取得策略
        strategy = payload.get("strategy", FSMStrategy.NON_STREAMING)
        
        logger.info(f"Creating session {session_id} with strategy {strategy}")
        
        try:
            # 儲存 session 策略
            self.session_strategies[session_id] = strategy
            
            # 根據策略初始化不同的 operators
            if strategy == FSMStrategy.BATCH:
                await self._setup_batch_mode(session_id)
            elif strategy == FSMStrategy.NON_STREAMING:
                await self._setup_non_streaming_mode(session_id)
            else:  # STREAMING
                await self._setup_streaming_mode(session_id)
            
            # 初始化該 session 的音訊隊列
            if self.audio_queue_manager:
                await self.audio_queue_manager.create_queue(session_id)
            
            # 建立該 session 的 timer
            await timer_manager.create_timer(session_id)
            logger.info(f"Timer created for session: {session_id}")
            
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
            ofType(destroy_session),
            async_flat_map(self._handle_destroy_session)
        )
    
    async def _handle_destroy_session(self, action):
        """處理 session 銷毀邏輯"""
        session_id = action.payload["id"]
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
            
            # 銷毀該 session 的 timer
            await timer_manager.destroy_timer(session_id)
            logger.info(f"Timer destroyed for session: {session_id}")
            
            # 清理 providers
            self.session_providers.pop(session_id, None)
            
            # 清理模式記錄
            self.session_strategies.pop(session_id, None)
            
            # Dispatch session_destroyed action
            if self.store:
                self.store.dispatch(session_destroyed(session_id))
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to destroy session {session_id}: {e}")
            return []
    
    async def _create_operator(self, operator_type: str, session_id: str, **kwargs) -> Optional[Any]:
        """創建並初始化 operator 的通用方法
        
        Args:
            operator_type: Operator 類型
            session_id: Session ID
            **kwargs: 傳給工廠函數的參數
            
        Returns:
            創建的 operator 實例，失敗返回 None
        """
        if operator_type not in self.operator_factories:
            logger.warning(f"{operator_type} operator factory not injected")
            return None
            
        try:
            operator = self.operator_factories[operator_type](**kwargs)
            
            # 初始化（如果有 initialize 方法）
            if hasattr(operator, 'initialize'):
                await operator.initialize()
                
            # 儲存到對應的字典
            if operator_type in self.session_operators:
                self.session_operators[operator_type][session_id] = operator
                
            logger.debug(f"{operator_type} operator created for session {session_id}")
            return operator
            
        except Exception as e:
            logger.error(f"Failed to create {operator_type} operator: {e}")
            return None
    
    async def _setup_batch_mode(self, session_id: str):
        """批次模式：收集完整音訊
        
        配置：
        - 不啟動實時 VAD，只做事後分析
        - Recording operator 持續錄製直到手動停止  
        - 完整音訊送入 Whisper 一次轉譯
        """
        recording = await self._create_operator(
            'recording', 
            session_id,
            store=self.store,
            audio_queue_manager=self.audio_queue_manager
        )
        
        if recording:
            # 配置批次模式參數
            recording.vad_controlled = False  # 關閉 VAD 控制
            recording.max_duration = 300  # 5 分鐘上限
            logger.info(f"✓ Session {session_id} 配置為批次模式")
    
    async def _setup_non_streaming_mode(self, session_id: str):
        """非串流實時模式：逐塊處理但等待完整結果"""
        
        # 獲取 session 的音訊格式（如果有的話）
        audio_format = self._get_audio_format(session_id)
        
        # 創建格式轉換 Operator
        # 如果 session 有音訊格式，使用它；否則使用預設值
        if audio_format:
            await self._create_operator(
                'format_conversion',
                session_id,
                target_format="pcm",
                sample_rate=audio_format.get('sample_rate', 16000),
                channels=audio_format.get('channels', 1)
            )
        else:
            await self._create_operator(
                'format_conversion',
                session_id,
                target_format="pcm",
                sample_rate=16000,
                channels=1
            )
        
        # 檢查是否啟用 WakeWord
        if self._is_wakeword_enabled():
            await self._create_operator('wakeword', session_id, store=self.store)
        
        # 創建 VAD Operator
        vad = await self._create_operator('vad', session_id, store=self.store)
        if vad:
            vad.min_silence_duration = 1.8
            vad.min_speech_duration = 0.5
            vad.threshold = 0.5
        
        # 創建 Recording Operator
        recording = await self._create_operator(
            'recording',
            session_id,
            store=self.store,
            audio_queue_manager=self.audio_queue_manager
        )
        if recording:
            recording.vad_controlled = True
            recording.silence_countdown_duration = 1.8
            recording.max_duration = 30
        
        # 記錄創建的 operators
        created = self._get_created_operators(session_id)
        if created:
            logger.info(f"✓ Session {session_id} 配置為非串流實時模式 (Operators: {', '.join(created)})")
    
    def _is_wakeword_enabled(self) -> bool:
        """檢查是否啟用 WakeWord"""
        try:
            from src.config.manager import ConfigManager
            config = ConfigManager()
            if hasattr(config, 'pipeline') and hasattr(config.pipeline, 'operators'):
                if hasattr(config.pipeline.operators, 'wakeword'):
                    return config.pipeline.operators.wakeword.enabled
        except Exception as e:
            logger.debug(f"Failed to read WakeWord config: {e}")
        return False
    
    def _get_created_operators(self, session_id: str) -> list:
        """獲取已創建的 operators 列表"""
        created = []
        operator_names = {
            'format_conversion': 'FormatConversion',
            'wakeword': 'WakeWord',
            'vad': 'VAD',
            'recording': 'Recording'
        }
        
        for op_type, name in operator_names.items():
            if op_type in self.session_operators and session_id in self.session_operators[op_type]:
                created.append(name)
        
        return created
    
    async def _setup_streaming_mode(self, session_id: str):
        """串流實時模式：逐塊處理並串流輸出"""
        
        # 創建 WakeWord Operator
        await self._create_operator('wakeword', session_id, store=self.store)
        
        # 創建 VAD Operator（串流模式使用更短的閾值）
        vad = await self._create_operator('vad', session_id, store=self.store)
        if vad:
            vad.min_silence_duration = 0.5  # 更短的靜音閾值
            vad.min_speech_duration = 0.3   # 更短的語音閾值
            vad.threshold = 0.5
        
        # 創建 Recording Operator
        recording = await self._create_operator(
            'recording',
            session_id,
            store=self.store,
            audio_queue_manager=self.audio_queue_manager
        )
        if recording:
            recording.vad_controlled = True
            recording.silence_countdown_duration = 1.0  # 更快的分段
            recording.segment_duration = 10             # 10 秒自動分段
            recording.max_duration = 30
        
        logger.info(f"✓ Session {session_id} 配置為串流實時模式")
    
    
    # ============================================================================
    # FSM 狀態轉換 Effects
    # ============================================================================
    
    @create_effect
    def fsm_transition_effect(self, action_stream):
        """FSM 狀態轉換 Effect
        
        監聽所有會導致 FSM 狀態變化的 actions，管理相應的 operators。
        """
        return action_stream.pipe(
            ofType(wake_triggered, start_recording, end_recording,
                   start_asr_streaming, end_asr_streaming, fsm_reset),
            async_flat_map(self._handle_fsm_transition)
        )
    
    async def _handle_fsm_transition(self, action):
        """處理 FSM 狀態轉換"""
        session_id = action.payload.get("session_id")
        logger.debug(f"Handling FSM transition for session {session_id} with action {action.type}")
        
        # 檢查 session 是否存在於任一 operator 字典中
        has_operators = any(
            session_id in operator_dict 
            for operator_dict in self.session_operators.values()
        )
        
        if not session_id or not has_operators:
            return []
        
        # 獲取該 session 的所有 operators
        operators = {}
        for op_type, op_dict in self.session_operators.items():
            if session_id in op_dict:
                operators[op_type] = op_dict[session_id]
        
        # Phase 3.1: 優化的 operator 控制邏輯
        if action.type == wake_triggered.type:
            # 喚醒後啟動 VAD
            if 'vad' in operators:
                await operators['vad'].start()
                logger.info(f"✅ VAD started for session {self._format_session_id(session_id)}...")
                
        elif action.type == start_recording.type:
            # 開始錄音
            if 'recording' in operators:
                await operators['recording'].start()
                logger.info(f"🔴 Recording started for session {self._format_session_id(session_id)}...")
                # 啟動錄音計時器
                timer = timer_manager.get_timer(session_id)
                if timer:
                    await timer.start_recording_timer()
                
        elif action.type == end_recording.type:
            # 結束錄音
            if 'recording' in operators:
                await operators['recording'].stop()
                logger.info(f"⏹️ Recording stopped for session {self._format_session_id(session_id)}...")
                # 取消錄音計時器
                timer = timer_manager.get_timer(session_id)
                if timer:
                    timer.cancel_timer('recording')
                # Phase 3.1: 確保錄音數據已保存
                if self.audio_queue_manager:
                    queue_size = await self.audio_queue_manager.get_queue_size(session_id)
                    logger.debug(f"💾 Audio queue size: {queue_size} chunks")
        
        elif action.type == start_asr_streaming.type:
            # 開始串流
            logger.info(f"📡 Streaming started for session {self._format_session_id(session_id)}...")
            # 啟動串流計時器
            timer = timer_manager.get_timer(session_id)
            if timer:
                await timer.start_streaming_timer()
                
        elif action.type == end_asr_streaming.type:
            # 結束串流
            logger.info(f"⏹️ Streaming stopped for session {self._format_session_id(session_id)}...")
            # 取消串流計時器
            timer = timer_manager.get_timer(session_id)
            if timer:
                timer.cancel_timer('streaming')
                
        elif action.type == fsm_reset.type:
            # Phase 3.1: 改進的重置邏輯
            logger.info(f"🔄 Resetting all operators for session {self._format_session_id(session_id)}...")
            for op_type, operator in operators.items():
                if hasattr(operator, 'reset'):
                    await operator.reset()
                    logger.debug(f"  - {op_type} operator reset")
                elif hasattr(operator, 'stop'):
                    await operator.stop()
                    logger.debug(f"  - {op_type} operator stopped")
        
        return []
    
    # ============================================================================
    # 音訊處理 Effects  
    # ============================================================================
    
    @create_effect
    def audio_processing_effect(self, action_stream):
        """音訊處理 Pipeline Effect
        
        監聽 audio_chunk_received action，將音訊數據通過 operator pipeline 處理。
        這是音訊處理的核心流程，確保數據按正確順序經過各個 operator。
        """
        return action_stream.pipe(
            ofType(audio_chunk_received),
            async_flat_map(self._process_audio_through_pipeline)
        )
    
    async def _process_audio_through_pipeline(self, action):
        """處理音訊通過 Pipeline
        
        音訊處理流程：
        1. 格式轉換 - 統一音訊格式 (PCM, 16kHz, mono)
        2. WakeWord 檢測 - 在 LISTENING 狀態檢測喚醒詞
        3. VAD 處理 - 在 RECORDING 狀態檢測語音/靜音
        4. AudioQueue - 儲存處理後的音訊數據
        
        注意：新架構中音訊數據由 AudioQueueManager 管理，
              此 action 只包含元數據（chunk_size, timestamp）
        """
        session_id = action.payload.get("session_id")
        audio_data = action.payload.get("data")
        chunk_size = action.payload.get("chunk_size")
        
        # 新架構：如果只有 chunk_size（元數據），跳過處理
        if chunk_size is not None and audio_data is None:
            # 這是新的元數據格式，音訊已經在 AudioQueueManager 中
            # 不需要警告，這是正常的
            return []
        
        if not session_id:
            logger.warning(f"Missing session_id in audio_chunk_received payload")
            return []
        
        # 舊架構相容：如果有實際音訊數據，繼續處理
        if audio_data is None:
            # 既沒有 chunk_size 也沒有 data，這才是真的無效
            logger.warning(f"Invalid audio_chunk_received payload: {action.payload}")
            return []
        
        try:
            # 獲取當前 session 狀態
            session_state = self._get_session_state(session_id)
            if not session_state:
                logger.debug(f"Session {session_id} not found or not initialized")
                return []
            
            current_fsm_state = session_state.get('fsm_state')
            logger.debug(f"Processing audio for session {session_id} in state {current_fsm_state}")
            
            # 1. 格式轉換 (總是執行)
            if session_id in self.session_operators.get('format_conversion', {}):
                try:
                    converter = self.session_operators['format_conversion'][session_id]
                    if hasattr(converter, 'process'):
                        audio_data = await converter.process(audio_data)
                        logger.debug(f"Audio format converted for session {session_id}")
                except Exception as e:
                    logger.error(f"Format conversion failed: {e}")
            
            # 2. WakeWord 檢測 (只在 LISTENING 狀態)
            if current_fsm_state == FSMStateEnum.LISTENING:
                if session_id in self.session_operators.get('wakeword', {}):
                    try:
                        wakeword = self.session_operators['wakeword'][session_id]
                        if hasattr(wakeword, 'process'):
                            detection = await wakeword.process(audio_data)
                            if detection and hasattr(detection, 'confidence'):
                                if detection.confidence > 0.7:  # 閾值可配置
                                    # Phase 3.2: 喚醒詞檢測日誌
                                    logger.info("┌" + "─" * 60 + "┐")
                                    logger.info(f"│ 🎆 WAKE WORD DETECTED!")
                                    logger.info(f"│ 🔹 Session: {self._format_session_id(session_id)}...")
                                    logger.info(f"│ 🎯 Confidence: {detection.confidence:.2f}")
                                    logger.info(f"│ 🔊 Trigger: {getattr(detection, 'trigger', 'unknown')}")
                                    logger.info("└" + "─" * 60 + "┘")
                                    self.store.dispatch(wake_triggered(
                                        session_id, 
                                        detection.confidence, 
                                        getattr(detection, 'trigger', 'unknown')
                                    ))
                    except Exception as e:
                        logger.error(f"WakeWord detection failed: {e}")
            
            # 3. VAD 處理 (只在 RECORDING 狀態)
            elif current_fsm_state == FSMStateEnum.RECORDING:
                if session_id in self.session_operators.get('vad', {}):
                    try:
                        vad = self.session_operators['vad'][session_id]
                        if hasattr(vad, 'process'):
                            vad_result = await vad.process(audio_data)
                            if vad_result:
                                if getattr(vad_result, 'is_speech', False):
                                    logger.debug(f"Speech detected for session {session_id}")
                                    self.store.dispatch(speech_detected(
                                        session_id, 
                                        getattr(vad_result, 'confidence', 0.5)
                                    ))
                                else:
                                    silence_duration = getattr(vad_result, 'silence_duration', 0)
                                    if silence_duration > 0:
                                        logger.debug(f"Silence detected for session {session_id}: {silence_duration}s")
                                        self.store.dispatch(silence_detected(
                                            session_id, 
                                            silence_duration
                                        ))
                    except Exception as e:
                        logger.error(f"VAD processing failed: {e}")
            
            # 4. 存入 AudioQueue (總是執行)
            if self.audio_queue_manager:
                try:
                    await self.audio_queue_manager.push(session_id, audio_data)
                    logger.debug(f"Audio pushed to queue for session {session_id}: {len(audio_data)} bytes")
                except Exception as e:
                    logger.error(f"Failed to push audio to queue: {e}")
            
            return []
            
        except Exception as e:
            logger.error(f"Pipeline processing failed for session {session_id}: {e}")
            if self.store:
                self.store.dispatch(session_error(session_id, str(e)))
            return []
    
    def _get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """獲取 session 狀態的輔助方法
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 狀態字典，如果不存在則返回 None
        """
        if not self.store:
            return None
            
        state = self.store.state
        sessions_state = state.get('sessions', {})
        
        # 處理不同的狀態結構
        if hasattr(sessions_state, 'get'):
            all_sessions = sessions_state.get('sessions', {})
        else:
            all_sessions = {}
            
        if hasattr(all_sessions, 'get'):
            return all_sessions.get(session_id)
        
        return None
    
    def _get_audio_format(self, session_id: str) -> Optional[Dict[str, Any]]:
        """獲取 session 的音訊格式
        
        Args:
            session_id: Session ID
            
        Returns:
            音訊格式字典，如果不存在則返回 None
        """
        session = self._get_session_state(session_id)
        if session:
            return session.get('audio_format')
        return None
    
    @create_effect
    def countdown_management_effect(self, action_stream):
        """倒數管理 Effect
        
        管理靜音倒數計時，用於自動停止錄音。
        當檢測到靜音時啟動計時器，如果在倒數期間檢測到語音則取消計時器。
        """
        return action_stream.pipe(
            ofType(silence_detected),
            ops.flat_map(lambda action: self._handle_countdown(action, action_stream))
        )
    
    def _handle_countdown(self, action, action_stream):
        """處理倒數計時邏輯
        
        改進版本：
        1. 增強視覺化日誌輸出
        2. 確保正確觸發 end_recording（而非 recording_stopped）
        3. 支援動態倒數時間調整
        """
        session_id = action.payload.get("session_id")
        duration = action.payload.get("duration", 1.8)  # 預設 1.8 秒
        
        # 檢查 session_id 是否有效
        if session_id is None:
            logger.warning("Received silence_detected action with session_id=None, skipping countdown")
            return []
        
        # 視覺化倒數開始
        logger.info("┌" + "─" * 60 + "┐")
        logger.info(f"│ 🔕 SILENCE COUNTDOWN STARTED - Session: {self._format_session_id(session_id)}...")
        logger.info(f"│ ⏱️  Duration: {duration}s")
        logger.info("└" + "─" * 60 + "┘")
        
        # Dispatch countdown_started
        if self.store:
            self.store.dispatch(countdown_started(session_id, duration))
        
        # 創建倒數計時器，但可以被 speech_detected 或 end_recording 取消
        return timer(duration).pipe(
            ops.map(lambda _: end_recording(session_id, "silence_timeout", duration)),
            ops.take_until(
                action_stream.pipe(
                    ops.filter(lambda b: 
                        b.payload.get("session_id") == session_id and
                        b.type in [
                            speech_detected.type,  # 檢測到語音，取消倒數
                            end_recording.type,  # 已經結束錄音
                            fsm_reset.type  # FSM 重置
                        ]
                    ),
                    ops.do_action(lambda b: self._log_countdown_cancelled(session_id, b.type))
                )
            ),
            ops.do_action(lambda a: self._log_countdown_completed(session_id) if a.type == end_recording.type else None)
        )
    
    def _log_countdown_cancelled(self, session_id: str, cancel_reason: str):
        """記錄倒數取消 - 增強視覺化"""
        reason_emoji = {
            speech_detected.type: "🗣️ SPEECH DETECTED",
            end_recording.type: "⏹️ RECORDING ENDED",
            fsm_reset.type: "🔄 FSM RESET"
        }.get(cancel_reason, f"❓ {cancel_reason}")
        
        logger.info("┌" + "─" * 60 + "┐")
        logger.info(f"│ ❌ COUNTDOWN CANCELLED - Session: {self._format_session_id(session_id)}...")
        logger.info(f"│ 📍 Reason: {reason_emoji}")
        logger.info("└" + "─" * 60 + "┘")
        
        if self.store:
            self.store.dispatch(countdown_cancelled(session_id))
    
    def _log_countdown_completed(self, session_id: str):
        """記錄倒數完成 - 視覺化日誌"""
        logger.info("┌" + "─" * 60 + "┐")
        logger.info(f"│ ✅ COUNTDOWN COMPLETED - Session: {self._format_session_id(session_id)}...")
        logger.info(f"│ 🔚 Triggering end_recording due to silence timeout")
        logger.info("└" + "─" * 60 + "┘")
    
    @create_effect
    def transcription_processing_effect(self, action_stream):
        """轉譯處理 Effect
        
        調用 Whisper provider 進行語音轉譯。
        
        取代原有的 mock_transcription_result。
        """
        return action_stream.pipe(
            ofType(begin_transcription),
            async_flat_map(self._handle_transcription)
        )
    
    async def _handle_transcription(self, action):
        """處理轉譯請求"""
        session_id = action.payload.get("session_id")
        
        try:
            # 嘗試使用真實的 Whisper provider
            if 'whisper' in self.provider_factories:
                # 創建 Whisper provider 實例
                whisper = self.provider_factories['whisper'](store=self.store)
                
                # 從音訊隊列獲取錄音數據
                audio_data = None
                if self.audio_queue_manager:
                    audio_data = self.audio_queue_manager.stop_recording(session_id)
                
                if audio_data:
                    # 調用真實的轉譯
                    result = await whisper.transcribe(audio_data)
                    if self.store:
                        self.store.dispatch(transcription_done(session_id, result))
                else:
                    logger.warning(f"No audio data available for transcription in session {session_id}")
                    if self.store:
                        self.store.dispatch(session_error(session_id, "No audio data available"))
            else:
                # 沒有 provider，使用模擬結果
                await asyncio.sleep(1.0)
                if self.store:
                    self.store.dispatch(transcription_done(
                        session_id,
                        f"模擬轉譯結果 (session: {session_id})"
                    ))
            
        except Exception as e:
            logger.error(f"Transcription failed for session {session_id}: {e}")
            if self.store:
                self.store.dispatch(session_error(session_id, str(e)))
        
        return []
    
    # ============================================================================
    # Timer 和 Window Effects
    # ============================================================================
    
    @create_effect
    def wake_window_timer(self, action_stream):
        """喚醒視窗計時器 Effect
        
        當檢測到喚醒詞後，啟動計時器。
        如果在超時內沒有開始錄音或串流，則重置 FSM。
        超時時間從 FSM 配置中讀取。
        """
        return action_stream.pipe(
            ofType(wake_triggered),
            ops.flat_map(lambda action: self._handle_wake_window_timeout(action, action_stream))
        )
    
    def _handle_wake_window_timeout(self, action, action_stream):
        """處理喚醒視窗超時"""
        session_id = action.payload["session_id"]
        
        # 從 Store 獲取 session 資訊
        state = self.store.state
        sessions_state = state.get('sessions', {})
        all_sessions = sessions_state.get('sessions', {}) if hasattr(sessions_state, 'get') else {}
        session = all_sessions.get(session_id) if hasattr(all_sessions, 'get') else None
        
        if not session:
            return timer(5.0).pipe(  # 預設 5 秒
                ops.map(lambda _: fsm_reset(session_id))
            )
        
        # 從 FSM 配置獲取超時設定
        strategy = session.get("strategy", FSMStrategy.NON_STREAMING)
        config = get_strategy_config(strategy)
        timeout_ms = config.timeout_configs.get(FSMStateEnum.ACTIVATED, 5000)
        timeout_sec = timeout_ms / 1000.0
        
        logger.debug(f"Wake window timeout for session {session_id}: {timeout_sec}s")
        
        return timer(timeout_sec).pipe(
            ops.map(lambda _: fsm_reset(session_id)),
            ops.take_until(
                action_stream.pipe(
                    ops.filter(lambda b: 
                        b.type in [start_recording.type, start_asr_streaming.type, fsm_reset.type] and
                        b.payload.get("session_id") == session_id
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
            ofType(end_recording),
            ops.delay(0.1),  # 小延遲確保狀態已更新
            ops.map(lambda a: begin_transcription(a.payload["session_id"]))
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
            ofType(wake_triggered, transcription_done, session_error),
            ops.do_action(lambda action: self._collect_metrics(action))
        )
    
    def _log_action(self, action):
        """記錄 Action 到日誌"""
        logger.info(f"Session Event: {action.type} | Payload: {action.payload}")
    
    def _collect_metrics(self, action):
        """收集業務指標"""
        if action.type == wake_triggered.type:
            # 記錄喚醒詞檢測指標
            confidence = action.payload.get("confidence", 0)
            trigger_type = action.payload.get("trigger", "unknown")
            logger.info(f"Wake word detected: {trigger_type} (confidence: {confidence})")
        
        elif action.type == transcription_done.type:
            # 記錄轉譯完成指標
            result_length = len(action.payload.get("result", ""))
            logger.info(f"Transcription completed: {result_length} characters")
        
        elif action.type == session_error.type:
            # 記錄錯誤指標
            error = action.payload.get("error", "unknown")
            logger.error(f"Session error: {error}")


class SessionTimerEffects:
    """Session 計時器相關的 Effects"""
    
    def __init__(self, store=None):
        """
        初始化 SessionTimerEffects
        
        Args:
            store: PyStoreX store 實例
        """
        self.store = store
    
    @create_effect
    def session_timeout(self, action_stream):
        """會話超時 Effect
        
        Phase 3.3: 實作狀態超時處理
        - 長時間未活動的會話將被自動重置
        - 加入超時警告日誌
        """
        return action_stream.pipe(
            ofType(wake_triggered, start_recording),
            ops.group_by(lambda a: a.payload["session_id"]),
            ops.flat_map(lambda group: group.pipe(
                ops.debounce(300.0),  # 5分鐘無活動
                ops.do_action(lambda a: logger.warning(
                    f"⚠️ Session {a.payload['session_id'][:8]}... inactive for 5 minutes, resetting..."
                )),
                ops.map(lambda a: fsm_reset(a.payload["session_id"]))
            ))
        )
    
    @create_effect
    def recording_timeout(self, action_stream):
        """錄音超時 Effect
        
        錄音時間過長時自動結束錄音。
        超時時間從 FSM 配置中讀取。
        """
        return action_stream.pipe(
            ofType(start_recording, start_asr_streaming),
            ops.flat_map(lambda action: self._handle_recording_timeout(action, action_stream))
        )
    
    def _handle_recording_timeout(self, action, action_stream):
        """處理錄音超時
        
        Phase 3.3: 實作狀態超時處理
        """
        session_id = action.payload["session_id"]
        is_streaming = action.type == start_asr_streaming.type
        
        # 從 Store 獲取 session 資訊
        state = self.store.state
        sessions_state = state.get('sessions', {})
        all_sessions = sessions_state.get('sessions', {}) if hasattr(sessions_state, 'get') else {}
        session = all_sessions.get(session_id) if hasattr(all_sessions, 'get') else None
        
        if not session:
            timeout_sec = 30.0  # 預設 30 秒
            logger.warning(f"⚠️ Session {session_id} not found, using default recording timeout")
        else:
            # 從 FSM 配置獲取超時設定
            strategy = session.get("strategy", FSMStrategy.NON_STREAMING)
            config = get_strategy_config(strategy)
            
            # 根據是錄音還是串流選擇對應的超時
            state_key = FSMStateEnum.STREAMING if is_streaming else FSMStateEnum.RECORDING
            timeout_ms = config.timeout_configs.get(state_key, 30000)
            timeout_sec = timeout_ms / 1000.0
        
        # Phase 3.3: 增強超時警告日誌
        logger.warning("┌" + "─" * 60 + "┐")
        logger.warning(f"│ ⏰ RECORDING TIMEOUT STARTED")
        logger.warning(f"│ 🔹 Session: {self._format_session_id(session_id)}...")
        logger.warning(f"│ ⏱️  Duration: {timeout_sec}s")
        logger.warning(f"│ 🎤 Type: {'Streaming' if is_streaming else 'Recording'}")
        logger.warning("└" + "─" * 60 + "┘")
        
        # 選擇結束動作
        end_action = end_asr_streaming if is_streaming else end_recording
        
        return timer(timeout_sec).pipe(
            ops.map(lambda _: end_action(
                session_id,
                "timeout",
                timeout_sec
            )),
            ops.do_action(lambda a: logger.error(
                f"❌ RECORDING TIMEOUT TRIGGERED for session {self._format_session_id(session_id)}... after {timeout_sec}s"
            )),
            ops.take_until(
                action_stream.pipe(
                    ops.filter(lambda b:
                        b.type in [end_recording.type, end_asr_streaming.type, fsm_reset.type] and
                        b.payload.get("session_id") == session_id
                    ),
                    ops.do_action(lambda b: logger.info(
                        f"✅ Recording timeout cancelled for session {self._format_session_id(session_id)}... (reason: {b.type})"
                    ))
                )
            )
        )