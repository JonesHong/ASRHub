"""
OpenWakeWord Operator 實作
支援 openWakeWord 模型載入、即時音訊處理和喚醒詞偵測
"""

import os
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict, deque
from functools import partial
import numpy as np
import scipy.signal
from datetime import datetime
from huggingface_hub import hf_hub_download, HfFolder

from src.pipeline.operators.base import OperatorBase
from src.core.exceptions import PipelineError
from src.config.manager import ConfigManager


class OpenWakeWordOperator(OperatorBase):
    """
    OpenWakeWord 喚醒詞偵測 Operator
    
    特點：
    - 支援 ONNX 模型推論
    - 自動重採樣到 16kHz
    - 滑動視窗機制（1280 樣本/幀）
    - 60 幀評分佇列
    - 可配置的偵測閾值
    - 去抖動機制防止重複觸發
    """
    
    def __init__(self):
        """
        初始化 OpenWakeWord Operator
        """
        # 從 ConfigManager 讀取配置
        config_manager = ConfigManager()
        config = {
            "enabled": True,
            "model_path": None,
            "threshold": 0.5,
            "language": "zh-TW"
        }
        
        # 設定預設值
        self.hf_repo_id = "JTBTechnology/kmu_wakeword"
        self.hf_filename = "hi_kmu_0721.onnx"
        self.hf_token = None
        
        # 從配置中獲取 wakeword 相關設定
        if hasattr(config_manager, 'wake_word_detection') and config_manager.wake_word_detection.enabled:
            # 找到 openWakeWord 配置
            for model_config in config_manager.wake_word_detection.models:
                if model_config.type == "openWakeWord":
                    config = {
                        "enabled": model_config.enabled,
                        "model_path": model_config.model_path,
                        "threshold": model_config.threshold,
                        "language": model_config.language
                    }
                    # 獲取其他配置
                    self.hf_repo_id = getattr(model_config, 'hf_repo_id', self.hf_repo_id)
                    self.hf_filename = getattr(model_config, 'hf_filename', self.hf_filename)
                    self.hf_token = getattr(model_config, 'hf_token', self.hf_token)
                    break
        
        super().__init__(config)
        
        # 模型相關
        self.model = None
        self.model_path = self.config.get("model_path")
        # hf_repo_id, hf_filename, hf_token 已在上面設定
        
        # 音訊處理參數
        self.chunk_size = 1280  # openWakeWord 需要的固定大小
        self.target_sample_rate = 16000  # 模型需要 16kHz
        
        # 狀態管理
        self.state = defaultdict(partial(deque, maxlen=60))  # 60 幀的評分佇列
        
        # 偵測參數
        self.threshold = self.config.get("threshold", 0.5)
        self.detection_cooldown = self.config.get("detection_cooldown", 0.8)  # 冷卻期（秒）
        self.last_detection_time = 0
        
        # 音訊緩衝區（用於重採樣）
        self.audio_buffer = np.array([], dtype=np.float32)
        
        # 偵測回呼
        self.detection_callback = None
    
    async def _initialize(self):
        """初始化 Operator 資源"""
        self.logger.info("初始化 OpenWakeWord Operator...")
        
        # 載入模型
        await self._load_model()
        
        # 清空狀態
        self.state.clear()
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_detection_time = 0
        
        self.logger.info("✓ OpenWakeWord Operator 初始化完成")
    
    async def _cleanup(self):
        """清理 Operator 資源"""
        self.logger.info("清理 OpenWakeWord Operator...")
        
        # 清理模型
        if self.model:
            del self.model
            self.model = None
        
        # 清理狀態
        self.state.clear()
        self.audio_buffer = np.array([], dtype=np.float32)
        
        self.logger.info("✓ OpenWakeWord Operator 清理完成")
    
    async def _load_model(self):
        """載入 openWakeWord 模型"""
        try:
            # 動態導入 openwakeword（避免在沒有安裝時報錯）
            from openwakeword.model import Model
            from openwakeword.utils import download_models
        except ImportError:
            raise PipelineError("請安裝 openwakeword: pip install openwakeword")
        
        # 下載預設模型
        download_models()
        
        # 決定模型路徑
        model_path = self.model_path
        
        if not model_path:
            # 嘗試從 HuggingFace 下載
            # 優先使用配置中的 token，否則從環境變數或 HfFolder 獲取
            hf_token = self.hf_token or os.environ.get("HF_TOKEN") or HfFolder.get_token()
            
            if hf_token and self.hf_repo_id and self.hf_filename:
                self.logger.info(f"從 HuggingFace 下載模型: {self.hf_repo_id}/{self.hf_filename}")
                try:
                    model_path = hf_hub_download(
                        repo_id=self.hf_repo_id,
                        filename=self.hf_filename,
                        token=hf_token,
                        repo_type="model"
                    )
                    self.logger.info(f"✓ 模型下載成功: {model_path}")
                except Exception as e:
                    self.logger.error(f"模型下載失敗: {e}")
                    raise PipelineError(f"無法下載模型: {e}")
            else:
                raise PipelineError("請設定模型路徑或提供 HF_TOKEN")
        
        # 載入模型
        try:
            self.model = Model(
                wakeword_models=[model_path],
                inference_framework="onnx"
            )
            self.logger.info(f"✓ 模型載入成功: {model_path}")
        except Exception as e:
            self.logger.error(f"模型載入失敗: {e}")
            raise PipelineError(f"無法載入模型: {e}")
    
    async def process(self, audio_data: bytes, **kwargs) -> Optional[bytes]:
        """
        處理音訊資料，偵測喚醒詞
        
        Args:
            audio_data: 輸入音訊資料（bytes）
            **kwargs: 額外參數
                - sample_rate: 輸入音訊的採樣率
                - session_id: 會話 ID
            
        Returns:
            原始音訊資料（不修改）
        """
        if not self.enabled or not self.model:
            return audio_data
        
        if not self.validate_audio_params(audio_data):
            return audio_data
        
        # 獲取採樣率
        input_sample_rate = kwargs.get("sample_rate", self.sample_rate)
        
        # 轉換為 numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        
        # 添加到緩衝區
        self.audio_buffer = np.concatenate([self.audio_buffer, audio_np])
        
        # 重採樣到 16kHz（如果需要）
        if input_sample_rate != self.target_sample_rate:
            # 計算需要的樣本數
            target_length = int(len(self.audio_buffer) * self.target_sample_rate / input_sample_rate)
            
            # 如果緩衝區太小，等待更多資料
            if target_length < self.chunk_size:
                return audio_data
            
            # 重採樣
            resampled = scipy.signal.resample(self.audio_buffer, target_length)
            self.audio_buffer = resampled
        
        # 處理完整的 chunks
        detections = []
        while len(self.audio_buffer) >= self.chunk_size:
            # 取出一個 chunk
            chunk = self.audio_buffer[:self.chunk_size]
            self.audio_buffer = self.audio_buffer[self.chunk_size:]
            
            # 推論
            try:
                predictions = self.model.predict(chunk)
                
                # 更新狀態並檢查偵測
                for model_name, score in predictions.items():
                    # 更新評分佇列
                    if len(self.state[model_name]) == 0:
                        # 初始化為零
                        self.state[model_name].extend(np.zeros(60))
                    
                    self.state[model_name].append(score)
                    
                    # 檢查是否超過閾值
                    if score > self.threshold:
                        current_time = asyncio.get_event_loop().time()
                        
                        # 檢查冷卻期
                        if current_time - self.last_detection_time > self.detection_cooldown:
                            self.last_detection_time = current_time
                            
                            detection = {
                                "model": model_name,
                                "score": float(score),
                                "timestamp": datetime.now().isoformat(),
                                "session_id": kwargs.get("session_id")
                            }
                            detections.append(detection)
                            
                            self.logger.info(
                                f"🎯 偵測到喚醒詞！模型: {model_name}, "
                                f"分數: {score:.3f}"
                            )
                            
                            # 觸發回呼
                            if self.detection_callback:
                                await self._trigger_callback(detection)
            
            except Exception as e:
                self.logger.error(f"推論錯誤: {e}")
        
        # 將偵測結果存入 kwargs（供後續 operator 使用）
        if detections:
            kwargs["wake_word_detections"] = detections
        
        # 返回原始音訊（不修改）
        return audio_data
    
    async def _trigger_callback(self, detection: Dict[str, Any]):
        """觸發偵測回呼"""
        try:
            if asyncio.iscoroutinefunction(self.detection_callback):
                await self.detection_callback(detection)
            else:
                self.detection_callback(detection)
        except Exception as e:
            self.logger.error(f"回呼執行錯誤: {e}")
    
    def set_detection_callback(self, callback):
        """
        設定喚醒詞偵測回呼函數
        
        Args:
            callback: 偵測到喚醒詞時呼叫的函數
        """
        self.detection_callback = callback
    
    def get_scores(self, model_name: Optional[str] = None) -> Dict[str, List[float]]:
        """
        獲取評分歷史
        
        Args:
            model_name: 模型名稱，如果不指定則返回所有模型
            
        Returns:
            評分歷史字典
        """
        if model_name:
            return {model_name: list(self.state.get(model_name, []))}
        else:
            return {name: list(scores) for name, scores in self.state.items()}
    
    def get_latest_score(self, model_name: Optional[str] = None) -> Optional[float]:
        """
        獲取最新評分
        
        Args:
            model_name: 模型名稱
            
        Returns:
            最新評分，如果沒有則返回 None
        """
        if not model_name and self.state:
            # 使用第一個模型
            model_name = list(self.state.keys())[0]
        
        if model_name and model_name in self.state and self.state[model_name]:
            return self.state[model_name][-1]
        
        return None
    
    async def flush(self):
        """清空內部緩衝區"""
        self.audio_buffer = np.array([], dtype=np.float32)
        for model_name in self.state:
            self.state[model_name].clear()
            self.state[model_name].extend(np.zeros(60))
        self.logger.debug("已清空音訊緩衝區和評分佇列")
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        super().update_config(config)
        
        # 更新特定參數
        if "threshold" in config:
            self.threshold = config["threshold"]
            self.logger.info(f"更新偵測閾值: {self.threshold}")
        
        if "detection_cooldown" in config:
            self.detection_cooldown = config["detection_cooldown"]
            self.logger.info(f"更新冷卻期: {self.detection_cooldown}秒")
    
    def get_info(self) -> Dict[str, Any]:
        """獲取 Operator 資訊"""
        info = super().get_info()
        info.update({
            "model_loaded": self.model is not None,
            "model_path": self.model_path,
            "threshold": self.threshold,
            "detection_cooldown": self.detection_cooldown,
            "buffer_size": len(self.audio_buffer),
            "models": list(self.state.keys()) if self.state else []
        })
        return info