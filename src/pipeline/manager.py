"""
ASR Hub Pipeline Manager
管理音訊處理管線的建立、配置和執行
"""

from typing import Dict, Any, List, Optional, Tuple
from src.utils.logger import logger
from src.core.exceptions import PipelineError, ConfigurationError
from src.pipeline.base import PipelineBase
from src.pipeline.operators.base import OperatorBase
# 直接使用具體的音頻格式轉換實現
from src.pipeline.operators.audio_format import (
    ScipyAudioFormatOperator, 
    FFmpegAudioFormatOperator
)
from src.pipeline.validator import PipelineValidator
from src.config.manager import ConfigManager
from src.models.audio_format import AudioMetadata, AudioFormat


class DefaultPipeline(PipelineBase):
    """
    預設的 Pipeline 實作
    整合智能格式轉換功能，自動分析 Operator 需求並插入必要的格式轉換
    """
    
    def __init__(self):
        """初始化 DefaultPipeline，使用 ConfigManager 獲取配置"""
        self.config_manager = ConfigManager()
        # 傳遞必要的配置給父類以通過驗證
        pipeline_config = self.config_manager.pipeline
        config_dict = {
            "sample_rate": pipeline_config.default_sample_rate,
            "channels": pipeline_config.channels,
            "encoding": pipeline_config.encoding,
            "buffer_size": pipeline_config.buffer_size
        }
        
        # 手動設置 encoding 格式對應
        encoding_map = {
            'linear16': AudioFormat.INT16,
            'int16': AudioFormat.INT16,
            'linear32': AudioFormat.INT32,
            'int32': AudioFormat.INT32,
            'float32': AudioFormat.FLOAT32,
        }
        audio_format = encoding_map.get(pipeline_config.encoding, AudioFormat.INT16)
        
        # 先設置 input_format
        self.input_format = AudioMetadata(
            sample_rate=pipeline_config.default_sample_rate,
            channels=pipeline_config.channels,
            format=audio_format
        )
        
        super().__init__(config_dict)
        self.name = "default"  # 設置 Pipeline 名稱
    
    def _get_audio_format_from_encoding(self, encoding: str) -> AudioFormat:
        """從編碼字符串獲取 AudioFormat"""
        encoding_map = {
            'linear16': AudioFormat.INT16,
            'linear32': AudioFormat.INT32,
            'float32': AudioFormat.FLOAT32,
        }
        return encoding_map.get(encoding, AudioFormat.INT16)
    
    def _initialize_operators(self):
        """初始化 operators 並自動插入格式轉換"""
        # 從配置中獲取要啟用的 operators
        operators_config = self.config_manager.pipeline.operators
        
        # 構建 operator 列表
        planned_operators = []
        
        # Sample Rate Adjustment (已棄用，改用 audio_format)
        if hasattr(operators_config, 'sample_rate_adjustment') and \
           operators_config.sample_rate_adjustment.enabled:
            self.logger.warning("sample_rate_adjustment 已棄用，請使用 audio_format")
        
        # VAD
        if hasattr(operators_config, 'vad') and operators_config.vad.enabled:
            from src.pipeline.operators.vad.silero_vad import SileroVADOperator
            planned_operators.append(('vad', SileroVADOperator()))
        
        # Wake Word
        if hasattr(operators_config, 'wakeword') and operators_config.wakeword.enabled:
            from src.pipeline.operators.wakeword.openwakeword import OpenWakeWordOperator
            planned_operators.append(('wakeword', OpenWakeWordOperator()))
        
        # Recording
        if hasattr(operators_config, 'recording') and operators_config.recording.enabled:
            # TODO: 實現實際的 Recording operator
            self.logger.debug("Recording operator 尚未實現")
        
        # 分析並構建最終的 pipeline
        self._build_smart_pipeline(planned_operators)
    
    def _build_smart_pipeline(self, planned_operators: List[Tuple[str, OperatorBase]]):
        """
        構建智能 pipeline，自動插入格式轉換
        
        Args:
            planned_operators: 計劃添加的 operators 列表 [(name, operator), ...]
        """
        current_format = self.input_format
        
        for name, operator in planned_operators:
            # 獲取 operator 的格式需求
            required_format = operator.get_required_audio_format()
            
            # 如果需要格式轉換
            if required_format and not self._formats_match(current_format, required_format):
                # 創建格式轉換器
                converter = self._create_format_converter(
                    current_format, 
                    required_format,
                    operator_name=name
                )
                self.add_operator(converter)
                self.logger.info(
                    f"插入格式轉換: {current_format.sample_rate}Hz -> "
                    f"{required_format.sample_rate}Hz for {name}"
                )
                current_format = required_format
            
            # 添加實際的 operator
            self.add_operator(operator)
            
            # 更新當前格式（如果 operator 改變了輸出格式）
            output_format = operator.get_output_audio_format()
            if output_format:
                current_format = output_format
    
    def _formats_match(self, format1: AudioMetadata, format2: AudioMetadata) -> bool:
        """檢查兩個音頻格式是否匹配"""
        return (format1.sample_rate == format2.sample_rate and
                format1.channels == format2.channels and
                format1.format == format2.format)
    
    def _create_format_converter(self, 
                                from_format: AudioMetadata,
                                to_format: AudioMetadata,
                                operator_name: str = "") -> OperatorBase:
        """
        創建格式轉換器
        
        Args:
            from_format: 源格式
            to_format: 目標格式
            operator_name: 使用此轉換器的 operator 名稱（用於日誌）
            
        Returns:
            配置好的格式轉換器
        """
        # 獲取配置的後端
        backend = 'scipy'  # 預設值
        try:
            if hasattr(self.config_manager.pipeline, 'audio_format') and \
               hasattr(self.config_manager.pipeline.audio_format, 'backend'):
                backend = self.config_manager.pipeline.audio_format.backend
        except AttributeError:
            pass
        
        # 創建轉換器
        converter_id = f"converter_for_{operator_name}" if operator_name else "converter"
        
        # 根據後端選擇具體實現
        if backend.lower() == 'ffmpeg':
            converter = FFmpegAudioFormatOperator(
                operator_id=converter_id,
                target_metadata=to_format
            )
        else:
            # 預設使用 scipy
            converter = ScipyAudioFormatOperator(
                operator_id=converter_id,
                target_metadata=to_format
            )
        
        return converter
    
    def analyze_pipeline(self) -> Dict[str, Any]:
        """
        分析 pipeline 結構，返回詳細信息
        
        Returns:
            包含 pipeline 分析結果的字典
        """
        analysis = {
            "input_format": self.input_format.to_dict(),
            "operators": []
        }
        
        current_format = self.input_format
        
        for operator in self.operators:
            op_info = {
                "type": operator.__class__.__name__,
                "input_format": current_format.to_dict()
            }
            
            # 獲取需求格式
            required = operator.get_required_audio_format()
            if required:
                op_info["required_format"] = required.to_dict()
                op_info["format_match"] = self._formats_match(current_format, required)
            
            # 獲取輸出格式
            output = operator.get_output_audio_format()
            if output:
                op_info["output_format"] = output.to_dict()
                current_format = output
            else:
                op_info["output_format"] = current_format.to_dict()
            
            analysis["operators"].append(op_info)
        
        analysis["final_format"] = current_format.to_dict()
        
        return analysis
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        """獲取 pipeline 信息"""
        info = super().get_pipeline_info()
        info["analysis"] = self.analyze_pipeline()
        return info


