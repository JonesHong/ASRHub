"""Silero VAD 語音活動檢測服務
核心職責：
1. 接收音訊資料，判斷是否為語音
2. 直接從 audio_queue 拉取音訊處理
3. 為每個 session 提供獨立的 callback 機制
"""

import time
import threading
from typing import Optional, Dict, Any, Callable
from pathlib import Path
import numpy as np
import onnxruntime as ort

from src.interface.vad import IVADService, VADConfig, VADState, VADResult
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.interface.exceptions import (
    VADInitializationError,
    VADModelError,
    VADSessionError,
    VADDetectionError,
    VADAudioError
)
from src.config.manager import ConfigManager
from src.core.buffer_manager import BufferManager
from src.interface.buffer import BufferConfig

# Get configuration from ConfigManager
config_manager = ConfigManager()


class SileroVAD(SingletonMixin, IVADService):
    """ Silero VAD 語音活動檢測服務
    
    核心功能：
    - 載入 ONNX 模型進行推論
    - 處理音訊判斷是否為語音
    - 為每個 session 提供獨立的監聽執行緒
    - Session-based callback 機制
    """
    
    def __init__(self):
        """初始化服務並自動載入模型"""
        if not hasattr(self, '_initialized'):
            self._initialized = False
            self._model = None
            self._config = self._load_config()
            
            # Session 管理
            self._sessions: Dict[str, Dict[str, Any]] = {}
            self._session_lock = threading.Lock()
            
            # 簡單的狀態追蹤（用於狀態變化檢測）
            self._last_state: Dict[str, VADState] = {}
            
            # BufferManager 管理（每個 session 一個）
            self._buffer_managers: Dict[str, BufferManager] = {}
            
            # 停止旗標（每個 session 一個）
            self._stop_flags: Dict[str, bool] = {}
            
            # 回調函數管理（每個 session 的回調）
            self._callbacks: Dict[str, Dict[str, Callable]] = {}
            
            # LSTM 隱藏狀態管理（每個 session 一組）
            self._hidden_states: Dict[str, tuple] = {}
            
            # logger.debug("SileroVAD 初始化")
            
            # 服務已經通過 service_loader 檢查了 enabled
            # 如果能到這裡，表示服務已啟用
            if self._config:
                # 自動初始化
                try:
                    self._load_model()
                    self._initialized = True
                    logger.debug("Silero VAD 初始化成功")
                except Exception as e:
                    logger.error(f"Silero VAD 自動初始化失敗: {e}")
                    # 允許稍後重試，不拋出錯誤
            else:
                logger.warning("Silero VAD 配置載入失敗")
    
    def _load_config(self) -> Optional[VADConfig]:
        """從 ConfigManager 載入設定"""
        try:
            if hasattr(config_manager, 'services') and hasattr(config_manager.services, 'vad'):
                vad_config = config_manager.services.vad
                
                # 服務已經通過 service_loader 檢查了 enabled
                # 檢查類型為 silero
                if vad_config.type == "silero":
                    # 使用統一後的欄位名稱（移除 silero_ 前綴）
                    cfg = vad_config.silero
                    return VADConfig(
                        threshold=cfg.threshold,
                        min_speech_duration=cfg.min_speech_duration,
                        min_silence_duration=cfg.min_silence_duration,
                        sample_rate=cfg.sample_rate,
                        chunk_size=cfg.chunk_size,
                        use_gpu=cfg.use_gpu,
                        model_path=cfg.model_path
                    )
            return None  # 不返回預設配置
        except Exception as e:
            logger.warning(f"載入配置失敗: {e}")
            return None
    
    def _ensure_initialized(self) -> bool:
        """確保服務已初始化
        
        Returns:
            是否成功初始化
        """
        if self._initialized:
            return True
        
        try:
            self._load_model()
            self._initialized = True
            logger.info("Silero VAD 延遲初始化成功")
            return True
        except Exception as e:
            logger.error(f"延遲初始化失敗: {e}")
            raise VADInitializationError(f"無法初始化 Silero VAD: {e}") from e
    
    def _load_model(self):
        """載入 Silero VAD 模型"""
        model_path = self._config.model_path or "models/silero_vad.onnx"
        model_path = Path(model_path)
        
        # 如果模型不存在，嘗試下載
        if not model_path.exists():
            self._download_model(model_path)
        
        # 載入模型
        try:
            providers = ['CUDAExecutionProvider'] if self._config.use_gpu else ['CPUExecutionProvider']
            
            self._model = ort.InferenceSession(
                str(model_path),
                providers=providers
            )
            
            logger.debug(f"VAD 模型載入: {model_path}")
            
        except Exception as e:
            logger.error(f"模型載入失敗: {e}")
            raise VADModelError(f"載入 Silero VAD ONNX 模型失敗: {e}") from e
    
    def _download_model(self, model_path: Path):
        """下載 Silero VAD 模型
        
        Args:
            model_path: 模型儲存路徑
        """
        import urllib.request
        
        model_url = "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx"
        
        # 確保目錄存在
        model_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"開始下載模型: {model_url}")
        
        try:
            urllib.request.urlretrieve(model_url, model_path)
            logger.info(f"模型下載成功: {model_path}")
        except Exception as e:
            logger.error(f"模型下載失敗: {e}")
            raise VADModelError(f"無法下載 Silero VAD 模型: {e}") from e
    
    def _get_hidden_states(self, session_id: str) -> tuple:
        """取得或初始化 session 的 LSTM 隱藏狀態
        
        Args:
            session_id: Session ID
            
        Returns:
            (h, c) 隱藏狀態元組
        """
        if session_id not in self._hidden_states:
            # 初始化隱藏狀態為零
            # Silero VAD 使用 64 維的隱藏狀態
            batch_size = 1
            hidden_size = 64
            h = np.zeros((2, batch_size, hidden_size), dtype=np.float32)
            c = np.zeros((2, batch_size, hidden_size), dtype=np.float32)
            self._hidden_states[session_id] = (h, c)
        return self._hidden_states[session_id]
    
    def detect(
        self,
        audio_data: np.ndarray,
        session_id: str = "default"
    ) -> VADResult:
        """偵測音訊中是否包含語音
        
        Args:
            audio_data: 音訊資料 (numpy array, float32 或 int16)
            session_id: 用於狀態追蹤的 session ID
            
        Returns:
            VAD 檢測結果
            
        Raises:
            VADAudioError: 音訊格式錯誤
            VADDetectionError: 推論過程錯誤
        """
        if not self._ensure_initialized():
            raise VADInitializationError("服務尚未初始化")
        
        # 記錄接收到的音訊格式（只記錄第一次）
        # if not hasattr(self, '_first_vad_logged'):
        #     self._first_vad_logged = {}
        # if session_id not in self._first_vad_logged:
        #     self._first_vad_logged[session_id] = True
        #     logger.info(f"🎙️ [VAD_RECEIVED] First audio for VAD session {session_id}: shape={audio_data.shape}, dtype={audio_data.dtype}, "
        #                f"min={audio_data.min():.4f}, max={audio_data.max():.4f}")
        
        # 驗證輸入
        if not isinstance(audio_data, np.ndarray):
            raise VADAudioError(f"音訊資料型別錯誤: {type(audio_data)}")
        
        if audio_data.size == 0:
            raise VADAudioError("音訊資料為空")
        
        # 確保音訊格式正確
        try:
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # 正規化到 [-1, 1]
            if np.abs(audio_data).max() > 1.0:
                audio_data = audio_data / 32768.0
        except Exception as e:
            raise VADAudioError(f"音訊格式轉換失敗: {e}") from e
        
        # 執行推論
        try:
            # 取得隱藏狀態
            h, c = self._get_hidden_states(session_id)
            
            # Silero VAD 需要的輸入格式
            # 檢查模型輸入以確定格式
            input_names = [inp.name for inp in self._model.get_inputs()]
            
            if len(input_names) == 4:  # 新版本：input, sr, h, c
                ort_inputs = {
                    'input': audio_data.reshape(1, -1),
                    'sr': np.array([16000], dtype=np.int64),  # 使用 int64
                    'h': h,
                    'c': c
                }
            else:  # 舊版本：input, sr
                ort_inputs = {
                    self._model.get_inputs()[0].name: audio_data.reshape(1, -1),
                    self._model.get_inputs()[1].name: np.array([16000], dtype=np.int64)  # 使用 int64
                }
            
            # 執行推論
            ort_outputs = self._model.run(None, ort_inputs)
            
            # 解析輸出
            if len(ort_outputs) == 3:  # 新版本返回 (output, h_new, c_new)
                probability = float(ort_outputs[0][0])
                # 更新隱藏狀態
                self._hidden_states[session_id] = (ort_outputs[1], ort_outputs[2])
            else:  # 舊版本只返回 output
                probability = float(ort_outputs[0][0])
            
            # 判斷狀態
            if probability > self._config.threshold:
                state = VADState.SPEECH
            else:
                state = VADState.SILENCE
            
            # 建立結果
            result = VADResult(
                state=state,
                probability=probability
            )
            
            # 檢查狀態變化並觸發 callback
            self._check_state_change(session_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"VAD 推論錯誤: {e}")
            raise VADDetectionError(f"VAD 推論失敗: {e}") from e
    
    def _check_state_change(self, session_id: str, result: VADResult):
        """檢查狀態變化並觸發 callback
        
        Args:
            session_id: Session ID
            result: VAD 檢測結果
        """
        prev_state = self._last_state.get(session_id)
        
        if prev_state != result.state:
            # 狀態變化，觸發 callback
            with self._session_lock:
                if session_id in self._sessions and self._sessions[session_id]["active"]:
                    callback = self._sessions[session_id].get("callback")
                    if callback:
                        try:
                            # 傳遞狀態變化資訊
                            callback(result)
                        except Exception as e:
                            logger.error(f"VAD callback 錯誤 [{session_id}]: {e}")
            
            # 更新狀態
            self._last_state[session_id] = result.state
    
    def start_listening(
        self,
        session_id: str,
        callback: Callable[[VADResult], None],
        model_path: Optional[str] = None,
        start_timestamp: Optional[float] = None  # 新增：從指定時間戳開始讀取
    ) -> bool:
        """開始監聽特定 session 的音訊
        
        當偵測到語音狀態變化時（SILENCE ↔ SPEECH），會呼叫提供的 callback。
        服務會自動從 audio_queue 拉取音訊進行處理。
        
        Args:
            session_id: Session ID
            callback: 當狀態變化時的回調函數，接收 VADResult 物件
            model_path: 可選的模型路徑（覆蓋預設）
            start_timestamp: 從指定時間戳開始讀取（可選）
            
        Returns:
            是否成功開始監聽
            
        Raises:
            VADSessionError: Session 參數錯誤
            VADInitializationError: 服務初始化失敗
            VADModelError: 載入指定模型失敗
            
        Example:
            # 定義簡單的 callback
            def on_vad_change(result):
                if result.state == VADState.SPEECH:
                    print(f"🎤 開始說話 (信心度: {result.probability:.2%})")
                elif result.state == VADState.SILENCE:
                     print(f"🔇 停止說話")
            
            # 開始監聽
            success = silero_vad.start_listening("user_123", on_vad_change)
            if success:
                 print("VAD 監聽已啟動")
            
            # 稍後停止監聽
            silero_vad.stop_listening("user_123")
            
        Note:
            - 每個 session 只能有一個監聽執行緒
            - 如果 session 已在監聽中，會返回 True 但不會重啟
            - Callback 只在狀態變化時觸發，不是每個音訊塊都會呼叫
            - 連續錯誤超過 10 次會自動停止監聽
        """
        # 參數驗證
        if not session_id:
            raise VADSessionError("Session ID 不能為空")
        
        if not callable(callback):
            raise VADSessionError("必須提供有效的回調函數")
        
        # 註冊為音訊佇列的讀者（可能從指定時間戳開始）
        from src.core.audio_queue_manager import audio_queue
        audio_queue.register_reader(session_id, "vad", start_timestamp)
        if start_timestamp:
            logger.debug(f"Registered VAD as reader for session {session_id} from timestamp {start_timestamp:.3f}")
        else:
            logger.debug(f"Registered VAD as reader for session {session_id}")
        
        # 檢查是否已在監聽
        with self._session_lock:
            if session_id in self._sessions and self._sessions[session_id]["active"]:
                logger.warning(f"Session {session_id} 已在監聽中")
                return True
        
        # 確保服務已初始化
        if not self._ensure_initialized():
            raise VADInitializationError("無法初始化 VAD 服務")
        
        # 如果提供了新的模型路徑，載入它
        if model_path and model_path != self._config.model_path:
            try:
                old_path = self._config.model_path
                self._config.model_path = model_path
                self._load_model()
                logger.info(f"載入新模型: {model_path}")
            except Exception as e:
                self._config.model_path = old_path
                raise VADModelError(f"載入指定模型失敗: {e}") from e
        
        # 建立監聽執行緒
        thread = threading.Thread(
            target=self._listening_loop,
            args=(session_id, callback),
            daemon=True
        )
        
        # 註冊 session
        with self._session_lock:
            self._sessions[session_id] = {
                "active": True,
                "thread": thread,
                "callback": callback
            }
        
        # 啟動執行緒
        thread.start()
        logger.info(f"開始監聽 session: {session_id}")
        
        return True
    
    def _get_buffer_manager(self, session_id: str) -> BufferManager:
        """取得或建立 session 的 BufferManager
        
        Args:
            session_id: Session ID
            
        Returns:
            BufferManager 實例
        """
        if session_id not in self._buffer_managers:
            # Silero VAD 使用較小的窗口以提升響應速度
            config = BufferConfig.for_silero_vad(
                sample_rate=16000,
                window_ms=200  # 從 400ms 減少到 200ms
            )
            self._buffer_managers[session_id] = BufferManager(config)
        return self._buffer_managers[session_id]
    
    def _listening_loop(self, session_id: str, callback: Callable):
        """監聽循環，持續從 audio_queue 拉取音訊並偵測
        
        Args:
            session_id: Session ID
            callback: 回調函數
        """
        from src.core.audio_queue_manager import audio_queue
        
        # 取得 BufferManager
        buffer_mgr = self._get_buffer_manager(session_id)
        self._stop_flags[session_id] = False
        
        logger.info(f"監聽執行緒啟動 [{session_id}]")
        
        # 錯誤計數器
        error_count = 0
        max_errors = 10
        
        while not self._stop_flags.get(session_id, False):
            # 檢查是否應該停止
            with self._session_lock:
                if session_id not in self._sessions or not self._sessions[session_id]["active"]:
                    break
            
            try:
                # 使用非破壞性的阻塞式讀取
                timestamped_audio = audio_queue.pull_blocking_timestamp(
                    session_id,
                    reader_id="vad",
                    timeout=0.01  # 保持較短超時以提升響應速度
                )
                
                if timestamped_audio is not None:
                    audio_chunk = timestamped_audio.audio
                else:
                    audio_chunk = None
                
                if audio_chunk is not None:
                    # 取得 bytes 資料
                    if hasattr(audio_chunk, 'data'):
                        data_bytes = audio_chunk.data
                    else:
                        # 假設是 bytes 或可轉換為 bytes
                        if isinstance(audio_chunk, bytes):
                            data_bytes = audio_chunk
                        else:
                            # 如果是 numpy array，轉換為 bytes
                            data_bytes = audio_chunk.astype(np.int16).tobytes()
                    
                    # 推入 BufferManager
                    buffer_mgr.push(data_bytes)
                    
                    # 處理所有就緒的 frames
                    for frame in buffer_mgr.pop_all():
                        # 明確使用小端 int16 → float32 [-1, 1]
                        audio_f32 = np.frombuffer(frame, dtype='<i2').astype(np.float32) / 32768.0
                        
                        # 偵測語音
                        try:
                            result = self.detect(audio_f32, session_id)
                            # 狀態變化會在 detect 內部觸發 callback
                            
                            # 重置錯誤計數
                            error_count = 0
                            
                        except (VADAudioError, VADDetectionError) as e:
                            logger.error(f"VAD 偵測錯誤 [{session_id}]: {e}")
                            error_count += 1
                            
                            if error_count >= max_errors:
                                logger.error(f"連續錯誤次數達到上限 [{session_id}]，停止監聽")
                                self._stop_flags[session_id] = True
                                break
                
            except Exception as e:
                if "timeout" not in str(e).lower():
                    logger.error(f"監聽循環錯誤 [{session_id}]: {e}")
                    error_count += 1
                    
                    if error_count >= max_errors:
                        logger.error(f"連續錯誤次數達到上限 [{session_id}]，停止監聽")
                        self._stop_flags[session_id] = True
                        break
        
        # 停止前處理殘餘資料
        tail = buffer_mgr.flush()
        if tail:
            try:
                audio_f32 = np.frombuffer(tail, dtype='<i2').astype(np.float32) / 32768.0
                result = self.detect(audio_f32, session_id)
                if callback:
                    callback(result)
            except Exception as e:
                logger.error(f"處理尾端資料錯誤 [{session_id}]: {e}")
        
        # 清理
        self._cleanup_session(session_id)
        logger.info(f"監聽執行緒結束 [{session_id}]")
    
    def _cleanup_session(self, session_id: str):
        """清理 session 相關資源
        
        Args:
            session_id: Session ID
        """
        # 清理 session
        with self._session_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
        
        # 清理 BufferManager
        if session_id in self._buffer_managers:
            self._buffer_managers[session_id].reset()
            del self._buffer_managers[session_id]
        
        # 清理停止旗標
        if session_id in self._stop_flags:
            del self._stop_flags[session_id]
        
        # 清除狀態
        if session_id in self._last_state:
            del self._last_state[session_id]
        
        # 清理 LSTM 隱藏狀態
        if session_id in self._hidden_states:
            del self._hidden_states[session_id]
    
    def stop_listening(self, session_id: str) -> bool:
        """停止監聽特定 session
        
        停止監聽執行緒並清理相關資源。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止（False 表示 session 不存在）
            
        Example:
            >>> # 停止監聽
            >>> if silero_vad.stop_listening("user_123"):
            ...     print("成功停止監聽")
            ... else:
            ...     print("Session 不存在")
        """
        with self._session_lock:
            if session_id not in self._sessions:
                logger.warning(f"Session {session_id} 不存在")
                return False
            
            # 標記為非活動狀態
            self._sessions[session_id]["active"] = False
            logger.info(f"停止監聽 session: {session_id}")
        
        # 設定停止旗標
        if session_id in self._stop_flags:
            self._stop_flags[session_id] = True
            
        # 等待執行緒結束（最多等待1秒）
        thread = self._sessions.get(session_id, {}).get("thread")
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        
        return True
    
    def is_listening(self, session_id: str) -> bool:
        """檢查是否正在監聽特定 session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在監聽
            
        Example:
            >>> # 檢查監聽狀態
            >>> if silero_vad.is_listening("user_123"):
            ...     print("正在監聽中")
            ... else:
            ...     print("未在監聽")
        """
        with self._session_lock:
            return (
                session_id in self._sessions and 
                self._sessions[session_id]["active"]
            )
    
    def shutdown(self):
        """關閉服務"""
        logger.info("關閉 Silero VAD 服務")
        
        # 停止所有監聽 session
        with self._session_lock:
            session_ids = list(self._sessions.keys())
        
        for session_id in session_ids:
            self.stop_listening(session_id)
        
        # 清除狀態
        self._last_state.clear()
        
        # 清除所有 LSTM 隱藏狀態
        self._hidden_states.clear()
        
        # 釋放模型
        self._model = None
        self._initialized = False
        
        logger.info("Silero VAD 服務已關閉")
    
    # ===== 以下是為了相容介面的必要方法（簡化實作） =====
    
    def initialize(self, config: Optional[VADConfig] = None) -> bool:
        """相容性方法 - 不建議使用
        
        Returns:
            是否成功初始化
        """
        logger.warning("initialize() 已廢棄，初始化會自動進行")
        return self._ensure_initialized()
    
    def process_chunk(
        self,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> VADResult:
        """相容性方法 - 不建議使用
        
        Args:
            audio_data: 音訊資料
            sample_rate: 取樣率
            
        Returns:
            VAD 檢測結果
        """
        logger.warning("process_chunk() 已廢棄，請使用 start_listening()")
        return self.detect(audio_data)
    
    
    def reset_session(self, session_id: str) -> bool:
        """重置 session 狀態
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功重置
        """
        reset_any = False
        
        # 重置最後狀態
        if session_id in self._last_state:
            del self._last_state[session_id]
            reset_any = True
        
        # 重置 LSTM 隱藏狀態
        if session_id in self._hidden_states:
            del self._hidden_states[session_id]
            reset_any = True
        
        if reset_any:
            logger.info(f"重置 VAD session: {session_id}")
            return True
        return False
    
    def is_initialized(self) -> bool:
        """檢查服務是否已初始化"""
        return self._initialized
    
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 狀態（只有基本資訊）"""
        return {
            "current_state": self._last_state.get(session_id, VADState.SILENCE).value,
            "is_listening": self.is_listening(session_id),
            "initialized": self._initialized
        }
    
    def clear_all_sessions(self) -> int:
        """清除所有 session 狀態"""
        count = len(self._sessions)
        
        # 停止所有監聽
        with self._session_lock:
            session_ids = list(self._sessions.keys())
        
        for session_id in session_ids:
            self.stop_listening(session_id)
        
        # 清除狀態
        self._last_state.clear()
        
        # 清除所有 LSTM 隱藏狀態
        self._hidden_states.clear()
        
        return count
    
    def get_config(self) -> VADConfig:
        """取得當前配置"""
        return self.config
    
    def is_monitoring(self, session_id: str) -> bool:
        """檢查是否正在監控特定 session
        
        在這個實作中，is_monitoring 等同於 is_listening
        """
        return self.is_listening(session_id)
    
    def process_stream(
        self,
        session_id: str,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> VADResult:
        """處理串流音訊（保持 session 狀態）
        
        這是 process_chunk 的 session 版本
        """
        # 如果採樣率不同，需要重採樣
        if sample_rate and sample_rate != self.config.sample_rate:
            # 簡單的重採樣（實際應用中應使用更好的方法）
            ratio = self.config.sample_rate / sample_rate
            new_length = int(len(audio_data) * ratio)
            indices = np.linspace(0, len(audio_data) - 1, new_length)
            audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)
        
        # 使用 process_chunk 處理
        result = self.process_chunk(audio_data)
        
        # 更新 session 狀態
        self._last_state[session_id] = result.state
        
        return result
    
    def start_monitoring(
        self,
        session_id: str,
        on_speech_detected: Optional[Callable[[str, VADResult], None]] = None,
        on_silence_detected: Optional[Callable[[str, VADResult], None]] = None
    ) -> bool:
        """開始監控特定 session 的音訊
        
        這個方法啟動監聽並設置回調
        """
        # 儲存回調
        if session_id not in self._callbacks:
            self._callbacks[session_id] = {}
        
        if on_speech_detected:
            self._callbacks[session_id]['on_speech'] = on_speech_detected
        if on_silence_detected:
            self._callbacks[session_id]['on_silence'] = on_silence_detected
        
        # 開始監聽
        return self.start_listening(session_id)
    
    def stop_monitoring(self, session_id: str) -> bool:
        """停止監控特定 session"""
        # 清除回調
        if session_id in self._callbacks:
            del self._callbacks[session_id]
        
        # 停止監聽
        return self.stop_listening(session_id)
    
    def update_config(self, config: VADConfig) -> bool:
        """更新 VAD 配置
        
        注意：更新配置可能需要重新載入模型
        """
        try:
            self.config = config
            
            # 如果閾值改變，更新檢測閾值
            if hasattr(self, 'threshold'):
                self.threshold = config.threshold
            
            # 如果模型路徑改變，可能需要重新載入模型
            # （這裡暫時不實作模型重載）
            
            logger.info(f"VAD 配置已更新: threshold={config.threshold}")
            return True
            
        except Exception as e:
            logger.error(f"更新 VAD 配置失敗: {e}")
            return False


# 模組級單例
silero_vad: SileroVAD = SileroVAD()

__all__ = ['SileroVAD', 'silero_vad']