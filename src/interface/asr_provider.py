"""ASR Provider 介面定義

定義語音識別提供者的抽象介面。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import numpy as np


class TranscriptionStatus(Enum):
    """轉譯狀態"""
    IDLE = "idle"                   # 閒置
    PROCESSING = "processing"       # 處理中
    COMPLETED = "completed"         # 完成
    ERROR = "error"                # 錯誤


@dataclass
class TranscriptionSegment:
    """轉譯片段"""
    text: str                           # 轉譯文字
    start_time: float                  # 開始時間（秒）
    end_time: float                    # 結束時間（秒）
    confidence: Optional[float] = None  # 信心度 (0.0 ~ 1.0)
    language: Optional[str] = None      # 語言代碼
    tokens: Optional[List[int]] = None  # Token IDs
    
    
@dataclass
class TranscriptionResult:
    """轉譯結果"""
    session_id: str                              # Session ID
    segments: List[TranscriptionSegment]         # 轉譯片段列表
    full_text: str                               # 完整轉譯文字
    language: Optional[str] = None               # 偵測到的語言
    duration: Optional[float] = None             # 音訊總長度（秒）
    processing_time: Optional[float] = None      # 處理時間（秒）
    metadata: Optional[Dict[str, Any]] = None    # 額外資訊


@dataclass 
class ASRConfig:
    """ASR 提供者配置"""
    model_name: str = "base"           # 模型名稱或路徑
    language: Optional[str] = "zh"     # 語言代碼 (None = 自動偵測)
    device: str = "cpu"                # 運算裝置 (cpu, cuda, mps)
    compute_type: str = "float32"      # 運算精度
    sample_rate: int = 16000           # 採樣率
    use_vad: bool = True               # 是否使用 VAD
    temperature: float = 0.0            # 溫度參數（影響隨機性）
    beam_size: int = 5                 # Beam search 大小
    best_of: int = 5                   # 最佳候選數量
    patience: float = 1.0              # Patience for early stopping
    length_penalty: float = 1.0        # 長度懲罰
    suppress_blank: bool = True        # 抑制空白
    suppress_tokens: Optional[List[int]] = None  # 要抑制的 token
    initial_prompt: Optional[str] = None         # 初始提示
    word_timestamps: bool = False                # 是否產生詞級時間戳
    prepend_punctuations: str = "\"'([{-"     # 前置標點
    append_punctuations: str = "\"'.。,，!！?？:：)]}"  # 後置標點


class IASRProvider(ABC):
    """ASR 提供者介面"""
    
    @abstractmethod
    def initialize(self, config: Optional[ASRConfig] = None) -> bool:
        """初始化 ASR 提供者
        
        Args:
            config: ASR 配置
            
        Returns:
            是否成功初始化
        """
        pass
    
    @abstractmethod
    def start_transcription(
        self, 
        session_id: str,
        callback: Optional[Callable[[TranscriptionResult], None]] = None
    ) -> bool:
        """開始轉譯特定 session 的音訊
        
        Args:
            session_id: Session ID
            callback: 轉譯完成時的回調函數
            
        Returns:
            是否成功開始轉譯
        """
        pass
    
    @abstractmethod
    def stop_transcription(self, session_id: str) -> bool:
        """停止轉譯特定 session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止
        """
        pass
    
    @abstractmethod
    def is_transcribing(self, session_id: str) -> bool:
        """檢查是否正在轉譯特定 session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在轉譯
        """
        pass
    
    @abstractmethod
    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        session_id: Optional[str] = None
    ) -> TranscriptionResult:
        """轉譯單段音訊
        
        Args:
            audio_data: 音訊數據 (numpy array, float32, -1.0 ~ 1.0)
            session_id: Session ID (可選)
            
        Returns:
            轉譯結果
        """
        pass
    
    @abstractmethod
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 狀態資訊
        
        Args:
            session_id: Session ID
            
        Returns:
            狀態資訊
        """
        pass
    
    @abstractmethod
    def reset_session(self, session_id: str) -> bool:
        """重置特定 session 的狀態
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功重置
        """
        pass
    
    @abstractmethod
    def get_config(self) -> Optional[ASRConfig]:
        """取得當前配置
        
        Returns:
            當前配置
        """
        pass
    
    @abstractmethod
    def update_config(self, config: ASRConfig) -> bool:
        """更新配置
        
        Args:
            config: 新配置
            
        Returns:
            是否成功更新
        """
        pass
    
    @abstractmethod
    def get_active_sessions(self) -> List[str]:
        """取得所有活動中的 session ID
        
        Returns:
            活動中的 session ID 列表
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """關閉提供者，釋放資源"""
        pass