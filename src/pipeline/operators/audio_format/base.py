#!/usr/bin/env python3
"""
音頻格式轉換 Operator 基礎類
定義音頻格式轉換的通用接口和功能
"""

from typing import Optional, Dict, Any
from abc import abstractmethod
import numpy as np

from src.pipeline.operators.base import BufferingOperator
from src.utils.logger import logger
from src.core.exceptions import PipelineError, AudioFormatError
from src.models.audio_format import AudioMetadata, AudioFormat


class AudioFormatOperatorBase(BufferingOperator):
    """
    音頻格式轉換 Operator 基礎類
    提供音頻格式轉換的通用功能和接口
    """
    
    def __init__(self, operator_id: str = 'default', target_metadata: Optional[AudioMetadata] = None):
        """
        初始化音頻格式轉換 Operator
        
        Args:
            operator_id: 操作器識別ID
            target_metadata: 目標音頻格式元數據
        """
        # 獲取配置
        from src.config.manager import ConfigManager
        self.config_manager = ConfigManager()
        
        # 取得 buffer size
        try:
            buffer_size = self.config_manager.pipeline.buffer_size
        except AttributeError:
            buffer_size = 8192
        
        super().__init__(buffer_size)
        
        self.logger = logger
        self.operator_id = operator_id
        
        # 設定目標元數據
        if target_metadata:
            self.target_metadata = target_metadata
        else:
            # 從配置中取得
            try:
                if hasattr(self.config_manager.pipeline, 'audio_format'):
                    af_config = self.config_manager.pipeline.audio_format
                    self.target_metadata = AudioMetadata(
                        sample_rate=af_config.sample_rate,
                        channels=af_config.channels,
                        format=AudioFormat(af_config.format)
                    )
                else:
                    # 使用 pipeline 配置作為預設值
                    self.target_metadata = AudioMetadata(
                        sample_rate=self.config_manager.pipeline.default_sample_rate,
                        channels=self.config_manager.pipeline.channels,
                        format=AudioFormat.INT16
                    )
            except AttributeError:
                # 最後的備用預設值
                self.target_metadata = AudioMetadata(
                    sample_rate=16000,
                    channels=1,
                    format=AudioFormat.INT16
                )
        
        # 轉換品質設定
        try:
            if hasattr(self.config_manager.pipeline, 'audio_format') and hasattr(self.config_manager.pipeline.audio_format, 'quality'):
                self.quality = self.config_manager.pipeline.audio_format.quality
            else:
                self.quality = 'medium'
        except AttributeError:
            self.quality = 'medium'
        
        # 當前輸入格式
        self.current_input_metadata = None
        
        self.logger.info(
            f"AudioFormatOperator[{self.operator_id}] 初始化 - "
            f"目標格式: {self.target_metadata.sample_rate}Hz, "
            f"{self.target_metadata.channels}ch, {self.target_metadata.format.value}"
        )
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音頻數據，轉換為目標格式
        
        Args:
            audio_data: 輸入音頻數據
            **kwargs: 額外參數
                - metadata: AudioMetadata 對象
                - sample_rate: 採樣率
                - channels: 聲道數
                - format: 音頻格式
                
        Returns:
            轉換後的音頻數據
        """
        if not self.enabled:
            return audio_data
            
        if not audio_data:
            return None
            
        try:
            # 獲取輸入元數據
            input_metadata = self._get_input_metadata(kwargs)
            
            # 檢查是否需要轉換
            if input_metadata == self.target_metadata:
                self.logger.debug(f"[{self.operator_id}] 音頻格式已符合目標，無需轉換")
                return audio_data
            
            # 記錄轉換信息
            self.logger.debug(
                f"[{self.operator_id}] 格式轉換: "
                f"{input_metadata.sample_rate}Hz {input_metadata.channels}ch {input_metadata.format.value} -> "
                f"{self.target_metadata.sample_rate}Hz {self.target_metadata.channels}ch {self.target_metadata.format.value}"
            )
            
            # 執行具體的轉換（由子類實現）
            converted_data = await self._convert_format(
                audio_data,
                input_metadata,
                self.target_metadata
            )
            
            # 更新統計
            self._update_statistics(len(audio_data), len(converted_data))
            
            return converted_data
            
        except Exception as e:
            self.logger.error(f"[{self.operator_id}] 音頻格式轉換失敗: {e}")
            raise PipelineError(f"音頻格式轉換失敗: {str(e)}")
    
    @abstractmethod
    async def _convert_format(self, audio_data: bytes, 
                            from_metadata: AudioMetadata,
                            to_metadata: AudioMetadata) -> bytes:
        """
        執行實際的格式轉換（由子類實現）
        
        Args:
            audio_data: 原始音頻數據
            from_metadata: 來源音頻元數據
            to_metadata: 目標音頻元數據
            
        Returns:
            轉換後的音頻數據
        """
        pass
    
    def _get_input_metadata(self, kwargs: Dict[str, Any]) -> AudioMetadata:
        """從參數中獲取輸入元數據"""
        # 優先使用 metadata 對象
        if 'metadata' in kwargs and isinstance(kwargs['metadata'], AudioMetadata):
            return kwargs['metadata']
        
        # 從單獨的參數構建
        sample_rate = kwargs.get('sample_rate', kwargs.get('input_rate', 16000))
        channels = kwargs.get('channels', 1)
        format_str = kwargs.get('format', kwargs.get('encoding', 'int16'))
        
        # 映射編碼格式
        format_map = {
            'linear16': AudioFormat.INT16,
            'linear32': AudioFormat.INT32,
            'int16': AudioFormat.INT16,
            'int24': AudioFormat.INT24,
            'int32': AudioFormat.INT32,
            'float32': AudioFormat.FLOAT32
        }
        
        audio_format = format_map.get(format_str.lower(), AudioFormat.INT16)
        
        return AudioMetadata(
            sample_rate=sample_rate,
            channels=channels,
            format=audio_format
        )
    
    def _update_statistics(self, input_size: int, output_size: int):
        """更新統計信息"""
        ratio = output_size / input_size if input_size > 0 else 0
        self.logger.debug(
            f"[{self.operator_id}] 轉換完成 - "
            f"輸入: {input_size} bytes, 輸出: {output_size} bytes, "
            f"比例: {ratio:.2f}"
        )
    
    def _to_numpy(self, audio_data: bytes, metadata: AudioMetadata) -> np.ndarray:
        """將音頻數據轉換為 numpy array"""
        if metadata.format == AudioFormat.INT24:
            # 特殊處理 24-bit
            samples = []
            for i in range(0, len(audio_data), 3):
                if i + 2 < len(audio_data):
                    sample = (audio_data[i] | 
                             (audio_data[i+1] << 8) | 
                             (audio_data[i+2] << 16))
                    if sample & 0x800000:
                        sample |= 0xFF000000
                    samples.append(sample)
            return np.array(samples, dtype=np.int32)
        else:
            # 其他格式直接轉換
            return np.frombuffer(audio_data, dtype=metadata.format.numpy_dtype)
    
    def _from_numpy(self, samples: np.ndarray, format: AudioFormat) -> bytes:
        """將 numpy array 轉換為音頻數據"""
        if format == AudioFormat.INT24:
            # 特殊處理 24-bit
            raise NotImplementedError("24-bit output not yet implemented")
        else:
            # 轉換數據類型
            if format == AudioFormat.FLOAT32:
                # 確保在 -1.0 到 1.0 範圍內
                samples = np.clip(samples, -1.0, 1.0)
            elif format == AudioFormat.INT16:
                # 確保在有效範圍內
                samples = np.clip(samples, -32768, 32767)
            elif format == AudioFormat.INT32:
                # 確保在有效範圍內
                samples = np.clip(samples, -2147483648, 2147483647)
            
            return samples.astype(format.numpy_dtype).tobytes()
    
    def get_info(self) -> Dict[str, Any]:
        """獲取 Operator 信息"""
        info = super().get_info()
        info.update({
            "operator_id": self.operator_id,
            "operator_type": self.__class__.__name__,
            "target_format": self.target_metadata.to_dict(),
            "quality": self.quality,
            "current_input": self.current_input_metadata.to_dict() if self.current_input_metadata else None
        })
        return info
    
    def update_config(self, config: Dict[str, Any]):
        """
        動態更新配置
        
        Args:
            config: 新配置，可包含：
                - target_metadata: AudioMetadata 對象
                - target_format: 目標格式字典
                - quality: 轉換品質
        """
        super().update_config(config)
        
        # 優先使用 AudioMetadata 對象
        if 'target_metadata' in config and isinstance(config['target_metadata'], AudioMetadata):
            self.target_metadata = config['target_metadata']
            self.logger.info(
                f"[{self.operator_id}] 目標格式更新為: "
                f"{self.target_metadata.sample_rate}Hz, "
                f"{self.target_metadata.channels}ch, "
                f"{self.target_metadata.format.value}"
            )
        # 支援字典格式
        elif 'target_format' in config:
            target_config = config['target_format']
            self.target_metadata = AudioMetadata(
                sample_rate=target_config.get('sample_rate', self.target_metadata.sample_rate),
                channels=target_config.get('channels', self.target_metadata.channels),
                format=AudioFormat(target_config.get('format', self.target_metadata.format.value))
            )
            self.logger.info(
                f"[{self.operator_id}] 目標格式更新為: "
                f"{self.target_metadata.sample_rate}Hz, "
                f"{self.target_metadata.channels}ch, "
                f"{self.target_metadata.format.value}"
            )
        
        # 更新品質
        if 'quality' in config:
            self.quality = config['quality']
            self.logger.info(f"[{self.operator_id}] 轉換品質更新為: {self.quality}")
    
    async def flush(self):
        """清空緩衝區"""
        await super().flush()
        self.logger.debug(f"[{self.operator_id}] 緩衝區已清空")
    
    def get_chunk_size_for_rate(self, sample_rate: int, base_chunk: int = 512) -> int:
        """
        根據採樣率計算合適的 chunk size
        
        Args:
            sample_rate: 採樣率
            base_chunk: 基準 chunk size（針對 16000 Hz）
            
        Returns:
            調整後的 chunk size
        """
        # 基準採樣率
        base_rate = 16000
        
        # 按比例調整 chunk size
        adjusted_chunk = int(base_chunk * sample_rate / base_rate)
        
        # 確保是偶數（對於 16-bit 音頻）
        if adjusted_chunk % 2 != 0:
            adjusted_chunk += 1
            
        return adjusted_chunk