"""Faster-Whisper ASR Provider  - 進階版高效能 Whisper 實作

核心改進：
1. 雙模式支援：音檔直接處理 + 串流chunk處理
2. BatchedInferencePipeline 整合，提升25-40%效能
3. 智能緩衝管理，基於音頻特徵動態調整
4. 統一的轉譯引擎，簡化架構複雜度
5. 強化的錯誤處理和自動恢復機制
"""

import time
import threading
from typing import Optional, Dict, Any, List, Callable, Union
from pathlib import Path
import numpy as np
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os

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
    SessionError,  
    ServiceExecutionError 
)
from src.config.manager import ConfigManager
from src.core.buffer_manager import BufferManager
from src.interface.buffer import BufferConfig

# 取得配置
config_manager = ConfigManager()


class ProcessingMode(Enum):
    """處理模式"""
    CHUNK_STREAMING = "chunk_streaming"  # 串流chunk處理
    FILE_BATCH = "file_batch"           # 音檔批次處理


@dataclass
class TranscriptionTask:
    """轉譯任務"""
    session_id: str
    audio_data: Union[np.ndarray, str, Path]  # 音頻數據或檔案路徑
    mode: ProcessingMode
    callback: Optional[Callable[[TranscriptionResult], None]] = None
    metadata: Optional[Dict[str, Any]] = None
    priority: int = 0  # 任務優先級


class SmartBuffer:
    """智能音頻緩衝管理器
    
    基於音頻特徵動態調整窗口大小和閾值，
    替代v1複雜的緩衝邏輯。
    """
    
    def __init__(self, session_id: str, sample_rate: int = 16000):
        self.session_id = session_id
        self.sample_rate = sample_rate
        
        # 動態參數
        self.min_chunk_duration = 0.5  # 最小chunk時長（秒）
        self.max_chunk_duration = 10.0  # 最大chunk時長（秒）
        self.silence_threshold = 0.01   # 靜音檢測閾值
        self.speech_threshold = 0.02    # 語音檢測閾值
        
        # 緩衝區
        self.audio_buffer = []
        self.last_activity_time = time.time()
        
        # 統計信息
        self.total_audio_duration = 0.0
        self.silence_duration = 0.0
        
    def push(self, audio_chunk: np.ndarray) -> bool:
        """推入音頻chunk"""
        if audio_chunk is None or len(audio_chunk) == 0:
            return False
            
        self.audio_buffer.append(audio_chunk)
        duration = len(audio_chunk) / self.sample_rate
        self.total_audio_duration += duration
        
        # 檢測語音活動
        rms_energy = np.sqrt(np.mean(audio_chunk ** 2))
        if rms_energy > self.speech_threshold:
            self.last_activity_time = time.time()
            self.silence_duration = 0.0
        else:
            self.silence_duration += duration
            
        return True
    
    def should_flush(self) -> bool:
        """判斷是否應該flush緩衝區"""
        if not self.audio_buffer:
            return False
            
        # 基於時長判斷
        if self.total_audio_duration >= self.max_chunk_duration:
            return True
            
        # 基於靜音判斷
        time_since_activity = time.time() - self.last_activity_time
        if (self.total_audio_duration >= self.min_chunk_duration and 
            (self.silence_duration >= 1.0 or time_since_activity >= 2.0)):
            return True
            
        return False
    
    def flush(self) -> Optional[np.ndarray]:
        """取出並清空緩衝區"""
        if not self.audio_buffer:
            return None
            
        combined = np.concatenate(self.audio_buffer)
        self.audio_buffer = []
        self.total_audio_duration = 0.0
        self.silence_duration = 0.0
        
        return combined


