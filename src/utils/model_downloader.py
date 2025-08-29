"""通用模型下載器

提供統一的模型下載和管理功能，支援多種模型來源。
"""

import os
import hashlib
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from urllib.parse import urlparse
import requests
from tqdm import tqdm
from src.utils.logger import logger


class ModelDownloader:
    """通用模型下載器
    
    支援：
    - HTTP/HTTPS 下載
    - Hugging Face Hub 整合
    - 進度顯示
    - 檔案校驗
    - 快取管理
    """
    
    DEFAULT_CACHE_DIR = Path.home() / ".cache" / "asrhub" / "models"
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        chunk_size: int = 8192,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """初始化模型下載器
        
        參數：
            cache_dir: 快取目錄
            chunk_size: 下載區塊大小
            timeout: 請求超時時間
            max_retries: 最大重試次數
        """
        self.cache_dir = Path(cache_dir) if cache_dir else self.DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 模型註冊表
        self._model_registry: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"模型下載器初始化，快取目錄: {self.cache_dir}")
    
    def register_model(
        self,
        model_name: str,
        url: str,
        checksum: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """註冊模型資訊
        
        參數：
            model_name: 模型名稱
            url: 下載 URL
            checksum: 檔案校驗碼
            metadata: 額外的元資料
        """
        self._model_registry[model_name] = {
            "url": url,
            "checksum": checksum,
            "metadata": metadata or {}
        }
        logger.debug(f"註冊模型: {model_name}")
    
    def download_model(
        self,
        model_name: str,
        force_download: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Path:
        """下載模型
        
        參數：
            model_name: 模型名稱或 URL
            force_download: 強制重新下載
            progress_callback: 進度回呼函數
            
        回傳：
            模型檔案路徑
        """
        # 檢查是否為註冊的模型
        if model_name in self._model_registry:
            model_info = self._model_registry[model_name]
            url = model_info["url"]
            checksum = model_info.get("checksum")
        else:
            # 直接作為 URL 處理
            url = model_name
            checksum = None
            model_name = self._get_filename_from_url(url)
        
        # 確定本地檔案路徑
        local_path = self.cache_dir / model_name
        
        # 檢查是否已存在且不需要強制下載
        if local_path.exists() and not force_download:
            if checksum and not self._verify_checksum(local_path, checksum):
                logger.warning(f"模型檔案校驗失敗，重新下載: {model_name}")
            else:
                logger.info(f"使用快取的模型: {local_path}")
                return local_path
        
        # 執行下載
        logger.info(f"開始下載模型: {model_name}")
        
        # 下載到臨時檔案
        temp_file = tempfile.NamedTemporaryFile(delete=False, dir=self.cache_dir)
        try:
            self._download_file(url, temp_file.name, progress_callback)
            
            # 校驗檔案
            if checksum and not self._verify_checksum(temp_file.name, checksum):
                raise ValueError(f"下載的檔案校驗失敗: {model_name}")
            
            # 移動到最終位置
            shutil.move(temp_file.name, local_path)
            logger.info(f"模型下載完成: {local_path}")
            
            return local_path
            
        except Exception as e:
            # 清理臨時檔案
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise RuntimeError(f"模型下載失敗: {e}")
    
    def download_from_huggingface(
        self,
        repo_id: str,
        filename: str,
        revision: str = "main",
        force_download: bool = False
    ) -> Path:
        """從 Hugging Face Hub 下載模型
        
        參數：
            repo_id: 儲存庫 ID（例如：'openai/whisper-base'）
            filename: 檔案名稱
            revision: 分支或標籤
            force_download: 強制重新下載
            
        回傳：
            模型檔案路徑
        """
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            raise ImportError("請安裝 huggingface-hub: pip install huggingface-hub")
        
        # 建立子目錄
        model_dir = self.cache_dir / repo_id.replace("/", "_")
        model_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                cache_dir=str(model_dir),
                force_download=force_download,
                resume_download=True
            )
            logger.info(f"從 Hugging Face 下載完成: {local_path}")
            return Path(local_path)
            
        except Exception as e:
            raise RuntimeError(f"從 Hugging Face 下載失敗: {e}")
    
    def list_cached_models(self) -> List[Dict[str, Any]]:
        """列出快取的模型
        
        回傳：
            模型資訊列表
        """
        models = []
        
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.cache_dir)
                models.append({
                    "name": str(rel_path),
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                })
        
        return models
    
    def clear_cache(
        self,
        model_name: Optional[str] = None
    ) -> int:
        """清理快取
        
        參數：
            model_name: 指定要清理的模型（None 表示清理全部）
            
        回傳：
            清理的檔案數量
        """
        count = 0
        
        if model_name:
            # 清理特定模型
            model_path = self.cache_dir / model_name
            if model_path.exists():
                if model_path.is_file():
                    model_path.unlink()
                    count = 1
                else:
                    shutil.rmtree(model_path)
                    count = sum(1 for _ in model_path.rglob("*") if _.is_file())
                logger.info(f"清理模型快取: {model_name}")
        else:
            # 清理所有快取
            for file_path in self.cache_dir.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    count += 1
            logger.info(f"清理了 {count} 個快取檔案")
        
        return count
    
    def get_cache_size(self) -> int:
        """取得快取大小
        
        回傳：
            快取總大小（位元組）
        """
        total_size = 0
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size
    
    def _download_file(
        self,
        url: str,
        dest_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """下載檔案
        
        參數：
            url: 下載 URL
            dest_path: 目標路徑
            progress_callback: 進度回呼
        """
        headers = {"User-Agent": "ASRHub/1.0"}
        
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                # 取得檔案大小
                total_size = int(response.headers.get('content-length', 0))
                
                # 使用 tqdm 顯示進度
                with open(dest_path, 'wb') as f:
                    with tqdm(
                        total=total_size,
                        unit='B',
                        unit_scale=True,
                        desc=os.path.basename(dest_path)
                    ) as pbar:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                pbar.update(len(chunk))
                                
                                # 呼叫進度回呼
                                if progress_callback:
                                    progress_callback(downloaded, total_size)
                
                return
                
            except Exception as e:
                logger.warning(f"下載失敗 (嘗試 {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # 指數退避
    
    def _verify_checksum(
        self,
        file_path: str,
        expected_checksum: str
    ) -> bool:
        """驗證檔案校驗碼
        
        參數：
            file_path: 檔案路徑
            expected_checksum: 預期的校驗碼
            
        回傳：
            是否匹配
        """
        # 判斷校驗碼類型
        if len(expected_checksum) == 32:
            algo = hashlib.md5()
        elif len(expected_checksum) == 40:
            algo = hashlib.sha1()
        elif len(expected_checksum) == 64:
            algo = hashlib.sha256()
        else:
            logger.warning(f"無法識別校驗碼類型: {expected_checksum}")
            return True  # 無法驗證時通過
        
        # 計算檔案校驗碼
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                algo.update(chunk)
        
        actual_checksum = algo.hexdigest()
        return actual_checksum == expected_checksum
    
    def _get_filename_from_url(self, url: str) -> str:
        """從 URL 提取檔案名稱
        
        參數：
            url: 檔案 URL
            
        回傳：
            檔案名稱
        """
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        
        if not filename:
            # 使用 URL 的 hash 作為檔案名稱
            filename = hashlib.md5(url.encode()).hexdigest()
        
        return filename


# 全域模型下載器實例
model_downloader = ModelDownloader()