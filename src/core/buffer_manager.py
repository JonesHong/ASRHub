"""音訊緩衝區管理服務

使用範例：
    # 固定大小模式（如 VAD）
    from src.interface.buffer import BufferConfig
    config = BufferConfig.for_silero_vad()
    buffer = BufferManager(config)
    buffer.push(audio_data)
    if buffer.ready():
        frame = buffer.pop()
    
    # 滑動窗口模式（如 Whisper）
    config = BufferConfig.for_whisper()
    buffer = BufferManager(config)
    
    # 動態模式
    config = BufferConfig(mode="dynamic")
    buffer = BufferManager(config)

為不同 ASR 服務提供統一的音訊切窗管理。
支援 fixed、sliding、dynamic 三種模式。
遵循 KISS 原則 - 簡單、清楚、可維護。
"""

from typing import List, Optional, Tuple
import threading

from src.interface.buffer import IBufferManager, BufferConfig
from src.utils.logger import logger
from src.config.manager import ConfigManager


class BufferManager(IBufferManager):
    """
    通用 Buffer 管理：
    - fixed   : 依 frame_size 取整窗，無重疊（step = frame）
    - sliding : 依 frame_size 取窗，依 step_size 滑動（可重疊）
    - dynamic : 依 min/max_duration 聚合，或由呼叫端決定 flush 時機
    """

    def __init__(self, cfg: BufferConfig):
        """初始化 BufferManager。
        
        Args:
            cfg: 緩衝區配置
            
        Raises:
            ValueError: 如果配置無效
        """
        # 驗證配置
        if not cfg:
            raise ValueError("BufferConfig is required")
        
        if cfg.sample_width <= 0:
            raise ValueError(f"sample_width must be > 0, got {cfg.sample_width}")
        
        if cfg.channels <= 0:
            raise ValueError(f"channels must be > 0, got {cfg.channels}")
        
        if cfg.sample_rate <= 0:
            raise ValueError(f"sample_rate must be > 0, got {cfg.sample_rate}")
        
        if cfg.mode not in ("fixed", "sliding", "dynamic"):
            raise ValueError(f"Invalid mode: {cfg.mode}, must be 'fixed', 'sliding', or 'dynamic'")
        
        self.cfg = cfg
        self._buf = bytearray()

        self._bytes_per_sample = cfg.sample_width * cfg.channels
        if self._bytes_per_sample <= 0:
            raise ValueError(f"bytes_per_sample must be > 0, got {self._bytes_per_sample}")

        def samp2bytes(samp: Optional[int]) -> Optional[int]:
            return None if samp is None else samp * self._bytes_per_sample

        self._frame_bytes = samp2bytes(cfg.frame_size)
        self._step_bytes = samp2bytes(cfg.step_size) if cfg.step_size is not None else self._frame_bytes

        # 驗證模式相關參數
        if cfg.mode in ("fixed", "sliding"):
            if self._frame_bytes is None or self._frame_bytes <= 0:
                raise ValueError(f"{cfg.mode} mode requires positive frame_size")
            if cfg.mode == "sliding":
                if self._step_bytes is None or not (0 < self._step_bytes <= self._frame_bytes):
                    raise ValueError("sliding mode requires 0 < step_size <= frame_size")

        # dynamic 門檻（毫秒換算成 bytes）
        self._min_dynamic_bytes = self._ms_to_bytes(cfg.min_duration_ms) if cfg.min_duration_ms else None
        self._max_dynamic_bytes = self._ms_to_bytes(cfg.max_duration_ms) if cfg.max_duration_ms else None
        
        # 驗證 dynamic 模式參數
        if cfg.mode == "dynamic":
            if self._max_dynamic_bytes and self._min_dynamic_bytes:
                if self._max_dynamic_bytes < self._min_dynamic_bytes:
                    raise ValueError(f"max_duration_ms must be >= min_duration_ms")
        
        logger.info(f"BufferManager initialized (mode={cfg.mode}, frame_size={cfg.frame_size}, "
                   f"step_size={cfg.step_size}, sample_rate={cfg.sample_rate}Hz)")

    # ---------- 公用工具 ----------
    def _ms_to_bytes(self, ms: int) -> int:
        """將毫秒轉換為位元組數。
        
        Args:
            ms: 毫秒數
            
        Returns:
            對應的位元組數
        """
        if ms <= 0:
            logger.warning(f"Invalid milliseconds value: {ms}, using 1")
            return 1
        
        bytes_per_sec = self.cfg.sample_rate * self._bytes_per_sample
        return max(1, int(bytes_per_sec * (ms / 1000.0)))

    def buffered_bytes(self) -> int:
        """取得緩衝區中的位元組數。
        
        Returns:
            緩衝區大小（位元組）
        """
        try:
            return len(self._buf)
        except Exception as e:
            logger.error(f"Failed to get buffered bytes: {e}")
            return 0

    def reset(self) -> bool:
        """重置緩衝區。
        
        Returns:
            是否成功重置
        """
        try:
            buffer_size = len(self._buf)
            self._buf.clear()
            if buffer_size > 0:
                logger.debug(f"Reset buffer, cleared {buffer_size} bytes")
            return True
        except Exception as e:
            logger.error(f"Failed to reset buffer: {e}")
            return False

    # ---------- 實作 ----------
    def push(self, audio_bytes: bytes) -> bool:
        """推入音訊資料到緩衝區。
        
        Returns:
            是否成功推入
        """
        try:
            if not audio_bytes:
                logger.warning("Empty audio bytes provided to push")
                return False
            
            if not isinstance(audio_bytes, (bytes, bytearray)):
                logger.error(f"Invalid type for audio_bytes: {type(audio_bytes)}")
                return False
            
            self._buf.extend(audio_bytes)

            # 防爆線機制（可選）
            if self.cfg.max_buffer_size and len(self._buf) > self.cfg.max_buffer_size:
                overflow = len(self._buf) - self.cfg.max_buffer_size
                del self._buf[:overflow]
                logger.warning(f"Buffer overflow, dropped {overflow} bytes (max_size={self.cfg.max_buffer_size})")
            
            logger.trace(f"Pushed {len(audio_bytes)} bytes to buffer (total={len(self._buf)})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to push audio bytes: {e}")
            return False

    def ready(self) -> bool:
        """檢查緩衝區是否就緒。
        
        Returns:
            是否就緒可以取出資料
        """
        try:
            if self.cfg.mode in ("fixed", "sliding"):
                return len(self._buf) >= (self._frame_bytes or 0)
            # dynamic
            if self._min_dynamic_bytes is None:
                # dynamic 無門檻 → 交由 flush 決定
                return False
            return len(self._buf) >= self._min_dynamic_bytes
        except Exception as e:
            logger.error(f"Failed to check if buffer is ready: {e}")
            return False

    def pop(self) -> Optional[bytes]:
        """從緩衝區取出音訊資料。
        
        Returns:
            音訊資料或 None（如果緩衝區未就緒）
        """
        try:
            if not self.ready():
                logger.trace("Buffer not ready for pop")
                return None

            if self.cfg.mode == "fixed":
                if self._frame_bytes is None:
                    logger.error("Frame bytes not set for fixed mode")
                    return None
                frame = bytes(self._buf[:int(self._frame_bytes)])
                del self._buf[:int(self._frame_bytes)]
                logger.trace(f"Popped fixed frame of {len(frame)} bytes")
                return frame

            if self.cfg.mode == "sliding":
                if self._frame_bytes is None or self._step_bytes is None:
                    logger.error("Frame/step bytes not set for sliding mode")
                    return None
                # 取窗長 frame，但只前進 step（可能重疊）
                frame = bytes(self._buf[:int(self._frame_bytes)])
                del self._buf[:int(self._step_bytes)]
                logger.trace(f"Popped sliding frame of {len(frame)} bytes, stepped {self._step_bytes} bytes")
                return frame

            # dynamic
            if self._min_dynamic_bytes is not None:
                size = len(self._buf)
                # 若設了 max_dynamic_bytes，避免過大；否則就取到目前全部
                if self._max_dynamic_bytes and size > self._max_dynamic_bytes:
                    size = int(self._max_dynamic_bytes)
                frame = bytes(self._buf[:size])
                del self._buf[:size]
                logger.trace(f"Popped dynamic frame of {len(frame)} bytes")
                return frame

            # dynamic 無門檻，交由 flush
            logger.trace("Dynamic mode without threshold, waiting for flush")
            return None
            
        except Exception as e:
            logger.error(f"Failed to pop from buffer: {e}")
            return None

    def pop_all(self) -> List[bytes]:
        """取出所有就緒的音訊資料。
        
        Returns:
            音訊資料列表（可能為空）
        """
        try:
            out: List[bytes] = []
            # 從配置獲取最大迭代次數
            config = ConfigManager()
            max_iterations = config.performance.max_iterations if hasattr(config, 'performance') and hasattr(config.performance, 'max_iterations') else 1000
            iterations = 0
            
            while self.ready() and iterations < max_iterations:
                f = self.pop()
                if f is None:
                    break
                out.append(f)
                iterations += 1
            
            if iterations >= max_iterations:
                logger.warning(f"pop_all reached max iterations ({max_iterations})")
            
            if out:
                logger.trace(f"Popped {len(out)} frames from buffer")
            
            return out
            
        except Exception as e:
            logger.error(f"Failed to pop all from buffer: {e}")
            return []

    def flush(self) -> Optional[bytes]:
        """強制輸出所有緩衝區資料並清空。
        
        Returns:
            緩衝區中的所有資料或 None（如果緩衝區為空）
        """
        try:
            if not self._buf:
                logger.trace("Buffer is empty, nothing to flush")
                return None
            
            buffer_size = len(self._buf)

            if self.cfg.mode in ("fixed", "sliding"):
                # 強制把目前緩衝輸出為一個 frame（不足者 zero-pad 或直接輸出殘量）
                # 這裡採「直接輸出殘量」，由下游決定是否 pad
                frame = bytes(self._buf)
                self._buf.clear()
                logger.debug(f"Flushed {buffer_size} bytes from {self.cfg.mode} mode buffer")
                return frame

            # dynamic: 直接輸出全部
            frame = bytes(self._buf)
            self._buf.clear()
            logger.debug(f"Flushed {buffer_size} bytes from dynamic mode buffer")
            return frame
            
        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}")
            return None


