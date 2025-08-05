"""
ASR Hub API 基礎類別
定義所有 API 實作的共同介面
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator
from src.utils.logger import logger
from src.core.session_manager import SessionManager
from src.core.exceptions import APIError


class APIResponse:
    """統一的 API 回應格式"""
    
    def __init__(self, 
                 status: str = "success",
                 data: Optional[Any] = None,
                 error: Optional[str] = None,
                 session_id: Optional[str] = None):
        """
        初始化 API 回應
        
        Args:
            status: 狀態（success, error）
            data: 回應資料
            error: 錯誤訊息
            session_id: Session ID
        """
        self.status = status
        self.data = data
        self.error = error
        self.session_id = session_id
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.session_id is not None:
            result["session_id"] = self.session_id
        return result


class APIBase(ABC):
    """
    API 基礎抽象類別
    所有 API 實作（HTTP SSE、WebSocket、gRPC 等）都需要繼承此類別
    """
    
    def __init__(self, config: Dict[str, Any], session_manager: SessionManager):
        """
        初始化 API
        
        Args:
            config: API 配置
            session_manager: Session 管理器
        """
        self.config = config
        self.session_manager = session_manager
        self.logger = logger
        self._running = False
    
    @abstractmethod
    async def start(self):
        """啟動 API 服務"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止 API 服務"""
        pass
    
    @abstractmethod
    async def handle_control_command(self, 
                                   command: str, 
                                   session_id: str, 
                                   params: Optional[Dict[str, Any]] = None) -> APIResponse:
        """
        處理控制指令
        
        Args:
            command: 指令名稱（start, stop, status, busy_start, busy_end）
            session_id: Session ID
            params: 額外參數
            
        Returns:
            API 回應
        """
        pass
    
    @abstractmethod
    async def handle_transcribe(self, 
                              session_id: str, 
                              audio_data: bytes,
                              params: Optional[Dict[str, Any]] = None) -> APIResponse:
        """
        處理單次轉譯請求
        
        Args:
            session_id: Session ID
            audio_data: 音訊資料
            params: 額外參數
            
        Returns:
            API 回應，包含轉譯結果
        """
        pass
    
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
        session = self.session_manager.get_session(session_id)
        return session is not None
    
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
        from src.models.audio import AudioFormat, AudioEncoding
        
        if not params:
            raise APIError("缺少音訊參數")
        
        # 必要參數檢查
        required_params = ["sample_rate", "channels", "format", "encoding", "bits_per_sample"]
        missing_params = [p for p in required_params if p not in params]
        
        if missing_params:
            raise APIError(f"缺少必要的音訊參數：{', '.join(missing_params)}")
        
        validated = {}
        
        # 驗證 sample_rate
        valid_rates = [8000, 16000, 22050, 24000, 32000, 44100, 48000]
        if params["sample_rate"] not in valid_rates:
            raise APIError(f"不支援的取樣率：{params['sample_rate']}，支援的取樣率：{valid_rates}")
        validated["sample_rate"] = params["sample_rate"]
        
        # 驗證 channels
        if params["channels"] not in [1, 2]:
            raise APIError(f"不支援的聲道數：{params['channels']}，支援單聲道(1)或立體聲(2)")
        validated["channels"] = params["channels"]
        
        # 驗證 format
        try:
            validated["format"] = AudioFormat(params["format"])
        except ValueError:
            valid_formats = [f.value for f in AudioFormat]
            raise APIError(f"不支援的音訊格式：{params['format']}，支援的格式：{valid_formats}")
        
        # 驗證 encoding
        try:
            validated["encoding"] = AudioEncoding(params["encoding"])
        except ValueError:
            valid_encodings = [e.value for e in AudioEncoding]
            raise APIError(f"不支援的編碼格式：{params['encoding']}，支援的編碼：{valid_encodings}")
        
        # 驗證 bits_per_sample
        valid_bits = [8, 16, 24, 32]
        if params["bits_per_sample"] not in valid_bits:
            raise APIError(f"不支援的位元深度：{params['bits_per_sample']}，支援的位元深度：{valid_bits}")
        validated["bits_per_sample"] = params["bits_per_sample"]
        
        return validated
    
    def is_running(self) -> bool:
        """檢查 API 服務是否正在運行"""
        return self._running