"""
音訊格式檢查器
用於 Pipeline 中的格式驗證和自動轉換
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from src.models.audio import AudioChunk, AudioFormat, AudioEncoding
from src.models.audio_metadata import AudioMetadata
from src.pipeline.operators.base import OperatorBase
from src.utils.logger import logger


@dataclass
class FormatRequirement:
    """格式需求定義"""
    sample_rates: Optional[List[int]] = None  # None 表示任意
    channels: Optional[List[int]] = None
    formats: Optional[List[AudioFormat]] = None
    encodings: Optional[List[AudioEncoding]] = None
    bits_per_sample: Optional[List[int]] = None
    
    def is_satisfied_by(self, audio_chunk: AudioChunk) -> bool:
        """檢查音訊是否滿足需求"""
        if self.sample_rates and audio_chunk.sample_rate not in self.sample_rates:
            return False
        if self.channels and audio_chunk.channels not in self.channels:
            return False
        if self.formats and audio_chunk.format not in self.formats:
            return False
        if self.encodings and audio_chunk.encoding not in self.encodings:
            return False
        if self.bits_per_sample and audio_chunk.bits_per_sample not in self.bits_per_sample:
            return False
        return True
    
    def get_conversion_target(self, audio_chunk: AudioChunk) -> Optional[AudioMetadata]:
        """獲取轉換目標格式"""
        if self.is_satisfied_by(audio_chunk):
            return None
        
        # 選擇最接近的目標格式
        target = AudioMetadata(
            sample_rate=audio_chunk.sample_rate,
            channels=audio_chunk.channels,
            format=audio_chunk.format,
            encoding=audio_chunk.encoding,
            bits_per_sample=audio_chunk.bits_per_sample
        )
        
        # 優先級：保持原格式 > 選擇第一個支援的格式
        if self.sample_rates and audio_chunk.sample_rate not in self.sample_rates:
            # 選擇最接近的取樣率
            target.sample_rate = min(self.sample_rates, 
                                    key=lambda x: abs(x - audio_chunk.sample_rate))
        
        if self.channels and audio_chunk.channels not in self.channels:
            target.channels = self.channels[0]
        
        if self.formats and audio_chunk.format not in self.formats:
            target.format = self.formats[0]
        
        if self.encodings and audio_chunk.encoding not in self.encodings:
            target.encoding = self.encodings[0]
        
        if self.bits_per_sample and audio_chunk.bits_per_sample not in self.bits_per_sample:
            target.bits_per_sample = self.bits_per_sample[0]
        
        return target


class AudioFormatChecker:
    """
    音訊格式檢查器
    用於分析 Pipeline 中的格式需求並規劃轉換
    """
    
    # 常見 Operator 的格式需求
    OPERATOR_REQUIREMENTS = {
        "SileroVAD": FormatRequirement(
            sample_rates=[16000],
            channels=[1],
            formats=[AudioFormat.PCM],
            encodings=[AudioEncoding.FLOAT32]
        ),
        "OpenWakeWord": FormatRequirement(
            sample_rates=[16000],
            channels=[1],
            formats=[AudioFormat.PCM],
            encodings=[AudioEncoding.LINEAR16]
        ),
        "WhisperProvider": FormatRequirement(
            sample_rates=[16000],
            channels=[1],
            formats=[AudioFormat.PCM],
            encodings=[AudioEncoding.FLOAT32]
        ),
        "VoskProvider": FormatRequirement(
            sample_rates=[16000, 8000],
            channels=[1],
            formats=[AudioFormat.PCM],
            encodings=[AudioEncoding.LINEAR16]
        ),
        "GoogleSTTProvider": FormatRequirement(
            sample_rates=[16000, 8000, 44100, 48000],
            channels=[1, 2],
            formats=[AudioFormat.PCM, AudioFormat.FLAC],
            encodings=[AudioEncoding.LINEAR16, AudioEncoding.FLAC]
        )
    }
    
    @classmethod
    def analyze_pipeline(
        cls,
        operators: List[OperatorBase],
        provider_name: Optional[str] = None
    ) -> List[Tuple[int, str, AudioMetadata]]:
        """
        分析 Pipeline 的格式需求
        
        Args:
            operators: Operator 列表
            provider_name: Provider 名稱
            
        Returns:
            需要插入的格式轉換列表 [(位置, 轉換器類型, 目標格式)]
        """
        conversions = []
        current_format = None
        
        # 分析每個 Operator 的需求
        for i, operator in enumerate(operators):
            operator_name = operator.__class__.__name__
            requirement = cls.OPERATOR_REQUIREMENTS.get(operator_name)
            
            if requirement and current_format:
                target = requirement.get_conversion_target(current_format)
                if target:
                    # 需要在這個 Operator 前插入轉換
                    converter_type = cls._select_converter(current_format, target)
                    conversions.append((i, converter_type, target))
                    current_format = target
        
        # 檢查 Provider 需求
        if provider_name and current_format:
            requirement = cls.OPERATOR_REQUIREMENTS.get(provider_name)
            if requirement:
                target = requirement.get_conversion_target(current_format)
                if target:
                    converter_type = cls._select_converter(current_format, target)
                    conversions.append((len(operators), converter_type, target))
        
        return conversions
    
    @classmethod
    def _select_converter(
        cls,
        source: AudioMetadata,
        target: AudioMetadata
    ) -> str:
        """選擇合適的轉換器"""
        # 如果只是取樣率不同
        if (source.channels == target.channels and
            source.format == target.format and
            source.encoding == target.encoding and
            source.bits_per_sample == target.bits_per_sample):
            return "SampleRateConverter"
        
        # 如果需要格式轉換
        if source.format != target.format:
            return "FFmpegOperator"
        
        # 預設使用 SciPy 轉換器
        return "ScipyOperator"
    
    @classmethod
    def validate_audio_chunk(
        cls,
        audio_chunk: AudioChunk,
        operator_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        驗證音訊是否符合 Operator 需求
        
        Args:
            audio_chunk: 音訊塊
            operator_name: Operator 名稱
            
        Returns:
            (是否有效, 錯誤訊息)
        """
        requirement = cls.OPERATOR_REQUIREMENTS.get(operator_name)
        if not requirement:
            return True, None
        
        if not requirement.is_satisfied_by(audio_chunk):
            errors = []
            
            if requirement.sample_rates and audio_chunk.sample_rate not in requirement.sample_rates:
                errors.append(f"取樣率 {audio_chunk.sample_rate} 不在支援範圍 {requirement.sample_rates}")
            
            if requirement.channels and audio_chunk.channels not in requirement.channels:
                errors.append(f"聲道數 {audio_chunk.channels} 不在支援範圍 {requirement.channels}")
            
            if requirement.formats and audio_chunk.format not in requirement.formats:
                errors.append(f"格式 {audio_chunk.format.value} 不在支援範圍 {[f.value for f in requirement.formats]}")
            
            if requirement.encodings and audio_chunk.encoding not in requirement.encodings:
                errors.append(f"編碼 {audio_chunk.encoding.value} 不在支援範圍 {[e.value for e in requirement.encodings]}")
            
            if requirement.bits_per_sample and audio_chunk.bits_per_sample not in requirement.bits_per_sample:
                errors.append(f"位元深度 {audio_chunk.bits_per_sample} 不在支援範圍 {requirement.bits_per_sample}")
            
            return False, "; ".join(errors)
        
        return True, None
    
    @classmethod
    def log_format_info(cls, audio_chunk: AudioChunk, context: str = ""):
        """記錄格式資訊"""
        duration_info = f"\n  時長: {audio_chunk.duration:.2f}秒" if audio_chunk.duration else ""
        
        logger.info(
            f"{context}音訊格式資訊:\n"
            f"  取樣率: {audio_chunk.sample_rate} Hz\n"
            f"  聲道數: {audio_chunk.channels}\n"
            f"  格式: {audio_chunk.format.value}\n"
            f"  編碼: {audio_chunk.encoding.value}\n"
            f"  位元深度: {audio_chunk.bits_per_sample} bit"
            f"{duration_info}"
        )