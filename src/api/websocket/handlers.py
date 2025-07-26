"""
WebSocket 訊息處理器
定義訊息格式和處理邏輯
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import json


class MessageType(Enum):
    """WebSocket 訊息類型"""
    # 系統訊息
    WELCOME = "welcome"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    
    # 控制訊息
    CONTROL = "control"
    CONTROL_RESPONSE = "control_response"
    
    # 音訊訊息
    AUDIO = "audio"
    
    # 轉譯結果
    TRANSCRIPT = "transcript"
    TRANSCRIPT_PARTIAL = "transcript_partial"
    TRANSCRIPT_FINAL = "transcript_final"
    
    # 狀態更新
    STATUS = "status"
    STATUS_UPDATE = "status_update"
    

@dataclass
class WebSocketMessage:
    """WebSocket 訊息基礎類別"""
    type: str
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return asdict(self)
    
    def to_json(self) -> str:
        """轉換為 JSON 字串"""
        return json.dumps(self.to_dict())
    

@dataclass
class WelcomeMessage(WebSocketMessage):
    """歡迎訊息"""
    connection_id: str
    version: str = "1.0"
    

@dataclass
class ErrorMessage(WebSocketMessage):
    """錯誤訊息"""
    error: str
    code: Optional[str] = None
    

@dataclass
class ControlMessage(WebSocketMessage):
    """控制訊息"""
    command: str
    params: Optional[Dict[str, Any]] = None
    

@dataclass
class ControlResponseMessage(WebSocketMessage):
    """控制回應訊息"""
    command: str
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    

@dataclass
class AudioMessage(WebSocketMessage):
    """音訊訊息（用於描述音訊資料）"""
    format: str  # pcm, wav
    sample_rate: int
    channels: int
    encoding: str  # signed-integer, float32
    bits: int
    chunk_id: Optional[int] = None
    is_last: bool = False
    

@dataclass
class TranscriptMessage(WebSocketMessage):
    """轉譯結果訊息"""
    text: str
    is_final: bool
    confidence: Optional[float] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    language: Optional[str] = None
    

@dataclass
class StatusMessage(WebSocketMessage):
    """狀態訊息"""
    session_id: str
    state: str  # IDLE, LISTENING, BUSY
    details: Optional[Dict[str, Any]] = None
    

class MessageBuilder:
    """訊息建構器"""
    
    @staticmethod
    def build_welcome(connection_id: str) -> Dict[str, Any]:
        """建立歡迎訊息"""
        from datetime import datetime
        return WelcomeMessage(
            type=MessageType.WELCOME.value,
            timestamp=datetime.now().isoformat(),
            connection_id=connection_id
        ).to_dict()
    
    @staticmethod
    def build_error(error: str, code: Optional[str] = None) -> Dict[str, Any]:
        """建立錯誤訊息"""
        from datetime import datetime
        return ErrorMessage(
            type=MessageType.ERROR.value,
            timestamp=datetime.now().isoformat(),
            error=error,
            code=code
        ).to_dict()
    
    @staticmethod
    def build_control_response(command: str, status: str, 
                             data: Optional[Dict[str, Any]] = None,
                             error: Optional[str] = None) -> Dict[str, Any]:
        """建立控制回應訊息"""
        from datetime import datetime
        return ControlResponseMessage(
            type=MessageType.CONTROL_RESPONSE.value,
            timestamp=datetime.now().isoformat(),
            command=command,
            status=status,
            data=data,
            error=error
        ).to_dict()
    
    @staticmethod
    def build_transcript(text: str, is_final: bool,
                        confidence: Optional[float] = None,
                        start_time: Optional[float] = None,
                        end_time: Optional[float] = None,
                        language: Optional[str] = None) -> Dict[str, Any]:
        """建立轉譯結果訊息"""
        from datetime import datetime
        message_type = MessageType.TRANSCRIPT_FINAL if is_final else MessageType.TRANSCRIPT_PARTIAL
        
        return TranscriptMessage(
            type=message_type.value,
            timestamp=datetime.now().isoformat(),
            text=text,
            is_final=is_final,
            confidence=confidence,
            start_time=start_time,
            end_time=end_time,
            language=language
        ).to_dict()
    
    @staticmethod
    def build_status(session_id: str, state: str, 
                    details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """建立狀態訊息"""
        from datetime import datetime
        return StatusMessage(
            type=MessageType.STATUS_UPDATE.value,
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            state=state,
            details=details
        ).to_dict()
    

class MessageValidator:
    """訊息驗證器"""
    
    @staticmethod
    def validate_control_message(data: Dict[str, Any]) -> bool:
        """驗證控制訊息"""
        required_fields = ["type", "command"]
        return all(field in data for field in required_fields)
    
    @staticmethod
    def validate_audio_metadata(data: Dict[str, Any]) -> bool:
        """驗證音訊元資料"""
        required_fields = ["format", "sample_rate", "channels"]
        return all(field in data for field in required_fields)
    
    @staticmethod
    def validate_message_type(data: Dict[str, Any]) -> bool:
        """驗證訊息類型"""
        if "type" not in data:
            return False
            
        valid_types = [t.value for t in MessageType]
        return data["type"] in valid_types