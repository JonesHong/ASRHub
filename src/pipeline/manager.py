"""
ASR Hub Pipeline Manager
管理音訊處理管線的建立、配置和執行
"""

from typing import Dict, Any, List, Optional
from src.utils.logger import get_logger
from src.core.exceptions import PipelineError, ConfigurationError
from src.pipeline.base import PipelineBase
from src.pipeline.operators.base import OperatorBase
from src.pipeline.operators.sample_rate import SampleRateOperator
from src.pipeline.validator import PipelineValidator


class DefaultPipeline(PipelineBase):
    """預設的 Pipeline 實作"""
    
    def _initialize_operators(self):
        """初始化 Pipeline 中的 Operators"""
        operator_configs = self.config.get("operators", {})
        
        # Sample Rate Adjustment
        if operator_configs.get("sample_rate_adjustment", {}).get("enabled", True):
            self.add_operator(
                SampleRateOperator(operator_configs.get("sample_rate_adjustment", {}))
            )
        
        # TODO: 添加其他 operators (VAD, Denoise, etc.)


class PipelineManager:
    """
    Pipeline 管理器
    負責建立、管理和協調多個 Pipeline 實例
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Pipeline Manager
        
        Args:
            config: Pipeline 配置
        """
        self.config = config
        self.logger = get_logger("pipeline.manager")
        
        # Pipeline 實例快取
        self.pipelines: Dict[str, PipelineBase] = {}
        
        # 可用的 Operator 類型註冊
        self.operator_registry: Dict[str, type] = {
            "sample_rate": SampleRateOperator,
            # TODO: 註冊其他 operators
        }
        
        # Pipeline 驗證器
        self.validator = PipelineValidator()
        
        self._initialized = False
    
    async def initialize(self):
        """初始化 Pipeline Manager"""
        if self._initialized:
            self.logger.warning("Pipeline Manager 已經初始化")
            return
        
        self.logger.info("初始化 Pipeline Manager...")
        
        # 建立預設 Pipeline
        await self._create_default_pipeline()
        
        self._initialized = True
        self.logger.success("Pipeline Manager 初始化完成")
    
    async def _create_default_pipeline(self):
        """建立預設的 Pipeline"""
        try:
            # 建立 Pipeline
            default_pipeline = DefaultPipeline(self.config)
            
            # 驗證 Pipeline 配置
            validation_result = self.validator.validate_pipeline(default_pipeline)
            if not validation_result["valid"]:
                raise ConfigurationError(
                    f"Pipeline 配置無效：{validation_result['errors']}"
                )
            
            # 啟動 Pipeline
            await default_pipeline.start()
            
            # 儲存到快取
            self.pipelines["default"] = default_pipeline
            
            self.logger.info("預設 Pipeline 建立成功")
            
        except Exception as e:
            self.logger.error(f"建立預設 Pipeline 失敗：{e}")
            raise
    
    async def create_pipeline(self, 
                            name: str,
                            config: Dict[str, Any]) -> PipelineBase:
        """
        建立新的 Pipeline
        
        Args:
            name: Pipeline 名稱
            config: Pipeline 配置
            
        Returns:
            建立的 Pipeline 實例
            
        Raises:
            PipelineError: 如果建立失敗
        """
        if name in self.pipelines:
            raise PipelineError(f"Pipeline '{name}' 已存在")
        
        try:
            # 建立 Pipeline
            pipeline = DefaultPipeline(config)
            
            # 驗證配置
            validation_result = self.validator.validate_pipeline(pipeline)
            if not validation_result["valid"]:
                raise ConfigurationError(
                    f"Pipeline 配置無效：{validation_result['errors']}"
                )
            
            # 啟動 Pipeline
            await pipeline.start()
            
            # 儲存到快取
            self.pipelines[name] = pipeline
            
            self.logger.info(f"Pipeline '{name}' 建立成功")
            return pipeline
            
        except Exception as e:
            self.logger.error(f"建立 Pipeline '{name}' 失敗：{e}")
            raise PipelineError(f"無法建立 Pipeline：{str(e)}")
    
    def get_pipeline(self, name: str = "default") -> Optional[PipelineBase]:
        """
        獲取指定的 Pipeline
        
        Args:
            name: Pipeline 名稱
            
        Returns:
            Pipeline 實例，如果不存在則返回 None
        """
        return self.pipelines.get(name)
    
    async def remove_pipeline(self, name: str):
        """
        移除指定的 Pipeline
        
        Args:
            name: Pipeline 名稱
        """
        if name == "default":
            raise PipelineError("不能移除預設 Pipeline")
        
        if name in self.pipelines:
            pipeline = self.pipelines[name]
            await pipeline.stop()
            del self.pipelines[name]
            self.logger.info(f"Pipeline '{name}' 已移除")
    
    def list_pipelines(self) -> List[str]:
        """
        列出所有 Pipeline 名稱
        
        Returns:
            Pipeline 名稱列表
        """
        return list(self.pipelines.keys())
    
    def get_pipeline_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        獲取 Pipeline 資訊
        
        Args:
            name: Pipeline 名稱
            
        Returns:
            Pipeline 資訊，如果不存在則返回 None
        """
        pipeline = self.get_pipeline(name)
        if pipeline:
            return pipeline.get_pipeline_info()
        return None
    
    def register_operator(self, name: str, operator_class: type):
        """
        註冊新的 Operator 類型
        
        Args:
            name: Operator 名稱
            operator_class: Operator 類別
        """
        if not issubclass(operator_class, OperatorBase):
            raise ValueError(f"{operator_class} 必須繼承自 OperatorBase")
        
        self.operator_registry[name] = operator_class
        self.logger.info(f"註冊 Operator：{name}")
    
    def get_registered_operators(self) -> List[str]:
        """
        獲取已註冊的 Operator 列表
        
        Returns:
            Operator 名稱列表
        """
        return list(self.operator_registry.keys())
    
    async def process_audio(self,
                          audio_data: bytes,
                          pipeline_name: str = "default",
                          **kwargs) -> Optional[bytes]:
        """
        使用指定的 Pipeline 處理音訊
        
        Args:
            audio_data: 音訊資料
            pipeline_name: Pipeline 名稱
            **kwargs: 額外參數
            
        Returns:
            處理後的音訊資料
            
        Raises:
            PipelineError: 如果處理失敗
        """
        pipeline = self.get_pipeline(pipeline_name)
        if not pipeline:
            raise PipelineError(f"Pipeline '{pipeline_name}' 不存在")
        
        if not pipeline.is_running():
            raise PipelineError(f"Pipeline '{pipeline_name}' 未運行")
        
        return await pipeline.process(audio_data, **kwargs)
    
    async def cleanup(self):
        """清理所有資源"""
        self.logger.info("清理 Pipeline Manager...")
        
        # 停止所有 Pipeline
        for name, pipeline in list(self.pipelines.items()):
            try:
                await pipeline.stop()
                self.logger.debug(f"Pipeline '{name}' 已停止")
            except Exception as e:
                self.logger.error(f"停止 Pipeline '{name}' 時發生錯誤：{e}")
        
        self.pipelines.clear()
        self._initialized = False
        self.logger.info("Pipeline Manager 清理完成")
    
    def get_status(self) -> Dict[str, Any]:
        """
        獲取 Pipeline Manager 狀態
        
        Returns:
            狀態資訊
        """
        return {
            "initialized": self._initialized,
            "pipeline_count": len(self.pipelines),
            "pipelines": {
                name: pipeline.get_pipeline_info()
                for name, pipeline in self.pipelines.items()
            },
            "registered_operators": self.get_registered_operators()
        }