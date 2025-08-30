"""Whisper 模型載入器 - 共享模型管理
負責：
1. 預載 Whisper 模型
2. 提供共享模型實例 
3. 背景載入和狀態管理
4. 支援多種 Whisper 實現

設計原則：
- 單例模式：確保全域只有一個載入器
- 延遲載入：按需創建模型
- 背景載入：不阻塞主執行緒
- 狀態管理：追蹤載入進度和錯誤
"""

import threading
import time
from typing import Dict, Optional, Tuple, Any, Union
from concurrent.futures import ThreadPoolExecutor, Future

from src.utils.logger import logger
from src.interface.exceptions import ServiceInitializationError


class ModelLoader:
    """Whisper 模型載入器（單例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 已載入的模型
            self._loaded_models: Dict[str, Any] = {}
            
            # 載入狀態：loading, ready, error
            self._loading_status: Dict[str, str] = {}
            
            # 載入鎖定（防止重複載入）
            self._loading_locks: Dict[str, threading.Lock] = {}
            
            # 背景載入任務
            self._loading_futures: Dict[str, Future] = {}
            
            # 執行緒池
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ModelLoader")
            
            logger.debug("ModelLoader 初始化完成")
    
    def _get_model_key(self, model_type: str, model_name: str, device: str, compute_type: str) -> str:
        """生成模型的唯一鍵值"""
        return f"{model_type}:{model_name}:{device}:{compute_type}"
    
    def get_status(self) -> Dict[str, Any]:
        """取得載入狀態"""
        return {
            'loaded_models': list(self._loaded_models.keys()),
            'loading_status': self._loading_status.copy(),
            'loading_futures_count': len(self._loading_futures)
        }
    
    def preload_model_async(self, model_type: str, model_name: str, device: str, compute_type: str) -> Future:
        """背景預載模型（非阻塞）
        
        Args:
            model_type: 模型類型 ("faster-whisper", "whisper")
            model_name: 模型名稱 (e.g., "base", "small", "turbo")
            device: 設備 ("cpu", "cuda")
            compute_type: 計算類型 ("int8", "float16", "float32")
            
        Returns:
            Future 物件，可用於檢查載入狀態
        """
        model_key = self._get_model_key(model_type, model_name, device, compute_type)
        
        # 如果已經載入或正在載入，返回現有的 Future
        if model_key in self._loaded_models:
            logger.debug(f"模型已載入: {model_key}")
            # 創建一個已完成的 Future
            future = Future()
            future.set_result(self._loaded_models[model_key])
            return future
        
        if model_key in self._loading_futures:
            logger.debug(f"模型正在載入中: {model_key}")
            return self._loading_futures[model_key]
        
        # 創建載入鎖
        if model_key not in self._loading_locks:
            self._loading_locks[model_key] = threading.Lock()
        
        # 設定載入狀態
        self._loading_status[model_key] = "loading"
        
        # 提交背景載入任務
        future = self._executor.submit(self._load_model_sync, model_type, model_name, device, compute_type)
        self._loading_futures[model_key] = future
        
        logger.info(f"🚀 背景載入任務已提交: {model_key}")
        
        return future
    
    def _load_model_sync(self, model_type: str, model_name: str, device: str, compute_type: str) -> Any:
        """同步載入模型（在背景執行緒中執行）"""
        model_key = self._get_model_key(model_type, model_name, device, compute_type)
        
        try:
            with self._loading_locks[model_key]:
                # 雙重檢查
                if model_key in self._loaded_models:
                    return self._loaded_models[model_key]
                
                logger.info(f"🔄 開始載入模型: {model_key}")
                start_time = time.time()
                
                if model_type == "faster-whisper":
                    model = self._load_faster_whisper_model(model_name, device, compute_type)
                elif model_type == "whisper":
                    model = self._load_whisper_model(model_name, device)
                else:
                    raise ValueError(f"不支援的模型類型: {model_type}")
                
                load_time = time.time() - start_time
                
                # 儲存模型
                self._loaded_models[model_key] = model
                self._loading_status[model_key] = "ready"
                
                # 清理載入任務
                if model_key in self._loading_futures:
                    del self._loading_futures[model_key]
                
                logger.success(f"✅ 模型載入完成: {model_key} (耗時: {load_time:.2f}s)")
                return model
                
        except Exception as e:
            self._loading_status[model_key] = "error"
            if model_key in self._loading_futures:
                del self._loading_futures[model_key]
            
            logger.error(f"❌ 模型載入失敗: {model_key}, 錯誤: {e}")
            raise ServiceInitializationError(f"無法載入模型 {model_key}: {e}") from e
    
    def _load_faster_whisper_model(self, model_name: str, device: str, compute_type: str) -> Any:
        """載入 Faster-Whisper 模型"""
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ServiceInitializationError(
                "faster-whisper 未安裝。請執行: pip install faster-whisper"
            ) from e
        
        logger.info(f"載入 FasterWhisper 模型: {model_name} on {device} with {compute_type}")
        
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=4,
            num_workers=1
        )
        
        return model
    
    def _load_whisper_model(self, model_name: str, device: str) -> Any:
        """載入原始 Whisper 模型"""
        try:
            import whisper
        except ImportError as e:
            raise ServiceInitializationError(
                "whisper 未安裝。請執行: pip install openai-whisper"
            ) from e
        
        logger.info(f"載入 Whisper 模型: {model_name} on {device}")
        
        model = whisper.load_model(model_name, device=device)
        return model
    
    def get_model(self, model_type: str, model_name: str, device: str, compute_type: str, wait: bool = True) -> Tuple[Optional[Any], str]:
        """取得模型實例
        
        Args:
            model_type: 模型類型
            model_name: 模型名稱
            device: 設備
            compute_type: 計算類型
            wait: 是否等待載入完成
            
        Returns:
            (模型實例, 狀態) - 狀態可能是 "ready", "loading", "error"
        """
        model_key = self._get_model_key(model_type, model_name, device, compute_type)
        
        # 如果已載入，直接返回
        if model_key in self._loaded_models:
            return self._loaded_models[model_key], "ready"
        
        # 如果不等待且正在載入，返回 loading 狀態
        if not wait and model_key in self._loading_status:
            status = self._loading_status[model_key]
            return None, status
        
        # 如果需要等待且有正在載入的任務
        if model_key in self._loading_futures:
            future = self._loading_futures[model_key]
            if wait:
                try:
                    logger.info(f"⏳ 等待模型載入完成: {model_key}")
                    model = future.result(timeout=60)  # 等待最多60秒
                    return model, "ready"
                except Exception as e:
                    logger.error(f"等待模型載入失敗: {e}")
                    return None, "error"
            else:
                return None, "loading"
        
        # 如果沒有任何載入記錄，開始同步載入（阻塞）
        if wait:
            try:
                model = self._load_model_sync(model_type, model_name, device, compute_type)
                return model, "ready"
            except Exception:
                return None, "error"
        else:
            # 開始背景載入
            self.preload_model_async(model_type, model_name, device, compute_type)
            return None, "loading"
    
    def is_model_ready(self, model_type: str, model_name: str, device: str, compute_type: str) -> bool:
        """檢查模型是否已載入完成"""
        model_key = self._get_model_key(model_type, model_name, device, compute_type)
        return model_key in self._loaded_models
    
    def wait_for_model(self, model_type: str, model_name: str, device: str, compute_type: str, timeout: float = 60.0) -> bool:
        """等待模型載入完成
        
        Args:
            model_type: 模型類型
            model_name: 模型名稱  
            device: 設備
            compute_type: 計算類型
            timeout: 超時時間（秒）
            
        Returns:
            True 如果載入成功，False 如果超時或失敗
        """
        model_key = self._get_model_key(model_type, model_name, device, compute_type)
        
        # 如果已載入，立即返回
        if model_key in self._loaded_models:
            return True
        
        # 如果有載入任務，等待完成
        if model_key in self._loading_futures:
            future = self._loading_futures[model_key]
            try:
                future.result(timeout=timeout)
                return True
            except Exception as e:
                logger.error(f"等待模型載入超時或失敗: {e}")
                return False
        
        # 沒有載入任務，返回 False
        return False
    
    def shutdown(self):
        """關閉模型載入器"""
        logger.info("正在關閉 ModelLoader...")
        self._executor.shutdown(wait=True)
        logger.info("ModelLoader 已關閉")


# 模組級別的單例
model_loader = ModelLoader()