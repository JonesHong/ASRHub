"""
HTTP SSE 伺服器實現

支援三個核心事件流程：
1. create_session - 建立新的 ASR session
2. start_listening - 設定音訊參數
3. emit_audio_chunk - 接收音訊資料並觸發轉譯

使用 Server-Sent Events (SSE) 推送轉譯結果。
"""

import asyncio
import json
import base64
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator
from collections import defaultdict
from asyncio import Queue

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
import uuid6

from src.api.http_sse.endpoints import SSEEndpoints, SSEEventTypes
from src.api.http_sse.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    StartListeningRequest,
    StartListeningResponse,
    EmitAudioChunkRequest,
    AudioChunkResponse,
    WakeActivateRequest,
    WakeActivateResponse,
    WakeDeactivateRequest,
    WakeDeactivateResponse,
    ErrorResponse,
    SSEEvent,
    TranscribeDoneEvent,
    PlayASRFeedbackEvent,
    HeartbeatEvent,
    ConnectionReadyEvent,
)

from src.store.main_store import store
from src.store.sessions.sessions_action import (
    create_session,
    start_listening,
    receive_audio_chunk,
    transcribe_done,
    wake_activated,
    wake_deactivated,
    play_asr_feedback,
)
from src.store.sessions.sessions_selector import (
    get_session_by_id,
    get_all_sessions,
    get_session_last_transcription,
)
from src.config.manager import ConfigManager
from src.utils.logger import logger


