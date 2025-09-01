"""
Sessions Effects  with Timestamp Support
使用時間戳機制協調多服務音頻處理，整合現有服務
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Dict, List
import numpy as np
from pystorex.effects import create_effect
import reactivex as rx
from reactivex import operators as ops
from pystorex.rx_operators import ofType

from src.interface.wake import WakeActivateSource
from src.utils.logger import logger
from src.config.manager import ConfigManager
from src.interface.action import Action
from src.interface.state import State

# Services - 使用現有的服務，不重新發明輪子
from src.core.audio_queue_manager import audio_queue, TimestampedAudio
from src.service.audio_converter import audio_converter
from src.service.audio_enhancer import audio_enhancer

# DeepFilterNet 是可選的 (需要 PyTorch)
try:
    from src.service.denoise.deepfilternet_denoiser import deepfilternet_denoiser

    HAS_DEEPFILTERNET = True
except (ImportError, AttributeError) as e:
    logger.warning(f"DeepFilterNet not available: {e}")
    deepfilternet_denoiser = None
    HAS_DEEPFILTERNET = False

from src.service.recording.recording import recording  # 使用現有的錄音服務
from src.core.buffer_manager import BufferManager, BufferConfig
from src.service.vad.silero_vad import silero_vad
from src.service.wakeword.openwakeword import openwakeword
from src.service.timer.timer_service import timer_service
from src.provider.provider_manager import get_provider_manager, PoolConfig
from src.interface.asr_provider import TranscriptionResult

# FSM Transitions - 直接使用 transitions library
from src.core.fsm_transitions import BatchPlugin, NonStreamingPlugin, StreamingPlugin, SessionFSM
from src.interface.strategy import Strategy

# Actions
from src.store.sessions.sessions_action import (
    create_session,
    delete_session,
    session_expired,
    reset_session,
    receive_audio_chunk,
    clear_audio_buffer,
    upload_started,
    upload_completed,
    start_listening,
    wake_activated,
    wake_deactivated,
    vad_speech_detected,
    vad_silence_detected,
    silence_timeout,
    record_started,
    record_stopped,
    play_asr_feedback,
    transcribe_started,
    transcribe_done,
    asr_stream_started,
    asr_stream_stopped,
    llm_reply_started,
    llm_replying,
    llm_reply_completed,
    llm_reply_timeout,
    tts_playback_started,
    tts_playing,
    tts_playback_completed,
    tts_playback_timeout,
    reply_interrupted,
    error_occurred,
    error_raised,
    error_reported,
)


# SessionState enum 已移除 - 現在完全使用 FSM 管理狀態
# 所有狀態查詢都通過 _get_fsm_state() 和相關 helper methods


class SessionEffects:
    """
    Session Effects  - 整合現有服務的音頻處理流程

    核心原則：
    1. 使用時間戳索引音頻，避免服務競爭
    2. 善用現有服務（Recording, AudioEnhancer, DeepFilterNet）
    3. 批量後處理而非實時處理
    4. Pre-roll 和 Tail padding 支援
    """

    # 類別級別變數 - 所有實例共享 FSM 狀態
    _fsm_instances: Dict[str, "SessionFSM"] = {}  # session_id -> FSM instance
    # _session_states 已移除 - 狀態現在由 FSM 實例管理
    _session_strategies: Dict[str, str] = {}  # 記錄每個 session 的策略
    _request_id_mapping: Dict[str, str] = {}  # request_id -> session_id 映射

    def __init__(self, store=None):
        """初始化 Effects"""
        self.store = store

        # 時間戳記錄
        self._wake_word_timestamps: Dict[str, float] = {}
        self._recording_start_timestamps: Dict[str, float] = {}
        self._silence_start_timestamps: Dict[str, float] = {}

        # 監控線程
        self._monitoring_threads: Dict[str, Dict[str, threading.Thread]] = {}

        # 從配置載入參數 - 使用正確的 ConfigManager 路徑
        config = ConfigManager()

        # audio_queue 相關配置
        self.pre_roll_duration = config.services.audio_queue.pre_roll_duration
        self.tail_padding_duration = config.services.audio_queue.tail_padding_duration

        # VAD 相關配置 - 現在可以直接使用 yaml2py 生成的結構
        self.silence_threshold = config.services.vad.silence_threshold

        # Provider Pool
        self._init_provider_pool()

        # ThreadPoolExecutor - 從 Provider Pool 配置取得
        max_workers = config.providers.pool.thread_pool_max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        logger.info(
            f"SessionEffects initialized with pre-roll={self.pre_roll_duration}s, "
            f"tail_padding={self.tail_padding_duration}s"
        )

    def _init_provider_pool(self):
        """初始化 Provider Pool - 使用單例"""
        self._provider_pool = get_provider_manager()  # 使用單例而不是創建新實例
        logger.info(f"Provider pool initialized (using singleton)")

    # === FSM 驗證輔助方法 ===

    def _get_or_create_fsm(self, session_id: str) -> Optional[SessionFSM]:
        """獲取或創建 session 的 FSM 實例

        Args:
            session_id: Session ID

        Returns:
            FSM 實例或 None
        """
        if session_id not in self._fsm_instances:
            strategy = self._session_strategies.get(session_id, Strategy.NON_STREAMING)

            # 根據策略創建對應的 FSM
            if strategy == Strategy.BATCH:
                self._fsm_instances[session_id] = SessionFSM(BatchPlugin)
            elif strategy == Strategy.NON_STREAMING:
                self._fsm_instances[session_id] = SessionFSM(NonStreamingPlugin)
            elif strategy == Strategy.STREAMING:
                self._fsm_instances[session_id] = SessionFSM(StreamingPlugin)
            else:
                logger.warning(f"未知的策略: {strategy}")
                return None

        return self._fsm_instances.get(session_id)

    def _can_transition(self, session_id: str, action: str) -> bool:
        """直接使用 transitions library 檢查狀態轉換是否合法

        Args:
            session_id: Session ID
            action: 要執行的動作

        Returns:
            是否可以轉換
        """
        fsm = self._get_or_create_fsm(session_id)

        if not fsm:
            return False

        # 使用 transitions 的 may_trigger() API
        return fsm.may_trigger(action)

    def _trigger_transition(self, session_id: str, action: str) -> bool:
        """觸發 FSM 狀態轉換

        Args:
            session_id: Session ID
            action: 要觸發的動作

        Returns:
            是否成功觸發
        """
        fsm = self._get_or_create_fsm(session_id)

        if not fsm:
            return False

        try:
            # 使用 transitions 的 trigger() API 觸發狀態轉換
            old_state = fsm.state
            logger.info(
                f"🔄 FSM Transition: [{session_id}] Triggering '{action}' from state '{old_state}'"
            )
            # 優先使用直接方法調用，如果不存在則使用 trigger()
            if hasattr(fsm, action):
                result = getattr(fsm, action)()
            else:
                result = fsm.trigger(action)
            new_state = fsm.state
            if result:
                logger.info(
                    f"✅ FSM State Changed: [{session_id}] '{old_state}' → '{new_state}' (action: {action})"
                )
            else:
                logger.warning(
                    f"❌ FSM Transition Failed: [{session_id}] Attempted '{action}' from '{old_state}', staying at '{new_state}'"
                )
            return result
        except Exception as e:
            logger.error(f"Failed to trigger transition '{action}' for session {session_id}: {e}")
            return False

    def _get_valid_actions(self, session_id: str) -> List[str]:
        """獲取當前狀態下可執行的所有動作

        Args:
            session_id: Session ID

        Returns:
            可執行的動作列表
        """
        fsm = self._get_or_create_fsm(session_id)

        if not fsm:
            return []

        # HierarchicalGraphMachine 沒有 get_triggers 方法
        # 改為返回基於當前狀態的可能動作列表
        current_state = fsm.state

        # 根據當前狀態返回可能的動作
        if current_state == State.IDLE:
            return [Action.START_LISTENING, Action.UPLOAD_STARTED]
        elif current_state == State.PROCESSING:
            return [Action.WAKE_ACTIVATED, Action.ERROR_OCCURRED]
        elif current_state == f"{State.PROCESSING}_{State.ACTIVATED}":
            return [Action.WAKE_DEACTIVATED, Action.RECORD_STARTED, Action.ASR_STREAM_STARTED]
        elif current_state == f"{State.PROCESSING}_{State.RECORDING}":
            return [Action.RECORD_STOPPED]
        elif current_state == f"{State.PROCESSING}_{State.TRANSCRIBING}":
            return [Action.TRANSCRIBE_DONE, Action.ASR_STREAM_STOPPED]
        else:
            return []

    def _get_fsm_state(self, session_id: str) -> str:
        """獲取 FSM 的當前狀態 - 統一的狀態查詢介面

        Args:
            session_id: Session ID

        Returns:
            當前 FSM 狀態，如果沒有 FSM 則返回 'idle'
        """
        fsm = self._get_or_create_fsm(session_id)
        return fsm.state if fsm else "idle"

    def _is_in_state(self, session_id: str, state: str) -> bool:
        """檢查是否在特定狀態

        注意：這個方法將被移除，改用 transitions 原生的 is_<state>() 方法
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return False
        return fsm.state == state

    def _is_idle(self, session_id: str) -> bool:
        """檢查是否在 idle 狀態

        使用 transitions 原生的 is_idle() 方法
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return True  # 沒有 FSM 時預設為 idle
        return fsm.is_idle() if hasattr(fsm, "is_idle") else fsm.state == "idle"

    def _is_processing(self, session_id: str) -> bool:
        """檢查是否在 processing 狀態（包含所有子狀態）

        使用 transitions 原生的 is_processing(allow_substates=True)
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return False
        # 使用 transitions 的原生方法檢查狀態（包含子狀態）
        return (
            fsm.is_processing(allow_substates=True)
            if hasattr(fsm, "is_processing")
            else fsm.state.startswith("processing")
        )

    def _is_waiting_wake_word(self, session_id: str) -> bool:
        """檢查是否在等待喚醒詞狀態

        注意：在 FSM 中，等待喚醒詞對應 'processing' 狀態（不是子狀態）
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return False
        # 檢查是否在 processing 狀態但不在任何子狀態
        return fsm.state == "processing"

    def _is_activated(self, session_id: str) -> bool:
        """檢查是否已被喚醒（在 activated 子狀態）

        使用 transitions 原生的 is_processing_activated() 方法
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return False
        return (
            fsm.is_processing_activated()
            if hasattr(fsm, "is_processing_activated")
            else fsm.state == "processing_activated"
        )

    def _is_recording(self, session_id: str) -> bool:
        """檢查是否在錄音中

        使用 transitions 原生的 is_processing_recording() 方法
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return False
        return (
            fsm.is_processing_recording()
            if hasattr(fsm, "is_processing_recording")
            else fsm.state == "processing_recording"
        )

    def _is_transcribing(self, session_id: str) -> bool:
        """檢查是否在轉譯中

        使用 transitions 原生的 is_processing_transcribing() 方法
        """
        fsm = self._get_or_create_fsm(session_id)
        if not fsm:
            return False
        return (
            fsm.is_processing_transcribing()
            if hasattr(fsm, "is_processing_transcribing")
            else fsm.state == "processing_transcribing"
        )

    def _set_session_strategy(self, session_id: str, strategy: str):
        """設定 session 的策略模式"""
        self._session_strategies[session_id] = strategy

    # === Audio Receive Effect ===

    @create_effect(dispatch=False)
    def handle_receive_audio_chunk(self, action_stream):
        """處理接收音訊塊 - 轉換並存入時間戳隊列"""
        return action_stream.pipe(
            ofType(receive_audio_chunk),
            ops.do_action(self._process_audio_chunk),
            ops.catch(self._handle_audio_error),
        )

    def _process_audio_chunk(self, action):
        """處理音頻片段 - 使用 session 的音訊配置"""
        payload = action.payload
        session_id = payload.get("session_id")
        audio_data = payload.get("audio_data")

        # 記錄接收到的音訊格式（只記錄第一次）
        # import numpy as np
        # if not hasattr(self, '_first_audio_logged'):
        #     self._process_audio_chunk = {}
        # if session_id not in self._first_audio_logged:
        #     self._first_audio_logged[session_id] = True
        #     if isinstance(audio_data, (bytes, bytearray)):
        #         logger.info(f"📥 [EFFECT_RECEIVED] First audio received for {session_id}: {len(audio_data)} bytes")
        #     elif isinstance(audio_data, np.ndarray):
        #         logger.info(f"📥 [EFFECT_RECEIVED] First audio received for {session_id}: shape={audio_data.shape}, dtype={audio_data.dtype}")

        # 從 selector 取得 session 的音訊配置
        from src.store.main_store import store
        from src.store.sessions.sessions_selector import get_session_audio_config

        audio_config = get_session_audio_config(session_id)(store.state)

        if not audio_config:
            logger.error(f"Session {session_id} has no audio configuration!")
            logger.error(
                "Audio config must be set when session is created or via SET_AUDIO_METADATA"
            )
            return

        # 從 session 的音訊配置取得參數
        actual_sample_rate = audio_config.get("sample_rate")  # , 16000
        actual_channels = audio_config.get("channels")  # , 1
        actual_format = audio_config.get("format")  # , 'pcm_s16le'

        # # 只記錄第一次的配置
        # if not hasattr(self, '_first_config_logged'):
        #     self._first_config_logged = {}
        # if session_id not in self._first_config_logged:
        #     self._first_config_logged[session_id] = True
        #     logger.info(f"📋 [EFFECT_CONFIG] Session audio config for {session_id}: {actual_sample_rate}Hz, "
        #                 f"{actual_channels}ch, {actual_format}")

        # 獲取或初始化 session 狀態
        # 使用 FSM 狀態查詢，不再需要手動設置狀態
        # FSM 在創建時已經是 idle 狀態，start_listening 會轉換到 processing
        fsm = self._get_or_create_fsm(session_id)
        # 使用原生方法檢查是否在 processing 狀態（包含子狀態）
        if fsm and not (hasattr(fsm, "is_processing") and fsm.is_processing(allow_substates=True)):
            # 如果不在 processing 狀態，使用原生方法觸發 start_listening
            if fsm:
                old_state = fsm.state
                if hasattr(fsm, "start_listening"):
                    fsm.start_listening()
                else:
                    fsm.trigger("start_listening")
                logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")
            self._start_wake_word_monitoring(session_id)

        # 記錄轉換過程（只記錄第一次）
        # if not hasattr(self, '_first_convert_logged'):
        #     self._first_convert_logged = {}

        # # 如果採樣率不是 16000，需要轉換（ASR 需要 16kHz）
        if actual_sample_rate != 16000:
            #     if session_id not in self._first_convert_logged:
            #         self._first_convert_logged[session_id] = True
            #         logger.info(f"🔄 [EFFECT_CONVERT] Converting audio from {actual_sample_rate}Hz to 16000Hz for ASR")

            from src.service.audio_converter import audio_converter

            # 使用 audio_converter 服務進行採樣率轉換
            try:
                converted_audio = audio_converter.convert_audio(
                    audio_data,
                    source_sample_rate=actual_sample_rate,
                    source_channels=actual_channels,
                )
                # if session_id in self._first_convert_logged and self._first_convert_logged[session_id]:
                #     self._first_convert_logged[session_id] = False  # 標記已經記錄過
                #     if isinstance(converted_audio, np.ndarray):
                #         logger.info(f"✅ [EFFECT_CONVERTED] Audio converted: shape={converted_audio.shape}, dtype={converted_audio.dtype}")
                #     else:
                #         logger.info(f"✅ [EFFECT_CONVERTED] Audio converted: {len(converted_audio)} bytes")
            except Exception as e:
                logger.error(f"Failed to convert audio sample rate: {e}")
                logger.warning("Using original audio data - ASR may not work properly")
                converted_audio = audio_data
        else:
            converted_audio = audio_data
            # if session_id not in self._first_convert_logged:
            #     # self._first_convert_logged[session_id] = True
            #     logger.info(f"✅ [EFFECT_NO_CONVERT] Audio already at 16kHz, no conversion needed")

        # 推送到時間戳隊列（只記錄第一次）
        # if not hasattr(self, '_first_queue_logged'):
        #     self._first_queue_logged = {}
        timestamp = audio_queue.push(session_id, converted_audio)
        # if session_id not in self._first_queue_logged:
        #     self._first_queue_logged[session_id] = True
        #     logger.info(f"📤 [EFFECT->QUEUE] First audio pushed to queue at timestamp {timestamp:.3f}")

        # if timestamp > 0:
        #     logger.trace(f"Audio pushed to queue at {timestamp:.3f} for session {session_id}")

    # === Wake Word Detection ===

    def _start_wake_word_monitoring(self, session_id: str):
        """啟動喚醒詞監控線程 - 使用 OpenWakeWord 服務"""
        logger.info(f"🎤 Starting wake word monitoring for session {session_id}")

        # 確保 OpenWakeWord 已初始化
        if not openwakeword.is_initialized():
            openwakeword.initialize()

        # 使用 OpenWakeWord 服務的 start_listening 方法
        # 這會自動處理 BufferManager 和音訊分塊
        # 回調函數接收 WakewordDetection 物件
        success = openwakeword.start_listening(
            session_id=session_id,
            callback=lambda detection: self._on_wake_word_detected(
                session_id,
                f"{WakeActivateSource.KEYWORD}:{detection.keyword}",  # 傳遞 keyword 作為 source
                detection.timestamp,
                detection.confidence,
            ),
        )

        if success:
            logger.info(f"✅ Wake word monitoring started successfully for session {session_id}")
        else:
            logger.error(f"❌ Failed to start wake word monitoring for session {session_id}")

        # 不需要手動線程管理，OpenWakeWord 服務會處理

    def _on_wake_word_detected(
        self, session_id: str, source: str, timestamp: float, confidence: float
    ):
        """處理喚醒詞檢測到事件 - 使用現有錄音服務"""
        logger.info(
            f"✅ Wake word detected: '{source}' (confidence: {confidence:.3f}) at {timestamp:.3f} for session {session_id}"
        )

        # 使用原生方法觸發 FSM 狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        success = False
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "wake_activated"):
                success = fsm.wake_activated()
            else:
                success = fsm.trigger("wake_activated")
            if success:
                logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")
            else:
                logger.warning(f"❌ FSM: [{session_id}] Failed to activate from {old_state}")
        if not success:
            # 使用原生方法獲取當前狀態
            current_state = fsm.state if fsm else "unknown"
            valid_triggers = []
            if fsm:
                # 獲取可用的觸發器
                for trigger in fsm.machine.get_triggers(current_state):
                    valid_triggers.append(trigger)
            logger.warning(
                f"Failed to trigger 'wake_activated' for session {session_id}. "
                f"Current state: {current_state}, "
                f"Valid actions: {valid_triggers}"
            )
            # 在生產環境中可能不要 return，讓系統繼續運作
            # return

        # 記錄喚醒時間戳
        self._wake_word_timestamps[session_id] = timestamp

        # 計算預錄開始時間
        recording_start = max(0, timestamp - self.pre_roll_duration)
        self._recording_start_timestamps[session_id] = recording_start

        # FSM 已經通過 record_started trigger 轉換到 processing_recording 狀態
        # 不需要手動設置狀態

        # 清除 audio_queue 以避免喚醒詞干擾後續的 ASR
        # 這會清除所有之前的音訊，確保錄音從喚醒詞後開始
        # 這樣可以避免喚醒詞本身被包含在 ASR 轉譯中
        logger.info(f"🧹 清除 session {session_id} 的 audio_queue，避免喚醒詞干擾 ASR")
        audio_queue.clear(session_id)

        # 使用現有的 Recording 服務開始錄音
        recording_metadata = {
            "wake_time": timestamp,
            "pre_roll": self.pre_roll_duration,
            "recording_start": recording_start,
        }

        # 開始錄音服務（從喚醒詞時間戳開始讀取）
        # 從 store 取得音訊配置
        from src.store.main_store import store
        from src.store.sessions.sessions_selector import get_session_audio_config

        audio_config = get_session_audio_config(session_id)(store.state) or {}
        recording.start_recording(
            session_id=session_id,
            sample_rate=16000,  # 固定使用 16kHz，因為 audio_queue 中的音訊已統一轉換為 16kHz
            channels=1,  # 固定使用單聲道，因為轉換時已統一為單聲道
            format="int16",  # 固定使用 int16 格式
            filename=f"{session_id}_{int(timestamp * 1000)}",
            metadata=recording_metadata,
            start_timestamp=recording_start,  # 從預錄開始時間戳開始讀取
        )

        # 啟動 VAD 監控
        self._start_vad_monitoring(session_id)

        # Dispatch wake_activated action（包含時間戳）
        # 注意: wake_activated 的函數簽名是 (session_id, source)
        self.store.dispatch(wake_activated(session_id, source))  # 使用檢測到的關鍵字作為 source

        # 使用原生方法觸發 FSM 狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        if fsm and hasattr(fsm, "record_started"):
            old_state = fsm.state
            fsm.record_started()
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # Dispatch record_started action（包含時間戳和元數據）
        self.store.dispatch(
            record_started(
                {
                    "session_id": session_id,
                    "timestamp": recording_start,
                    "metadata": recording_metadata,
                }
            )
        )

        logger.info(
            f"Recording started from {recording_start:.3f} (pre-roll {self.pre_roll_duration}s)"
        )

    # === VAD Monitoring ===

    def _start_vad_monitoring(self, session_id: str):
        """啟動 VAD 監控線程 - 使用 Silero VAD 服務"""
        logger.info(f"👂 Starting VAD monitoring for session {session_id}")

        # 獲取喚醒詞時間戳（VAD 應從喚醒詞檢測時間開始）
        wake_timestamp = self._wake_word_timestamps.get(session_id)

        # 確保 Silero VAD 已初始化
        if not silero_vad.is_initialized():
            silero_vad._ensure_initialized()

        # VAD 狀態追蹤
        silence_start = None

        def vad_callback(result):
            """VAD 檢測回調 - 接收 VADResult 物件"""
            nonlocal silence_start
            current_time = time.time()

            # 從 VADResult 提取狀態和信心值
            from src.interface.vad import VADState

            is_speech = result.state == VADState.SPEECH
            confidence = result.probability

            if is_speech:
                # 偵測到語音時，停止任何正在運行的靜音計時器並重置狀態
                if silence_start is not None:
                    logger.info(
                        f"🎤 Speech detected (confidence: {confidence:.3f}), silence timer reset"
                    )
                    silence_start = None
                    # 停止靜音計時器
                    timer_service.stop_timer(session_id)
                else:
                    logger.debug(f"🎤 Speech continues (confidence: {confidence:.3f})")
                # 派發語音檢測 action
                self.store.dispatch(vad_speech_detected(session_id))
            else:
                # 只在錄音狀態下，且尚未開始計時的情況下啟動新的靜音計時器
                fsm = self._get_or_create_fsm(session_id)
                is_recording = (
                    fsm
                    and hasattr(fsm, "is_processing_recording")
                    and fsm.is_processing_recording()
                )
                if silence_start is None and is_recording:
                    silence_start = current_time
                    logger.info(
                        f"🤫 Silence started at {silence_start:.3f} (confidence: {confidence:.3f})"
                    )
                    # 派發靜音檢測 action（包含時間戳）
                    self.store.dispatch(
                        vad_silence_detected({"session_id": session_id, "timestamp": silence_start})
                    )
                    # 啟動靜音計時器
                    timer_service.start_countdown(
                        session_id,
                        self.silence_threshold,
                        lambda sid: self._on_silence_timeout(sid, current_time),
                    )

        # 使用 Silero VAD 服務的 start_listening 方法
        # 這會自動處理 BufferManager 和音訊分塊
        success = silero_vad.start_listening(
            session_id=session_id,
            callback=vad_callback,
            start_timestamp=wake_timestamp,  # 從喚醒詞時間戳開始讀取
        )

        if success:
            logger.info(f"✅ VAD monitoring started successfully for session {session_id}")
        else:
            logger.error(f"❌ Failed to start VAD monitoring for session {session_id}")

        # 不需要手動線程管理，Silero VAD 服務會處理

    def _on_silence_timeout(self, session_id: str, timestamp: float):
        """處理靜音超時事件 - 批量後處理音頻"""
        logger.info(f"⏰ Silence timeout at {timestamp:.3f} for session {session_id}")

        # 計算結束時間（加上尾部填充）
        recording_end = timestamp + self.tail_padding_duration

        # FSM 會通過 record_stopped trigger 轉換狀態
        # 不需要手動設置狀態

        # 停止錄音服務
        recording_info = recording.stop_recording(session_id)

        # 收集錄音數據進行後處理
        recording_start = self._recording_start_timestamps.get(session_id, 0)
        audio_chunks = audio_queue.get_audio_between_timestamps(
            session_id, recording_start, recording_end
        )

        # 使用原生方法觸發 FSM 狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        if fsm and hasattr(fsm, "record_stopped"):
            old_state = fsm.state
            fsm.record_stopped()
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # Dispatch record_stopped action（包含時間戳和錄音資訊）
        self.store.dispatch(
            record_stopped(
                {"session_id": session_id, "timestamp": recording_end, "info": recording_info or {}}
            )
        )

        # 批量後處理收集到的音頻 - 傳遞錄音檔案路徑
        recording_filepath = recording_info.get("filepath") if recording_info else None
        if recording_filepath:
            # 使用錄音檔案進行轉譯
            self._batch_process_audio(session_id, audio_chunks, recording_filepath)
        elif audio_chunks:
            # 沒有錄音檔案時使用音頻chunks
            self._batch_process_audio(session_id, audio_chunks, None)
        else:
            logger.warning(f"No audio collected for session {session_id}")

        # 清空 audio queue，準備下一次對話
        audio_queue.clear(session_id)
        logger.debug(f"Cleared audio queue for session {session_id}")

        # 不需要 reset，FSM 會自動從 processing_transcribing 回到 processing_activated
        # 但需要清理一些臨時狀態並重新啟動喚醒詞監控
        self._cleanup_for_next_round(session_id)

    def _batch_process_audio(
        self,
        session_id: str,
        audio_chunks: List[TimestampedAudio],
        recording_filepath: Optional[str] = None,
    ):
        """批量處理錄音數據（降噪、增強、ASR）

        Args:
            session_id: Session ID
            audio_chunks: 音頻片段列表
            recording_filepath: 錄音檔案路徑（如果有的話）
        """
        if recording_filepath:
            logger.info(f"Processing recording file for session {session_id}: {recording_filepath}")

            # 如果有錄音檔案，直接使用它進行 ASR 轉譯
            import os

            if os.path.exists(recording_filepath):
                self._transcribe_recording_file(session_id, recording_filepath)
                return
            else:
                logger.warning(
                    f"Recording file not found: {recording_filepath}, falling back to audio chunks"
                )

        if audio_chunks:
            logger.info(f"Processing {len(audio_chunks)} audio chunks for session {session_id}")

        # 不需要觸發 transcribe_started，因為這不是 FSM 中定義的事件
        # 直接派發 action 即可，現在包含檔案路徑

        # Dispatch transcribe_started action with file path
        self.store.dispatch(transcribe_started(session_id, recording_filepath))

        # 合併音頻片段
        combined_audio = self._combine_audio_chunks(audio_chunks)

        config = ConfigManager()

        # 步驟 1: 降噪（可選）
        if config.services.denoiser.enabled and HAS_DEEPFILTERNET:
            logger.info(f"Applying noise reduction for session {session_id}")
            try:
                # DeepFilterNet 自動處理採樣率轉換 (16k→48k→16k)
                denoised_audio, denoise_report = deepfilternet_denoiser.auto_denoise(
                    combined_audio, purpose="asr", sample_rate=16000
                )
                logger.debug(f"Denoising report: {denoise_report}")
            except Exception as e:
                logger.warning(f"Denoising failed: {e}, using original audio")
                denoised_audio = combined_audio
        else:
            if config.services.denoiser.enabled and not HAS_DEEPFILTERNET:
                logger.warning(
                    "DeepFilterNet not available (PyTorch not installed), skipping denoising"
                )
            denoised_audio = combined_audio

        # 步驟 2: 音頻增強（可選）
        if config.services.audio_enhancer.enabled:
            logger.info(f"Applying audio enhancement for session {session_id}")
            try:
                enhanced_audio, report = audio_enhancer.auto_enhance(
                    denoised_audio, purpose="asr"  # 正確的參數名稱是 purpose 而非 preset
                )
                logger.debug(f"Enhancement report: {report}")
            except Exception as e:
                logger.warning(f"Enhancement failed: {e}, using denoised audio")
                enhanced_audio = denoised_audio
        else:
            enhanced_audio = denoised_audio

        # 步驟 3: ASR 處理
        config = ConfigManager()
        # 將 enhanced_audio 從 bytes 轉換為 numpy array (如果需要)
        if isinstance(enhanced_audio, bytes):
            enhanced_audio = np.frombuffer(enhanced_audio, dtype=np.int16)

        # MVP 版本需要先將音訊寫入臨時檔案
        import tempfile
        import soundfile as sf
        import os

        # 建立臨時檔案用於轉譯
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_filename = temp_file.name
            try:
                # 確保音訊是 float32 格式 (-1.0 到 1.0)
                if enhanced_audio.dtype == np.int16:
                    audio_float32 = enhanced_audio.astype(np.float32) / 32768.0
                else:
                    audio_float32 = enhanced_audio

                # 寫入 WAV 檔案
                sf.write(temp_filename, audio_float32, 16000)
                logger.debug(f"Written temporary audio file: {temp_filename}")

                # 使用 lease_context 而非 lease（lease 返回 tuple，lease_context 是 context manager）
                result = None  # 初始化 result
                with self._provider_pool.lease_context(
                    session_id, timeout=config.providers.pool.lease_timeout
                ) as (provider, error):
                    if provider:
                        try:
                            # MVP 版本使用 transcribe_file 方法
                            result = provider.transcribe_file(temp_filename)
                            logger.info(f"Transcription result: {result.full_text[:100]}...")

                        except Exception as e:
                            logger.error(f"Transcription error: {e}")
                            self.store.dispatch(error_raised(session_id, str(e)))
                    else:
                        logger.error(f"Failed to get provider for session {session_id}: {error}")

            finally:
                # 清理臨時檔案
                try:
                    os.unlink(temp_filename)
                    logger.debug(f"Removed temporary audio file: {temp_filename}")
                except Exception as e:
                    logger.warning(f"Failed to remove temporary file {temp_filename}: {e}")

        # 使用原生方法觸發 FSM 狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        if fsm and hasattr(fsm, "transcribe_done"):
            old_state = fsm.state
            fsm.transcribe_done()
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # Dispatch transcribe_done action with result
        self.store.dispatch(transcribe_done(session_id, result))

        # Reset session 只在最後統一處理，避免重複調用
        # self._reset_session(session_id)  # 移到 handle_transcribe_done 統一處理

    def _transcribe_recording_file(self, session_id: str, filepath: str):
        """直接使用錄音檔案進行轉譯

        Args:
            session_id: Session ID
            filepath: 錄音檔案路徑
        """
        logger.info(f"Transcribing recording file: {filepath}")

        # Dispatch transcribe_started action
        self.store.dispatch(transcribe_started(session_id, filepath))

        config = ConfigManager()
        result = None  # 初始化 result

        try:
            # 使用 lease_context 取得 ASR provider
            with self._provider_pool.lease_context(
                session_id, timeout=config.providers.pool.lease_timeout
            ) as (provider, error):
                if provider:
                    try:
                        # 直接使用錄音檔案進行轉譯
                        result = provider.transcribe_file(filepath)

                        if result and result.full_text:
                            logger.info(f"✅ Transcription successful for {session_id}")
                            logger.block("📝 Transcription:", [result.full_text])

                        else:
                            logger.warning(f"Empty transcription result for {session_id}")

                    except Exception as e:
                        logger.error(f"Transcription error: {e}")
                        self.store.dispatch(error_raised(session_id, str(e)))
                else:
                    logger.error(f"Failed to get provider for session {session_id}: {error}")

        except Exception as e:
            logger.error(f"Failed to transcribe recording: {e}")
            self.store.dispatch(error_raised(session_id, str(e)))

        # 使用原生方法觸發 FSM 狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        if fsm and hasattr(fsm, "transcribe_done"):
            old_state = fsm.state
            fsm.transcribe_done()
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # Dispatch transcribe_done action with result
        self.store.dispatch(transcribe_done(session_id, result))

        # Reset session 只在最後統一處理，避免重複調用
        # self._reset_session(session_id)  # 移到 handle_transcribe_done 統一處理

    def _combine_audio_chunks(self, chunks: List[TimestampedAudio]) -> np.ndarray:
        """合併音頻片段"""
        if not chunks:
            return np.array([], dtype=np.int16)

        audio_parts = []
        for chunk in chunks:
            if isinstance(chunk.audio, np.ndarray):
                # 確保是正確的維度
                if chunk.audio.ndim == 0:
                    logger.warning(f"Skipping 0-dimensional array")
                    continue
                audio_parts.append(chunk.audio)
            elif hasattr(chunk.audio, "data"):
                # 如果是 AudioChunk 物件
                if isinstance(chunk.audio.data, bytes):
                    # 將 bytes 轉換為 numpy array
                    audio_array = np.frombuffer(chunk.audio.data, dtype=np.int16)
                    audio_parts.append(audio_array)
                elif isinstance(chunk.audio.data, np.ndarray):
                    if chunk.audio.data.ndim == 0:
                        logger.warning(f"Skipping 0-dimensional array")
                        continue
                    audio_parts.append(chunk.audio.data)
            else:
                # 處理其他格式
                if isinstance(chunk.audio, bytes):
                    audio_array = np.frombuffer(chunk.audio, dtype=np.int16)
                    audio_parts.append(audio_array)
                else:
                    logger.warning(f"Unknown audio format: {type(chunk.audio)}")

        if not audio_parts:
            logger.warning("No valid audio parts to concatenate")
            return np.array([], dtype=np.int16)

        return np.concatenate(audio_parts)

    def _cleanup_for_next_round(self, session_id: str):
        """轉譯完成後的輕量級清理，準備下一輪喚醒詞檢測

        與 _reset_session 不同，這個方法：
        - 不會重建 FSM（保持在 processing_activated 狀態）
        - 只清理必要的臨時狀態
        - 重新啟動喚醒詞監控
        """
        logger.info(f"🧹 Cleaning up for next round: session {session_id}")

        # 停止並清理計時器，避免舊計時器在新循環中觸發
        if timer_service.is_active(session_id):
            timer_service.stop_timer(session_id)
            logger.info(f"⏰ Stopped active timer for session {session_id}")

        # 清理時間戳記錄
        self._wake_word_timestamps.pop(session_id, None)
        self._recording_start_timestamps.pop(session_id, None)
        self._silence_start_timestamps.pop(session_id, None)

        # FSM 狀態會保持在 processing_activated，準備下一輪喚醒詞檢測
        # 不需要手動設置狀態

        # 重新啟動喚醒詞監控
        logger.info(f"✅ Restarting wake word monitoring for next round: session {session_id}")
        self._start_wake_word_monitoring(session_id)

    def _reset_session(self, session_id: str):
        """重置會話狀態"""
        logger.info(f"Resetting session {session_id}")

        # FSM 會處理狀態轉換，不需要手動設定
        # 重置 FSM 到初始狀態
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            # 使用原生方法重置 FSM 到 IDLE 狀態
            old_state = fsm.state
            if hasattr(fsm, "reset_session"):
                fsm.reset_session()
            else:
                fsm.trigger("reset_session")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # 停止並清理計時器，避免舊計時器在新循環中觸發
        if timer_service.is_active(session_id):
            timer_service.stop_timer(session_id)
            logger.info(f"⏰ Stopped active timer for session {session_id}")

        # 清理時間戳記錄
        self._wake_word_timestamps.pop(session_id, None)
        self._recording_start_timestamps.pop(session_id, None)
        self._silence_start_timestamps.pop(session_id, None)

        # 清空音訊佇列，讓下一輪開始是乾淨的
        logger.info(f"Clearing audio queue for session {session_id} for clean next round")
        audio_queue.clear(session_id)

        # 重新啟動喚醒詞監控
        self._start_wake_word_monitoring(session_id)

    def _handle_audio_error(self, error, caught):
        """處理音頻錯誤

        Args:
            error: 錯誤對象
            caught: 被捕獲的 observable
        """
        logger.error(f"Audio processing error: {error}")
        # 返回空的 observable 以防止錯誤傳播
        return rx.empty()

    # === Session Lifecycle Effects ===

    @create_effect(dispatch=False)
    def handle_session_expired(self, action_stream):
        """處理會話過期"""
        return action_stream.pipe(ofType(session_expired), ops.do_action(self._cleanup_session))

    @create_effect(dispatch=False)
    def handle_delete_session(self, action_stream):
        """處理刪除會話"""
        return action_stream.pipe(ofType(delete_session), ops.do_action(self._cleanup_session))

    def _cleanup_session(self, action):
        """清理會話資源"""
        session_id = action.payload

        logger.info(f"Cleaning up session {session_id}")

        # 停止錄音服務（如果正在錄音）
        if recording.is_recording(session_id):
            recording.stop_recording(session_id)

        # 停止所有監控線程
        self._stop_all_monitoring(session_id)

        # 停止並清理計時器
        if timer_service.is_active(session_id):
            timer_service.stop_timer(session_id)
            logger.info(f"⏰ Stopped timer for session {session_id} during cleanup")

        # 清理狀態
        # 狀態隨 FSM 實例一起被清理
        self._session_strategies.pop(session_id, None)
        self._wake_word_timestamps.pop(session_id, None)
        self._recording_start_timestamps.pop(session_id, None)
        self._silence_start_timestamps.pop(session_id, None)

        # 清理 FSM 實例
        self._fsm_instances.pop(session_id, None)

        # 清理音頻隊列
        audio_queue.clear(session_id)

    def _stop_all_monitoring(self, session_id: str):
        """停止所有監控線程"""
        logger.info(f"Stopping all monitoring for session {session_id}")

        # 停止 VAD 服務
        try:
            silero_vad.stop_listening(session_id)
            logger.debug(f"VAD monitoring stopped for session {session_id}")
        except Exception as e:
            logger.warning(f"Error stopping VAD monitoring for session {session_id}: {e}")

        # 停止 OpenWakeWord 服務
        try:
            openwakeword.stop_listening(session_id)
            logger.debug(f"OpenWakeWord monitoring stopped for session {session_id}")
        except Exception as e:
            logger.warning(f"Error stopping OpenWakeWord monitoring for session {session_id}: {e}")

        # 清理舊的線程追蹤（如果存在）
        if session_id in self._monitoring_threads:
            del self._monitoring_threads[session_id]

        # FSM 狀態會隨著 FSM 實例一起被刪除，不需要手動設定

    # === Reset Session Effect ===

    @create_effect(dispatch=False)
    def handle_reset_session(self, action_stream):
        """處理重置會話"""
        return action_stream.pipe(ofType(reset_session), ops.do_action(self._reset_session))

    def _reset_session(self, action):
        """重置會話狀態 - 保留 session 並重新啟動監控循環"""
        # Handle both action object and string
        if isinstance(action, str):
            session_id = action
        else:
            session_id = action.payload

        logger.info(f"Resetting session {session_id} for next round")

        # 停止當前的監控線程
        self._stop_all_monitoring(session_id)

        # 停止並清理計時器，避免舊計時器在新循環中觸發
        if timer_service.is_active(session_id):
            timer_service.stop_timer(session_id)
            logger.info(f"⏰ Stopped active timer for session {session_id} during reset")

        # FSM 狀態會保持在 processing_activated，準備下一輪喚醒詞檢測
        # 不需要手動設置狀態

        # 重置 FSM 狀態回到 listening
        if session_id in self._fsm_instances:
            # 重新創建 FSM 實例以確保乾淨的狀態
            strategy = self._session_strategies.get(session_id, Strategy.NON_STREAMING)
            del self._fsm_instances[session_id]
            fsm = self._get_or_create_fsm(session_id)
            if fsm:
                # FSM 創建後會在 IDLE 狀態，使用原生方法進入 PROCESSING 狀態
                logger.info(
                    f"🔄 FSM Reset: [{session_id}] Recreated FSM, initial state: {fsm.state}"
                )
                old_state = fsm.state
                success = False
                if hasattr(fsm, "start_listening"):
                    success = fsm.start_listening()
                else:
                    success = fsm.trigger("start_listening")
                if success:
                    logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")
                else:
                    logger.warning(
                        f"Failed to transition FSM to listening state for session {session_id}"
                    )
        else:
            # 如果沒有 FSM 實例，創建一個新的
            fsm = self._get_or_create_fsm(session_id)
            if fsm:
                logger.info(f"🆕 FSM Created: [{session_id}] Initial state: {fsm.state}")
                # 使用原生方法觸發 START_LISTENING 動作
                old_state = fsm.state
                if hasattr(fsm, "start_listening"):
                    fsm.start_listening()
                else:
                    fsm.trigger("start_listening")
                logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # 清理時間戳（但保留 session）
        self._wake_word_timestamps.pop(session_id, None)
        self._recording_start_timestamps.pop(session_id, None)
        self._silence_start_timestamps.pop(session_id, None)

        # 清空音訊佇列和 buffer，讓下一輪開始是乾淨的
        logger.info(f"Clearing audio queue and buffers for session {session_id}")
        audio_queue.clear(session_id)

        # 清理任何存在的 buffer（如果有的話）
        from src.core.buffer_manager import BufferManager

        # BufferManager 是基於 session 的，清空音訊佇列已經足夠

        # 重新啟動喚醒詞監控，開始新的循環
        logger.info(f"Restarting wake word monitoring for session {session_id}")
        self._start_wake_word_monitoring(session_id)

    # === Create Session Effect ===

    @create_effect(dispatch=False)
    def handle_create_session(self, action_stream):
        """處理創建會話"""
        return action_stream.pipe(ofType(create_session), ops.do_action(self._create_session))

    @classmethod
    def get_session_id_by_request_id(cls, request_id: str) -> Optional[str]:
        """根據 request_id 獲取對應的 session_id"""
        return cls._request_id_mapping.get(request_id)

    def _create_session(self, action):
        """創建新會話 - 處理副作用，不生成 session_id（由 reducer 生成）"""

        # 從 action 中取得策略和 request_id
        if hasattr(action.payload, "get"):
            # 新格式：payload 是 Map，包含 strategy, audio_config, request_id
            strategy = action.payload.get("strategy", Strategy.NON_STREAMING)
            audio_config = action.payload.get("audio_config")
            request_id = action.payload.get("request_id")
        else:
            # 舊格式：payload 直接是 strategy 字串
            strategy = action.payload if action.payload else Strategy.NON_STREAMING
            audio_config = None
            request_id = None

        # 從 state 獲取 reducer 創建的 session
        # Reducer 已經創建了 session，我們需要找到它
        state = self.store.state
        sessions_data = state.get("sessions", {})

        # 獲取真正的 sessions dict (SessionsState 內的 sessions 欄位)
        if hasattr(sessions_data, "get") and "sessions" in sessions_data:
            sessions = sessions_data.get("sessions", {})
        else:
            sessions = sessions_data

        # 找到最新創建的 session（有 request_id 的）
        session_id = None
        for sid, session in sessions.items():
            if hasattr(session, "get") and session.get("request_id") == request_id:
                session_id = sid
                break

        if not session_id:
            # 如果沒有 request_id，取最新的 session
            if sessions:
                session_id = list(sessions.keys())[-1]
            else:
                logger.error("No session found in state after reducer created it")
                return None

        logger.info(
            f"Processing session {session_id} with strategy {strategy} and request_id {request_id}"
        )

        # 設定策略（確保只存儲策略字串，而不是整個 payload）
        self._session_strategies[session_id] = strategy

        # 如果有 request_id，建立映射
        if request_id:
            self._request_id_mapping[request_id] = session_id
            logger.debug(f"Mapped request_id {request_id} to session_id {session_id}")

        # FSM 初始狀態就是 IDLE，不需要手動設定

        # 創建 FSM 實例（通過 _get_or_create_fsm 自動創建）
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            logger.debug(f"FSM created for session {session_id}, initial state: {fsm.state}")

        # 可以在這裡 dispatch 一個 session_created action 回到 reducer
        # 但目前看起來沒有這個 action

        return session_id

    # === Start Listen Effect ===

    @create_effect(dispatch=False)
    def handle_start_listening(self, action_stream):
        """處理開始監聽"""
        return action_stream.pipe(
            ofType(start_listening), ops.do_action(self._init_session_listening)
        )

    @create_effect(dispatch=False)
    def handle_wake_activated(self, action_stream):
        """處理喚醒詞激活"""
        return action_stream.pipe(ofType(wake_activated), ops.do_action(self._on_wake_activated))

    def _on_wake_activated(self, action):
        """處理喚醒詞激活事件"""
        payload = action.payload
        session_id = payload.get("session_id")
        source = payload.get("source", "unknown")

        logger.info(f"Wake word activated for session {session_id} from {source}")

        # 使用原生方法觸發 FSM 狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        success = False
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "wake_activated"):
                success = fsm.wake_activated()
            else:
                success = fsm.trigger(Action.WAKE_ACTIVATED)
            if success:
                logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")
            else:
                logger.warning(f"❌ FSM: [{session_id}] Failed to transition from {old_state}")

        if success:
            # 已修復: 現在完全通過 FSM 管理狀態
            # FSM 已經正確處理了狀態轉換到 processing_activated
            logger.info(f"✅ FSM transitioned to activated state for session {session_id}")
        else:
            logger.error(f"❌ Failed to transition FSM to activated state for session {session_id}")

    def _init_session_listening(self, action):
        """初始化會話監聽"""
        payload = action.payload
        session_id = payload.get("session_id")

        logger.info(f"Initializing listening for session {session_id}")

        # FSM 會在下面的 start_listening 轉換中處理狀態變更

        # 設定策略（如果還沒設定）
        if session_id not in self._session_strategies:
            # 從 payload 中取得 format 或其他資訊來決定策略
            # 目前預設使用 NON_STREAMING
            self._session_strategies[session_id] = Strategy.NON_STREAMING

        # 觸發 FSM 狀態轉換
        # 使用原生方法觸發狀態轉換
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "start_listening"):
                fsm.start_listening()
            else:
                fsm.trigger("start_listening")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # 啟動喚醒詞監控
        self._start_wake_word_monitoring(session_id)

    # === Error Handling Effects ===

    @create_effect(dispatch=False)
    def handle_error_occurred(self, action_stream):
        """處理錯誤發生"""
        return action_stream.pipe(ofType(error_occurred), ops.do_action(self._on_error_occurred))

    def _on_error_occurred(self, action):
        """處理錯誤事件"""
        session_id = action.payload

        logger.error(f"Error occurred for session {session_id}")

        # 觸發 FSM 狀態轉換到錯誤狀態
        # 使用原生方法觸發錯誤狀態
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "error_occurred"):
                fsm.error_occurred()
            else:
                fsm.trigger("error_occurred")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # 停止所有監控
        self._stop_all_monitoring(session_id)

        # FSM 已經在上面通過 error_occurred 轉換處理了狀態

    # === Wake Word Effects ===

    @create_effect(dispatch=False)
    def handle_wake_deactivated(self, action_stream):
        """處理喚醒詞停用"""
        return action_stream.pipe(
            ofType(wake_deactivated), ops.do_action(self._on_wake_deactivated)
        )

    def _on_wake_deactivated(self, action):
        """處理喚醒詞停用事件"""
        payload = action.payload
        session_id = payload.get("session_id")
        source = payload.get("source")

        logger.info(f"Wake word deactivated for session {session_id} from {source}")

        # 觸發 FSM 狀態轉換
        # 使用原生方法觸發喚醒詞停用
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "wake_deactivated"):
                fsm.wake_deactivated()
            else:
                fsm.trigger("wake_deactivated")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # 停止錄音
        if recording.is_recording(session_id):
            recording.stop_recording(session_id)

        # FSM 會通過 wake_deactivated 轉換自動回到 IDLE 狀態

    # === Upload Effects (for Batch Strategy) ===

    @create_effect(dispatch=False)
    def handle_upload_started(self, action_stream):
        """處理檔案上傳開始"""
        return action_stream.pipe(ofType(upload_started), ops.do_action(self._on_upload_started))

    def _on_upload_started(self, action):
        """處理檔案上傳開始事件"""
        payload = action.payload
        session_id = payload.get("session_id")
        file_name = payload.get("file_name")

        logger.info(f"Upload started for session {session_id}: {file_name}")

        # 確保策略是 BATCH
        if session_id not in self._session_strategies:
            self._session_strategies[session_id] = Strategy.BATCH

        # 觸發 FSM 狀態轉換
        # 使用原生方法觸發上傳開始
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "upload_started"):
                fsm.upload_started()
            else:
                fsm.trigger("upload_started")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

    @create_effect(dispatch=False)
    def handle_upload_completed(self, action_stream):
        """處理檔案上傳完成"""
        return action_stream.pipe(
            ofType(upload_completed), ops.do_action(self._on_upload_completed)
        )

    def _on_upload_completed(self, action):
        """處理檔案上傳完成事件"""
        payload = action.payload
        session_id = payload.get("session_id")
        file_name = payload.get("file_name")

        logger.info(f"Upload completed for session {session_id}: {file_name}")

        # 觸發 FSM 狀態轉換
        # 使用原生方法觸發上傳完成
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "upload_completed"):
                fsm.upload_completed()
            else:
                fsm.trigger("upload_completed")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

        # 開始轉錄處理 - 收集所有音訊並進行批次處理
        self._start_batch_transcription(session_id, file_name)

    def _start_batch_transcription(self, session_id: str, file_name: str):
        """開始批次轉譯處理

        Args:
            session_id: Session ID
            file_name: 檔案名稱（僅用於記錄）
        """
        logger.info(f"🎯 Starting batch transcription for session {session_id}")

        # 從 audio queue 收集所有音訊
        chunks = []
        queue_size = audio_queue.size(session_id)

        if queue_size > 0:
            # 使用 pull 方法一次取出所有音訊
            chunks = audio_queue.pull(session_id, count=queue_size)
            logger.info(f"📦 Collected {len(chunks)} audio chunks from queue")
        else:
            logger.warning(f"⚠️ No audio chunks in queue for session {session_id}")
            return

        # 將 AudioChunk 轉換為 TimestampedAudio 格式（如果需要的話）
        from src.core.audio_queue_manager import TimestampedAudio
        import time

        timestamped_chunks = []
        for i, chunk in enumerate(chunks):
            # 如果 chunk 已經是 TimestampedAudio，直接使用
            if hasattr(chunk, "timestamp") and hasattr(chunk, "data"):
                timestamped_chunks.append(chunk)
            else:
                # 否則創建一個簡單的 TimestampedAudio
                timestamped_chunks.append(
                    TimestampedAudio(timestamp=time.time() + i * 0.1, data=chunk)  # 簡單的時間戳
                )

        # 調用批次處理方法進行轉譯
        self._batch_process_audio(session_id, timestamped_chunks, None)

        logger.info(f"✅ Batch transcription initiated for session {session_id}")

    # === Stream Effects (for Streaming Strategy) ===

    @create_effect(dispatch=False)
    def handle_asr_stream_started(self, action_stream):
        """處理 ASR 串流開始"""
        return action_stream.pipe(
            ofType(asr_stream_started), ops.do_action(self._on_asr_stream_started)
        )

    def _on_asr_stream_started(self, action):
        """處理 ASR 串流開始事件"""
        session_id = action.payload

        logger.info(f"ASR stream started for session {session_id}")

        # 觸發 FSM 狀態轉換
        # 使用原生方法觸發 ASR 串流開始
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "asr_stream_started"):
                fsm.asr_stream_started()
            else:
                fsm.trigger("asr_stream_started")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")

    @create_effect(dispatch=False)
    def handle_asr_stream_stopped(self, action_stream):
        """處理 ASR 串流停止"""
        return action_stream.pipe(
            ofType(asr_stream_stopped), ops.do_action(self._on_asr_stream_stopped)
        )

    def _on_asr_stream_stopped(self, action):
        """處理 ASR 串流停止事件"""
        session_id = action.payload

        logger.info(f"ASR stream stopped for session {session_id}")

        # 觸發 FSM 狀態轉換
        # 使用原生方法觸發 ASR 串流停止
        fsm = self._get_or_create_fsm(session_id)
        if fsm:
            old_state = fsm.state
            if hasattr(fsm, "asr_stream_stopped"):
                fsm.asr_stream_stopped()
            else:
                fsm.trigger("asr_stream_stopped")
            logger.info(f"✅ FSM: [{session_id}] {old_state} → {fsm.state}")
