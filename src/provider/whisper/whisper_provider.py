"""OpenAI Whisper ASR Provider - MVP 檔案轉譯版本

核心職責：
1. 載入 OpenAI Whisper 模型
2. 轉譯檔案路徑的音訊
3. 返回標準化的轉譯結果

遵守 MVP & KISS 原則，只支援檔案路徑轉譯。
"""

import threading
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
import numpy as np
import time

from src.interface.asr_provider import (
    IASRProvider, 
    ASRConfig, 
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionStatus
)
from src.utils.logger import logger
from src.interface.exceptions import (
    ServiceInitializationError,
    ServiceExecutionError 
)
from src.config.manager import ConfigManager


class WhisperProvider(IASRProvider):
    """簡化版 OpenAI Whisper ASR 提供者
    
    只支援檔案路徑轉譯，移除所有串流和 session 管理複雜性。
    支援單例和非單例模式：
    - 單例模式：WhisperProvider() 或 WhisperProvider.get_singleton()
    - 非單例模式：WhisperProvider(singleton=False) - 用於 provider pool
    """
    
    _singleton_instance = None
    _singleton_lock = threading.Lock()
    
    def __new__(cls, singleton: bool = True):
        """建立實例（支援單例/非單例模式）"""
        if singleton:
            # 單例模式
            if cls._singleton_instance is None:
                with cls._singleton_lock:
                    if cls._singleton_instance is None:
                        cls._singleton_instance = super().__new__(cls)
            return cls._singleton_instance
        else:
            # 非單例模式（為 provider pool 使用）
            return super().__new__(cls)
    
    def __init__(self, singleton: bool = True):
        """初始化 Provider
        
        Args:
            singleton: 是否使用單例模式（預設為 True 以保持向後相容）
        """
        # 避免重複初始化（單例模式）
        if singleton and hasattr(self, '_initialized') and self._initialized:
            return
            
        if not hasattr(self, '_initialized'):
            self._initialized = False
            self._model = None
            self._config = None
            self._transcribe_lock = threading.Lock()  # 確保執行緒安全
            
            # 自動載入配置和模型
            self._load_config()
            if self._config:
                try:
                    self._load_model()
                    self._initialized = True
                    logger.info(f"WhisperProvider MVP 初始化成功 (singleton={singleton})")
                except Exception as e:
                    logger.error(f"模型載入失敗: {e}")
    
    def _load_config(self) -> None:
        """從 ConfigManager 載入配置"""
        try:
            config_manager = ConfigManager()
            if hasattr(config_manager, 'providers') and hasattr(config_manager.providers, 'whisper'):
                whisper_config = config_manager.providers.whisper
                
                self._config = ASRConfig(
                    model_name=whisper_config.model_size or "base",
                    language=whisper_config.language,
                    device=whisper_config.whisper_device or "cpu",
                    compute_type="default",  # OpenAI Whisper doesn't use this
                    beam_size=5,
                    temperature=0.0
                )
        except Exception as e:
            logger.warning(f"載入配置失敗，使用預設值: {e}")
            self._config = ASRConfig(
                model_name="base",
                device="cpu",
                compute_type="default"
            )
    
    def _load_model(self) -> None:
        """載入 OpenAI Whisper 模型"""
        try:
            import whisper
        except ImportError as e:
            raise ServiceInitializationError(
                "openai-whisper 未安裝。請執行: pip install openai-whisper"
            ) from e
        
        logger.info(f"載入模型: {self._config.model_name} on {self._config.device}")
        
        # Load model with specified device
        self._model = whisper.load_model(
            name=self._config.model_name,
            device=self._config.device
        )
        
        logger.info("模型載入成功")
    
    def transcribe_file(self, file_path: str) -> TranscriptionResult:
        """轉譯檔案（核心功能）
        
        Args:
            file_path: 音訊檔案路徑
            
        Returns:
            轉譯結果
        """
        if not self._initialized or not self._model:
            raise ServiceInitializationError("服務未初始化")
        
        if not Path(file_path).exists():
            raise ServiceExecutionError(f"檔案不存在: {file_path}")
        
        start_time = time.time()
        
        # 記錄接收到的檔案資訊
        file_size = Path(file_path).stat().st_size
        logger.info(f"🎯 [ASR_RECEIVED] Whisper transcribing file:")
        logger.info(f"   - File Path: {file_path}")
        logger.info(f"   - File Size: {file_size} bytes ({file_size/1024:.1f} KB)")
        logger.info(f"   - Language: {self._config.language}")
        logger.info(f"   - Model: {self._config.model_name}")
        
        try:
            # 使用 lock 確保執行緒安全
            with self._transcribe_lock:
                # 執行轉譯
                result = self._model.transcribe(
                    file_path,
                    language=self._config.language,
                    task="transcribe",
                    temperature=self._config.temperature,
                    verbose=False
                )
                
                # 收集所有片段
                segments = []
                full_text = result.get("text", "").strip()
                
                # 處理片段
                for segment in result.get("segments", []):
                    seg = TranscriptionSegment(
                        text=segment["text"],
                        start_time=segment["start"],
                        end_time=segment["end"],
                        confidence=None  # OpenAI Whisper doesn't provide confidence scores
                    )
                    segments.append(seg)
            
            # 建立結果
            processing_time = time.time() - start_time
            
            # 計算總時長
            duration = segments[-1].end_time if segments else 0.0
            
            result = TranscriptionResult(
                session_id=f"file_{Path(file_path).stem}",
                segments=segments,
                full_text=full_text,
                language=result.get("language", self._config.language),
                duration=duration,
                processing_time=processing_time,
                metadata={
                    "file_path": file_path,
                    "model": self._config.model_name,
                    "device": self._config.device
                }
            )
            
            logger.info(f"轉譯完成: {file_path} ({processing_time:.2f}秒)")
            return result
            
        except Exception as e:
            logger.error(f"轉譯失敗: {e}")
            raise ServiceExecutionError(f"轉譯失敗: {e}") from e
    
    # ========== IASRProvider 介面實作（最小化）==========
    
    def initialize(self, config: Optional[ASRConfig] = None) -> bool:
        """初始化（已在 __init__ 完成）"""
        if config:
            self._config = config
            self._load_model()
            self._initialized = True
        return self._initialized
    
    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        session_id: Optional[str] = None
    ) -> TranscriptionResult:
        """轉譯音訊數據
        
        注意：MVP 版本改為接受檔案路徑字串
        """
        # MVP 簡化：假設 audio_data 是檔案路徑字串
        if isinstance(audio_data, str):
            return self.transcribe_file(audio_data)
        else:
            raise NotImplementedError("MVP 版本只支援檔案路徑轉譯")
    
    def start_transcription(
        self, 
        session_id: str,
        callback: Optional[Callable[[TranscriptionResult], None]] = None
    ) -> bool:
        """開始轉譯（不支援串流）"""
        raise NotImplementedError("MVP 版本不支援串流轉譯，請使用 transcribe_file()")
    
    def stop_transcription(self, session_id: str) -> bool:
        """停止轉譯（不支援）"""
        return False
    
    def is_transcribing(self, session_id: str) -> bool:
        """檢查轉譯狀態（永遠返回 False）"""
        return False
    
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 狀態（不支援）"""
        return None
    
    def reset_session(self, session_id: str) -> bool:
        """重置 session（不支援）"""
        return False
    
    def get_active_sessions(self) -> List[str]:
        """取得活動 sessions（永遠空）"""
        return []
    
    def get_config(self) -> Optional[ASRConfig]:
        """取得當前配置"""
        return self._config
    
    def update_config(self, config: ASRConfig) -> bool:
        """更新配置"""
        try:
            old_model = self._config.model_name if self._config else None
            old_device = self._config.device if self._config else None
            
            self._config = config
            
            # 如果模型或設備改變，重新載入
            if config.model_name != old_model or config.device != old_device:
                self._load_model()
            
            return True
        except Exception as e:
            logger.error(f"更新配置失敗: {e}")
            return False
    
    def shutdown(self) -> None:
        """關閉並釋放資源"""
        logger.info("關閉 WhisperProvider")
        self._model = None
        self._initialized = False
    
    @classmethod
    def get_singleton(cls) -> 'WhisperProvider':
        """取得單例實例（向後相容）
        
        Returns:
            WhisperProvider 單例實例
        """
        return cls(singleton=True)
    
    @classmethod
    def reset_singleton(cls):
        """重置單例（主要用於測試）"""
        with cls._singleton_lock:
            if cls._singleton_instance:
                try:
                    cls._singleton_instance.shutdown()
                except Exception as e:
                    logger.error(f"重置單例時發生錯誤: {e}")
                finally:
                    cls._singleton_instance = None


# 模組級單例（向後相容）
whisper_provider = WhisperProvider.get_singleton()

__all__ = ['WhisperProvider', 'whisper_provider']
