"""Wakeword Detection 服務介面定義

定義喚醒詞檢測服務的抽象介面。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import numpy as np


# === Wake Activation/Deactivation Sources ===
class WakeActivateSource:
    """喚醒啟用來源"""
    VISUAL = "visual"
    UI = "ui"
    KEYWORD = "keyword"

WakeActivateSource.KEYWORD
class WakeDeactivateSource:
    """喚醒停用來源"""
    VISUAL = "visual"
    UI = "ui"
    VAD_SILENCE_TIMEOUT = "vad_silence_timeout"


# === Wakeword Status and Data Classes ===

@dataclass
class WakewordDetection:
    """喚醒詞檢測結果。"""
    keyword: str                     # 檢測到的關鍵字
    confidence: float                # 信心度 (0.0 ~ 1.0)
    timestamp: float                 # 檢測時間戳
    session_id: str                  # Session ID
    model_name: Optional[str] = None  # 模型名稱
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class WakewordConfig:
    """喚醒詞服務配置。"""
    model_path: Optional[str] = None     # 模型路徑
    threshold: float = 0.5                # 檢測閾值
    cooldown_seconds: float = 2.0        # 冷卻期（秒）
    debounce_time: float = 2.0           # 去抖動時間（秒）
    sample_rate: int = 16000             # 採樣率
    chunk_size: int = 1280                # 處理塊大小
    max_buffer_size: int = 100           # 最大緩衝區大小
    continuous_detection: bool = True     # 連續檢測模式
    use_gpu: bool = False                 # 是否使用 GPU
    # OpenWakeWord 特定配置
    hf_repo_id: Optional[str] = None     # HuggingFace repo ID
    hf_filename: Optional[str] = None    # HuggingFace 檔名
    hf_token: Optional[str] = None       # HuggingFace token


class IWakewordService(ABC):
    """喚醒詞檢測服務介面。"""
    
    @abstractmethod
    def initialize(self, config: Optional[WakewordConfig] = None) -> bool:
        """初始化喚醒詞服務。
        
        Args:
            config: 服務配置
            
        Returns:
            是否成功初始化
        """
        pass
    
    @abstractmethod
    def start_monitoring(
        self,
        session_id: str,
        keywords: Optional[List[str]] = None,
        on_detected: Optional[Callable[[str, WakewordDetection], None]] = None
    ) -> bool:
        """開始監控特定 session 的音訊。
        
        Args:
            session_id: Session ID
            keywords: 要監聽的關鍵字列表（None 表示使用預設）
            on_detected: 檢測到喚醒詞時的回調
            
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
    ) -> Optional[WakewordDetection]:
        """處理單個音訊片段。
        
        Args:
            audio_data: 音訊數據 (numpy array)
            sample_rate: 採樣率（如果與配置不同）
            
        Returns:
            檢測結果（如果有）
        """
        pass
    
    @abstractmethod
    def process_stream(
        self,
        session_id: str,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> Optional[WakewordDetection]:
        """處理串流音訊（保持 session 狀態）。
        
        Args:
            session_id: Session ID
            audio_data: 音訊數據
            sample_rate: 採樣率
            
        Returns:
            檢測結果（如果有）
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
    def set_default_hook(
        self,
        on_detected: Optional[Callable[[str, WakewordDetection], None]] = None
    ) -> None:
        """設定預設的檢測 hook。
        
        Args:
            on_detected: 檢測到喚醒詞時的預設回調
        """
        pass
    
    @abstractmethod
    def get_monitoring_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得監控資訊。
        
        Args:
            session_id: Session ID
            
        Returns:
            監控資訊（如果正在監控）
        """
        pass
    
    @abstractmethod
    def stop_all_monitoring(self) -> int:
        """停止所有監控。
        
        Returns:
            停止的監控數量
        """
        pass
    
    @abstractmethod
    def update_config(self, config: WakewordConfig) -> bool:
        """更新服務配置。
        
        Args:
            config: 新的配置
            
        Returns:
            是否成功更新
        """
        pass
    
    @abstractmethod
    def get_config(self) -> WakewordConfig:
        """取得當前配置。
        
        Returns:
            當前配置
        """
        pass
    
    @abstractmethod
    def is_initialized(self) -> bool:
        """檢查服務是否已初始化。
        
        Returns:
            是否已初始化
        """
        pass