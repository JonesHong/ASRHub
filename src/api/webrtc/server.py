"""
WebRTC 伺服器實現

使用 LiveKit 實現 WebRTC 通訊，支援雙向音訊傳輸與 ASR 結果廣播。
仿照 http_sse 的架構風格實作。
"""

import asyncio
import json
from typing import Optional, Dict, Any
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from src.api.webrtc.signals import WebRTCSignals, LiveKitEventTypes
from src.api.webrtc.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    StartSessionRequest,
    StartSessionResponse,
    StopSessionRequest,
    StopSessionResponse,
    SessionStatusResponse,
    RoomStatusResponse,
    ErrorResponse,
    SessionStatus,
)
from src.api.webrtc.room_manager import room_manager

from src.store.main_store import store
from src.store.sessions.sessions_action import (
    create_session,
    start_listening,
    delete_session,
)
from src.store.sessions.sessions_selector import (
    get_session_by_id,
    get_all_sessions,
)

from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.utils.id_provider import new_id


class WebRTCServer:
    """WebRTC 伺服器"""
    
    def __init__(self):
        """初始化 WebRTC 伺服器"""
        self.config_manager = ConfigManager()
        self.webrtc_config = self.config_manager.api.webrtc
        
        if not self.webrtc_config.enabled:
            logger.info("WebRTC 服務已停用")
            return
        
        # FastAPI 應用程式
        self.app = FastAPI(
            title="ASR Hub WebRTC API",
            version="1.0.0",
            description="語音識別中介服務 WebRTC API (LiveKit)"
        )
        
        # 系統狀態
        self.is_running = False
        
        # 設定路由
        self._setup_routes()
        
        # 設定中介軟體
        self._setup_middleware()
    
    def _setup_middleware(self):
        """設定中介軟體"""
        # CORS 設定
        cors_origins = ["*"]  # 預設允許所有來源
        if hasattr(self.webrtc_config, 'cors_origins'):
            cors_origins = self.webrtc_config.cors_origins
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """設定 API 路由"""
        
        # === 唯一的 REST 端點 ===
        @self.app.post(WebRTCSignals.CREATE_SESSION, response_model=CreateSessionResponse)
        async def create_session_signal(request: CreateSessionRequest):
            """建立新的 ASR session 並生成 LiveKit token
            
            所有其他控制操作都透過 DataChannel 進行：
            - start_listening: 透過 DataChannel 發送控制命令
            - wake 控制: 透過 DataChannel 發送控制命令
            - 狀態查詢: 透過 DataChannel 發送查詢命令
            """
            return await self._handle_create_session(request)
        
        # 所有其他操作都已移至 DataChannel 處理
        # 參見 room_manager.py 的 _handle_data_channel_message 方法
    
    async def _handle_create_session(self, request: CreateSessionRequest) -> CreateSessionResponse:
        """處理建立 Session 請求"""
        try:
            # 使用提供的 request_id 或生成新的
            request_id = request.request_id if request.request_id else new_id()
            
            # 將 SessionStrategy 轉換為內部 Strategy
            # WebRTC 預設使用 NON_STREAMING（即時轉譯）
            from src.interface.strategy import Strategy
            internal_strategy = Strategy.NON_STREAMING
            
            # 分發到 PyStoreX Store
            action = create_session(
                strategy=internal_strategy,
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
            
            # 生成 LiveKit token
            token = room_manager.generate_token(session_id)
            
            # 添加 session 到 room manager
            room_manager.add_session(session_id, request.metadata)
            
            logger.info(f"✅ Session 建立成功: {session_id} (策略: {request.strategy})")
            
            # 返回資訊
            connect_host = self.webrtc_config.host
            base_url = f"http://{connect_host}:{self.webrtc_config.port}"
            
            return CreateSessionResponse(
                session_id=session_id,
                request_id=request_id,
                token=token,
                room_name=self.webrtc_config.livekit.room_name,
                livekit_url=self.webrtc_config.livekit.url,
                api_url=base_url + WebRTCSignals.API_PREFIX
            )
            
        except Exception as e:
            logger.error(f"建立 Session 失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    # 所有控制操作都已移至 DataChannel 處理
    # 包括：start_listening、wake 控制、狀態查詢
    # 參見 room_manager.py 的 _handle_data_channel_message 方法
    
    async def initialize(self):
        """初始化 WebRTC 伺服器"""
        if not self.webrtc_config.enabled:
            return False
        
        try:
            # 初始化 Room Manager
            await room_manager.initialize()
            
            # 以伺服器身份連線到 LiveKit 房間
            connected = await room_manager.connect_as_server()
            if not connected:
                logger.warning("⚠️ 無法連線到 LiveKit 房間，將在背景重試")
            
            self.is_running = True
            # 初始化成功，不需要重複日誌
            return True
            
        except Exception as e:
            logger.error(f"❌ WebRTC 初始化失敗: {e}")
            return False
    
    async def start(self):
        """啟動 WebRTC 伺服器"""
        if not self.is_running:
            await self.initialize()
        
        if not self.is_running:
            return
        
        # 設定 uvicorn 配置
        config = uvicorn.Config(
            app=self.app,
            host=self.webrtc_config.host,
            port=self.webrtc_config.port,
            log_level="warning"  # 減少 uvicorn 的日誌輸出
        )
        
        # 建立伺服器
        server = uvicorn.Server(config)
        
        # 啟動訊息由 main.py 統一顯示
        
        # 啟動伺服器
        await server.serve()
    
    async def stop(self):
        """停止 WebRTC 伺服器"""
        if not self.is_running:
            return
        
        logger.info("🛑 正在停止 WebRTC 伺服器...")
        self.is_running = False
        
        # 清理 Room Manager
        await room_manager.cleanup()
        
        logger.info("✅ WebRTC 伺服器已停止")


# 模組級單例
webrtc_server = WebRTCServer()


async def initialize():
    """初始化 WebRTC 伺服器（供 main.py 調用）"""
    return await webrtc_server.initialize()


async def start():
    """啟動 WebRTC 伺服器（供 main.py 調用）"""
    await webrtc_server.start()


async def stop():
    """停止 WebRTC 伺服器（供 main.py 調用）"""
    await webrtc_server.stop()


# 測試用主程式
if __name__ == "__main__":
    import asyncio
    
    async def test_server():
        """測試 WebRTC 伺服器"""
        logger.info("🚀 啟動 WebRTC 伺服器測試...")
        
        if await initialize():
            logger.info("✅ WebRTC 伺服器已啟動")
            
            # 啟動伺服器
            await start()
        else:
            logger.error("❌ WebRTC 伺服器啟動失敗")
    
    asyncio.run(test_server())