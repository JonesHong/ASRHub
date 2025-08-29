"""麥克風服務介面定義

定義麥克風擷取服務的標準介面。
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Any
import numpy as np


class IMicrophoneService(ABC):
    """麥克風服務介面。
    
    提供即時麥克風音訊擷取功能。
    """
    
    @abstractmethod
    def start_capture(self, callback: Optional[Callable] = None) -> bool:
        """開始擷取麥克風音訊。
        
        Args:
            callback: 音訊資料回調函數，接收 (audio_data, sample_rate)
            
        Returns:
            是否成功開始擷取
        """
        pass
    
    @abstractmethod
    def stop_capture(self) -> bool:
        """停止擷取。
        
        Returns:
            是否成功停止
        """
        pass
    
    @abstractmethod
    def is_capturing(self) -> bool:
        """檢查是否正在擷取。
        
        Returns:
            是否正在擷取
        """
        pass
    
    @abstractmethod
    def get_devices(self) -> list:
        """取得可用的音訊裝置列表。
        
        Returns:
            裝置列表
        """
        pass
    
    @abstractmethod
    def set_device(self, device_index: int) -> bool:
        """設定使用的音訊裝置。
        
        Args:
            device_index: 裝置索引
            
        Returns:
            是否設定成功
        """
        pass
    
    @abstractmethod
    def read_chunk(self, frames: int = 1024) -> Optional[np.ndarray]:
        """讀取一個音訊片段（非阻塞）。
        
        Args:
            frames: 要讀取的幀數
            
        Returns:
            音訊資料 numpy array，如果沒有資料返回 None
        """
        pass