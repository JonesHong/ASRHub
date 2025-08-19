"""
ASR Hub Operator 基礎類別
定義 Pipeline 中各種音訊處理運算子的共同介面
支援 PyStoreX 整合與 AudioQueueManager
"""

# 模組級變數 - 直接導入和實例化
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.utils.logger import logger
from src.core.exceptions import PipelineError
from src.audio import AudioMetadata
from src.core.audio_queue_manager import AudioQueueManager, get_audio_queue_manager
from src.store import get_global_store
from src.config.manager import ConfigManager
import asyncio

# 模組級全域實例
config_manager = ConfigManager()
store = get_global_store()
audio_queue_manager = get_audio_queue_manager()


class OperatorBase(ABC):
    """
    Operator 基礎抽象類別
    所有音訊處理運算子都需要繼承此類別
    
    支援兩種使用模式：
    1. 基本模式：直接處理音訊資料
    2. PyStoreX 模式：整合 Store 和 AudioQueueManager
    """
    
    def __init__(self):
        """
        初始化 Operator
        使用模組級變數提供統一的依賴項
        """
        self.enabled = True
        self._initialized = False
        
        # 使用模組級全域實例
        self.config_manager = config_manager
        self.store = store
        self.audio_queue_manager = audio_queue_manager
        self.current_session_id = None
    
    async def start(self):
        """
        啟動 Operator
        可以在此初始化資源、載入模型等
        """
        if self._initialized:
            logger.warning(f"{self.__class__.__name__} 已經初始化")
            return
        
        logger.info(f"啟動 {self.__class__.__name__}")
        await self._initialize()
        self._initialized = True
    
    async def stop(self):
        """
        停止 Operator
        可以在此釋放資源、清理緩衝等
        """
        if not self._initialized:
            logger.warning(f"{self.__class__.__name__} 未初始化")
            return
        
        logger.info(f"停止 {self.__class__.__name__}")
        await self._cleanup()
        self._initialized = False
    
    @abstractmethod
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊資料
        
        Args:
            audio_data: 輸入音訊資料
            **kwargs: 額外參數（如 session_id, metadata 等）
            
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
        
        子類別應該覆寫此方法來處理自己的配置更新
        
        Args:
            config: 新的配置
        """
        logger.debug(f"{self.__class__.__name__} 收到配置更新請求")
    
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
        logger.info(f"{self.__class__.__name__} {'啟用' if enabled else '停用'}")
    
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
            "has_config_manager": self.config_manager is not None,
            "has_store": self.store is not None,
            "has_queue_manager": self.audio_queue_manager is not None
        }
    
    def get_required_audio_format(self) -> Optional[AudioMetadata]:
        """
        獲取此 Operator 需要的輸入音頻格式
        
        Returns:
            需要的音頻格式，如果返回 None 表示可接受任何格式
        """
        return None
    
    def get_output_audio_format(self) -> Optional[AudioMetadata]:
        """
        獲取此 Operator 輸出的音頻格式
        
        Returns:
            輸出的音頻格式，如果返回 None 表示輸出格式與輸入相同
        """
        return None
    
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
            logger.warning("收到空的音訊資料")
            return False
        
        return True
    
    # ============================================================================
    # PyStoreX 和 AudioQueueManager 整合方法
    # ============================================================================
    
    async def process_from_queue(self, session_id: str, timeout: float = 1.0) -> Optional[bytes]:
        """
        從 AudioQueueManager 取得並處理音訊
        
        Args:
            session_id: Session ID
            timeout: 超時時間（秒）
            
        Returns:
            處理後的音訊數據
        """
        if not self.audio_queue_manager:
            logger.warning(f"{self.__class__.__name__}: No AudioQueueManager configured")
            return None
            
        try:
            # 從佇列拉取音訊
            audio_data = await self.audio_queue_manager.pull(session_id, timeout=timeout)
            
            if audio_data:
                # 處理音訊
                result = await self.process(audio_data, session_id=session_id)
                return result
            else:
                return None
                
        except asyncio.TimeoutError:
            logger.debug(f"{self.__class__.__name__}: No audio available for session {session_id}")
            return None
        except Exception as e:
            logger.error(f"{self.__class__.__name__}: Error processing from queue: {e}")
            return None
    
    async def process_streaming(self, session_id: str):
        """
        持續從佇列處理音訊（串流模式）
        
        Args:
            session_id: Session ID
        """
        if not self.audio_queue_manager:
            logger.error(f"{self.__class__.__name__}: AudioQueueManager required for streaming")
            return
            
        self.current_session_id = session_id
        logger.info(f"{self.__class__.__name__}: Starting streaming for session {session_id}")
        
        try:
            while self.enabled:
                # 從佇列取音訊
                audio_data = await self.process_from_queue(session_id, timeout=0.1)
                
                if audio_data is None:
                    # 沒有音訊時短暫等待
                    await asyncio.sleep(0.01)
                    continue
                    
                # 這裡可以加入額外的串流邏輯
                
        except Exception as e:
            logger.error(f"{self.__class__.__name__}: Streaming error: {e}")
        finally:
            logger.info(f"{self.__class__.__name__}: Stopped streaming for session {session_id}")
            self.current_session_id = None
    
    async def get_pre_recording(self, session_id: str, seconds: float = 2.0) -> Optional[bytes]:
        """
        獲取 pre-recording 緩衝的音訊
        
        Args:
            session_id: Session ID
            seconds: 要獲取的秒數
            
        Returns:
            pre-recording 音訊數據
        """
        if not self.audio_queue_manager:
            return None
            
        if session_id not in self.audio_queue_manager.queues:
            return None
            
        queue = self.audio_queue_manager.queues[session_id]
        return queue.get_pre_recording(seconds)
    
    async def start_recording_from_queue(self, session_id: str):
        """
        開始從佇列錄音
        
        Args:
            session_id: Session ID
        """
        if not self.audio_queue_manager:
            logger.error("AudioQueueManager required for recording")
            return
            
        if session_id not in self.audio_queue_manager.queues:
            await self.audio_queue_manager.create_queue(session_id)
            
        queue = self.audio_queue_manager.queues[session_id]
        await queue.start_recording()
        
        logger.info(f"Started recording from queue for session {session_id}")
    
    async def stop_recording_from_queue(self, session_id: str) -> Optional[bytes]:
        """
        停止從佇列錄音並獲取錄音數據
        
        Args:
            session_id: Session ID
            
        Returns:
            錄音數據
        """
        if not self.audio_queue_manager:
            return None
            
        if session_id not in self.audio_queue_manager.queues:
            return None
            
        queue = self.audio_queue_manager.queues[session_id]
        recording = await queue.stop_recording()
        
        logger.info(f"Stopped recording from queue for session {session_id}, got {len(recording) if recording else 0} bytes")
        
        return recording


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
    
    def __init__(self, buffer_size: int = 8192):
        """
        初始化緩衝 Operator
        
        Args:
            buffer_size: 緩衝區大小，預設 8192 bytes
        """
        super().__init__()
        self.buffer_size = buffer_size
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
            logger.debug(f"清空緩衝區，大小：{len(self.buffer)} bytes")
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