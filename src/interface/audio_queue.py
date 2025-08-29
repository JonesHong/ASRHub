"""音訊佇列管理器介面

為每個 session 管理音訊佇列的簡單介面。
遵循 KISS 原則 - 簡單、清楚、可維護。
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.interface.audio import AudioChunk


class IAudioQueueManager(ABC):
    """音訊佇列管理器服務介面。
    
    為不同的 session 管理音訊片段，提供簡單的
    推入、拉取和清除操作。
    """
    
    @abstractmethod
    def push(self, session_id: str, chunk: AudioChunk) -> None:
        """推入音訊片段到 session 佇列。
        
        Args:
            session_id: Session 識別碼
            chunk: 要推入的音訊片段
        """
        pass
    
    @abstractmethod
    def pull(self, session_id: str, count: int = 1) -> List[AudioChunk]:
        """從 session 佇列拉取音訊片段。
        
        Args:
            session_id: Session 識別碼
            count: 要拉取的片段數量 (預設: 1)
            
        Returns:
            音訊片段列表 (佇列為空時回傳空列表)
        """
        pass
    
    @abstractmethod
    def clear(self, session_id: str) -> None:
        """清除 session 佇列中的所有音訊片段。
        
        Args:
            session_id: Session 識別碼
        """
        pass
    
    @abstractmethod
    def size(self, session_id: str) -> int:
        """取得 session 佇列的當前大小。
        
        Args:
            session_id: Session 識別碼
            
        Returns:
            佇列中的片段數量 (佇列不存在時回傳 0)
        """
        pass
    
    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """檢查 session 是否存在佇列。
        
        Args:
            session_id: Session 識別碼
            
        Returns:
            佇列存在回傳 True，否則回傳 False
        """
        pass
    
    @abstractmethod
    def remove(self, session_id: str) -> None:
        """移除整個 session 佇列。
        
        Args:
            session_id: Session 識別碼
        """
        pass