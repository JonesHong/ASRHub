"""
ASR Hub Pipeline 基礎類別
定義音訊處理管線的抽象介面
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from src.utils.logger import logger
from src.core.exceptions import PipelineError
from src.pipeline.operators.base import OperatorBase
from src.config.manager import ConfigManager


class PipelineBase(ABC):
    """
    Pipeline 基礎抽象類別
    管理一系列 Operators 的執行順序和資料流
    """
    
    def __init__(self):
        """
        初始化 Pipeline
        """
        self.config_manager = ConfigManager()
        self.config = self.config_manager.pipeline  # 這是 PipelineSchema 實例，不是字典
        self.operators: List[OperatorBase] = []
        self._running = False
        
        # 從配置初始化 operators
        self._initialize_operators()
    
    @abstractmethod
    def _initialize_operators(self):
        """
        初始化 Pipeline 中的 Operators
        子類別需要實作此方法來建立和配置 operators
        """
        pass
    
    async def start(self):
        """啟動 Pipeline"""
        if self._running:
            logger.warning("Pipeline 已經在運行中")
            return
        
        logger.info("啟動 Pipeline")
        self._running = True
        
        # 啟動所有 operators
        for operator in self.operators:
            await operator.start()
    
    async def stop(self):
        """停止 Pipeline"""
        if not self._running:
            logger.warning("Pipeline 未在運行中")
            return
        
        logger.info("停止 Pipeline")
        self._running = False
        
        # 停止所有 operators（反向順序）
        for operator in reversed(self.operators):
            await operator.stop()
    
    async def process(self, audio_data: bytes, **kwargs) -> bytes:
        """
        處理單一音訊資料塊
        
        Args:
            audio_data: 輸入音訊資料
            **kwargs: 額外參數
            
        Returns:
            處理後的音訊資料
            
        Raises:
            PipelineError: 如果處理過程中發生錯誤
        """
        if not self._running:
            raise PipelineError("Pipeline 未啟動")
        
        try:
            # 依序通過所有 operators
            processed_data = audio_data
            
            # 如果有多個 operators，使用進度條
            if len(self.operators) > 1 and kwargs.get('show_progress', True):
                # 使用 logger.progress.track_list 正確的方式顯示處理進度
                for i, operator in enumerate(logger.progress.track_list(
                    self.operators, 
                    description="Pipeline processing"
                )):
                    # 顯示當前處理的 operator
                    op_name = operator.__class__.__name__
                    logger.debug(f"Processing: {op_name}")
                    
                    processed_data = await operator.process(processed_data, **kwargs)
                    
                    # 如果 operator 返回 None，表示資料被過濾掉
                    if processed_data is None:
                        logger.debug(f"資料被 {op_name} 過濾")
                        return None
            else:
                # 單個 operator 或不顯示進度條
                for operator in self.operators:
                    processed_data = await operator.process(processed_data, **kwargs)
                    
                    # 如果 operator 返回 None，表示資料被過濾掉
                    if processed_data is None:
                        logger.debug(f"資料被 {operator.__class__.__name__} 過濾")
                        return None
            
            return processed_data
            
        except Exception as e:
            logger.error(f"Pipeline 處理錯誤：{e}")
            raise PipelineError(f"Pipeline 處理失敗：{str(e)}")
    
    async def process_stream(self, 
                           audio_stream: AsyncGenerator[bytes, None],
                           **kwargs) -> AsyncGenerator[bytes, None]:
        """
        處理音訊串流
        
        Args:
            audio_stream: 輸入音訊串流
            **kwargs: 額外參數
            
        Yields:
            處理後的音訊資料塊
            
        Raises:
            PipelineError: 如果處理過程中發生錯誤
        """
        if not self._running:
            raise PipelineError("Pipeline 未啟動")
        
        try:
            async for audio_chunk in audio_stream:
                processed_chunk = await self.process(audio_chunk, **kwargs)
                
                # 只輸出非 None 的資料
                if processed_chunk is not None:
                    yield processed_chunk
                    
        except Exception as e:
            logger.error(f"Pipeline 串流處理錯誤：{e}")
            raise PipelineError(f"Pipeline 串流處理失敗：{str(e)}")
    
    def add_operator(self, operator: OperatorBase, position: Optional[int] = None):
        """
        添加 Operator 到 Pipeline
        
        Args:
            operator: 要添加的 Operator
            position: 插入位置，None 表示添加到末尾
        """
        if position is None:
            self.operators.append(operator)
        else:
            self.operators.insert(position, operator)
        
        logger.debug(f"添加 Operator：{operator.__class__.__name__}")
    
    def remove_operator(self, operator_type: type) -> bool:
        """
        從 Pipeline 移除指定類型的 Operator
        
        Args:
            operator_type: Operator 類型
            
        Returns:
            是否成功移除
        """
        for i, operator in enumerate(self.operators):
            if isinstance(operator, operator_type):
                removed = self.operators.pop(i)
                logger.debug(f"移除 Operator：{removed.__class__.__name__}")
                return True
        return False
    
    def get_operators(self) -> List[OperatorBase]:
        """獲取所有 Operators"""
        return self.operators.copy()
    
    def get_config(self) -> Dict[str, Any]:
        """獲取 Pipeline 配置"""
        return self.config.to_dict()
    
    def update_config(self, config: Dict[str, Any]):
        """
        更新 Pipeline 配置
        
        Args:
            config: 新的配置
        """
        # 重新從 ConfigManager 獲取配置
        self.config_manager = ConfigManager()
        self.config = self.config_manager.pipeline
        logger.info("Pipeline 配置已更新")
        
        # 通知所有 operators 配置已更新
        for operator in self.operators:
            if hasattr(operator, 'update_config'):
                operator.update_config(config)
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        """
        獲取 Pipeline 資訊
        
        Returns:
            Pipeline 資訊字典
        """
        return {
            "type": self.__class__.__name__,
            "running": self._running,
            "operators": [
                {
                    "type": op.__class__.__name__,
                    "enabled": getattr(op, 'enabled', True)
                }
                for op in self.operators
            ],
            "config": self.config.to_dict()
        }
    
    def is_running(self) -> bool:
        """檢查 Pipeline 是否正在運行"""
        return self._running
    
    async def flush(self):
        """
        清空 Pipeline 緩衝區
        某些 operators 可能有內部緩衝，此方法用於清空它們
        """
        for operator in self.operators:
            if hasattr(operator, 'flush'):
                await operator.flush()