#!/usr/bin/env python3
"""
音頻元數據協議
定義各種 API 如何傳遞音頻格式信息
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
import json
from enum import Enum

from src.models.audio_format import AudioMetadata, AudioFormat


class MetadataTransmissionMethod(Enum):
    """元數據傳輸方式"""
    HEADERS = "headers"           # HTTP/WebSocket headers
    FIRST_MESSAGE = "first_message"  # 第一條消息
    INLINE = "inline"             # 每條消息都包含
    SIDEBAND = "sideband"         # 獨立通道


@dataclass
class AudioStreamConfig:
    """音頻流配置"""
    # 音頻格式
    metadata: AudioMetadata
    
    # 傳輸設定
    transmission_method: MetadataTransmissionMethod = MetadataTransmissionMethod.FIRST_MESSAGE
    
    # 緩衝設定
    chunk_duration_ms: int = 100  # 每個 chunk 的時長（毫秒）
    
    # 是否包含時間戳
    include_timestamps: bool = True
    
    # 是否壓縮
    compression: Optional[str] = None  # 'gzip', 'zlib', None
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'metadata': self.metadata.to_dict(),
            'transmission_method': self.transmission_method.value,
            'chunk_duration_ms': self.chunk_duration_ms,
            'include_timestamps': self.include_timestamps,
            'compression': self.compression
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioStreamConfig':
        """從字典創建"""
        return cls(
            metadata=AudioMetadata.from_dict(data['metadata']),
            transmission_method=MetadataTransmissionMethod(data.get('transmission_method', 'first_message')),
            chunk_duration_ms=data.get('chunk_duration_ms', 100),
            include_timestamps=data.get('include_timestamps', True),
            compression=data.get('compression')
        )


class AudioMessage:
    """統一的音頻消息格式"""
    
    MESSAGE_TYPES = {
        'config': 'audio_config',      # 配置消息
        'data': 'audio_data',          # 音頻數據
        'control': 'control',          # 控制消息
        'status': 'status'             # 狀態消息
    }
    
    def __init__(self, message_type: str, **kwargs):
        self.type = message_type
        self.data = kwargs
    
    def to_json(self) -> str:
        """轉換為 JSON"""
        return json.dumps({
            'type': self.type,
            **self.data
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AudioMessage':
        """從 JSON 創建"""
        data = json.loads(json_str)
        msg_type = data.pop('type')
        return cls(msg_type, **data)
    
    @classmethod
    def create_config_message(cls, config: AudioStreamConfig) -> 'AudioMessage':
        """創建配置消息"""
        return cls(
            cls.MESSAGE_TYPES['config'],
            config=config.to_dict()
        )
    
    @classmethod
    def create_data_message(cls, audio_data: bytes, 
                          timestamp: Optional[float] = None,
                          sequence: Optional[int] = None) -> 'AudioMessage':
        """創建音頻數據消息"""
        import base64
        return cls(
            cls.MESSAGE_TYPES['data'],
            audio=base64.b64encode(audio_data).decode('utf-8'),
            timestamp=timestamp,
            sequence=sequence
        )


class HTTPAudioProtocol:
    """HTTP 音頻協議"""
    
    @staticmethod
    def create_headers(metadata: AudioMetadata) -> Dict[str, str]:
        """創建 HTTP headers"""
        return {
            'X-Audio-Sample-Rate': str(metadata.sample_rate),
            'X-Audio-Channels': str(metadata.channels),
            'X-Audio-Format': metadata.format.value,
            'X-Audio-Encoding': 'raw',  # raw, base64, etc.
        }
    
    @staticmethod
    def parse_headers(headers: Dict[str, str]) -> AudioMetadata:
        """從 HTTP headers 解析"""
        return AudioMetadata(
            sample_rate=int(headers.get('X-Audio-Sample-Rate', '16000')),
            channels=int(headers.get('X-Audio-Channels', '1')),
            format=AudioFormat(headers.get('X-Audio-Format', 'int16'))
        )


class WebSocketAudioProtocol:
    """WebSocket 音頻協議"""
    
    def __init__(self, config: AudioStreamConfig):
        self.config = config
        self.sequence = 0
    
    async def send_initial_config(self, websocket):
        """發送初始配置"""
        msg = AudioMessage.create_config_message(self.config)
        await websocket.send(msg.to_json())
    
    async def send_audio_data(self, websocket, audio_data: bytes, timestamp: float):
        """發送音頻數據"""
        if self.config.transmission_method == MetadataTransmissionMethod.INLINE:
            # 每條消息都包含元數據
            msg = {
                'type': 'audio_data',
                'audio': audio_data,
                'metadata': self.config.metadata.to_dict(),
                'timestamp': timestamp,
                'sequence': self.sequence
            }
        else:
            # 只發送音頻數據
            msg = AudioMessage.create_data_message(
                audio_data, 
                timestamp=timestamp,
                sequence=self.sequence
            )
        
        self.sequence += 1
        
        if isinstance(msg, dict):
            await websocket.send_json(msg)
        else:
            await websocket.send(msg.to_json())


class SSEAudioProtocol:
    """Server-Sent Events 音頻協議"""
    
    @staticmethod
    def format_config_event(config: AudioStreamConfig) -> str:
        """格式化配置事件"""
        return f"event: audio_config\ndata: {json.dumps(config.to_dict())}\n\n"
    
    @staticmethod
    def format_data_event(audio_data: bytes, timestamp: float) -> str:
        """格式化數據事件"""
        import base64
        data = {
            'audio': base64.b64encode(audio_data).decode('utf-8'),
            'timestamp': timestamp
        }
        return f"event: audio_data\ndata: {json.dumps(data)}\n\n"


class MicrophoneService:
    """
    麥克風服務示例
    展示如何獲取和傳遞音頻元數據
    """
    
    def __init__(self):
        self.current_config = None
        self._detect_microphone_format()
    
    def _detect_microphone_format(self):
        """檢測麥克風格式"""
        import pyaudio
        p = pyaudio.PyAudio()
        
        try:
            # 獲取預設輸入設備信息
            device_info = p.get_default_input_device_info()
            
            # 嘗試不同的格式
            for sample_rate in [48000, 44100, 16000]:
                for channels in [2, 1]:
                    for format_info in [
                        (pyaudio.paInt24, AudioFormat.INT24),
                        (pyaudio.paInt16, AudioFormat.INT16)
                    ]:
                        pa_format, audio_format = format_info
                        
                        try:
                            # 測試是否支援此格式
                            stream = p.open(
                                format=pa_format,
                                channels=channels,
                                rate=sample_rate,
                                input=True,
                                frames_per_buffer=1024,
                                start=False
                            )
                            stream.close()
                            
                            # 成功！保存配置
                            self.current_config = AudioStreamConfig(
                                metadata=AudioMetadata(
                                    sample_rate=sample_rate,
                                    channels=channels,
                                    format=audio_format
                                )
                            )
                            
                            print(f"✅ Detected microphone format: {sample_rate}Hz, {channels}ch, {audio_format.value}")
                            p.terminate()
                            return
                            
                        except:
                            continue
            
            # 使用預設值
            self.current_config = AudioStreamConfig(
                metadata=AudioMetadata(16000, 1, AudioFormat.INT16)
            )
            
        finally:
            p.terminate()
    
    def get_current_config(self) -> AudioStreamConfig:
        """獲取當前麥克風配置"""
        return self.current_config
    
    async def start_streaming_to_asrhub(self, asrhub_url: str):
        """開始串流到 ASRHub"""
        import aiohttp
        
        # 根據不同的 API 選擇協議
        if 'websocket' in asrhub_url:
            await self._stream_via_websocket(asrhub_url)
        elif 'sse' in asrhub_url:
            await self._stream_via_sse(asrhub_url)
        else:
            await self._stream_via_http(asrhub_url)
    
    async def _stream_via_websocket(self, url: str):
        """通過 WebSocket 串流"""
        import websockets
        
        async with websockets.connect(url) as websocket:
            # 1. 發送音頻配置
            protocol = WebSocketAudioProtocol(self.current_config)
            await protocol.send_initial_config(websocket)
            
            # 2. 開始錄音並串流
            # ... 錄音邏輯 ...
            
    async def _stream_via_http(self, url: str):
        """通過 HTTP 串流"""
        import aiohttp
        
        # 創建 headers
        headers = HTTPAudioProtocol.create_headers(self.current_config.metadata)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                # ... 發送音頻數據 ...
                pass


# 使用示例
if __name__ == "__main__":
    # 麥克風服務檢測格式
    mic_service = MicrophoneService()
    config = mic_service.get_current_config()
    
    print(f"\n當前麥克風配置:")
    print(f"  採樣率: {config.metadata.sample_rate} Hz")
    print(f"  聲道數: {config.metadata.channels}")
    print(f"  格式: {config.metadata.format.value}")
    
    # 展示不同協議的元數據傳遞
    print(f"\nHTTP Headers:")
    headers = HTTPAudioProtocol.create_headers(config.metadata)
    for k, v in headers.items():
        print(f"  {k}: {v}")
    
    print(f"\nWebSocket 初始消息:")
    msg = AudioMessage.create_config_message(config)
    print(f"  {msg.to_json()}")
    
    print(f"\nSSE 配置事件:")
    sse_event = SSEAudioProtocol.format_config_event(config)
    print(f"  {sse_event}")