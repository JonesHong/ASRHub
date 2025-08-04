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

from src.pipeline.operators.base import OperatorBase
from src.core.exceptions import PipelineError
from src.utils.logger import logger
from src.models.audio_format import AudioMetadata, AudioFormat
from .model_downloader import ensure_vad_model


class SileroVADOperator(OperatorBase):
    """使用 Silero VAD 模型進行語音活動檢測"""
    
    def __init__(self):
        super().__init__()
        
        # 從 ConfigManager 獲取配置
        from src.config.manager import ConfigManager
        self.config_manager = ConfigManager()
        
        self.model = None
        self.h = None  # 隱藏狀態 h
        self.c = None  # 隱藏狀態 c
        
        # 獲取格式要求 - 單一真相來源
        self.required_format = self.get_required_audio_format()
        self.window_size_samples = 512  # Silero VAD 使用 512 樣本窗口
        
        # 嘗試從配置中獲取設定，使用 yaml2py 正確方式
        try:
            # 直接存取屬性，讓 yaml2py 處理預設值
            vad_config = self.config_manager.pipeline.operators.vad
            
            self.threshold = vad_config.threshold
            self.min_silence_duration = vad_config.min_silence_duration
            self.min_speech_duration = vad_config.min_speech_duration
            self.model_path = vad_config.model_path
            
            # 進階功能
            self.adaptive_threshold = vad_config.adaptive_threshold
            self.threshold_window_size = vad_config.threshold_window_size
            self.smoothing_window = vad_config.smoothing_window
            
        except AttributeError:
            # 如果配置不存在，使用硬編碼預設值
            self.threshold = 0.5
            self.min_silence_duration = 0.5
            self.min_speech_duration = 0.25
            self.model_path = 'models/silero_vad.onnx'
            
            # 進階功能
            self.adaptive_threshold = False
            self.threshold_window_size = 50
            self.smoothing_window = 3
        
        # 狀態追蹤
        self.in_speech = False
        self.speech_start_time = None
        self.speech_end_time = None
        self.silence_start_time = None
        self.speech_duration = 0
        self.silence_duration = 0
        
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
            sample_rate=16000,  # Silero VAD 固定需要 16kHz
            channels=1,         # 只支援單聲道
            format=AudioFormat.INT16  # 接受 int16 輸入
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
                model_name = 'silero_vad_v4'  # 預設值
                try:
                    if hasattr(config_manager.pipeline.operators.vad, 'model_name'):
                        model_name = config_manager.pipeline.operators.vad.model_name
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
            providers = ['CPUExecutionProvider']  # 預設使用 CPU
            
            # 如果有 GPU 可用，優先使用
            use_gpu = False
            try:
                if hasattr(self.config_manager.pipeline.operators.vad, 'use_gpu'):
                    use_gpu = self.config_manager.pipeline.operators.vad.use_gpu
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
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊並返回 VAD 結果
        
        Args:
            audio_data: 輸入音訊資料
            **kwargs: 額外參數
            
        Returns:
            audio_data: 透傳音訊，附加 VAD 資訊在 kwargs 中
        """
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
            
            while len(self.audio_buffer) >= window_size_bytes:
                # 提取一個窗口的音訊
                window_bytes = self.audio_buffer[:window_size_bytes]
                self.audio_buffer = self.audio_buffer[window_size_bytes:]
                
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
                await self._update_speech_state(is_speech, current_time, speech_prob)
                
                # 更新閾值歷史（用於自適應閾值）
                if self.adaptive_threshold:
                    self._update_threshold_history(speech_prob)
                
                vad_results.append({
                    'speech_detected': is_speech,
                    'speech_probability': float(speech_prob),
                    'timestamp': current_time
                })
                
                self.total_frames_processed += 1
            
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
    
    async def _update_speech_state(self, is_speech: bool, timestamp: float, speech_prob: float):
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
                
                logger.debug(f"語音開始 (機率: {speech_prob:.3f})")
                
                # 觸發語音開始回調
                if self.speech_start_callback:
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
                # 可能是語音結束
                if self.silence_start_time is None:
                    self.silence_start_time = timestamp
                
                # 計算靜音持續時間
                silence_duration = timestamp - self.silence_start_time
                
                # 檢查是否達到最小靜音時長
                if silence_duration >= self.min_silence_duration:
                    # 語音結束
                    self.speech_end_time = self.silence_start_time
                    self.in_speech = False
                    self.speech_duration = 0
                    self.silence_start_time = None
                    
                    logger.debug(f"語音結束 (靜音時長: {silence_duration:.3f}s)")
                    
                    # 觸發語音結束回調
                    if self.speech_end_callback:
                        await self.speech_end_callback({
                            'timestamp': timestamp,
                            'speech_duration': self.speech_end_time - self.speech_start_time,
                            'silence_duration': silence_duration
                        })
            else:
                # 持續靜音
                self.silence_duration += frame_duration
    
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