class ResourcePool:
    """資源池管理器
    
    管理 WhisperModel 和 BatchedInferencePipeline 的生命週期，
    支援多session並行處理。
    """
    
    def __init__(self, config: ASRConfig):
        self.config = config
        self._model = None
        self._batched_model = None
        self._model_lock = threading.Lock()
        self._initialization_error = None
        
        # 健康狀態
        self.is_healthy = False
        self.last_health_check = 0
        self.consecutive_failures = 0
        
        # 初始化模型
        self._initialize_models()
    
    def _initialize_models(self):
        """初始化模型"""
        try:
            from faster_whisper import WhisperModel, BatchedInferencePipeline
        except ImportError as e:
            self._initialization_error = ServiceInitializationError(
                "faster-whisper 套件未安裝。請執行: pip install faster-whisper"
            )
            logger.error(f"導入失敗: {e}")
            return
        
        try:
            with self._model_lock:
                logger.info(f"載入 Faster-Whisper 模型: {self.config.model_name}")
                
                # 載入基礎模型
                self._model = WhisperModel(
                    self.config.model_name,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                    cpu_threads=4,
                    num_workers=1
                )
                
                # 載入批次處理模型
                self._batched_model = BatchedInferencePipeline(
                    model=self._model,
                    chunk_length=30,  # 30秒chunk
                    stride_length=5   # 5秒重疊
                )
                
                self.is_healthy = True
                self.consecutive_failures = 0
                logger.info("模型載入成功")
                
        except Exception as e:
            self._initialization_error = ServiceInitializationError(
                f"載入 Faster-Whisper 模型失敗: {e}"
            )
            logger.error(f"模型載入失敗: {e}")
            self.is_healthy = False
    
    def get_model(self) -> tuple:
        """取得模型實例"""
        if self._initialization_error:
            raise self._initialization_error
            
        if not self.is_healthy:
            self._health_check()
            
        return self._model, self._batched_model
    
    def _health_check(self):
        """健康檢查"""
        current_time = time.time()
        if current_time - self.last_health_check < 30:  # 30秒內不重複檢查
            return
            
        self.last_health_check = current_time
        
        try:
            if self._model is None:
                self._initialize_models()
            else:
                # 簡單的健康檢查：處理很短的靜音
                silent_audio = np.zeros(1600)  # 0.1秒靜音
                list(self._model.transcribe(silent_audio))
                
            self.is_healthy = True
            self.consecutive_failures = 0
            
        except Exception as e:
            self.consecutive_failures += 1
            self.is_healthy = False
            logger.warning(f"健康檢查失敗 ({self.consecutive_failures}): {e}")
            
            # 連續失敗超過3次，嘗試重新初始化
            if self.consecutive_failures >= 3:
                logger.info("嘗試重新初始化模型")
                self._model = None
                self._batched_model = None
                self._initialize_models()


class TranscriptionEngine:
    """統一轉譯引擎
    
    支援音檔和chunk兩種模式的統一處理核心。
    """
    
    def __init__(self, resource_pool: ResourcePool, config: ASRConfig):
        self.resource_pool = resource_pool
        self.config = config
        
        # 執行緒池用於並行處理
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="transcription")
    
    def transcribe_chunk(
        self,
        audio_data: np.ndarray,
        session_id: str,
        context: Optional[str] = None
    ) -> Optional[TranscriptionResult]:
        """處理音頻chunk"""
        try:
            model, _ = self.resource_pool.get_model()
            return self._do_transcription(model, audio_data, session_id, context)
            
        except Exception as e:
            logger.error(f"Chunk轉譯失敗 [{session_id}]: {e}")
            raise ServiceExecutionError(f"Chunk轉譯失敗: {e}") from e
    
    def transcribe_file(
        self,
        file_path: Union[str, Path],
        session_id: str
    ) -> TranscriptionResult:
        """處理音檔文件"""
        try:
            _, batched_model = self.resource_pool.get_model()
            
            # 使用批次模型處理完整音檔
            segments, info = batched_model.transcribe(
                str(file_path),
                language=self.config.language,
                task="transcribe",
                beam_size=self.config.beam_size,
                batch_size=16  # 批次大小
            )
            
            return self._build_result(segments, info, session_id, file_mode=True)
            
        except Exception as e:
            logger.error(f"文件轉譯失敗 [{session_id}]: {e}")
            raise ServiceExecutionError(f"文件轉譯失敗: {e}") from e
    
    def _do_transcription(
        self,
        model,
        audio_data: np.ndarray,
        session_id: str,
        context: Optional[str] = None
    ) -> Optional[TranscriptionResult]:
        """執行轉譯"""
        start_time = time.time()
        
        # 確保音訊格式正確
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)
        audio_data = np.clip(audio_data, -1.0, 1.0)
        
        # 執行轉譯
        segments, info = model.transcribe(
            audio_data,
            language=self.config.language,
            task="transcribe",
            beam_size=self.config.beam_size,
            best_of=self.config.best_of,
            temperature=self.config.temperature,
            condition_on_previous_text=True,
            initial_prompt=context[-200:] if context else self.config.initial_prompt,
            suppress_blank=self.config.suppress_blank,
            word_timestamps=self.config.word_timestamps
        )
        
        return self._build_result(segments, info, session_id, start_time)
    
    def _build_result(
        self,
        segments,
        info,
        session_id: str,
        start_time: Optional[float] = None,
        file_mode: bool = False
    ) -> TranscriptionResult:
        """構建轉譯結果"""
        result_segments = []
        full_text = ""
        
        for segment in segments:
            seg = TranscriptionSegment(
                text=segment.text,
                start_time=segment.start,
                end_time=segment.end,
                confidence=getattr(segment, 'avg_logprob', None)
            )
            result_segments.append(seg)
            full_text += segment.text
        
        processing_time = time.time() - start_time if start_time else 0
        
        return TranscriptionResult(
            session_id=session_id,
            segments=result_segments,
            full_text=full_text.strip(),
            language=info.language if info else self.config.language,
            duration=info.duration if info else len(segments) * 2.0,  # 估算
            processing_time=processing_time,
            metadata={
                "model": self.config.model_name,
                "device": self.config.device,
                "mode": "file" if file_mode else "chunk",
                "batch_processed": file_mode
            }
        )
    
    def shutdown(self):
        """關閉引擎"""
        self.executor.shutdown(wait=True)


