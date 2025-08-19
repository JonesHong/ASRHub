"""
實時串流協議定義
定義 WebSocket/SocketIO 實時音訊串流協議
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime


class StreamMessageType(str, Enum):
    """串流訊息類型"""
    # 控制訊息
    STREAM_START = "stream_start"
    STREAM_STOP = "stream_stop"
    STREAM_PAUSE = "stream_pause"
    STREAM_RESUME = "stream_resume"
    
    # 音訊訊息
    AUDIO_CHUNK = "audio_chunk"
    AUDIO_CONFIG = "audio_config"
    
    # 結果訊息
    PARTIAL_TRANSCRIPT = "partial_transcript"
    FINAL_TRANSCRIPT = "final_transcript"
    SEGMENT_COMPLETE = "segment_complete"
    
    # 狀態訊息
    VAD_EVENT = "vad_event"
    BUFFER_STATUS = "buffer_status"
    BACKPRESSURE = "backpressure"
    
    # 錯誤訊息
    ERROR = "error"
    WARNING = "warning"


class VADEventType(str, Enum):
    """VAD 事件類型"""
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    SILENCE_DETECTED = "silence_detected"


class BackpressureLevel(str, Enum):
    """背壓級別"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class StreamMessage:
    """基礎串流訊息"""
    type: StreamMessageType
    session_id: str
    timestamp: str = None
    sequence: Optional[int] = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return asdict(self)


@dataclass
class AudioChunkMessage(StreamMessage):
    """音訊塊訊息"""
    type: StreamMessageType = StreamMessageType.AUDIO_CHUNK
    data: str = None  # Base64 encoded audio
    size: int = 0
    duration_ms: int = 0
    is_final: bool = False


@dataclass
class PartialTranscriptMessage(StreamMessage):
    """部分轉譯結果訊息"""
    type: StreamMessageType = StreamMessageType.PARTIAL_TRANSCRIPT
    text: str = ""
    confidence: float = 0.0
    language: Optional[str] = None
    offset_ms: int = 0
    duration_ms: int = 0
    is_stable: bool = False  # 是否為穩定結果（不太會變化）


@dataclass
class FinalTranscriptMessage(StreamMessage):
    """最終轉譯結果訊息"""
    type: StreamMessageType = StreamMessageType.FINAL_TRANSCRIPT
    segment_id: str = ""
    text: str = ""
    confidence: float = 0.0
    language: Optional[str] = None
    start_time_ms: int = 0
    end_time_ms: int = 0
    words: Optional[List[Dict[str, Any]]] = None
    alternatives: Optional[List[Dict[str, Any]]] = None


@dataclass
class VADEventMessage(StreamMessage):
    """VAD 事件訊息"""
    type: StreamMessageType = StreamMessageType.VAD_EVENT
    event_type: VADEventType = VADEventType.SPEECH_START
    confidence: float = 0.0
    energy_level: float = 0.0
    
    
@dataclass
class BufferStatusMessage(StreamMessage):
    """緩衝區狀態訊息"""
    type: StreamMessageType = StreamMessageType.BUFFER_STATUS
    buffer_size: int = 0
    buffer_duration_ms: int = 0
    usage_percent: float = 0.0
    chunks_queued: int = 0
    chunks_processed: int = 0


@dataclass 
class BackpressureMessage(StreamMessage):
    """背壓訊息"""
    type: StreamMessageType = StreamMessageType.BACKPRESSURE
    level: BackpressureLevel = BackpressureLevel.NONE
    message: str = ""
    suggested_action: str = ""
    retry_after_ms: Optional[int] = None