# ============== 使用建議 ==============

"""
建議搭配（以 16kHz, mono, int16 為例）：

1) Silero VAD
   - 目的：快速偵測語音起訖，低延遲 + 穩定
   - 推薦配置：
        cfg = BufferConfig.for_silero_vad(sample_rate=16000, window_ms=400)
        bm = BufferManager(cfg)
   - 流程：push(chunk) → while bm.ready(): vad_in = bm.pop()

2) openWakeWord
   - 目的：關鍵字喚醒，模型通常要求固定 frame 大小（e.g., 512/1024 samples）
   - 推薦配置：
        cfg = BufferConfig.for_openwakeword(sample_rate=16000, frame_samples=512)
        bm = BufferManager(cfg)
   - 流程：push → while ready → pop，確保每窗維度一致

3) FunASR (Streaming)
   - 目的：串流 ASR，依賴固定 context window（常見 9600 samples ≈ 0.6s）
   - 推薦配置：
        cfg = BufferConfig.for_funasr(sample_rate=16000, frame_samples=9600)
        bm = BufferManager(cfg)

4) Whisper / faster-whisper
   - 目的：大段語音片段轉譯，建議長窗 + 重疊避免斷句
   - 推薦配置（5s 窗，50% overlap）：
        cfg = BufferConfig.for_whisper(sample_rate=16000, window_sec=5.0, overlap=0.5)
        bm = BufferManager(cfg)
   - 流程：push → while ready → pop（得到滑動窗輸入）；或在段落結束時 bm.flush()

通用原則：
- AudioQueueManager 僅負責「存取」；BufferManager 放在各服務內，依該服務需求切窗。
- 若擔心記憶體，可設 cfg.max_buffer_bytes。
- dynamic 模式：當你想以「時間門檻」聚合（min/max_duration_ms）或由上層事件（如靜音）觸發 flush。
"""