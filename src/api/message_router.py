"""
統一的訊息路由器
處理不同 API 協定之間的訊息轉換和路由
"""

import asyncio
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

from src.utils.logger import logger
from src.api.connection_manager import ConnectionType
from src.core.exceptions import RoutingError


class MessageType(Enum):
    """訊息類型"""
    # 控制訊息
    CONTROL = "control"
    CONTROL_RESPONSE = "control_response"
    
    # 音訊訊息
    AUDIO_DATA = "audio_data"
    AUDIO_METADATA = "audio_metadata"
    
    # 轉譯結果
    TRANSCRIPT_PARTIAL = "transcript_partial"
    TRANSCRIPT_FINAL = "transcript_final"
    
    # 狀態訊息
    STATUS = "status"
    STATUS_UPDATE = "status_update"
    
    # 系統訊息
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    
    # 連線管理
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"


@dataclass
class UnifiedMessage:
    """統一的訊息格式"""
    message_id: str
    message_type: MessageType
    source_protocol: ConnectionType
    target_protocol: Optional[ConnectionType] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "source_protocol": self.source_protocol.value,
            "target_protocol": self.target_protocol.value if self.target_protocol else None,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata
        }


class MessageRouter:
    """
    統一的訊息路由器
    負責不同協定之間的訊息轉換和路由
    """
    
    def __init__(self):
        """初始化訊息路由器"""
        
        # 訊息轉換器註冊表
        self.converters: Dict[tuple, Callable] = {}
        
        # 訊息處理器註冊表
        self.handlers: Dict[MessageType, List[Callable]] = {
            msg_type: [] for msg_type in MessageType
        }
        
        # 協定適配器
        self.protocol_adapters: Dict[ConnectionType, Any] = {}
        
        # 訊息佇列
        self.message_queue = asyncio.Queue()
        
        # 路由表
        self.routing_rules: List[Dict[str, Any]] = []
        
        # 註冊預設轉換器
        self._register_default_converters()
        
        self._running = False
        self._router_task = None
        
    def _register_default_converters(self):
        """註冊預設的訊息轉換器"""
        # WebSocket <-> Socket.io
        self.register_converter(
            ConnectionType.WEBSOCKET,
            ConnectionType.SOCKETIO,
            self._convert_websocket_to_socketio
        )
        self.register_converter(
            ConnectionType.SOCKETIO,
            ConnectionType.WEBSOCKET,
            self._convert_socketio_to_websocket
        )
        
        # HTTP SSE -> WebSocket/Socket.io
        self.register_converter(
            ConnectionType.HTTP_SSE,
            ConnectionType.WEBSOCKET,
            self._convert_sse_to_websocket
        )
        self.register_converter(
            ConnectionType.HTTP_SSE,
            ConnectionType.SOCKETIO,
            self._convert_sse_to_socketio
        )
        
    async def start(self):
        """啟動訊息路由器"""
        self._running = True
        self._router_task = asyncio.create_task(self._routing_loop())
        logger.info("Message router started")
        
    async def stop(self):
        """停止訊息路由器"""
        self._running = False
        
        if self._router_task:
            self._router_task.cancel()
            try:
                await self._router_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Message router stopped")
        
    def register_converter(self, 
                         source_protocol: ConnectionType,
                         target_protocol: ConnectionType,
                         converter: Callable):
        """
        註冊訊息轉換器
        
        Args:
            source_protocol: 來源協定
            target_protocol: 目標協定
            converter: 轉換函式
        """
        key = (source_protocol, target_protocol)
        self.converters[key] = converter
        logger.info(
            f"Registered converter: {source_protocol.value} -> {target_protocol.value}"
        )
        
    def register_handler(self, message_type: MessageType, handler: Callable):
        """
        註冊訊息處理器
        
        Args:
            message_type: 訊息類型
            handler: 處理函式
        """
        self.handlers[message_type].append(handler)
        logger.info(f"Registered handler for {message_type.value}")
        
    def register_protocol_adapter(self, protocol: ConnectionType, adapter: Any):
        """
        註冊協定適配器
        
        Args:
            protocol: 協定類型
            adapter: 適配器實例
        """
        self.protocol_adapters[protocol] = adapter
        logger.info(f"Registered adapter for {protocol.value}")
        
    async def route_message(self, message: UnifiedMessage):
        """
        路由訊息
        
        Args:
            message: 統一訊息
        """
        await self.message_queue.put(message)
        
    async def _routing_loop(self):
        """訊息路由循環"""
        while self._running:
            try:
                # 從佇列取得訊息
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )
                
                # 處理訊息
                await self._process_message(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in routing loop: {e}")
                
    async def _process_message(self, message: UnifiedMessage):
        """
        處理訊息
        
        Args:
            message: 統一訊息
        """
        try:
            # 執行訊息處理器
            handlers = self.handlers.get(message.message_type, [])
            for handler in handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")
                    
            # 如果有目標協定，進行轉換和轉發
            if message.target_protocol:
                await self._forward_message(message)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    async def _forward_message(self, message: UnifiedMessage):
        """
        轉發訊息到目標協定
        
        Args:
            message: 統一訊息
        """
        # 獲取轉換器
        converter_key = (message.source_protocol, message.target_protocol)
        converter = self.converters.get(converter_key)
        
        if not converter:
            logger.warning(
                f"No converter found for {message.source_protocol.value} -> "
                f"{message.target_protocol.value}"
            )
            return
            
        # 轉換訊息
        try:
            converted_data = await converter(message)
        except Exception as e:
            logger.error(f"Error converting message: {e}")
            return
            
        # 獲取目標協定適配器
        adapter = self.protocol_adapters.get(message.target_protocol)
        if not adapter:
            logger.warning(
                f"No adapter found for {message.target_protocol.value}"
            )
            return
            
        # 發送訊息
        try:
            await adapter.send_message(converted_data)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
    async def _convert_websocket_to_socketio(self, message: UnifiedMessage) -> Dict[str, Any]:
        """
        WebSocket 訊息轉換為 Socket.io 格式
        
        Args:
            message: WebSocket 訊息
            
        Returns:
            Socket.io 格式訊息
        """
        # 根據訊息類型進行轉換
        if message.message_type == MessageType.CONTROL:
            return {
                "event": "control",
                "data": message.data
            }
        elif message.message_type == MessageType.AUDIO_DATA:
            return {
                "event": "audio_chunk",
                "data": {
                    "audio": message.data.get("audio"),
                    "format": message.data.get("format", "base64"),
                    "chunk_id": message.data.get("chunk_id")
                }
            }
        elif message.message_type in [MessageType.TRANSCRIPT_PARTIAL, MessageType.TRANSCRIPT_FINAL]:
            return {
                "event": "partial_result" if message.message_type == MessageType.TRANSCRIPT_PARTIAL else "final_result",
                "data": message.data
            }
        else:
            return {
                "event": message.message_type.value,
                "data": message.data
            }
            
    async def _convert_socketio_to_websocket(self, message: UnifiedMessage) -> Dict[str, Any]:
        """
        Socket.io 訊息轉換為 WebSocket 格式
        
        Args:
            message: Socket.io 訊息
            
        Returns:
            WebSocket 格式訊息
        """
        # 從 Socket.io 事件轉換
        event = message.data.get("event")
        event_data = message.data.get("data", {})
        
        if event == "control":
            return {
                "type": "control",
                "command": event_data.get("command"),
                "params": event_data.get("params", {})
            }
        elif event == "audio_chunk":
            return {
                "type": "audio",
                "data": event_data.get("audio"),
                "format": event_data.get("format", "binary")
            }
        else:
            return {
                "type": event,
                "data": event_data
            }
            
    async def _convert_sse_to_websocket(self, message: UnifiedMessage) -> Dict[str, Any]:
        """
        HTTP SSE 訊息轉換為 WebSocket 格式
        
        Args:
            message: SSE 訊息
            
        Returns:
            WebSocket 格式訊息
        """
        return {
            "type": message.message_type.value,
            "data": message.data,
            "timestamp": message.timestamp.isoformat()
        }
        
    async def _convert_sse_to_socketio(self, message: UnifiedMessage) -> Dict[str, Any]:
        """
        HTTP SSE 訊息轉換為 Socket.io 格式
        
        Args:
            message: SSE 訊息
            
        Returns:
            Socket.io 格式訊息
        """
        return {
            "event": message.message_type.value,
            "data": message.data
        }
        
    def add_routing_rule(self, rule: Dict[str, Any]):
        """
        添加路由規則
        
        Args:
            rule: 路由規則
        """
        self.routing_rules.append(rule)
        logger.info(f"Added routing rule: {rule}")
        
    def create_unified_message(self,
                             message_type: MessageType,
                             source_protocol: ConnectionType,
                             data: Dict[str, Any],
                             session_id: Optional[str] = None,
                             target_protocol: Optional[ConnectionType] = None,
                             metadata: Optional[Dict[str, Any]] = None) -> UnifiedMessage:
        """
        建立統一訊息
        
        Args:
            message_type: 訊息類型
            source_protocol: 來源協定
            data: 訊息資料
            session_id: Session ID
            target_protocol: 目標協定
            metadata: 元資料
            
        Returns:
            統一訊息
        """
        import uuid
        
        return UnifiedMessage(
            message_id=str(uuid.uuid4()),
            message_type=message_type,
            source_protocol=source_protocol,
            target_protocol=target_protocol,
            session_id=session_id,
            data=data,
            metadata=metadata or {}
        )