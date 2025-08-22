"""
SSE 連線管理器
專門處理 Server-Sent Events 相關邏輯
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, Set
from datetime import datetime
from src.utils.logger import logger


class SSEConnectionManager:
    """SSE 連線管理器"""
    
    def __init__(self, max_connections: int = 100):
        """
        初始化
        
        Args:
            max_connections: 最大連線數
        """
        self.connections: Dict[str, asyncio.Queue] = {}
        self.max_connections = max_connections
    
    def is_connected(self, session_id: str) -> bool:
        """檢查 Session 是否已連線"""
        return session_id in self.connections
    
    def can_accept_connection(self) -> bool:
        """檢查是否可以接受新連線"""
        return len(self.connections) < self.max_connections
    
    async def add_connection(self, session_id: str) -> asyncio.Queue:
        """
        添加新連線
        
        Args:
            session_id: Session ID
            
        Returns:
            訊息佇列
            
        Raises:
            ConnectionError: 如果超過最大連線數
        """
        if not self.can_accept_connection():
            raise ConnectionError("Too many connections")
        
        if session_id in self.connections:
            # 如果已存在，先清理舊的
            await self.remove_connection(session_id)
        
        queue = asyncio.Queue()
        self.connections[session_id] = queue
        logger.debug(f"SSE 連線建立 - Session: {session_id[:8]}...")
        return queue
    
    async def remove_connection(self, session_id: str):
        """
        移除連線
        
        Args:
            session_id: Session ID
        """
        if session_id in self.connections:
            queue = self.connections[session_id]
            # 發送結束訊號
            await queue.put(None)
            del self.connections[session_id]
            logger.debug(f"SSE 連線移除 - Session: {session_id[:8]}...")
    
    async def send_event(self, session_id: str, event: Dict[str, Any]):
        """
        發送事件到指定連線
        
        Args:
            session_id: Session ID
            event: 事件資料
        """
        if session_id in self.connections:
            queue = self.connections[session_id]
            await queue.put(event)
    
    async def broadcast_event(self, event: Dict[str, Any], 
                            exclude: Optional[Set[str]] = None):
        """
        廣播事件到所有連線
        
        Args:
            event: 事件資料
            exclude: 要排除的 Session ID 集合
        """
        exclude = exclude or set()
        
        for session_id, queue in self.connections.items():
            if session_id not in exclude:
                await queue.put(event)
    
    def format_sse_event(self, event: str, data: Any, event_id: Optional[str] = None) -> str:
        """
        格式化 SSE 事件
        
        Args:
            event: 事件類型
            data: 事件資料
            event_id: 事件 ID（可選）
            
        Returns:
            SSE 格式字串
        """
        lines = []
        
        # 事件類型
        if event:
            lines.append(f"event: {event}")
        
        # 轉換資料為 JSON
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, ensure_ascii=False)
        else:
            data_str = str(data)
        
        # SSE 規範要求每行資料都要有 "data: " 前綴
        for line in data_str.split('\n'):
            lines.append(f"data: {line}")
        
        # 添加事件 ID
        if event_id:
            lines.append(f"id: {event_id}")
        else:
            lines.append(f"id: {int(time.time() * 1000)}")
        
        # 事件結束需要兩個換行符
        return '\n'.join(lines) + '\n\n'
    
    async def create_heartbeat_task(self, session_id: str, interval: int = 30):
        """
        建立心跳任務
        
        Args:
            session_id: Session ID
            interval: 心跳間隔（秒）
            
        Returns:
            心跳任務
        """
        async def heartbeat():
            while session_id in self.connections:
                await asyncio.sleep(interval)
                await self.send_event(session_id, {
                    "event": "heartbeat",
                    "data": {"timestamp": datetime.now().isoformat()}
                })
        
        return asyncio.create_task(heartbeat())
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """獲取連線統計資訊"""
        return {
            "active_connections": len(self.connections),
            "max_connections": self.max_connections,
            "usage_percentage": (len(self.connections) / self.max_connections * 100) 
                             if self.max_connections > 0 else 0,
            "session_ids": list(self.connections.keys())
        }
    
    async def cleanup_all(self):
        """清理所有連線"""
        session_ids = list(self.connections.keys())
        for session_id in session_ids:
            await self.remove_connection(session_id)
        logger.info("所有 SSE 連線已清理")


class SSEEventBuilder:
    """SSE 事件建構器"""
    
    @staticmethod
    def connected_event(session_id: str) -> Dict[str, Any]:
        """建立連線事件"""
        return {
            "event": "connected",
            "data": {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    @staticmethod
    def disconnected_event(session_id: str) -> Dict[str, Any]:
        """建立斷線事件"""
        return {
            "event": "disconnected",
            "data": {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    @staticmethod
    def error_event(message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """建立錯誤事件"""
        data = {
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        if details:
            data["details"] = details
        
        return {"event": "error", "data": data}
    
    @staticmethod
    def status_event(state: str, state_code: str, session_id: str,
                    message: Optional[str] = None) -> Dict[str, Any]:
        """建立狀態事件"""
        data = {
            "state": state,
            "state_code": state_code,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
        if message:
            data["message"] = message
        
        return {"event": "status", "data": data}
    
    @staticmethod
    def transcript_event(text: str, is_final: bool = False,
                        confidence: float = 0.95, language: str = "zh",
                        **extra) -> Dict[str, Any]:
        """建立轉譯事件"""
        return {
            "event": "transcript",
            "data": {
                "text": text,
                "is_final": is_final,
                "confidence": confidence,
                "language": language,
                "timestamp": datetime.now().isoformat(),
                **extra
            }
        }
    
    @staticmethod
    def action_event(action_type: str, session_id: str,
                    payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """建立動作事件"""
        return {
            "event": "action",
            "data": {
                "type": action_type,
                "session_id": session_id,
                "payload": payload or {},
                "timestamp": datetime.now().isoformat()
            }
        }