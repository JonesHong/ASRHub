"""錄音服務實作

從 AudioQueueManager 取得音訊片段並寫入本地檔案。
支援多個 session 同時錄音，採用完全無狀態設計。
"""

import os
import wave
import threading
import schedule
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor
import struct
from src.interface.recording import IRecordingService
from src.core.audio_queue_manager import audio_queue
from src.utils.logger import logger
from src.utils.singleton import SingletonMixin
from src.config.manager import ConfigManager




class Recording(SingletonMixin, IRecordingService):
    """錄音服務實作。
    
    特性：
    - 無狀態服務，可處理多個 session
    - 從 audio queue 取得音訊並寫入檔案
    - 自動檔案命名和路徑管理
    - 背景錄音支援
    - 自動清理舊檔案
    - 使用 SingletonMixin 確保單例
    """
    
    def __init__(self):
        """初始化錄音服務。"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 從 ConfigManager 載入配置
            self._config = ConfigManager()
            self._recording_config = self._config.services.recording
            
            # 錄音狀態管理
            self._recording_sessions: Set[str] = set()
            self._recording_threads: Dict[str, threading.Thread] = {}
            self._recording_info: Dict[str, Dict[str, Any]] = {}
            self._lock = threading.Lock()
            
            # 執行緒池
            self._executor = ThreadPoolExecutor(max_workers=self._recording_config.recording_max_workers)
            
            # 預設輸出目錄
            self._default_output_dir = Path(self._recording_config.output_dir)
            self._default_output_dir.mkdir(parents=True, exist_ok=True)
            
            # 自動清理設定
            if self._recording_config.recording_auto_cleanup:
                self._setup_auto_cleanup()
            
            logger.info(f"錄音服務已初始化，輸出目錄: {self._default_output_dir}")
    
    
    def start_recording(
        self,
        session_id: str,
        sample_rate: Optional[int] = None,  # 新增：客戶端提供的採樣率
        channels: Optional[int] = None,  # 新增：客戶端提供的聲道數
        format: Optional[str] = None,  # 新增：客戶端提供的音訊格式 (int16, float32 等)
        output_dir: Optional[Path] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        start_timestamp: Optional[float] = None  # 新增：從指定時間戳開始讀取
    ) -> bool:
        """開始錄音。
        
        Args:
            session_id: Session ID
            output_dir: 輸出目錄（可選，未指定則使用預設值）
            filename: 檔案名稱（可選，未指定則自動產生）
            metadata: 額外的中繼資料
            start_timestamp: 從指定時間戳開始讀取（可選）
            
        Returns:
            是否成功開始錄音
        """
        # 註冊為音訊佇列的讀者（可能從指定時間戳開始）
        from src.core.audio_queue_manager import audio_queue
        audio_queue.register_reader(session_id, "recording", start_timestamp)
        if start_timestamp:
            logger.debug(f"Registered Recording as reader for session {session_id} from timestamp {start_timestamp:.3f}")
        else:
            logger.debug(f"Registered Recording as reader for session {session_id}")
        
        with self._lock:
            if session_id in self._recording_sessions:
                logger.warning(f"Session {session_id} 已經在錄音中")
                return False
            
            # 如果未指定則使用預設目錄
            if output_dir is None:
                output_dir = self._default_output_dir
            else:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
            
            # 如果未指定則產生檔案名稱
            if filename is None:
                # 格式: [<session_id or 'test'>]YYYYMMDD.HHmmssss-YYYYMMDD.HHmmssss.wav
                # 開始時間會在此記錄，結束時間會在停止錄音時更新
                start_time = datetime.now()
                start_str = start_time.strftime('%Y%m%d.%H%M%S%f')[:-2]  # 微秒取前4位
                # 先使用相同的時間作為結束時間占位符，之後會更新
                filename = f"[{session_id}]{start_str}-{start_str}"
            
            # 如果沒有副檔名則加上
            if not filename.endswith(f'.{self._recording_config.file_format}'):
                filename = f"{filename}.{self._recording_config.file_format}"
            
            filepath = output_dir / filename
            
            # 儲存錄音資訊（包含客戶端提供的音訊參數）
            self._recording_info[session_id] = {
                'filepath': filepath,
                'start_time': datetime.now(),
                'metadata': metadata or {},
                'chunks_written': 0,
                'bytes_written': 0,
                'wav_file': None,
                'stop_event': threading.Event(),
                'sample_rate': sample_rate,  # 儲存客戶端提供的採樣率
                'channels': channels,  # 儲存客戶端提供的聲道數
                'format': format  # 儲存客戶端提供的音訊格式
            }
            
            self._recording_sessions.add(session_id)
            
            # 啟動錄音執行緒
            thread = threading.Thread(
                target=self._recording_worker,
                args=(session_id,),
                daemon=True
            )
            thread.start()
            self._recording_threads[session_id] = thread
            
            logger.info(f"已開始為 session {session_id} 錄音，檔案: {filepath}")
            return True
    
    def stop_recording(self, session_id: str) -> Optional[Dict[str, Any]]:
        """停止錄音。
        
        Args:
            session_id: Session ID
            
        Returns:
            錄音資訊或 None（如果未在錄音中）
        """
        with self._lock:
            if session_id not in self._recording_sessions:
                logger.warning(f"Session {session_id} 未在錄音中")
                return None
            
            # 發送停止信號
            if session_id in self._recording_info:
                self._recording_info[session_id]['stop_event'].set()
            
            # 先取得錄音資訊（避免 UnboundLocalError）
            info = self._recording_info.get(session_id, {})
            
            # 等待執行緒結束（增加超時時間並檢查檔案狀態）
            if session_id in self._recording_threads:
                thread = self._recording_threads[session_id]
                thread.join(timeout=5.0)  # 增加超時時間到 5 秒
                
                # 檢查執行緒是否真的結束
                if thread.is_alive():
                    logger.warning(f"錄音執行緒 {session_id} 在 5 秒後仍未結束")
                
                del self._recording_threads[session_id]
            
            # 等待檔案確實關閉
            import time
            max_wait = 2.0  # 最多再等 2 秒
            wait_interval = 0.1
            waited = 0
            
            # 檢查檔案是否已關閉
            while waited < max_wait:
                if info.get('file_closed', False):
                    logger.debug(f"確認檔案已關閉: {info.get('filepath')}")
                    break
                time.sleep(wait_interval)
                waited += wait_interval
            else:
                logger.warning(f"等待檔案關閉超時: {info.get('filepath')}")
            
            # 重新命名檔案以包含正確的結束時間
            old_filepath = info.get('filepath')
            new_filepath = None
            
            if old_filepath and old_filepath.exists():
                try:
                    # 取得開始和結束時間
                    start_time = info.get('start_time', datetime.now())
                    end_time = datetime.now()
                    
                    # 格式化時間字串
                    start_str = start_time.strftime('%Y%m%d.%H%M%S%f')[:-2]  # 微秒取前4位
                    end_str = end_time.strftime('%Y%m%d.%H%M%S%f')[:-2]  # 微秒取前4位
                    
                    # 建立新的檔案名稱
                    new_filename = f"[{session_id}]{start_str}-{end_str}.{self._recording_config.file_format}"
                    new_filepath = old_filepath.parent / new_filename
                    
                    # 重新命名檔案
                    old_filepath.rename(new_filepath)
                    logger.info(f"錄音檔案已重新命名: {old_filepath.name} -> {new_filename}")
                    
                except Exception as e:
                    logger.error(f"重新命名錄音檔案時發生錯誤: {e}")
                    new_filepath = old_filepath
            
            # 清理
            self._recording_sessions.discard(session_id)
            if session_id in self._recording_info:
                del self._recording_info[session_id]
            
            # 回傳錄音摘要
            return {
                'session_id': session_id,
                'filepath': str(new_filepath if new_filepath else info.get('filepath', '')),
                'start_time': info.get('start_time'),
                'end_time': datetime.now(),
                'chunks_written': info.get('chunks_written', 0),
                'bytes_written': info.get('bytes_written', 0),
                'metadata': info.get('metadata', {})
            }
    
    def is_recording(self, session_id: str) -> bool:
        """檢查 session 是否正在錄音。
        
        Args:
            session_id: Session ID
            
        Returns:
            是否正在錄音
        """
        with self._lock:
            return session_id in self._recording_sessions
    
    def get_recording_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得錄音資訊。
        
        Args:
            session_id: Session ID
            
        Returns:
            錄音資訊或 None（如果未在錄音中）
        """
        with self._lock:
            if session_id not in self._recording_sessions:
                return None
            
            info = self._recording_info.get(session_id, {})
            return {
                'session_id': session_id,
                'filepath': str(info.get('filepath', '')),
                'start_time': info.get('start_time'),
                'duration': (datetime.now() - info.get('start_time')).total_seconds() if info.get('start_time') else 0,
                'chunks_written': info.get('chunks_written', 0),
                'bytes_written': info.get('bytes_written', 0),
                'metadata': info.get('metadata', {})
            }
    
    def list_recordings(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """列出錄音檔案。
        
        Args:
            session_id: Session ID 用於過濾（可選）
            
        Returns:
            錄音檔案字典
        """
        recordings = []
        
        # 列出輸出目錄中的檔案
        pattern = f"{session_id}*.{self._recording_config.file_format}" if session_id else f"*.{self._recording_config.file_format}"
        
        for filepath in self._default_output_dir.glob(pattern):
            if filepath.is_file():
                stat = filepath.stat()
                recordings.append({
                    'filename': filepath.name,
                    'filepath': str(filepath),
                    'size_bytes': stat.st_size,
                    'created_time': datetime.fromtimestamp(stat.st_ctime),
                    'modified_time': datetime.fromtimestamp(stat.st_mtime)
                })
        
        # 按建立時間排序（最新的在前）
        recordings.sort(key=lambda x: x['created_time'], reverse=True)
        
        return {
            'count': len(recordings),
            'recordings': recordings
        }
    
    def cleanup_old_recordings(self, days: Optional[int] = None) -> int:
        """清理舊的錄音檔案。
        
        Args:
            days: 保留天數（可選，未指定則使用配置預設值）
            
        Returns:
            刪除的檔案數量
        """
        if days is None:
            days = self._recording_config.cleanup_days
        
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0
        
        for filepath in self._default_output_dir.glob(f"*.{self._recording_config.file_format}"):
            if filepath.is_file():
                # 檢查檔案年齡
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                if mtime < cutoff_date:
                    try:
                        filepath.unlink()
                        deleted_count += 1
                        logger.info(f"已刪除舊錄音檔案: {filepath}")
                    except Exception as e:
                        logger.error(f"無法刪除檔案 {filepath}: {e}")
        
        if deleted_count > 0:
            logger.info(f"已清理 {deleted_count} 個舊錄音檔案")
        
        return deleted_count
    
    def _recording_worker(self, session_id: str):
        """背景錄音工作執行緒。
        
        Args:
            session_id: Session ID
        """
        info = self._recording_info.get(session_id)
        if not info:
            logger.error(f"找不到 session {session_id} 的錄音資訊")
            return
        
        filepath = info['filepath']
        stop_event = info['stop_event']
        
        try:
            # 使用客戶端提供的參數，若無則使用預設值
            actual_sample_rate = info.get('sample_rate') or self._recording_config.sample_rate
            actual_channels = info.get('channels') or self._recording_config.channels
            audio_format = info.get('format') or 'int16'
            
            # 根據音訊格式決定 sample_width
            # int16 = 2 bytes, int32 = 4 bytes, float32 = 4 bytes
            format_to_width = {
                'int16': 2,
                'int32': 4,
                'float32': 4,
                'float64': 8
            }
            actual_sample_width = format_to_width.get(audio_format, 2)  # 預設使用 int16 (2 bytes)
            
            logger.info(f"💾 [RECORDING_CONFIG] Recording with parameters:")
            logger.info(f"   - Sample Rate: {actual_sample_rate} Hz")
            logger.info(f"   - Channels: {actual_channels}")
            logger.info(f"   - Format: {audio_format}")
            logger.info(f"   - Sample Width: {actual_sample_width} bytes")
            logger.info(f"   - File Path: {filepath}")
            
            # 開啟 WAV 檔案（使用客戶端的參數）
            wav_file = wave.open(str(filepath), 'wb')
            wav_file.setnchannels(actual_channels)
            wav_file.setsampwidth(actual_sample_width)
            wav_file.setframerate(actual_sample_rate)
            
            info['wav_file'] = wav_file
            
            logger.info(f"錄音工作執行緒已啟動，session: {session_id}")
            
            # 錄音迴圈
            chunks_buffer = []
            
            while not stop_event.is_set():
                # 從佇列取得音訊片段（使用非破壞性讀取）
                try:
                    timestamped_audio = audio_queue.pull_blocking_timestamp(
                        session_id,
                        reader_id="recording",
                        timeout=self._recording_config.wait_timeout
                    )
                    
                    if timestamped_audio is not None:
                        audio_chunk = timestamped_audio.audio
                    else:
                        audio_chunk = None
                    
                    if audio_chunk is not None:
                        # 加入緩衝區
                        chunks_buffer.append(audio_chunk)
                        
                        # 批次寫入檔案
                        if len(chunks_buffer) >= self._recording_config.recording_batch_size:
                            self._write_chunks_to_file(wav_file, chunks_buffer, info)
                            chunks_buffer = []
                        
                        # 檢查檔案大小限制
                        if info['bytes_written'] > self._recording_config.max_file_size_mb * 1024 * 1024:
                            logger.warning(f"錄音檔案大小已達上限，session: {session_id}")
                            break
                    
                except Exception as e:
                    # 超時是正常的，繼續
                    if 'timeout' not in str(e).lower():
                        logger.error(f"取得音訊片段時發生錯誤: {e}")
                    continue
            
            # 寫入剩餘的片段
            if chunks_buffer:
                self._write_chunks_to_file(wav_file, chunks_buffer, info)
            
            # 確保所有資料寫入磁碟後關閉檔案
            wav_file.close()
            logger.info(f"WAV 檔案已關閉: {filepath}")
            
            # 標記檔案寫入完成
            info['file_closed'] = True
            
            logger.info(f"錄音工作執行緒已停止，session: {session_id}")
            
        except Exception as e:
            logger.error(f"錄音工作執行緒發生錯誤，session {session_id}: {e}")
        
        finally:
            # 確保檔案已關閉
            if info.get('wav_file'):
                try:
                    info['wav_file'].close()
                except:
                    pass
    
    def _write_chunks_to_file(self, wav_file, chunks, info):
        """將音訊片段寫入 WAV 檔案。
        
        Args:
            wav_file: WAV 檔案物件
            chunks: 音訊片段列表
            info: 錄音資訊字典
        """
        import numpy as np
        
        try:
            for chunk in chunks:
                # 如果需要，將片段轉換為 bytes
                if hasattr(chunk, 'data'):
                    data = chunk.data
                else:
                    data = chunk
                
                # 確保轉換為 bytes（如果是 numpy array）
                if isinstance(data, np.ndarray):
                    # 記錄第一個 chunk 的格式（避免過多日誌）
                    if info['chunks_written'] == 0:
                        logger.info(f"📝 [RECORDING_WRITE] Writing numpy array: shape={data.shape}, dtype={data.dtype}")
                    data = data.tobytes()
                elif info['chunks_written'] == 0:
                    logger.info(f"📝 [RECORDING_WRITE] Writing raw bytes: {len(data)} bytes")
                
                # 寫入檔案
                wav_file.writeframes(data)
                
                # 更新統計
                info['chunks_written'] += 1
                info['bytes_written'] += len(data)
            
        except Exception as e:
            logger.error(f"寫入檔案時發生錯誤: {e}")
    
    def _setup_auto_cleanup(self):
        """設定自動清理舊錄音檔案。"""
        # 解析清理排程（HH:MM 格式）
        try:
            cleanup_time = self._recording_config.cleanup_schedule
            schedule.every().day.at(cleanup_time).do(self.cleanup_old_recordings)
            
            # 啟動排程執行緒
            def scheduler_worker():
                while True:
                    schedule.run_pending()
                    threading.Event().wait(60)  # 每分鐘檢查一次
            
            scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
            scheduler_thread.start()
            
            logger.info(f"已設定每日 {cleanup_time} 自動清理")
            
        except Exception as e:
            logger.error(f"設定自動清理失敗: {e}")


# 模組級單例實例
recording: Recording = Recording()