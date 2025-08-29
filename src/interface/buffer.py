"""Buffer 管理器介面定義

定義音訊緩衝區管理的抽象介面。
用於統一不同服務對音訊分塊的需求。
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Literal
from dataclasses import dataclass, field

# 延遲載入 ConfigManager 避免循環引用
_config_manager = None

def _get_config_manager():
    """延遲載入 ConfigManager"""
    global _config_manager
    if _config_manager is None:
        from src.config.manager import ConfigManager
        _config_manager = ConfigManager()
    return _config_manager

# Buffer 模式類型
Mode = Literal["fixed", "sliding", "dynamic"]


def _get_buffer_defaults():
    """從 ConfigManager 取得預設值"""
    config = _get_config_manager()
    buffer_config = config.services.buffer_manager
    return {
        'sample_rate': buffer_config.default_sample_rate,
        'channels': buffer_config.default_channels,
        'sample_width': buffer_config.default_sample_width,
        'max_buffer_size': buffer_config.max_buffer_size
    }


@dataclass
class BufferConfig:
    """Buffer 配置
    
    Attributes:
        mode: 緩衝模式 (fixed/sliding/dynamic)
        frame_size: 固定模式的幀大小（樣本數）
        step_size: 滑動模式的步進大小（樣本數）
        sample_rate: 採樣率（從 config.yaml 載入）
        channels: 聲道數（從 config.yaml 載入）
        sample_width: 每個樣本的字節數（從 config.yaml 載入）
        max_buffer_size: 最大緩衝區大小（從 config.yaml 載入）
        min_duration_ms: 動態模式的最小持續時間（毫秒）
        max_duration_ms: 動態模式的最大持續時間（毫秒）
    """
    mode: Mode = "fixed"
    frame_size: Optional[int] = None
    step_size: Optional[int] = None
    sample_rate: int = field(default_factory=lambda: _get_buffer_defaults()['sample_rate'])
    channels: int = field(default_factory=lambda: _get_buffer_defaults()['channels'])
    sample_width: int = field(default_factory=lambda: _get_buffer_defaults()['sample_width'])
    max_buffer_size: Optional[int] = field(default_factory=lambda: _get_buffer_defaults()['max_buffer_size'])
    min_duration_ms: Optional[int] = None
    max_duration_ms: Optional[int] = None
    
    @classmethod
    def for_silero_vad(cls, sample_rate: Optional[int] = None, window_ms: Optional[int] = None) -> 'BufferConfig':
        """Silero VAD 配置（從 config.yaml 載入預設值）"""
        config = _get_config_manager()
        buffer_cfg = config.services.buffer_manager
        vad_cfg = buffer_cfg.vad_buffer
        
        # 使用配置值或覆蓋參數
        window_ms = window_ms or vad_cfg.window_ms
        sample_rate = sample_rate or buffer_cfg.default_sample_rate
        
        frame_size = int(sample_rate * window_ms / 1000)  # 樣本數
        return cls(
            mode=vad_cfg.mode,
            frame_size=frame_size,
            sample_rate=sample_rate
        )
    
    @classmethod
    def for_openwakeword(cls, sample_rate: Optional[int] = None, frame_samples: Optional[int] = None) -> 'BufferConfig':
        """OpenWakeWord 配置（從 config.yaml 載入預設值）"""
        config = _get_config_manager()
        buffer_cfg = config.services.buffer_manager
        wakeword_cfg = buffer_cfg.wakeword_buffer
        
        # 使用配置值或覆蓋參數
        frame_samples = frame_samples or wakeword_cfg.frame_samples
        sample_rate = sample_rate or buffer_cfg.default_sample_rate
            
        return cls(
            mode=wakeword_cfg.mode,
            frame_size=frame_samples,  # 直接是樣本數
            sample_rate=sample_rate
        )
    
    @classmethod
    def for_funasr(cls, sample_rate: Optional[int] = None, frames_per_buffer: Optional[int] = None) -> 'BufferConfig':
        """FunASR 配置（從 config.yaml 載入預設值）"""
        config = _get_config_manager()
        buffer_cfg = config.services.buffer_manager
        funasr_cfg = buffer_cfg.funasr_buffer
        
        # 使用配置值或覆蓋參數
        frames_per_buffer = frames_per_buffer or funasr_cfg.frames_per_buffer
        sample_rate = sample_rate or buffer_cfg.default_sample_rate
            
        return cls(
            mode=funasr_cfg.mode,
            frame_size=frames_per_buffer,  # 直接是樣本數
            sample_rate=sample_rate
        )
    
    @classmethod  
    def for_whisper(cls, sample_rate: Optional[int] = None, 
                   window_seconds: Optional[int] = None,
                   step_seconds: Optional[int] = None) -> 'BufferConfig':
        """Whisper 配置（從 config.yaml 載入預設值）"""
        config = _get_config_manager()
        buffer_cfg = config.services.buffer_manager
        whisper_cfg = buffer_cfg.whisper_buffer
        
        # 使用配置值或覆蓋參數
        window_seconds = window_seconds or whisper_cfg.window_seconds
        step_seconds = step_seconds or whisper_cfg.step_seconds
        sample_rate = sample_rate or buffer_cfg.default_sample_rate
            
        frame_size = sample_rate * window_seconds  # 樣本數
        step_size = sample_rate * step_seconds  # 樣本數
        return cls(
            mode=whisper_cfg.mode,
            frame_size=frame_size,
            step_size=step_size,
            sample_rate=sample_rate
        )


class IBufferManager(ABC):
    """Buffer 管理器介面
    
    提供統一的音訊緩衝區管理功能。
    支援固定大小、滑動窗口和動態大小三種模式。
    """
    
    @abstractmethod
    def push(self, data: bytes) -> None:
        """推入音訊資料
        
        Args:
            data: 音訊資料（bytes）
        """
        pass
    
    @abstractmethod
    def pop(self) -> Optional[bytes]:
        """取出一個完整的 frame
        
        Returns:
            完整的音訊 frame 或 None（如果資料不足）
        """
        pass
    
    @abstractmethod
    def pop_all(self) -> List[bytes]:
        """取出所有完整的 frames
        
        Returns:
            所有完整的音訊 frames 列表
        """
        pass
    
    @abstractmethod
    def flush(self) -> Optional[bytes]:
        """清空緩衝區並返回剩餘資料
        
        Returns:
            剩餘的音訊資料或 None
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """重置緩衝區"""
        pass
    
    @abstractmethod
    def ready(self) -> bool:
        """檢查是否有完整的 frame 可取出
        
        Returns:
            True 如果有完整的 frame
        """
        pass
    
    @abstractmethod
    def buffered_bytes(self) -> int:
        """取得當前緩衝的字節數
        
        Returns:
            緩衝區中的字節數
        """
        pass