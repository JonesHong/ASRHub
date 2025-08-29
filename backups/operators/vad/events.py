"""
VAD 事件定義和管理
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
import time

from src.utils.logger import logger


class VADEvent(str, Enum):
    """VAD 事件類型"""
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    SILENCE_TIMEOUT = "silence_timeout"
    VAD_RESULT = "vad_result"
    THRESHOLD_CHANGED = "threshold_changed"
    STATE_CHANGED = "state_changed"


@dataclass
class VADEventData:
    """VAD 事件數據"""
    event_type: VADEvent
    timestamp: float
    session_id: Optional[str] = None
    speech_probability: Optional[float] = None
    speech_duration: Optional[float] = None
    silence_duration: Optional[float] = None
    threshold: Optional[float] = None
    in_speech: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        data = {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp,
            'session_id': self.session_id
        }
        
        # 添加非 None 的可選字段
        optional_fields = [
            'speech_probability', 'speech_duration', 'silence_duration',
            'threshold', 'in_speech', 'metadata'
        ]
        
        for field in optional_fields:
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        
        return data


class VADEventManager:
    """VAD 事件管理器"""
    
    def __init__(self):
        """初始化事件管理器"""
        self.listeners: Dict[VADEvent, List[Callable]] = {
            event: [] for event in VADEvent
        }
        self.event_history: List[VADEventData] = []
        self.max_history_size = 1000
    
    def register_listener(self, event_type: VADEvent, callback: Callable):
        """
        註冊事件監聽器
        
        Args:
            event_type: 事件類型
            callback: 回調函數
        """
        if event_type not in self.listeners:
            logger.warning(f"未知的事件類型: {event_type}")
            return
        
        self.listeners[event_type].append(callback)
        logger.debug(f"註冊 {event_type.value} 事件監聽器")
    
    def unregister_listener(self, event_type: VADEvent, callback: Callable):
        """
        取消註冊事件監聽器
        
        Args:
            event_type: 事件類型
            callback: 回調函數
        """
        if event_type in self.listeners and callback in self.listeners[event_type]:
            self.listeners[event_type].remove(callback)
            logger.debug(f"取消註冊 {event_type.value} 事件監聽器")
    
    async def emit_event(self, event_data: VADEventData):
        """
        發送事件
        
        Args:
            event_data: 事件數據
        """
        # 添加到歷史記錄
        self.event_history.append(event_data)
        
        # 限制歷史記錄大小
        if len(self.event_history) > self.max_history_size:
            self.event_history = self.event_history[-self.max_history_size:]
        
        # 觸發監聽器
        listeners = self.listeners.get(event_data.event_type, [])
        
        for listener in listeners:
            try:
                # 如果是異步函數
                if asyncio.iscoroutinefunction(listener):
                    await listener(event_data)
                else:
                    listener(event_data)
                    
            except Exception as e:
                logger.error(f"事件監聽器執行錯誤: {e}")
    
    def get_event_history(self, 
                         event_type: Optional[VADEvent] = None,
                         limit: int = 100) -> List[VADEventData]:
        """
        獲取事件歷史
        
        Args:
            event_type: 特定事件類型（可選）
            limit: 返回數量限制
            
        Returns:
            事件列表
        """
        if event_type:
            history = [e for e in self.event_history if e.event_type == event_type]
        else:
            history = self.event_history
        
        return history[-limit:]
    
    def clear_history(self):
        """清空事件歷史"""
        self.event_history.clear()
        logger.debug("已清空 VAD 事件歷史")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        獲取事件統計信息
        
        Returns:
            統計信息字典
        """
        stats = {
            'total_events': len(self.event_history),
            'event_counts': {},
            'listener_counts': {}
        }
        
        # 統計各類事件數量
        for event in VADEvent:
            count = sum(1 for e in self.event_history if e.event_type == event)
            stats['event_counts'][event.value] = count
            stats['listener_counts'][event.value] = len(self.listeners[event])
        
        # 計算語音活動統計
        speech_starts = [e for e in self.event_history if e.event_type == VADEvent.SPEECH_START]
        speech_ends = [e for e in self.event_history if e.event_type == VADEvent.SPEECH_END]
        
        if speech_starts:
            stats['first_speech_time'] = speech_starts[0].timestamp
            stats['last_speech_time'] = speech_starts[-1].timestamp
        
        if speech_ends:
            total_speech_duration = sum(e.speech_duration for e in speech_ends if e.speech_duration)
            stats['total_speech_duration'] = total_speech_duration
            stats['average_speech_duration'] = total_speech_duration / len(speech_ends) if speech_ends else 0
        
        return stats


# 單例事件管理器
_event_manager = None

def get_vad_event_manager() -> VADEventManager:
    """獲取 VAD 事件管理器單例"""
    global _event_manager
    if _event_manager is None:
        _event_manager = VADEventManager()
    return _event_manager


# 快捷函數
async def emit_vad_event(event_type: VADEvent, **kwargs):
    """
    發送 VAD 事件的快捷函數
    
    Args:
        event_type: 事件類型
        **kwargs: 事件數據
    """
    event_data = VADEventData(
        event_type=event_type,
        timestamp=time.time(),
        **kwargs
    )
    
    manager = get_vad_event_manager()
    await manager.emit_event(event_data)


import asyncio  # 放在最後避免循環導入