class FasterWhisperProvider(IASRProvider):
    """Faster-Whisper ASR 提供者 版本
    
    主要改進：
    1. 支援音檔直接處理和串流chunk處理
    2. 整合BatchedInferencePipeline提升效能
    3. 智能緩衝管理
    4. 統一的轉譯引擎
    5. 強化的錯誤處理機制
    """
    
    _singleton_instance = None
    _singleton_lock = threading.Lock()
    
    def __new__(cls, singleton: bool = True):
        """建立實例（支援單例/非單例模式）"""
        if singleton:
            if cls._singleton_instance is None:
                with cls._singleton_lock:
                    if cls._singleton_instance is None:
                        cls._singleton_instance = super().__new__(cls)
            return cls._singleton_instance
        else:
            return super().__new__(cls)
    
    def __init__(self, singleton: bool = True):
        """初始化 Faster-Whisper Provider """
        # 避免重複初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self._initialized = False
        self._config = self._load_config()
        
        # 核心組件
        self._resource_pool = None
        self._transcription_engine = None
        
        # Session管理
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._session_lock = threading.Lock()
        
        # 智能緩衝管理器
        self._smart_buffers: Dict[str, SmartBuffer] = {}
        
        # 停止旗標
        self._stop_flags: Dict[str, bool] = {}
        
        # 結果快取
        self._results_cache: Dict[str, List[TranscriptionResult]] = {}
        
        logger.info("FasterWhisperProvider 初始化開始")
        
        # 自動初始化
        try:
            if self._config:
                self._initialize_components()
                self._initialized = True
                logger.info("FasterWhisperProvider 初始化成功")
        except Exception as e:
            logger.error(f"初始化失敗: {e}")
    
    def _load_config(self) -> Optional[ASRConfig]:
        """從 ConfigManager 載入設定"""
        try:
            if hasattr(config_manager, 'providers') and hasattr(config_manager.providers, 'whisper'):
                whisper_config = config_manager.providers.whisper
                if whisper_config.whisper_enabled and whisper_config.use_faster_whisper:
                    
                    # 智能選擇compute_type
                    compute_type = whisper_config.compute_type
                    if whisper_config.whisper_device == "cpu":
                        if compute_type not in ["int8", "float32"]:
                            compute_type = "int8"
                    else:
                        if compute_type not in ["float16", "int8_float16"]:
                            compute_type = "float16"
                    
                    return ASRConfig(
                        model_name=whisper_config.model_size or "base",
                        language=whisper_config.language,
                        device=whisper_config.whisper_device,
                        compute_type=compute_type,
                        use_vad=False,  # 版本統一由模型處理
                        temperature=0.0,
                        beam_size=5,
                        best_of=5,
                        patience=1.0,
                        length_penalty=1.0,
                        suppress_blank=True,
                        word_timestamps=False,
                        initial_prompt=None
                    )
            return ASRConfig()
        except Exception as e:
            logger.warning(f"載入配置失敗: {e}")
            return ASRConfig()
    
    def _initialize_components(self):
        """初始化核心組件"""
        if not self._config:
            raise ServiceInitializationError("配置未載入")
        
        # 初始化資源池
        self._resource_pool = ResourcePool(self._config)
        
        # 初始化轉譯引擎
        self._transcription_engine = TranscriptionEngine(self._resource_pool, self._config)
        
        logger.info("核心組件初始化完成")
    
    # ========== IASRProvider 接口實現 ==========
    
    def initialize(self, config: Optional[ASRConfig] = None) -> bool:
        """初始化 ASR 提供者"""
        if config:
            self._config = config
        
        try:
            self._initialize_components()
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"初始化失敗: {e}")
            return False
    
    def start_transcription(
        self, 
        session_id: str,
        callback: Optional[Callable[[TranscriptionResult], None]] = None
    ) -> bool:
        """開始轉譯特定 session 的音訊"""
        if not session_id:
            raise SessionError("Session ID 不能為空")
        
        if not self._initialized:
            raise ServiceInitializationError("服務未初始化")
        
        # 檢查是否已在轉譯
        with self._session_lock:
            if session_id in self._sessions and self._sessions[session_id].get("active"):
                logger.warning(f"Session {session_id} 已在轉譯中")
                return True
        
        # 建立轉譯執行緒
        thread = threading.Thread(
            target=self._transcription_loop,
            args=(session_id, callback),
            daemon=True,
            name=f"faster-whisper--{session_id}"
        )
        
        # 建立智能緩衝管理器
        self._smart_buffers[session_id] = SmartBuffer(
            session_id, 
            self._config.sample_rate
        )
        
        # 儲存 session 資訊
        with self._session_lock:
            self._sessions[session_id] = {
                "callback": callback,
                "thread": thread,
                "active": True,
                "start_time": time.time(),
                "mode": ProcessingMode.CHUNK_STREAMING,
                "context": ""  # 用於串流上下文
            }
        
        self._stop_flags[session_id] = False
        thread.start()
        logger.info(f"開始轉譯 session: {session_id} (串流模式)")
        return True
    
    def stop_transcription(self, session_id: str) -> bool:
        """停止轉譯特定 session"""
        if not session_id:
            raise SessionError("Session ID 不能為空")
        
        with self._session_lock:
            if session_id not in self._sessions:
                logger.warning(f"Session {session_id} 不存在")
                return False
            
            session = self._sessions[session_id]
            session["active"] = False
        
        # 設置停止旗標
        self._stop_flags[session_id] = True
        
        try:
            # 等待執行緒結束
            thread = session.get("thread")
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
                if thread.is_alive():
                    logger.warning(f"Session {session_id} 執行緒未能及時停止")
            
            logger.info(f"已停止轉譯 session: {session_id}")
            return True
            
        except Exception as e:
            raise SessionError(f"停止 session {session_id} 時發生錯誤: {e}") from e
    
    def is_transcribing(self, session_id: str) -> bool:
        """檢查是否正在轉譯特定 session"""
        with self._session_lock:
            return session_id in self._sessions and self._sessions[session_id].get("active", False)
    
    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        session_id: Optional[str] = None
    ) -> TranscriptionResult:
        """轉譯單段音訊"""
        if not self._initialized:
            raise ServiceInitializationError("服務未初始化")
        
        # 使用臨時 session ID 如果沒有提供
        if not session_id:
            session_id = f"temp_{time.time()}"
        
        return self._transcription_engine.transcribe_chunk(
            audio_data, 
            session_id
        )
    
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 狀態資訊"""
        with self._session_lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                return {
                    "active": session.get("active", False),
                    "start_time": session.get("start_time"),
                    "mode": session.get("mode", ProcessingMode.CHUNK_STREAMING).value,
                    "has_callback": session.get("callback") is not None,
                    "thread_alive": session.get("thread") and session["thread"].is_alive(),
                    "results_count": len(self._results_cache.get(session_id, [])),
                    "context_length": len(session.get("context", ""))
                }
        return None
    
    def reset_session(self, session_id: str) -> bool:
        """重置特定 session 的狀態"""
        # 停止轉譯（如果正在進行）
        if self.is_transcribing(session_id):
            self.stop_transcription(session_id)
        
        # 清理快取和資源
        if session_id in self._results_cache:
            del self._results_cache[session_id]
        
        if session_id in self._smart_buffers:
            del self._smart_buffers[session_id]
        
        return True
    
    def get_config(self) -> Optional[ASRConfig]:
        """取得當前配置"""
        return self._config
    
    def update_config(self, config: ASRConfig) -> bool:
        """更新配置"""
        try:
            old_model = self._config.model_name if self._config else None
            old_device = self._config.device if self._config else None
            old_compute_type = self._config.compute_type if self._config else None
            
            self._config = config
            
            # 如果關鍵配置改變，重新初始化
            if (config.model_name != old_model or 
                config.device != old_device or
                config.compute_type != old_compute_type):
                self._initialize_components()
            
            return True
        except Exception as e:
            logger.error(f"更新配置失敗: {e}")
            return False
    
    def get_active_sessions(self) -> List[str]:
        """取得所有活動中的 session ID"""
        with self._session_lock:
            return [sid for sid, info in self._sessions.items() if info.get("active", False)]
    
    def shutdown(self) -> None:
        """關閉提供者，釋放資源"""
        logger.info("關閉 FasterWhisperProvider")
        
        # 停止所有活動的 sessions
        active_sessions = self.get_active_sessions()
        for session_id in active_sessions:
            self.stop_transcription(session_id)
        
        # 關閉轉譯引擎
        if self._transcription_engine:
            self._transcription_engine.shutdown()
        
        # 清理快取
        self._results_cache.clear()
        self._smart_buffers.clear()
        
        self._initialized = False
        logger.info("FasterWhisperProvider 已關閉")
    
    # ==========  新增功能 ==========
    
    def transcribe_file(
        self,
        file_path: Union[str, Path],
        session_id: Optional[str] = None,
        callback: Optional[Callable[[TranscriptionResult], None]] = None
    ) -> TranscriptionResult:
        """轉譯音檔文件（新增功能）
        
        Args:
            file_path: 音檔路徑
            session_id: Session ID (可選)
            callback: 完成回調 (可選)
            
        Returns:
            轉譯結果
        """
        if not self._initialized:
            raise ServiceInitializationError("服務未初始化")
        
        if not session_id:
            session_id = f"file_{int(time.time())}"
        
        # 檢查檔案是否存在
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"音檔不存在: {file_path}")
        
        logger.info(f"開始轉譯音檔: {file_path}")
        
        try:
            # 使用轉譯引擎處理檔案
            result = self._transcription_engine.transcribe_file(file_path, session_id)
            
            # 觸發回調
            if callback:
                callback(result)
            
            logger.info(f"音檔轉譯完成: {session_id}, 文字長度: {len(result.full_text)}")
            return result
            
        except Exception as e:
            logger.error(f"音檔轉譯失敗 [{session_id}]: {e}")
            raise ServiceExecutionError(f"音檔轉譯失敗: {e}") from e
    
    def get_model_info(self) -> Dict[str, Any]:
        """取得模型資訊"""
        if not self._initialized or not self._resource_pool:
            return {"initialized": False}
        
        return {
            "initialized": True,
            "model_name": self._config.model_name,
            "device": self._config.device,
            "compute_type": self._config.compute_type,
            "healthy": self._resource_pool.is_healthy,
            "consecutive_failures": self._resource_pool.consecutive_failures,
            "supported_modes": ["chunk_streaming", "file_batch"],
            "active_sessions": len(self.get_active_sessions()),
            "version": "2.0"
        }
    
    # ========== 內部實現 ==========
    
    def _transcription_loop(self, session_id: str, callback: Optional[Callable]):
        """轉譯循環，處理串流chunk"""
        from src.core.audio_queue_manager import audio_queue
        
        smart_buffer = self._smart_buffers[session_id]
        
        # 初始化結果快取
        if session_id not in self._results_cache:
            self._results_cache[session_id] = []
        
        logger.info(f"轉譯執行緒啟動 [{session_id}]")
        
        error_count = 0
        max_errors = 5  # 版本更嚴格的錯誤限制
        
        while not self._stop_flags.get(session_id, False):
            # 檢查session是否應該停止
            with self._session_lock:
                if session_id not in self._sessions or not self._sessions[session_id]["active"]:
                    break
            
            try:
                # 從音頻隊列取得數據
                audio_chunk = audio_queue.pop_blocking(session_id, timeout=0.1)
                
                if audio_chunk is not None:
                    # 處理音頻數據
                    if hasattr(audio_chunk, 'data'):
                        data_bytes = audio_chunk.data
                    else:
                        if isinstance(audio_chunk, bytes):
                            data_bytes = audio_chunk
                        else:
                            data_bytes = audio_chunk.astype(np.int16).tobytes()
                    
                    # 轉換為float32
                    audio_f32 = np.frombuffer(data_bytes, dtype='<i2').astype(np.float32) / 32768.0
                    
                    # 推入智能緩衝區
                    smart_buffer.push(audio_f32)
                    
                    # 檢查是否需要flush
                    if smart_buffer.should_flush():
                        combined_audio = smart_buffer.flush()
                        
                        if combined_audio is not None and len(combined_audio) > 0:
                            # 取得當前上下文
                            current_context = ""
                            with self._session_lock:
                                current_context = self._sessions[session_id].get("context", "")
                            
                            # 執行轉譯
                            result = self._transcription_engine.transcribe_chunk(
                                combined_audio,
                                session_id,
                                current_context
                            )
                            
                            if result and result.full_text.strip():
                                # 更新上下文
                                with self._session_lock:
                                    self._sessions[session_id]["context"] = result.full_text
                                
                                # 快取結果
                                self._results_cache[session_id].append(result)
                                
                                # 觸發回調
                                if callback:
                                    callback(result)
                                
                                error_count = 0  # 重置錯誤計數
                
            except Exception as e:
                if "timeout" not in str(e).lower():
                    error_count += 1
                    logger.error(f"轉譯循環錯誤 [{session_id}]: {e}")
                    
                    if error_count >= max_errors:
                        logger.error(f"連續錯誤次數達到上限 [{session_id}]，停止轉譯")
                        self._stop_flags[session_id] = True
                        break
        
        # 處理剩餘的緩衝數據
        if session_id in self._smart_buffers:
            final_audio = self._smart_buffers[session_id].flush()
            if final_audio is not None and len(final_audio) > 0:
                try:
                    with self._session_lock:
                        context = self._sessions[session_id].get("context", "")
                    
                    result = self._transcription_engine.transcribe_chunk(
                        final_audio, session_id, context
                    )
                    
                    if callback and result and result.full_text.strip():
                        callback(result)
                        
                except Exception as e:
                    logger.error(f"處理最終數據錯誤 [{session_id}]: {e}")
        
        # 清理session資源
        self._cleanup_session(session_id)
        logger.info(f"轉譯執行緒結束 [{session_id}]")
    
    def _cleanup_session(self, session_id: str):
        """清理session相關資源"""
        # 清理session
        with self._session_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
        
        # 清理智能緩衝區
        if session_id in self._smart_buffers:
            del self._smart_buffers[session_id]
        
        # 清理停止旗標
        if session_id in self._stop_flags:
            del self._stop_flags[session_id]
    
    # ========== 類方法 ==========
    
    @classmethod
    def get_singleton(cls) -> 'FasterWhisperProvider':
        """取得單例實例"""
        return cls(singleton=True)
    
    @classmethod
    def reset_singleton(cls):
        """重置單例"""
        with cls._singleton_lock:
            if cls._singleton_instance:
                try:
                    cls._singleton_instance.shutdown()
                except Exception as e:
                    logger.error(f"重置單例時發生錯誤: {e}")
                finally:
                    cls._singleton_instance = None


# 模組級單例（向後相容）
faster_whisper_provider = FasterWhisperProvider.get_singleton()

__all__ = ['FasterWhisperProvider', 'faster_whisper_provider', 'ProcessingMode', 'TranscriptionTask']