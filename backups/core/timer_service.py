"""
ASR Hub 計時器服務 - RxPy 響應式實現
整合原有 asyncio 和 RxPy 版本，提供統一的計時器管理
"""

from typing import Optional, Callable, Dict, Any
from reactivex import timer, operators as ops
from pystorex import ofType
from src.utils.logger import logger


class TimerService:
    """計時器服務 - 使用 RxPy 響應式編程
    
    提供統一的計時器管理功能，支援會話超時、錄音超時等
    每個 session 有獨立的 TimerService 實例，由 TimerManager 管理
    """
    
    def __init__(self, session_id: str):
        """初始化計時器服務
        
        Args:
            session_id: Session ID
        """
        self.session_id = session_id
        self.active_timers = {}  # 儲存活動的計時器訂閱
        logger.info(f"TimerService 初始化完成 - Session: {self.format_session_id(session_id)}")
    
    def format_session_id(self, session_id: str) -> str:
        """格式化 session ID
        
        Args:
            session_id: Session ID
            
        Returns:
            格式化後的 session ID
        """
        if session_id is None:
            return "[None]"
        return session_id[:8] if len(session_id) > 8 else session_id
    
    # ========== 通用計時器模式 (from sessions version) ==========
    
    def create_session_timeout(self, timeout_seconds: float = 300.0):
        """創建會話超時處理器
        
        Args:
            timeout_seconds: 超時秒數，預設 5 分鐘
            
        Returns:
            RxPy 操作符
        """
        def handle_session_timeout(action_stream):
            """處理會話超時"""
            # 延遲 import 避免循環引用
            from src.store.sessions.sessions_actions import (
                wake_triggered, start_recording, fsm_reset
            )
            
            return action_stream.pipe(
                ofType(wake_triggered, start_recording),
                ops.group_by(lambda a: a.payload["session_id"]),
                ops.flat_map(lambda group: group.pipe(
                    ops.debounce(timeout_seconds),
                    ops.do_action(lambda a: logger.warning(
                        f"⚠️ Session {self.format_session_id(a.payload['session_id'])} "
                        f"inactive for {timeout_seconds/60:.1f} minutes, resetting..."
                    )),
                    ops.map(lambda a: fsm_reset(a.payload["session_id"]))
                ))
            )
        
        return handle_session_timeout
    
    def create_recording_timeout(
        self, 
        get_session_state: Callable[[str], Optional[Dict[str, Any]]]
    ):
        """創建錄音超時處理器
        
        Args:
            get_session_state: 獲取 session 狀態的函數
            
        Returns:
            RxPy 操作符
        """
        def handle_recording_timeout(action_stream):
            """處理錄音超時"""
            # 延遲 import 避免循環引用
            from src.store.sessions.sessions_actions import (
                start_recording, start_asr_streaming
            )
            
            return action_stream.pipe(
                ofType(start_recording, start_asr_streaming),
                ops.flat_map(lambda action: self._handle_recording_timeout(
                    action, 
                    action_stream, 
                    get_session_state
                ))
            )
        
        return handle_recording_timeout
    
    def _handle_recording_timeout(
        self, 
        action, 
        action_stream,
        get_session_state: Callable[[str], Optional[Dict[str, Any]]]
    ):
        """內部處理錄音超時
        
        Args:
            action: 觸發的 action
            action_stream: Action stream
            get_session_state: 獲取 session 狀態的函數
            
        Returns:
            Observable stream
        """
        session_id = action.payload["session_id"]
        is_streaming = action.type == start_asr_streaming.type
        
        # 獲取超時設定
        timeout_sec = self._get_recording_timeout(
            session_id, 
            is_streaming, 
            get_session_state
        )
        
        # 增強超時警告日誌
        logger.block("Recording Timeout Warning", [
            f"🔴 RECORDING TIMEOUT STARTED - Session: {self.format_session_id(session_id)}...",
            f"⏱️  Duration: {timeout_sec}s",
            f"🎤 Type: {'Streaming' if is_streaming else 'Recording'}"
        ])
        
        # 選擇結束動作
        end_action = end_asr_streaming if is_streaming else end_recording
        
        return timer(timeout_sec).pipe(
            ops.map(lambda _: end_action(
                session_id,
                "timeout",
                timeout_sec
            )),
            ops.do_action(lambda a: logger.error(
                f"❌ RECORDING TIMEOUT TRIGGERED for session {self.format_session_id(session_id)} "
                f"after {timeout_sec}s"
            )),
            ops.take_until(action_stream.pipe(
                ofType(end_recording, end_asr_streaming),
                ops.filter(lambda a: a.payload.get("session_id") == session_id)
            ))
        )
    
    def _get_recording_timeout(
        self, 
        session_id: str, 
        is_streaming: bool,
        get_session_state: Callable[[str], Optional[Dict[str, Any]]]
    ) -> float:
        """獲取錄音超時設定
        
        Args:
            session_id: Session ID
            is_streaming: 是否為串流模式
            get_session_state: 獲取 session 狀態的函數
            
        Returns:
            超時秒數
        """
        # 從 Store 獲取 session 資訊
        session = get_session_state(session_id)
        
        if not session:
            timeout_sec = 30.0  # 預設 30 秒
            logger.warning(
                f"⚠️ Session {self.format_session_id(session_id)} not found, "
                "using default recording timeout"
            )
        else:
            # 延遲 import 避免循環引用
            from src.store.sessions.sessions_state import FSMStrategy, FSMStateEnum
            from src.store.sessions.fsm_config import get_strategy_config
            
            # 從 FSM 配置獲取超時設定
            strategy = session.get("strategy", FSMStrategy.NON_STREAMING)
            config = get_strategy_config(strategy)
            
            # 根據是錄音還是串流選擇對應的超時
            state_key = FSMStateEnum.STREAMING if is_streaming else FSMStateEnum.RECORDING
            timeout_ms = config.timeout_configs.get(state_key, 30000)
            timeout_sec = timeout_ms / 1000.0
        
        return timeout_sec
    
    def create_silence_timeout(
        self,
        get_session_state: Callable[[str], Optional[Dict[str, Any]]],
        default_timeout: float = 2.0
    ):
        """創建靜音超時處理器
        
        Args:
            get_session_state: 獲取 session 狀態的函數
            default_timeout: 預設超時秒數
            
        Returns:
            RxPy 操作符
        """
        def handle_silence_timeout(action_stream):
            """處理靜音超時"""
            return action_stream.pipe(
                ofType(start_recording),
                ops.flat_map(lambda action: self._handle_silence_timeout(
                    action, 
                    action_stream, 
                    get_session_state,
                    default_timeout
                ))
            )
        
        return handle_silence_timeout
    
    def _handle_silence_timeout(
        self, 
        action, 
        action_stream,
        get_session_state: Callable[[str], Optional[Dict[str, Any]]],
        default_timeout: float
    ):
        """內部處理靜音超時
        
        Args:
            action: 觸發的 action
            action_stream: Action stream
            get_session_state: 獲取 session 狀態的函數
            default_timeout: 預設超時秒數
            
        Returns:
            Observable stream
        """
        session_id = action.payload["session_id"]
        
        # 延遲 import 避免循環引用
        from src.store.sessions.sessions_actions import end_recording
        from src.store.sessions.sessions_state import FSMStrategy
        from src.store.sessions.fsm_config import get_strategy_config
        
        # 從配置獲取靜音超時設定
        session = get_session_state(session_id)
        if session:
            strategy = session.get("strategy", FSMStrategy.NON_STREAMING)
            config = get_strategy_config(strategy)
            
            # 獲取靜音超時設定
            silence_timeout = getattr(config, 'silence_timeout', default_timeout)
        else:
            silence_timeout = default_timeout
        
        logger.info(
            f"👂 Monitoring silence for session {self.format_session_id(session_id)} "
            f"(timeout: {silence_timeout}s)"
        )
        
        # 靜音計時器
        return timer(silence_timeout).pipe(
            ops.map(lambda _: end_recording(
                session_id,
                "silence_timeout",
                silence_timeout
            )),
            ops.do_action(lambda a: logger.info(
                f"🔇 Silence timeout triggered for session {self.format_session_id(session_id)} "
                f"after {silence_timeout}s"
            )),
            # 如果收到結束錄音或有新的音訊，取消計時器
            ops.take_until(action_stream.pipe(
                ofType(end_recording),
                ops.filter(lambda a: a.payload.get("session_id") == session_id)
            ))
        )
    
    # ========== 業務計時器 (from core version) ==========
    
    def create_awake_timer(self, timeout_seconds: float = 5.0):
        """創建喚醒視窗計時器
        
        Args:
            timeout_seconds: 超時秒數
            
        Returns:
            RxPy 操作符
        """
        def handle_awake_timeout(action_stream):
            """處理喚醒視窗超時"""
            return action_stream.pipe(
                ofType(wake_triggered),
                ops.filter(lambda a: a.payload.get("session_id") == self.session_id),
                ops.switch_map(lambda _: timer(timeout_seconds).pipe(
                    ops.map(lambda _: fsm_reset(self.session_id)),
                    ops.do_action(lambda _: logger.info(
                        f"⏰ Awake timeout for session {self.format_session_id(self.session_id)}"
                    )),
                    ops.take_until(action_stream.pipe(
                        ofType(start_recording, fsm_reset),
                        ops.filter(lambda a: a.payload.get("session_id") == self.session_id)
                    ))
                ))
            )
        
        return handle_awake_timeout
    
    def create_vad_silence_timer(self, timeout_seconds: float = 3.0):
        """創建 VAD 靜音計時器
        
        Args:
            timeout_seconds: 超時秒數
            
        Returns:
            RxPy 操作符
        """
        from src.store.sessions.sessions_actions import silence_started, speech_detected
        
        def handle_vad_silence(action_stream):
            """處理 VAD 靜音超時"""
            return action_stream.pipe(
                ofType(silence_started),
                ops.filter(lambda a: a.payload.get("session_id") == self.session_id),
                ops.switch_map(lambda _: timer(timeout_seconds).pipe(
                    ops.map(lambda _: end_recording(
                        self.session_id,
                        "vad_timeout", 
                        timeout_seconds
                    )),
                    ops.do_action(lambda _: logger.info(
                        f"🔇 VAD silence timeout for session {self.format_session_id(self.session_id)}"
                    )),
                    ops.take_until(action_stream.pipe(
                        ofType(speech_detected, end_recording),
                        ops.filter(lambda a: a.payload.get("session_id") == self.session_id)
                    ))
                ))
            )
        
        return handle_vad_silence
    
    def create_session_idle_timer(self, timeout_seconds: float = 600.0):
        """創建會話閒置計時器
        
        Args:
            timeout_seconds: 超時秒數，預設 10 分鐘
            
        Returns:
            RxPy 操作符
        """
        def handle_session_idle(action_stream):
            """處理會話閒置超時"""
            # 任何活動都會重置計時器
            activity_actions = [wake_triggered, start_recording, start_asr_streaming]
            
            return action_stream.pipe(
                ofType(*activity_actions),
                ops.filter(lambda a: a.payload.get("session_id") == self.session_id),
                ops.debounce(timeout_seconds),
                ops.map(lambda _: fsm_reset(self.session_id)),
                ops.do_action(lambda _: logger.warning(
                    f"💤 Session idle timeout for {self.format_session_id(self.session_id)}"
                ))
            )
        
        return handle_session_idle
    
    def cancel_all_timers(self):
        """取消所有計時器
        
        Note: 在 RxPy 中，計時器會在 subscription dispose 時自動取消
        這個方法主要用於相容性和顯式清理
        """
        self.active_timers.clear()
        logger.debug(f"All timers cancelled for session {self.format_session_id(self.session_id)}")
    
    def cleanup(self):
        """清理資源"""
        self.cancel_all_timers()
        logger.debug(f"TimerService cleanup completed for session {self.format_session_id(self.session_id)}")