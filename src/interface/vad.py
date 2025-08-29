"""VAD (Voice Activity Detection) 服務介面定義

定義語音活動檢測服務的抽象介面。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, List, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import numpy as np


class VADState(Enum):
    """VAD 狀態。"""
    SILENCE = "silence"    # 靜音
    SPEECH = "speech"      # 說話中
    UNCERTAIN = "uncertain"  # 不確定


@dataclass
class VADResult:
    """VAD 檢測結果。"""
    state: VADState
    probability: float  # 語音機率 (0.0 ~ 1.0)
    start_time: Optional[float] = None  # 語音開始時間
    end_time: Optional[float] = None    # 語音結束時間
    duration: Optional[float] = None    # 持續時間
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class VADConfig:
    """VAD 配置。"""
    threshold: float = 0.5  # 語音檢測閾值
    min_speech_duration: float = 0.25  # 最小語音持續時間（秒）
    min_silence_duration: float = 0.5  # 最小靜音持續時間（秒）
    sample_rate: int = 16000  # 採樣率
    frame_size: int = 512  # 幀大小（樣本數）
    chunk_size: int = 512  # 音訊塊大小
    window_size: int = 512  # 滑動窗口大小
    use_gpu: bool = False  # 是否使用 GPU
    model_path: Optional[str] = None  # 模型路徑
    speech_pad_ms: int = 30  # 語音前後填充（毫秒）
    return_seconds: bool = False  # 是否返回秒數
    max_speech_duration: float = 60.0  # 最大語音持續時間（秒）


class IVADService(ABC):
    """VAD 服務介面。"""
    
    @abstractmethod
    def initialize(self, config: Optional[VADConfig] = None) -> bool:
        """初始化 VAD 服務。
        
        Args:
            config: VAD 配置
            
        Returns:
            是否成功初始化
        """
        pass
    
    @abstractmethod
    def start_monitoring(
        self,
        session_id: str,
        on_speech_detected: Optional[Callable[[str, VADResult], None]] = None,
        on_silence_detected: Optional[Callable[[str, VADResult], None]] = None
    ) -> bool:
        """開始監控特定 session 的音訊。
        
        Args:
            session_id: Session ID
            on_speech_detected: 檢測到語音時的回調
            on_silence_detected: 檢測到靜音時的回調
            
        Returns:
            是否成功開始監控
        """
        pass
    
    @abstractmethod
    def stop_monitoring(self, session_id: str) -> bool:
        """停止監控特定 session。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止
        """
        pass
    
    @abstractmethod
    def is_monitoring(self, session_id: str) -> bool:
        """檢查是否正在監控特定 session。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在監控
        """
        pass
    
    @abstractmethod
    def process_chunk(
        self,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> VADResult:
        """處理單個音訊片段。
        
        Args:
            audio_data: 音訊數據 (numpy array)
            sample_rate: 採樣率（如果與配置不同）
            
        Returns:
            VAD 檢測結果
        """
        pass
    
    @abstractmethod
    def process_stream(
        self,
        session_id: str,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> VADResult:
        """處理串流音訊（保持 session 狀態）。
        
        Args:
            session_id: Session ID
            audio_data: 音訊數據
            sample_rate: 採樣率
            
        Returns:
            VAD 檢測結果
        """
        pass
    
    @abstractmethod
    def reset_session(self, session_id: str) -> bool:
        """重置特定 session 的狀態。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功重置
        """
        pass
    
    @abstractmethod
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 狀態資訊。
        
        Args:
            session_id: Session ID
            
        Returns:
            狀態資訊
        """
        pass
    
    @abstractmethod
    def update_config(self, config: VADConfig) -> bool:
        """更新 VAD 配置。
        
        Args:
            config: 新的配置
            
        Returns:
            是否成功更新
        """
        pass
    
    @abstractmethod
    def get_config(self) -> VADConfig:
        """取得當前配置。
        
        Returns:
            當前 VAD 配置
        """
        pass
    
    @abstractmethod
    def clear_all_sessions(self) -> int:
        """清除所有 session 狀態。
        
        Returns:
            清除的 session 數量
        """
        pass
    
    @abstractmethod
    def is_initialized(self) -> bool:
        """檢查服務是否已初始化。
        
        Returns:
            是否已初始化
        """
        pass