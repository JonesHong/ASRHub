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
from src.utils.logger import logger
from src.core.session_manager import SessionManager
from src.core.exceptions import APIError
from src.api.websocket.stream_manager import WebSocketStreamManager
from src.pipeline.manager import PipelineManager
from src.providers.manager import ProviderManager
from src.models.audio import AudioChunk, AudioFormat
from src.utils.audio_converter import convert_webm_to_pcm
from src.config.manager import ConfigManager


class WebSocketServer(APIBase):
    """
    WebSocket Server 實作
    支援即時雙向通訊和音訊串流處理
    """
    
    def __init__(self, session_manager: SessionManager,
                 pipeline_manager: Optional[PipelineManager] = None,
                 provider_manager: Optional[ProviderManager] = None):
        """
        初始化 WebSocket 服務器
        使用 ConfigManager 獲取配置
        
        Args:
            session_manager: Session 管理器
            pipeline_manager: Pipeline 管理器
            provider_manager: Provider 管理器
        """
        # 只傳遞 session_manager 給父類
        super().__init__(session_manager)
        
        # 從 ConfigManager 獲取配置
        ws_config = self.config_manager.api.websocket
        
        self.host = ws_config.host
        self.port = ws_config.port
        self.server = None
        self.connections: Dict[str, WebSocketConnection] = {}
        self.logger = logger
        self.stream_manager = WebSocketStreamManager()
        self.pipeline_manager = pipeline_manager
        self.provider_manager = provider_manager
        
    async def start(self):
        """啟動 WebSocket 服務器"""
        try:
            self._running = True
            # 為兼容新版 websockets，創建一個包裝函數
            async def connection_handler(websocket):
                await self.handle_connection(websocket, "/")
            
            self.server = await websockets.serve(
                connection_handler,
                self.host,
                self.port
            )
            self.logger.info(f"WebSocket server started on {self.host}:{self.port}")
            
            # 啟動心跳檢查任務
            asyncio.create_task(self._heartbeat_task())
            
        except Exception as e:
            self.logger.error(f"Failed to start WebSocket server: {e}")
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
                
            self.logger.info("WebSocket server stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping WebSocket server: {e}")
            
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
        self.logger.info(f"New WebSocket connection: {connection_id}")
        
        try:
            # 發送歡迎訊息
            from src.api.websocket.handlers import MessageBuilder
            await self._send_message(connection, MessageBuilder.build_welcome(connection_id))
            
            # 處理訊息
            async for message in websocket:
                await self._handle_message(connection, message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"WebSocket connection closed: {connection_id}")
        except Exception as e:
            self.logger.error(f"Error handling connection {connection_id}: {e}")
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
                
            message_type = data.get("type")
            
            if message_type == "audio_config":
                # 處理音訊配置訊息
                await self._handle_audio_config(connection, data)
            elif message_type == "control":
                await self._handle_control_message(connection, data)
            elif message_type == "audio":
                # 處理 JSON 格式的音訊資料
                await self._handle_audio_json(connection, data)
            elif message_type == "ping":
                await self._send_message(connection, {"type": "pong"})
            else:
                await self._send_error(connection, f"Unknown message type: {message_type}")
                
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            await self._send_error(connection, str(e))
            
    async def _handle_control_message(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """
        處理控制訊息
        
        Args:
            connection: WebSocket 連線
            data: 控制訊息資料
        """
        from src.api.websocket.handlers import MessageBuilder, MessageValidator
        
        # 驗證控制訊息格式
        if not MessageValidator.validate_control_message(data):
            await self._send_error(connection, "Invalid control message format")
            return
            
        command = data.get("command")
        params = data.get("params", {})
        
        # 如果沒有 session_id，先建立新的 session
        if not connection.session_id and command == "start":
            connection.session_id = data.get("session_id") or str(uuid.uuid4())
            self.logger.info(f"從 control start 命令設置 session_id: {connection.session_id}")
            
        response = await self.handle_control_command(
            command=command,
            session_id=connection.session_id,
            params=params
        )
        
        # 使用 MessageBuilder 建立回應
        response_message = MessageBuilder.build_control_response(
            command=command,
            status=response.status,
            data=response.data,
            error=response.error
        )
        
        await self._send_message(connection, response_message)
        
        # 如果狀態有變更，推送狀態更新
        if command in ["start", "stop", "busy_start", "busy_end"]:
            await self._broadcast_status_update(connection)
        
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
            # 檢查 session 狀態
            session = self.session_manager.get_session(connection.session_id)
            if not session or session.state != "LISTENING":
                await self._send_error(connection, "Session not in LISTENING state")
                return
                
            # 檢查是否已建立串流
            if connection.session_id not in self.stream_manager.stream_buffers:
                # 檢查連線是否有音訊配置
                if not hasattr(connection, 'audio_config') or connection.audio_config is None:
                    self.logger.error(f"連線 {connection.id} 沒有音訊配置, session_id: {connection.session_id}")
                    self.logger.debug(f"連線屬性: {[attr for attr in dir(connection) if not attr.startswith('_')]}")
                    await self._send_error(connection, "缺少音訊配置，請先發送 audio_config 訊息")
                    return
                    
                # 使用連線的音訊配置建立串流
                self.stream_manager.create_stream(connection.session_id, connection.audio_config)
                
                # 啟動串流處理任務
                asyncio.create_task(self._process_audio_stream(connection))
                
            # 檢查背壓
            if self.stream_manager.implement_backpressure(connection.session_id):
                await self._send_message(connection, {
                    "type": "backpressure",
                    "message": "Audio buffer near capacity, please slow down"
                })
                
            # 添加音訊資料到串流
            if self.stream_manager.add_audio_chunk(connection.session_id, audio_data):
                # 發送確認
                await self._send_message(connection, {
                    "type": "audio_received",
                    "size": len(audio_data),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                await self._send_error(connection, "Failed to process audio chunk")
                
        except Exception as e:
            self.logger.error(f"Error handling audio data: {e}")
            await self._send_error(connection, str(e))
    
    async def _handle_audio_json(self, connection: 'WebSocketConnection', data: Dict[str, Any]):
        """
        處理 JSON 格式的音訊資料
        
        Args:
            connection: WebSocket 連線
            data: 包含 base64 編碼音訊的 JSON 資料
        """
        # 更新 session_id
        if "session_id" in data:
            if not connection.session_id:
                connection.session_id = data["session_id"]
                self.logger.info(f"從 audio 訊息設置 session_id: {connection.session_id}")
        
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
            self.logger.error(f"Error decoding audio data: {e}")
            await self._send_error(connection, "Failed to decode audio data")
        
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
                    "exists": session is not None
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
        
    async def _send_message(self, connection: 'WebSocketConnection', message: Dict[str, Any]):
        """
        發送訊息到客戶端
        
        Args:
            connection: WebSocket 連線
            message: 訊息內容
        """
        try:
            await connection.websocket.send(json.dumps(message))
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            
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
                self.logger.info(f"從 audio_config 訊息設置 session_id: {connection.session_id}")
        
        # 驗證音訊參數
        try:
            self.logger.debug(f"收到音訊配置: {config}")
            validated_params = await self.validate_audio_params(config)
            
            # 儲存音訊配置到連線
            connection.audio_config = validated_params
            
            self.logger.info(f"音訊配置已儲存到連線 {connection.id}, session_id: {connection.session_id}")
            self.logger.debug(f"儲存的配置: {validated_params}")
            
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
            
            self.logger.info(f"音訊配置已更新: {validated_params}")
            
        except APIError as e:
            await self._send_error(connection, f"音訊配置錯誤: {str(e)}")
        except Exception as e:
            self.logger.error(f"處理音訊配置時發生錯誤: {e}")
            await self._send_error(connection, "處理音訊配置失敗")
        
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
            
        session = self.session_manager.get_session(connection.session_id)
        if not session:
            return
            
        # 建立狀態更新訊息
        status_message = MessageBuilder.build_status(
            session_id=connection.session_id,
            state=session.state,
            details={
                "last_activity": session.last_activity.isoformat() if hasattr(session, 'last_activity') else None
            }
        )
        
        # 發送給同一 session 的所有連線
        for conn_id, conn in self.connections.items():
            if conn.session_id == connection.session_id:
                try:
                    await self._send_message(conn, status_message)
                except Exception as e:
                    self.logger.error(f"Error broadcasting to connection {conn_id}: {e}")
        
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
                
            # 關閉 WebSocket
            await connection.websocket.close()
            
            # 移除連線記錄
            del self.connections[connection_id]
            
            self.logger.info(f"Connection {connection_id} closed and cleaned up")
            
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
                            self.logger.warning(f"Connection {conn_id} failed heartbeat")
                            await self._close_connection(conn_id)
                            
                # 每 30 秒檢查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat task: {e}")
                
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
                    "type": "progress",
                    "message": f"接收音訊片段 {chunk_count}",
                    "timestamp": datetime.now().isoformat()
                })
            
            if audio_chunks:
                # 合併所有音訊片段
                complete_audio = b''.join(audio_chunks)
                self.logger.info(f"收集完成，共 {len(audio_chunks)} 個片段，總大小 {len(complete_audio)} bytes")
                
                # 呼叫實際的轉譯處理
                await self._transcribe_audio(connection, complete_audio)
            else:
                await self._send_error(connection, "沒有收到音訊資料")
                
        except Exception as e:
            self.logger.error(f"Error processing audio stream: {e}")
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
                "type": "transcript_partial",
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
                self.logger.info("開始轉換 WebM 音訊到 PCM 格式")
                try:
                    pcm_data = convert_webm_to_pcm(audio_data)
                    self.logger.info(f"音訊轉換成功: {len(audio_data)} bytes WebM -> {len(pcm_data)} bytes PCM")
                except Exception as e:
                    self.logger.error(f"音訊轉換失敗: {e}")
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
                    format=AudioFormat.PCM,  # 轉換後的格式
                    encoding=audio_config["encoding"],
                    bits_per_sample=audio_config["bits_per_sample"]
                )
                
                # 透過 Pipeline 處理音訊（如果有）
                processed_audio_data = pcm_data
                if self.pipeline_manager:
                    # 獲取預設 pipeline
                    pipeline = self.pipeline_manager.get_pipeline("default")
                    if pipeline:
                        # 處理音訊
                        processed_audio_data = await pipeline.process(audio.data)
                
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
            
            self.logger.info(f"轉譯完成: {final_text}")
            
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
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