"""
ASR Hub 轉譯結果資料模型
定義語音轉文字的結果資料結構
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TranscriptStatus(Enum):
    """轉譯狀態"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # 串流中的部分結果


@dataclass
class Word:
    """
    單詞級別的轉譯資訊
    """
    text: str                    # 單詞文字
    start_time: float           # 開始時間（秒）
    end_time: float             # 結束時間（秒）
    confidence: float           # 信心分數 (0.0-1.0)
    speaker: Optional[int] = None  # 說話者 ID（如果有說話者分離）
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence
        }
        if self.speaker is not None:
            result["speaker"] = self.speaker
        return result


@dataclass
class TranscriptSegment:
    """
    轉譯片段
    用於表示一段完整的轉譯結果（可能是一個句子或段落）
    """
    text: str                              # 轉譯文字
    start_time: float                      # 開始時間（秒）
    end_time: float                        # 結束時間（秒）
    confidence: float                      # 平均信心分數
    words: Optional[List[Word]] = None     # 詞級別資訊
    speaker: Optional[int] = None          # 說話者 ID
    language: Optional[str] = None         # 語言代碼
    is_final: bool = True                  # 是否為最終結果（串流時使用）
    
    def get_duration(self) -> float:
        """獲取片段時長"""
        return self.end_time - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
            "duration": self.get_duration(),
            "is_final": self.is_final
        }
        
        if self.words:
            result["words"] = [word.to_dict() for word in self.words]
        if self.speaker is not None:
            result["speaker"] = self.speaker
        if self.language:
            result["language"] = self.language
            
        return result


@dataclass
class TranscriptAlternative:
    """
    轉譯替代結果
    某些 ASR 系統會提供多個可能的轉譯結果
    """
    text: str              # 替代文字
    confidence: float      # 信心分數
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "text": self.text,
            "confidence": self.confidence
        }


@dataclass
class TranscriptResult:
    """
    完整的轉譯結果
    包含所有轉譯資訊和元資料
    """
    
    # 基本資訊
    text: str                                      # 完整轉譯文字
    segments: List[TranscriptSegment]              # 轉譯片段列表
    language: str                                  # 語言代碼
    confidence: float                              # 整體信心分數
    
    # 時間資訊
    start_time: float = 0.0                        # 開始時間
    end_time: float = 0.0                          # 結束時間
    created_at: datetime = field(default_factory=datetime.now)  # 建立時間
    
    # 狀態資訊
    status: TranscriptStatus = TranscriptStatus.COMPLETED
    error_message: Optional[str] = None
    
    # 額外資訊
    alternatives: Optional[List[TranscriptAlternative]] = None  # 替代結果
    speaker_count: Optional[int] = None            # 說話者數量
    audio_duration: Optional[float] = None         # 原始音訊時長
    processing_time: Optional[float] = None        # 處理時間
    
    # ASR Provider 資訊
    provider: Optional[str] = None                 # 使用的 ASR 提供者
    model: Optional[str] = None                    # 使用的模型
    
    # 元資料
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化後處理"""
        # 如果沒有提供時間資訊，從片段計算
        if self.segments and (self.start_time == 0.0 or self.end_time == 0.0):
            self.start_time = min(seg.start_time for seg in self.segments)
            self.end_time = max(seg.end_time for seg in self.segments)
        
        # 計算整體信心分數（如果未提供）
        if self.confidence == 0.0 and self.segments:
            total_duration = sum(seg.get_duration() for seg in self.segments)
            if total_duration > 0:
                weighted_confidence = sum(
                    seg.confidence * seg.get_duration() 
                    for seg in self.segments
                )
                self.confidence = weighted_confidence / total_duration
    
    def get_duration(self) -> float:
        """獲取轉譯涵蓋的時長"""
        return self.end_time - self.start_time
    
    def get_word_count(self) -> int:
        """獲取總詞數"""
        return len(self.text.split())
    
    def get_words_per_minute(self) -> float:
        """計算每分鐘詞數"""
        duration_minutes = self.get_duration() / 60.0
        if duration_minutes > 0:
            return self.get_word_count() / duration_minutes
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "text": self.text,
            "language": self.language,
            "confidence": self.confidence,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.get_duration(),
            "created_at": self.created_at.isoformat(),
            "word_count": self.get_word_count(),
            "words_per_minute": self.get_words_per_minute(),
            "segments": [seg.to_dict() for seg in self.segments]
        }
        
        # 可選欄位
        if self.error_message:
            result["error_message"] = self.error_message
        if self.alternatives:
            result["alternatives"] = [alt.to_dict() for alt in self.alternatives]
        if self.speaker_count is not None:
            result["speaker_count"] = self.speaker_count
        if self.audio_duration is not None:
            result["audio_duration"] = self.audio_duration
        if self.processing_time is not None:
            result["processing_time"] = self.processing_time
        if self.provider:
            result["provider"] = self.provider
        if self.model:
            result["model"] = self.model
        if self.metadata:
            result["metadata"] = self.metadata
            
        return result
    
    def to_srt(self) -> str:
        """
        轉換為 SRT 字幕格式
        
        Returns:
            SRT 格式字串
        """
        srt_lines = []
        
        for i, segment in enumerate(self.segments, 1):
            # 序號
            srt_lines.append(str(i))
            
            # 時間碼
            start_time = self._format_srt_time(segment.start_time)
            end_time = self._format_srt_time(segment.end_time)
            srt_lines.append(f"{start_time} --> {end_time}")
            
            # 文字
            srt_lines.append(segment.text)
            
            # 空行
            srt_lines.append("")
        
        return "\n".join(srt_lines)
    
    def to_vtt(self) -> str:
        """
        轉換為 WebVTT 字幕格式
        
        Returns:
            WebVTT 格式字串
        """
        vtt_lines = ["WEBVTT", ""]
        
        for segment in self.segments:
            # 時間碼
            start_time = self._format_vtt_time(segment.start_time)
            end_time = self._format_vtt_time(segment.end_time)
            vtt_lines.append(f"{start_time} --> {end_time}")
            
            # 文字
            vtt_lines.append(segment.text)
            
            # 空行
            vtt_lines.append("")
        
        return "\n".join(vtt_lines)
    
    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """格式化為 SRT 時間碼"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    @staticmethod
    def _format_vtt_time(seconds: float) -> str:
        """格式化為 WebVTT 時間碼"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"