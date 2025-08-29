"""
Silero VAD Operator
使用 Silero VAD 模型進行語音活動檢測
"""

import asyncio
import time
from typing import Dict, Any, Optional, Tuple
import numpy as np
import onnxruntime as ort
from pathlib import Path

from src.operators.base import OperatorBase
from src.core.exceptions import PipelineError
from src.utils.logger import logger
from src.audio import AudioMetadata, AudioSampleFormat
from .model_downloader import ensure_vad_model

# 模組級變數 - 直接導入和實例化
from src.config.manager import ConfigManager
from src.store import get_global_store
from src.core.audio_queue_manager import AudioQueueManager
from src.core.timer_manager import TimerManager

config_manager = ConfigManager()
store = get_global_store()
timer_manager = TimerManager()
audio_queue_manager = AudioQueueManager()


class SileroVADOperator(OperatorBase):
    """使用 Silero VAD 模型進行語音活動檢測"""
    
    def __init__(self):
        """
        初始化 Silero VAD Operator
        使用模組級變數和 TimerManager 管理計時器
        """
        super().__init__()
        
        
        # 用於追蹤當前 session_id
        self.current_session_id = None
        
        self.model = None
        self.h = None  # 隱藏狀態 h
        self.c = None  # 隱藏狀態 c
        
        # 獲取格式要求 - 單一真相來源
        self.required_format = self.get_required_audio_format()
        self.window_size_samples = 512  # Silero VAD 使用 512 樣本窗口
        
        # 從配置中獲取設定 - 配置必須存在
        vad_config = config_manager.operators.vad
        # 根據 VAD 類型獲取對應的配置，預設使用 silero
        if vad_config.type == "silero":
            silero_config = vad_config.silero
            self.threshold = silero_config.threshold
            self.min_silence_duration = silero_config.min_silence_duration
            self.min_speech_duration = silero_config.min_speech_duration
            self.model_path = silero_config.model_path
            # 進階功能
            self.adaptive_threshold = silero_config.adaptive_threshold
            self.smoothing_window = silero_config.smoothing_window
            # 自適應閾值窗口大小
            self.threshold_window_size = silero_config.threshold_window_size
        else:
            raise ValueError(f"不支援的 VAD 類型: {vad_config.type}")
        
        # 狀態追蹤
        self.in_speech = False
        self.speech_start_time = None
        self.speech_end_time = None
        self.silence_start_time = None
        self.speech_duration = 0
        self.silence_duration = 0
        self.last_speech_end_time = None  # 記錄最後一次語音結束時間
        
        # 緩衝區（處理跨幀音訊）
        self.audio_buffer = bytearray()
        
        # 統計資訊
        self.total_speech_frames = 0
        self.total_silence_frames = 0
        self.total_frames_processed = 0
        self.frame_count = 0  # 添加幀計數器
        
        # 進階功能狀態
        self.threshold_history = []  # 用於自適應閾值
        self.probability_history = []  # 用於平滑處理
        self.last_speech_prob = 0.0  # 保存最後的語音機率
        
        # 回調函數
        self.speech_start_callback = None
        self.speech_end_callback = None
        self.vad_result_callback = None
    
    def get_required_audio_format(self) -> AudioMetadata:
        """
        獲取 Silero VAD 需要的音頻格式
        
        Silero VAD v4 模型需求：
        - 採樣率：16000 Hz（模型訓練時的採樣率）
        - 聲道數：1（模型只支援單聲道）
        - 格式：int16（雖然內部會轉換為 float32，但輸入接受 int16）
        
        Returns:
            需要的音頻格式
        """
        return AudioMetadata(
            sample_rate=config_manager.audio.default_sample_rate,  # 從配置讀取
            channels=config_manager.audio.channels,               # 從配置讀取
            format=AudioSampleFormat.INT16  # 接受 int16 輸入
        )
    
    def get_output_audio_format(self) -> Optional[AudioMetadata]:
        """
        VAD 不改變音頻格式，只是過濾和標記
        
        Returns:
            None 表示輸出格式與輸入相同
        """
        return None
    
    async def _initialize(self):
        """初始化 VAD 模型"""
        logger.info("初始化 Silero VAD 模型...")
        
        try:
            # 檢查模型文件是否存在，如果不存在則自動下載
            model_path = Path(self.model_path)
            if not model_path.exists():
                logger.info("模型文件不存在，開始自動下載...")
                # 從配置中獲取模型名稱
                # 檢查是否有 model_name 配置
                try:
                    vad_config = config_manager.operators.vad
                    if vad_config.type == "silero":
                        model_name = vad_config.silero.model_name
                except AttributeError:
                    pass
                models_dir = model_path.parent
                
                # 確保模型已下載
                model_path = await ensure_vad_model(model_name, str(models_dir))
                self.model_path = str(model_path)
            
            # 載入 ONNX 模型
            logger.info(f"載入 VAD 模型: {model_path}")
            
            # 設定 ONNX Runtime 選項
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            
            # 檢查可用的 providers
            available_providers = ort.get_available_providers()
            providers = ['CUDAExecutionProvider']  # 預設使用 GPU
            
            # 如果有 GPU 可用，優先使用
            use_gpu = True
            try:
                vad_config = config_manager.operators.vad
                if vad_config.type == "silero":
                    use_gpu = vad_config.silero.use_gpu
            except AttributeError:
                pass
            
            if 'CUDAExecutionProvider' in available_providers and use_gpu:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                logger.info("使用 GPU 加速")
            
            self.model = ort.InferenceSession(
                str(model_path),
                sess_options=sess_options,
                providers=providers
            )
            
            # 獲取模型輸入輸出資訊
            self.inputs = self.model.get_inputs()
            self.outputs = self.model.get_outputs()
            
            # 記錄所有輸入
            logger.info("模型輸入:")
            for i, inp in enumerate(self.inputs):
                logger.info(f"  輸入 {i}: {inp.name}, 形狀: {inp.shape}, 類型: {inp.type}")
            
            # 記錄所有輸出
            logger.info("模型輸出:")
            for i, out in enumerate(self.outputs):
                logger.info(f"  輸出 {i}: {out.name}, 形狀: {out.shape}, 類型: {out.type}")
                
            # 設置主要輸入輸出名稱
            self.input_name = self.inputs[0].name
            self.output_name = self.outputs[0].name
            
            # 初始化隱藏狀態 (如果模型需要)
            if len(self.inputs) > 2:
                # 檢查是否有 h 和 c 輸入
                for inp in self.inputs:
                    if inp.name == 'h':
                        # 從形狀中獲取維度 [2, batch, hidden_size]
                        shape = inp.shape
                        # shape[2] 可能是動態的，使用預設值 64
                        hidden_size = 64 if isinstance(shape[2], str) else shape[2]
                        self.h = np.zeros((2, 1, hidden_size), dtype=np.float32)
                        logger.info(f"初始化隱藏狀態 h: shape=(2, 1, {hidden_size})")
                    elif inp.name == 'c':
                        # 從形狀中獲取維度 [2, batch, hidden_size]
                        shape = inp.shape
                        # shape[2] 可能是動態的，使用預設值 64
                        hidden_size = 64 if isinstance(shape[2], str) else shape[2]
                        self.c = np.zeros((2, 1, hidden_size), dtype=np.float32)
                        logger.info(f"初始化隱藏狀態 c: shape=(2, 1, {hidden_size})")
            
            logger.info("✓ Silero VAD 模型初始化完成")
            
        except Exception as e:
            logger.error(f"初始化 VAD 模型失敗: {e}")
            raise PipelineError(f"VAD 初始化失敗: {e}")
    
    async def _cleanup(self):
        """清理資源"""
        logger.info("清理 Silero VAD 資源...")
        
        # 清空緩衝區
        self.audio_buffer.clear()
        
        # 重置狀態
        self.in_speech = False
        self.speech_start_time = None
        self.speech_end_time = None
        self.silence_start_time = None
        
        # 釋放模型
        self.model = None
        
        logger.info("✓ Silero VAD 資源清理完成")
    
    async def _process_window(self, window_bytes: bytes, vad_results: list, kwargs: dict):
        """處理單個窗口的音訊"""
        # 轉換為 numpy array - 使用統一的格式
        audio_np = np.frombuffer(window_bytes, dtype=self.required_format.format.numpy_dtype).astype(np.float32)
        audio_np = audio_np / 32768.0  # 正規化到 [-1, 1]
        
        # 執行 VAD 推論
        speech_prob = await self._run_vad_inference(audio_np)
        
        # 增加幀計數
        self.frame_count += 1
        
        # 調試輸出
        if self.frame_count <= 5:  # 前 5 幀都輸出
            logger.info(f"VAD 推論結果: 幀={self.frame_count}, 機率={speech_prob:.4f}, 音訊能量={np.abs(audio_np).mean():.4f}, 閾值={self.threshold}")
        
        # 應用平滑處理
        speech_prob = self._apply_smoothing(speech_prob)
        
        # 保存最後的語音機率
        self.last_speech_prob = float(speech_prob)
        
        # 判斷是否為語音（可能使用自適應閾值）
        current_threshold = self._get_adaptive_threshold() if self.adaptive_threshold else self.threshold
        is_speech = speech_prob > current_threshold
        
        # 更新狀態
        current_time = time.time()
        await self._update_speech_state(is_speech, current_time, speech_prob, **kwargs)
        
        # 更新閾值歷史（用於自適應閾值）
        if self.adaptive_threshold:
            self._update_threshold_history(speech_prob)
        
        vad_results.append({
            'speech_detected': is_speech,
            'speech_probability': float(speech_prob),
            'timestamp': current_time
        })
        
        self.total_frames_processed += 1
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊並返回 VAD 結果
        
        Args:
            audio_data: 輸入音訊資料
            **kwargs: 額外參數
            
        Returns:
            audio_data: 透傳音訊，附加 VAD 資訊在 kwargs 中
        """
        # 更新當前 session_id
        self.current_session_id = kwargs.get('session_id')
        
        if not self.enabled or not self._initialized:
            return audio_data
        
        if not self.validate_audio_params(audio_data):
            return None
        
        # 調試：檢查接收到的音訊
        if self.frame_count == 0:
            logger.debug(f"第一次接收音訊: {len(audio_data)} bytes")
            if 'metadata' in kwargs:
                meta = kwargs['metadata']
                if hasattr(meta, 'sample_rate'):  # 確認是 AudioMetadata 對象
                    logger.debug(f"音訊格式: {meta.sample_rate}Hz, {meta.channels}ch, {meta.format}")
        
        try:
            # 添加音訊到緩衝區
            self.audio_buffer.extend(audio_data)
            
            # 處理完整的窗口
            bytes_per_sample = self.required_format.format.bytes_per_sample
            window_size_bytes = self.window_size_samples * bytes_per_sample
            
            # 調試：第一次處理時顯示資訊
            if self.frame_count == 0:
                logger.info(f"VAD 窗口參數: 樣本數={self.window_size_samples}, 每樣本位元組={bytes_per_sample}, 窗口大小={window_size_bytes} bytes")
                logger.info(f"緩衝區大小: {len(self.audio_buffer)} bytes")
            
            vad_results = []
            
            # 計算需要處理的窗口數
            num_windows = len(self.audio_buffer) // window_size_bytes
            
            # 如果有多個窗口要處理，顯示處理資訊
            if num_windows > 5:
                logger.debug(f"VAD 開始處理 {num_windows} 個音訊窗口")
                window_idx = 0
                while len(self.audio_buffer) >= window_size_bytes:
                    # 每處理 10 個窗口顯示一次進度
                    if window_idx % 10 == 0:
                        logger.debug(f"VAD 處理進度: {window_idx + 1}/{num_windows}")
                    
                    # 提取一個窗口的音訊
                    window_bytes = self.audio_buffer[:window_size_bytes]
                    self.audio_buffer = self.audio_buffer[window_size_bytes:]
                    
                    # 處理窗口（與原邏輯相同）
                    await self._process_window(window_bytes, vad_results, kwargs)
                    window_idx += 1
                
                logger.debug(f"VAD 處理完成，共處理 {window_idx} 個窗口")
            else:
                # 少量窗口不需要進度條
                while len(self.audio_buffer) >= window_size_bytes:
                    # 提取一個窗口的音訊
                    window_bytes = self.audio_buffer[:window_size_bytes]
                    self.audio_buffer = self.audio_buffer[window_size_bytes:]
                    
                    # 處理窗口
                    await self._process_window(window_bytes, vad_results, kwargs)
                
            
            # 將 VAD 結果附加到 kwargs
            # 確保有個字典來存放 VAD 結果
            if 'vad_info' not in kwargs:
                kwargs['vad_info'] = {}
            
            kwargs['vad_info'] = {
                'results': vad_results,
                'in_speech': self.in_speech,
                'continuous_speech': self.speech_duration,
                'continuous_silence': self.silence_duration,
                'stats': {
                    'total_frames': self.total_frames_processed,
                    'speech_frames': self.total_speech_frames,
                    'silence_frames': self.total_silence_frames
                }
            }
            
            # 觸發結果回調
            if self.vad_result_callback and vad_results:
                for result in vad_results:
                    await self.vad_result_callback(result)
            
            return audio_data
            
        except Exception as e:
            logger.error(f"VAD 處理錯誤: {e}")
            raise PipelineError(f"VAD 處理失敗: {e}")
    
    def update_config(self, config: Dict[str, Any]):
        """
        更新 VAD 配置
        
        Args:
            config: 配置字典
        """
        logger.debug(f"VAD 配置更新: {config}")
        
        # 更新基本參數
        if 'threshold' in config:
            self.threshold = config['threshold']
            logger.info(f"VAD 閾值更新為: {self.threshold}")
        
        if 'min_silence_duration' in config:
            self.min_silence_duration = config['min_silence_duration']
            
        if 'min_speech_duration' in config:
            self.min_speech_duration = config['min_speech_duration']
            
        if 'adaptive_threshold' in config:
            self.adaptive_threshold = config['adaptive_threshold']
            
        if 'smoothing_window' in config:
            self.smoothing_window = config['smoothing_window']
    
    async def _run_vad_inference(self, audio_chunk: np.ndarray) -> float:
        """
        執行 VAD 推論
        
        Args:
            audio_chunk: 音訊樣本 (正規化的 float32)
            
        Returns:
            語音機率 (0-1)
        """
        try:
            # 準備輸入張量
            # Silero VAD 期望輸入形狀: [batch_size, samples]
            input_tensor = audio_chunk.reshape(1, -1)
            
            # 執行推論 - 使用統一的採樣率
            ort_inputs = {
                'input': input_tensor,
                'sr': np.array(self.required_format.sample_rate, dtype=np.int64)
            }
            
            # 添加隱藏狀態
            if self.h is not None and self.c is not None:
                ort_inputs['h'] = self.h.astype(np.float32)
                ort_inputs['c'] = self.c.astype(np.float32)
            
            # 取得所有輸出
            ort_outputs = self.model.run(None, ort_inputs)
            
            # 提取語音機率
            speech_prob = ort_outputs[0][0].item()
            
            # 更新隱藏狀態 (如果有 hn 和 cn 輸出)
            if len(ort_outputs) >= 3:
                self.h = ort_outputs[1]  # hn
                self.c = ort_outputs[2]  # cn
            
            # 調試輸出
            if speech_prob > 0.01:  # 只輸出有意義的機率值
                logger.debug(f"VAD 機率: {speech_prob:.4f}, 閾值: {self.threshold}")
            
            return speech_prob
            
        except Exception as e:
            logger.error(f"VAD 推論錯誤: {e}")
            raise
    
    async def _update_speech_state(self, is_speech: bool, timestamp: float, speech_prob: float, **kwargs):
        """
        更新語音/靜音狀態
        
        Args:
            is_speech: 是否檢測到語音
            timestamp: 當前時間戳
            speech_prob: 語音機率
        """
        frame_duration = self.window_size_samples / self.required_format.sample_rate
        
        if is_speech:
            self.total_speech_frames += 1
            
            if not self.in_speech:
                # 語音開始
                self.speech_start_time = timestamp
                self.in_speech = True
                self.silence_duration = 0
                self.silence_start_time = None  # 重置靜音開始時間
                self._silence_detected_triggered = False  # 重置靜音觸發標記
                
                logger.debug(f"語音開始 (機率: {speech_prob:.3f})")
                
                # 使用 TimerManager 取消靜音計時器
                if self.current_session_id:
                    timer = timer_manager.get_timer(self.current_session_id)
                    if timer:
                        await timer.on_speech_detected()
                    else:
                        logger.debug(f"No timer found for session: {self.current_session_id}")
                
                # 優先使用 Store dispatch，否則使用回呼（向後相容）
                if self.store:
                    # 直接 dispatch speech_detected action
                    from src.store.sessions.sessions_actions import speech_detected
                    self.store.dispatch(speech_detected(
                        session_id=kwargs.get("session_id"),
                        timestamp=timestamp,
                        confidence=float(speech_prob)
                    ))
                elif self.speech_start_callback:
                    # 保留回呼介面（向後相容）
                    await self.speech_start_callback({
                        'timestamp': timestamp,
                        'speech_probability': speech_prob
                    })
            
            # 更新語音持續時間
            if self.speech_start_time:
                self.speech_duration = timestamp - self.speech_start_time
        else:
            self.total_silence_frames += 1
            
            if self.in_speech:
                # 語音結束，開始靜音計時
                if self.silence_start_time is None:
                    self.silence_start_time = timestamp
                    logger.debug(f"開始追蹤靜音時間")
                    
                # 計算靜音持續時間
                silence_elapsed = timestamp - self.silence_start_time
                
                # 檢查最小語音持續時間
                speech_duration = timestamp - self.speech_start_time if self.speech_start_time else 0
                if speech_duration >= self.min_speech_duration:
                    # 語音足夠長，標記語音結束
                    logger.info(f"🔇 語音結束 (語音時長: {speech_duration:.3f}s)")
                    
                    # 記錄語音結束
                    self.speech_end_time = timestamp
                    self.last_speech_end_time = self.speech_end_time
                    self.in_speech = False
                    self.speech_duration = 0
                    # 不要重置 silence_start_time，因為我們需要繼續計算靜音時間
                    
                    # 立即 dispatch silence_started action 表示進入靜音狀態
                    if self.store:
                        from src.store.sessions.sessions_actions import silence_started
                        logger.info(f"📢 Dispatching silence_started - 進入靜音狀態")
                        self.store.dispatch(silence_started(
                            session_id=kwargs.get("session_id"),
                            timestamp=timestamp
                        ))
                    
                    # 觸發語音結束回呼（如果有）
                    if self.speech_end_callback:
                        await self.speech_end_callback({
                            'speech_duration': speech_duration,
                            'timestamp': timestamp
                        })
                # else: 語音太短，繼續等待
                
            else:
                # 持續靜音
                if self.silence_start_time:
                    # 計算靜音持續時間
                    silence_elapsed = timestamp - self.silence_start_time
                    self.silence_duration = silence_elapsed
                    
                    # 檢查是否達到最小靜音持續時間（確認為穩定靜音）
                    if not hasattr(self, '_silence_detected_triggered') or not self._silence_detected_triggered:
                        if silence_elapsed >= self.min_silence_duration:
                            # 靜音已持續足夠時間，現在才觸發 silence_detected
                            logger.info(f"✅ 確認靜音狀態，開始倒數計時器 (靜音已持續: {silence_elapsed:.3f}s)")
                            
                            # 標記已觸發，避免重複
                            self._silence_detected_triggered = True
                            
                            # 使用 TimerManager 開始靜音計時器
                            if self.current_session_id:
                                timer = timer_manager.get_timer(self.current_session_id)
                                if timer:
                                    logger.info(f"啟動靜音計時器 for session: {self.current_session_id}")
                                    await timer.on_silence_detected()
                                else:
                                    logger.warning(f"No timer found for session: {self.current_session_id}")
                            
                            # Dispatch silence_detected action（現在才開始倒數）
                            if self.store:
                                from src.store.sessions.sessions_actions import silence_detected
                                # 從配置讀取倒數時間
                                try:
                                    countdown_duration = self.config_manager.operators.recording.vad_control.silence_countdown
                                except:
                                    countdown_duration = 1.8  # 預設值
                                    
                                logger.info(f"📢 Dispatching silence_detected with countdown: {countdown_duration}s")
                                self.store.dispatch(silence_detected(
                                    session_id=kwargs.get("session_id"),
                                    duration=countdown_duration,
                                    timestamp=timestamp
                                ))
    
    def set_speech_callbacks(self, 
                            start_callback=None, 
                            end_callback=None, 
                            result_callback=None):
        """
        設置語音事件回調函數
        
        Args:
            start_callback: 語音開始回調
            end_callback: 語音結束回調
            result_callback: VAD 結果回調
        """
        self.speech_start_callback = start_callback
        self.speech_end_callback = end_callback
        self.vad_result_callback = result_callback
    
    def get_state(self) -> Dict[str, Any]:
        """
        獲取當前 VAD 狀態
        
        Returns:
            狀態字典
        """
        return {
            'in_speech': self.in_speech,
            'speech_duration': self.speech_duration,
            'silence_duration': self.silence_duration,
            'total_frames_processed': self.total_frames_processed,
            'total_speech_frames': self.total_speech_frames,
            'total_silence_frames': self.total_silence_frames,
            'speech_ratio': self.total_speech_frames / max(1, self.total_frames_processed),
            'speech_probability': getattr(self, 'last_speech_prob', 0.0)  # 添加當前語音機率
        }
    
    def get_info(self) -> Dict[str, Any]:
        """
        獲取 Operator 資訊
        
        Returns:
            包含 VAD 狀態的資訊字典
        """
        # 先取得基礎資訊
        info = super().get_info()
        
        # 加入 VAD 特定狀態
        vad_state = self.get_state()
        info.update({
            'is_speaking': self.in_speech,
            'speech_probability': vad_state['speech_probability'],
            'in_speech': vad_state['in_speech'],
            'speech_duration': vad_state['speech_duration'],
            'silence_duration': vad_state['silence_duration']
        })
        
        return info
    
    async def reset_state(self):
        """重置 VAD 狀態"""
        self.in_speech = False
        self.speech_start_time = None
        self.speech_end_time = None
        self.silence_start_time = None
        self.speech_duration = 0
        self.silence_duration = 0
        self.total_speech_frames = 0
        self.total_silence_frames = 0
        self.total_frames_processed = 0
        
        # 重置模型狀態張量
        if hasattr(self, 'model') and self.model is not None:
            # 重置隱藏狀態
            if hasattr(self, 'h') and hasattr(self, 'c'):
                # 保持原有形狀
                if self.h is not None:
                    self.h = np.zeros_like(self.h)
                if self.c is not None:
                    self.c = np.zeros_like(self.c)
                logger.debug("重置 VAD 隱藏狀態")
        self.audio_buffer.clear()
        
        logger.debug("VAD 狀態已重置")
    
    def _apply_smoothing(self, probability: float) -> float:
        """
        應用平滑處理以減少誤判
        
        Args:
            probability: 當前語音機率
            
        Returns:
            平滑後的機率
        """
        # 添加到歷史記錄
        self.probability_history.append(probability)
        
        # 限制歷史記錄大小
        if len(self.probability_history) > self.smoothing_window:
            self.probability_history.pop(0)
        
        # 如果歷史記錄不足，直接返回
        if len(self.probability_history) < self.smoothing_window:
            return probability
        
        # 計算加權平均（最近的權重較高）
        weights = np.linspace(0.5, 1.0, self.smoothing_window)
        weights = weights / weights.sum()
        
        smoothed_prob = np.average(self.probability_history, weights=weights)
        
        return float(smoothed_prob)
    
    def _get_adaptive_threshold(self) -> float:
        """
        計算自適應閾值
        基於最近的語音機率分布動態調整閾值
        
        Returns:
            自適應閾值
        """
        # 如果歷史記錄不足，使用預設閾值
        if len(self.threshold_history) < self.threshold_window_size:
            return self.threshold
        
        # 計算最近窗口內的統計資訊
        recent_probs = self.threshold_history[-self.threshold_window_size:]
        mean_prob = np.mean(recent_probs)
        std_prob = np.std(recent_probs)
        
        # 基於統計資訊計算自適應閾值
        # 使用均值加上標準差的倍數作為閾值
        adaptive_threshold = mean_prob + 1.5 * std_prob
        
        # 限制閾值範圍
        adaptive_threshold = np.clip(adaptive_threshold, 0.3, 0.8)
        
        return float(adaptive_threshold)
    
    def _update_threshold_history(self, probability: float):
        """
        更新閾值歷史記錄
        
        Args:
            probability: 語音機率
        """
        self.threshold_history.append(probability)
        
        # 限制歷史記錄大小
        if len(self.threshold_history) > self.threshold_window_size * 2:
            self.threshold_history = self.threshold_history[-self.threshold_window_size:]
    
    
    async def process_from_queue(self, session_id: str):
        """
        從 AudioQueueManager 處理音訊（串流模式）
        
        Args:
            session_id: Session ID
        """
        # 設定當前 session_id
        self.current_session_id = session_id
        
        if not self.audio_queue_manager:
            logger.warning("VADOperator: No AudioQueueManager configured")
            return
        
        logger.info(f"VADOperator: Starting queue processing for session {session_id}")
        
        # 確保佇列存在
        if session_id not in self.audio_queue_manager.queues:
            await self.audio_queue_manager.create_queue(session_id)
        
        try:
            while self.enabled:
                try:
                    # 從佇列拉取音訊（VAD 需要固定大小的塊）
                    audio_data = await self.audio_queue_manager.pull(session_id, timeout=0.1)
                    
                    if audio_data:
                        # 創建元數據
                        metadata = AudioMetadata(
                            sample_rate=self.required_format.sample_rate,
                            channels=self.required_format.channels,
                            format=self.required_format.format
                        )
                        
                        # 處理音訊並執行 VAD
                        result = await self.process(audio_data, metadata=metadata)
                        
                        # 如果 Store 存在，dispatch VAD 結果
                        if self.store and self.in_speech:
                            from src.store.sessions.sessions_actions import speech_detected
                            self.store.dispatch(speech_detected(
                                session_id=session_id,
                                confidence=self.last_speech_prob,
                                timestamp=time.time()
                            ))
                        elif self.store and not self.in_speech and self.silence_duration > self.min_silence_duration:
                            from src.store.sessions.sessions_actions import silence_detected
                            self.store.dispatch(silence_detected(
                                session_id=session_id,
                                duration=self.silence_duration,
                                timestamp=time.time()
                            ))
                    else:
                        # 沒有音訊時短暫等待
                        await asyncio.sleep(0.01)
                        
                except asyncio.TimeoutError:
                    # 超時是正常的，繼續等待
                    continue
                except Exception as e:
                    logger.error(f"VADOperator queue processing error: {e}")
                    break
                    
        finally:
            logger.info(f"VADOperator: Stopped queue processing for session {session_id}")