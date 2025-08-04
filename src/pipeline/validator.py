"""
ASR Hub Pipeline Validator
驗證 Pipeline 配置和執行狀態
"""

from typing import Dict, Any, List, Optional
from src.utils.logger import logger
from src.pipeline.base import PipelineBase
from src.pipeline.operators.base import OperatorBase
from src.models.audio_format import AudioMetadata, AudioFormat


class PipelineValidator:
    """
    Pipeline 驗證器
    確保 Pipeline 配置正確且可以正常運行
    """
    
    def __init__(self):
        """初始化 Pipeline Validator"""
        self.logger = logger
        
        # 驗證規則
        self.validation_rules = {
            "required_operators": [],  # 必需的 Operator 列表
            "operator_order": [],      # Operator 順序限制
            "parameter_constraints": {}  # 參數約束
        }
    
    def validate_pipeline(self, pipeline: PipelineBase) -> Dict[str, Any]:
        """
        驗證 Pipeline 配置
        
        Args:
            pipeline: 要驗證的 Pipeline 實例
            
        Returns:
            驗證結果字典，包含：
                - valid: 是否有效
                - errors: 錯誤列表
                - warnings: 警告列表
                - info: 資訊列表
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "info": []
        }
        
        # 驗證基本配置
        self._validate_basic_config(pipeline, result)
        
        # 驗證 Operators
        self._validate_operators(pipeline, result)
        
        # 驗證 Operator 順序
        self._validate_operator_order(pipeline, result)
        
        # 驗證參數
        self._validate_parameters(pipeline, result)
        
        # 驗證相容性
        self._validate_compatibility(pipeline, result)
        
        # 設定最終有效性
        result["valid"] = len(result["errors"]) == 0
        
        # 記錄驗證結果
        if result["valid"]:
            self.logger.debug(f"Pipeline 驗證通過，警告數：{len(result['warnings'])}")
        else:
            self.logger.warning(f"Pipeline 驗證失敗，錯誤數：{len(result['errors'])}")
        
        return result
    
    def _validate_basic_config(self, pipeline: PipelineBase, result: Dict[str, Any]):
        """驗證基本配置"""
        # 檢查 Pipeline 名稱
        if not hasattr(pipeline, 'name') or not pipeline.name:
            result["warnings"].append("Pipeline 缺少名稱")
        
        # 檢查配置物件
        if not hasattr(pipeline, 'config') or not pipeline.config:
            result["errors"].append("Pipeline 缺少配置")
            return
        
        # 檢查必要的配置項目
        required_config_keys = ["sample_rate", "channels"]
        for key in required_config_keys:
            if key not in pipeline.config:
                result["errors"].append(f"配置缺少必要項目：{key}")
        
        # 檢查取樣率
        if "sample_rate" in pipeline.config:
            sample_rate = pipeline.config["sample_rate"]
            if sample_rate not in [8000, 16000, 22050, 44100, 48000]:
                result["warnings"].append(
                    f"非標準取樣率：{sample_rate} Hz，可能影響處理效能"
                )
        
        # 檢查聲道數
        if "channels" in pipeline.config:
            channels = pipeline.config["channels"]
            if channels < 1 or channels > 8:
                result["errors"].append(f"無效的聲道數：{channels}")
    
    def _validate_operators(self, pipeline: PipelineBase, result: Dict[str, Any]):
        """驗證 Operators"""
        if not hasattr(pipeline, 'operators') or not pipeline.operators:
            result["info"].append("Pipeline 沒有配置任何 Operators")
            return
        
        # 檢查每個 Operator
        for i, operator in enumerate(pipeline.operators):
            # 檢查是否為有效的 Operator
            if not isinstance(operator, OperatorBase):
                result["errors"].append(
                    f"第 {i+1} 個 Operator 不是有效的 OperatorBase 實例"
                )
                continue
            
            # 檢查 Operator 是否已初始化
            if hasattr(operator, '_initialized') and not operator._initialized:
                result["warnings"].append(
                    f"Operator '{operator.__class__.__name__}' 尚未初始化"
                )
            
            # 檢查 Operator 配置
            if hasattr(operator, 'config'):
                self._validate_operator_config(operator, i, result)
    
    def _validate_operator_config(self, 
                                 operator: OperatorBase, 
                                 index: int,
                                 result: Dict[str, Any]):
        """驗證單個 Operator 的配置"""
        operator_name = operator.__class__.__name__
        
        # 檢查是否啟用
        if hasattr(operator, 'enabled') and not operator.enabled:
            result["info"].append(f"Operator '{operator_name}' 已停用")
            return
        
        # 特定 Operator 的驗證
        if operator_name == "AudioFormatOperator":
            # 檢查音頻格式設定
            if hasattr(operator, 'target_metadata'):
                target_metadata = operator.target_metadata
                if target_metadata.sample_rate not in [8000, 16000, 22050, 44100, 48000]:
                    result["warnings"].append(
                        f"AudioFormatOperator 使用非標準取樣率：{target_metadata.sample_rate} Hz"
                    )
                if target_metadata.channels > 2:
                    result["warnings"].append(
                        f"AudioFormatOperator 目標聲道數過多：{target_metadata.channels}"
                    )
        
        # 檢查緩衝區大小（如果適用）
        if hasattr(operator, 'buffer_size'):
            buffer_size = operator.buffer_size
            if buffer_size < 1024:
                result["warnings"].append(
                    f"Operator '{operator_name}' 的緩衝區太小：{buffer_size}"
                )
            elif buffer_size > 65536:
                result["warnings"].append(
                    f"Operator '{operator_name}' 的緩衝區太大：{buffer_size}"
                )
    
    def _validate_operator_order(self, pipeline: PipelineBase, result: Dict[str, Any]):
        """驗證 Operator 順序"""
        if not hasattr(pipeline, 'operators') or len(pipeline.operators) < 2:
            return
        
        # 建立 Operator 類型列表
        operator_types = [op.__class__.__name__ for op in pipeline.operators]
        
        # 檢查建議的順序
        # 音頻格式轉換應該在 VAD/WakeWord 之前
        if "AudioFormatOperator" in operator_types:
            format_index = operator_types.index("AudioFormatOperator")
            processing_operators = ["VADOperator", "SileroVADOperator", "OpenWakeWordOperator"]
            
            for proc_op in processing_operators:
                if proc_op in operator_types:
                    proc_index = operator_types.index(proc_op)
                    if format_index > proc_index:
                        result["warnings"].append(
                            f"建議將 AudioFormatOperator 放在 {proc_op} 之前，"
                            f"確保音頻格式正確"
                        )
        
        # 檢查降噪應該在其他處理之前
        if "DenoiseOperator" in operator_types:
            denoise_index = operator_types.index("DenoiseOperator")
            if denoise_index > 0:
                result["info"].append(
                    "建議將 DenoiseOperator 作為第一個 Operator 以獲得最佳效果"
                )
    
    def _validate_parameters(self, pipeline: PipelineBase, result: Dict[str, Any]):
        """驗證參數約束"""
        # 檢查 Pipeline 層級的參數
        if hasattr(pipeline, 'config'):
            config = pipeline.config
            
            # 檢查緩衝區大小與取樣率的關係
            if "buffer_size" in config and "sample_rate" in config:
                buffer_size = config["buffer_size"]
                sample_rate = config["sample_rate"]
                
                # 計算緩衝區時長
                buffer_duration = buffer_size / (sample_rate * 2)  # 假設 16-bit
                
                if buffer_duration < 0.01:  # 小於 10ms
                    result["warnings"].append(
                        f"緩衝區時長太短：{buffer_duration*1000:.1f}ms，可能導致處理不穩定"
                    )
                elif buffer_duration > 1.0:  # 大於 1 秒
                    result["warnings"].append(
                        f"緩衝區時長太長：{buffer_duration:.2f}秒，可能增加延遲"
                    )
    
    def _validate_compatibility(self, pipeline: PipelineBase, result: Dict[str, Any]):
        """驗證相容性"""
        if not hasattr(pipeline, 'operators') or not pipeline.operators:
            return
        
        # 檢查 Operator 之間的相容性
        for i in range(len(pipeline.operators) - 1):
            current_op = pipeline.operators[i]
            next_op = pipeline.operators[i + 1]
            
            # 檢查輸出格式相容性
            if hasattr(current_op, 'output_format') and hasattr(next_op, 'input_format'):
                if current_op.output_format != next_op.input_format:
                    result["errors"].append(
                        f"Operator 格式不相容：{current_op.__class__.__name__} "
                        f"輸出 {current_op.output_format}，但 "
                        f"{next_op.__class__.__name__} 需要 {next_op.input_format}"
                    )
    
    def validate_runtime_state(self, pipeline: PipelineBase) -> Dict[str, Any]:
        """
        驗證 Pipeline 的執行時狀態
        
        Args:
            pipeline: Pipeline 實例
            
        Returns:
            驗證結果
        """
        result = {
            "healthy": True,
            "issues": [],
            "stats": {}
        }
        
        # 檢查 Pipeline 是否正在運行
        if hasattr(pipeline, 'is_running') and callable(pipeline.is_running):
            if not pipeline.is_running():
                result["healthy"] = False
                result["issues"].append("Pipeline 未在運行")
        
        # 檢查 Operator 狀態
        if hasattr(pipeline, 'operators'):
            for operator in pipeline.operators:
                if hasattr(operator, 'get_stats') and callable(operator.get_stats):
                    stats = operator.get_stats()
                    operator_name = operator.__class__.__name__
                    result["stats"][operator_name] = stats
                    
                    # 檢查錯誤率
                    if "error_count" in stats and "processed_count" in stats:
                        if stats["processed_count"] > 0:
                            error_rate = stats["error_count"] / stats["processed_count"]
                            if error_rate > 0.1:  # 錯誤率超過 10%
                                result["healthy"] = False
                                result["issues"].append(
                                    f"{operator_name} 錯誤率過高：{error_rate*100:.1f}%"
                                )
        
        return result
    
    def suggest_optimizations(self, pipeline: PipelineBase) -> List[str]:
        """
        根據 Pipeline 配置提供優化建議
        
        Args:
            pipeline: Pipeline 實例
            
        Returns:
            優化建議列表
        """
        suggestions = []
        
        # 檢查是否缺少常用的 Operators
        if hasattr(pipeline, 'operators'):
            operator_types = [op.__class__.__name__ for op in pipeline.operators]
            
            # VAD 建議
            if "VADOperator" not in operator_types:
                suggestions.append(
                    "建議添加 VAD (Voice Activity Detection) 以減少靜音處理"
                )
            
            # 降噪建議
            if "DenoiseOperator" not in operator_types:
                suggestions.append(
                    "建議添加降噪處理以提高辨識準確率"
                )
            
            # 音頻格式轉換建議
            if "AudioFormatOperator" not in operator_types:
                if hasattr(pipeline, 'config'):
                    sample_rate = pipeline.config.get("sample_rate", 0)
                    channels = pipeline.config.get("channels", 1)
                    
                    # 檢查是否需要格式轉換
                    needs_conversion = False
                    conversion_reasons = []
                    
                    if sample_rate != 16000:
                        needs_conversion = True
                        conversion_reasons.append(f"採樣率 {sample_rate}Hz → 16000Hz")
                    
                    if channels > 1:
                        needs_conversion = True
                        conversion_reasons.append(f"{channels} 聲道 → 單聲道")
                    
                    if needs_conversion:
                        suggestions.append(
                            f"建議添加 AudioFormatOperator 進行格式轉換：" + 
                            "、".join(conversion_reasons) + 
                            " 以獲得最佳處理效果"
                        )
        
        # 緩衝區大小建議
        if hasattr(pipeline, 'config'):
            buffer_size = pipeline.config.get("buffer_size", 0)
            sample_rate = pipeline.config.get("sample_rate", 16000)
            
            optimal_buffer_size = int(sample_rate * 0.1 * 2)  # 100ms 的資料
            if abs(buffer_size - optimal_buffer_size) > optimal_buffer_size * 0.5:
                suggestions.append(
                    f"建議將緩衝區大小調整為 {optimal_buffer_size} "
                    f"（約 100ms）以平衡延遲和效能"
                )
        
        return suggestions