class PipelineManager:
    """
    Pipeline 管理器
    負責建立、管理和協調多個 Pipeline 實例
    """
    
    def __init__(self):
        """
        初始化 Pipeline Manager
        使用 ConfigManager 獲取配置
        """
        self.config_manager = ConfigManager()
        self.logger = logger
        
        # Pipeline 實例快取
        self.pipelines: Dict[str, PipelineBase] = {}
        
        # 可用的 Operator 類型註冊
        self.operator_registry: Dict[str, type] = {
            # "sample_rate": SampleRateOperator,  # 已移除，使用 audio_format 代替
            "audio_format": ScipyAudioFormatOperator,  # 預設使用 scipy 實現
            "audio_format_scipy": ScipyAudioFormatOperator,
            "audio_format_ffmpeg": FFmpegAudioFormatOperator,
            # TODO: 註冊其他 operators (vad, wakeword, recording)
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
            default_pipeline = DefaultPipeline()
            
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
    
    async def create_pipeline(self, name: str) -> PipelineBase:
        """
        建立新的 Pipeline
        
        Args:
            name: Pipeline 名稱
            
        Returns:
            建立的 Pipeline 實例
            
        Raises:
            PipelineError: 如果建立失敗
        """
        if name in self.pipelines:
            raise PipelineError(f"Pipeline '{name}' 已存在")
        
        try:
            # 建立 Pipeline (使用 ConfigManager)
            pipeline = DefaultPipeline()
            
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