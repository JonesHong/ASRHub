"""OpenWakeWord 喚醒詞偵測服務 - 簡化版

核心職責：
1. 接收音訊資料，判斷是否觸發關鍵字
2. 直接從 audio_queue 拉取音訊處理
3. 觸發 hook 回調
"""

import time
import threading
from typing import Optional, Dict, Any, List, Callable
import numpy as np
from pathlib import Path

from src.interface.wake import IWakewordService, WakewordConfig, WakewordDetection
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.interface.exceptions import (
    WakewordInitializationError,
    WakewordModelError,
    WakewordSessionError,
    WakewordDetectionError,
    WakewordAudioError
)
from src.config.manager import ConfigManager
from src.core.buffer_manager import BufferManager
from src.interface.buffer import BufferConfig

# Get configuration from ConfigManager
config_manager = ConfigManager()


class OpenWakeword(SingletonMixin, IWakewordService):
    """簡化版 OpenWakeWord 喚醒詞偵測服務
    
    核心功能：
    - 載入 ONNX 模型進行推論
    - 處理音訊判斷是否包含關鍵字
    - 直接從 audio_queue 拉取音訊
    - 觸發檢測 hooks
    """
    
    def __init__(self):
        """初始化服務並載入模型"""
        if not hasattr(self, '_initialized'):
            self._initialized = False
            self._model = None
            
            # Session 管理
            self._sessions: Dict[str, Dict[str, Any]] = {}
            # 結構: {session_id: {"callback": callable, "thread": thread, "active": bool}}
            self._session_lock = threading.Lock()
            
            # BufferManager 管理（每個 session 一個）
            self._buffer_managers: Dict[str, BufferManager] = {}
            
            # 防抖動追蹤
            self._last_detection_time: Dict[str, float] = {}
            
            # 停止旗標（每個 session 一個）
            self._stop_flags: Dict[str, bool] = {}
            
            # 載入配置
            self._config = self._load_config()
            
            # 服務已經通過 service_loader 檢查了 enabled
            # 如果能到這裡，表示服務已啟用
            if self._config:
                # 直接初始化（KISS 原則）
                try:
                    self._load_model()
                    self._initialized = True
                    logger.info("OpenWakeword 服務初始化成功")
                except Exception as e:
                    logger.error(f"OpenWakeword 初始化失敗: {e}")
                    # 服務仍可使用，但需要稍後重試
                    self._initialized = False
            else:
                logger.warning("OpenWakeword 配置載入失敗")
    
    def _load_config(self) -> Optional[WakewordConfig]:
        """從 ConfigManager 載入設定"""
        try:
            if hasattr(config_manager, 'services') and hasattr(config_manager.services, 'wakeword'):
                wakeword_config = config_manager.services.wakeword
                
                # 服務已經通過 service_loader 檢查了 enabled
                # 檢查類型為 openwakeword
                if wakeword_config.type == "openwakeword":
                    # 使用統一後的欄位名稱（移除 wakeword_ 前綴）
                    cfg = wakeword_config.openwakeword
                    return WakewordConfig(
                        model_path=cfg.model_path,
                        threshold=cfg.threshold,
                        chunk_size=cfg.chunk_size,
                        sample_rate=cfg.sample_rate,
                        debounce_time=cfg.debounce_time,
                        use_gpu=cfg.use_gpu
                    )
            return None  # 不返回預設配置
        except Exception as e:
            logger.warning(f"載入配置失敗: {e}")
            return None
    
    def _ensure_initialized(self) -> bool:
        """確保服務已初始化，如果失敗則重試
        
        內部使用，用於 lazy initialization 或錯誤恢復
        
        Returns:
            是否成功初始化
        """
        if self._initialized:
            return True
        
        try:
            logger.info("嘗試重新初始化 OpenWakeword")
            self._load_model()
            self._initialized = True
            logger.info("OpenWakeword 重新初始化成功")
            return True
        except Exception as e:
            logger.error(f"重新初始化失敗: {e}")
            return False
    
    def _load_model(self):
        """載入 OpenWakeWord 模型
        
        Raises:
            WakewordModelError: 當模型載入失敗時
        """
        try:
            from openwakeword.model import Model
            from openwakeword.utils import download_models
        except ImportError as e:
            raise WakewordModelError(
                "openwakeword 套件未安裝。請執行: pip install openwakeword"
            ) from e
        
        if not self._config:
            raise WakewordModelError("配置未載入，無法取得模型路徑")
        
        model_path = self._config.model_path or "hey_jarvis_v0.1"
        
        # 如果不是本地檔案，嘗試下載
        if not Path(model_path).exists():
            try:
                logger.info(f"下載模型: {model_path}")
                download_models([model_path])
            except Exception as e:
                raise WakewordModelError(
                    f"無法下載模型 {model_path}: {e}"
                ) from e
        
        # 載入模型
        try:
            logger.info(f"載入模型: {model_path}")
            self._model = Model(
                wakeword_models=[model_path],
                inference_framework="onnx"
            )
            logger.info("模型載入成功")
        except Exception as e:
            raise WakewordModelError(
                f"載入模型失敗 {model_path}: {e}"
            ) from e
    
    def detect(
        self,
        audio_data: np.ndarray,
        session_id: str = "default"
    ) -> Optional[WakewordDetection]:
        """偵測音訊中的關鍵字
        
        Args:
            audio_data: 音訊資料 (numpy array, float32 或 int16)
            session_id: 用於防抖動的 session ID
            
        Returns:
            如果偵測到關鍵字則回傳 WakewordDetection，否則 None
            
        Raises:
            WakewordDetectionError: 當偵測過程發生錯誤
            WakewordAudioError: 當音訊資料格式錯誤
        """
        if not self._initialized:
            raise WakewordDetectionError("服務尚未初始化，無法進行偵測")
        
        if not self._model:
            raise WakewordDetectionError("模型未載入，無法進行偵測")
        
        # 驗證音訊資料
        if audio_data is None or len(audio_data) == 0:
            raise WakewordAudioError("音訊資料為空")
        
        if not isinstance(audio_data, np.ndarray):
            raise WakewordAudioError(
                f"音訊資料必須是 numpy array，收到 {type(audio_data)}"
            )
        
        # 確保音訊格式正確
        # OpenWakeWord 模型需要 int16 範圍的 float32 值（-32768.0 到 32767.0）
        try:
            if audio_data.dtype == np.int16:
                # int16 直接轉為 float32（保持原始範圍）
                audio_data = audio_data.astype(np.float32)
            elif audio_data.dtype != np.float32:
                raise WakewordAudioError(
                    f"不支援的音訊資料型別: {audio_data.dtype}"
                )
            # 如果已經是 float32，假設已經在正確範圍內
        except Exception as e:
            raise WakewordAudioError(f"音訊格式轉換失敗: {e}") from e
        
        # 記錄接收到的音訊格式（只記錄第一次）
        # if not hasattr(self, '_first_oww_logged'):
        #     self._first_oww_logged = {}
        # if session_id not in self._first_oww_logged:
        #     self._first_oww_logged[session_id] = True
        #     logger.info(f"🔊 [OWW_RECEIVED] First audio for OpenWakeWord session {session_id}: shape={audio_data.shape}, "
        #                f"dtype={audio_data.dtype}, range=[{audio_data.min():.4f}, {audio_data.max():.4f}]")
        
        # 執行推論
        try:
            predictions = self._model.predict(audio_data)
            
            # DEBUG: 顯示預測結果
            logger.debug(f"[{session_id}] 預測結果: {predictions}")
            
            # 檢查每個關鍵字
            for keyword, score in predictions.items():
                logger.debug(f"[{session_id}] {keyword}: score={score:.4f}, threshold={self._config.threshold:.4f}")
                
                # 檢查是否超過閾值
                if score >= self._config.threshold:
                    current_time = time.time()
                    
                    # 防抖動檢查
                    last_time = self._last_detection_time.get(f"{session_id}_{keyword}", 0)
                    if current_time - last_time < self._config.debounce_time:
                        logger.debug(f"防抖動: {keyword} 在 {self._config.debounce_time}s 內重複觸發")
                        continue
                    
                    # 更新最後偵測時間
                    self._last_detection_time[f"{session_id}_{keyword}"] = current_time
                    
                    # 建立偵測結果
                    detection = WakewordDetection(
                        keyword=keyword,
                        confidence=float(score),
                        timestamp=current_time,
                        session_id=session_id
                    )
                    
                    # 觸發 session 的回調
                    if session_id in self._sessions:
                        callback = self._sessions[session_id].get("callback")
                        if callback:
                            try:
                                callback(detection)
                            except Exception as e:
                                logger.error(f"執行回調錯誤 [{session_id}]: {e}")
                    
                    logger.info(f"偵測到關鍵字: {keyword} (信心度: {score:.3f})")
                    return detection
            
            return None
            
        except Exception as e:
            raise WakewordDetectionError(f"推論過程發生錯誤: {e}") from e
    
    def _get_buffer_manager(self, session_id: str) -> BufferManager:
        """取得或建立 session 的 BufferManager
        
        Args:
            session_id: Session ID
            
        Returns:
            BufferManager 實例
        """
        if session_id not in self._buffer_managers:
            # OpenWakeWord 使用固定 frame size (1280 samples)
            # 模型需要固定的 chunk size，不能使用配置中的值
            config = BufferConfig.for_openwakeword(
                sample_rate=self._config.sample_rate,
                frame_samples=1280  # OpenWakeWord 模型的固定需求
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
                    reader_id="openwakeword", 
                    timeout=0.1
                )
                
                if timestamped_audio is not None:
                    audio_chunk = timestamped_audio.audio
                    # DEBUG: 記錄成功讀取
                    if error_count % 20 == 0:  # 每20次記錄一次，避免太多日誌
                        logger.debug(f"[OWW] Successfully read audio chunk for {session_id}, timestamp: {timestamped_audio.timestamp:.3f}")
                else:
                    audio_chunk = None
                
                if audio_chunk is not None:
                    # DEBUG: 檢查收到的原始數據
                    logger.debug(f"[{session_id}] 原始 audio_chunk 類型: {type(audio_chunk)}")
                    if isinstance(audio_chunk, np.ndarray):
                        logger.debug(f"[{session_id}] 原始 numpy array: dtype={audio_chunk.dtype}, "
                                   f"shape={audio_chunk.shape}, "
                                   f"range=[{audio_chunk.min():.4f}, {audio_chunk.max():.4f}]")
                    # 取得 bytes 資料
                    if hasattr(audio_chunk, 'data'):
                        data_bytes = audio_chunk.data
                    else:
                        # 假設是 bytes 或可轉換為 bytes
                        if isinstance(audio_chunk, bytes):
                            data_bytes = audio_chunk
                        elif isinstance(audio_chunk, np.ndarray):
                            # 如果是 numpy array，需要先檢查並正規化
                            if audio_chunk.dtype == np.float32:
                                # 如果是 float32，確保在正確範圍內再轉換
                                # 可能來自上游的數據已經被錯誤處理
                                logger.debug(f"[{session_id}] 收到 float32 array: "
                                           f"shape={audio_chunk.shape}, "
                                           f"range=[{audio_chunk.min():.4f}, {audio_chunk.max():.4f}]")
                                # 直接將 float32 轉為 int16（假設已經在 [-1, 1] 範圍）
                                audio_int16 = (audio_chunk * 32768.0).clip(-32768, 32767).astype(np.int16)
                                data_bytes = audio_int16.tobytes()
                            else:
                                # int16 或其他類型，直接轉換
                                data_bytes = audio_chunk.astype(np.int16).tobytes()
                        else:
                            # 其他未知類型
                            logger.warning(f"[{session_id}] 未知的音訊數據類型: {type(audio_chunk)}")
                            continue
                    
                    # DEBUG: 檢查音訊數據
                    logger.debug(f"[{session_id}] 收到音訊塊: {len(data_bytes)} bytes")
                    
                    # 推入 BufferManager
                    buffer_mgr.push(data_bytes)
                    
                    # DEBUG: 檢查 BufferManager 狀態
                    frames_ready = buffer_mgr.pop_all()
                    logger.debug(f"[{session_id}] BufferManager 產生 {len(frames_ready)} 個 frames")
                    
                    # 處理所有就緒的 frames
                    for idx, frame in enumerate(frames_ready):
                        # OpenWakeWord 模型需要的是 int16 值範圍的 float32（不是歸一化的）
                        # 即：-32768.0 到 32767.0 的 float32 值
                        # 使用 np.int16 確保正確處理有符號整數
                        audio_int16 = np.frombuffer(frame, dtype=np.int16)
                        audio_f32 = audio_int16.astype(np.float32)
                        
                        # 移除DC偏移（如果存在）
                        audio_mean = audio_f32.mean()
                        if abs(audio_mean) > 100:  # 如果平均值偏離太大
                            logger.debug(f"[{session_id}] 偵測到DC偏移: {audio_mean:.2f}，進行修正")
                            audio_f32 = audio_f32 - audio_mean
                        
                        # 智能振幅檢查：OpenWakeWord 需要 int16 範圍的 float32（-32768 到 32767）
                        # 但要避免過度處理已經良好的音訊
                        max_abs_val = np.abs(audio_f32).max()
                        
                        # 只有在音訊明顯太小（< 1000）或過大（> 30000）時才進行調整
                        if max_abs_val > 0 and max_abs_val < 1000:
                            # 只對真正微弱的訊號進行適度放大
                            scale_factor = 5000.0 / max_abs_val  # 溫和放大到 5000 左右
                            audio_f32 = audio_f32 * scale_factor
                            logger.debug(f"[{session_id}] 微弱訊號增強: 放大 {scale_factor:.2f}x "
                                       f"(原始範圍: ±{max_abs_val:.0f}, 新範圍: ±{max_abs_val * scale_factor:.0f})")
                        elif max_abs_val > 30000:
                            # 防止削波，縮小過大的訊號
                            scale_factor = 20000.0 / max_abs_val
                            audio_f32 = audio_f32 * scale_factor
                            logger.debug(f"[{session_id}] 削波防護: 縮小 {1/scale_factor:.2f}x "
                                       f"(原始範圍: ±{max_abs_val:.0f}, 新範圍: ±{max_abs_val * scale_factor:.0f})")
                        else:
                            # 音訊品質良好，保持原貌
                            logger.debug(f"[{session_id}] 音訊品質良好，維持原始範圍: ±{max_abs_val:.0f}")
                        
                        # DEBUG: 檢查 frame 資料
                        logger.debug(f"[{session_id}] Frame {idx}: shape={audio_f32.shape}, "
                                   f"min={audio_f32.min():.4f}, max={audio_f32.max():.4f}, "
                                   f"mean={audio_f32.mean():.4f}, std={audio_f32.std():.4f}")
                        
                        # 偵測喚醒詞
                        try:
                            result = self.detect(audio_f32, session_id)
                            # detect 內部會觸發 callback（如果偵測到關鍵字）
                            
                            # 重置錯誤計數
                            error_count = 0
                            
                        except (WakewordAudioError, WakewordDetectionError) as e:
                            logger.error(f"喚醒詞偵測錯誤 [{session_id}]: {e}")
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
                # detect 內部會觸發 callback
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
        
        # 清除防抖動追蹤
        keys_to_remove = [k for k in self._last_detection_time.keys() 
                        if k.startswith(f"{session_id}_")]
        for key in keys_to_remove:
            del self._last_detection_time[key]
    
    def start_listening(
        self, 
        session_id: str, 
        callback: Callable[[WakewordDetection], None],
        model_path: Optional[str] = None
    ) -> bool:
        """開始監聽指定 session 的音訊流
        
        Args:
            session_id: Session ID
            callback: 當偵測到關鍵字時要呼叫的函數
            model_path: 自訂模型路徑或名稱（可選，使用預設模型）
            
        Returns:
            是否成功開始監聽
            
        Raises:
            WakewordSessionError: 當 session 管理發生錯誤
            WakewordInitializationError: 當服務初始化失敗
            
        Example:
            def on_wakeword(detection):
                print(f"Session {detection.session_id} 偵測到: {detection.keyword}")
            
            # 使用預設模型
            openwakeword.start_listening("session123", on_wakeword)
            
            # 使用自訂模型
            openwakeword.start_listening("session456", on_wakeword, "path/to/model.onnx")
        """
        # 驗證參數
        if not session_id:
            raise WakewordSessionError("Session ID 不能為空")
        
        if not callback or not callable(callback):
            raise WakewordSessionError("必須提供有效的回調函數")
        
        # 確保服務已初始化（如果初始化失敗會自動重試）
        try:
            if not self._ensure_initialized():
                raise WakewordInitializationError("服務初始化失敗，無法開始監聽")
        except Exception as e:
            raise WakewordInitializationError(f"服務初始化過程發生錯誤: {e}") from e
        
        # 如果已經在監聽，警告並返回
        if session_id in self._sessions and self._sessions[session_id].get("active"):
            logger.warning(f"Session {session_id} 已在監聽中，無需重複開始")
            return True  # 已經在監聽，視為成功
        
        # 如果指定了新模型，載入它
        if model_path and model_path != self._config.model_path:
            logger.info(f"Session {session_id} 使用自訂模型: {model_path}")
            # 注意：目前實作中所有 session 共用同一個模型
            # 如果需要每個 session 用不同模型，需要更複雜的架構
            # 這裡暫時記錄警告
            logger.warning("目前版本所有 session 共用同一個模型，自訂模型將套用到所有 sessions")
        
        # 註冊為音訊佇列的讀者
        from src.core.audio_queue_manager import audio_queue
        audio_queue.register_reader(session_id, "openwakeword")
        logger.debug(f"Registered OpenWakeWord as reader for session {session_id}")
        
        # 建立監聽執行緒
        def listen_loop():
            self._listening_loop(session_id, callback)
        
        # 建立並啟動執行緒
        try:
            thread = threading.Thread(
                target=listen_loop, 
                daemon=True, 
                name=f"wakeword-{session_id}"
            )
            
            # 儲存 session 資訊
            self._sessions[session_id] = {
                "callback": callback,
                "thread": thread,
                "active": True,
                "model_path": model_path
            }
            
            thread.start()
            logger.info(f"成功開始監聽 session: {session_id}")
            return True
            
        except Exception as e:
            raise WakewordSessionError(f"無法建立監聽執行緒: {e}") from e
    
    def stop_listening(self, session_id: str) -> bool:
        """停止監聽指定 session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止
            
        Raises:
            WakewordSessionError: 當 session 管理發生錯誤
        """
        if not session_id:
            raise WakewordSessionError("Session ID 不能為空")
        
        with self._session_lock:
            if session_id not in self._sessions:
                logger.warning(f"Session {session_id} 不存在")
                return False
            
            session = self._sessions[session_id]
            
            # 標記為非活動
            session["active"] = False
        
        # 設置停止旗標
        if session_id in self._stop_flags:
            self._stop_flags[session_id] = True
        
        # 清理該 session 的檢測時間記錄，避免下次重啟時誤觸發
        keys_to_remove = [key for key in self._last_detection_time.keys() if key.startswith(f"{session_id}_")]
        for key in keys_to_remove:
            del self._last_detection_time[key]
        if keys_to_remove:
            logger.info(f"🧹 Cleared detection time records for session {session_id}: {len(keys_to_remove)} records")
        
        # 清理 buffer manager
        if session_id in self._buffer_managers:
            self._buffer_managers[session_id].reset()
            del self._buffer_managers[session_id]
            logger.debug(f"Cleared buffer manager for session {session_id}")
        
        try:
            # 等待執行緒結束（最多等待 1 秒）
            thread = session.get("thread")
            if thread and thread.is_alive():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    logger.warning(f"Session {session_id} 執行緒未能及時停止")
            
            # 清理 session 記錄（不刪除，以便重新啟動）
            # 保留 session 但標記為非活動
            # del self._sessions[session_id]  # 不刪除，以便重新啟動
            
            logger.info(f"已停止監聽 session: {session_id}")
            return True
            
        except Exception as e:
            raise WakewordSessionError(
                f"停止 session {session_id} 時發生錯誤: {e}"
            ) from e
    
    def is_listening(self, session_id: str) -> bool:
        """檢查指定 session 是否正在監聽
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在監聽
        """
        return session_id in self._sessions and self._sessions[session_id].get("active", False)
    
    def get_active_sessions(self) -> List[str]:
        """取得所有正在監聽的 session ID
        
        Returns:
            活動中的 session ID 列表
        """
        return [sid for sid, info in self._sessions.items() if info.get("active", False)]
    
    def initialize(self, config: Optional[WakewordConfig] = None) -> bool:
        """初始化喚醒詞服務
        
        Args:
            config: 服務配置
            
        Returns:
            是否成功初始化
        """
        if config:
            self._config = config
        return self._ensure_initialized()
    
    def start_monitoring(
        self,
        session_id: str,
        keywords: Optional[List[str]] = None,
        on_detected: Optional[Callable[[str, WakewordDetection], None]] = None
    ) -> bool:
        """開始監控特定 session 的音訊
        
        Args:
            session_id: Session ID
            keywords: 要監聽的關鍵字列表（None 表示使用預設）
            on_detected: 檢測到喚醒詞時的回調
            
        Returns:
            是否成功開始監控
        """
        # 包裝 callback 以符合介面
        if on_detected:
            def wrapped_callback(detection):
                on_detected(session_id, detection)
            return self.start_listening(session_id, wrapped_callback)
        return self.start_listening(session_id, lambda x: None)
    
    def stop_monitoring(self, session_id: str) -> bool:
        """停止監控特定 session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功停止
        """
        return self.stop_listening(session_id)
    
    def is_monitoring(self, session_id: str) -> bool:
        """檢查是否正在監控特定 session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在監控
        """
        return self.is_listening(session_id)
    
    def process_chunk(
        self,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> Optional[WakewordDetection]:
        """處理單個音訊片段
        
        Args:
            audio_data: 音訊數據 (numpy array)
            sample_rate: 採樣率（如果與配置不同）
            
        Returns:
            檢測結果（如果有）
        """
        # 使用臨時 session ID 處理單個 chunk
        temp_session = "temp_chunk"
        return self.detect(audio_data, temp_session)
    
    def process_stream(
        self,
        session_id: str,
        audio_data: np.ndarray,
        sample_rate: Optional[int] = None
    ) -> Optional[WakewordDetection]:
        """處理串流音訊（保持 session 狀態）
        
        Args:
            session_id: Session ID
            audio_data: 音訊數據
            sample_rate: 採樣率
            
        Returns:
            檢測結果（如果有）
        """
        return self.detect(audio_data, session_id)
    
    def reset_session(self, session_id: str) -> bool:
        """重置特定 session 的狀態
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功重置
        """
        # 清理防抖動追蹤
        keys_to_remove = [k for k in self._last_detection_time.keys() 
                        if k.startswith(f"{session_id}_")]
        for key in keys_to_remove:
            del self._last_detection_time[key]
        
        # 重置 BufferManager
        if session_id in self._buffer_managers:
            self._buffer_managers[session_id].reset()
        
        return True
    
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 狀態資訊
        
        Args:
            session_id: Session ID
            
        Returns:
            狀態資訊
        """
        if session_id in self._sessions:
            session = self._sessions[session_id]
            return {
                "active": session.get("active", False),
                "model_path": session.get("model_path"),
                "has_callback": session.get("callback") is not None,
                "thread_alive": session.get("thread", None) and session["thread"].is_alive()
            }
        return None
    
    def set_default_hook(
        self,
        on_detected: Optional[Callable[[str, WakewordDetection], None]] = None
    ) -> None:
        """設定預設的檢測 hook
        
        Args:
            on_detected: 檢測到喚醒詞時的預設回調
        """
        # 本實作中不使用預設 hook，每個 session 有自己的 callback
        logger.warning("OpenWakeword 不支援預設 hook，請為每個 session 設定獨立的 callback")
    
    def get_monitoring_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得監控資訊
        
        Args:
            session_id: Session ID
            
        Returns:
            監控資訊（如果正在監控）
        """
        if self.is_listening(session_id):
            return {
                "status": "monitoring",
                "session_id": session_id,
                "model_initialized": self._initialized,
                "config": {
                    "threshold": self._config.threshold if self._config else None,
                    "sample_rate": self._config.sample_rate if self._config else None,
                    "chunk_size": self._config.chunk_size if self._config else None
                }
            }
        return None
    
    def stop_all_monitoring(self) -> int:
        """停止所有監控
        
        Returns:
            停止的監控數量
        """
        active_sessions = self.get_active_sessions()
        count = len(active_sessions)
        
        for session_id in active_sessions:
            self.stop_listening(session_id)
        
        return count
    
    def get_config(self) -> Optional[WakewordConfig]:
        """取得當前配置
        
        Returns:
            當前配置
        """
        return self._config
    
    def update_config(self, config: WakewordConfig) -> bool:
        """更新配置
        
        Args:
            config: 新配置
            
        Returns:
            是否成功更新
        """
        try:
            self._config = config
            # 如果模型路徑改變，重新載入模型
            if config.model_path != self._config.model_path:
                self._load_model()
            return True
        except Exception as e:
            logger.error(f"更新配置失敗: {e}")
            return False
    
    def shutdown(self):
        """關閉服務"""
        logger.info("關閉 OpenWakeword 服務")
        
        # 停止所有活動的 sessions
        active_sessions = list(self._sessions.keys())
        for session_id in active_sessions:
            self.stop_listening(session_id)
        
        # 清除防抖動追蹤
        self._last_detection_time.clear()
        
        # 釋放模型
        self._model = None
        self._initialized = False
        
        logger.info("OpenWakeword 服務已關閉")
    
    
    def is_initialized(self) -> bool:
        """檢查服務是否已初始化"""
        return self._initialized
    
    

# 模組級單例
openwakeword: OpenWakeword = OpenWakeword()

__all__ = ['OpenWakeword', 'openwakeword']