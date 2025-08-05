"""
ASR Hub HTTP SSE 處理器
處理各種 SSE 事件和請求
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from src.utils.logger import logger
from src.models.audio import AudioChunk, AudioFormat
from src.models.transcript import TranscriptSegment, TranscriptResult
from src.core.exceptions import APIError, ValidationError


class SSEEventHandler:
    """SSE 事件處理器"""
    
    def __init__(self):
        self.logger = logger
        
    def format_control_event(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化控制事件
        
        Args:
            command: 指令名稱
            params: 指令參數
            
        Returns:
            格式化的事件資料
        """
        return {
            "type": "control",
            "command": command,
            "params": params,
            "timestamp": datetime.now().isoformat()
        }
    
    def format_transcript_event(self, 
                              segment: TranscriptSegment,
                              session_id: str,
                              sequence_number: int) -> Dict[str, Any]:
        """
        格式化轉譯事件
        
        Args:
            segment: 轉譯片段
            session_id: Session ID
            sequence_number: 序列號
            
        Returns:
            格式化的事件資料
        """
        return {
            "type": "transcript",
            "session_id": session_id,
            "sequence": sequence_number,
            "segment": segment.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
    
    def format_error_event(self, 
                         error_type: str,
                         message: str,
                         details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        格式化錯誤事件
        
        Args:
            error_type: 錯誤類型
            message: 錯誤訊息
            details: 錯誤詳情
            
        Returns:
            格式化的事件資料
        """
        event = {
            "type": "error",
            "error_type": error_type,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        
        if details:
            event["details"] = details
            
        return event
    
    def format_status_event(self, 
                          status: str,
                          info: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化狀態事件
        
        Args:
            status: 狀態名稱
            info: 狀態資訊
            
        Returns:
            格式化的事件資料
        """
        return {
            "type": "status",
            "status": status,
            "info": info,
            "timestamp": datetime.now().isoformat()
        }
    
    def format_progress_event(self,
                            processed: int,
                            total: int,
                            message: Optional[str] = None) -> Dict[str, Any]:
        """
        格式化進度事件
        
        Args:
            processed: 已處理數量
            total: 總數量
            message: 進度訊息
            
        Returns:
            格式化的事件資料
        """
        event = {
            "type": "progress",
            "processed": processed,
            "total": total,
            "percentage": round((processed / total * 100) if total > 0 else 0, 2),
            "timestamp": datetime.now().isoformat()
        }
        
        if message:
            event["message"] = message
            
        return event
    
    def format_wake_event(self,
                         wake_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化喚醒詞事件
        
        Args:
            wake_data: 喚醒詞資料
            
        Returns:
            格式化的事件資料
        """
        return {
            "type": "wake_word",
            "source": wake_data.get("source", "wake_word"),
            "model": wake_data.get("detection", {}).get("model"),
            "score": wake_data.get("detection", {}).get("score"),
            "timestamp": wake_data.get("timestamp", datetime.now().isoformat())
        }
    
    def format_state_change_event(self,
                                 old_state: str,
                                 new_state: str,
                                 event_type: Optional[str] = None) -> Dict[str, Any]:
        """
        格式化狀態變更事件
        
        Args:
            old_state: 舊狀態
            new_state: 新狀態
            event_type: 觸發的事件類型
            
        Returns:
            格式化的事件資料
        """
        return {
            "type": "state_change",
            "old_state": old_state,
            "new_state": new_state,
            "event": event_type,
            "timestamp": datetime.now().isoformat()
        }


class AudioRequestHandler:
    """音訊請求處理器"""
    
    def __init__(self):
        self.logger = logger
        
    def validate_audio_upload(self, 
                            content_type: str,
                            content_length: int,
                            max_size: int = 10 * 1024 * 1024) -> None:
        """
        驗證音訊上傳請求
        
        Args:
            content_type: Content-Type 標頭
            content_length: Content-Length 標頭
            max_size: 最大允許大小（位元組）
            
        Raises:
            ValidationError: 如果驗證失敗
        """
        # 檢查 Content-Type
        valid_types = [
            "audio/wav",
            "audio/x-wav",
            "audio/mp3",
            "audio/mpeg",
            "audio/flac",
            "audio/ogg",
            "audio/webm",
            "application/octet-stream"  # 原始 PCM
        ]
        
        if content_type not in valid_types:
            raise ValidationError(f"不支援的音訊格式：{content_type}")
        
        # 檢查大小
        if content_length > max_size:
            raise ValidationError(
                f"音訊檔案太大：{content_length} bytes "
                f"(最大：{max_size} bytes)"
            )
    
    def parse_audio_params(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        從請求標頭解析音訊參數
        
        Args:
            headers: HTTP 標頭
            
        Returns:
            音訊參數字典
            
        Raises:
            ValidationError: 如果缺少必要參數
        """
        params = {}
        
        # 必要參數對應的 header 名稱
        header_mapping = {
            "sample_rate": ["X-Audio-Sample-Rate", "X-Sample-Rate"],
            "channels": ["X-Audio-Channels", "X-Channels"],
            "format": ["X-Audio-Format", "X-Format"],
            "encoding": ["X-Audio-Encoding", "X-Encoding"],
            "bits_per_sample": ["X-Audio-Bits", "X-Audio-Bits-Per-Sample", "X-Bits-Per-Sample"]
        }
        
        # 解析每個必要參數
        for param_name, header_names in header_mapping.items():
            value = None
            for header_name in header_names:
                if header_name in headers:
                    if param_name in ["sample_rate", "channels", "bits_per_sample"]:
                        try:
                            value = int(headers[header_name])
                        except ValueError:
                            raise ValidationError(f"無效的 {param_name}：{headers[header_name]}")
                    else:
                        value = headers[header_name].lower()
                    break
            
            if value is None:
                raise ValidationError(f"缺少必要的音訊參數 header：{param_name}")
            
            params[param_name] = value
        
        return params
    
    def create_audio_chunk(self, 
                         data: bytes,
                         params: Dict[str, Any],
                         sequence_number: int = 0) -> AudioChunk:
        """
        建立音訊資料塊
        
        Args:
            data: 音訊資料
            params: 音訊參數
            sequence_number: 序列號
            
        Returns:
            AudioChunk 實例
        """
        # 映射格式
        format_map = {
            "pcm": AudioFormat.PCM,
            "wav": AudioFormat.WAV,
            "mp3": AudioFormat.MP3,
            "flac": AudioFormat.FLAC,
            "ogg": AudioFormat.OGG,
            "webm": AudioFormat.WEBM
        }
        
        audio_format = format_map.get(params["format"], AudioFormat.PCM)
        
        return AudioChunk(
            data=data,
            sample_rate=params["sample_rate"],
            channels=params["channels"],
            format=audio_format,
            sequence_number=sequence_number
        )


class SessionRequestHandler:
    """Session 請求處理器"""
    
    def __init__(self):
        self.logger = logger
    
    def validate_session_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證建立 Session 的請求
        
        Args:
            data: 請求資料
            
        Returns:
            驗證後的資料
            
        Raises:
            ValidationError: 如果驗證失敗
        """
        validated = {
            "metadata": {},
            "pipeline_config": {},
            "provider_config": {}
        }
        
        # 驗證並提取元資料
        if "metadata" in data:
            if not isinstance(data["metadata"], dict):
                raise ValidationError("metadata 必須是字典")
            validated["metadata"] = data["metadata"]
        
        # 驗證 Pipeline 配置
        if "pipeline_config" in data:
            if not isinstance(data["pipeline_config"], dict):
                raise ValidationError("pipeline_config 必須是字典")
            
            # 驗證 operators
            if "operators" in data["pipeline_config"]:
                if not isinstance(data["pipeline_config"]["operators"], list):
                    raise ValidationError("operators 必須是列表")
                
                # 驗證每個 operator
                valid_operators = [
                    "vad", "denoise", "sample_rate_adjustment",
                    "voice_separation", "format_conversion", "recording",
                    # 新增喚醒詞相關 operators
                    "openwakeword", "wakeword"
                ]
                
                for op in data["pipeline_config"]["operators"]:
                    if op not in valid_operators:
                        raise ValidationError(f"無效的 operator：{op}")
            
            validated["pipeline_config"] = data["pipeline_config"]
        
        # 驗證 Provider 配置
        if "provider_config" in data:
            if not isinstance(data["provider_config"], dict):
                raise ValidationError("provider_config 必須是字典")
            
            # 驗證 provider
            if "provider" in data["provider_config"]:
                valid_providers = [
                    "whisper", "funasr", "vosk", 
                    "google_stt", "openai"
                ]
                
                if data["provider_config"]["provider"] not in valid_providers:
                    raise ValidationError(
                        f"無效的 provider：{data['provider_config']['provider']}"
                    )
            
            validated["provider_config"] = data["provider_config"]
        
        # 驗證喚醒詞相關參數
        if "wake_timeout" in data:
            try:
                wake_timeout = float(data["wake_timeout"])
                if wake_timeout <= 0:
                    raise ValidationError("wake_timeout 必須大於 0")
                validated["wake_timeout"] = wake_timeout
            except (ValueError, TypeError):
                raise ValidationError("wake_timeout 必須是數字")
        
        if "priority" in data:
            try:
                priority = int(data["priority"])
                validated["priority"] = priority
            except (ValueError, TypeError):
                raise ValidationError("priority 必須是整數")
        
        return validated
    
    def format_session_info(self, session: Any) -> Dict[str, Any]:
        """
        格式化 Session 資訊
        
        Args:
            session: Session 實例
            
        Returns:
            格式化的 Session 資訊
        """
        return {
            "id": session.id,
            "state": session.state,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "metadata": session.metadata,
            "pipeline_config": session.pipeline_config,
            "provider_config": session.provider_config
        }


class TranscriptResponseHandler:
    """轉譯回應處理器"""
    
    def __init__(self):
        self.logger = logger
        
    def format_streaming_response(self,
                                segments: List[TranscriptSegment],
                                session_id: str,
                                include_alternatives: bool = False) -> List[Dict[str, Any]]:
        """
        格式化串流轉譯回應
        
        Args:
            segments: 轉譯片段列表
            session_id: Session ID
            include_alternatives: 是否包含替代結果
            
        Returns:
            格式化的回應列表
        """
        responses = []
        
        for i, segment in enumerate(segments):
            response = {
                "session_id": session_id,
                "sequence": i,
                "text": segment.text,
                "is_final": segment.is_final,
                "confidence": segment.confidence,
                "start_time": segment.start_time,
                "end_time": segment.end_time
            }
            
            # 添加詞級別資訊
            if segment.words:
                response["words"] = [word.to_dict() for word in segment.words]
            
            # 添加語言資訊
            if segment.language:
                response["language"] = segment.language
            
            # 添加說話者資訊
            if segment.speaker is not None:
                response["speaker"] = segment.speaker
            
            responses.append(response)
        
        return responses
    
    def format_final_response(self, result: TranscriptResult) -> Dict[str, Any]:
        """
        格式化最終轉譯結果
        
        Args:
            result: 轉譯結果
            
        Returns:
            格式化的回應
        """
        response = result.to_dict()
        
        # 添加額外的統計資訊
        response["statistics"] = {
            "total_segments": len(result.segments),
            "total_words": result.get_word_count(),
            "average_confidence": result.confidence,
            "processing_time": result.processing_time
        }
        
        return response
    
    def merge_partial_results(self, 
                            partials: List[TranscriptSegment]) -> TranscriptSegment:
        """
        合併部分結果
        
        Args:
            partials: 部分結果列表
            
        Returns:
            合併後的片段
        """
        if not partials:
            return None
        
        # 合併文字
        merged_text = " ".join(seg.text for seg in partials)
        
        # 計算時間範圍
        start_time = min(seg.start_time for seg in partials)
        end_time = max(seg.end_time for seg in partials)
        
        # 計算平均信心分數
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


class WakeWordRequestHandler:
    """喚醒詞請求處理器"""
    
    def __init__(self):
        self.logger = logger
    
    def validate_wake_command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證喚醒指令
        
        Args:
            data: 請求資料
            
        Returns:
            驗證後的資料
            
        Raises:
            ValidationError: 如果驗證失敗
        """
        validated = {}
        
        # 驗證會話 ID
        if "session_id" in data:
            if not isinstance(data["session_id"], str):
                raise ValidationError("session_id 必須是字串")
            validated["session_id"] = data["session_id"]
        
        # 驗證喚醒源
        if "source" in data:
            valid_sources = ["wake_word", "ui", "visual"]
            if data["source"] not in valid_sources:
                raise ValidationError(f"無效的喚醒源：{data['source']}")
            validated["source"] = data["source"]
        else:
            validated["source"] = "ui"  # 預設為 UI 喚醒
        
        # 驗證喚醒超時
        if "wake_timeout" in data:
            try:
                wake_timeout = float(data["wake_timeout"])
                if wake_timeout <= 0:
                    raise ValidationError("wake_timeout 必須大於 0")
                validated["wake_timeout"] = wake_timeout
            except (ValueError, TypeError):
                raise ValidationError("wake_timeout 必須是數字")
        
        return validated
    
    def validate_sleep_command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證休眠指令
        
        Args:
            data: 請求資料
            
        Returns:
            驗證後的資料
            
        Raises:
            ValidationError: 如果驗證失敗
        """
        validated = {}
        
        # 驗證會話 ID
        if "session_id" in data:
            if not isinstance(data["session_id"], str):
                raise ValidationError("session_id 必須是字串")
            validated["session_id"] = data["session_id"]
        
        return validated
    
    def validate_set_wake_timeout_command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證設定喚醒超時指令
        
        Args:
            data: 請求資料
            
        Returns:
            驗證後的資料
            
        Raises:
            ValidationError: 如果驗證失敗
        """
        validated = {}
        
        # 驗證會話 ID
        if "session_id" in data:
            if not isinstance(data["session_id"], str):
                raise ValidationError("session_id 必須是字串")
            validated["session_id"] = data["session_id"]
        
        # 驗證超時值（必須）
        if "timeout" not in data:
            raise ValidationError("缺少 timeout 參數")
        
        try:
            timeout = float(data["timeout"])
            if timeout <= 0:
                raise ValidationError("timeout 必須大於 0")
            validated["timeout"] = timeout
        except (ValueError, TypeError):
            raise ValidationError("timeout 必須是數字")
        
        return validated
    
    def format_wake_status_response(self, system_state: str, 
                                   sessions: List[Any]) -> Dict[str, Any]:
        """
        格式化喚醒狀態回應
        
        Args:
            system_state: 系統狀態
            sessions: 會話列表
            
        Returns:
            格式化的回應
        """
        active_wake_sessions = [
            {
                "id": s.id,
                "wake_source": s.wake_source,
                "wake_time": s.wake_time.isoformat() if s.wake_time else None,
                "wake_timeout": s.wake_timeout,
                "is_wake_expired": s.is_wake_expired()
            }
            for s in sessions if s.wake_time and not s.is_wake_expired()
        ]
        
        return {
            "system_state": system_state,
            "active_wake_sessions": active_wake_sessions,
            "total_wake_sessions": len(active_wake_sessions),
            "timestamp": datetime.now().isoformat()
        }
    
    def format_wake_response(self, success: bool, 
                           message: str,
                           session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        格式化喚醒回應
        
        Args:
            success: 是否成功
            message: 回應訊息
            session_id: 會話 ID
            
        Returns:
            格式化的回應
        """
        response = {
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        
        if session_id:
            response["session_id"] = session_id
        
        return response