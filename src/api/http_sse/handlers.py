"""
ASR Hub HTTP SSE 處理器
處理各種 SSE 事件和請求
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from src.utils.logger import get_logger
from src.models.audio import AudioChunk, AudioFormat
from src.models.transcript import TranscriptSegment, TranscriptResult
from src.core.exceptions import APIError, ValidationError


class SSEEventHandler:
    """SSE 事件處理器"""
    
    def __init__(self):
        self.logger = get_logger("sse.handler")
        
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


class AudioRequestHandler:
    """音訊請求處理器"""
    
    def __init__(self):
        self.logger = get_logger("sse.audio_handler")
        
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
        """
        params = {
            "sample_rate": 16000,
            "channels": 1,
            "format": "pcm",
            "encoding": "linear16"
        }
        
        # 從自定義標頭解析參數
        if "X-Audio-Sample-Rate" in headers:
            try:
                params["sample_rate"] = int(headers["X-Audio-Sample-Rate"])
            except ValueError:
                self.logger.warning(f"無效的取樣率：{headers['X-Audio-Sample-Rate']}")
        
        if "X-Audio-Channels" in headers:
            try:
                params["channels"] = int(headers["X-Audio-Channels"])
            except ValueError:
                self.logger.warning(f"無效的聲道數：{headers['X-Audio-Channels']}")
        
        if "X-Audio-Format" in headers:
            params["format"] = headers["X-Audio-Format"].lower()
        
        if "X-Audio-Encoding" in headers:
            params["encoding"] = headers["X-Audio-Encoding"].lower()
        
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
        self.logger = get_logger("sse.session_handler")
    
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
                    "voice_separation", "format_conversion", "recording"
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
        self.logger = get_logger("sse.transcript_handler")
        
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