class StreamProtocol:
    """串流協議處理器"""
    
    @staticmethod
    def create_audio_chunk(
        session_id: str,
        audio_data: bytes,
        sequence: int,
        is_final: bool = False
    ) -> Dict[str, Any]:
        """創建音訊塊訊息"""
        import base64
        
        return AudioChunkMessage(
            session_id=session_id,
            sequence=sequence,
            data=base64.b64encode(audio_data).decode('utf-8'),
            size=len(audio_data),
            duration_ms=len(audio_data) * 1000 // 32000,  # 假設 16kHz, 16-bit
            is_final=is_final
        ).to_dict()
    
    @staticmethod
    def create_partial_transcript(
        session_id: str,
        text: str,
        confidence: float,
        offset_ms: int,
        sequence: Optional[int] = None
    ) -> Dict[str, Any]:
        """創建部分轉譯結果訊息"""
        return PartialTranscriptMessage(
            session_id=session_id,
            sequence=sequence,
            text=text,
            confidence=confidence,
            offset_ms=offset_ms
        ).to_dict()
    
    @staticmethod
    def create_final_transcript(
        session_id: str,
        segment_id: str,
        text: str,
        confidence: float,
        start_time_ms: int,
        end_time_ms: int,
        words: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """創建最終轉譯結果訊息"""
        return FinalTranscriptMessage(
            session_id=session_id,
            segment_id=segment_id,
            text=text,
            confidence=confidence,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            words=words
        ).to_dict()
    
    @staticmethod
    def create_vad_event(
        session_id: str,
        event_type: VADEventType,
        confidence: float = 0.0
    ) -> Dict[str, Any]:
        """創建 VAD 事件訊息"""
        return VADEventMessage(
            session_id=session_id,
            event_type=event_type,
            confidence=confidence
        ).to_dict()
    
    @staticmethod
    def create_backpressure(
        session_id: str,
        level: BackpressureLevel,
        message: str = ""
    ) -> Dict[str, Any]:
        """創建背壓訊息"""
        suggested_actions = {
            BackpressureLevel.LOW: "Consider reducing audio quality",
            BackpressureLevel.MEDIUM: "Please slow down audio transmission",
            BackpressureLevel.HIGH: "Pause audio transmission temporarily",
            BackpressureLevel.CRITICAL: "Stop audio transmission immediately"
        }
        
        retry_after = {
            BackpressureLevel.LOW: None,
            BackpressureLevel.MEDIUM: 100,
            BackpressureLevel.HIGH: 500,
            BackpressureLevel.CRITICAL: 1000
        }
        
        return BackpressureMessage(
            session_id=session_id,
            level=level,
            message=message or f"System experiencing {level.value} load",
            suggested_action=suggested_actions.get(level, ""),
            retry_after_ms=retry_after.get(level)
        ).to_dict()
    
    @staticmethod
    def parse_message(data: Dict[str, Any]) -> StreamMessage:
        """解析串流訊息"""
        msg_type = StreamMessageType(data.get("type"))
        
        message_classes = {
            StreamMessageType.AUDIO_CHUNK: AudioChunkMessage,
            StreamMessageType.PARTIAL_TRANSCRIPT: PartialTranscriptMessage,
            StreamMessageType.FINAL_TRANSCRIPT: FinalTranscriptMessage,
            StreamMessageType.VAD_EVENT: VADEventMessage,
            StreamMessageType.BUFFER_STATUS: BufferStatusMessage,
            StreamMessageType.BACKPRESSURE: BackpressureMessage
        }
        
        message_class = message_classes.get(msg_type, StreamMessage)
        
        # 過濾有效的欄位
        valid_fields = message_class.__dataclass_fields__.keys()
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return message_class(**filtered_data)


class StreamingConfig:
    """串流配置"""
    
    # 窗口配置
    WINDOW_SIZE_MS = 3000  # 3秒窗口
    OVERLAP_SIZE_MS = 500  # 500ms 重疊
    
    # 緩衝配置
    MIN_CHUNK_SIZE = 1600  # 最小處理單位（100ms @ 16kHz）
    MAX_BUFFER_SIZE = 320000  # 最大緩衝（20秒 @ 16kHz）
    BUFFER_THRESHOLD = 0.8  # 緩衝區閾值
    
    # VAD 配置
    VAD_THRESHOLD = 0.5  # VAD 信心閾值
    SILENCE_DURATION_MS = 1000  # 靜音持續時間
    SPEECH_MIN_DURATION_MS = 200  # 最小語音長度
    
    # 性能配置
    MAX_CONCURRENT_STREAMS = 100  # 最大並發串流數
    STREAM_TIMEOUT_SECONDS = 300  # 串流超時（5分鐘）
    
    # 背壓配置
    BACKPRESSURE_THRESHOLDS = {
        "buffer_usage": 0.8,  # 緩衝區使用率
        "queue_length": 100,   # 隊列長度
        "latency_ms": 500,     # 延遲毫秒
        "memory_mb": 100       # 記憶體使用
    }