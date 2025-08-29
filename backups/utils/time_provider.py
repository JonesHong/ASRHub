"""
時間提供者工具類
用於統一管理時間戳，避免系統時間異常問題
"""

import time
import warnings
from typing import Optional


class TimeProvider:
    """時間提供者類，統一管理時間戳獲取"""
    
    _mock_time: Optional[float] = None
    _base_time: Optional[float] = None
    _start_time: Optional[float] = None
    
    @classmethod
    def now(cls) -> float:
        """
        獲取當前時間戳
        
        Returns:
            float: Unix 時間戳
        """
        # 如果設置了模擬時間，返回模擬時間
        if cls._mock_time is not None:
            return cls._mock_time
        
        # 獲取實際時間
        current_time = time.time()
        
        # 檢查時間是否異常（如果超過2030年，可能是系統時間有問題）
        # 正確的 2030 年時間戳約為 1893456000 秒
        # 正確的 2050 年時間戳約為 2524608000 秒
        # 但如果系統有問題，時間戳可能是微秒級別（乘以 1000000）
        
        # 檢查是否是微秒級時間戳（大於 10^12，即超過 2281 年）
        if current_time > 1e12:
            warnings.warn(
                f"系統時間異常：{current_time}（可能是微秒級時間戳）。"
                f"轉換為秒級時間戳。"
            )
            # 將微秒轉換為秒
            return current_time / 1e6
        
        # 檢查是否是毫秒級時間戳（大於 10^10，即超過 2286 年）
        elif current_time > 1e10:
            warnings.warn(
                f"系統時間異常：{current_time}（可能是毫秒級時間戳）。"
                f"轉換為秒級時間戳。"
            )
            # 將毫秒轉換為秒
            return current_time / 1e3
        
        return current_time
    
    @classmethod
    def elapsed_since_start(cls) -> float:
        """
        獲取從程式啟動到現在的經過時間
        
        Returns:
            float: 經過的秒數
        """
        # 如果沒有啟動時間，使用當前時間
        if cls._start_time is None:
            cls._start_time = cls.now()
        return cls.now() - cls._start_time
    
    @classmethod
    def set_mock_time(cls, mock_time: Optional[float] = None):
        """
        設置模擬時間（用於測試）
        
        Args:
            mock_time: 模擬的時間戳，None 表示使用真實時間
        """
        cls._mock_time = mock_time
    
    @classmethod
    def reset(cls):
        """重置時間提供者狀態"""
        cls._mock_time = None
        cls._base_time = None
        cls._start_time = cls.now()


def get_current_time() -> float:
    """
    獲取當前時間戳的便捷函數
    
    Returns:
        float: Unix 時間戳
    """
    return TimeProvider.now()


def get_elapsed_time() -> float:
    """
    獲取程式運行時間的便捷函數
    
    Returns:
        float: 從程式啟動到現在的秒數
    """
    return TimeProvider.elapsed_since_start()