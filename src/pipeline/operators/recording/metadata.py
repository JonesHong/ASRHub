"""
錄音元數據管理
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from src.utils.logger import logger



@dataclass
class AudioMetadata:
    """音訊元數據"""
    # 基本資訊
    session_id: str
    recording_id: str
    start_time: float
    end_time: float
    duration: float
    
    # 音訊參數
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    format: str = "wav"
    codec: Optional[str] = None
    
    # 檔案資訊
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    checksum: Optional[str] = None
    
    # VAD 資訊
    vad_enabled: bool = False
    speech_segments: List[Dict[str, float]] = field(default_factory=list)
    total_speech_duration: float = 0.0
    speech_ratio: float = 0.0
    
    # 分段資訊
    is_segmented: bool = False
    segment_index: Optional[int] = None
    total_segments: Optional[int] = None
    segment_files: List[str] = field(default_factory=list)
    
    # 自定義標籤
    tags: Dict[str, Any] = field(default_factory=dict)
    
    # 處理資訊
    processing_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        data = asdict(self)
        # 轉換時間戳為可讀格式
        data['start_time_str'] = datetime.fromtimestamp(self.start_time).isoformat()
        data['end_time_str'] = datetime.fromtimestamp(self.end_time).isoformat()
        return data
    
    def to_json(self, indent: int = 2) -> str:
        """轉換為 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioMetadata':
        """從字典創建"""
        # 移除額外的時間字符串字段
        data.pop('start_time_str', None)
        data.pop('end_time_str', None)
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AudioMetadata':
        """從 JSON 字符串創建"""
        data = json.loads(json_str)
        return cls.from_dict(data)


