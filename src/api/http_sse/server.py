"""
ASR Hub HTTP SSE Server
實作基於 Server-Sent Events 的 HTTP API
"""

import asyncio
import json
from typing import Dict, Any, Optional, Set
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from src.api.base import APIBase, APIResponse
from src.api.http_sse.routes import routes
from src.audio.converter import AudioConverter
from src.utils.logger import logger
from src.store import get_global_store
from src.store.sessions import sessions_actions, sessions_selectors
from src.store.sessions.sessions_state import translate_fsm_state
from src.core.exceptions import APIError, SessionError
from src.config.manager import ConfigManager
from src.core.audio_queue_manager import get_audio_queue_manager

# 模組級變數
store = get_global_store()
audio_queue_manager = get_audio_queue_manager()
config_manager = ConfigManager()

class SSEServer(APIBase):
    """
    HTTP Server-Sent Events API 實作
    提供基於 SSE 的即時語音轉文字服務
    """
    
    def __init__(self, provider_manager=None):
        """
        初始化 SSE Server
        使用 ConfigManager 獲取配置
        
        Args:
            provider_manager: Provider 管理器（可選）
        """
        # 初始化父類
        super().__init__()
        
        # 使用模組級變數獲取配置
        sse_config = config_manager.api.http_sse
        
        self.app = FastAPI(title="ASR Hub SSE API", version="0.1.0")
        self.provider_manager = provider_manager
        
        # SSE 連線管理
        self.sse_connections: Dict[str, asyncio.Queue] = {}
        self.audio_buffers: Dict[str, bytearray] = {}
        self.audio_params: Dict[str, Dict[str, Any]] = {}  # 保存音頻參數
        self.processed_sessions: Set[str] = set()  # 追蹤已處理的 session
        
        # 設定路由
        self._setup_routes()
        
        # 設定 CORS
        if sse_config.cors_enabled:
            self._setup_cors()
        
        # 伺服器配置
        self.host = sse_config.host
        self.port = sse_config.port
        self.max_connections = sse_config.max_connections
        self.timeout = sse_config.request_timeout
        
        # Uvicorn 伺服器
        self.server = None
    
    # ========== 通用輔助方法 ==========
    
    def _create_response(self, action: str, session_id: str, **kwargs) -> Dict[str, Any]:
        """建立標準化回應"""
        response = {
            "status": "success",
            "action": action,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
        response.update(kwargs)
        return response
    
    def create_success_response(self, data: Dict[str, Any], session_id: str = None) -> Dict[str, Any]:
        """建立成功回應"""
        response = {"status": "success", "timestamp": datetime.now().isoformat()}
        if session_id:
            response["session_id"] = session_id
        response.update(data)
        return response
    
    def create_error_response(self, message: str, session_id: str = None) -> Dict[str, Any]:
        """建立錯誤回應"""
        response = {"status": "error", "message": message, "timestamp": datetime.now().isoformat()}
        if session_id:
            response["session_id"] = session_id
        return response
    
    async def _handle_simple_action(self, session_id: str, action_name: str, 
                                   dispatch_action, log_message: str,
                                   **extra_fields) -> Dict[str, Any]:
        """處理簡單的 action（無請求參數）"""
        try:
            # 對於 chunk_upload_start 和需要 session 的 action，先確保 session 存在
            if action_name in ['chunk_upload_start', 'upload_file', 'recording_start']:
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    # 如果 session 不存在，先創建一個
                    logger.info(f"Session {session_id} 不存在，自動創建 (來自 {action_name})")
                    store.dispatch(sessions_actions.create_session(session_id, "batch"))
            
            store.dispatch(dispatch_action(session_id))
            logger.info(f"{log_message} - Session: {session_id}")
            
            if session_id in self.sse_connections:
                event_data = {
                    "type": action_name,
                    "timestamp": datetime.now().isoformat()
                }
                event_data.update(extra_fields)
                await self._send_sse_event(session_id, "action_received", event_data)
            
            return self._create_response(action_name, session_id, **extra_fields)
            
        except Exception as e:
            logger.error(f"{log_message}錯誤：{e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _handle_action_with_params(self, session_id: str, request: Request,
                                        action_name: str, dispatch_action,
                                        log_message: str, param_extractor=None) -> Dict[str, Any]:
        """處理帶參數的 action"""
        try:
            data = await request.json() if request.headers.get("content-type") == "application/json" else {}
            
            # 提取參數
            params = param_extractor(data) if param_extractor else data
            
            # 分發動作
            if isinstance(params, dict):
                store.dispatch(dispatch_action(session_id, **params))
            else:
                store.dispatch(dispatch_action(session_id, params))
            
            # 記錄日誌
            if isinstance(params, dict):
                param_str = ", ".join(f"{k}: {v}" for k, v in params.items())
            else:
                param_str = str(params)
            logger.info(f"{log_message} - Session: {session_id}, {param_str}")
            
            # 發送 SSE 事件
            if session_id in self.sse_connections:
                event_data = {"type": action_name, "timestamp": datetime.now().isoformat()}
                if isinstance(params, dict):
                    event_data.update(params)
                await self._send_sse_event(session_id, "action_received", event_data)
            
            # 返回響應
            return self._create_response(action_name, session_id, **params if isinstance(params, dict) else {})
            
        except Exception as e:
            logger.error(f"{log_message}錯誤：{e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _handle_state_change(self, session_id: str, new_state: str, message: str) -> Dict[str, Any]:
        """處理狀態變更"""
        store.dispatch(sessions_actions.update_session_state(session_id, new_state))
        await self._send_sse_event(session_id, "status", {
            "state": translate_fsm_state(new_state),
            "state_code": new_state,
            "message": message
        })
        return self.create_success_response({"state": translate_fsm_state(new_state)}, session_id)
        
    def _setup_cors(self):
        """設定 CORS 中間件"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 生產環境應該限制來源
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """設定 API 路由"""

        # ========== Session Management Endpoints ==========
        
        @self.app.post(f"/{routes['SESSION_START_LISTENING']}/{{session_id}}")
        async def start_listening(session_id: str, request: Request):
            """開始監聽音訊"""
            return await self._handle_action_with_params(
                session_id, request, "start_listening",
                lambda sid, audio_format="pcm": sessions_actions.start_listening(sid, audio_format),
                "開始監聽",
                lambda data: {"audio_format": data.get("audio_format", "pcm")}
            )
        
        # ========== Upload Management Endpoints ==========
        
        @self.app.post(f"/{routes['UPLOAD_FILE']}/{{session_id}}")
        async def upload_file_start(session_id: str):
            """開始檔案上傳"""
            return await self._handle_simple_action(
                session_id, "upload_file",
                sessions_actions.upload_file,
                "開始檔案上傳"
            )
        
        @self.app.post(f"/{routes['UPLOAD_FILE_DONE']}/{{session_id}}")
        async def upload_file_done(session_id: str):
            """完成檔案上傳"""
            return await self._handle_simple_action(
                session_id, "upload_file_done",
                sessions_actions.upload_file_done,
                "完成檔案上傳"
            )
        
        @self.app.post(f"/{routes['UPLOAD_CHUNK_START']}/{{session_id}}")
        async def chunk_upload_start(session_id: str):
            """開始分塊上傳"""
            return await self._handle_simple_action(
                session_id, "chunk_upload_start",
                sessions_actions.chunk_upload_start,
                "開始分塊上傳"
            )
        
        @self.app.post(f"/{routes['UPLOAD_CHUNK_DONE']}/{{session_id}}")
        async def chunk_upload_done(session_id: str):
            """完成分塊上傳"""
            return await self._handle_simple_action(
                session_id, "chunk_upload_done",
                sessions_actions.chunk_upload_done,
                "完成分塊上傳"
            )
        
        # ========== Recording Management Endpoints ==========
        
        @self.app.post(f"/{routes['RECORDING_START']}/{{session_id}}")
        async def start_recording(session_id: str, request: Request):
            """開始錄音"""
            return await self._handle_action_with_params(
                session_id, request, "start_recording",
                lambda sid, strategy="non_streaming": sessions_actions.start_recording(sid, strategy),
                "開始錄音",
                lambda data: {"strategy": data.get("strategy", "non_streaming")}
            )
        
        @self.app.post(f"/{routes['RECORDING_END']}/{{session_id}}")
        async def end_recording(session_id: str, request: Request):
            """結束錄音"""
            return await self._handle_action_with_params(
                session_id, request, "end_recording",
                lambda sid, trigger="manual", duration=0: sessions_actions.end_recording(sid, trigger, duration),
                "結束錄音",
                lambda data: {"trigger": data.get("trigger", "manual"), "duration": data.get("duration", 0)}
            )
        
        # ========== Transcription Endpoints ==========
        
        @self.app.post(f"/{routes['TRANSCRIPTION_BEGIN']}/{{session_id}}")
        async def begin_transcription(session_id: str):
            """開始轉譯"""
            return await self._handle_simple_action(
                session_id, "begin_transcription",
                sessions_actions.begin_transcription,
                "開始轉譯"
            )
        
        @self.app.post(f"/{routes['AUDIO_CHUNK']}/{{session_id}}")
        async def audio_chunk_received(session_id: str, request: Request):
            """
            接收音訊分塊
            """
            try:
                data = await request.json()
                chunk_data = data.get("chunk_data")
                chunk_id = data.get("chunk_id")
                
                if not chunk_data:
                    raise HTTPException(status_code=400, detail="Missing chunk_data")
                
                store.dispatch(sessions_actions.audio_chunk_received(
                    session_id,
                    chunk_data,
                    chunk_id
                ))
                
                logger.debug(f"接收音訊分塊 - Session: {session_id}, Chunk ID: {chunk_id}")
                
                if session_id in self.sse_connections:
                    await self._send_sse_event(session_id, "action_received", {
                        "type": "audio_chunk_received",
                        "chunk_id": chunk_id,
                        "timestamp": datetime.now().isoformat()
                    })
                
                return {
                    "status": "success",
                    "action": "audio_chunk_received",
                    "session_id": session_id,
                    "chunk_id": chunk_id,
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"接收音訊分塊錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get(f"/{routes['EVENTS']}/{{session_id}}")
        async def events_stream(session_id: str, request: Request):
            """
            SSE 事件流端點
            用於發送 PyStoreX 事件給前端
            """
            # 檢查或創建 session
            state = store.state if store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            
            if not session:
                # 自動創建 session，使用 batch 策略（適合 SSE 模式）
                store.dispatch(sessions_actions.create_session(
                    session_id,
                    "batch"  # 使用 batch 策略
                ))
                logger.info(f"自動創建 session: {session_id} (strategy: batch)")
            
            # 檢查連線數限制
            if len(self.sse_connections) >= self.max_connections:
                raise HTTPException(status_code=503, detail="Too many connections")
            
            # 建立 SSE 回應
            return StreamingResponse(
                self._events_stream(session_id, request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Cache-Control",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Content-Type": "text/event-stream; charset=utf-8"
                }
            )
        
        @self.app.get("/")
        async def root():
            """根路徑"""
            return {
                "service": "ASR Hub SSE API",
                "version": "0.1.0",
                "status": "running",
                "endpoints": {
                    "health": f"/{routes['HEALTH']}",
                    "events": f"/{routes['EVENTS']}/{{session_id}}",
                    "session_management": {
                        "create": f"POST /{routes['SESSION']}",
                        "get": f"GET /{routes['SESSION']}/{{session_id}}",
                        "delete": f"DELETE /{routes['SESSION']}/{{session_id}}",
                        "start_listening": f"POST /{routes['SESSION_START_LISTENING']}/{{session_id}}",
                        "status": f"GET /{routes['SESSION_STATUS']}/{{session_id}}",
                        "wake": f"POST /{routes['SESSION_WAKE']}/{{session_id}}",
                        "sleep": f"POST /{routes['SESSION_SLEEP']}/{{session_id}}",
                        "wake_timeout": f"PUT /{routes['SESSION_WAKE_TIMEOUT']}/{{session_id}}",
                        "wake_status": f"GET /{routes['SESSION_WAKE_STATUS']}/{{session_id}}",
                        "busy_start": f"POST /{routes['SESSION_BUSY_START']}/{{session_id}}",
                        "busy_end": f"POST /{routes['SESSION_BUSY_END']}/{{session_id}}"
                    },
                    "upload_management": {
                        "upload_audio": f"POST /{routes['UPLOAD']}/{{session_id}}",
                        "upload_file": f"POST /{routes['UPLOAD_FILE']}/{{session_id}}",
                        "upload_file_done": f"POST /{routes['UPLOAD_FILE_DONE']}/{{session_id}}",
                        "chunk_upload_start": f"POST /{routes['UPLOAD_CHUNK_START']}/{{session_id}}",
                        "chunk_upload_done": f"POST /{routes['UPLOAD_CHUNK_DONE']}/{{session_id}}"
                    },
                    "recording_management": {
                        "start": f"POST /{routes['RECORDING_START']}/{{session_id}}",
                        "end": f"POST /{routes['RECORDING_END']}/{{session_id}}"
                    },
                    "transcription": {
                        "begin": f"POST /{routes['TRANSCRIPTION_BEGIN']}/{{session_id}}",
                        "stream": f"GET /{routes['TRANSCRIBE']}/{{session_id}}",
                        "one_shot": f"POST /{routes['TRANSCRIBE_V1']}",
                        "audio_chunk": f"POST /{routes['AUDIO_CHUNK']}/{{session_id}}"
                    }
                }
            }

        @self.app.get(f"/{routes['HEALTH']}")
        async def health_check():
            """健康檢查端點"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "active_sessions": len(sessions_selectors.get_all_sessions(store.state)) if store else 0,
                "active_connections": len(self.sse_connections)
            }

        # ========== Session Control Endpoints ==========
        
        @self.app.get(f"/{routes['SESSION_STATUS']}/{{session_id}}")
        async def get_session_status(session_id: str):
            """獲取 session 狀態"""
            try:
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                current_state = session.get("state", "IDLE")
                return {
                    "status": "success",
                    "session_id": session_id,
                    "state": translate_fsm_state(current_state),
                    "state_code": current_state,
                    "created_at": session.get("created_at", datetime.now()).isoformat() if isinstance(session.get("created_at"), datetime) else session.get("created_at"),
                    "last_activity": session.get("last_activity", datetime.now()).isoformat() if isinstance(session.get("last_activity"), datetime) else session.get("last_activity")
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"獲取狀態錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post(f"/{routes['SESSION_WAKE']}/{{session_id}}")
        async def wake_session(session_id: str, request: Request):
            """喚醒 session"""
            try:
                data = await request.json() if request.headers.get("content-type") == "application/json" else {}
                source = data.get("source", "ui")
                wake_timeout = data.get("wake_timeout")
                
                # 使用 Store dispatch 喚醒 session
                store.dispatch(sessions_actions.wake_session(
                    session_id, 
                    source=source, 
                    wake_timeout=wake_timeout
                ))
                
                # 重新獲取 session
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if session:
                    await self._send_sse_event(session_id, "wake_word", {
                        "source": source,
                        "wake_time": session.get("wake_time").isoformat() if isinstance(session.get("wake_time"), datetime) else session.get("wake_time"),
                        "wake_timeout": session.get("wake_timeout", 30.0)
                    })
                    return {
                        "status": "success",
                        "message": f"Session awakened from {source}",
                        "wake_timeout": session.get("wake_timeout", 30.0)
                    }
                else:
                    raise HTTPException(status_code=404, detail="Session not found")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"喚醒 session 錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post(f"/{routes['SESSION_SLEEP']}/{{session_id}}")
        async def sleep_session(session_id: str):
            """休眠 session"""
            try:
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                # 使用 Store dispatch 清除喚醒狀態
                store.dispatch(sessions_actions.clear_wake_state(session_id))
                
                await self._send_sse_event(session_id, "state_change", {
                    "old_state": session.get("state", "IDLE"),
                    "new_state": "IDLE",
                    "event": "sleep"
                })
                
                return {
                    "status": "success",
                    "message": "Session set to sleep"
                }
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"休眠 session 錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put(f"/{routes['SESSION_WAKE_TIMEOUT']}/{{session_id}}")
        async def set_wake_timeout(session_id: str, request: Request):
            """設定喚醒超時"""
            try:
                data = await request.json()
                timeout = data.get("timeout")
                
                if timeout is None:
                    raise HTTPException(status_code=400, detail="Missing timeout parameter")
                
                timeout = float(timeout)
                if timeout <= 0:
                    raise HTTPException(status_code=400, detail="Timeout must be positive")
                
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                # 更新 wake_timeout
                store.dispatch(sessions_actions.update_session_metadata(
                    session_id, 
                    {"wake_timeout": timeout}
                ))
                
                return {
                    "status": "success",
                    "message": f"Wake timeout set to {timeout} seconds",
                    "wake_timeout": timeout
                }
                
            except HTTPException:
                raise
            except (ValueError, TypeError) as e:
                raise HTTPException(status_code=400, detail="Invalid timeout value")
            except Exception as e:
                logger.error(f"設定喚醒超時錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get(f"/{routes['SESSION_WAKE_STATUS']}/{{session_id}}")
        async def get_wake_status(session_id: str):
            """獲取喚醒狀態"""
            try:
                # 獲取系統狀態
                system_state = "IDLE"  # 暫時硬編碼，之後應該從 SystemListener 獲取
                
                # 使用 selector 獲取活躍的喚醒 sessions
                state = store.state if store else None
                active_wake_sessions = sessions_selectors.get_active_wake_sessions()(state) if state else []
                wake_stats = sessions_selectors.get_wake_stats()(state) if state else {}
                
                return {
                    "status": "success",
                    "system_state": system_state,
                    "active_wake_sessions": [
                        {
                            "id": s.get("id"),
                            "wake_source": s.get("wake_source"),
                            "wake_time": s.get("wake_time").isoformat() if isinstance(s.get("wake_time"), datetime) else s.get("wake_time"),
                            "wake_timeout": s.get("wake_timeout", 30.0),
                            "is_wake_expired": self._is_wake_expired(s)
                        }
                        for s in active_wake_sessions
                    ],
                    "stats": wake_stats
                }
                
            except Exception as e:
                logger.error(f"獲取喚醒狀態錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post(f"/{routes['SESSION_BUSY_START']}/{{session_id}}")
        async def start_busy_mode(session_id: str):
            """進入忙碌模式"""
            try:
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                # 更新狀態為 BUSY
                store.dispatch(sessions_actions.update_session_state(session_id, "BUSY"))
                
                await self._send_sse_event(session_id, "status", {
                    "state": translate_fsm_state("BUSY"),
                    "state_code": "BUSY",
                    "message": "Entered busy mode"
                })
                
                return {
                    "status": "success",
                    "state": translate_fsm_state("BUSY"),
                    "message": "Entered busy mode"
                }
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"進入忙碌模式錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post(f"/{routes['SESSION_BUSY_END']}/{{session_id}}")
        async def end_busy_mode(session_id: str):
            """結束忙碌模式"""
            try:
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                # 更新狀態為 LISTENING
                store.dispatch(sessions_actions.update_session_state(session_id, "LISTENING"))
                
                await self._send_sse_event(session_id, "status", {
                    "state": translate_fsm_state("LISTENING"),
                    "state_code": "LISTENING",
                    "message": "Exited busy mode"
                })
                
                return {
                    "status": "success",
                    "state": translate_fsm_state("LISTENING"),
                    "message": "Exited busy mode"
                }
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"結束忙碌模式錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get(f"/{routes['TRANSCRIBE']}/{{session_id}}")
        async def transcribe_sse(session_id: str, request: Request):
            """SSE 轉譯端點"""
            # 檢查 session
            if not self.validate_session(session_id):
                raise HTTPException(status_code=404, detail="Session not found")
            
            # 檢查連線數限制
            if len(self.sse_connections) >= self.max_connections:
                raise HTTPException(status_code=503, detail="Too many connections")
            
            # 建立 SSE 回應
            return StreamingResponse(
                self._sse_stream(session_id, request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # 停用 Nginx 緩衝
                }
            )

        @self.app.post(f"/{routes['UPLOAD']}/{{session_id}}")
        async def upload_audio(session_id: str, request: Request):
            """音訊上傳端點"""
            try:
                # 檢查 session，如果不存在則創建
                state = store.state if store else None
                session = sessions_selectors.get_session(session_id)(state) if state else None
                
                if not session:
                    # 自動創建 session
                    logger.info(f"Session {session_id} 不存在，自動創建 (來自音訊上傳)")
                    store.dispatch(sessions_actions.create_session(session_id, "batch"))
                    # 再次確認 session 已創建
                    state = store.state
                    session = sessions_selectors.get_session(session_id)(state)
                
                # 清理之前的處理狀態，允許新的上傳
                if session_id in self.processed_sessions:
                    self.processed_sessions.remove(session_id)
                    logger.info(f"清理已處理標記，允許新上傳 - Session: {session_id}")
                
                # 清理舊的音訊緩衝區
                if session_id in self.audio_buffers:
                    self.audio_buffers[session_id] = bytearray()
                    logger.info(f"清理舊的音訊緩衝區 - Session: {session_id}")
                
                # 解析 multipart form data
                form = await request.form()
                audio_file = form.get("audio")
                
                if not audio_file:
                    raise HTTPException(status_code=400, detail="Missing audio file")
                
                # 讀取音訊檔案內容
                audio_data = await audio_file.read()
                if not audio_data:
                    raise HTTPException(status_code=400, detail="Empty audio data")
                
                # 獲取檔案名和內容類型用於格式檢測
                filename = getattr(audio_file, 'filename', 'audio') or 'audio'
                content_type = getattr(audio_file, 'content_type', 'audio/wav') or 'audio/wav'
                
                logger.info(f"接收到音訊檔案: {filename}, 類型: {content_type}, 大小: {len(audio_data)} bytes")
                
                # 從檔案名和內容類型檢測音訊格式
                audio_format = 'wav'  # 預設格式
                
                # 從檔案名推測格式
                if filename:
                    file_ext = filename.split('.')[-1].lower()
                    if file_ext in ['webm', 'mp3', 'mp4', 'wav', 'ogg', 'pcm']:
                        audio_format = file_ext
                
                # 從內容類型確認格式
                if content_type:
                    if 'webm' in content_type:
                        audio_format = 'webm'
                    elif 'mp3' in content_type:
                        audio_format = 'mp3'
                    elif 'mp4' in content_type:
                        audio_format = 'mp4'
                    elif 'wav' in content_type:
                        audio_format = 'wav'
                    elif 'ogg' in content_type:
                        audio_format = 'ogg'
                
                # 解析音頻參數
                audio_params = {
                    'sample_rate': 16000,
                    'format': audio_format
                }
                
                # 從 headers 獲取音頻參數（如果有的話）
                if request.headers.get('X-Audio-Sample-Rate'):
                    try:
                        audio_params['sample_rate'] = int(request.headers['X-Audio-Sample-Rate'])
                        logger.info(f"音頻採樣率: {audio_params['sample_rate']} Hz")
                    except ValueError:
                        logger.warning(f"無效的採樣率: {request.headers['X-Audio-Sample-Rate']}")
                
                if request.headers.get('X-Audio-Format'):
                    audio_params['format'] = request.headers['X-Audio-Format']
                
                logger.info(f"檢測到音頻格式: {audio_params['format']}")
                
                # 保存音頻參數到 session
                if session_id not in self.audio_params:
                    self.audio_params = {}
                self.audio_params[session_id] = audio_params
                
                # 添加到緩衝區
                if session_id not in self.audio_buffers:
                    self.audio_buffers[session_id] = bytearray()
                
                self.audio_buffers[session_id].extend(audio_data)
                
                # 同時添加到 AudioQueueManager
                if audio_queue_manager:
                    await audio_queue_manager.push(session_id, audio_data)
                    logger.debug(f"已添加 {len(audio_data)} bytes 到 AudioQueueManager - Session: {session_id}")
                
                # 設置音訊元數據 - 這是關鍵！
                store.dispatch(sessions_actions.update_session_metadata(
                    session_id,
                    {
                        "audio_metadata": {
                            "format": audio_params['format'],
                            "sample_rate": audio_params['sample_rate'],
                            "filename": filename,
                            "content_type": content_type,
                            "size": len(audio_data)
                        }
                    }
                ))
                
                # 如果有 SSE 連線，發送音訊進行處理
                if session_id in self.sse_connections:
                    await self._process_audio_chunk(session_id, audio_data)
                
                return {"status": "success", "bytes_received": len(audio_data)}
                
            except Exception as e:
                logger.error(f"音訊上傳錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post(f"/{routes['SESSION']}")
        async def create_session(request: Request):
            """建立新 Session"""
            try:
                data = await request.json() if request.headers.get("content-type") == "application/json" else {}
                
                # 使用 Store dispatch 創建 session
                import uuid
                session_id = data.get("session_id", str(uuid.uuid4()))
                
                # Dispatch create_session action，從請求中獲取 strategy
                strategy = data.get("strategy", "batch")  # 預設使用 batch 策略
                store.dispatch(sessions_actions.create_session(session_id, strategy))
                logger.info(f"創建 session: {session_id} (strategy: {strategy})")
                
                # 更新 metadata 和 config
                if data.get("metadata"):
                    store.dispatch(sessions_actions.update_session_metadata(
                        session_id, data["metadata"]
                    ))
                if data.get("pipeline_config") or data.get("provider_config"):
                    store.dispatch(sessions_actions.update_session_config(
                        session_id,
                        pipeline_config=data.get("pipeline_config"),
                        provider_config=data.get("provider_config")
                    ))
                
                return {
                    "status": "success",
                    "session_id": session_id,
                    "created_at": datetime.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"建立 session 錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get(f"/{routes['SESSION']}/{{session_id}}")
        async def get_session(session_id: str):
            """獲取 Session 資訊"""
            # 使用 selector 獲取 session
            state = store.state if store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return session

        @self.app.delete(f"/{routes['SESSION']}/{{session_id}}")
        async def delete_session(session_id: str):
            """刪除 Session"""
            if not self.validate_session(session_id):
                raise HTTPException(status_code=404, detail="Session not found")
            
            # 關閉 SSE 連線
            if session_id in self.sse_connections:
                queue = self.sse_connections[session_id]
                await queue.put(None)  # 發送結束訊號
            
            # 清理資源
            self._cleanup_session(session_id)
            
            # 使用 Store dispatch 刪除 session
            store.dispatch(sessions_actions.destroy_session(session_id))
            
            return {"status": "success", "message": "Session deleted"}

        @self.app.post(f"/{routes['TRANSCRIBE_V1']}")
        async def transcribe_audio(request: Request):
            """一次性音訊轉譯端點（同步模式）"""
            try:
                # 解析表單資料
                form = await request.form()
                
                # 獲取音訊檔案路徑或資料
                audio_file = form.get("audio")
                if not audio_file:
                    raise HTTPException(status_code=400, detail="Missing audio parameter")
                
                # 獲取其他參數
                provider_name = form.get("provider", "whisper")
                language = form.get("language", "auto")
                
                # 建立臨時 session
                import uuid
                temp_session_id = str(uuid.uuid4())
                
                # 使用 Store dispatch 創建 session，一次性辨識使用 batch 策略
                store.dispatch(sessions_actions.create_session(temp_session_id, "batch"))
                logger.info(f"創建臨時 session: {temp_session_id} (strategy: batch)")
                store.dispatch(sessions_actions.update_session_metadata(
                    temp_session_id, {"type": "one-shot"}
                ))
                store.dispatch(sessions_actions.update_session_config(
                    temp_session_id,
                    provider_config={
                        "provider": provider_name,
                        "language": language
                    }
                ))
                
                try:
                    # 讀取音訊檔案
                    import os
                    import time
                    from src.audio import AudioChunk, AudioContainerFormat
                    from src.providers.manager import ProviderManager
                    # from src.pipeline.manager import PipelineManager  # REMOVED: Pipeline layer removed
                    
                    start_time = time.time()
                    
                    # 判斷音訊來源
                    if isinstance(audio_file, str):
                        # 檔案路徑
                        audio_path = audio_file
                        if not os.path.exists(audio_path):
                            raise HTTPException(status_code=400, detail=f"Audio file not found: {audio_path}")
                    else:
                        # 上傳的檔案
                        import tempfile
                        # 儲存上傳的檔案到臨時位置
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                            content = await audio_file.read()
                            tmp_file.write(content)
                            audio_path = tmp_file.name
                    
                    # 獲取 Provider Manager 實例
                    # SSEServer 應該有 provider_manager 的引用
                    provider_manager = getattr(self, 'provider_manager', None)
                    
                    # 如果沒有，嘗試從 store 中獲取
                    if not provider_manager:
                        provider_manager = getattr(store, 'provider_manager', None)
                    
                    # 如果還是沒有，創建一個新的
                    if not provider_manager:
                        from src.providers.manager import ProviderManager
                        from src.config.manager import ConfigManager
                        config_manager = ConfigManager()
                        provider_config = config_manager.providers
                        provider_manager = ProviderManager(provider_config)
                        await provider_manager.initialize()
                    
                    if not provider_manager:
                        raise HTTPException(status_code=500, detail="Provider Manager not available")
                    
                    # 使用 Provider 進行轉譯
                    logger.info(f"使用 {provider_name} 轉譯音訊檔案：{audio_path}")
                    
                    # 讀取音訊檔案
                    with open(audio_path, 'rb') as f:
                        audio_file_data = f.read()
                    
                    # 轉換音訊格式為 PCM
                    # AudioConverter already imported above
                    try:
                        # 從檔案副檔名推測格式
                        file_ext = os.path.splitext(audio_path)[1].lower().lstrip('.')
                        if file_ext == 'wav':
                            # WAV 檔案需要提取 PCM 資料
                            import wave
                            import io
                            try:
                                with wave.open(io.BytesIO(audio_file_data), 'rb') as wav_file:
                                    # 確認是 16kHz 單聲道
                                    if wav_file.getframerate() == 16000 and wav_file.getnchannels() == 1 and wav_file.getsampwidth() == 2:
                                        # 跳過 WAV 頭部，直接讀取 PCM 資料
                                        audio_data = wav_file.readframes(wav_file.getnframes())
                                    else:
                                        # 需要轉換
                                        audio_data = AudioConverter.convert_audio_file_to_pcm(
                                            audio_file_data,
                                            target_sample_rate=config_manager.stream.sample_rate,
                                            target_channels=config_manager.stream.channels,
                                            source_format='wav'
                                        )
                            except Exception:
                                # 如果 wave 模組無法處理，使用通用轉換
                                audio_data = AudioConverter.convert_audio_file_to_pcm(
                                    audio_file_data,
                                    target_sample_rate=config_manager.stream.sample_rate,
                                    target_channels=config_manager.stream.channels,
                                    source_format='wav'
                                )
                        elif file_ext == 'pcm':
                            # 純 PCM 格式，直接使用
                            audio_data = audio_file_data
                        else:
                            # 轉換為 PCM 格式
                            audio_data = AudioConverter.convert_audio_file_to_pcm(
                                audio_file_data,
                                target_sample_rate=config_manager.stream.sample_rate,
                                target_channels=config_manager.stream.channels,
                                source_format=file_ext
                            )
                    except Exception as e:
                        logger.error(f"音訊格式轉換失敗：{e}")
                        raise HTTPException(status_code=400, detail=f"音訊格式轉換失敗：{str(e)}")
                    
                    # 使用 ProviderManager 的 transcribe 方法（支援池化）
                    result = await provider_manager.transcribe(
                        audio_data=audio_data,
                        provider_name=provider_name,
                        language=language if language != "auto" else None
                    )
                    
                    # 計算處理時間
                    processing_time = time.time() - start_time
                    
                    # 格式化回應
                    # 從 metadata 中提取 segments
                    segments = []
                    if result.metadata and 'segments' in result.metadata:
                        segments = result.metadata['segments']
                    
                    response = {
                        "status": "success",
                        "transcript": {
                            "text": result.text,
                            "language": result.language or language,
                            "confidence": result.confidence,
                            "duration": result.audio_duration if hasattr(result, 'audio_duration') else None,
                            "segments": segments
                        },
                        "metadata": {
                            "provider": provider_name,
                            "session_id": session.id,
                            "processing_time": processing_time
                        }
                    }
                    
                    # 清理臨時檔案
                    if not isinstance(audio_file, str) and os.path.exists(audio_path):
                        os.unlink(audio_path)
                    
                    return response
                    
                finally:
                    # 清理臨時 session
                    store.dispatch(sessions_actions.destroy_session(temp_session_id))
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"轉譯錯誤：{e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
    
    async def _events_stream(self, session_id: str, request: Request):
        """
        事件流生成器（用於 /events/{session_id} 端點）
        監聽 PyStoreX store 的事件並發送給前端
        
        Args:
            session_id: Session ID
            request: FastAPI Request 物件
        """
        # 建立訊息佇列
        queue = asyncio.Queue()
        self.sse_connections[session_id] = queue
        
        try:
            # 發送初始連線事件
            yield self._format_sse_event("connected", {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })
            
            # 註冊 store 變化監聽器
            store_subscription = None
            if store:
                def on_store_change():
                    # 在異步上下文中處理 store 變化
                    asyncio.create_task(self._handle_store_change(session_id, queue))
                
                # 監聽 store 變化（如果 store 支持訂閱）
                if hasattr(store, 'subscribe'):
                    store_subscription = store.subscribe(on_store_change)
            
            # 啟動 store 事件監聽任務
            async def monitor_store_events():
                """監聽 store 事件並轉發"""
                last_state_hash = None
                last_transcription = None
                last_fsm_state = None
                polling_count = 0
                
                while True:
                    try:
                        await asyncio.sleep(0.05)  # 50ms 輪詢 (更頻繁)
                        polling_count += 1
                        
                        # 每秒記錄一次監聽狀態
                        if polling_count % 20 == 0:
                            logger.debug(f"SSE 監聽中 - Session: {session_id[:8]}... (輪詢 {polling_count})")
                        
                        # 獲取當前 session 狀態
                        state = store.state if store else None
                        session = sessions_selectors.get_session(session_id)(state) if state else None
                        
                        if session:
                            # 檢查轉譯結果變化
                            current_transcription = session.get("transcription")
                            if current_transcription and current_transcription != last_transcription:
                                last_transcription = current_transcription
                                logger.info(f"SSE: 檢測到新的轉譯結果 - Session: {session_id[:8]}...")
                                
                                # 廣播轉譯結果
                                await self._broadcast_transcription_result_sse(session_id, current_transcription, queue)
                            
                            # 檢查 FSM 狀態變化
                            current_fsm_state = session.get("fsm_state")
                            if current_fsm_state != last_fsm_state:
                                last_fsm_state = current_fsm_state
                                logger.debug(f"SSE: FSM 狀態變化 - Session: {session_id[:8]}... -> {current_fsm_state}")
                                
                                # 翻譯狀態為中文
                                translated_state = translate_fsm_state(current_fsm_state)
                                
                                await queue.put({
                                    "event": "status",
                                    "data": {
                                        "state": translated_state,
                                        "state_code": str(current_fsm_state) if current_fsm_state else "IDLE",
                                        "session_id": session_id,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                })
                            
                            # 檢查辨識狀態
                            current_state = session.get("state")
                            if current_state == "TRANSCRIBING":
                                await queue.put({
                                    "event": "action",
                                    "data": {
                                        "type": "[Session] Begin Transcription",
                                        "payload": {
                                            "session_id": session_id
                                        }
                                    }
                                })
                                    
                    except Exception as e:
                        logger.error(f"監聽 store 事件錯誤: {e}")
                        break
            
            # 啟動監聽任務
            monitor_task = asyncio.create_task(monitor_store_events())
            
            # 心跳任務
            async def heartbeat():
                while True:
                    await asyncio.sleep(30)
                    await queue.put({
                        "event": "heartbeat",
                        "data": {"timestamp": datetime.now().isoformat()}
                    })
            
            heartbeat_task = asyncio.create_task(heartbeat())
            
            # 主事件循環
            while True:
                if await request.is_disconnected():
                    logger.info(f"SSE 客戶端斷開連接 - Session: {session_id[:8]}...")
                    break
                
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    if event is None:
                        break
                    
                    yield self._format_sse_event(event["event"], event["data"])
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"事件流錯誤：{e}")
                    yield self._format_sse_event("error", {"message": str(e)})
                    break
            
        finally:
            # 清理
            if 'monitor_task' in locals():
                monitor_task.cancel()
            if 'heartbeat_task' in locals():
                heartbeat_task.cancel()
            if store_subscription and hasattr(store_subscription, 'dispose'):
                store_subscription.dispose()
            self._cleanup_session(session_id)
            
            yield self._format_sse_event("disconnected", {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })
    
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

    async def _broadcast_transcription_result_sse(self, session_id: str, result: Any, queue: asyncio.Queue):
        """
        廣播轉譯結果到 SSE 連接
        
        Args:
            session_id: Session ID
            result: 轉譯結果
            queue: SSE 事件隊列
        """
        try:
            # 首先轉換不可變物件為標準字典
            converted_result = self._convert_immutable_to_dict(result)
            
            # 處理不同類型的結果
            if isinstance(converted_result, dict):
                text = converted_result.get("text", "")
                confidence = converted_result.get("confidence", 0.95)
                language = converted_result.get("language", "zh")
            else:
                text = str(converted_result)
                confidence = 0.95
                language = "zh"
            
            # 發送 action 事件
            await queue.put({
                "event": "action",
                "data": {
                    "type": "[Session] Transcription Done",
                    "payload": {
                        "session_id": session_id,
                        "result": converted_result if isinstance(converted_result, dict) else {"text": text}
                    }
                }
            })
            
            # 發送 transcript 事件
            await queue.put({
                "event": "transcript",
                "data": {
                    "text": text,
                    "is_final": True,
                    "confidence": confidence,
                    "language": language,
                    "timestamp": datetime.now().isoformat()
                }
            })
            
            logger.info(f"SSE: 已廣播轉譯結果 - Session: {session_id[:8]}... - Text: {text[:50]}...")
            
        except Exception as e:
            logger.error(f"SSE 廣播轉譯結果失敗: {e}")
    
    async def _handle_store_change(self, session_id: str, queue: asyncio.Queue):
        """
        處理 store 變化（用於響應式監聽）
        
        Args:
            session_id: Session ID
            queue: SSE 事件隊列
        """
        try:
            state = store.state if store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            
            if session:
                # 檢查轉譯結果
                transcription = session.get("transcription")
                if transcription:
                    # 轉換 immutable 物件後再廣播
                    converted_transcription = self._convert_immutable_to_dict(transcription)
                    await self._broadcast_transcription_result_sse(session_id, converted_transcription, queue)
                    
        except Exception as e:
            logger.error(f"處理 store 變化失敗: {e}")
    
    async def _sse_stream(self, session_id: str, request: Request):
        """
        SSE 串流生成器
        
        Args:
            session_id: Session ID
            request: FastAPI Request 物件
        """
        # 建立訊息佇列
        queue = asyncio.Queue()
        self.sse_connections[session_id] = queue
        
        try:
            # 發送初始連線事件
            yield self._format_sse_event("connected", {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })
            
            # 心跳任務
            async def heartbeat():
                while True:
                    await asyncio.sleep(30)  # 每 30 秒發送心跳
                    await queue.put({
                        "event": "heartbeat",
                        "data": {"timestamp": datetime.now().isoformat()}
                    })
            
            heartbeat_task = asyncio.create_task(heartbeat())
            
            # 主事件循環
            while True:
                # 檢查客戶端是否斷線
                if await request.is_disconnected():
                    break
                
                try:
                    # 等待事件（超時設定）
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    if event is None:  # 結束訊號
                        break
                    
                    # 格式化並發送事件
                    yield self._format_sse_event(event["event"], event["data"])
                    
                except asyncio.TimeoutError:
                    continue  # 繼續等待
                except Exception as e:
                    logger.error(f"SSE 串流錯誤：{e}")
                    yield self._format_sse_event("error", {"message": str(e)})
                    break
            
        finally:
            # 清理
            heartbeat_task.cancel()
            self._cleanup_session(session_id)
            
            # 發送斷線事件
            yield self._format_sse_event("disconnected", {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })
    
    def _format_sse_event(self, event: str, data: Any) -> str:
        """
        格式化 SSE 事件，確保符合 HTML5 SSE 標準
        
        Args:
            event: 事件類型
            data: 事件資料
            
        Returns:
            SSE 格式字串
        """
        lines = []
        
        # 事件類型（必須在 data 之前）
        if event:
            lines.append(f"event: {event}")
        
        # 轉換不可變物件為可序列化物件
        converted_data = self._convert_immutable_to_dict(data)
        
        # 資料
        if isinstance(converted_data, (dict, list)):
            data_str = json.dumps(converted_data, ensure_ascii=False)
        else:
            data_str = str(converted_data)
        
        # SSE 規範要求每行資料都要有 "data: " 前綴
        # 處理多行數據
        for line in data_str.split('\n'):
            lines.append(f"data: {line}")
        
        # 添加唯一 ID（可選，但有助於調試）
        import time
        lines.append(f"id: {int(time.time() * 1000)}")
        
        # 事件結束需要兩個換行符
        return '\n'.join(lines) + '\n\n'
    
    async def _process_audio_chunk(self, session_id: str, audio_data: bytes):
        """
        處理音訊資料塊
        
        Args:
            session_id: Session ID
            audio_data: 音訊資料
        """
        # 對於串流模式，我們不在這裡處理音訊
        # 而是等待 stop 命令後統一處理
        # 這樣可以避免重複轉譯
        pass
    
    async def _process_all_audio(self, session_id: str):
        """
        處理所有緩衝的音訊資料
        
        Args:
            session_id: Session ID
        """
        try:
            # 檢查是否已經處理過
            if session_id in self.processed_sessions:
                logger.warning(f"Session {session_id} 已經處理過，跳過重複處理")
                return
            
            # 標記為已處理
            self.processed_sessions.add(session_id)
            logger.info(f"開始處理 Session {session_id} 的音訊資料")
            
            # 使用 selector 獲取 session
            state = store.state if store else None
            session = sessions_selectors.get_session(session_id)(state) if state else None
            if not session:
                raise Exception("Session not found")
            
            # 檢查是否有音訊資料
            if session_id not in self.audio_buffers or len(self.audio_buffers[session_id]) == 0:
                await self._send_sse_event(session_id, "error", {
                    "message": "沒有音訊資料",
                    "timestamp": datetime.now().isoformat()
                })
                return
            
            # 獲取完整音訊資料
            complete_audio = bytes(self.audio_buffers[session_id])
            logger.info(f"處理完整音訊，大小: {len(complete_audio)} bytes")
            
            # 獲取音頻參數
            audio_params = self.audio_params.get(session_id, {})
            audio_format = audio_params.get('format', 'pcm')  # 預設 PCM
            
            logger.info(f"音頻參數: 格式={audio_format}")
            
            # 發送進度事件
            await self._send_sse_event(session_id, "progress", {
                "percentage": 50,
                "message": "開始處理音訊...",
                "timestamp": datetime.now().isoformat()
            })
            
            # 檢查音訊格式並轉換
            from src.audio.converter import AudioConverter
            from src.audio import AudioChunk, AudioContainerFormat
            
            # 根據音頻格式決定是否需要轉換
            pcm_data = complete_audio
            
            if audio_format in ['webm', 'mp3', 'mp4', 'ogg']:  # WAV 檔案通常已包含 PCM 資料
                try:
                    # 需要轉換為 PCM
                    logger.info(f"轉換 {audio_format} 格式，原始大小: {len(complete_audio)} bytes")
                    
                    if audio_format == 'webm':
                        # WebM 特別處理
                        pcm_data = AudioConverter.convert_webm_to_pcm(complete_audio, sample_rate=config_manager.stream.sample_rate, channels=config_manager.stream.channels)
                    else:
                        # 其他格式使用通用轉換
                        pcm_data = AudioConverter.convert_audio_file_to_pcm(
                            complete_audio,
                            sample_rate=config_manager.stream.sample_rate,
                            channels=config_manager.stream.channels
                        )
                    
                    logger.info(f"轉換成功，PCM 大小: {len(pcm_data)} bytes")
                except Exception as e:
                    logger.error(f"音訊格式轉換失敗: {e}")
                    # 發送錯誤並返回
                    await self._send_sse_event(session_id, "error", {
                        "message": f"音訊格式轉換失敗: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    })
                    return
            else:
                # WAV 或 PCM 格式，直接使用
                logger.info(f"音頻已是可用格式 ({audio_format})，大小: {len(pcm_data)} bytes")
            
            # 建立 AudioChunk
            from src.audio import AudioEncoding, AudioMetadata, AudioSampleFormat
            
            # 建立 AudioMetadata
            metadata = AudioMetadata(
                sample_rate=config_manager.stream.sample_rate,
                channels=config_manager.stream.channels,
                format=AudioSampleFormat.INT16,  # 16-bit PCM
                container_format=AudioContainerFormat.WAV if audio_format == 'wav' else AudioContainerFormat.PCM,
                encoding=AudioEncoding.LINEAR16
            )
            
            # 建立 AudioChunk
            audio_chunk = AudioChunk(
                data=pcm_data,
                metadata=metadata
            )
            
            # 獲取 provider
            if not self.provider_manager:
                raise Exception("Provider manager not available")
            
            # Session 是 immutables.Map，需要用 get 方法
            provider_config = session.get('provider_config', {})
            if isinstance(provider_config, dict):
                provider_name = provider_config.get("provider", "whisper")
            else:
                provider_name = "whisper"
            
            # Pipeline 功能已移除，直接使用原始音訊
            processed_audio = audio_chunk.data
            
            # 執行轉譯
            logger.info(f"使用 {provider_name} 進行轉譯")
            
            # 發送部分結果
            await self._send_sse_event(session_id, "transcript", {
                "text": "正在進行語音辨識...",
                "is_final": False,
                "confidence": 0.0,
                "timestamp": datetime.now().isoformat()
            })
            
            # 使用 ProviderManager 的 transcribe 方法（支援池化）
            result = await self.provider_manager.transcribe(
                audio_data=processed_audio if processed_audio else pcm_data,
                provider_name=provider_name,
                language=provider_config.get("language", "zh") if isinstance(provider_config, dict) else "zh"
            )
            
            if result and result.text:
                # 發送最終結果
                await self._send_sse_event(session_id, "transcript", {
                    "text": result.text,
                    "is_final": True,
                    "confidence": result.confidence if hasattr(result, 'confidence') else 0.95,
                    "language": result.language if hasattr(result, 'language') else "zh",
                    "timestamp": datetime.now().isoformat()
                })
                
                logger.info(f"轉譯完成: {result.text[:50]}...")
            else:
                await self._send_sse_event(session_id, "error", {
                    "message": "無法辨識音訊內容",
                    "timestamp": datetime.now().isoformat()
                })
            
            # 清除緩衝區
            self.audio_buffers[session_id] = bytearray()
            
        except Exception as e:
            logger.error(f"處理音訊錯誤：{e}")
            await self._send_sse_event(session_id, "error", {
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    async def _send_sse_event(self, session_id: str, event: str, data: Any):
        """
        發送 SSE 事件
        
        Args:
            session_id: Session ID
            event: 事件類型
            data: 事件資料
        """
        if session_id in self.sse_connections:
            queue = self.sse_connections[session_id]
            await queue.put({"event": event, "data": data})
    
    def _cleanup_session(self, session_id: str):
        """
        清理 Session 相關資源
        
        Args:
            session_id: Session ID
        """
        # 移除 SSE 連線
        if session_id in self.sse_connections:
            del self.sse_connections[session_id]
        
        # 清理音訊緩衝
        if session_id in self.audio_buffers:
            del self.audio_buffers[session_id]
        
        # 清除音頻參數
        if session_id in self.audio_params:
            del self.audio_params[session_id]
        
        # 清理已處理標記
        if session_id in self.processed_sessions:
            self.processed_sessions.remove(session_id)
        
        logger.debug(f"清理 Session {session_id} 資源")
    
    def _is_wake_expired(self, session) -> bool:
        """檢查喚醒是否已超時"""
        import time
        if not session or not session.get("wake_time"):
            return False
        wake_timeout = session.get("wake_timeout", 30.0)
        return (time.time() - session["wake_time"]) > wake_timeout
    
    async def start(self):
        """啟動 SSE Server"""
        if self._running:
            logger.warning("SSE Server 已經在運行中")
            return
        
        logger.info(f"啟動 SSE Server: {self.host}:{self.port}")
        
        # 設定 Uvicorn 配置
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True
        )
        
        # 建立伺服器
        self.server = uvicorn.Server(config)
        self._running = True
        
        # 在背景執行
        asyncio.create_task(self.server.serve())
        
        logger.success(f"SSE Server 啟動成功: http://{self.host}:{self.port}")
    
    async def stop(self):
        """停止 SSE Server"""
        if not self._running:
            logger.warning("SSE Server 未在運行中")
            return
        
        logger.info("停止 SSE Server")
        
        # 關閉所有 SSE 連線
        for session_id in list(self.sse_connections.keys()):
            await self._send_sse_event(session_id, "server_shutdown", {
                "message": "Server is shutting down"
            })
            self._cleanup_session(session_id)
        
        # 停止伺服器
        if self.server:
            self.server.should_exit = True
            await self.server.shutdown()
        
        self._running = False
        logger.success("SSE Server 已停止")
    
    # handle_control_command 已移除 - 功能已拆分為專用端點：
    # - GET /session/status/{session_id} - 獲取狀態
    # - POST /session/wake/{session_id} - 喚醒 session
    # - POST /session/sleep/{session_id} - 休眠 session
    # - PUT /session/wake/timeout/{session_id} - 設定喚醒超時
    # - GET /session/wake/status/{session_id} - 獲取喚醒狀態
    # - POST /session/busy/start/{session_id} - 進入忙碌模式
    # - POST /session/busy/end/{session_id} - 結束忙碌模式
    
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
        # SSE 模式下不使用此方法
        return self.create_error_response(
            "Use SSE streaming for transcription",
            session_id
        )
    
    async def handle_transcribe_stream(self, session_id: str, audio_stream, params=None):
        """
        處理串流轉譯請求
        
        Args:
            session_id: Session ID
            audio_stream: 音訊串流
            params: 額外參數
        """
        # SSE 模式下不使用此方法
        yield self.create_error_response(
            "Use SSE streaming for transcription",
            session_id
        )