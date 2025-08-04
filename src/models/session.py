"""
ASR Hub Session 資料模型
定義 ASR 會話的資料結構
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid


class SessionState(Enum):
    """Session 狀態"""
    IDLE = "idle"              # 閒置狀態
    LISTENING = "listening"    # 聆聽中
    BUSY = "busy"             # 忙碌狀態（處理中但暫停聆聽）
    PROCESSING = "processing"  # 處理中
    ERROR = "error"           # 錯誤狀態
    TERMINATED = "terminated"  # 已終止


class SessionType(Enum):
    """Session 類型"""
    REALTIME = "realtime"     # 即時串流
    BATCH = "batch"           # 批次處理
    FILE = "file"             # 檔案處理


@dataclass
class SessionConfig:
    """Session 配置"""
    # Pipeline 配置
    pipeline_operators: List[str] = field(default_factory=list)
    pipeline_config: Dict[str, Any] = field(default_factory=dict)
    
    # Provider 配置
    provider_name: str = "whisper"
    provider_config: Dict[str, Any] = field(default_factory=dict)
    
    # 音訊配置
    sample_rate: int = 16000
    channels: int = 1
    audio_format: str = "pcm"
    
    # 行為配置
    auto_terminate_silence: bool = True
    silence_timeout: float = 3.0
    max_duration: Optional[float] = None
    
    # 串流配置
    buffer_size: int = 8192
    chunk_size: int = 1024
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "pipeline": {
                "operators": self.pipeline_operators,
                "config": self.pipeline_config
            },
            "provider": {
                "name": self.provider_name,
                "config": self.provider_config
            },
            "audio": {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "format": self.audio_format
            },
            "behavior": {
                "auto_terminate_silence": self.auto_terminate_silence,
                "silence_timeout": self.silence_timeout,
                "max_duration": self.max_duration
            },
            "stream": {
                "buffer_size": self.buffer_size,
                "chunk_size": self.chunk_size
            }
        }


@dataclass
class SessionStatistics:
    """Session 統計資訊"""
    # 音訊統計
    total_audio_duration: float = 0.0     # 總音訊時長（秒）
    total_audio_bytes: int = 0            # 總音訊資料量
    audio_chunks_received: int = 0        # 接收的音訊塊數
    
    # 轉譯統計
    total_transcribed_words: int = 0      # 總轉譯詞數
    total_transcribed_segments: int = 0   # 總轉譯片段數
    average_confidence: float = 0.0       # 平均信心分數
    
    # 效能統計
    total_processing_time: float = 0.0    # 總處理時間
    average_latency: float = 0.0          # 平均延遲
    realtime_factor: float = 0.0          # 即時因子（處理時間/音訊時長）
    
    # 錯誤統計
    error_count: int = 0                  # 錯誤次數
    retry_count: int = 0                  # 重試次數
    
    def update_audio_stats(self, duration: float, bytes_count: int):
        """更新音訊統計"""
        self.total_audio_duration += duration
        self.total_audio_bytes += bytes_count
        self.audio_chunks_received += 1
    
    def update_transcript_stats(self, word_count: int, confidence: float):
        """更新轉譯統計"""
        self.total_transcribed_words += word_count
        self.total_transcribed_segments += 1
        
        # 更新平均信心分數
        if self.total_transcribed_segments == 1:
            self.average_confidence = confidence
        else:
            # 計算加權平均
            total = self.average_confidence * (self.total_transcribed_segments - 1)
            self.average_confidence = (total + confidence) / self.total_transcribed_segments
    
    def calculate_realtime_factor(self):
        """計算即時因子"""
        if self.total_audio_duration > 0:
            self.realtime_factor = self.total_processing_time / self.total_audio_duration
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "audio": {
                "total_duration": self.total_audio_duration,
                "total_bytes": self.total_audio_bytes,
                "chunks_received": self.audio_chunks_received
            },
            "transcript": {
                "total_words": self.total_transcribed_words,
                "total_segments": self.total_transcribed_segments,
                "average_confidence": self.average_confidence
            },
            "performance": {
                "total_processing_time": self.total_processing_time,
                "average_latency": self.average_latency,
                "realtime_factor": self.realtime_factor
            },
            "errors": {
                "error_count": self.error_count,
                "retry_count": self.retry_count
            }
        }


@dataclass
class Session:
    """
    ASR Session 完整資料模型
    代表一個完整的語音辨識會話
    """
    
    # 基本資訊
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: SessionType = SessionType.REALTIME
    state: SessionState = SessionState.IDLE
    
    # 時間資訊
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_activity: datetime = field(default_factory=datetime.now)
    
    # 配置
    config: SessionConfig = field(default_factory=SessionConfig)
    
    # 統計資訊
    statistics: SessionStatistics = field(default_factory=SessionStatistics)
    
    # 客戶端資訊
    client_id: Optional[str] = None
    client_info: Dict[str, Any] = field(default_factory=dict)
    
    # 元資料
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    # 錯誤資訊
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    def start(self):
        """開始 Session"""
        self.started_at = datetime.now()
        self.state = SessionState.LISTENING
        self.update_activity()
    
    def stop(self):
        """停止 Session"""
        self.ended_at = datetime.now()
        self.state = SessionState.TERMINATED
        self.update_activity()
    
    def set_error(self, error_message: str, error_details: Optional[Dict[str, Any]] = None):
        """設定錯誤狀態"""
        self.state = SessionState.ERROR
        self.error_message = error_message
        self.error_details = error_details
        self.statistics.error_count += 1
        self.update_activity()
    
    def update_activity(self):
        """更新最後活動時間"""
        self.last_activity = datetime.now()
    
    def change_state(self, new_state: SessionState):
        """
        變更狀態
        
        Args:
            new_state: 新狀態
        """
        old_state = self.state
        self.state = new_state
        self.update_activity()
        
        # 記錄狀態變更到元資料
        if "state_history" not in self.metadata:
            self.metadata["state_history"] = []
        
        self.metadata["state_history"].append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": self.last_activity.isoformat()
        })
    
    def is_active(self) -> bool:
        """檢查 Session 是否活躍"""
        return self.state in [
            SessionState.LISTENING,
            SessionState.PROCESSING,
            SessionState.BUSY
        ]
    
    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """
        檢查 Session 是否過期
        
        Args:
            timeout_seconds: 超時秒數
            
        Returns:
            是否過期
        """
        if self.state == SessionState.TERMINATED:
            return True
        
        time_since_activity = datetime.now() - self.last_activity
        return time_since_activity.total_seconds() > timeout_seconds
    
    def get_duration(self) -> Optional[float]:
        """
        獲取 Session 持續時間
        
        Returns:
            持續時間（秒），如果尚未結束則返回 None
        """
        if self.started_at:
            end_time = self.ended_at or datetime.now()
            duration = end_time - self.started_at
            return duration.total_seconds()
        return None
    
    def add_tag(self, tag: str):
        """添加標籤"""
        if tag not in self.tags:
            self.tags.append(tag)
    
    def remove_tag(self, tag: str):
        """移除標籤"""
        if tag in self.tags:
            self.tags.remove(tag)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "id": self.id,
            "type": self.type.value,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "config": self.config.to_dict(),
            "statistics": self.statistics.to_dict(),
            "is_active": self.is_active(),
            "tags": self.tags,
            "metadata": self.metadata
        }
        
        # 可選欄位
        if self.started_at:
            result["started_at"] = self.started_at.isoformat()
        if self.ended_at:
            result["ended_at"] = self.ended_at.isoformat()
        if self.client_id:
            result["client_id"] = self.client_id
        if self.client_info:
            result["client_info"] = self.client_info
        if self.error_message:
            result["error"] = {
                "message": self.error_message,
                "details": self.error_details
            }
        
        duration = self.get_duration()
        if duration is not None:
            result["duration"] = duration
            
        return result