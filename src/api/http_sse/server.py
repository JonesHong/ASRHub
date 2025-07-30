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
from src.utils.logger import get_logger
from src.core.session_manager import SessionManager
from src.core.exceptions import APIError, SessionError
from src.config.manager import ConfigManager


class SSEServer(APIBase):
    """
    HTTP Server-Sent Events API 實作
    提供基於 SSE 的即時語音轉文字服務
    """
    
    def __init__(self, session_manager: SessionManager, provider_manager=None, pipeline_manager=None):
        """
        初始化 SSE Server
        使用 ConfigManager 獲取配置
        
        Args:
            session_manager: Session 管理器
            provider_manager: Provider 管理器（可選）
            pipeline_manager: Pipeline 管理器（可選）
        """
        # 從 ConfigManager 獲取配置
        config_manager = ConfigManager()
        sse_config = config_manager.api.http_sse
        
        # 轉換為字典以兼容父類
        config_dict = sse_config.to_dict()
        super().__init__(config_dict, session_manager)
        
        self.app = FastAPI(title="ASR Hub SSE API", version="0.1.0")
        self.logger = get_logger("api.sse")
        self.provider_manager = provider_manager
        self.pipeline_manager = pipeline_manager
        
        # SSE 連線管理
        self.sse_connections: Dict[str, asyncio.Queue] = {}
        self.audio_buffers: Dict[str, bytearray] = {}
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
        
        @self.app.get("/")
        async def root():
            """根路徑"""
            return {
                "service": "ASR Hub SSE API",
                "version": "0.1.0",
                "status": "running",
                "endpoints": {
                    "health": "/health",
                    "control": "/control",
                    "transcribe": "/transcribe/{session_id}",
                    "transcribe_v1": "/v1/transcribe",
                    "audio_upload": "/audio/{session_id}",
                    "session": "/session"
                }
            }
        
        @self.app.get("/health")
        async def health_check():
            """健康檢查端點"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "active_sessions": self.session_manager.get_session_count(),
                "active_connections": len(self.sse_connections)
            }
        
        @self.app.post("/control")
        async def control_command(request: Request):
            """控制指令端點"""
            try:
                data = await request.json()
                command = data.get("command")
                session_id = data.get("session_id")
                params = data.get("params", {})
                
                if not command or not session_id:
                    raise HTTPException(status_code=400, detail="Missing command or session_id")
                
                response = await self.handle_control_command(command, session_id, params)
                return response.to_dict()
                
            except Exception as e:
                self.logger.error(f"控制指令錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/transcribe/{session_id}")
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
        
        @self.app.post("/audio/{session_id}")
        async def upload_audio(session_id: str, request: Request):
            """音訊上傳端點"""
            try:
                # 檢查 session
                if not self.validate_session(session_id):
                    raise HTTPException(status_code=404, detail="Session not found")
                
                # 讀取音訊資料
                audio_data = await request.body()
                if not audio_data:
                    raise HTTPException(status_code=400, detail="Empty audio data")
                
                # 添加到緩衝區
                if session_id not in self.audio_buffers:
                    self.audio_buffers[session_id] = bytearray()
                
                self.audio_buffers[session_id].extend(audio_data)
                
                # 如果有 SSE 連線，發送音訊進行處理
                if session_id in self.sse_connections:
                    await self._process_audio_chunk(session_id, audio_data)
                
                return {"status": "success", "bytes_received": len(audio_data)}
                
            except Exception as e:
                self.logger.error(f"音訊上傳錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/session")
        async def create_session(request: Request):
            """建立新 Session"""
            try:
                data = await request.json() if request.headers.get("content-type") == "application/json" else {}
                
                session = self.session_manager.create_session(
                    metadata=data.get("metadata", {}),
                    pipeline_config=data.get("pipeline_config", {}),
                    provider_config=data.get("provider_config", {})
                )
                
                return {
                    "status": "success",
                    "session_id": session.id,
                    "created_at": session.created_at.isoformat()
                }
                
            except Exception as e:
                self.logger.error(f"建立 session 錯誤：{e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/session/{session_id}")
        async def get_session(session_id: str):
            """獲取 Session 資訊"""
            session = self.session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return session.to_dict()
        
        @self.app.delete("/session/{session_id}")
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
            
            # 刪除 session
            self.session_manager.delete_session(session_id)
            
            return {"status": "success", "message": "Session deleted"}
        
        @self.app.post("/v1/transcribe")
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
                session = self.session_manager.create_session(
                    metadata={"type": "one-shot"},
                    provider_config={
                        "provider": provider_name,
                        "language": language
                    }
                )
                
                try:
                    # 讀取音訊檔案
                    import os
                    import time
                    from src.models.audio import AudioChunk, AudioFormat
                    from src.providers.manager import ProviderManager
                    from src.pipeline.manager import PipelineManager
                    
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
                    
                    # 如果沒有，嘗試從 session_manager 獲取
                    if not provider_manager:
                        provider_manager = getattr(self.session_manager, 'provider_manager', None)
                    
                    # 如果還是沒有，創建一個新的
                    if not provider_manager:
                        from src.providers.manager import ProviderManager
                        from src.config.manager import ConfigManager
                        config_manager = ConfigManager()
                        provider_config = config_manager.get_config()['providers']
                        provider_manager = ProviderManager(provider_config)
                        await provider_manager.initialize()
                    
                    if not provider_manager:
                        raise HTTPException(status_code=500, detail="Provider Manager not available")
                    
                    # 使用 Provider 進行轉譯
                    self.logger.info(f"使用 {provider_name} 轉譯音訊檔案：{audio_path}")
                    
                    # 讀取音訊檔案
                    with open(audio_path, 'rb') as f:
                        audio_file_data = f.read()
                    
                    # 轉換音訊格式為 PCM
                    from src.utils.audio_utils import convert_audio_file_to_pcm
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
                                        audio_data = convert_audio_file_to_pcm(
                                            audio_file_data,
                                            output_sample_rate=16000,
                                            output_channels=1,
                                            input_format='wav'
                                        )
                            except Exception:
                                # 如果 wave 模組無法處理，使用通用轉換
                                audio_data = convert_audio_file_to_pcm(
                                    audio_file_data,
                                    output_sample_rate=16000,
                                    output_channels=1,
                                    input_format='wav'
                                )
                        elif file_ext == 'pcm':
                            # 純 PCM 格式，直接使用
                            audio_data = audio_file_data
                        else:
                            # 轉換為 PCM 格式
                            audio_data = convert_audio_file_to_pcm(
                                audio_file_data,
                                output_sample_rate=16000,
                                output_channels=1,
                                input_format=file_ext
                            )
                    except Exception as e:
                        self.logger.error(f"音訊格式轉換失敗：{e}")
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
                    self.session_manager.delete_session(session.id)
                    
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"轉譯錯誤：{e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
    
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
                    self.logger.error(f"SSE 串流錯誤：{e}")
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
        格式化 SSE 事件
        
        Args:
            event: 事件類型
            data: 事件資料
            
        Returns:
            SSE 格式字串
        """
        lines = []
        
        # 事件類型
        if event:
            lines.append(f"event: {event}")
        
        # 資料
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, ensure_ascii=False)
        else:
            data_str = str(data)
        
        # SSE 規範要求每行資料都要有 "data: " 前綴
        for line in data_str.split('\n'):
            lines.append(f"data: {line}")
        
        # 事件結束需要兩個換行
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
                self.logger.warning(f"Session {session_id} 已經處理過，跳過重複處理")
                return
            
            # 標記為已處理
            self.processed_sessions.add(session_id)
            self.logger.info(f"開始處理 Session {session_id} 的音訊資料")
            
            # 獲取 session
            session = self.session_manager.get_session(session_id)
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
            self.logger.info(f"處理完整音訊，大小: {len(complete_audio)} bytes")
            
            # 發送進度事件
            await self._send_sse_event(session_id, "progress", {
                "percentage": 50,
                "message": "開始處理音訊...",
                "timestamp": datetime.now().isoformat()
            })
            
            # 檢查音訊格式並轉換
            from src.utils.audio_utils import convert_webm_to_pcm
            from src.models.audio import AudioChunk, AudioFormat
            
            try:
                # 嘗試轉換音訊格式
                self.logger.info(f"轉換音訊格式，原始大小: {len(complete_audio)} bytes")
                pcm_data = convert_webm_to_pcm(complete_audio)
                self.logger.info(f"轉換成功，PCM 大小: {len(pcm_data)} bytes")
            except Exception as e:
                self.logger.error(f"音訊轉換失敗: {e}")
                # 假設已經是 PCM 格式
                pcm_data = complete_audio
            
            # 建立 AudioChunk
            audio_chunk = AudioChunk(
                data=pcm_data,
                sample_rate=16000,
                channels=1,
                format=AudioFormat.PCM
            )
            
            # 獲取 provider
            if not self.provider_manager:
                raise Exception("Provider manager not available")
            
            provider_name = session.provider_config.get("provider", "whisper")
            
            # 透過 pipeline 處理（如果有）
            processed_audio = audio_chunk
            if self.pipeline_manager:
                pipeline = self.pipeline_manager.get_pipeline("default")
                if pipeline:
                    processed_audio = await pipeline.process(audio_chunk)
            
            # 執行轉譯
            self.logger.info(f"使用 {provider_name} 進行轉譯")
            
            # 發送部分結果
            await self._send_sse_event(session_id, "transcript", {
                "text": "正在進行語音辨識...",
                "is_final": False,
                "confidence": 0.0,
                "timestamp": datetime.now().isoformat()
            })
            
            # 使用 ProviderManager 的 transcribe 方法（支援池化）
            result = await self.provider_manager.transcribe(
                audio_data=processed_audio.data if processed_audio else pcm_data,
                provider_name=provider_name,
                language=session.provider_config.get("language", "zh")
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
                
                self.logger.info(f"轉譯完成: {result.text[:50]}...")
            else:
                await self._send_sse_event(session_id, "error", {
                    "message": "無法辨識音訊內容",
                    "timestamp": datetime.now().isoformat()
                })
            
            # 清除緩衝區
            self.audio_buffers[session_id] = bytearray()
            
        except Exception as e:
            self.logger.error(f"處理音訊錯誤：{e}")
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
        
        # 清理已處理標記
        if session_id in self.processed_sessions:
            self.processed_sessions.remove(session_id)
        
        self.logger.debug(f"清理 Session {session_id} 資源")
    
    async def start(self):
        """啟動 SSE Server"""
        if self._running:
            self.logger.warning("SSE Server 已經在運行中")
            return
        
        self.logger.info(f"啟動 SSE Server: {self.host}:{self.port}")
        
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
        
        self.logger.success(f"SSE Server 啟動成功: http://{self.host}:{self.port}")
    
    async def stop(self):
        """停止 SSE Server"""
        if not self._running:
            self.logger.warning("SSE Server 未在運行中")
            return
        
        self.logger.info("停止 SSE Server")
        
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
        self.logger.success("SSE Server 已停止")
    
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
            if not session:
                return self.create_error_response("Session not found", session_id)
            
            # 處理不同的指令
            if command == "start":
                self.session_manager.update_session_state(session_id, "LISTENING")
                await self._send_sse_event(session_id, "status", {
                    "state": "LISTENING",
                    "message": "Started listening"
                })
                return self.create_success_response({"state": "LISTENING"}, session_id)
                
            elif command == "stop":
                self.session_manager.update_session_state(session_id, "IDLE")
                
                # 處理緩衝區中的所有音訊
                if session_id in self.audio_buffers and len(self.audio_buffers[session_id]) > 0:
                    self.logger.info(f"處理緩衝區音訊，大小: {len(self.audio_buffers[session_id])} bytes")
                    # 強制處理所有音訊資料
                    await self._process_all_audio(session_id)
                
                await self._send_sse_event(session_id, "status", {
                    "state": "IDLE",
                    "message": "Stopped listening"
                })
                return self.create_success_response({"state": "IDLE"}, session_id)
                
            elif command == "status":
                return self.create_success_response({
                    "state": session.state,
                    "created_at": session.created_at.isoformat(),
                    "last_activity": session.last_activity.isoformat()
                }, session_id)
                
            elif command == "busy_start":
                self.session_manager.update_session_state(session_id, "BUSY")
                await self._send_sse_event(session_id, "status", {
                    "state": "BUSY",
                    "message": "Entered busy mode"
                })
                return self.create_success_response({"state": "BUSY"}, session_id)
                
            elif command == "busy_end":
                self.session_manager.update_session_state(session_id, "LISTENING")
                await self._send_sse_event(session_id, "status", {
                    "state": "LISTENING",
                    "message": "Exited busy mode"
                })
                return self.create_success_response({"state": "LISTENING"}, session_id)
            
            # 喚醒詞相關指令
            elif command == "wake":
                source = params.get("source", "ui") if params else "ui"
                wake_timeout = params.get("wake_timeout") if params else None
                
                success = self.session_manager.wake_session(
                    session_id, 
                    source=source, 
                    wake_timeout=wake_timeout
                )
                
                if success:
                    session = self.session_manager.get_session(session_id)
                    await self._send_sse_event(session_id, "wake_word", {
                        "source": source,
                        "wake_time": session.wake_time.isoformat() if session.wake_time else None,
                        "wake_timeout": session.wake_timeout
                    })
                    return self.create_success_response({
                        "message": f"Session awakened from {source}",
                        "wake_timeout": session.wake_timeout
                    }, session_id)
                else:
                    return self.create_error_response("Failed to wake session", session_id)
            
            elif command == "sleep":
                session = self.session_manager.get_session(session_id)
                if session:
                    session.clear_wake()
                    await self._send_sse_event(session_id, "state_change", {
                        "old_state": session.state,
                        "new_state": "IDLE",
                        "event": "sleep"
                    })
                    return self.create_success_response({
                        "message": "Session set to sleep"
                    }, session_id)
                else:
                    return self.create_error_response("Session not found", session_id)
            
            elif command == "set_wake_timeout":
                if not params or "timeout" not in params:
                    return self.create_error_response("Missing timeout parameter", session_id)
                
                try:
                    timeout = float(params["timeout"])
                    if timeout <= 0:
                        return self.create_error_response("Timeout must be positive", session_id)
                    
                    session = self.session_manager.get_session(session_id)
                    if session:
                        session.wake_timeout = timeout
                        return self.create_success_response({
                            "message": f"Wake timeout set to {timeout} seconds",
                            "wake_timeout": timeout
                        }, session_id)
                    else:
                        return self.create_error_response("Session not found", session_id)
                        
                except (ValueError, TypeError):
                    return self.create_error_response("Invalid timeout value", session_id)
            
            elif command == "get_wake_status":
                # 獲取系統狀態（這裡需要 SystemListener 的支援）
                system_state = "IDLE"  # 暫時硬編碼，之後應該從 SystemListener 獲取
                
                # 獲取活躍的喚醒 sessions
                active_wake_sessions = self.session_manager.get_active_wake_sessions()
                
                wake_stats = self.session_manager.get_wake_stats()
                
                return self.create_success_response({
                    "system_state": system_state,
                    "active_wake_sessions": [
                        {
                            "id": s.id,
                            "wake_source": s.wake_source,
                            "wake_time": s.wake_time.isoformat() if s.wake_time else None,
                            "wake_timeout": s.wake_timeout,
                            "is_wake_expired": s.is_wake_expired()
                        }
                        for s in active_wake_sessions
                    ],
                    "stats": wake_stats
                }, session_id)
                
            else:
                return self.create_error_response(f"Unknown command: {command}", session_id)
                
        except Exception as e:
            self.logger.error(f"處理控制指令錯誤：{e}")
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