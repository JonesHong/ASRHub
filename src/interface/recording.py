"""錄音服務介面定義

定義錄音服務的標準介面，確保實現的一致性。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path


class IRecordingService(ABC):
    """錄音服務介面。
    
    提供音訊錄製功能，從 audio queue 取得音訊並寫入檔案。
    """
    
    @abstractmethod
    def start_recording(
        self,
        session_id: str,
        output_dir: Optional[Path] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """開始錄音。
        
        Args:
            session_id: Session ID
            output_dir: 輸出目錄（可選，未指定則使用預設值）
            filename: 檔案名稱（可選，未指定則自動產生）
            metadata: 額外的中繼資料
            
        Returns:
            是否成功開始錄音
        """
        pass
    
    @abstractmethod
    def stop_recording(self, session_id: str) -> Optional[Dict[str, Any]]:
        """停止錄音。
        
        Args:
            session_id: Session ID
            
        Returns:
            錄音資訊或 None（如果未在錄音中）
        """
        pass
    
    @abstractmethod
    def is_recording(self, session_id: str) -> bool:
        """檢查是否正在錄音。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在錄音
        """
        pass
    
    @abstractmethod
    def get_recording_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得錄音資訊。
        
        Args:
            session_id: Session ID
            
        Returns:
            錄音資訊或 None（如果未在錄音中）
        """
        pass
    
    @abstractmethod
    def list_recordings(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """列出錄音檔案。
        
        Args:
            session_id: Session ID 用於過濾（可選）
            
        Returns:
            錄音檔案字典
        """
        pass
    
    @abstractmethod
    def cleanup_old_recordings(self, days: Optional[int] = None) -> int:
        """清理舊的錄音檔案。
        
        Args:
            days: 保留天數（可選，未指定則使用配置預設值）
            
        Returns:
            刪除的檔案數量
        """
        pass