class MetadataManager:
    """元數據管理器"""
    
    def __init__(self, metadata_dir: Optional[Path] = None):
        """
        初始化元數據管理器
        
        Args:
            metadata_dir: 元數據儲存目錄
        """
        self.metadata_dir = metadata_dir
        if metadata_dir:
            metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # 記憶體快取
        self.metadata_cache: Dict[str, AudioMetadata] = {}
    
    def create_metadata(self, **kwargs) -> AudioMetadata:
        """
        創建元數據
        
        Args:
            **kwargs: 元數據字段
            
        Returns:
            AudioMetadata 實例
        """
        metadata = AudioMetadata(**kwargs)
        
        # 加入快取
        cache_key = f"{metadata.session_id}_{metadata.recording_id}"
        self.metadata_cache[cache_key] = metadata
        
        logger.debug(f"創建元數據: {cache_key}")
        return metadata
    
    def update_metadata(self, 
                       session_id: str,
                       recording_id: str,
                       updates: Dict[str, Any]) -> Optional[AudioMetadata]:
        """
        更新元數據
        
        Args:
            session_id: 會話 ID
            recording_id: 錄音 ID
            updates: 更新內容
            
        Returns:
            更新後的元數據
        """
        cache_key = f"{session_id}_{recording_id}"
        metadata = self.metadata_cache.get(cache_key)
        
        if not metadata:
            logger.warning(f"找不到元數據: {cache_key}")
            return None
        
        # 更新字段
        for key, value in updates.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
            else:
                # 添加到自定義標籤
                metadata.tags[key] = value
        
        logger.debug(f"更新元數據: {cache_key}")
        return metadata
    
    def add_speech_segment(self,
                          session_id: str,
                          recording_id: str,
                          start_time: float,
                          end_time: float,
                          confidence: Optional[float] = None):
        """
        添加語音段落
        
        Args:
            session_id: 會話 ID
            recording_id: 錄音 ID
            start_time: 開始時間
            end_time: 結束時間
            confidence: 置信度
        """
        metadata = self.get_metadata(session_id, recording_id)
        if not metadata:
            return
        
        segment = {
            'start': start_time,
            'end': end_time,
            'duration': end_time - start_time
        }
        
        if confidence is not None:
            segment['confidence'] = confidence
        
        metadata.speech_segments.append(segment)
        
        # 更新統計
        metadata.total_speech_duration = sum(s['duration'] for s in metadata.speech_segments)
        if metadata.duration > 0:
            metadata.speech_ratio = metadata.total_speech_duration / metadata.duration
    
    def add_processing_info(self,
                           session_id: str,
                           recording_id: str,
                           processor_name: str,
                           info: Dict[str, Any]):
        """
        添加處理資訊
        
        Args:
            session_id: 會話 ID
            recording_id: 錄音 ID
            processor_name: 處理器名稱
            info: 處理資訊
        """
        metadata = self.get_metadata(session_id, recording_id)
        if not metadata:
            return
        
        metadata.processing_info[processor_name] = {
            **info,
            'timestamp': datetime.now().isoformat()
        }
    
    def save_metadata(self, 
                     session_id: str,
                     recording_id: str,
                     file_path: Optional[Path] = None) -> Optional[Path]:
        """
        儲存元數據到文件
        
        Args:
            session_id: 會話 ID
            recording_id: 錄音 ID
            file_path: 指定的文件路徑
            
        Returns:
            儲存的文件路徑
        """
        metadata = self.get_metadata(session_id, recording_id)
        if not metadata:
            return None
        
        # 確定儲存路徑
        if file_path is None:
            if self.metadata_dir:
                file_path = self.metadata_dir / f"{session_id}_{recording_id}_metadata.json"
            else:
                logger.warning("沒有指定元數據儲存路徑")
                return None
        
        # 儲存到文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(metadata.to_json())
            
            logger.info(f"元數據已儲存: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"儲存元數據失敗: {e}")
            return None
    
    def load_metadata(self, file_path: Path) -> Optional[AudioMetadata]:
        """
        從文件載入元數據
        
        Args:
            file_path: 文件路徑
            
        Returns:
            元數據實例
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json_str = f.read()
            
            metadata = AudioMetadata.from_json(json_str)
            
            # 加入快取
            cache_key = f"{metadata.session_id}_{metadata.recording_id}"
            self.metadata_cache[cache_key] = metadata
            
            logger.info(f"元數據已載入: {file_path}")
            return metadata
            
        except Exception as e:
            logger.error(f"載入元數據失敗: {e}")
            return None
    
    def get_metadata(self, 
                    session_id: str,
                    recording_id: str) -> Optional[AudioMetadata]:
        """
        獲取元數據
        
        Args:
            session_id: 會話 ID
            recording_id: 錄音 ID
            
        Returns:
            元數據實例
        """
        cache_key = f"{session_id}_{recording_id}"
        return self.metadata_cache.get(cache_key)
    
    def list_metadata(self, session_id: Optional[str] = None) -> List[AudioMetadata]:
        """
        列出元數據
        
        Args:
            session_id: 會話 ID（可選）
            
        Returns:
            元數據列表
        """
        if session_id:
            return [m for m in self.metadata_cache.values() if m.session_id == session_id]
        else:
            return list(self.metadata_cache.values())
    
    def clear_cache(self):
        """清空快取"""
        self.metadata_cache.clear()
        logger.debug("元數據快取已清空")
    
    def generate_summary(self, session_id: str) -> Dict[str, Any]:
        """
        生成會話摘要
        
        Args:
            session_id: 會話 ID
            
        Returns:
            摘要字典
        """
        metadata_list = self.list_metadata(session_id)
        
        if not metadata_list:
            return {}
        
        summary = {
            'session_id': session_id,
            'total_recordings': len(metadata_list),
            'total_duration': sum(m.duration for m in metadata_list),
            'total_size': sum(m.file_size or 0 for m in metadata_list),
            'total_speech_duration': sum(m.total_speech_duration for m in metadata_list),
            'average_speech_ratio': sum(m.speech_ratio for m in metadata_list) / len(metadata_list),
            'formats': list(set(m.format for m in metadata_list)),
            'sample_rates': list(set(m.sample_rate for m in metadata_list)),
            'recordings': []
        }
        
        # 添加每個錄音的摘要
        for metadata in metadata_list:
            recording_summary = {
                'recording_id': metadata.recording_id,
                'duration': metadata.duration,
                'speech_ratio': metadata.speech_ratio,
                'segments': len(metadata.speech_segments),
                'file_path': metadata.file_path
            }
            summary['recordings'].append(recording_summary)
        
        return summary