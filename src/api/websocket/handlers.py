"""
WebSocket 訊息處理器
簡化版本，只保留必要的功能
"""

from typing import Dict, Any, Optional
from datetime import datetime
from src.api.websocket.routes import routes


class MessageBuilder:
    """訊息建構器 - 簡化版本"""
    
    @staticmethod
    def build_welcome(connection_id: str) -> Dict[str, Any]:
        """建立歡迎訊息"""
        return {
            "type": routes["WELCOME"],
            "timestamp": datetime.now().isoformat(),
            "connection_id": connection_id,
            "version": "1.0"
        }
    
    @staticmethod
    def build_error(error: str, code: Optional[str] = None) -> Dict[str, Any]:
        """建立錯誤訊息"""
        return {
            "type": routes["ERROR"],
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "code": code
        }
    
    @staticmethod
    def build_control_response(command: str, status: str, 
                             data: Optional[Dict[str, Any]] = None,
                             error: Optional[str] = None) -> Dict[str, Any]:
        """建立控制回應訊息"""
        return {
            "type": "control_response",
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "status": status,
            "data": data,
            "error": error
        }
    
    @staticmethod
    def build_transcript(text: str, is_final: bool,
                        confidence: Optional[float] = None,
                        start_time: Optional[float] = None,
                        end_time: Optional[float] = None,
                        language: Optional[str] = None) -> Dict[str, Any]:
        """建立轉譯結果訊息"""
        message_type = routes["TRANSCRIPT"] if is_final else routes["TRANSCRIPT_PARTIAL"]
        
        return {
            "type": message_type,
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "is_final": is_final,
            "confidence": confidence,
            "start_time": start_time,
            "end_time": end_time,
            "language": language
        }
    
    @staticmethod
    def build_status(session_id: str, state: str, 
                    details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """建立狀態訊息"""
        return {
            "type": routes["STATUS"],
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "state": state,
            "details": details
        }


class MessageValidator:
    """訊息驗證器 - 簡化版本"""
    
    @staticmethod
    def validate_control_message(data: Dict[str, Any]) -> bool:
        """驗證控制訊息"""
        return "type" in data and "command" in data
    
    @staticmethod
    def validate_audio_metadata(data: Dict[str, Any]) -> bool:
        """驗證音訊元資料"""
        required_fields = ["format", "sample_rate", "channels"]
        return all(field in data for field in required_fields)