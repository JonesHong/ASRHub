"""
ASR Hub Provider 基礎類別
定義所有 ASR 提供者的共同介面
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from src.utils.logger import logger
from src.core.exceptions import ProviderError, ModelError
from src.config.manager import ConfigManager


@dataclass
class TranscriptionResult:
    """轉譯結果資料類別"""
    text: str                          # 轉譯文字
    confidence: float                  # 信心分數 (0.0-1.0)
    language: Optional[str] = None     # 語言代碼
    start_time: Optional[float] = None # 開始時間（秒）
    end_time: Optional[float] = None   # 結束時間（秒）
    words: Optional[List[Dict]] = None # 詞級別資訊
    metadata: Optional[Dict] = None    # 額外元資料
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        result = {
            "text": self.text,
            "confidence": self.confidence
        }
        
        if self.language:
            result["language"] = self.language
        if self.start_time is not None:
            result["start_time"] = self.start_time
        if self.end_time is not None:
            result["end_time"] = self.end_time
        if self.words:
            result["words"] = self.words
        if self.metadata:
            result["metadata"] = self.metadata
            
        return result


@dataclass
class StreamingResult:
    """串流轉譯結果"""
    text: str                      # 當前片段文字
    is_final: bool                 # 是否為最終結果
    confidence: float              # 信心分數
    timestamp: float               # 時間戳記
    metadata: Optional[Dict] = None # 額外元資料


class ProviderBase(ABC):
    """
    ASR Provider 基礎抽象類別
    所有 ASR 提供者（Whisper、FunASR、Vosk 等）都需要繼承此類別
    """
    
    def __init__(self, provider_name: Optional[str] = None):
        """
        初始化 Provider
        
        Args:
            provider_name: Provider 名稱，如果不提供則使用類別名稱推測
        """
        self.logger = logger
        self.name = self.__class__.__name__
        self._initialized = False
        
        # 初始化 ConfigManager
        self.config_manager = ConfigManager()
        
        # 決定 provider 名稱
        if provider_name:
            self.provider_key = provider_name
        else:
            # 從類別名稱推測，例如 WhisperProvider -> whisper
            self.provider_key = self.name.replace('Provider', '').lower()
        
        # 獲取對應的配置
        try:
            provider_config = getattr(self.config_manager.providers, self.provider_key)
            
            # 模型相關配置 - 支援不同 provider 的屬性名稱
            # Whisper 使用 model_size，其他可能使用 model
            if hasattr(provider_config, 'model_size'):
                self.model_name = provider_config.model_size
            elif hasattr(provider_config, 'model'):
                self.model_name = provider_config.model
            else:
                self.model_name = "unknown"
            
            self.model_path = provider_config.model_path
            self.device = provider_config.device
            
            # 支援可選的 compute_type
            if hasattr(provider_config, 'compute_type'):
                self.compute_type = provider_config.compute_type
            else:
                self.compute_type = "default"
            
            # 語言設定
            self.language = provider_config.language
            self.supported_languages = []
            
            # 音訊參數 - 從 stream 配置獲取
            self.sample_rate = self.config_manager.stream.sample_rate
            self.channels = self.config_manager.stream.channels
            
        except AttributeError as e:
            self.logger.error(f"無法獲取 {self.provider_key} 的配置：{e}")
            raise ProviderError(f"Provider {self.provider_key} 配置不存在")
    
    async def initialize(self):
        """
        初始化 Provider
        載入模型、分配資源等
        """
        if self._initialized:
            self.logger.warning(f"{self.name} 已經初始化")
            return
        
        try:
            self.logger.info(f"初始化 {self.name}")
            await self._load_model()
            self._initialized = True
            self.logger.info(f"{self.name} 初始化完成")
        except Exception as e:
            self.logger.error(f"{self.name} 初始化失敗：{e}")
            raise ModelError(f"無法初始化 {self.name}：{str(e)}")
    
    async def cleanup(self):
        """
        清理 Provider
        釋放模型、清理資源等
        """
        if not self._initialized:
            self.logger.warning(f"{self.name} 未初始化")
            return
        
        try:
            self.logger.info(f"清理 {self.name}")
            await self._unload_model()
            self._initialized = False
            self.logger.info(f"{self.name} 清理完成")
        except Exception as e:
            self.logger.error(f"{self.name} 清理失敗：{e}")
    
    @abstractmethod
    async def _load_model(self):
        """
        載入 ASR 模型
        子類別需要實作此方法來載入特定的模型
        """
        pass
    
    @abstractmethod
    async def _unload_model(self):
        """
        卸載 ASR 模型
        子類別需要實作此方法來釋放模型資源
        """
        pass
    
    @abstractmethod
    async def transcribe(self, 
                        audio_data: bytes, 
                        **kwargs) -> TranscriptionResult:
        """
        執行單次語音轉譯
        
        Args:
            audio_data: 音訊資料（PCM 格式）
            **kwargs: 額外參數（如語言、提示詞等）
            
        Returns:
            轉譯結果
            
        Raises:
            ProviderError: 如果轉譯失敗
        """
        pass
    
    @abstractmethod
    async def transcribe_stream(self, 
                              audio_stream: AsyncGenerator[bytes, None],
                              **kwargs) -> AsyncGenerator[StreamingResult, None]:
        """
        執行串流語音轉譯
        
        Args:
            audio_stream: 音訊資料串流
            **kwargs: 額外參數
            
        Yields:
            串流轉譯結果
            
        Raises:
            ProviderError: 如果轉譯失敗
        """
        pass
    
    def is_initialized(self) -> bool:
        """檢查 Provider 是否已初始化"""
        return self._initialized
    
    def get_supported_languages(self) -> List[str]:
        """
        獲取支援的語言列表
        
        Returns:
            語言代碼列表
        """
        return self.supported_languages
    
    def supports_language(self, language: str) -> bool:
        """
        檢查是否支援指定語言
        
        Args:
            language: 語言代碼
            
        Returns:
            是否支援
        """
        return language in self.supported_languages or language == "auto"
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        獲取模型資訊
        
        Returns:
            模型資訊字典
        """
        return {
            "name": self.model_name,
            "path": self.model_path,
            "device": self.device,
            "compute_type": self.compute_type,
            "initialized": self._initialized
        }
    
    def get_provider_info(self) -> Dict[str, Any]:
        """
        獲取 Provider 資訊
        
        Returns:
            Provider 資訊字典
        """
        return {
            "name": self.name,
            "initialized": self._initialized,
            "model": self.get_model_info(),
            "supported_languages": self.supported_languages,
            "config": {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "language": self.language
            }
        }
    
    def validate_audio_format(self, audio_data: bytes) -> bool:
        """
        驗證音訊格式是否符合要求
        
        Args:
            audio_data: 音訊資料
            
        Returns:
            是否有效
        """
        if not audio_data:
            self.logger.warning("收到空的音訊資料")
            return False
        
        # 基本驗證，子類別可以擴展
        return True
    
    async def warmup(self):
        """
        預熱模型
        某些模型第一次推理較慢，可以預先執行一次推理來預熱
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            self.logger.debug("開始預熱模型")
            # 使用靜音資料進行預熱
            silence_duration = 1.0  # 1 秒靜音
            silence_samples = int(self.sample_rate * silence_duration)
            silence_data = bytes(silence_samples * 2)  # 16-bit PCM
            
            # 執行一次轉譯
            await self.transcribe(silence_data)
            self.logger.debug("模型預熱完成")
        except Exception as e:
            self.logger.warning(f"模型預熱失敗：{e}")
    
