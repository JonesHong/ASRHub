"""
ASR Hub API 基礎類別
定義所有 API 實作的共同介面
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from src.utils.logger import logger
from src.store import get_global_store
from src.store.sessions.sessions_selectors import session_exists, get_session
from src.core.exceptions import APIError
from src.config.manager import ConfigManager

# 模組級變數
config_manager = ConfigManager()
store = get_global_store()


class APIResponse:
    """統一的 API 回應格式"""
    
    def __init__(self, 
                 status: str = "success",
                 data: Optional[Any] = None,
                 error: Optional[str] = None,
                 session_id: Optional[str] = None,
                 timestamp: Optional[datetime] = None):
        """
        初始化 API 回應
        
        Args:
            status: 狀態（success, error）
            data: 回應資料
            error: 錯誤訊息
            session_id: Session ID
            timestamp: 時間戳記
        """
        self.status = status
        self.data = data
        self.error = error
        self.session_id = session_id
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "status": self.status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data": self.data,
            "error": self.error,
            "session_id": self.session_id
        }
        return result


class APIBase(ABC):
    """
    API 基礎抽象類別
    所有 API 實作（HTTP SSE、WebSocket、gRPC 等）都需要繼承此類別
    """
    
    def __init__(self):
        """
        初始化 API
        """
        self._running = False
    
    @abstractmethod
    async def start(self):
        """啟動 API 服務"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止 API 服務"""
        pass
    
    async def handle_control_command(self, 
                                   command: str, 
                                   session_id: str, 
                                   params: Optional[Dict[str, Any]] = None) -> APIResponse:
        """
        處理控制指令 - 純事件驅動實現
        
        Args:
            command: 指令名稱（start, stop, status, wake, reset）
            session_id: Session ID
            params: 額外參數
            
        Returns:
            API 回應
        """
        from src.store.sessions import sessions_actions
        from src.store.sessions import get_session, get_session_transcription
        from src.store.sessions import FSMStrategy
        import asyncio
        
        # 驗證 session
        if not self.validate_session(session_id):
            return self.create_error_response("Session not found", session_id)
        
        # 定義命令映射表
        command_map = {
            "start": lambda: store.dispatch(
                sessions_actions.start_recording(
                    session_id, 
                    strategy=params.get("strategy", FSMStrategy.NON_STREAMING)
                )
            ),
            "stop": lambda: store.dispatch(
                sessions_actions.end_recording(
                    session_id, 
                    trigger="api", 
                    duration=0
                )
            ),
            "wake": lambda: store.dispatch(
                sessions_actions.wake_triggered(
                    session_id, 
                    confidence=1.0, 
                    trigger="api"
                )
            ),
            "reset": lambda: store.dispatch(
                sessions_actions.fsm_reset(session_id)
            ),
        }
        
        # 特殊處理 status 命令（不需要分發 action）
        if command == "status":
            state = store.state
            session = get_session(session_id)(state)
            if session:
                return self.create_success_response({
                    "state": session.get("state", "IDLE"),
                    "fsm_state": str(session.get("fsm_state", "IDLE")),
                    "strategy": str(session.get("strategy", "NON_STREAMING"))
                }, session_id)
            else:
                return self.create_error_response("Session not found", session_id)
        
        # 執行命令
        if command in command_map:
            command_map[command]()
            
            # 特殊處理 stop 命令 - 等待轉譯結果
            if command == "stop":
                result = await self._wait_for_transcription_result(session_id)
                if result:
                    return self.create_success_response(result, session_id)
                else:
                    return self.create_success_response({"message": "Recording stopped"}, session_id)
            
            return self.create_success_response({"message": f"Command '{command}' executed"}, session_id)
        else:
            return self.create_error_response(f"Unknown command: {command}", session_id)
    
    async def _wait_for_transcription_result(self, session_id: str, timeout: float = 5.0):
        """
        等待轉譯結果
        
        Args:
            session_id: Session ID
            timeout: 超時時間（秒）
            
        Returns:
            轉譯結果或 None
        """
        from src.store.sessions import get_session_transcription, clear_transcript
        import asyncio
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            state = store.state
            result = get_session_transcription(session_id)(state)
            
            if result:
                # 清除結果避免重複讀取
                store.dispatch(clear_transcript(session_id))
                return result
            
            # 短暫等待
            await asyncio.sleep(0.1)
        
        logger.warning(f"等待轉譯結果超時 - Session: {session_id}")
        return None
    
    async def handle_transcribe(self, 
                              session_id: str, 
                              audio_data: bytes,
                              params: Optional[Dict[str, Any]] = None) -> APIResponse:
        """
        處理單次轉譯請求 - 純事件驅動實現
        
        Args:
            session_id: Session ID
            audio_data: 音訊資料
            params: 額外參數
            
        Returns:
            API 回應，包含轉譯結果
        """
        from src.store.sessions import sessions_actions, get_session
        from src.store.sessions import FSMStrategy
        from src.core.audio_queue_manager import get_audio_queue_manager
        
        # 驗證 session
        if not self.validate_session(session_id):
            return self.create_error_response("Session not found", session_id)
        
        # 獲取 session 策略
        state = store.state
        session = get_session(session_id)(state)
        if not session:
            return self.create_error_response("Session not found", session_id)
        
        strategy = session.get("strategy", FSMStrategy.NON_STREAMING)
        audio_queue_manager = get_audio_queue_manager()
        
        # 根據策略處理
        if strategy == FSMStrategy.BATCH:
            # BATCH 策略：推送音訊並立即處理
            await audio_queue_manager.push(session_id, audio_data)
            store.dispatch(sessions_actions.upload_file(session_id))
            
            # 等待結果
            result = await self._wait_for_transcription_result(session_id)
            if result:
                return self.create_success_response(result, session_id)
            else:
                return self.create_error_response("Transcription failed", session_id)
                
        elif strategy == FSMStrategy.NON_STREAMING:
            # NON_STREAMING 策略：累積音訊，等待 stop 命令
            await audio_queue_manager.push(session_id, audio_data)
            store.dispatch(sessions_actions.audio_chunk_received(
                session_id,
                chunk_size=len(audio_data)
            ))
            
            return self.create_success_response({
                "status": "buffered",
                "chunk_size": len(audio_data),
                "message": "Audio chunk buffered, waiting for stop command"
            }, session_id)
            
        elif strategy == FSMStrategy.STREAMING:
            # STREAMING 策略：暫不支援
            return self.create_error_response(
                "STREAMING mode not supported in synchronous API", 
                session_id
            )
        else:
            return self.create_error_response(
                f"Unknown strategy: {strategy}", 
                session_id
            )
    
    @abstractmethod
    async def handle_transcribe_stream(self, 
                                     session_id: str,
                                     audio_stream: AsyncGenerator[bytes, None],
                                     params: Optional[Dict[str, Any]] = None) -> AsyncGenerator[APIResponse, None]:
        """
        處理串流轉譯請求
        
        Args:
            session_id: Session ID
            audio_stream: 音訊串流
            params: 額外參數
            
        Yields:
            串流 API 回應
        """
        pass
    
    def validate_session(self, session_id: str) -> bool:
        """
        驗證 Session 是否有效
        
        Args:
            session_id: Session ID
            
        Returns:
            是否有效
        """
        # 使用 selector 檢查 session 是否存在
        state = store.state if store else None
        return session_exists(session_id)(state) if state else False
    
    def create_error_response(self, error_msg: str, session_id: Optional[str] = None) -> APIResponse:
        """
        建立錯誤回應
        
        Args:
            error_msg: 錯誤訊息
            session_id: Session ID
            
        Returns:
            錯誤回應
        """
        return APIResponse(
            status="error",
            error=error_msg,
            session_id=session_id
        )
    
    def create_success_response(self, data: Any, session_id: Optional[str] = None) -> APIResponse:
        """
        建立成功回應
        
        Args:
            data: 回應資料
            session_id: Session ID
            
        Returns:
            成功回應
        """
        return APIResponse(
            status="success",
            data=data,
            session_id=session_id
        )
    
    async def validate_audio_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證音訊參數
        
        Args:
            params: 參數字典
            
        Returns:
            驗證後的參數
            
        Raises:
            APIError: 如果參數無效或缺少必要參數
        """
        from src.audio import AudioContainerFormat, AudioEncoding
        
        if not params:
            raise APIError("Missing audio parameters")
        
        # 提供預設值
        default_params = {
            "format": "pcm",
            "encoding": "linear16",
            "bits_per_sample": 16
        }
        
        # 合併預設值
        merged_params = {**default_params, **params}
        
        # 必要參數檢查 (只檢查必須由使用者提供的參數)
        required_params = ["sample_rate", "channels"]
        missing_params = [p for p in required_params if p not in params]
        
        if missing_params:
            raise APIError(f"Missing required parameters: {', '.join(missing_params)}")
        
        validated = {}
        
        # 驗證 sample_rate
        valid_rates = [8000, 16000, 22050, 24000, 32000, 44100, 48000]
        if merged_params["sample_rate"] not in valid_rates:
            raise APIError(f"Invalid sample_rate: {merged_params['sample_rate']}")
        validated["sample_rate"] = merged_params["sample_rate"]
        
        # 驗證 channels
        if merged_params["channels"] not in [1, 2]:
            raise APIError(f"Invalid channels: {merged_params['channels']}")
        validated["channels"] = merged_params["channels"]
        
        # 驗證 format
        try:
            validated["format"] = AudioContainerFormat(merged_params["format"])
        except ValueError:
            raise APIError(f"Invalid format: {merged_params['format']}")
        
        # 驗證 encoding
        try:
            validated["encoding"] = AudioEncoding(merged_params["encoding"])
        except ValueError:
            raise APIError(f"Invalid encoding: {merged_params['encoding']}")
        
        # 驗證 bits_per_sample
        valid_bits = [8, 16, 24, 32]
        if merged_params["bits_per_sample"] not in valid_bits:
            raise APIError(f"Invalid bits_per_sample: {merged_params['bits_per_sample']}")
        validated["bits_per_sample"] = merged_params["bits_per_sample"]
        
        return validated
    
    @property
    def running(self) -> bool:
        """檢查 API 服務是否正在運行"""
        return self._running
    
    def is_running(self) -> bool:
        """檢查 API 服務是否正在運行"""
        return self._running