"""
ASR Hub Operator Validator
驗證 Operator 配置和執行狀態
"""

from typing import Dict, Any, List, Optional
from src.utils.logger import logger
from src.operators.base import OperatorBase
from src.audio import AudioMetadata, AudioSampleFormat as AudioFormat


class OperatorValidator:
    """
    Operator 驗證器
    確保 Operator 配置正確且可以正常運行
    """
    
    def __init__(self):
        """初始化 Operator Validator"""
        
        # 驗證規則
        self.validation_rules = {
            "required_operators": [],  # 必需的 Operator 列表
            "operator_order": [],      # Operator 順序限制
            "parameter_constraints": {}  # 參數約束
        }
    
    def validate_operators(self, operators: List[OperatorBase]) -> Dict[str, Any]:
        """
        驗證 Operator 列表配置
        
        Args:
            operators: 要驗證的 Operator 列表
            
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
        
        # 驗證 Operators
        self._validate_operator_list(operators, result)
        
        # 驗證 Operator 順序
        self._validate_operator_order(operators, result)
        
        # 驗證相容性
        self._validate_compatibility(operators, result)
        
        # 設定最終有效性
        result["valid"] = len(result["errors"]) == 0
        
        # 記錄驗證結果
        if result["valid"]:
            logger.debug(f"Operator 驗證通過，警告數：{len(result['warnings'])}")
        else:
            logger.warning(f"Operator 驗證失敗，錯誤數：{len(result['errors'])}")
        
        return result
    
    def _validate_operator_list(self, operators: List[OperatorBase], result: Dict[str, Any]):
        """驗證 Operator 列表"""
        if not operators:
            result["info"].append("沒有配置任何 Operators")
            return
        
        # 檢查每個 Operator
        for i, operator in enumerate(operators):
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
    
    def _validate_operator_order(self, operators: List[OperatorBase], result: Dict[str, Any]):
        """驗證 Operator 順序"""
        if len(operators) < 2:
            return
        
        # 建立 Operator 類型列表
        operator_types = [op.__class__.__name__ for op in operators]
        
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
    
    def _validate_compatibility(self, operators: List[OperatorBase], result: Dict[str, Any]):
        """驗證相容性"""
        if not operators:
            return
        
        # 檢查 Operator 之間的相容性
        for i in range(len(operators) - 1):
            current_op = operators[i]
            next_op = operators[i + 1]
            
            # 檢查輸出格式相容性
            if hasattr(current_op, 'output_format') and hasattr(next_op, 'input_format'):
                if current_op.output_format != next_op.input_format:
                    result["errors"].append(
                        f"Operator 格式不相容：{current_op.__class__.__name__} "
                        f"輸出 {current_op.output_format}，但 "
                        f"{next_op.__class__.__name__} 需要 {next_op.input_format}"
                    )
    
    def validate_runtime_state(self, operators: List[OperatorBase]) -> Dict[str, Any]:
        """
        驗證 Operator 的執行時狀態
        
        Args:
            operators: Operator 列表
            
        Returns:
            驗證結果
        """
        result = {
            "healthy": True,
            "issues": [],
            "stats": {}
        }
        
        # 檢查 Operator 狀態
        for operator in operators:
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
    
    def suggest_optimizations(self, operators: List[OperatorBase]) -> List[str]:
        """
        根據 Operator 配置提供優化建議
        
        Args:
            operators: Operator 列表
            
        Returns:
            優化建議列表
        """
        suggestions = []
        
        if not operators:
            suggestions.append("建議添加必要的 Operators 進行音訊處理")
            return suggestions
        
        operator_types = [op.__class__.__name__ for op in operators]
        
        # VAD 建議
        if "VADOperator" not in operator_types and "SileroVADOperator" not in operator_types:
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
            suggestions.append(
                "建議添加 AudioFormatOperator 進行格式標準化"
            )
        
        return suggestions