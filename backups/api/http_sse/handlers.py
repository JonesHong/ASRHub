"""
ASR Hub HTTP SSE 處理器
處理各種 SSE 事件和請求
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from src.utils.logger import logger
from src.audio import AudioChunk, AudioContainerFormat, AudioEncoding
from src.models.transcript import TranscriptSegment, TranscriptResult
from src.core.exceptions import APIError, ValidationError


class BaseHandler:
    """所有處理器的基礎類別"""
    
    @staticmethod
    def create_timestamp() -> str:
        """產生 ISO 格式時間戳記"""
        return datetime.now().isoformat()
    
    @staticmethod
    def validate_dict_field(data: Dict[str, Any], field_name: str, required: bool = False) -> Dict[str, Any]:
        """驗證字典欄位"""
        value = data.get(field_name, {})
        if required and not value:
            raise ValidationError(f"缺少必要的 {field_name}")
        if value and not isinstance(value, dict):
            raise ValidationError(f"{field_name} 必須是字典")
        return value
    
    @staticmethod
    def validate_numeric_field(data: Dict[str, Any], field_name: str, 
                              min_value: float = None, required: bool = False) -> Optional[float]:
        """驗證數值欄位"""
        if field_name not in data:
            if required:
                raise ValidationError(f"缺少必要的 {field_name}")
            return None
        
        try:
            value = float(data[field_name])
            if min_value is not None and value < min_value:
                raise ValidationError(f"{field_name} 必須大於 {min_value}")
            return value
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} 必須是數字")
    
    def create_event(self, event_type: str, **kwargs) -> Dict[str, Any]:
        """建立基礎事件結構"""
        return {
            "type": event_type,
            "timestamp": self.create_timestamp(),
            **kwargs
        }


class SSEEventHandler(BaseHandler):
    """SSE 事件處理器"""
    
    def format_control_event(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """格式化控制事件"""
        return self.create_event("control", command=command, params=params)
    
    def format_transcript_event(self, segment: TranscriptSegment, session_id: str,
                              sequence_number: int) -> Dict[str, Any]:
        """格式化轉譯事件"""
        return self.create_event(
            "transcript",
            session_id=session_id,
            sequence=sequence_number,
            segment=segment.to_dict()
        )
    
    def format_error_event(self, error_type: str, message: str,
                         details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """格式化錯誤事件"""
        event = self.create_event("error", error_type=error_type, message=message)
        if details:
            event["details"] = details
        return event
    
    def format_status_event(self, status: str, info: Dict[str, Any]) -> Dict[str, Any]:
        """格式化狀態事件"""
        return self.create_event("status", status=status, info=info)
    
    def format_progress_event(self, processed: int, total: int,
                            message: Optional[str] = None) -> Dict[str, Any]:
        """格式化進度事件"""
        event = self.create_event(
            "progress",
            processed=processed,
            total=total,
            percentage=round((processed / total * 100) if total > 0 else 0, 2)
        )
        if message:
            event["message"] = message
        return event
    
    def format_wake_event(self, wake_data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化喚醒詞事件"""
        return {
            "type": "wake_word",
            "source": wake_data.get("source", "wake_word"),
            "model": wake_data.get("detection", {}).get("model"),
            "score": wake_data.get("detection", {}).get("score"),
            "timestamp": wake_data.get("timestamp", self.create_timestamp())
        }
    
    def format_state_change_event(self, old_state: str, new_state: str,
                                 event_type: Optional[str] = None) -> Dict[str, Any]:
        """格式化狀態變更事件"""
        return self.create_event(
            "state_change",
            old_state=old_state,
            new_state=new_state,
            event=event_type
        )


