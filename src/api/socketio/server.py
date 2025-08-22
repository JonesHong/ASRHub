"""
ASR Hub Socket.io Server 實作
支援事件驅動的即時通訊和房間管理
"""

import asyncio
import json
import socketio
from aiohttp import web
from typing import Dict, Any, Optional, AsyncGenerator, Set, List
import uuid
from datetime import datetime

from src.api.base import APIBase, APIResponse
from src.utils.logger import logger
from src.store import get_global_store
from src.store.sessions import sessions_actions, sessions_selectors
from src.store.sessions.sessions_actions import audio_metadata
from src.store.sessions.sessions_state import translate_fsm_state
from src.core.exceptions import APIError
from .routes import routes

# 模組級變數
store = get_global_store()
from src.api.socketio.stream_manager import SocketIOStreamManager
from src.providers.manager import ProviderManager
from src.audio import AudioChunk, AudioContainerFormat
from src.config.manager import ConfigManager

# 從 ConfigManager 獲取配置
config_manager = ConfigManager()
sio_config = config_manager.api.socketio

class SocketIOServer(APIBase):
    """
    Socket.io Server 實作
    支援事件驅動通訊、房間管理和廣播功能
    """
    
    def __init__(self, provider_manager: Optional[ProviderManager] = None):
        """
        初始化 Socket.io 服務器
        使用 ConfigManager 獲取配置
        
        Args:
            provider_manager: Provider 管理器
        """
        # 初始化父類
        super().__init__()
        
        # 获取全局 store 实例
        self.store = get_global_store()
        
        self.provider_manager = provider_manager
        self.host = sio_config.host
        self.port = sio_config.port
        
        
        # 建立 Socket.io 服務器
        self.sio = socketio.AsyncServer(
            async_mode='aiohttp',
            cors_allowed_origins='*',
            logger=False,  # 關閉內部日誌，使用我們自己的 logger
            engineio_logger=False
        )
        
        # 建立 aiohttp 應用
        self.app = web.Application()
        self.sio.attach(self.app)
        
        # 連線管理
        self.connections: Dict[str, SocketIOConnection] = {}
        self.session_rooms: Dict[str, Set[str]] = {}  # session_id -> Set[sid]
        
        # 串流管理器
        self.stream_manager = SocketIOStreamManager()
        
        # 添加分塊序號追蹤 (用於批次上傳)
        self.chunk_sequences: Dict[str, int] = {}
        
        # 設定命名空間
        self.namespace = "/asr"
        
        # 註冊事件處理器
        self._register_event_handlers()
        
    def _register_event_handlers(self):
        """註冊 Socket.io 事件處理器"""
        
        # 使用 setattr 動態註冊事件處理器，避免硬編碼
        async def handle_connect(sid, environ):
            """處理客戶端連線"""
            await self._handle_connect(sid, environ)
        self.sio.on(routes["CONNECT"], namespace=self.namespace)(handle_connect)
            
        async def handle_disconnect(sid):
            """處理客戶端斷線"""
            await self._handle_disconnect(sid)
        self.sio.on(routes["DISCONNECT"], namespace=self.namespace)(handle_disconnect)
            
        async def handle_audio_chunk(sid, data):
            """處理音訊資料"""
            await self._handle_audio_chunk_event(sid, data)
        self.sio.on(routes["AUDIO_CHUNK"], namespace=self.namespace)(handle_audio_chunk)
            
        async def handle_subscribe(sid, data):
            """訂閱特定 session"""
            await self._handle_subscribe_event(sid, data)
        self.sio.on(routes["SUBSCRIBE"], namespace=self.namespace)(handle_subscribe)
            
        async def handle_unsubscribe(sid, data):
            """取消訂閱"""
            await self._handle_unsubscribe_event(sid, data)
        self.sio.on(routes["UNSUBSCRIBE"], namespace=self.namespace)(handle_unsubscribe)
            
        async def handle_ping(sid):
            """處理 ping"""
            await self.sio.emit(routes["PONG"], namespace=self.namespace, to=sid)
        self.sio.on(routes["PING"], namespace=self.namespace)(handle_ping)
            
        # === Session 管理事件 ===
        async def handle_session_create(sid, data):
            """處理創建會話事件"""
            await self._handle_session_create(sid, data)
        self.sio.on(routes["SESSION_CREATE"], namespace=self.namespace)(handle_session_create)
        
        async def handle_session_start(sid, data):
            """處理開始監聽事件"""
            await self._handle_session_start(sid, data)
        self.sio.on(routes["SESSION_START"], namespace=self.namespace)(handle_session_start)
        
        async def handle_session_stop(sid, data):
            """處理停止監聽事件"""
            await self._handle_session_stop(sid, data)
        self.sio.on(routes["SESSION_STOP"], namespace=self.namespace)(handle_session_stop)
        
        async def handle_session_destroy(sid, data):
            """處理銷毀會話事件"""
            await self._handle_session_destroy(sid, data)
        self.sio.on(routes["SESSION_DESTROY"], namespace=self.namespace)(handle_session_destroy)
        
        # === 錄音管理事件 ===
        async def handle_recording_start(sid, data):
            """處理開始錄音事件"""
            await self._handle_recording_start(sid, data)
        self.sio.on(routes["RECORDING_START"], namespace=self.namespace)(handle_recording_start)
        
        async def handle_recording_end(sid, data):
            """處理結束錄音事件"""
            await self._handle_recording_end(sid, data)
        self.sio.on(routes["RECORDING_END"], namespace=self.namespace)(handle_recording_end)
        
        # === 上傳管理事件 ===
        async def handle_chunk_upload_start(sid, data):
            """處理開始分塊上傳事件"""
            await self._handle_chunk_upload_start(sid, data)
        self.sio.on(routes["CHUNK_UPLOAD_START"], namespace=self.namespace)(handle_chunk_upload_start)
        
        async def handle_chunk_upload_done(sid, data):
            """處理完成分塊上傳事件"""
            await self._handle_chunk_upload_done(sid, data)
        self.sio.on(routes["CHUNK_UPLOAD_DONE"], namespace=self.namespace)(handle_chunk_upload_done)
        
        async def handle_file_upload(sid, data):
            """處理檔案上傳事件"""
            await self._handle_file_upload(sid, data)
        self.sio.on(routes["FILE_UPLOAD"], namespace=self.namespace)(handle_file_upload)
        
        async def handle_file_upload_done(sid, data):
            """處理檔案上傳完成事件"""
            await self._handle_file_upload_done(sid, data)
        self.sio.on(routes["FILE_UPLOAD_DONE"], namespace=self.namespace)(handle_file_upload_done)
        
        # === 音訊元資料事件 ===
        async def handle_audio_metadata(sid, data):
            """處理音訊元資料事件"""
            await self._handle_audio_metadata(sid, data)
        self.sio.on("audio/metadata", namespace=self.namespace)(handle_audio_metadata)
            
    async def start(self):
        """啟動 Socket.io 服務器"""
        try:
            logger.info(f"正在啟動 Socket.IO 服務器在 {self.host}:{self.port}...")
            
            # 建立 web runner
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            # 建立 TCP site
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            # 只有在成功啟動後才設置 _running
            self._running = True
            logger.success(f"✅ Socket.IO 服務器成功啟動在 {self.host}:{self.port}")
            
            # 啟動 PyStoreX 事件監聽任務
            asyncio.create_task(self._listen_store_events())
            logger.debug("PyStoreX 事件監聽任務已啟動")
            
        except OSError as e:
            if e.errno == 48:  # Address already in use
                logger.error(f"❌ Port {self.port} 已被佔用，Socket.IO 服務器無法啟動")
            else:
                logger.error(f"❌ Socket.IO 服務器啟動失敗 (OSError): {e}")
            self._running = False
            raise
        except Exception as e:
            logger.error(f"❌ Socket.IO 服務器啟動失敗: {e}")
            self._running = False
            raise
            
    async def stop(self):
        """停止 Socket.io 服務器"""
        try:
            self._running = False
            
            # 斷開所有連線
            for sid in list(self.connections.keys()):
                await self._handle_disconnect(sid)
                
            # 停止 site
            if hasattr(self, 'site'):
                await self.site.stop()
                
            # 清理 runner
            if hasattr(self, 'runner'):
                await self.runner.cleanup()
            
            logger.info("Socket.io server stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Socket.io server: {e}")
            
    async def _handle_connect(self, sid: str, environ: Dict[str, Any]):
        """
        處理新連線
        
        Args:
            sid: Socket ID
            environ: 環境資訊
        """
        try:
            # 建立連線資訊
            connection = SocketIOConnection(
                sid=sid,
                session_id=None,
                connected_at=datetime.now(),
                rooms=set()
            )
            
            self.connections[sid] = connection
            
            # 發送歡迎訊息
            await self.sio.emit(
                routes["WELCOME"],
                {
                    'sid': sid,
                    'version': '1.0',
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
            logger.info(f"New Socket.io connection: {sid}")
            
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
            
    async def _handle_disconnect(self, sid: str):
        """
        處理斷線
        
        Args:
            sid: Socket ID
        """
        try:
            if sid not in self.connections:
                return
                
            connection = self.connections[sid]
            
            # 離開所有房間
            for room in connection.rooms:
                await self.sio.leave_room(sid, room, namespace=self.namespace)
                
            # 從 session 房間移除
            if connection.session_id:
                if connection.session_id in self.session_rooms:
                    self.session_rooms[connection.session_id].discard(sid)
                    if not self.session_rooms[connection.session_id]:
                        del self.session_rooms[connection.session_id]
                        
                # 清理串流
                self.stream_manager.cleanup_stream(connection.session_id)
                
            # 移除連線記錄
            del self.connections[sid]
            
            logger.info(f"Socket.io connection disconnected: {sid}")
            
        except Exception as e:
            logger.error(f"Error handling disconnect: {e}")
            
    # ========== Session 管理 Handlers ==========
    
    async def _handle_audio_chunk_event(self, sid: str, data: Dict[str, Any]):
        """
        處理音訊資料事件
        
        Args:
            sid: Socket ID
            data: 音訊資料
        """
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            
            # 允許從 data 中獲取 session_id (批次上傳模式)
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID provided")
                return
                
            # 更新 connection 的 session_id
            if not connection.session_id:
                connection.session_id = session_id
                
            # 使用 selector 檢查 session 狀態
            state = self.store.state if self.store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            
            # 如果 session 不存在且不是批次上傳模式，則創建 session
            if not session and not data.get("batch_mode", True):  # 默認為批次模式
                logger.info(f"Socket.IO: Session {session_id} not found, creating new session for batch upload")
                self.store.dispatch(sessions_actions.create_session(session_id, "batch"))
                # 重新獲取 session 狀態
                state = self.store.state if self.store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
            if not session:
                await self._emit_error(sid, f"Failed to create or find session {session_id}")
                return
                
            # 處理音訊資料
            audio_data = data.get("audio")
            audio_format = data.get("format", "base64")
            
            if audio_format == "base64":
                import base64
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data
                
            # 建立串流（如果不存在）
            if session_id not in self.stream_manager.stream_buffers:
                # 批次上傳模式：不需要音訊配置，使用預設值
                # 音訊配置會在後續的 metadata 或實際處理時確定
                default_audio_config = {
                    "sample_rate": 16000,
                    "channels": 1,
                    "encoding": "linear16",  # 使用小寫以匹配 AudioEncoding 枚舉
                    "bits_per_sample": 16
                }
                
                # 如果連線有音訊配置，使用它；否則使用預設值
                audio_config = getattr(connection, 'audio_config', None) or default_audio_config
                
                # 使用音訊配置
                self.stream_manager.create_stream(session_id, audio_config)
                
                # 批次上傳模式不啟動處理任務，等待 chunk_upload_done
                # 只有在非批次模式才啟動處理任務
                if not data.get("batch_mode", False):
                    asyncio.create_task(self._process_audio_stream(connection))
                
            # 獲取 chunk_id（如果有的話）
            chunk_id = data.get("chunk_id")
            
            # 驗證分塊序號 (類似 WebSocket 實現)
            if chunk_id is not None:
                if session_id not in self.chunk_sequences:
                    self.chunk_sequences[session_id] = 0
                expected_id = self.chunk_sequences.get(session_id, 0)
                if chunk_id != expected_id:
                    logger.warning(
                        f"🚨 Chunk sequence mismatch for session {session_id}: "
                        f"expected {expected_id}, got {chunk_id}. This may cause format detection issues."
                    )
                    # 更新期望序號以繼續處理（容錯機制）
                    self.chunk_sequences[session_id] = chunk_id + 1
                else:
                    logger.info(f"Socket.IO: ✅ Chunk {chunk_id} received in correct order for session {session_id}")
                    self.chunk_sequences[session_id] = chunk_id + 1
            
            # 直接添加音訊數據到串流管理器
            # stream_manager 會在內部創建正確的 AudioChunk
            add_success = self.stream_manager.add_audio_chunk(session_id, audio_bytes, chunk_id)
                
            # 添加到串流
            if add_success:
                # 批次上傳模式：同時推送到 AudioQueueManager
                # 這樣 SessionEffects 在 chunk_upload_done 時才能獲取到數據
                from src.core.audio_queue_manager import get_audio_queue_manager
                audio_queue_manager = get_audio_queue_manager()
                
                # 確保 AudioQueueManager 有這個 session 的隊列
                queue = audio_queue_manager.get_queue(session_id)
                if not queue:
                    await audio_queue_manager.create_queue(session_id)
                    logger.debug(f"Created audio queue for session {session_id}")
                
                # 推送音訊數據到 AudioQueueManager
                await audio_queue_manager.push(session_id, audio_bytes)
                logger.debug(f"Pushed {len(audio_bytes)} bytes to AudioQueueManager for session {session_id}")
                
                # 分發 audio_chunk_received action (類似 WebSocket 實現)
                chunk_size = len(audio_bytes)
                self.store.dispatch(sessions_actions.audio_chunk_received(session_id, chunk_size))
                logger.info(f"Socket.IO: 📦 Received audio chunk {chunk_id}, size={chunk_size} bytes, session={session_id}")
                
                # 發送確認
                await self.sio.emit(
                    routes["AUDIO_RECEIVED"],
                    {
                        'size': len(audio_bytes),
                        'chunk_id': data.get('chunk_id'),
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    to=sid
                )
                
                # 檢查背壓
                if self.stream_manager.implement_backpressure(session_id):
                    await self.sio.emit(
                        routes["BACKPRESSURE"],
                        {'message': 'Audio buffer near capacity'},
                        namespace=self.namespace,
                        to=sid
                    )
            else:
                await self._emit_error(sid, "Failed to process audio chunk")
                
        except Exception as e:
            logger.error(f"Error handling audio chunk: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_subscribe_event(self, sid: str, data: Dict[str, Any]):
        """
        處理訂閱事件
        
        Args:
            sid: Socket ID
            data: 訂閱資料
        """
        try:
            session_id = data.get("session_id")
            if not session_id:
                await self._emit_error(sid, "No session_id provided")
                return
                
            # 加入房間
            await self._join_session_room(sid, session_id)
            
            # 發送確認
            await self.sio.emit(
                routes["SUBSCRIBED"],
                {
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
            # 使用 selector 發送當前狀態
            state = self.store.state if self.store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            if session:
                current_state = session.get("fsm_state", "IDLE")
                await self.sio.emit(
                    routes["STATUS_UPDATE"],
                    {
                        'session_id': session_id,
                        'state': translate_fsm_state(current_state),
                        'state_code': current_state,
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    to=sid
                )
                
        except Exception as e:
            logger.error(f"Error handling subscribe: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_unsubscribe_event(self, sid: str, data: Dict[str, Any]):
        """
        處理取消訂閱事件
        
        Args:
            sid: Socket ID
            data: 取消訂閱資料
        """
        try:
            session_id = data.get("session_id")
            if not session_id:
                await self._emit_error(sid, "No session_id provided")
                return
                
            # 離開房間
            await self._leave_session_room(sid, session_id)
            
            # 發送確認
            await self.sio.emit(
                routes["UNSUBSCRIBED"],
                {
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling unsubscribe: {e}")
            await self._emit_error(sid, str(e))
            
    async def _join_session_room(self, sid: str, session_id: str):
        """
        加入 session 房間
        
        Args:
            sid: Socket ID
            session_id: Session ID
        """
        room_name = f"session_{session_id}"
        await self.sio.enter_room(sid, room_name, namespace=self.namespace)
        
        # 更新連線資訊
        if sid in self.connections:
            self.connections[sid].rooms.add(room_name)
            
        # 更新 session 房間記錄
        if session_id not in self.session_rooms:
            self.session_rooms[session_id] = set()
        self.session_rooms[session_id].add(sid)
        
        logger.info(f"Socket {sid} joined room {room_name}")
        
    async def _leave_session_room(self, sid: str, session_id: str):
        """
        離開 session 房間
        
        Args:
            sid: Socket ID
            session_id: Session ID
        """
        room_name = f"session_{session_id}"
        await self.sio.leave_room(sid, room_name, namespace=self.namespace)
        
        # 更新連線資訊
        if sid in self.connections:
            self.connections[sid].rooms.discard(room_name)
            
        # 更新 session 房間記錄
        if session_id in self.session_rooms:
            self.session_rooms[session_id].discard(sid)
            
        logger.info(f"Socket {sid} left room {room_name}")
        
    async def _listen_store_events(self):
        """
        監聽 PyStoreX store 事件
        """
        if not self.store:
            logger.warning("No store available for event listening")
            return
            
        last_state = {}
        
        while self._running:
            try:
                current_state = self.store.state if self.store else {}
                
                # 檢查 sessions 狀態變化
                if 'sessions' in current_state:
                    current_sessions = current_state['sessions'].get('sessions', {})
                    last_sessions = last_state.get('sessions', {}).get('sessions', {})
                    
                    # 檢查每個 session 的狀態變化
                    for session_id, session_data in current_sessions.items():
                        last_session = last_sessions.get(session_id, {})
                        
                        # 檢查轉譯結果（修復字段名稱不匹配問題）
                        current_transcription = session_data.get('transcription')
                        last_transcription = last_session.get('transcription')
                        if current_transcription != last_transcription:
                            logger.block("Transcription Result Detected", [
                                f"🔔 Session: {session_id[:8]}...",
                                f"📝 Result: {str(current_transcription)[:50]}...",
                                f"🚀 Broadcasting to room..."
                            ])
                            if current_transcription:
                                # 廣播轉譯結果到房間
                                await self._broadcast_transcription_result(session_id, current_transcription)
                                
                        # 檢查狀態變化（修復字段名稱不匹配問題 - 使用 fsm_state）
                        if session_data.get('fsm_state') != last_session.get('fsm_state'):
                            logger.debug(f"State change detected for session {session_id}: {last_session.get('fsm_state')} -> {session_data.get('fsm_state')}")
                            await self._broadcast_status_to_room(session_id)
                            
                last_state = current_state
                await asyncio.sleep(0.1)  # 每 100ms 檢查一次
                
            except Exception as e:
                logger.error(f"Error in store event listener: {e}")
                await asyncio.sleep(1)
    
    async def _broadcast_transcription_result(self, session_id: str, result: Any):
        """
        廣播轉譯結果到房間
        
        Args:
            session_id: Session ID
            result: 轉譯結果
        """
        room_name = f"session_{session_id}"
        
        # 將 immutables.Map 轉換為可序列化的 dict
        serializable_result = self._convert_immutable_to_dict(result)
        
        # 準備轉譯結果數據 - 與 WebSocket 格式保持一致
        transcription_data = {
            'session_id': session_id,
            'result': serializable_result if isinstance(serializable_result, dict) else {'text': str(serializable_result)},
            'timestamp': datetime.now().isoformat()
        }
        
        # 發送轉譯完成事件到房間
        await self.sio.emit(
            routes["TRANSCRIPT"],
            transcription_data,
            namespace=self.namespace,
            room=room_name
        )
        
        # 也直接發送給所有與此 session 相關的連線
        for sid, connection in self.connections.items():
            if connection.session_id == session_id:
                await self.sio.emit(
                    routes["TRANSCRIPT"],
                    transcription_data,
                    namespace=self.namespace,
                    to=sid
                )
        
        # 向後兼容：也發送 final_result 事件
        if isinstance(serializable_result, dict):
            text = serializable_result.get('text', '')
        else:
            text = str(serializable_result)
            
        await self.sio.emit(
            routes["TRANSCRIPT"],
            {
                'text': text,
                'is_final': True,
                'confidence': 0.95,
                'timestamp': datetime.now().isoformat()
            },
            namespace=self.namespace,
            room=room_name
        )
        
        logger.info(f"Socket.IO: Broadcasted transcription result for session {session_id}")
    
    def _convert_immutable_to_dict(self, obj):
        """
        遞歸地將所有不可變物件轉換為可序列化的 Python 物件
        
        Args:
            obj: 要轉換的物件（可能包含 immutables.Map、immutables.List 等）
            
        Returns:
            完全可序列化的 Python 物件
        """
        # 處理 immutables.Map
        if hasattr(obj, 'items') and hasattr(obj, '__class__') and 'Map' in str(obj.__class__):
            return {key: self._convert_immutable_to_dict(value) for key, value in obj.items()}
        
        # 處理 immutables.List 或其他序列類型
        elif hasattr(obj, '__iter__') and hasattr(obj, '__class__') and ('List' in str(obj.__class__) or 'Vector' in str(obj.__class__)):
            return [self._convert_immutable_to_dict(item) for item in obj]
        
        # 處理 tuple (可能來自 immutable 轉換)
        elif isinstance(obj, tuple):
            return [self._convert_immutable_to_dict(item) for item in obj]
        
        # 處理標準 dict
        elif isinstance(obj, dict):
            return {key: self._convert_immutable_to_dict(value) for key, value in obj.items()}
        
        # 處理標準 list
        elif isinstance(obj, list):
            return [self._convert_immutable_to_dict(item) for item in obj]
        
        # 處理其他有 to_dict 方法的物件
        elif hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
            return self._convert_immutable_to_dict(obj.to_dict())
        
        # 處理日期時間物件
        elif hasattr(obj, 'isoformat'):
            return obj.isoformat()
        
        # 處理 Enum
        elif hasattr(obj, 'value'):
            return obj.value
        
        # 原始類型直接返回
        else:
            return obj
    
    async def _broadcast_status_to_room(self, session_id: str):
        """
        廣播狀態到房間
        
        Args:
            session_id: Session ID
        """
        # 使用 selector 獲取 session
        state = self.store.state if self.store else None
        session = sessions_selectors.get_session(session_id)(state) if state else None
        if not session:
            return
            
        room_name = f"session_{session_id}"
        
        current_state = session.get("fsm_state", "IDLE")
        await self.sio.emit(
            routes["STATUS_UPDATE"],
            {
                'session_id': session_id,
                'state': translate_fsm_state(current_state),
                'state_code': current_state,
                'timestamp': datetime.now().isoformat()
            },
            namespace=self.namespace,
            room=room_name
        )
        
    # === 新增獨立的事件處理器 ===
    
    async def _handle_session_create(self, sid: str, data: Dict[str, Any]):
        """處理創建會話事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            # 優先使用前端提供的 session_id，確保 ID 一致性
            session_id = payload.get("session_id")
            
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.info(f"Socket.IO: Generated new session ID: {session_id}")
            else:
                logger.info(f"Socket.IO: Using frontend-provided session ID: {session_id}")
                
            # 更新連線的 session_id
            connection.session_id = session_id
            
            # 分發 action 到 store，使用 batch 策略
            strategy = payload.get("strategy", "batch").lower()
            self.store.dispatch(sessions_actions.create_session(session_id, strategy))
            logger.info(f"Socket.IO: Created session {session_id} with strategy: {strategy}")
            
            # 發送確認
            await self.sio.emit(
                routes["SESSION_CREATE"],
                {
                    'status': 'created',
                    'session_id': session_id,
                    'strategy': strategy,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling session create: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_session_start(self, sid: str, data: Dict[str, Any]):
        """處理開始監聽事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 更新連線的 session_id
            connection.session_id = session_id
            
            # 檢查音訊配置
            audio_config = payload.get("audio_config", {})
            if audio_config:
                self.store.dispatch(sessions_actions.update_audio_config(session_id, audio_config))
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.start_listening(session_id))
            logger.info(f"Socket.IO: Started listening for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["SESSION_START"],
                {
                    'status': 'listening',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling session start: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_session_stop(self, sid: str, data: Dict[str, Any]):
        """處理停止監聽事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.stop(session_id))
            logger.info(f"Socket.IO: Stopped listening for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["SESSION_STOP"],
                {
                    'status': 'stopped',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling session stop: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_session_destroy(self, sid: str, data: Dict[str, Any]):
        """處理銷毀會話事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.destroy_session(session_id))
            logger.info(f"Socket.IO: Destroyed session {session_id}")
            
            # 清理連線的 session_id
            connection.session_id = None
            
            # 發送確認
            await self.sio.emit(
                routes["SESSION_DESTROY"],
                {
                    'status': 'destroyed',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling session destroy: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_recording_start(self, sid: str, data: Dict[str, Any]):
        """處理開始錄音事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.start_recording(session_id))
            logger.info(f"Socket.IO: Started recording for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["RECORDING_START"],
                {
                    'status': 'recording',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling recording start: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_recording_end(self, sid: str, data: Dict[str, Any]):
        """處理結束錄音事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.end_recording(session_id))
            logger.info(f"Socket.IO: Ended recording for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["RECORDING_END"],
                {
                    'status': 'ended',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling recording end: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_chunk_upload_start(self, sid: str, data: Dict[str, Any]):
        """處理開始分塊上傳事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            # 優先使用前端提供的 session_id
            session_id = payload.get("session_id")
            
            if not session_id:
                # 如果前端沒有提供，嘗試使用連線的 session_id
                session_id = connection.session_id
                
            if not session_id:
                # 最後選擇：生成新的 session_id
                session_id = str(uuid.uuid4())
                logger.info(f"Socket.IO: Generated new session ID for chunk upload: {session_id}")
            else:
                logger.info(f"Socket.IO: Using session ID for chunk upload: {session_id}")
                
            # 更新連線的 session_id
            connection.session_id = session_id
                
            # 重置分塊序號
            self.chunk_sequences[session_id] = 0
            
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.chunk_upload_start(session_id))
            logger.info(f"Socket.IO: Started chunk upload for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["CHUNK_UPLOAD_START"],
                {
                    'status': 'ready',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling chunk upload start: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_chunk_upload_done(self, sid: str, data: Dict[str, Any]):
        """處理完成分塊上傳事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.chunk_upload_done(session_id))
            logger.info(f"Socket.IO: Completed chunk upload for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["CHUNK_UPLOAD_DONE"],
                {
                    'status': 'processing',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling chunk upload done: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_file_upload(self, sid: str, data: Dict[str, Any]):
        """處理檔案上傳事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                session_id = str(uuid.uuid4())
                connection.session_id = session_id
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.upload_file(session_id))
            logger.info(f"Socket.IO: File upload for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["FILE_UPLOAD"],
                {
                    'status': 'uploading',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling file upload: {e}")
            await self._emit_error(sid, str(e))
            
    async def _handle_file_upload_done(self, sid: str, data: Dict[str, Any]):
        """處理檔案上傳完成事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "No session ID")
                return
                
            # 分發 action 到 store
            self.store.dispatch(sessions_actions.upload_file_done(session_id))
            logger.info(f"Socket.IO: File upload done for session {session_id}")
            
            # 發送確認
            await self.sio.emit(
                routes["FILE_UPLOAD_DONE"],
                {
                    'status': 'completed',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling file upload done: {e}")
            await self._emit_error(sid, str(e))
    
    async def _handle_audio_metadata(self, sid: str, data: Dict[str, Any]):
        """處理音訊元資料事件"""
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            payload = data.get("payload", {})
            session_id = payload.get("session_id") or connection.session_id
            
            if not session_id:
                await self._emit_error(sid, "Session ID is required for audio metadata")
                return
            
            # 提取元資料 - 前端發送的是 audio_metadata
            metadata = payload.get("audio_metadata", {})
            
            logger.info(f"Socket.IO: Received audio metadata for session {session_id}")
            logger.debug(f"Metadata: {metadata}")
            
            # 分發 audio metadata 事件到 store
            self.store.dispatch(
                audio_metadata(
                    session_id=session_id,
                    audio_metadata=metadata  # 使用正確的參數名
                )
            )
            
            # 發送確認
            await self.sio.emit(
                "audio/metadata",
                {
                    'status': 'received',
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            logger.error(f"Error handling audio metadata: {e}")
            await self._emit_error(sid, str(e))
    
    # === 輔助方法 ===
    
    async def _emit_error(self, sid: str, error_message: str):
        """
        發送錯誤訊息
        
        Args:
            sid: Socket ID
            error_message: 錯誤訊息
        """
        await self.sio.emit(
            routes["ERROR"],
            {
                'error': error_message,
                'timestamp': datetime.now().isoformat()
            },
            namespace=self.namespace,
            to=sid
        )
        
    async def _process_audio_stream(self, connection: 'SocketIOConnection'):
        """
        處理音訊串流
        
        Args:
            connection: Socket.io 連線
        """
        if not connection.session_id:
            return
            
        room_name = f"session_{connection.session_id}"
        
        try:
            # 收集所有音訊片段
            audio_chunks = []
            chunk_count = 0
            
            # 獲取音訊串流
            async for audio_chunk in self.stream_manager.get_audio_stream(connection.session_id):
                # audio_chunk 是 AudioChunk 物件，需要取出 data
                audio_chunks.append(audio_chunk.data)
                chunk_count += 1
                
                # 發送進度更新
                await self.sio.emit(
                    routes["PROGRESS"],
                    {
                        'percent': 50,
                        'message': f'接收音訊片段 {chunk_count}',
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    room=room_name
                )
            
            if audio_chunks:
                # 合併所有音訊片段
                complete_audio = b''.join(audio_chunks)
                logger.info(f"收集完成，共 {len(audio_chunks)} 個片段，總大小 {len(complete_audio)} bytes")
                
                # 呼叫實際的轉譯處理
                await self._transcribe_audio(connection, complete_audio, room_name)
            else:
                await self.sio.emit(
                    routes["ERROR"],
                    {
                        'error': '沒有收到音訊資料',
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    room=room_name
                )
                
        except Exception as e:
            logger.error(f"Error processing audio stream: {e}")
            await self.sio.emit(
                routes["ERROR"],
                {
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                room=room_name
            )
        finally:
            # 清理串流
            self.stream_manager.cleanup_stream(connection.session_id)
    
    async def _transcribe_audio(self, connection: 'SocketIOConnection', audio_data: bytes, room_name: str):
        """
        執行語音轉文字
        
        Args:
            connection: Socket.io 連線
            audio_data: 完整的音訊資料
            room_name: 房間名稱
        """
        try:
            # 發送開始轉譯訊息
            await self.sio.emit(
                routes["TRANSCRIBE_START"],
                {
                    'text': '正在進行語音辨識...',
                    'is_final': False,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                room=room_name
            )
            
            if not self.provider_manager:
                # 如果沒有 provider manager，使用模擬結果
                await asyncio.sleep(1)
                final_text = f"[模擬] 收到 {len(audio_data)} bytes 的音訊"
            else:
                # 先將 WebM 轉換為 PCM
                logger.info("開始轉換 WebM 音訊到 PCM 格式")
                try:
                    from src.audio.converter import AudioConverter
                    pcm_data = AudioConverter.convert_webm_to_pcm(audio_data)
                    logger.info(f"音訊轉換成功: {len(audio_data)} bytes WebM -> {len(pcm_data)} bytes PCM")
                except Exception as e:
                    logger.error(f"音訊轉換失敗: {e}")
                    # 如果轉換失敗，無法處理
                    await self.sio.emit(
                        routes["ERROR"],
                        {
                            'error': "無法轉換音訊格式。請確保系統已安裝 FFmpeg。"
                                    "在 macOS 上可以使用 'brew install ffmpeg' 安裝 FFmpeg。",
                            'timestamp': datetime.now().isoformat()
                        },
                        namespace=self.namespace,
                        room=room_name
                    )
                    return
                
                # 建立 AudioChunk 物件
                from src.audio import AudioChunk, AudioContainerFormat, AudioEncoding
                audio = AudioChunk(
                    data=pcm_data,
                    sample_rate=config_manager.pipeline.default_sample_rate,  # 從配置讀取
                    channels=config_manager.pipeline.channels,               # 從配置讀取
                    format=AudioContainerFormat.PCM,  # 轉換後的格式
                    encoding=AudioEncoding.LINEAR16,  # PCM 使用 LINEAR16 編碼
                    bits_per_sample=16  # 16 位元深度
                )
                
                # Pipeline 功能已移除，直接使用 pcm_data
                processed_audio_data = pcm_data
                
                # 使用 ProviderManager 的 transcribe 方法（支援池化）
                provider_name = self.provider_manager.default_provider
                logger.info(f"使用 {provider_name} 進行轉譯")
                
                # 執行轉譯
                result = await self.provider_manager.transcribe(
                    audio_data=processed_audio_data,
                    provider_name=provider_name,
                    language="zh"  # 預設中文，應該從配置獲取
                )
                
                # 發送最終結果
                if result and result.text:
                    final_text = result.text
                    
                    await self.sio.emit(
                        routes["TRANSCRIPT"],
                        {
                            'text': final_text,
                            'is_final': True,
                            'confidence': result.confidence if hasattr(result, 'confidence') else 0.95,
                            'timestamp': datetime.now().isoformat()
                        },
                        namespace=self.namespace,
                        room=room_name
                    )
                else:
                    final_text = "無法辨識音訊內容"
                    await self.sio.emit(
                        routes["ERROR"],
                        {
                            'error': final_text,
                            'timestamp': datetime.now().isoformat()
                        },
                        namespace=self.namespace,
                        room=room_name
                    )
            
            logger.info(f"轉譯完成: {final_text}")
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            await self.sio.emit(
                routes["ERROR"],
                {
                    'error': f'轉譯錯誤: {str(e)}',
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                room=room_name
            )
            
    async def handle_control_command(self, 
                                   command: str, 
                                   session_id: str, 
                                   params: Optional[Dict[str, Any]] = None,
                                   connection: Optional['SocketIOConnection'] = None) -> APIResponse:
        """
        處理控制指令
        
        Args:
            command: 指令名稱
            session_id: Session ID
            params: 額外參數
            
        Returns:
            API 回應
        """
        try:
            # 使用 selector 獲取 session
            state = self.store.state if self.store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            
            if command == "start":
                if not session:
                    # 使用 Store dispatch 創建 session (不傳遞 audio_format)
                    self.store.dispatch(sessions_actions.create_session(session_id))
                
                # 檢查是否有音訊配置
                audio_format = None
                # 從參數或連線取得音訊格式
                if params and "audio_format" in params:
                    audio_format = params["audio_format"]
                elif connection and hasattr(connection, 'audio_config') and connection.audio_config:
                    # 從連線的 audio_config 轉換為 audio_format
                    audio_format = {
                        "sample_rate": connection.audio_config["sample_rate"],
                        "channels": connection.audio_config["channels"],
                        "encoding": connection.audio_config["encoding"].value if hasattr(connection.audio_config["encoding"], 'value') else connection.audio_config["encoding"],
                        "bits_per_sample": connection.audio_config["bits_per_sample"]
                    }
                
                # 使用 start_listening action 傳遞 audio_format
                self.store.dispatch(sessions_actions.start_listening(session_id, audio_format))
                
                return self.create_success_response(
                    {"status": "started", "session_id": session_id},
                    session_id
                )
                
            elif command == "stop":
                if session:
                    self.store.dispatch(sessions_actions.update_session_state(session_id, "IDLE"))
                    # 停止音訊串流
                    self.stream_manager.stop_stream(session_id)
                return self.create_success_response(
                    {"status": "stopped", "session_id": session_id},
                    session_id
                )
                
            elif command == "status":
                status = {
                    "session_id": session_id,
                    "state": session.get("fsm_state", "IDLE") if session else "NO_SESSION",  # 修復字段名稱不匹配
                    "exists": session is not None,
                    "stream_active": self.stream_manager.is_stream_active(session_id)
                }
                return self.create_success_response(status, session_id)
                
            elif command == "busy_start":
                if session:
                    self.store.dispatch(sessions_actions.update_session_state(session_id, "BUSY"))
                return self.create_success_response(
                    {"status": "busy_started", "session_id": session_id},
                    session_id
                )
                
            elif command == "busy_end":
                if session:
                    self.store.dispatch(sessions_actions.update_session_state(session_id, "LISTENING"))
                return self.create_success_response(
                    {"status": "busy_ended", "session_id": session_id},
                    session_id
                )
                
            else:
                return self.create_error_response(f"Unknown command: {command}", session_id)
                
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            return self.create_error_response(str(e), session_id)
            
    async def handle_transcribe(self, 
                              session_id: str, 
                              audio_data: bytes,
                              params: Optional[Dict[str, Any]] = None) -> APIResponse:
        """
        處理單次轉譯請求
        
        Args:
            session_id: Session ID
            audio_data: 音訊資料
            params: 額外參數
            
        Returns:
            API 回應
        """
        # TODO: 實作單次轉譯
        return self.create_error_response("Not implemented yet", session_id)
        
    async def handle_transcribe_stream(self, 
                                     session_id: str,
                                     audio_stream: AsyncGenerator[bytes, None],
                                     params: Optional[Dict[str, Any]] = None) -> AsyncGenerator[APIResponse, None]:
        """
        處理串流轉譯請求
        
        Args:
            session_id: Session ID
            audio_stream: 音訊串流
            params: 額外參數
            
        Yields:
            串流 API 回應
        """
        # TODO: 實作串流轉譯
        yield self.create_error_response("Not implemented yet", session_id)
        

class SocketIOConnection:
    """Socket.io 連線資訊"""
    
    def __init__(self, sid: str, session_id: Optional[str], 
                 connected_at: datetime, rooms: Set[str]):
        self.sid = sid
        self.session_id = session_id
        self.connected_at = connected_at
        self.last_activity = connected_at
        self.rooms = rooms
        self.audio_config = None  # 儲存音訊配置