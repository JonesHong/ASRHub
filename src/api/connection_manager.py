"""
統一的連線管理器
管理所有 API 協定的連線
"""

import asyncio
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

from src.utils.logger import logger
from src.core.exceptions import ConnectionError


class ConnectionType(Enum):
    """連線類型"""
    WEBSOCKET = "websocket"
    SOCKETIO = "socketio"
    HTTP_SSE = "http_sse"
    GRPC = "grpc"
    REDIS = "redis"


class ConnectionState(Enum):
    """連線狀態"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ConnectionInfo:
    """連線資訊"""
    connection_id: str
    connection_type: ConnectionType
    session_id: Optional[str] = None
    state: ConnectionState = ConnectionState.CONNECTING
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_activity(self):
        """更新最後活動時間"""
        self.last_activity = datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "connection_id": self.connection_id,
            "connection_type": self.connection_type.value,
            "session_id": self.session_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "metadata": self.metadata
        }


class ConnectionManager:
    """
    統一的連線管理器
    跨協定管理所有連線
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化連線管理器
        
        Args:
            config: 配置
        """
        self.config = config or {}
        
        # 連線儲存
        self.connections: Dict[str, ConnectionInfo] = {}
        
        # 按類型分組的連線
        self.connections_by_type: Dict[ConnectionType, Set[str]] = {
            conn_type: set() for conn_type in ConnectionType
        }
        
        # Session 到連線的映射
        self.session_connections: Dict[str, Set[str]] = {}
        
        # 連線限制
        self.max_connections = self.config.get("max_connections", 1000)
        self.max_connections_per_session = self.config.get("max_connections_per_session", 10)
        
        # 鎖
        self._lock = asyncio.Lock()
        
        # 健康檢查任務
        self._health_check_task = None
        self._running = False
        
    async def start(self):
        """啟動連線管理器"""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Connection manager started")
        
    async def stop(self):
        """停止連線管理器"""
        self._running = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
                
        # 清理所有連線
        await self.cleanup_all_connections()
        
        logger.info("Connection manager stopped")
        
    async def register_connection(self, 
                                connection_type: ConnectionType,
                                connection_id: Optional[str] = None,
                                session_id: Optional[str] = None,
                                metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        註冊新連線
        
        Args:
            connection_type: 連線類型
            connection_id: 連線 ID（可選，不提供則自動生成）
            session_id: Session ID（可選）
            metadata: 額外資訊
            
        Returns:
            連線 ID
            
        Raises:
            ConnectionError: 如果達到連線限制
        """
        async with self._lock:
            # 檢查連線限制
            if len(self.connections) >= self.max_connections:
                raise ConnectionError("Maximum connection limit reached")
                
            # 生成連線 ID
            if not connection_id:
                connection_id = str(uuid.uuid4())
                
            # 檢查 session 連線限制
            if session_id:
                session_conns = self.session_connections.get(session_id, set())
                if len(session_conns) >= self.max_connections_per_session:
                    raise ConnectionError(
                        f"Maximum connections per session limit reached for session {session_id}"
                    )
                    
            # 建立連線資訊
            connection_info = ConnectionInfo(
                connection_id=connection_id,
                connection_type=connection_type,
                session_id=session_id,
                state=ConnectionState.CONNECTED,
                metadata=metadata or {}
            )
            
            # 儲存連線
            self.connections[connection_id] = connection_info
            self.connections_by_type[connection_type].add(connection_id)
            
            # 更新 session 映射
            if session_id:
                if session_id not in self.session_connections:
                    self.session_connections[session_id] = set()
                self.session_connections[session_id].add(connection_id)
                
            logger.info(
                f"Registered {connection_type.value} connection: {connection_id}"
                f" for session: {session_id}"
            )
            
            return connection_id
            
    async def unregister_connection(self, connection_id: str):
        """
        取消註冊連線
        
        Args:
            connection_id: 連線 ID
        """
        async with self._lock:
            if connection_id not in self.connections:
                return
                
            connection_info = self.connections[connection_id]
            
            # 更新狀態
            connection_info.state = ConnectionState.DISCONNECTED
            
            # 從類型分組中移除
            self.connections_by_type[connection_info.connection_type].discard(connection_id)
            
            # 從 session 映射中移除
            if connection_info.session_id:
                if connection_info.session_id in self.session_connections:
                    self.session_connections[connection_info.session_id].discard(connection_id)
                    if not self.session_connections[connection_info.session_id]:
                        del self.session_connections[connection_info.session_id]
                        
            # 移除連線
            del self.connections[connection_id]
            
            logger.info(
                f"Unregistered {connection_info.connection_type.value} "
                f"connection: {connection_id}"
            )
            
    async def update_connection_session(self, connection_id: str, session_id: str):
        """
        更新連線的 session
        
        Args:
            connection_id: 連線 ID
            session_id: 新的 Session ID
        """
        async with self._lock:
            if connection_id not in self.connections:
                raise ConnectionError(f"Connection {connection_id} not found")
                
            connection_info = self.connections[connection_id]
            old_session_id = connection_info.session_id
            
            # 從舊 session 移除
            if old_session_id and old_session_id in self.session_connections:
                self.session_connections[old_session_id].discard(connection_id)
                if not self.session_connections[old_session_id]:
                    del self.session_connections[old_session_id]
                    
            # 添加到新 session
            connection_info.session_id = session_id
            if session_id not in self.session_connections:
                self.session_connections[session_id] = set()
            self.session_connections[session_id].add(connection_id)
            
            connection_info.update_activity()
            
            logger.info(
                f"Updated connection {connection_id} session: "
                f"{old_session_id} -> {session_id}"
            )
            
    async def get_connection_info(self, connection_id: str) -> Optional[ConnectionInfo]:
        """
        獲取連線資訊
        
        Args:
            connection_id: 連線 ID
            
        Returns:
            連線資訊
        """
        async with self._lock:
            return self.connections.get(connection_id)
            
    async def get_connections_by_session(self, session_id: str) -> List[ConnectionInfo]:
        """
        獲取 session 的所有連線
        
        Args:
            session_id: Session ID
            
        Returns:
            連線資訊列表
        """
        async with self._lock:
            connection_ids = self.session_connections.get(session_id, set())
            return [
                self.connections[conn_id] 
                for conn_id in connection_ids 
                if conn_id in self.connections
            ]
            
    async def get_connections_by_type(self, connection_type: ConnectionType) -> List[ConnectionInfo]:
        """
        獲取特定類型的所有連線
        
        Args:
            connection_type: 連線類型
            
        Returns:
            連線資訊列表
        """
        async with self._lock:
            connection_ids = self.connections_by_type.get(connection_type, set())
            return [
                self.connections[conn_id] 
                for conn_id in connection_ids 
                if conn_id in self.connections
            ]
            
    async def update_connection_state(self, connection_id: str, state: ConnectionState):
        """
        更新連線狀態
        
        Args:
            connection_id: 連線 ID
            state: 新狀態
        """
        async with self._lock:
            if connection_id in self.connections:
                self.connections[connection_id].state = state
                self.connections[connection_id].update_activity()
                
    async def update_connection_metadata(self, connection_id: str, metadata: Dict[str, Any]):
        """
        更新連線元資料
        
        Args:
            connection_id: 連線 ID
            metadata: 元資料
        """
        async with self._lock:
            if connection_id in self.connections:
                self.connections[connection_id].metadata.update(metadata)
                self.connections[connection_id].update_activity()
                
    async def cleanup_inactive_connections(self, timeout_seconds: int = 300):
        """
        清理不活躍的連線
        
        Args:
            timeout_seconds: 超時秒數
        """
        async with self._lock:
            now = datetime.now()
            inactive_connections = []
            
            for conn_id, conn_info in self.connections.items():
                if (now - conn_info.last_activity).total_seconds() > timeout_seconds:
                    inactive_connections.append(conn_id)
                    
            for conn_id in inactive_connections:
                await self.unregister_connection(conn_id)
                
            if inactive_connections:
                logger.info(f"Cleaned up {len(inactive_connections)} inactive connections")
                
    async def cleanup_all_connections(self):
        """清理所有連線"""
        async with self._lock:
            connection_ids = list(self.connections.keys())
            
            for conn_id in connection_ids:
                await self.unregister_connection(conn_id)
                
            self.connections.clear()
            self.session_connections.clear()
            for conn_set in self.connections_by_type.values():
                conn_set.clear()
                
    async def get_statistics(self) -> Dict[str, Any]:
        """
        獲取連線統計資訊
        
        Returns:
            統計資訊
        """
        async with self._lock:
            stats = {
                "total_connections": len(self.connections),
                "connections_by_type": {
                    conn_type.value: len(self.connections_by_type[conn_type])
                    for conn_type in ConnectionType
                },
                "total_sessions": len(self.session_connections),
                "sessions_with_multiple_connections": sum(
                    1 for conns in self.session_connections.values() if len(conns) > 1
                ),
                "connection_states": {}
            }
            
            # 統計連線狀態
            for conn_info in self.connections.values():
                state = conn_info.state.value
                stats["connection_states"][state] = stats["connection_states"].get(state, 0) + 1
                
            return stats
            
    async def _health_check_loop(self):
        """健康檢查循環"""
        while self._running:
            try:
                # 清理不活躍連線
                await self.cleanup_inactive_connections()
                
                # 記錄統計資訊
                stats = await self.get_statistics()
                logger.debug(f"Connection statistics: {stats}")
                
                # 每 60 秒檢查一次
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                
    def is_session_locked(self, session_id: str) -> bool:
        """
        檢查 session 是否被鎖定（用於防止並發修改）
        
        Args:
            session_id: Session ID
            
        Returns:
            是否被鎖定
        """
        # TODO: 實作 session 鎖定機制
        return False