class AudioRequestHandler(BaseHandler):
    """音訊請求處理器"""
    
    # 支援的音訊格式
    SUPPORTED_FORMATS = {
        "audio/wav", "audio/x-wav", "audio/mp3", "audio/mpeg",
        "audio/flac", "audio/ogg", "audio/webm", "application/octet-stream"
    }
    
    # 音訊格式映射
    FORMAT_MAP = {
        "pcm": AudioContainerFormat.PCM,
        "wav": AudioContainerFormat.WAV,
        "mp3": AudioContainerFormat.MP3,
        "flac": AudioContainerFormat.FLAC,
        "ogg": AudioContainerFormat.OGG,
        "webm": AudioContainerFormat.WEBM
    }
    
    # 標頭映射
    HEADER_MAPPING = {
        "sample_rate": (["X-Audio-Sample-Rate", "X-Sample-Rate"], int),
        "channels": (["X-Audio-Channels", "X-Channels"], int),
        "format": (["X-Audio-Format", "X-Format"], str),
        "encoding": (["X-Audio-Encoding", "X-Encoding"], str),
        "bits_per_sample": (["X-Audio-Bits", "X-Audio-Bits-Per-Sample", "X-Bits-Per-Sample"], int)
    }
    
    def validate_audio_upload(self, content_type: str, content_length: int,
                            max_size: int = 10 * 1024 * 1024) -> None:
        """驗證音訊上傳請求"""
        if content_type not in self.SUPPORTED_FORMATS:
            raise ValidationError(f"不支援的音訊格式：{content_type}")
        
        if content_length > max_size:
            raise ValidationError(
                f"音訊檔案太大：{content_length} bytes (最大：{max_size} bytes)"
            )
    
    def parse_audio_params(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """從請求標頭解析音訊參數"""
        params = {}
        
        for param_name, (header_names, converter) in self.HEADER_MAPPING.items():
            value = None
            for header_name in header_names:
                if header_name in headers:
                    raw_value = headers[header_name]
                    try:
                        value = converter(raw_value) if converter == int else raw_value.lower()
                    except ValueError:
                        raise ValidationError(f"無效的 {param_name}：{raw_value}")
                    break
            
            if value is None:
                raise ValidationError(f"缺少必要的音訊參數 header：{param_name}")
            params[param_name] = value
        
        return params
    
    def create_audio_chunk(self, data: bytes, params: Dict[str, Any],
                         sequence_number: int = 0) -> AudioChunk:
        """建立音訊資料塊"""
        audio_format = self.FORMAT_MAP.get(params["format"], AudioContainerFormat.PCM)
        
        return AudioChunk(
            data=data,
            sample_rate=params["sample_rate"],
            channels=params["channels"],
            format=audio_format,
            encoding=AudioEncoding.LINEAR16,
            bits_per_sample=params.get("bits_per_sample", 16),
            sequence_number=sequence_number
        )


class SessionRequestHandler(BaseHandler):
    """Session 請求處理器"""
    
    # 有效的配置選項
    VALID_OPERATORS = [
        "vad", "denoise", "audio_formatter", "voice_separation",
        "recording", "openwakeword", "wakeword"
    ]
    
    VALID_PROVIDERS = [
        "whisper", "funasr", "vosk", "google_stt", "openai"
    ]
    
    def validate_session_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證建立 Session 的請求"""
        validated = {
            "metadata": self.validate_dict_field(data, "metadata"),
            "pipeline_config": self._validate_pipeline_config(data),
            "provider_config": self._validate_provider_config(data)
        }
        
        # 驗證可選的數值欄位
        if "wake_timeout" in data:
            validated["wake_timeout"] = self.validate_numeric_field(
                data, "wake_timeout", min_value=0
            )
        
        if "priority" in data:
            validated["priority"] = int(
                self.validate_numeric_field(data, "priority") or 0
            )
        
        return validated
    
    def _validate_pipeline_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證 Pipeline 配置"""
        config = self.validate_dict_field(data, "pipeline_config")
        
        if "operators" in config:
            operators = config["operators"]
            if not isinstance(operators, list):
                raise ValidationError("operators 必須是列表")
            
            for op in operators:
                if op not in self.VALID_OPERATORS:
                    raise ValidationError(f"無效的 operator：{op}")
        
        return config
    
    def _validate_provider_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證 Provider 配置"""
        config = self.validate_dict_field(data, "provider_config")
        
        if "provider" in config:
            if config["provider"] not in self.VALID_PROVIDERS:
                raise ValidationError(f"無效的 provider：{config['provider']}")
        
        return config
    
    def format_session_info(self, session: Any) -> Dict[str, Any]:
        """格式化 Session 資訊"""
        def safe_isoformat(dt):
            return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
        
        return {
            "id": session.id,
            "state": session.state,
            "created_at": safe_isoformat(session.created_at),
            "last_activity": safe_isoformat(session.last_activity),
            "metadata": session.metadata,
            "pipeline_config": session.pipeline_config,
            "provider_config": session.provider_config
        }


class TranscriptResponseHandler(BaseHandler):
    """轉譯回應處理器"""
    
    def format_streaming_response(self, segments: List[TranscriptSegment],
                                session_id: str,
                                include_alternatives: bool = False) -> List[Dict[str, Any]]:
        """格式化串流轉譯回應"""
        return [
            self._format_segment(segment, session_id, i)
            for i, segment in enumerate(segments)
        ]
    
    def _format_segment(self, segment: TranscriptSegment, session_id: str,
                       sequence: int) -> Dict[str, Any]:
        """格式化單個轉譯片段"""
        response = {
            "session_id": session_id,
            "sequence": sequence,
            "text": segment.text,
            "is_final": segment.is_final,
            "confidence": segment.confidence,
            "start_time": segment.start_time,
            "end_time": segment.end_time
        }
        
        # 添加可選欄位
        if segment.words:
            response["words"] = [word.to_dict() for word in segment.words]
        if segment.language:
            response["language"] = segment.language
        if segment.speaker is not None:
            response["speaker"] = segment.speaker
        
        return response
    
    def format_final_response(self, result: TranscriptResult) -> Dict[str, Any]:
        """格式化最終轉譯結果"""
        response = result.to_dict()
        response["statistics"] = {
            "total_segments": len(result.segments),
            "total_words": result.get_word_count(),
            "average_confidence": result.confidence,
            "processing_time": result.processing_time
        }
        return response
    
    def merge_partial_results(self, partials: List[TranscriptSegment]) -> Optional[TranscriptSegment]:
        """合併部分結果"""
        if not partials:
            return None
        
        # 合併文字
        merged_text = " ".join(seg.text for seg in partials)
        
        # 計算時間範圍
        start_time = min(seg.start_time for seg in partials)
        end_time = max(seg.end_time for seg in partials)
        
        # 計算加權平均信心分數
        total_duration = sum(seg.end_time - seg.start_time for seg in partials)
        if total_duration > 0:
            weighted_confidence = sum(
                seg.confidence * (seg.end_time - seg.start_time)
                for seg in partials
            )
            avg_confidence = weighted_confidence / total_duration
        else:
            avg_confidence = sum(seg.confidence for seg in partials) / len(partials)
        
        # 合併詞資訊
        all_words = []
        for seg in partials:
            if seg.words:
                all_words.extend(seg.words)
        
        return TranscriptSegment(
            text=merged_text,
            start_time=start_time,
            end_time=end_time,
            confidence=avg_confidence,
            words=all_words if all_words else None,
            is_final=True
        )


class WakeWordRequestHandler(BaseHandler):
    """喚醒詞請求處理器"""
    
    VALID_SOURCES = ["wake_word", "ui", "visual"]
    
    def _validate_session_id(self, data: Dict[str, Any]) -> Optional[str]:
        """驗證 session_id"""
        session_id = data.get("session_id")
        if session_id and not isinstance(session_id, str):
            raise ValidationError("session_id 必須是字串")
        return session_id
    
    def validate_wake_command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證喚醒指令"""
        validated = {}
        
        # 驗證 session_id
        if session_id := self._validate_session_id(data):
            validated["session_id"] = session_id
        
        # 驗證喚醒源
        source = data.get("source", "ui")
        if source not in self.VALID_SOURCES:
            raise ValidationError(f"無效的喚醒源：{source}")
        validated["source"] = source
        
        # 驗證喚醒超時
        if "wake_timeout" in data:
            validated["wake_timeout"] = self.validate_numeric_field(
                data, "wake_timeout", min_value=0
            )
        
        return validated
    
    def validate_sleep_command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證休眠指令"""
        validated = {}
        if session_id := self._validate_session_id(data):
            validated["session_id"] = session_id
        return validated
    
    def validate_set_wake_timeout_command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證設定喚醒超時指令"""
        validated = {}
        
        if session_id := self._validate_session_id(data):
            validated["session_id"] = session_id
        
        # timeout 是必要欄位
        validated["timeout"] = self.validate_numeric_field(
            data, "timeout", min_value=0, required=True
        )
        
        return validated
    
    def format_wake_status_response(self, system_state: str,
                                   sessions: List[Any]) -> Dict[str, Any]:
        """格式化喚醒狀態回應"""
        def safe_isoformat(dt):
            return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
        
        active_wake_sessions = [
            {
                "id": s.id,
                "wake_source": s.wake_source,
                "wake_time": safe_isoformat(s.wake_time) if s.wake_time else None,
                "wake_timeout": s.wake_timeout,
                "is_wake_expired": s.is_wake_expired()
            }
            for s in sessions if s.wake_time and not s.is_wake_expired()
        ]
        
        return {
            "system_state": system_state,
            "active_wake_sessions": active_wake_sessions,
            "total_wake_sessions": len(active_wake_sessions),
            "timestamp": self.create_timestamp()
        }
    
    def format_wake_response(self, success: bool, message: str,
                           session_id: Optional[str] = None) -> Dict[str, Any]:
        """格式化喚醒回應"""
        response = {
            "success": success,
            "message": message,
            "timestamp": self.create_timestamp()
        }
        
        if session_id:
            response["session_id"] = session_id
        
        return response