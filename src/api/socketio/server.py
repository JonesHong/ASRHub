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
from src.core.session_manager import SessionManager
from src.core.exceptions import APIError
from src.api.socketio.stream_manager import SocketIOStreamManager
from src.pipeline.manager import PipelineManager
from src.providers.manager import ProviderManager
from src.models.audio import AudioChunk, AudioFormat
from src.config.manager import ConfigManager


class SocketIOServer(APIBase):
    """
    Socket.io Server 實作
    支援事件驅動通訊、房間管理和廣播功能
    """
    
    def __init__(self, session_manager: SessionManager,
                 pipeline_manager: Optional[PipelineManager] = None,
                 provider_manager: Optional[ProviderManager] = None):
        """
        初始化 Socket.io 服務器
        使用 ConfigManager 獲取配置
        
        Args:
            session_manager: Session 管理器
            pipeline_manager: Pipeline 管理器
            provider_manager: Provider 管理器
        """
        # 從 ConfigManager 獲取配置
        config_manager = ConfigManager()
        sio_config = config_manager.api.socketio
        
        # 轉換為字典以兼容父類
        config_dict = sio_config.to_dict()
        super().__init__(config_dict, session_manager)
        
        self.pipeline_manager = pipeline_manager
        self.provider_manager = provider_manager
        self.host = sio_config.host
        self.port = sio_config.port
        
        # 初始化 logger
        self.logger = logger
        
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
        
        # 設定命名空間
        self.namespace = "/asr"
        
        # 註冊事件處理器
        self._register_event_handlers()
        
    def _register_event_handlers(self):
        """註冊 Socket.io 事件處理器"""
        
        @self.sio.event(namespace=self.namespace)
        async def connect(sid, environ):
            """處理客戶端連線"""
            await self._handle_connect(sid, environ)
            
        @self.sio.event(namespace=self.namespace)
        async def disconnect(sid):
            """處理客戶端斷線"""
            await self._handle_disconnect(sid)
            
        @self.sio.event(namespace=self.namespace)
        async def control(sid, data):
            """處理控制指令"""
            await self._handle_control_event(sid, data)
            
        @self.sio.event(namespace=self.namespace)
        async def audio_chunk(sid, data):
            """處理音訊資料"""
            await self._handle_audio_chunk_event(sid, data)
            
        @self.sio.event(namespace=self.namespace)
        async def subscribe(sid, data):
            """訂閱特定 session"""
            await self._handle_subscribe_event(sid, data)
            
        @self.sio.event(namespace=self.namespace)
        async def unsubscribe(sid, data):
            """取消訂閱"""
            await self._handle_unsubscribe_event(sid, data)
            
        @self.sio.event(namespace=self.namespace)
        async def ping(sid):
            """處理 ping"""
            await self.sio.emit('pong', namespace=self.namespace, to=sid)
            
    async def start(self):
        """啟動 Socket.io 服務器"""
        try:
            self._running = True
            
            # 建立 web runner
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            # 建立 TCP site
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            self.logger.info(f"Socket.io server started on {self.host}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start Socket.io server: {e}")
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
            
            self.logger.info("Socket.io server stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Socket.io server: {e}")
            
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
                'welcome',
                {
                    'sid': sid,
                    'version': '1.0',
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
            self.logger.info(f"New Socket.io connection: {sid}")
            
        except Exception as e:
            self.logger.error(f"Error handling connection: {e}")
            
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
            
            self.logger.info(f"Socket.io connection disconnected: {sid}")
            
        except Exception as e:
            self.logger.error(f"Error handling disconnect: {e}")
            
    async def _handle_control_event(self, sid: str, data: Dict[str, Any]):
        """
        處理控制事件
        
        Args:
            sid: Socket ID
            data: 控制資料
        """
        try:
            if sid not in self.connections:
                await self._emit_error(sid, "Connection not found")
                return
                
            connection = self.connections[sid]
            command = data.get("command")
            params = data.get("params", {})
            
            # 如果是 start 指令且沒有 session，建立新的
            if command == "start" and not connection.session_id:
                connection.session_id = str(uuid.uuid4())
                # 自動加入 session 房間
                await self._join_session_room(sid, connection.session_id)
                
            response = await self.handle_control_command(
                command=command,
                session_id=connection.session_id,
                params=params
            )
            
            # 發送回應
            await self.sio.emit(
                'control_response',
                {
                    'command': command,
                    'status': response.status,
                    'data': response.data,
                    'error': response.error,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
            # 廣播狀態更新到房間
            if command in ["start", "stop", "busy_start", "busy_end"]:
                await self._broadcast_status_to_room(connection.session_id)
                
        except Exception as e:
            self.logger.error(f"Error handling control event: {e}")
            await self._emit_error(sid, str(e))
            
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
            
            if not connection.session_id:
                await self._emit_error(sid, "No active session")
                return
                
            # 檢查 session 狀態
            session = self.session_manager.get_session(connection.session_id)
            if not session or session.state != "LISTENING":
                await self._emit_error(sid, "Session not in LISTENING state")
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
            if connection.session_id not in self.stream_manager.stream_buffers:
                audio_params = data.get("audio_params", {})
                self.stream_manager.create_stream(connection.session_id, audio_params)
                
                # 啟動處理任務
                asyncio.create_task(self._process_audio_stream(connection))
                
            # 添加到串流
            if self.stream_manager.add_audio_chunk(connection.session_id, audio_bytes):
                # 發送確認
                await self.sio.emit(
                    'audio_received',
                    {
                        'size': len(audio_bytes),
                        'chunk_id': data.get('chunk_id'),
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    to=sid
                )
                
                # 檢查背壓
                if self.stream_manager.implement_backpressure(connection.session_id):
                    await self.sio.emit(
                        'backpressure',
                        {'message': 'Audio buffer near capacity'},
                        namespace=self.namespace,
                        to=sid
                    )
            else:
                await self._emit_error(sid, "Failed to process audio chunk")
                
        except Exception as e:
            self.logger.error(f"Error handling audio chunk: {e}")
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
                'subscribed',
                {
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
            # 發送當前狀態
            session = self.session_manager.get_session(session_id)
            if session:
                await self.sio.emit(
                    'status_update',
                    {
                        'session_id': session_id,
                        'state': session.state,
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    to=sid
                )
                
        except Exception as e:
            self.logger.error(f"Error handling subscribe: {e}")
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
                'unsubscribed',
                {
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat()
                },
                namespace=self.namespace,
                to=sid
            )
            
        except Exception as e:
            self.logger.error(f"Error handling unsubscribe: {e}")
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
        
        self.logger.info(f"Socket {sid} joined room {room_name}")
        
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
            
        self.logger.info(f"Socket {sid} left room {room_name}")
        
    async def _broadcast_status_to_room(self, session_id: str):
        """
        廣播狀態到房間
        
        Args:
            session_id: Session ID
        """
        session = self.session_manager.get_session(session_id)
        if not session:
            return
            
        room_name = f"session_{session_id}"
        
        await self.sio.emit(
            'status_update',
            {
                'session_id': session_id,
                'state': session.state,
                'timestamp': datetime.now().isoformat()
            },
            namespace=self.namespace,
            room=room_name
        )
        
    async def _emit_error(self, sid: str, error_message: str):
        """
        發送錯誤訊息
        
        Args:
            sid: Socket ID
            error_message: 錯誤訊息
        """
        await self.sio.emit(
            'error',
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
                    'progress',
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
                self.logger.info(f"收集完成，共 {len(audio_chunks)} 個片段，總大小 {len(complete_audio)} bytes")
                
                # 呼叫實際的轉譯處理
                await self._transcribe_audio(connection, complete_audio, room_name)
            else:
                await self.sio.emit(
                    'error',
                    {
                        'error': '沒有收到音訊資料',
                        'timestamp': datetime.now().isoformat()
                    },
                    namespace=self.namespace,
                    room=room_name
                )
                
        except Exception as e:
            self.logger.error(f"Error processing audio stream: {e}")
            await self.sio.emit(
                'error',
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
                'partial_result',
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
                self.logger.info("開始轉換 WebM 音訊到 PCM 格式")
                try:
                    from src.utils.audio_converter import convert_webm_to_pcm
                    pcm_data = convert_webm_to_pcm(audio_data)
                    self.logger.info(f"音訊轉換成功: {len(audio_data)} bytes WebM -> {len(pcm_data)} bytes PCM")
                except Exception as e:
                    self.logger.error(f"音訊轉換失敗: {e}")
                    # 如果轉換失敗，無法處理
                    await self.sio.emit(
                        'error',
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
                from src.models.audio import AudioChunk, AudioFormat
                audio = AudioChunk(
                    data=pcm_data,
                    sample_rate=16000,  # 預設值，應該從前端參數獲取
                    channels=1,
                    format=AudioFormat.PCM  # 轉換後的格式
                )
                
                # 透過 Pipeline 處理音訊（如果有）
                processed_audio_data = pcm_data
                if self.pipeline_manager:
                    # 獲取預設 pipeline
                    pipeline = self.pipeline_manager.get_pipeline("default")
                    if pipeline:
                        # 處理音訊
                        processed_result = await pipeline.process(audio.data)
                        if processed_result:
                            processed_audio_data = processed_result
                
                # 使用 ProviderManager 的 transcribe 方法（支援池化）
                provider_name = self.provider_manager.default_provider
                self.logger.info(f"使用 {provider_name} 進行轉譯")
                
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
                        'final_result',
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
                        'error',
                        {
                            'error': final_text,
                            'timestamp': datetime.now().isoformat()
                        },
                        namespace=self.namespace,
                        room=room_name
                    )
            
            self.logger.info(f"轉譯完成: {final_text}")
            
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            await self.sio.emit(
                'error',
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
                                   params: Optional[Dict[str, Any]] = None) -> APIResponse:
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
            session = self.session_manager.get_session(session_id)
            
            if command == "start":
                if not session:
                    session = self.session_manager.create_session(session_id)
                self.session_manager.update_session_state(session_id, "LISTENING")
                return self.create_success_response(
                    {"status": "started", "session_id": session_id},
                    session_id
                )
                
            elif command == "stop":
                if session:
                    self.session_manager.update_session_state(session_id, "IDLE")
                    # 停止音訊串流
                    self.stream_manager.stop_stream(session_id)
                return self.create_success_response(
                    {"status": "stopped", "session_id": session_id},
                    session_id
                )
                
            elif command == "status":
                status = {
                    "session_id": session_id,
                    "state": session.state if session else "NO_SESSION",
                    "exists": session is not None,
                    "stream_active": self.stream_manager.is_stream_active(session_id)
                }
                return self.create_success_response(status, session_id)
                
            elif command == "busy_start":
                if session:
                    self.session_manager.update_session_state(session_id, "BUSY")
                return self.create_success_response(
                    {"status": "busy_started", "session_id": session_id},
                    session_id
                )
                
            elif command == "busy_end":
                if session:
                    self.session_manager.update_session_state(session_id, "LISTENING")
                return self.create_success_response(
                    {"status": "busy_ended", "session_id": session_id},
                    session_id
                )
                
            else:
                return self.create_error_response(f"Unknown command: {command}", session_id)
                
        except Exception as e:
            self.logger.error(f"Error handling command {command}: {e}")
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