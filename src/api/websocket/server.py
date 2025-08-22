"""
ASR Hub WebSocket Server 實作
處理 WebSocket 連線的即時雙向通訊
"""

import asyncio
import json
import websockets
from websockets.server import WebSocketServerProtocol
from typing import Dict, Any, Optional, AsyncGenerator, Set
import uuid
from datetime import datetime

from src.api.base import APIBase, APIResponse
from src.api.websocket.routes import routes
from src.utils.logger import logger
from src.store import get_global_store
from src.store.sessions import sessions_actions, sessions_selectors
from src.store.sessions.sessions_state import translate_fsm_state
from src.core.exceptions import APIError

# 模組級變數
store = get_global_store()
from src.api.websocket.stream_manager import WebSocketStreamManager
from src.providers.manager import ProviderManager
from src.audio import AudioChunk, AudioContainerFormat
from src.audio.converter import AudioConverter
from src.config.manager import ConfigManager


class WebSocketServer(APIBase):
    """
    WebSocket Server 實作
    支援即時雙向通訊和音訊串流處理
    """
    
    def __init__(self, provider_manager: Optional[ProviderManager] = None):
        """
        初始化 WebSocket 服務器
        使用 ConfigManager 獲取配置
        
        Args:
            provider_manager: Provider 管理器
        """
        # 初始化父類
        super().__init__()
        
        # 從 ConfigManager 獲取配置
        config_manager = ConfigManager()
        ws_config = config_manager.api.websocket
        
        self.host = ws_config.host
        self.port = ws_config.port
        self.server = None
        self.connections: Dict[str, WebSocketConnection] = {}
        self.stream_manager = WebSocketStreamManager()
        self.provider_manager = provider_manager
        # 添加分塊序號追蹤 (類似 SocketIO 實現)
        self.chunk_sequences: Dict[str, int] = {}
        
    async def start(self):
        """啟動 WebSocket 服務器"""
        try:
            logger.info(f"正在啟動 WebSocket 服務器在 {self.host}:{self.port}...")
            
            # websockets 15.x 版本只需要一個參數
            async def connection_handler(websocket):
                # 從 websocket 對象獲取 path
                path = websocket.path if hasattr(websocket, 'path') else '/'
                await self.handle_connection(websocket, path)
            
            # 嘗試啟動服務器
            self.server = await websockets.serve(
                connection_handler,
                self.host,
                self.port
            )
            
            # 只有在成功啟動後才設置 _running
            self._running = True
            logger.success(f"✅ WebSocket 服務器成功啟動在 {self.host}:{self.port}")
            
            # 啟動心跳檢查任務
            heartbeat_task = asyncio.create_task(self._heartbeat_task())
            logger.debug("心跳檢查任務已啟動")
            
            # 啟動 PyStoreX 事件監聽任務
            store_listener_task = asyncio.create_task(self._listen_store_events())
            logger.debug("PyStoreX 事件監聽任務已啟動")
            
        except OSError as e:
            if e.errno == 48:  # Address already in use
                logger.error(f"❌ Port {self.port} 已被佔用，WebSocket 服務器無法啟動")
            else:
                logger.error(f"❌ WebSocket 服務器啟動失敗 (OSError): {e}")
            self._running = False
            raise
        except Exception as e:
            logger.error(f"❌ WebSocket 服務器啟動失敗: {e}")
            self._running = False
            raise
    
    async def stop(self):
        """停止 WebSocket 服務器"""
        try:
            self._running = False
            
            # 關閉所有連線
            for conn_id in list(self.connections.keys()):
                await self._close_connection(conn_id)
            
            # 關閉服務器
            if self.server:
                self.server.close()
                await self.server.wait_closed()
                
            logger.info("WebSocket server stopped")
            
        except Exception as e:
            logger.error(f"Error stopping WebSocket server: {e}")
            
    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        處理新的 WebSocket 連線
        
        Args:
            websocket: WebSocket 連線
            path: 連線路徑
        """
        connection_id = str(uuid.uuid4())
        connection = WebSocketConnection(
            id=connection_id,
            websocket=websocket,
            session_id=None,
            connected_at=datetime.now()
        )
        
        self.connections[connection_id] = connection
        logger.info(f"New WebSocket connection: {connection_id}")
        
        # 強制輸出到 stderr 和檔案
        import sys
        sys.stderr.write(f"[WS DEBUG] Connection established: {connection_id}\n")
        sys.stderr.flush()
        
        # 寫入到檔案以確保訊息有被記錄
        with open("/tmp/websocket_debug.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - WebSocket connection: {connection_id}\n")
            f.flush()
        
        try:
            # 發送歡迎訊息
            from src.api.websocket.handlers import MessageBuilder
            await self._send_message(connection, MessageBuilder.build_welcome(connection_id))
            
            # 處理訊息
            logger.info(f"WebSocket {connection_id}: Starting message loop")
            async for message in websocket:
                # logger.info(f"WebSocket {connection_id}: Received raw message, type={type(message)}, length={len(message) if message else 0}")
                await self._handle_message(connection, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket connection closed: {connection_id}")
        except Exception as e:
            logger.error(f"Error handling connection {connection_id}: {e}")
        finally:
            await self._close_connection(connection_id)
            
    async def _handle_message(self, connection: 'WebSocketConnection', message: str | bytes):
        """
        處理接收到的訊息
        
        Args:
            connection: WebSocket 連線
            message: 訊息內容
        """
        try:
            # 處理二進位音訊資料
            if isinstance(message, bytes):
                if connection.session_id:
                    await self._handle_audio_data(connection, message)
                else:
                    await self._send_error(connection, "No active session")
                return
            
            # 處理 JSON 控制訊息
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await self._send_error(connection, "Invalid JSON format")
                return
                
            # 檢查事件欄位（WebSocket 使用 event 欄位來識別事件類型）
            event_type = data.get("event")
            
            if not event_type:
                await self._send_error(connection, "Missing event type")
                return
            
            # 提取實際的資料內容
            payload = data.get("data", {})
            
            # 路由到對應的 handler（新的獨立事件）
            if event_type == routes["SESSION_CREATE"]:
                await self._handle_session_create(connection, payload)
            elif event_type == routes["SESSION_START"]:
                await self._handle_session_start(connection, payload)
            elif event_type == routes["SESSION_STOP"]:
                await self._handle_session_stop(connection, payload)
            elif event_type == routes["SESSION_DESTROY"]:
                await self._handle_session_destroy(connection, payload)
            elif event_type == routes["RECORDING_START"]:
                await self._handle_recording_start(connection, payload)
            elif event_type == routes["RECORDING_END"]:
                await self._handle_recording_end(connection, payload)
            elif event_type == routes["CHUNK_UPLOAD_START"]:
                await self._handle_chunk_upload_start(connection, payload)
            elif event_type == routes["CHUNK_UPLOAD_DONE"]:
                await self._handle_chunk_upload_done(connection, payload)
            elif event_type == routes["FILE_UPLOAD"]:
                await self._handle_file_upload(connection, payload)
            elif event_type == routes["FILE_UPLOAD_DONE"]:
                await self._handle_file_upload_done(connection, payload)
            
            # 音訊處理事件
            elif event_type == routes["AUDIO_CHUNK"] or event_type == "chunk/data":
                await self._handle_audio_chunk_message(connection, payload)
            elif event_type == routes["AUDIO_CONFIG"]:
                await self._handle_audio_config(connection, payload)
            elif event_type == routes["AUDIO_METADATA"]:
                await self._handle_audio_metadata(connection, payload)
                
            # 控制指令
            elif event_type == routes["AUDIO"]:
                await self._handle_audio_json(connection, payload)
                
            # 系統事件
            elif event_type == routes["PING"]:
                await self._send_message(connection, {"type": routes["PONG"]})
            else:
                await self._send_error(connection, f"Unknown event type: {event_type}")
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self._send_error(connection, str(e))
            
    async def _handle_audio_data(self, connection: 'WebSocketConnection', audio_data: bytes):
        """
        處理音訊資料
        
        Args:
            connection: WebSocket 連線
            audio_data: 音訊資料
        """
        if not connection.session_id:
            await self._send_error(connection, "No active session for audio streaming")
            return
            
        try:
            # 使用 selector 檢查 session 狀態
            state = store.state if store else None
            session = sessions_selectors.get_session(connection.session_id)(state) if state else None
            if not session or session.get("state", "IDLE") != "LISTENING":
                await self._send_error(connection, "Session not in LISTENING state")
                return
                
            # 檢查是否已建立串流
            if connection.session_id not in self.stream_manager.stream_buffers:
                # 檢查連線是否有音訊配置
                if not hasattr(connection, 'audio_config') or connection.audio_config is None:
                    logger.error(f"連線 {connection.id} 沒有音訊配置, session_id: {connection.session_id}")
                    logger.debug(f"連線屬性: {[attr for attr in dir(connection) if not attr.startswith('_')]}")
                    await self._send_error(connection, "缺少音訊配置，請先發送 audio_config 訊息")
                    return
                    
                # 使用連線的音訊配置建立串流
                self.stream_manager.create_stream(connection.session_id, connection.audio_config)
                
                # 啟動串流處理任務
                asyncio.create_task(self._process_audio_stream(connection))
                
            # 檢查背壓
            if self.stream_manager.implement_backpressure(connection.session_id):
                await self._send_message(connection, {
                    "type": routes["BACKPRESSURE"],
                    "message": "Audio buffer near capacity, please slow down"
                })
                
            # 添加音訊資料到串流
            if self.stream_manager.add_audio_chunk(connection.session_id, audio_data):
                # 發送確認
                await self._send_message(connection, {
                    "type": routes["AUDIO_RECEIVED"],
                    "size": len(audio_data),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                await self._send_error(connection, "Failed to process audio chunk")
                
        except Exception as e:
            logger.error(f"Error handling audio data: {e}")
            await self._send_error(connection, str(e))
    
    # ========== Session 管理 Handlers ==========
    
    async def _handle_session_create(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理創建會話事件"""
        try:
            # data 現在直接是 payload (來自 {event, data} 結構)
            session_id = data.get("session_id") or str(uuid.uuid4())
            # 將 strategy 轉換為小寫以符合 FSMStrategy enum
            strategy = data.get("strategy", "batch").lower()
            
            connection.session_id = session_id
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.create_session(session_id, strategy))
            
            await self._send_message(connection, {
                "type": routes["SESSION_CREATE"],
                "payload": {"session_id": session_id, "status": "created"}
            })
            
            logger.info(f"Session created: {session_id}")
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            await self._send_error(connection, f"Failed to create session: {str(e)}")
    
    async def _handle_session_start(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理開始監聽事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            audio_format = data.get("audio_format", "pcm")
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.start_listening(session_id, audio_format))
            
            await self._send_message(connection, {
                "type": routes["SESSION_START"],
                "payload": {"session_id": session_id, "status": "listening"}
            })
            
            logger.info(f"Session started listening: {session_id}")
            
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            await self._send_error(connection, f"Failed to start session: {str(e)}")
    
    async def _handle_session_stop(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理停止監聽事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.stop_listening(session_id))
            
            await self._send_message(connection, {
                "type": routes["SESSION_STOP"],
                "payload": {"session_id": session_id, "status": "stopped"}
            })
            
            logger.info(f"Session stopped: {session_id}")
            
        except Exception as e:
            logger.error(f"Error stopping session: {e}")
            await self._send_error(connection, f"Failed to stop session: {str(e)}")
    
    async def _handle_session_destroy(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理銷毀會話事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.destroy_session(session_id))
            
            if connection.session_id == session_id:
                connection.session_id = None
            
            await self._send_message(connection, {
                "type": routes["SESSION_DESTROY"],
                "payload": {"session_id": session_id, "status": "destroyed"}
            })
            
            logger.info(f"Session destroyed: {session_id}")
            
        except Exception as e:
            logger.error(f"Error destroying session: {e}")
            await self._send_error(connection, f"Failed to destroy session: {str(e)}")
    
    # ========== 錄音管理 Handlers ==========
    
    async def _handle_recording_start(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理開始錄音事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            strategy = data.get("strategy", "non_streaming").lower()
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.start_recording(session_id, strategy))
            
            await self._send_message(connection, {
                "type": routes["RECORDING_START"],
                "payload": {"session_id": session_id, "status": "recording"}
            })
            
            logger.info(f"Recording started: {session_id}")

            
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            await self._send_error(connection, f"Failed to start recording: {str(e)}")
    
    async def _handle_recording_end(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理結束錄音事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            trigger = payload.get("trigger", "manual")
            duration = payload.get("duration", 0)
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.end_recording(session_id, trigger, duration))
            
            await self._send_message(connection, {
                "type": routes["RECORDING_END"],
                "payload": {
                    "session_id": session_id,
                    "status": "ended",
                    "trigger": trigger,
                    "duration": duration
                }
            })
            
            logger.info(f"Recording ended: {session_id}")
            
        except Exception as e:
            logger.error(f"Error ending recording: {e}")
            await self._send_error(connection, f"Failed to end recording: {str(e)}")
    
    # ========== 上傳管理 Handlers ==========
    
    async def _handle_chunk_upload_start(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理開始分塊上傳事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            connection.session_id = session_id
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.chunk_upload_start(session_id))
            
            await self._send_message(connection, {
                "type": routes["CHUNK_UPLOAD_START"],
                "payload": {"session_id": session_id, "status": "ready"}
            })
            
            logger.info(f"Chunk upload started: {session_id}")
            
        except Exception as e:
            logger.error(f"Error starting chunk upload: {e}")
            await self._send_error(connection, f"Failed to start chunk upload: {str(e)}")
    
    async def _handle_chunk_upload_done(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理完成分塊上傳事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            connection.session_id = session_id
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.chunk_upload_done(session_id))
            
            await self._send_message(connection, {
                "type": routes["CHUNK_UPLOAD_DONE"],
                "payload": {"session_id": session_id, "status": "processing"}
            })
            
            logger.info(f"Chunk upload done: {session_id}")
            
        except Exception as e:
            logger.error(f"Error completing chunk upload: {e}")
            await self._send_error(connection, f"Failed to complete chunk upload: {str(e)}")
    
    async def _handle_file_upload(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理檔案上傳事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            connection.session_id = session_id
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.upload_file(session_id))
            
            await self._send_message(connection, {
                "type": routes["FILE_UPLOAD"],
                "payload": {"session_id": session_id, "status": "uploading"}
            })
            
            logger.info(f"File upload started: {session_id}")
            
        except Exception as e:
            logger.error(f"Error starting file upload: {e}")
            await self._send_error(connection, f"Failed to start file upload: {str(e)}")
    
    async def _handle_file_upload_done(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """處理檔案上傳完成事件"""
        try:
            # data 現在直接是 payload
            session_id = data.get("session_id") or connection.session_id
            
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            store = get_global_store()
            if not store:
                await self._send_error(connection, "Store not initialized")
                return
                
            store.dispatch(sessions_actions.upload_file_done(session_id))
            
            await self._send_message(connection, {
                "type": routes["FILE_UPLOAD_DONE"],
                "payload": {"session_id": session_id, "status": "completed"}
            })
            
            logger.info(f"File upload done: {session_id}")
            
        except Exception as e:
            logger.error(f"Error completing file upload: {e}")
            await self._send_error(connection, f"Failed to complete file upload: {str(e)}")
    
    async def _handle_audio_chunk_message(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """
        處理音訊塊上傳訊息
        
        Args:
            connection: WebSocket 連線
            data: 包含音訊塊的訊息
        """
        # logger.info(f"WebSocket: _handle_audio_chunk_message called with data keys: {list(data.keys())}")
        session_id = data.get("session_id")
        # logger.info(f"WebSocket: processing audio chunk for session_id={session_id}")
        if not session_id:
            await self._send_error(connection, "No session_id provided")
            return
            
        # 設置連線的 session_id
        if not connection.session_id:
            connection.session_id = session_id
            # 初始化該 session 的分塊序號
            if session_id not in self.chunk_sequences:
                self.chunk_sequences[session_id] = 0
            
        # 驗證分塊序號 (類似 SocketIO 實現)
        chunk_id = data.get("chunk_id")
        if chunk_id is not None:
            expected_id = self.chunk_sequences.get(session_id, 0)
            if chunk_id != expected_id:
                logger.warning(
                    f"🚨 Chunk sequence mismatch for session {session_id}: "
                    f"expected {expected_id}, got {chunk_id}. This may cause format detection issues."
                )
                # 更新期望序號以繼續處理（容錯機制）
                self.chunk_sequences[session_id] = chunk_id + 1
            else:
                logger.debug(f"✅ Chunk {chunk_id} received in correct order for session {session_id}")
                self.chunk_sequences[session_id] = chunk_id + 1
            
        # 解碼 base64 音訊資料
        import base64
        audio_base64 = data.get("audio")
        if not audio_base64:
            await self._send_error(connection, "No audio data provided")
            return
        
        try:
            # logger.info(f"WebSocket: Decoding base64 audio data, length={len(audio_base64)}")
            audio_bytes = base64.b64decode(audio_base64)
            # logger.info(f"WebSocket: Decoded {len(audio_bytes)} bytes of audio data")
            
            # 將音訊推送到 AudioQueueManager
            # 檢測批次模式：如果有多個音訊塊或檔案大小較大，使用批次模式
            is_batch_mode = data.get("is_batch", False) or data.get("total_chunks", 1) > 1 or len(audio_bytes) > 32768  # 32KB 以上視為批次
            
            # logger.info(f"WebSocket: About to import get_audio_queue_manager")
            from src.core.audio_queue_manager import get_audio_queue_manager
            # logger.info(f"WebSocket: About to call get_audio_queue_manager()")
            audio_queue_manager = get_audio_queue_manager()
            # logger.info(f"WebSocket: Got audio_queue_manager, about to push audio for session {session_id}, batch_mode={is_batch_mode}")
            await audio_queue_manager.push(session_id, audio_bytes, batch_mode=is_batch_mode)
            # logger.info(f"WebSocket: Successfully pushed audio to AudioQueueManager for session {session_id}")
            
            # 分發 audio_chunk_received action
            chunk_size = len(audio_bytes)
            # logger.info(f"WebSocket: About to dispatch audio_chunk_received action, chunk_size={chunk_size}")
            store.dispatch(sessions_actions.audio_chunk_received(session_id, chunk_size))
            # logger.info(f"WebSocket: Successfully dispatched audio_chunk_received action")
            
            # 發送確認
            await self._send_message(connection, {
                "type": routes["AUDIO_RECEIVED"],  
                "size": chunk_size,
                "chunk_id": data.get("chunk_id")
            })
            
        except Exception as e:
            logger.error(f"處理音訊塊時發生錯誤: {e}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception details: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            await self._send_error(connection, str(e))
    
    async def _listen_store_events(self):
        """
        監聽 PyStoreX store 的事件並廣播給相關的 WebSocket 客戶端
        """
        logger.info("開始監聽 PyStoreX store 事件")
        
        while self._running:
            try:
                # 訂閱 store 的狀態變化
                # 注意：這裡需要根據實際的 PyStoreX API 調整
                # 暫時使用輪詢方式檢查狀態變化
                await asyncio.sleep(0.1)  # 100ms 檢查一次
                
                # 獲取最新的 store 實例
                current_store = get_global_store()
                if not current_store:
                    logger.debug("Store not initialized yet, waiting...")
                    continue
                
                # 檢查每個連線的 session 狀態
                for conn_id, connection in list(self.connections.items()):
                    if connection.session_id:
                        # 獲取 session 狀態
                        state = current_store.state
                        if not state:
                            continue
                            
                        # 使用正確的選擇器路徑
                        sessions_state = state.get('sessions', {})
                        all_sessions = sessions_state.get('sessions', {})
                        session = all_sessions.get(connection.session_id)
                        
                        if session:
                            # 檢查是否有新的轉譯結果 (存儲在 transcription 欄位)
                            transcription = session.get("transcription")
                            if transcription:
                                # 如果有轉譯結果且尚未發送
                                if not hasattr(connection, '_last_transcription_sent'):
                                    connection._last_transcription_sent = None
                                    
                                # 比較整個轉譯結果對象
                                if transcription != connection._last_transcription_sent:
                                    logger.info(f"[✨] 檢測到新的轉譯結果，session: {connection.session_id[:8]}...")
                                    
                                    # 轉換 immutables.Map 為可序列化的 dict
                                    serializable_result = self._convert_immutable_to_dict(transcription)
                                    
                                    # 發送最終轉譯結果
                                    message = {
                                        "type": routes["TRANSCRIPT"],
                                        "session_id": connection.session_id,
                                        "result": serializable_result,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    
                                    logger.info(f"[📤] 發送轉譯結果到 WebSocket 客戶端: {conn_id[:8]}...")
                                    await self._send_message(connection, message)
                                    connection._last_transcription_sent = transcription
                                    # 修復屬性訪問 - transcription 現在是字典格式
                                    if isinstance(transcription, dict):
                                        text_preview = transcription.get('text', '')
                                        # 檢查是否為空結果並提供用戶友好信息
                                        if not text_preview.strip():
                                            metadata = transcription.get('metadata', {})
                                            empty_reason = metadata.get('empty_result_reason', 'unknown')
                                            logger.info(f"發送空轉譯結果給連線 {conn_id}: 原因={empty_reason}")
                                        else:
                                            logger.info(f"發送轉譯結果給連線 {conn_id}: {text_preview[:50]}...")
                                    else:
                                        logger.info(f"發送轉譯結果給連線 {conn_id}: {str(transcription)[:50]}...")
                            
                            # 檢查其他狀態變化
                            current_state = session.get("state")
                            if not hasattr(connection, '_last_state'):
                                connection._last_state = None
                                
                            if current_state != connection._last_state:
                                # 發送狀態更新
                                await self._send_message(connection, {
                                    "type": routes["EVENT"],
                                    "event": {
                                        "type": "state_changed",
                                        "state": current_state,
                                        "session_id": connection.session_id
                                    }
                                })
                                connection._last_state = current_state
                                logger.debug(f"狀態變更: {connection._last_state} -> {current_state}")
                                
            except Exception as e:
                logger.error(f"監聽 store 事件時發生錯誤: {e}")
                await asyncio.sleep(1)  # 錯誤後等待1秒再繼續
        
        logger.info("停止監聽 PyStoreX store 事件")
    
    async def _handle_audio_json(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """
        處理 JSON 格式的音訊資料（向後兼容）
        
        Args:
            connection: WebSocket 連線
            data: 包含 base64 編碼音訊的 JSON 資料
        """
        # 更新 session_id
        if "session_id" in data:
            if not connection.session_id:
                connection.session_id = data["session_id"]
                logger.info(f"從 audio 訊息設置 session_id: {connection.session_id}")
        
        if not connection.session_id:
            await self._send_error(connection, "No session_id provided")
            return
        
        # 解碼 base64 音訊資料
        import base64
        audio_base64 = data.get("audio")
        if not audio_base64:
            await self._send_error(connection, "No audio data provided")
            return
        
        try:
            audio_bytes = base64.b64decode(audio_base64)
            await self._handle_audio_data(connection, audio_bytes)
        except Exception as e:
            logger.error(f"Error decoding audio data: {e}")
            await self._send_error(connection, "Failed to decode audio data")
        
    async def handle_control_command(self, 
                                   command: str, 
                                   session_id: str, 
                                   params: Optional[Dict[str, Any]] = None,
                                   connection: Optional['WebSocketConnection'] = None) -> APIResponse:
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
            state = store.state if store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            
            if command == "start":
                if not session:
                    # 使用 Store dispatch 創建 session (不傳遞 audio_format)
                    store.dispatch(sessions_actions.create_session(session_id))
                
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
                store.dispatch(sessions_actions.start_listening(session_id, audio_format))
                
                return self.create_success_response(
                    {"status": "started", "session_id": session_id},
                    session_id
                )
                
            elif command == "stop":
                if session:
                    store.dispatch(sessions_actions.update_session_state(session_id, "IDLE"))
                    # 停止音訊串流
                    self.stream_manager.stop_stream(session_id)
                return self.create_success_response(
                    {"status": "stopped", "session_id": session_id},
                    session_id
                )
                
            elif command == "status":
                status = {
                    "session_id": session_id,
                    "state": session.get("state", "IDLE") if session else "NO_SESSION",
                    "exists": session is not None
                }
                return self.create_success_response(status, session_id)
                
            elif command == "busy_start":
                if session:
                    store.dispatch(sessions_actions.update_session_state(session_id, "BUSY"))
                return self.create_success_response(
                    {"status": "busy_started", "session_id": session_id},
                    session_id
                )
                
            elif command == "busy_end":
                if session:
                    store.dispatch(sessions_actions.update_session_state(session_id, "LISTENING"))
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
        # 這個方法將在後續整合 Pipeline 和 Provider 時實作
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
        # 這個方法將在後續整合 Pipeline 和 Provider 時實作
        yield self.create_error_response("Not implemented yet", session_id)
        
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

    async def _send_message(self, connection: 'WebSocketConnection', message: Dict[str, Any]):
        """
        發送訊息到客戶端
        
        Args:
            connection: WebSocket 連線
            message: 訊息內容
        """
        try:
            # 使用自定義的遞歸轉換器處理所有不可變物件
            message_dict = self._convert_immutable_to_dict(message)
            await connection.websocket.send(json.dumps(message_dict))
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            logger.error(f"Message type: {type(message)}")
            logger.error(f"Message content: {str(message)[:200]}...")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
    async def _handle_audio_config(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """
        處理音訊配置訊息
        
        Args:
            connection: WebSocket 連線
            data: 音訊配置資料
        """
        config = data.get("config", {})
        
        # 更新 session_id（如果提供）
        if "session_id" in data:
            if not connection.session_id:
                connection.session_id = data["session_id"]
                logger.info(f"從 audio_config 訊息設置 session_id: {connection.session_id}")
        
        # 驗證音訊參數
        try:
            logger.debug(f"收到音訊配置: {config}")
            validated_params = await self.validate_audio_params(config)
            
            # 儲存音訊配置到連線
            connection.audio_config = validated_params
            
            logger.info(f"音訊配置已儲存到連線 {connection.id}, session_id: {connection.session_id}")
            logger.debug(f"儲存的配置: {validated_params}")
            
            # 發送確認訊息
            await self._send_message(connection, {
                "type": "audio_config_ack",
                "status": "success",
                "config": {
                    "sample_rate": validated_params["sample_rate"],
                    "channels": validated_params["channels"],
                    "format": validated_params["format"].value,
                    "encoding": validated_params["encoding"].value,
                    "bits_per_sample": validated_params["bits_per_sample"]
                },
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"音訊配置已更新: {validated_params}")
            
        except APIError as e:
            await self._send_error(connection, f"音訊配置錯誤: {str(e)}")
        except Exception as e:
            logger.error(f"處理音訊配置時發生錯誤: {e}")
            await self._send_error(connection, "處理音訊配置失敗")
    
    async def _handle_audio_metadata(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """
        處理音訊元資料訊息
        
        Args:
            connection: WebSocket 連線
            data: 音訊元資料
        """
        try:
            session_id = data.get("session_id") or connection.session_id
            if not session_id:
                await self._send_error(connection, "No session_id provided")
                return
            
            metadata = data.get("audio_metadata", {})
            
            # 記錄收到的元資料
            logger.info(f"收到音訊元資料 - Session: {session_id}")
            logger.debug(f"元資料內容: {metadata}")
            
            # 儲存元資料到 store（如果需要）
            store = get_global_store()
            if store:
                # 可以將元資料儲存到 session 中
                from src.store.sessions import sessions_actions
                store.dispatch(sessions_actions.audio_metadata(session_id, metadata))
            
            # 發送確認訊息
            await self._send_message(connection, {
                "type": "audio_metadata_ack",
                "status": "success",
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"音訊元資料已處理: {session_id}")
            
        except Exception as e:
            logger.error(f"處理音訊元資料時發生錯誤: {e}")
            await self._send_error(connection, f"處理音訊元資料失敗: {str(e)}")
        
    async def _send_error(self, connection: 'WebSocketConnection', error_message: str):
        """
        發送錯誤訊息
        
        Args:
            connection: WebSocket 連線
            error_message: 錯誤訊息
        """
        from src.api.websocket.handlers import MessageBuilder
        await self._send_message(connection, MessageBuilder.build_error(error_message))
        
    async def _broadcast_status_update(self, connection: 'WebSocketConnection'):
        """
        廣播狀態更新
        
        Args:
            connection: 觸發更新的連線
        """
        from src.api.websocket.handlers import MessageBuilder
        
        if not connection.session_id:
            return
            
        # 使用 selector 獲取 session
        state = store.state if store else None
        session = sessions_selectors.get_session(connection.session_id)(state) if state else None
        if not session:
            return
            
        # 建立狀態更新訊息
        current_state = session.get("state", "IDLE")
        status_message = MessageBuilder.build_status(
            session_id=connection.session_id,
            state=translate_fsm_state(current_state),
            details={
                "state_code": current_state,
                "last_activity": session.get("last_activity").isoformat() if isinstance(session.get("last_activity"), datetime) else session.get("last_activity")
            }
        )
        
        # 發送給同一 session 的所有連線
        for conn_id, conn in self.connections.items():
            if conn.session_id == connection.session_id:
                try:
                    await self._send_message(conn, status_message)
                except Exception as e:
                    logger.error(f"Error broadcasting to connection {conn_id}: {e}")
        
    async def _close_connection(self, connection_id: str):
        """
        關閉並清理連線
        
        Args:
            connection_id: 連線 ID
        """
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            
            # 清理音訊串流
            if connection.session_id:
                self.stream_manager.cleanup_stream(connection.session_id)
                # 清理分塊序號追蹤
                if connection.session_id in self.chunk_sequences:
                    del self.chunk_sequences[connection.session_id]
                    logger.debug(f"Cleaned up chunk sequence tracking for session {connection.session_id}")
                
            # 關閉 WebSocket
            await connection.websocket.close()
            
            # 移除連線記錄
            del self.connections[connection_id]
            
            logger.info(f"Connection {connection_id} closed and cleaned up")
            
    async def _heartbeat_task(self):
        """心跳檢查任務"""
        while self._running:
            try:
                # 檢查所有連線
                for conn_id in list(self.connections.keys()):
                    connection = self.connections.get(conn_id)
                    if connection:
                        try:
                            # 發送 ping
                            pong_waiter = await connection.websocket.ping()
                            await asyncio.wait_for(pong_waiter, timeout=10)
                        except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
                            logger.warning(f"Connection {conn_id} failed heartbeat")
                            await self._close_connection(conn_id)
                            
                # 每 30 秒檢查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                
    async def _process_audio_stream(self, connection: 'WebSocketConnection'):
        """
        處理音訊串流
        
        Args:
            connection: WebSocket 連線
        """
        if not connection.session_id:
            return
            
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
                await self._send_message(connection, {
                    "type": routes["PROGRESS"],
                    "message": f"接收音訊片段 {chunk_count}",
                    "timestamp": datetime.now().isoformat()
                })
            
            if audio_chunks:
                # 合併所有音訊片段
                complete_audio = b''.join(audio_chunks)
                logger.info(f"收集完成，共 {len(audio_chunks)} 個片段，總大小 {len(complete_audio)} bytes")
                
                # 呼叫實際的轉譯處理
                await self._transcribe_audio(connection, complete_audio)
            else:
                await self._send_error(connection, "沒有收到音訊資料")
                
        except Exception as e:
            logger.error(f"Error processing audio stream: {e}")
            await self._send_error(connection, f"處理音訊串流錯誤: {str(e)}")
        finally:
            # 清理串流
            self.stream_manager.cleanup_stream(connection.session_id)
    
    async def _transcribe_audio(self, connection: 'WebSocketConnection', audio_data: bytes):
        """
        執行語音轉文字
        
        Args:
            connection: WebSocket 連線
            audio_data: 完整的音訊資料
        """
        try:
            # 發送開始轉譯訊息
            await self._send_message(connection, {
                "type": routes["TRANSCRIPT_PARTIAL"],
                "text": "正在進行語音辨識...",
                "is_final": False,
                "timestamp": datetime.now().isoformat()
            })
            
            if not self.provider_manager:
                # 如果沒有 provider manager，使用模擬結果
                await asyncio.sleep(1)
                final_text = f"[模擬] 收到 {len(audio_data)} bytes 的音訊"
            else:
                # 先將 WebM 轉換為 PCM
                logger.info("開始轉換 WebM 音訊到 PCM 格式")
                try:
                    pcm_data = AudioConverter.convert_webm_to_pcm(audio_data)
                    logger.info(f"音訊轉換成功: {len(audio_data)} bytes WebM -> {len(pcm_data)} bytes PCM")
                except Exception as e:
                    logger.error(f"音訊轉換失敗: {e}")
                    # 如果轉換失敗，無法處理
                    await self._send_error(connection, 
                        "無法轉換音訊格式。請確保系統已安裝 FFmpeg 或 pydub。"
                        "在 macOS 上可以使用 'brew install ffmpeg' 安裝 FFmpeg。")
                    return
                
                # 從連線的音訊配置建立 AudioChunk
                audio_config = getattr(connection, 'audio_config', None)
                if not audio_config:
                    # 如果沒有配置，使用嚴格錯誤
                    await self._send_error(connection, "缺少音訊配置")
                    return
                
                # 建立 AudioChunk 物件
                audio = AudioChunk(
                    data=pcm_data,
                    sample_rate=audio_config["sample_rate"],
                    channels=audio_config["channels"],
                    format=AudioContainerFormat.PCM,  # 轉換後的格式
                    encoding=audio_config["encoding"],
                    bits_per_sample=audio_config["bits_per_sample"]
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
                    
                    from src.api.websocket.handlers import MessageBuilder
                    final_result = MessageBuilder.build_transcript(
                        text=final_text,
                        is_final=True,
                        confidence=result.confidence if hasattr(result, 'confidence') else 0.95
                    )
                    
                    await self._send_message(connection, final_result)
                else:
                    final_text = "無法辨識音訊內容"
                    await self._send_error(connection, final_text)
            
            logger.info(f"轉譯完成: {final_text}")
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            await self._send_error(connection, f"轉譯錯誤: {str(e)}")
                

class WebSocketConnection:
    """WebSocket 連線資訊"""
    
    def __init__(self, id: str, websocket: WebSocketServerProtocol, 
                 session_id: Optional[str], connected_at: datetime):
        self.id = id
        self.websocket = websocket
        self.session_id = session_id
        self.connected_at = connected_at
        self.last_activity = connected_at
        self.audio_config = None  # 儲存音訊配置
        self._last_state = None  # 追蹤上次發送的狀態
        self._last_transcription_sent = None  # 追蹤上次發送的轉譯結果