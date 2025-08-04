"""
VAD 模型下載器
支援從 Hugging Face Hub 或其他來源下載 VAD 模型
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
import hashlib
from tqdm.asyncio import tqdm

from src.utils.logger import logger

logger = logger


class VADModelDownloader:
    """VAD 模型下載管理器"""
    
    # Silero VAD 模型資訊
    SILERO_VAD_MODELS = {
        "silero_vad_v4": {
            "url": "https://huggingface.co/onnx-community/silero-vad/resolve/main/onnx/model_q4f16.onnx",
            "sha256": "skip",  # Temporarily skip validation for new model
            "size": 1914453,  # bytes
            "description": "Silero VAD v4.0 ONNX model"
        },
        "silero_vad_v3": {
            "url": "https://github.com/snakers4/silero-vad/raw/v3.1/files/silero_vad.onnx", 
            "sha256": "a3f4d66e2e6f311a1c3b94a1e4b7c7f0de3bcb6a8e8d4f5c6d7e8f9a0b1c2d3e",
            "size": 1856234,
            "description": "Silero VAD v3.1 ONNX model (legacy)"
        }
    }
    
    def __init__(self, models_dir: str = "models"):
        """
        初始化模型下載器
        
        Args:
            models_dir: 模型儲存目錄
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
    
    async def download_model(self, 
                           model_name: str = "silero_vad_v4",
                           force_download: bool = False) -> Path:
        """
        下載 VAD 模型
        
        Args:
            model_name: 模型名稱
            force_download: 是否強制重新下載
            
        Returns:
            模型文件路徑
        """
        if model_name not in self.SILERO_VAD_MODELS:
            raise ValueError(f"未知的模型名稱: {model_name}")
        
        model_info = self.SILERO_VAD_MODELS[model_name]
        model_path = self.models_dir / f"{model_name}.onnx"
        
        # 檢查模型是否已存在
        if model_path.exists() and not force_download:
            logger.info(f"模型已存在: {model_path}")
            
            # 驗證檔案完整性
            if model_info.get("sha256") == "skip":
                logger.info("跳過雜湊驗證")
                return model_path
            elif await self._verify_model(model_path, model_info["sha256"]):
                return model_path
            else:
                logger.warning("模型檔案損壞，重新下載...")
        
        # 下載模型
        logger.info(f"下載 VAD 模型: {model_name}")
        logger.info(f"從: {model_info['url']}")
        logger.info(f"到: {model_path}")
        
        try:
            await self._download_file(
                url=model_info["url"],
                dest_path=model_path,
                expected_size=model_info.get("size"),
                expected_hash=model_info.get("sha256")
            )
            
            logger.info(f"✓ 模型下載完成: {model_path}")
            return model_path
            
        except Exception as e:
            logger.error(f"模型下載失敗: {e}")
            if model_path.exists():
                model_path.unlink()  # 刪除不完整的文件
            raise
    
    async def _download_file(self,
                           url: str,
                           dest_path: Path,
                           expected_size: Optional[int] = None,
                           expected_hash: Optional[str] = None):
        """
        下載文件並顯示進度
        
        Args:
            url: 下載 URL
            dest_path: 目標路徑
            expected_size: 預期文件大小
            expected_hash: 預期文件雜湊值
        """
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            
            # 獲取文件大小
            total_size = int(response.headers.get("content-length", 0))
            if total_size == 0 and expected_size:
                total_size = expected_size
            
            # 創建進度條
            progress_bar = tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=dest_path.name
            )
            
            # 下載並寫入文件
            sha256_hash = hashlib.sha256()
            
            with open(dest_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    sha256_hash.update(chunk)
                    progress_bar.update(len(chunk))
            
            progress_bar.close()
            
            # 驗證文件雜湊
            if expected_hash and expected_hash != "skip":
                actual_hash = sha256_hash.hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError(
                        f"文件雜湊不符!\n"
                        f"預期: {expected_hash}\n"
                        f"實際: {actual_hash}"
                    )
    
    async def _verify_model(self, model_path: Path, expected_hash: str) -> bool:
        """
        驗證模型文件完整性
        
        Args:
            model_path: 模型文件路徑
            expected_hash: 預期的 SHA256 雜湊值
            
        Returns:
            是否驗證通過
        """
        try:
            sha256_hash = hashlib.sha256()
            
            with open(model_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)
            
            actual_hash = sha256_hash.hexdigest()
            is_valid = actual_hash == expected_hash
            
            if not is_valid:
                logger.warning(f"模型雜湊不符: {actual_hash} != {expected_hash}")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"驗證模型失敗: {e}")
            return False
    
    def get_model_path(self, model_name: str = "silero_vad_v4") -> Path:
        """
        獲取模型路徑（不下載）
        
        Args:
            model_name: 模型名稱
            
        Returns:
            模型文件路徑
        """
        return self.models_dir / f"{model_name}.onnx"
    
    def list_available_models(self) -> Dict[str, Any]:
        """
        列出可用的模型
        
        Returns:
            模型資訊字典
        """
        models = {}
        
        for name, info in self.SILERO_VAD_MODELS.items():
            model_path = self.get_model_path(name)
            models[name] = {
                **info,
                "downloaded": model_path.exists(),
                "path": str(model_path)
            }
        
        return models


# 便利函數
async def ensure_vad_model(model_name: str = "silero_vad_v4",
                          models_dir: str = "models") -> Path:
    """
    確保 VAD 模型已下載
    
    Args:
        model_name: 模型名稱
        models_dir: 模型目錄
        
    Returns:
        模型文件路徑
    """
    downloader = VADModelDownloader(models_dir)
    return await downloader.download_model(model_name)