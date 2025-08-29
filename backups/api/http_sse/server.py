"""
Ultra-Thin HTTP SSE Server
純協議轉換層 - 只負責 HTTP/SSE 協議，所有業務邏輯由 SessionEffects 處理
"""

import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.utils.logger import logger
from src.store import get_global_store
from src.store.sessions import sessions_actions as actions
from src.config.manager import ConfigManager
from .sse_event_stream import create_selector_event_stream

# 模組級變數
store = get_global_store()
config_manager = ConfigManager()


class HTTPSSEServer:
    """
    極簡 HTTP SSE Server
    
    責任：
    1. 接收 HTTP 請求
    2. 派發 PyStoreX actions
    3. 訂閱並轉發 store 事件
    
    不負責：
    - 音訊格式轉換
    - 音訊緩衝管理
    - 轉譯觸發決策
    - 狀態輪詢
    """
    
    def __init__(self):
        """初始化極簡 SSE Server"""
        self.app = FastAPI(
            title="ASR Hub Ultra-Thin SSE API",
            version="0.3.0",
            description="純協議轉換層 - 業務邏輯由 SessionEffects 處理"
        )
        
        # 配置
        self.config = config_manager.api.http_sse
        
        # Store 引用
        self.store = store
        
        # 設置中間件
        self._setup_middleware()
        
        # 設置路由
        self._setup_routes()
        
        logger.info("🚀 Ultra-Thin SSE Server 初始化完成")
    
    def _setup_middleware(self):
        """設置中間件"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """設置路由 - 只轉發，不處理"""
        
        # ========================================
        # Session 管理端點
        # ========================================
        
        @self.app.post("/session")
        async def create_session(request: Request):
            """創建 Session - 只派發 action"""
            try:
                body = await request.json()
                session_id = body.get("session_id")
                
                if not session_id:
                    raise HTTPException(status_code=400, detail="Missing session_id")
                
                # 只派發 action，不處理
                # create_session expects (session_id, strategy=FSMStrategy.NON_STREAMING)
                from src.store.sessions.sessions_state import FSMStrategy
                strategy = body.get("strategy", FSMStrategy.NON_STREAMING)
                self.store.dispatch(actions.create_session(session_id, strategy))
                
                logger.info(f"📤 Dispatched create_session action: {session_id[:8]}...")
                
                return {
                    "status": "accepted",
                    "session_id": session_id,
                    "message": "Session creation action dispatched"
                }
                
            except Exception as e:
                logger.error(f"Failed to dispatch create_session: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.delete("/session/{session_id}")
        async def destroy_session(session_id: str):
            """銷毀 Session - 只派發 action"""
            try:
                # 只派發 action
                # destroy_session expects (session_id)
                self.store.dispatch(actions.destroy_session(session_id))
                
                # Session 已由 Store 處理
                
                logger.info(f"📤 Dispatched destroy_session action: {session_id[:8]}...")
                
                return {
                    "status": "accepted",
                    "message": "Session destruction action dispatched"
                }
                
            except Exception as e:
                logger.error(f"Failed to dispatch destroy_session: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/session/status/{session_id}")
        async def get_session_status(session_id: str):
            """獲取 Session 狀態 - 從 store 讀取"""
            try:
                state = self.store.get_state()
                sessions = state.get("sessions", {})
                
                if session_id not in sessions:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                session = sessions[session_id]
                
                # 直接返回 session 狀態，不處理
                return {
                    "session_id": session_id,
                    "state": session.get("fsm_state"),
                    "created_at": session.get("created_at"),
                    "last_activity": session.get("last_activity")
                }
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get session status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========================================
        # 音訊接收端點
        # ========================================
        
        @self.app.post("/audio/{session_id}")
        async def receive_audio_chunk(session_id: str, request: Request):
            """接收音訊 - 只派發 action，不處理"""
            try:
                # 讀取音訊數據
                audio_data = await request.body()
                
                if not audio_data:
                    raise HTTPException(status_code=400, detail="No audio data")
                
                # 獲取 metadata
                content_type = request.headers.get("content-type", "audio/webm")
                
                # 只派發 action，不進行任何處理
                # audio_chunk_received expects (session_id, chunk_size=0, timestamp=None)
                self.store.dispatch(actions.audio_chunk_received(
                    session_id,
                    len(audio_data),
                    datetime.now().isoformat()
                ))
                
                logger.debug(f"📤 Dispatched audio_chunk_received: {session_id[:8]}... ({len(audio_data)} bytes)")
                
                return {
                    "status": "accepted",
                    "bytes_received": len(audio_data),
                    "message": "Audio chunk action dispatched"
                }
                
            except Exception as e:
                logger.error(f"Failed to dispatch audio_chunk: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/audio/metadata/{session_id}")
        async def receive_audio_metadata(session_id: str, request: Request):
            """接收音訊 metadata - 只派發 action"""
            try:
                metadata = await request.json()
                
                # 派發 metadata action
                # audio_metadata expects (session_id, audio_metadata)
                self.store.dispatch(actions.audio_metadata(
                    session_id,
                    metadata
                ))
                
                logger.info(f"📤 Dispatched audio_metadata: {session_id[:8]}...")
                
                return {
                    "status": "accepted",
                    "message": "Audio metadata action dispatched"
                }
                
            except Exception as e:
                logger.error(f"Failed to dispatch audio_metadata: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========================================
        # SSE 事件流端點
        # ========================================
        
        @self.app.get("/events/{session_id}")
        async def sse_event_stream(session_id: str):
            """SSE 事件流 - 訂閱並轉發 store 事件"""
            try:
                logger.info(f"🔌 SSE connection request: {session_id[:8]}...")
                
                # 檢查 session 是否存在
                state = self.store.get_state()
                if session_id not in state.get("sessions", {}):
                    raise HTTPException(status_code=404, detail="Session not found")
                
                # 使用新的 selector-based event stream
                return StreamingResponse(
                    create_selector_event_stream(self.store, session_id),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"
                    }
                )
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to create SSE stream: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========================================
        # 控制端點
        # ========================================
        
        @self.app.post("/control/{session_id}/start")
        async def start_recording(session_id: str):
            """開始錄音 - 派發 action"""
            try:
                # start_recording expects (session_id, strategy)
                from src.store.sessions.sessions_state import FSMStrategy
                self.store.dispatch(actions.start_recording(
                    session_id,
                    FSMStrategy.NON_STREAMING
                ))
                
                return {"status": "accepted", "message": "Start recording action dispatched"}
                
            except Exception as e:
                logger.error(f"Failed to dispatch start_recording: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/control/{session_id}/stop")
        async def stop_recording(session_id: str):
            """停止錄音 - 派發 action"""
            try:
                # end_recording expects (session_id, trigger, duration)
                self.store.dispatch(actions.end_recording(
                    session_id,
                    "manual",  # trigger: manual stop
                    0  # duration: unknown
                ))
                
                return {"status": "accepted", "message": "Stop recording action dispatched"}
                
            except Exception as e:
                logger.error(f"Failed to dispatch end_recording: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/control/{session_id}/reset")
        async def reset_session(session_id: str):
            """重置 Session - 派發 action"""
            try:
                # fsm_reset expects (session_id)
                self.store.dispatch(actions.fsm_reset(session_id))
                
                return {"status": "accepted", "message": "Reset action dispatched"}
                
            except Exception as e:
                logger.error(f"Failed to dispatch fsm_reset: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========================================
        # 健康檢查
        # ========================================
        
        @self.app.get("/health")
        async def health_check():
            """健康檢查"""
            return {
                "status": "healthy",
                "server": "ultra-thin",
                "version": "0.3.0",
                "timestamp": datetime.now().isoformat()
            }
    
    async def start(self, host: str = "0.0.0.0", port: int = None):
        """啟動伺服器"""
        port = port or self.config.port
        
        logger.info(f"🚀 Starting Ultra-Thin SSE Server on {host}:{port}")
        
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        await server.serve()


# 便利函數
def create_ultra_thin_server() -> HTTPSSEServer:
    """創建極簡 SSE Server 實例"""
    return HTTPSSEServer()


if __name__ == "__main__":
    # 測試運行
    import asyncio
    
    async def main():
        server = create_ultra_thin_server()
        await server.start()
    
    asyncio.run(main())