class HTTPSSEServer:
    """HTTP SSE 伺服器"""
    
    def __init__(self):
        """初始化 HTTP SSE 伺服器"""
        self.config_manager = ConfigManager()
        self.http_config = self.config_manager.api.http_sse
        
        if not self.http_config.enabled:
            logger.info("HTTP SSE 服務已停用")
            return
        
        # FastAPI 應用程式
        self.app = FastAPI(
            title="ASR Hub HTTP SSE API",
            version="1.0.0",
            description="語音識別中介服務 HTTP SSE API"
        )
        
        # SSE 連線管理
        self.sse_connections: Dict[str, Queue] = {}  # session_id -> event queue
        self.sse_tasks: Dict[str, asyncio.Task] = {}  # session_id -> SSE task
        
        # Store 訂閱
        self.store_subscription = None
        
        # 系統狀態
        self.start_time = time.time()
        self.is_running = False
        
        # 設定路由
        self._setup_routes()
        
        # 設定中介軟體
        self._setup_middleware()
    
    def _setup_middleware(self):
        """設定中介軟體"""
        # CORS 設定 - 使用預設或從設定取得
        cors_origins = ["*"]  # 預設允許所有來源
        if hasattr(self.http_config, 'cors_origins'):
            cors_origins = self.http_config.cors_origins
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """設定 API 路由"""
        
        # === 主要功能 (與 Redis 相同) ===
        @self.app.post(SSEEndpoints.CREATE_SESSION, response_model=CreateSessionResponse)
        async def create_session_endpoint(request: CreateSessionRequest):
            """建立新的 ASR session"""
            return await self._handle_create_session(request)
        
        @self.app.post(SSEEndpoints.START_LISTENING, response_model=StartListeningResponse)
        async def start_listening_endpoint(request: StartListeningRequest):
            """開始監聽音訊"""
            return await self._handle_start_listening(request)
        
        # === Wake 控制 ===
        @self.app.post(SSEEndpoints.WAKE_ACTIVATE, response_model=WakeActivateResponse)
        async def wake_activate_endpoint(request: WakeActivateRequest):
            """啟用喚醒"""
            return await self._handle_wake_activate(request)
        
        @self.app.post(SSEEndpoints.WAKE_DEACTIVATE, response_model=WakeDeactivateResponse)
        async def wake_deactivate_endpoint(request: WakeDeactivateRequest):
            """停用喚醒"""
            return await self._handle_wake_deactivate(request)
        
        # === 音訊串流 ===
        @self.app.post(SSEEndpoints.EMIT_AUDIO_CHUNK)
        async def emit_audio_chunk_endpoint(request: Request):
            """發送二進制音訊資料 - 使用 metadata + separator + binary 格式"""
            # 讀取完整的請求體
            body = await request.body()
            
            # 定義分隔符
            separator = b'\x00\x00\xFF\xFF'
            
            # 找到分隔符位置
            separator_idx = body.find(separator)
            if separator_idx == -1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid request format. Expected: [JSON metadata] + [separator] + [binary audio]"
                )
            
            # 分離 metadata 和音訊資料
            metadata_json = body[:separator_idx]
            audio_bytes = body[separator_idx + len(separator):]
            
            # 解析 metadata
            try:
                metadata = json.loads(metadata_json.decode('utf-8'))
                session_id = metadata.get('session_id')
                chunk_id = metadata.get('chunk_id')
                
                if not session_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Missing session_id in metadata"
                    )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid metadata JSON"
                )
            
            return await self._handle_emit_audio_chunk(session_id, audio_bytes, chunk_id)
        
        # === SSE 事件串流 ===
        @self.app.get(SSEEndpoints.EVENTS_STREAM)
        async def events_stream_endpoint(session_id: str, request: Request):
            """SSE 事件串流"""
            return await self._handle_events_stream(session_id, request)
    
    async def _handle_create_session(self, request: CreateSessionRequest) -> CreateSessionResponse:
        """處理建立 Session 請求"""
        try:
            # 生成 request_id（如果客戶端沒提供）
            request_id = request.request_id or str(uuid6.uuid7())
            
            # 分發到 PyStoreX Store
            action = create_session(
                strategy=request.strategy,
                request_id=request_id
            )
            store.dispatch(action)
            
            # 從 state 獲取 reducer 創建的 session_id
            state = store.state
            sessions_data = state.get("sessions", {})
            
            # 處理 immutables.Map 和 dict
            if hasattr(sessions_data, 'get') and 'sessions' in sessions_data:
                sessions = sessions_data.get('sessions', {})
            else:
                sessions = sessions_data
            
            session_id = None
            
            # 找到對應的 session
            for sid, session in sessions.items():
                session_request_id = None
                if hasattr(session, 'get'):
                    session_request_id = session.get('request_id')
                elif hasattr(session, '__getitem__'):
                    try:
                        session_request_id = session['request_id']
                    except (KeyError, TypeError):
                        pass
                
                if session_request_id == request_id:
                    session_id = sid
                    break
            
            # Fallback: 從 SessionEffects 獲取
            if not session_id:
                from src.store.sessions.sessions_effect import SessionEffects
                session_id = SessionEffects.get_session_id_by_request_id(request_id)
            
            if not session_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create session"
                )
            
            # 建立 SSE 事件佇列
            self.sse_connections[session_id] = Queue()
            
            logger.info(f"✅ Session 建立成功: {session_id} (策略: {request.strategy})")
            
            # 返回 URLs 
            connect_host =  self.http_config.host
            base_url = f"http://{connect_host}:{self.http_config.port}"
            return CreateSessionResponse(
                session_id=session_id,
                request_id=request_id,
                sse_url=f"{base_url}{SSEEndpoints.API_PREFIX}/sessions/{session_id}/events",
                audio_url=f"{base_url}{SSEEndpoints.API_PREFIX}/sessions/{session_id}/audio"
            )
            
        except Exception as e:
            logger.error(f"建立 Session 失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def _handle_start_listening(self, request: StartListeningRequest) -> StartListeningResponse:
        """處理開始監聽請求"""
        try:
            session_id = request.session_id
            # 檢查 session 是否存在
            session = get_session_by_id(session_id)(store.state)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_id} not found"
                )
            
            # 分發到 Store
            action = start_listening(
                session_id=session_id,
                sample_rate=request.sample_rate,
                channels=request.channels,
                format=request.format
            )
            store.dispatch(action)
            
            logger.info(f"✅ 開始監聽 session {session_id}: {request.sample_rate}Hz, {request.channels}ch, {request.format}")
            
            # 發送 SSE 事件
            await self._send_sse_event(session_id, SSEEventTypes.LISTENING_STARTED, {
                "session_id": session_id,
                "sample_rate": request.sample_rate,
                "channels": request.channels,
                "format": request.format,
                "timestamp": datetime.now().isoformat()
            })
            
            return StartListeningResponse(
                session_id=session_id,
                sample_rate=request.sample_rate,
                channels=request.channels,
                format=request.format,
                status="listening"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"開始監聽失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def _handle_emit_audio_chunk(
        self, 
        session_id: str,
        audio_bytes: bytes,
        chunk_id: Optional[str] = None
    ) -> AudioChunkResponse:
        """處理二進位音訊片段 - 從 session 取得音訊參數"""
        try:
            # 檢查 session 是否存在並取得音訊參數
            session = get_session_by_id(session_id)(store.state)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_id} not found"
                )
            
            # 從 session 取得音訊參數（在 start_listening 時設定的）
            # 使用 getattr 和 get 方法相容不同的資料結構
            if hasattr(session, 'get'):
                sample_rate = session.get('sample_rate', 16000)
                channels = session.get('channels', 1)
                audio_format = session.get('format', 'int16')
            else:
                sample_rate = getattr(session, 'sample_rate', 16000)
                channels = getattr(session, 'channels', 1)
                audio_format = getattr(session, 'format', 'int16')
            
            # 如果需要轉換格式，使用 audio_converter 服務
            if sample_rate != 16000 or channels != 1:
                from src.service.audio_converter.scipy_converter import audio_converter
                
                # 轉換音訊格式
                converted_audio = await self._run_in_thread(
                    lambda: audio_converter.convert(
                        audio_bytes,
                        input_sample_rate=sample_rate,
                        input_channels=channels,
                        target_sample_rate=16000,
                        target_channels=1,
                        target_format="int16"
                    )
                )
                audio_bytes = converted_audio
                logger.debug(f"音訊已轉換: {sample_rate}Hz {channels}ch -> 16000Hz 1ch")
            
            # 直接分發到 Store，讓 SessionEffects 和 audio_queue_manager 處理
            action = receive_audio_chunk(
                session_id=session_id,
                audio_data=audio_bytes
            )
            store.dispatch(action)
            
            logger.debug(f"📥 音訊片段 [{session_id}]: chunk={chunk_id or 'unnamed'}, size={len(audio_bytes)}")
            
            return AudioChunkResponse(
                session_id=session_id,
                chunk_id=chunk_id or f"chunk_{time.time()}",
                bytes_received=len(audio_bytes),
                status="received"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"處理音訊失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def _run_in_thread(self, func):
        """在執行緒中執行同步函數"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)
    
    async def _handle_wake_activate(self, request: WakeActivateRequest) -> WakeActivateResponse:
        """處理喚醒啟用請求"""
        try:
            session_id = request.session_id
            # 檢查 session 是否存在
            session = get_session_by_id(session_id)(store.state)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_id} not found"
                )
            
            # 分發到 Store
            action = wake_activated(session_id=session_id, source=request.source)
            store.dispatch(action)
            
            logger.info(f"🎯 喚醒啟用 [session: {session_id}]: 來源={request.source}")
            
            # 發送 SSE 事件
            await self._send_sse_event(session_id, SSEEventTypes.WAKE_ACTIVATED, {
                "session_id": session_id,
                "source": request.source,
                "timestamp": datetime.now().isoformat()
            })
            
            return WakeActivateResponse(
                session_id=session_id,
                source=request.source,
                status="activated"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"喚醒啟用失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def _handle_wake_deactivate(self, request: WakeDeactivateRequest) -> WakeDeactivateResponse:
        """處理喚醒停用請求"""
        try:
            session_id = request.session_id
            # 檢查 session 是否存在
            session = get_session_by_id(session_id)(store.state)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_id} not found"
                )
            
            # 分發到 Store
            action = wake_deactivated(session_id=session_id, source=request.source)
            store.dispatch(action)
            
            logger.info(f"🛑 喚醒停用 [session: {session_id}]: 來源={request.source}")
            
            # 發送 SSE 事件
            await self._send_sse_event(session_id, SSEEventTypes.WAKE_DEACTIVATED, {
                "session_id": session_id,
                "source": request.source,
                "timestamp": datetime.now().isoformat()
            })
            
            return WakeDeactivateResponse(
                session_id=session_id,
                source=request.source,
                status="deactivated"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"喚醒停用失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    
    async def _handle_events_stream(self, session_id: str, request: Request) -> StreamingResponse:
        """處理 SSE 事件串流"""
        try:
            # 檢查 session 是否存在
            session = get_session_by_id(session_id)(store.state)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_id} not found"
                )
            
            # 檢查是否已有連線
            if session_id not in self.sse_connections:
                self.sse_connections[session_id] = Queue()
            
            # 建立 SSE 生成器
            async def event_generator():
                try:
                    # 發送連線就緒事件
                    ready_event = ConnectionReadyEvent(
                        session_id=session_id,
                        timestamp=datetime.now().isoformat()
                    )
                    yield self._format_sse_event(SSEEventTypes.CONNECTION_READY, ready_event.model_dump())
                    
                    # 心跳序列號
                    heartbeat_seq = 0
                    
                    # 事件迴圈
                    queue = self.sse_connections[session_id]
                    while True:
                        try:
                            # 等待事件或心跳
                            event = await asyncio.wait_for(queue.get(), timeout=30.0)
                            
                            if event is None:
                                # 結束信號
                                break
                            
                            # 發送事件
                            yield event
                            
                        except asyncio.TimeoutError:
                            # 發送心跳
                            heartbeat_seq += 1
                            heartbeat_event = HeartbeatEvent(
                                session_id=session_id,
                                timestamp=datetime.now().isoformat(),
                                sequence=heartbeat_seq
                            )
                            yield self._format_sse_event(SSEEventTypes.HEARTBEAT, heartbeat_event.model_dump())
                        
                        # 檢查客戶端是否斷線
                        if await request.is_disconnected():
                            break
                            
                except Exception as e:
                    logger.error(f"SSE 生成器錯誤: {e}")
                finally:
                    # 清理連線
                    if session_id in self.sse_connections:
                        del self.sse_connections[session_id]
                    logger.info(f"SSE 連線已關閉: {session_id}")
            
            # 返回 SSE 串流
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # 禁用 Nginx 緩衝
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"建立 SSE 串流失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def _send_sse_event(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """發送 SSE 事件到客戶端"""
        try:
            if session_id in self.sse_connections:
                queue = self.sse_connections[session_id]
                event = self._format_sse_event(event_type, data)
                await queue.put(event)
                logger.debug(f"📤 SSE 事件 [{session_id}]: {event_type}")
        except Exception as e:
            logger.error(f"發送 SSE 事件失敗: {e}")
    
    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """格式化 SSE 事件"""
        event_id = str(uuid6.uuid7())
        lines = [
            f"id: {event_id}",
            f"event: {event_type}",
            f"data: {json.dumps(data)}",
            "",  # 空行結束事件
            ""
        ]
        return "\n".join(lines)
    
    def _setup_store_listeners(self):
        """設定 Store 事件監聽器"""
        # 儲存事件循環參考
        self.loop = None
        
        def handle_store_action(action):
            """處理 Store 的 action 事件"""
            # action 可能是 dict 或 Action 物件
            if hasattr(action, "type"):
                action_type = action.type
                payload = action.payload if hasattr(action, "payload") else {}
            else:
                action_type = action.get("type", "") if isinstance(action, dict) else ""
                payload = action.get("payload", {}) if isinstance(action, dict) else {}
            
            # 記錄所有收到的 action（調試用）
            if action_type not in [receive_audio_chunk.type]:
                logger.info(f"📡 [HTTP SSE] 處理 Store action: {action_type}")
            
            # 只有我們關心的事件才處理
            if action_type in [transcribe_done.type, play_asr_feedback.type]:
                # 安全地在事件循環中執行
                self._schedule_async_task(action_type, payload)
        
        # 訂閱 Store 的 action stream
        self.store_subscription = store._action_subject.subscribe(handle_store_action)
        # logger.debug("Store 事件監聽器已設定")  # 改為 debug 級別，避免重複顯示
    
    def _schedule_async_task(self, action_type: str, payload: Dict[str, Any]):
        """安全地排程非同步任務"""
        try:
            # 取得或設定事件循環
            if self.loop is None:
                try:
                    self.loop = asyncio.get_running_loop()
                except RuntimeError:
                    # 沒有運行中的事件循環，嘗試取得當前執行緒的事件循環
                    self.loop = asyncio.get_event_loop()
            
            # 監聽轉譯完成事件
            if action_type == transcribe_done.type:
                asyncio.run_coroutine_threadsafe(self._handle_transcribe_done(payload), self.loop)
            
            # 監聽 ASR 回饋音事件
            elif action_type == play_asr_feedback.type:
                # 根據 command 判斷播放或停止
                # 處理 dict 和 immutables.Map 的情況
                command = None
                if hasattr(payload, 'get'):
                    command = payload.get("command")
                elif isinstance(payload, dict):
                    command = payload.get("command")
                
                if command == "play":
                    asyncio.run_coroutine_threadsafe(self._handle_asr_feedback_play(payload), self.loop)
                elif command == "stop":
                    asyncio.run_coroutine_threadsafe(self._handle_asr_feedback_stop(payload), self.loop)
                else:
                    logger.warning(f"未知的 ASR 回饋音 command: {command}, payload type: {type(payload)}")
                
        except Exception as e:
            logger.error(f"排程非同步任務失敗: {e}")
    
    async def _handle_transcribe_done(self, payload: Dict[str, Any]):
        """處理轉譯完成事件"""
        try:
            session_id = payload.get("session_id")
            if not session_id:
                logger.warning("轉譯完成事件缺少 session_id")
                return
            
            # 從 payload 取得 result
            result = payload.get("result")
            
            if not result:
                # 從 Store 取得最後的轉譯結果
                last_transcription = get_session_last_transcription(session_id)(store.state)
                if last_transcription:
                    text = last_transcription.get("full_text", "")
                    language = last_transcription.get("language")
                    duration = last_transcription.get("duration")
                else:
                    logger.warning(f"Session {session_id} 沒有轉譯結果")
                    return
            else:
                # 從 result 物件提取資料
                text = ""
                language = None
                duration = None
                
                if result:
                    if hasattr(result, "full_text"):
                        text = result.full_text.strip() if result.full_text else ""
                    if hasattr(result, "language"):
                        language = result.language
                    if hasattr(result, "duration"):
                        duration = result.duration
            
            if not text:
                logger.warning(f"Session {session_id} 的轉譯結果為空")
                return
            
            # 發送 SSE 事件
            event_data = TranscribeDoneEvent(
                session_id=session_id,
                text=text,
                confidence=None,
                language=language,
                duration=duration,
                timestamp=datetime.now().isoformat()
            )
            
            await self._send_sse_event(session_id, SSEEventTypes.TRANSCRIBE_DONE, event_data.model_dump())
            
            logger.info(f'📤 轉譯結果已推送 [session: {session_id}]: "{text[:100]}..."')
            
        except Exception as e:
            logger.error(f"處理轉譯完成事件失敗: {e}")
    
    async def _handle_asr_feedback_play(self, payload: Dict[str, Any]):
        """處理 ASR 回饋音播放事件"""
        try:
            # 處理 payload 可能是字串、dict 或 immutables.Map 的情況
            session_id = None
            
            if isinstance(payload, str):
                session_id = payload
            elif hasattr(payload, 'get'):  # 處理 dict 和 immutables.Map
                session_id = payload.get("session_id")
                # 如果是 immutables.Map，session_id 可能也是 immutables.Map
                if hasattr(session_id, 'get'):
                    session_id = str(session_id) if session_id else None
            
            if not session_id:
                # 靜默返回，可能是其他 API 的 session
                logger.info(f"ASR 回饋音播放事件缺少 session_id，payload: {payload}")
                return
            
            # 發送 SSE 事件
            event_data = PlayASRFeedbackEvent(
                session_id=session_id,
                command="play",
                timestamp=datetime.now().isoformat()
            )
            
            await self._send_sse_event(session_id, SSEEventTypes.PLAY_ASR_FEEDBACK, event_data.model_dump())
            
            logger.info(f"🔊 ASR 回饋音播放指令已推送 [session: {session_id}]")
            
        except Exception as e:
            logger.error(f"處理 ASR 回饋音播放事件失敗: {e}")
    
    async def _handle_asr_feedback_stop(self, payload: Dict[str, Any]):
        """處理 ASR 回饋音停止事件"""
        try:
            # 處理 payload 可能是字串、dict 或 immutables.Map 的情況
            session_id = None
            
            if isinstance(payload, str):
                session_id = payload
            elif hasattr(payload, 'get'):  # 處理 dict 和 immutables.Map
                session_id = payload.get("session_id")
                # 如果是 immutables.Map，session_id 可能也是 immutables.Map
                if hasattr(session_id, 'get'):
                    session_id = str(session_id) if session_id else None
            
            if not session_id:
                # 靜默返回，可能是其他 API 的 session
                logger.info(f"ASR 回饋音停止事件缺少 session_id，payload: {payload}")
                return
            
            # 發送 SSE 事件
            event_data = PlayASRFeedbackEvent(
                session_id=session_id,
                command="stop",
                timestamp=datetime.now().isoformat()
            )
            
            await self._send_sse_event(session_id, SSEEventTypes.PLAY_ASR_FEEDBACK, event_data.model_dump())
            
            logger.info(f"🔇 ASR 回饋音停止指令已推送 [session: {session_id}]")
            
        except Exception as e:
            logger.error(f"處理 ASR 回饋音停止事件失敗: {e}")
    
    async def initialize(self):
        """初始化 HTTP SSE 伺服器"""
        if not self.http_config.enabled:
            return False
        
        try:
            # 設定 Store 監聽器
            self._setup_store_listeners()
            
            self.is_running = True
            logger.info(f"✅ HTTP SSE 伺服器已初始化")
            return True
            
        except Exception as e:
            logger.error(f"❌ HTTP SSE 初始化失敗: {e}")
            return False
    
    async def start(self):
        """啟動 HTTP SSE 伺服器"""
        if not self.is_running:
            await self.initialize()
        
        if not self.is_running:
            return
        
        # 儲存當前事件循環
        self.loop = asyncio.get_running_loop()
        
        # 設定 uvicorn 配置
        config = uvicorn.Config(
            app=self.app,
            host=self.http_config.host,
            port=self.http_config.port,
            log_level="warning"  # 減少 uvicorn 的日誌輸出
        )
        
        # 建立伺服器
        server = uvicorn.Server(config)
        
        logger.info(f"🚀 HTTP SSE 伺服器啟動於 http://{self.http_config.host}:{self.http_config.port}")
        
        # 啟動伺服器
        await server.serve()
    
    def stop(self):
        """停止 HTTP SSE 伺服器"""
        if not self.is_running:
            return
        
        logger.info("🛑 正在停止 HTTP SSE 伺服器...")
        self.is_running = False
        
        # 清理所有 SSE 連線
        for session_id in list(self.sse_connections.keys()):
            queue = self.sse_connections[session_id]
            asyncio.create_task(queue.put(None))  # 發送結束信號
        
        # 清理所有 SSE tasks
        for session_id, task in self.sse_tasks.items():
            if not task.done():
                task.cancel()
        
        self.sse_connections.clear()
        self.sse_tasks.clear()
        
        # 清理 Store 訂閱
        if self.store_subscription:
            self.store_subscription.dispose()
        
        logger.info("✅ HTTP SSE 伺服器已停止")


# 模組級單例
http_sse_server = HTTPSSEServer()


async def initialize():
    """初始化 HTTP SSE 伺服器（供 main.py 調用）"""
    return await http_sse_server.initialize()


async def start():
    """啟動 HTTP SSE 伺服器（供 main.py 調用）"""
    await http_sse_server.start()


def stop():
    """停止 HTTP SSE 伺服器（供 main.py 調用）"""
    http_sse_server.stop()


# 測試用主程式
if __name__ == "__main__":
    import asyncio
    
    async def test_server():
        """測試 HTTP SSE 伺服器"""
        logger.info("🚀 啟動 HTTP SSE 伺服器測試...")
        
        if await initialize():
            logger.info("✅ HTTP SSE 伺服器已啟動")
            
            # 啟動伺服器
            await start()
        else:
            logger.error("❌ HTTP SSE 伺服器啟動失敗")
    
    asyncio.run(test_server())