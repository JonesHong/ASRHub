"""
ASR Hub Operator 基礎類別
定義 Pipeline 中各種音訊處理運算子的共同介面
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.utils.logger import get_logger
from src.core.exceptions import PipelineError


class OperatorBase(ABC):
    """
    Operator 基礎抽象類別
    所有音訊處理運算子都需要繼承此類別
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Operator
        
        Args:
            config: Operator 配置
        """
        self.config = config or {}
        self.logger = get_logger(f"operator.{self.__class__.__name__.lower()}")
        self.enabled = self.config.get("enabled", True)
        self._initialized = False
        
        # 音訊參數
        self.sample_rate = self.config.get("sample_rate", 16000)
        self.channels = self.config.get("channels", 1)
        self.dtype = self.config.get("dtype", "int16")
    
    async def start(self):
        """
        啟動 Operator
        可以在此初始化資源、載入模型等
        """
        if self._initialized:
            self.logger.warning(f"{self.__class__.__name__} 已經初始化")
            return
        
        self.logger.info(f"啟動 {self.__class__.__name__}")
        await self._initialize()
        self._initialized = True
    
    async def stop(self):
        """
        停止 Operator
        可以在此釋放資源、清理緩衝等
        """
        if not self._initialized:
            self.logger.warning(f"{self.__class__.__name__} 未初始化")
            return
        
        self.logger.info(f"停止 {self.__class__.__name__}")
        await self._cleanup()
        self._initialized = False
    
    @abstractmethod
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊資料
        
        Args:
            audio_data: 輸入音訊資料
            **kwargs: 額外參數
            
        Returns:
            處理後的音訊資料，如果返回 None 表示資料被過濾
            
        Raises:
            PipelineError: 如果處理過程中發生錯誤
        """
        pass
    
    @abstractmethod
    async def _initialize(self):
        """
        初始化 Operator 資源
        子類別需要實作此方法來進行特定的初始化
        """
        pass
    
    @abstractmethod
    async def _cleanup(self):
        """
        清理 Operator 資源
        子類別需要實作此方法來進行特定的清理
        """
        pass
    
    def update_config(self, config: Dict[str, Any]):
        """
        更新 Operator 配置
        
        Args:
            config: 新的配置
        """
        self.config.update(config)
        
        # 更新常用參數
        self.enabled = self.config.get("enabled", self.enabled)
        self.sample_rate = self.config.get("sample_rate", self.sample_rate)
        self.channels = self.config.get("channels", self.channels)
        self.dtype = self.config.get("dtype", self.dtype)
        
        self.logger.debug(f"{self.__class__.__name__} 配置已更新")
    
    def is_enabled(self) -> bool:
        """檢查 Operator 是否啟用"""
        return self.enabled
    
    def set_enabled(self, enabled: bool):
        """
        設定 Operator 啟用狀態
        
        Args:
            enabled: 是否啟用
        """
        self.enabled = enabled
        self.logger.info(f"{self.__class__.__name__} {'啟用' if enabled else '停用'}")
    
    def get_info(self) -> Dict[str, Any]:
        """
        獲取 Operator 資訊
        
        Returns:
            Operator 資訊字典
        """
        return {
            "type": self.__class__.__name__,
            "enabled": self.enabled,
            "initialized": self._initialized,
            "config": self.config
        }
    
    async def flush(self):
        """
        清空內部緩衝區
        某些 Operator 可能有內部緩衝，可以覆寫此方法來實作清空邏輯
        """
        pass
    
    def validate_audio_params(self, audio_data: bytes) -> bool:
        """
        驗證音訊參數是否符合預期
        
        Args:
            audio_data: 音訊資料
            
        Returns:
            是否有效
        """
        # 基本驗證，子類別可以擴展
        if not audio_data:
            self.logger.warning("收到空的音訊資料")
            return False
        
        return True


class PassthroughOperator(OperatorBase):
    """
    直通 Operator
    不對音訊進行任何處理，直接返回原始資料
    主要用於測試和除錯
    """
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """直接返回輸入資料"""
        if not self.enabled:
            return audio_data
        
        if not self.validate_audio_params(audio_data):
            return None
        
        return audio_data
    
    async def _initialize(self):
        """無需初始化"""
        pass
    
    async def _cleanup(self):
        """無需清理"""
        pass


class BufferingOperator(OperatorBase):
    """
    緩衝 Operator 基礎類別
    提供音訊資料緩衝功能的基礎實作
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.buffer_size = self.config.get("buffer_size", 8192)
        self.buffer = bytearray()
    
    async def _initialize(self):
        """初始化緩衝區"""
        self.buffer = bytearray()
    
    async def _cleanup(self):
        """清理緩衝區"""
        self.buffer.clear()
    
    async def flush(self):
        """清空緩衝區"""
        if self.buffer:
            self.logger.debug(f"清空緩衝區，大小：{len(self.buffer)} bytes")
            self.buffer.clear()
    
    def add_to_buffer(self, data: bytes):
        """
        添加資料到緩衝區
        
        Args:
            data: 要添加的資料
        """
        self.buffer.extend(data)
    
    def get_buffer_size(self) -> int:
        """獲取當前緩衝區大小"""
        return len(self.buffer)
    
    def is_buffer_full(self) -> bool:
        """檢查緩衝區是否已滿"""
        return len(self.buffer) >= self.buffer_size