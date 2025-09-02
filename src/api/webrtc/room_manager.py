"""
LiveKit Room 管理器

管理共享的 LiveKit room，處理參與者加入/離開、音訊接收等功能。
"""

import asyncio
import json
from typing import Optional, Dict, Any, Set, Union
from datetime import datetime, timedelta
import weakref

from livekit import rtc
from livekit.api import AccessToken, VideoGrants, TokenVerifier
import uuid6

from src.store.main_store import store
from src.store.sessions.sessions_action import (
    receive_audio_chunk,
    transcribe_done,
    play_asr_feedback,
    start_listening,
    record_stopped,
    wake_activated,
    wake_deactivated,
    clear_audio_buffer,
)
from src.api.webrtc.signals import (
    DataChannelTopics,
    DataChannelCommands,
    DataChannelEvents,
)
from src.config.manager import ConfigManager
from src.utils.logger import logger


class LiveKitRoomManager:
    """LiveKit Room 管理器（單例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化 Room 管理器"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 配置
            self.config_manager = ConfigManager()
            self.webrtc_config = self.config_manager.api.webrtc
            self.livekit_config = self.webrtc_config.livekit
            
            # Room 實例
            self.room: Optional[rtc.Room] = None
            self.is_connected = False
            
            # Session 管理
            self.sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session info
            self.participants: Dict[str, str] = {}  # participant_sid -> session_id
            
            # 音訊串流管理（使用 weak references 防止記憶體洩漏）
            self.audio_streams: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
            self.stream_tasks: Dict[str, asyncio.Task] = {}
            
            # Store 訂閱
            self.store_subscription = None
            
            # 事件循環參考（用於跨執行緒呼叫）
            self.loop = None
            
            # 重連參數
            self.reconnect_attempts = 0
            self.max_reconnect_attempts = 5
            self.reconnect_delay = 1.0  # 初始延遲（秒）
    
    async def initialize(self) -> bool:
        """初始化 Room 連線"""
        try:
            if self.room and self.is_connected:
                logger.info("LiveKit Room 已經連線")
                return True
            
            # 建立 Room 實例
            self.room = rtc.Room()
            
            # 取得當前事件循環（用於跨執行緒呼叫）
            try:
                self.loop = asyncio.get_running_loop()
                self._main_loop = self.loop  # 儲存主事件循環供跨執行緒使用
                logger.debug(f"🔧 已儲存主事件循環")
            except RuntimeError:
                self.loop = asyncio.get_event_loop()
                self._main_loop = self.loop
                logger.debug(f"🔧 已儲存事件循環（非運行中）")
            
            # 設定事件處理器
            self._setup_event_handlers()
            
            # 設定 Store 監聽器
            self._setup_store_listeners()
            
            logger.info("✅ LiveKit Room Manager 已初始化")
            return True
            
        except Exception as e:
            logger.error(f"❌ LiveKit Room Manager 初始化失敗: {e}")
            return False
    
    def _setup_event_handlers(self):
        """設定 Room 事件處理器"""
        if not self.room:
            return
        
        @self.room.on("connected")
        def on_connected():
            """房間連線成功"""
            self.is_connected = True
            self.reconnect_attempts = 0
            logger.info(f"✅ 已連線到 LiveKit 房間: {self.livekit_config.room_name}")
        
        @self.room.on("disconnected")
        def on_disconnected():
            """房間斷線"""
            was_connected = self.is_connected
            self.is_connected = False
            
            # 只有在之前已連線的情況下才嘗試重連
            if was_connected:
                logger.warning("⚠️ LiveKit 房間已斷線，將嘗試重連")
                # 嘗試重連
                asyncio.create_task(self._handle_reconnect())
            else:
                logger.debug("🔍 LiveKit 連線關閉（未完成初始連線）")
        
        @self.room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            """參與者加入"""
            session_id = participant.metadata
            if session_id:
                self.participants[participant.sid] = session_id
                # 更新 session 連線狀態
                if session_id in self.sessions:
                    self.sessions[session_id]["is_connected"] = True
                    self.sessions[session_id]["last_activity"] = datetime.now()
                logger.info(f"👤 參與者加入 [session: {session_id}]: {participant.sid}")
        
        @self.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            """參與者離開"""
            session_id = self.participants.pop(participant.sid, None)
            if session_id:
                # 清理資源
                self._cleanup_session_resources(session_id)
                logger.info(f"👤 參與者離開 [session: {session_id}]: {participant.sid}")
        
        @self.room.on("track_subscribed")
        def on_track_subscribed(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant
        ):
            """訂閱到音訊軌道"""
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                session_id = participant.metadata
                if session_id:
                    logger.info(f"🎵 訂閱音訊軌道 [session: {session_id}]: {publication.sid}")
                    # 開始處理音訊串流
                    asyncio.create_task(self._process_audio_stream(track, session_id))
        
        @self.room.on("track_unsubscribed")
        def on_track_unsubscribed(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant
        ):
            """取消訂閱音訊軌道"""
            session_id = participant.metadata
            if session_id:
                logger.info(f"🔇 取消訂閱音訊軌道 [session: {session_id}]: {publication.sid}")
                # 停止音訊處理
                self._stop_audio_stream(session_id)
        
        @self.room.on("data_received")
        def on_data_received(data_packet: rtc.DataPacket):
            """接收資料訊息（包含控制命令）"""
            asyncio.create_task(self._handle_data_channel_message(data_packet))
    
    async def _process_audio_stream(self, track: rtc.Track, session_id: str):
        """處理音訊串流"""
        try:
            # 建立音訊串流（使用全域音訊設定或預設值）
            from src.config.manager import ConfigManager
            config = ConfigManager()
            
            audio_stream = rtc.AudioStream.from_track(
                track=track,
                sample_rate=config.audio.default_sample_rate if hasattr(config, 'audio') else 16000,
                num_channels=config.audio.default_channels if hasattr(config, 'audio') else 1
            )
            
            # 儲存串流參考
            self.audio_streams[session_id] = audio_stream
            
            # 設定音訊配置（在開始處理音訊前）
            from src.store.sessions.sessions_action import start_listening
            audio_config_action = start_listening(
                session_id=session_id,
                sample_rate=config.audio.default_sample_rate if hasattr(config, 'audio') else 16000,
                channels=config.audio.default_channels if hasattr(config, 'audio') else 1,
                format="int16"  # WebRTC 通常使用 16-bit PCM
            )
            store.dispatch(audio_config_action)
            logger.info(f"🎤 音訊配置已設定 [session: {session_id}]: 16kHz, 1ch, int16")
            
            # 注意：不要在這裡發送 record_started！
            # record_started 應該由 SessionEffects 在喚醒詞偵測到後才發送
            
            # 處理音訊幀
            async for event in audio_stream:
                try:
                    # AudioFrameEvent → AudioFrame → bytes (16-bit PCM)
                    audio_bytes = event.frame.data.tobytes()
                    
                    # 分發到 Store（與 http_sse 相同的處理流程）
                    action = receive_audio_chunk(
                        session_id=session_id,
                        audio_data=audio_bytes
                    )
                    store.dispatch(action)
                    
                    logger.debug(f"📥 音訊幀 [{session_id}]: {len(audio_bytes)} bytes")
                    
                except Exception as e:
                    logger.error(f"處理音訊幀失敗 [{session_id}]: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"音訊串流處理失敗 [{session_id}]: {e}")
        finally:
            # 通知停止錄音
            store.dispatch(record_stopped(session_id=session_id))
            
            # 清理串流
            if session_id in self.audio_streams:
                del self.audio_streams[session_id]
    
    def _stop_audio_stream(self, session_id: str):
        """停止音訊串流處理"""
        # 取消處理任務
        if session_id in self.stream_tasks:
            task = self.stream_tasks.pop(session_id)
            if not task.done():
                task.cancel()
        
        # 清理串流參考
        if session_id in self.audio_streams:
            del self.audio_streams[session_id]
    
    def _cleanup_session_resources(self, session_id: str):
        """清理 Session 資源"""
        # 停止音訊串流
        self._stop_audio_stream(session_id)
        
        # 移除 session 資訊
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        logger.debug(f"🧹 已清理 session 資源: {session_id}")
    
    async def _handle_data_channel_message(self, data_packet: rtc.DataPacket):
        """處理 DataChannel 訊息（控制命令和狀態查詢）"""
        try:
            # 解析訊息
            message = json.loads(data_packet.data.decode())
            topic = data_packet.topic
            participant = data_packet.participant
            
            # 從參與者 metadata 取得 session_id
            session_id = participant.metadata if participant else None
            
            if not session_id:
                logger.warning(f"收到沒有 session_id 的訊息: {message}")
                return
            
            logger.info(f"📨 收到 DataChannel 訊息 [topic: {topic}, session: {session_id}]: {message.get('command', message.get('type', 'unknown'))}")
            
            # 根據主題處理不同類型的訊息
            if topic == DataChannelTopics.CONTROL:
                await self._handle_control_command(session_id, message)
            elif topic == DataChannelTopics.AUDIO_METADATA:
                await self._handle_audio_metadata(session_id, message)
            else:
                logger.debug(f"未處理的主題: {topic}")
                
        except json.JSONDecodeError as e:
            logger.error(f"解析 DataChannel 訊息失敗: {e}")
        except Exception as e:
            logger.error(f"處理 DataChannel 訊息失敗: {e}")
    
    async def _handle_control_command(self, session_id: str, message: Dict[str, Any]):
        """處理控制命令"""
        command = message.get("command")
        params = message.get("params", {})
        
        try:
            if command == DataChannelCommands.START_LISTENING:
                # 開始監聽
                action = start_listening(
                    session_id=session_id,
                    sample_rate=params.get("sample_rate", 16000),
                    channels=params.get("channels", 1),
                    format=params.get("format", "int16")
                )
                store.dispatch(action)
                
                # 更新 session 狀態
                if session_id in self.sessions:
                    self.sessions[session_id]["is_listening"] = True
                    self.sessions[session_id]["last_activity"] = datetime.now()
                
                # 發送確認
                await self._send_status_update(
                    session_id,
                    DataChannelEvents.LISTENING_STARTED,
                    {"sample_rate": params.get("sample_rate", 16000)}
                )
                logger.info(f"✅ 開始監聽 [session: {session_id}]")
                
            elif command == DataChannelCommands.WAKE_ACTIVATED:
                # 啟用喚醒
                action = wake_activated(
                    session_id=session_id,
                    source=params.get("source", "manual")
                )
                store.dispatch(action)
                
                # 發送確認
                await self._send_status_update(
                    session_id,
                    DataChannelEvents.WAKE_STATUS_CHANGED,
                    {"wake_active": True}
                )
                logger.info(f"✅ 喚醒已啟用 [session: {session_id}]")
                
            elif command == DataChannelCommands.WAKE_DEACTIVATED:
                # 停用喚醒
                action = wake_deactivated(
                    session_id=session_id,
                    source=params.get("source", "manual")
                )
                store.dispatch(action)
                
                # 發送確認
                await self._send_status_update(
                    session_id,
                    DataChannelEvents.WAKE_STATUS_CHANGED,
                    {"wake_active": False}
                )
                logger.info(f"✅ 喚醒已停用 [session: {session_id}]")
                
            elif command == DataChannelCommands.CLEAR_AUDIO_BUFFER:
                # 清除音訊緩衝
                action = clear_audio_buffer(session_id=session_id)
                store.dispatch(action)
                
                # 發送確認
                await self._send_status_update(
                    session_id,
                    DataChannelEvents.BUFFER_CLEARED,
                    {}
                )
                logger.info(f"✅ 音訊緩衝已清除 [session: {session_id}]")
                
            elif command == DataChannelCommands.GET_STATUS:
                # 查詢狀態
                await self._send_session_status(session_id)
                
            elif command == DataChannelCommands.GET_STATS:
                # 查詢統計
                await self._send_session_stats(session_id)
                
            else:
                logger.warning(f"未知的控制命令: {command}")
                await self._send_error(
                    session_id,
                    "UNKNOWN_COMMAND",
                    f"Unknown command: {command}"
                )
                
        except Exception as e:
            logger.error(f"處理控制命令失敗 [{command}]: {e}")
            await self._send_error(
                session_id,
                "COMMAND_ERROR",
                str(e)
            )
    
    async def _handle_audio_metadata(self, session_id: str, message: Dict[str, Any]):
        """處理音訊元資料"""
        # 可以用來處理音訊格式變更、時間戳等資訊
        logger.debug(f"音訊元資料 [session: {session_id}]: {message}")
    
    async def _send_status_update(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """發送狀態更新給特定 session"""
        try:
            message = {
                "type": event_type,
                "session_id": session_id,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # 透過 DataChannel 發送給特定參與者
            if self.room and self.room.local_participant:
                # 找到對應的參與者
                for participant in self.room.remote_participants.values():
                    if participant.metadata == session_id:
                        await self.room.local_participant.publish_data(
                            json.dumps(message).encode(),
                            reliable=True,
                            destination_identities=[participant.identity],
                            topic=DataChannelTopics.STATUS
                        )
                        break
                        
        except Exception as e:
            logger.error(f"發送狀態更新失敗: {e}")
    
    async def _send_session_status(self, session_id: str):
        """發送 session 狀態"""
        session_info = self.sessions.get(session_id, {})
        status = {
            "session_id": session_id,
            "is_connected": session_info.get("is_connected", False),
            "is_listening": session_info.get("is_listening", False),
            "created_at": session_info.get("created_at", datetime.now()).isoformat(),
            "last_activity": session_info.get("last_activity", datetime.now()).isoformat()
        }
        
        await self._send_status_update(
            session_id,
            DataChannelEvents.STATUS_UPDATE,
            status
        )
    
    async def _send_session_stats(self, session_id: str):
        """發送 session 統計"""
        # TODO: 從 Store 或其他地方收集統計資訊
        stats = {
            "audio_chunks_received": 0,
            "transcriptions_completed": 0,
            "errors": 0
        }
        
        await self._send_status_update(
            session_id,
            DataChannelEvents.STATS_UPDATE,
            stats
        )
    
    async def _send_error(self, session_id: str, error_code: str, error_message: str):
        """發送錯誤訊息"""
        try:
            message = {
                "type": DataChannelEvents.ERROR_REPORTED,
                "session_id": session_id,
                "error_code": error_code,
                "error_message": error_message,
                "timestamp": datetime.now().isoformat()
            }
            
            # 透過 DataChannel 發送
            if self.room and self.room.local_participant:
                for participant in self.room.remote_participants.values():
                    if participant.metadata == session_id:
                        await self.room.local_participant.publish_data(
                            json.dumps(message).encode(),
                            reliable=True,
                            destination_identities=[participant.identity],
                            topic=DataChannelTopics.ERROR
                        )
                        break
                        
        except Exception as e:
            logger.error(f"發送錯誤訊息失敗: {e}")
    
    async def _handle_reconnect(self):
        """處理重連邏輯"""
        # 避免重複重連
        if self.is_connected:
            logger.debug("已連線，取消重連")
            return
            
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error("❌ 達到最大重連次數，放棄重連")
            return
        
        self.reconnect_attempts += 1
        delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))  # 指數退避
        delay = min(delay, 30.0)  # 最多等待 30 秒
        
        logger.info(f"⏳ {delay:.1f} 秒後嘗試重連（第 {self.reconnect_attempts} 次）")
        await asyncio.sleep(delay)
        
        # 再次檢查是否已連線
        if self.is_connected:
            logger.debug("在等待期間已連線，取消重連")
            return
        
        try:
            # 重新連線到房間
            if self.room and hasattr(self, '_last_room_token'):
                # 建立房間選項
                room_options = rtc.RoomOptions(
                    auto_subscribe=True,
                    dynacast=False,
                )
                
                await self.room.connect(
                    self.livekit_config.url,
                    self._last_room_token,
                    options=room_options
                )
                
                # 等待連線確認
                await asyncio.sleep(1)
                
                if self.is_connected:
                    logger.info("✅ 重連成功")
                else:
                    raise Exception("重連後仍未收到 connected 事件")
        except Exception as e:
            logger.error(f"❌ 重連失敗: {e}")
            # 繼續重試
            if self.reconnect_attempts < self.max_reconnect_attempts:
                await self._handle_reconnect()
    
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
            
            # 調試日誌：顯示所有收到的 action
            if "record" in action_type.lower() or "play_asr" in action_type.lower():
                logger.debug(f"🔍 [WebRTC] 收到 action: {action_type}, payload 類型: {type(payload)}")
            
            # 只有我們關心的事件才處理
            if action_type in [transcribe_done.type, play_asr_feedback.type]:
                logger.info(f"📡 [WebRTC] 處理 Store action: {action_type}")
                # 安全地在事件循環中執行
                self._schedule_async_task(action_type, payload)
        
        # 訂閱 Store 的 action stream
        self.store_subscription = store._action_subject.subscribe(handle_store_action)
        logger.info("📡 [WebRTC] Store 事件監聽器已設定")  # 顯示初始化訊息
    
    def _schedule_async_task(self, action_type: str, payload: Any):
        """安全地排程非同步任務"""
        try:
            import threading
            logger.debug(f"🔧 [WebRTC] 排程任務: {action_type} 從執行緒: {threading.current_thread().name}")
            
            # 確保有可用的事件循環
            if self.loop is None or not self.loop.is_running():
                # 嘗試取得主執行緒的事件循環
                main_thread = threading.main_thread()
                
                # 如果在主執行緒，直接取得事件循環
                if threading.current_thread() == main_thread:
                    try:
                        self.loop = asyncio.get_running_loop()
                        logger.debug(f"🔧 [WebRTC] 使用主執行緒的運行中事件循環")
                    except RuntimeError:
                        self.loop = asyncio.get_event_loop()
                        logger.debug(f"🔧 [WebRTC] 使用主執行緒的事件循環")
                else:
                    # 如果不在主執行緒，需要特殊處理
                    logger.warning(f"⚠️ [WebRTC] 在非主執行緒 {threading.current_thread().name} 中，無法取得事件循環")
                    # 嘗試使用已儲存的循環
                    if hasattr(self, '_main_loop') and self._main_loop:
                        self.loop = self._main_loop
                        logger.debug(f"🔧 [WebRTC] 使用已儲存的主事件循環")
                    else:
                        logger.error(f"❌ [WebRTC] 無法取得有效的事件循環")
                        return
            
            # 驗證事件循環是否可用
            if not self.loop or not self.loop.is_running():
                logger.error(f"❌ [WebRTC] 事件循環不可用或未運行")
                return
            
            # 監聽轉譯完成事件
            if action_type == transcribe_done.type:
                logger.info(f"📡 [WebRTC] 排程廣播轉譯結果")
                future = asyncio.run_coroutine_threadsafe(self._broadcast_transcription(payload), self.loop)
                # 設定超時避免永久等待
                future.add_done_callback(lambda f: logger.debug(f"✅ 轉譯廣播完成") if not f.exception() else logger.error(f"❌ 轉譯廣播失敗: {f.exception()}"))
            
            # 監聽 ASR 回饋音事件 (play_asr_feedback action)
            elif action_type == play_asr_feedback.type:
                command = payload.get("command") if hasattr(payload, "get") else None
                logger.info(f"📡 [WebRTC] 排程廣播 ASR 回饋音 ({command}), payload: {type(payload)}")
                if command == "play":
                    future = asyncio.run_coroutine_threadsafe(self._broadcast_asr_feedback_play(payload), self.loop)
                    future.add_done_callback(lambda f: logger.debug(f"✅ 回饋音播放廣播完成") if not f.exception() else logger.error(f"❌ 回饋音播放廣播失敗: {f.exception()}"))
                elif command == "stop":
                    future = asyncio.run_coroutine_threadsafe(self._broadcast_asr_feedback_stop(payload), self.loop)
                    future.add_done_callback(lambda f: logger.debug(f"✅ 回饋音停止廣播完成") if not f.exception() else logger.error(f"❌ 回饋音停止廣播失敗: {f.exception()}"))
                
        except Exception as e:
            logger.error(f"排程非同步任務失敗: {e}", exc_info=True)
    
    async def _broadcast_transcription(self, payload: Dict[str, Any]):
        """廣播轉譯結果給所有參與者"""
        try:
            session_id = payload.get("session_id")
            result = payload.get("result")
            
            if not session_id or not result:
                return
            
            # 準備廣播訊息
            message = {
                "type": DataChannelEvents.TRANSCRIBE_DONE,  # 使用正確的事件類型
                "session_id": session_id,
                "text": getattr(result, "full_text", ""),
                "language": getattr(result, "language", None),
                "confidence": getattr(result, "confidence", None),
                "duration": getattr(result, "duration", None),
                "timestamp": datetime.now().isoformat()
            }
            
            # 透過 DataChannel 廣播給所有參與者
            if self.room and self.room.local_participant:
                await self.room.local_participant.publish_data(
                    json.dumps(message).encode(),
                    reliable=True,
                    topic=DataChannelTopics.ASR_RESULT  # 使用 ASR 結果主題廣播
                )
                
                logger.info(f"📤 轉譯結果已廣播 [session: {session_id}]: \"{message['text'][:50]}...\"")
                
        except Exception as e:
            logger.error(f"廣播轉譯結果失敗: {e}")
    
    async def _broadcast_asr_feedback_play(self, payload: Union[str, Dict[str, Any]]):
        """廣播 ASR 回饋音播放事件"""
        try:
            logger.info(f"🔊 [WebRTC] 開始廣播 ASR 回饋音播放事件")
            logger.debug(f"🔊 [WebRTC] Payload 類型: {type(payload)}, 內容: {payload}")
            
            # 處理 payload 可能是字串、dict 或 immutables.Map 的情況
            session_id = None
            
            if isinstance(payload, str):
                session_id = payload
                logger.debug(f"🔊 [WebRTC] Payload 是字串: {session_id}")
            elif hasattr(payload, 'get'):  # 處理 dict 和 immutables.Map
                session_id = payload.get("session_id")
                logger.debug(f"🔊 [WebRTC] 從 payload 取得 session_id: {session_id}")
                # 如果是 immutables.Map，session_id 可能也是 immutables.Map
                if hasattr(session_id, 'get'):
                    session_id = str(session_id) if session_id else None
                    logger.debug(f"🔊 [WebRTC] 轉換 immutables.Map session_id: {session_id}")
            
            if not session_id:
                logger.warning(f"ASR 回饋音播放事件缺少 session_id，payload 類型: {type(payload)}, 內容: {payload}")
                return
            
            logger.info(f"🔊 [WebRTC] Session ID: {session_id}")
            
            # 準備廣播訊息
            message = {
                "type": DataChannelEvents.PLAY_ASR_FEEDBACK,
                "session_id": session_id,
                "command": "play",
                "timestamp": datetime.now().isoformat()
            }
            logger.debug(f"🔊 [WebRTC] 準備廣播訊息: {message}")
            
            # 檢查 room 和連線狀態
            if not self.room:
                logger.warning(f"🔊 [WebRTC] Room 未初始化，無法廣播")
                return
            
            if not self.is_connected:
                logger.warning(f"🔊 [WebRTC] Room 未連線，無法廣播")
                return
            
            if not self.room.local_participant:
                logger.warning(f"🔊 [WebRTC] 沒有 local_participant，無法廣播")
                return
            
            # 透過 DataChannel 廣播給所有參與者
            logger.info(f"🔊 [WebRTC] 正在廣播 ASR 回饋音播放指令...")
            await self.room.local_participant.publish_data(
                json.dumps(message).encode(),
                reliable=True,
                topic=DataChannelTopics.STATUS  # 使用狀態主題
            )
            
            logger.info(f"✅ [WebRTC] ASR 回饋音播放指令已廣播 [session: {session_id}]")
                
        except Exception as e:
            logger.error(f"廣播 ASR 回饋音播放事件失敗: {e}")
    
    async def _broadcast_asr_feedback_stop(self, payload: Union[str, Dict[str, Any]]):
        """廣播 ASR 回饋音停止事件"""
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
                logger.warning(f"ASR 回饋音停止事件缺少 session_id，payload 類型: {type(payload)}")
                return
            
            # 準備廣播訊息
            message = {
                "type": DataChannelEvents.PLAY_ASR_FEEDBACK,
                "session_id": session_id,
                "command": "stop",
                "timestamp": datetime.now().isoformat()
            }
            
            # 透過 DataChannel 廣播給所有參與者
            if self.room and self.room.local_participant:
                await self.room.local_participant.publish_data(
                    json.dumps(message).encode(),
                    reliable=True,
                    topic=DataChannelTopics.STATUS  # 使用狀態主題
                )
                
                logger.debug(f"🔇 ASR 回饋音停止指令已廣播 [session: {session_id}]")
                
        except Exception as e:
            logger.error(f"廣播 ASR 回饋音停止事件失敗: {e}")
    
    def generate_token(
        self, 
        session_id: str, 
        name: str = None,
        can_publish: bool = True,
        can_subscribe: bool = True,
        can_publish_data: bool = True
    ) -> str:
        """生成 LiveKit 存取 token"""
        # 使用新的 API - 鏈式調用
        token = AccessToken(
            self.livekit_config.api_key,
            self.livekit_config.api_secret
        ) \
        .with_identity(session_id) \
        .with_name(name or f"Session-{session_id[:8]}") \
        .with_metadata(session_id) \
        .with_ttl(timedelta(hours=1)) \
        .with_grants(VideoGrants(
            room_join=True,
            room=self.livekit_config.room_name,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            can_publish_data=can_publish_data
        ))
        
        return token.to_jwt()
    
    async def connect_as_server(self) -> bool:
        """以伺服器身份連線到房間（用於廣播）"""
        try:
            if self.is_connected:
                logger.info("✅ [WebRTC] 已經連線到 LiveKit 房間")
                return True
            
            logger.info(f"🔄 [WebRTC] 正在連線到 LiveKit: {self.livekit_config.url}")
            
            # 生成伺服器 token，給予更多權限
            server_token = self.generate_token(
                session_id="asr_hub_server",
                name="ASR Hub Server",
                # 伺服器需要能發送資料到房間
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True
            )
            
            # 儲存 token 供重連使用
            self._last_room_token = server_token
            
            # 建立房間選項，確保正確的設定
            room_options = rtc.RoomOptions(
                auto_subscribe=True,
                dynacast=False,  # 伺服器端不需要 dynacast
                # 不發布任何媒體軌道，只使用 DataChannel
            )
            
            # 連線到房間
            await self.room.connect(
                self.livekit_config.url,
                server_token,
                options=room_options
            )
            
            # 等待連線成功事件（最多等待 5 秒，給更多時間）
            max_wait = 5.0
            wait_interval = 0.1
            waited = 0.0
            
            while not self.is_connected and waited < max_wait:
                await asyncio.sleep(wait_interval)
                waited += wait_interval
                
                # 檢查 room 的實際狀態
                if hasattr(self.room, 'connection_state'):
                    state = self.room.connection_state
                    if state == rtc.ConnectionState.CONN_CONNECTED:
                        # 手動設置狀態，如果事件沒有觸發
                        self.is_connected = True
                        logger.info("✅ [WebRTC] 偵測到房間已連線（透過狀態檢查）")
                        break
            
            if self.is_connected:
                logger.info(f"✅ [WebRTC] 成功連線到 LiveKit 房間: {self.livekit_config.room_name}")
            else:
                # 如果超時但沒有錯誤，可能是事件未觸發，檢查 room 狀態
                logger.warning(f"⚠️ [WebRTC] 等待 {max_wait} 秒後 is_connected 仍為 False")
                
                # 最後嘗試：檢查房間的連線狀態
                if hasattr(self.room, 'connection_state'):
                    state = self.room.connection_state
                    logger.info(f"🔍 [WebRTC] Room connection state: {state}")
                    if state == rtc.ConnectionState.CONN_CONNECTED:
                        self.is_connected = True
                        logger.info("✅ [WebRTC] 房間實際上已連線，更新狀態")
                        return True
                
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"伺服器連線失敗: {e}")
            return False
    
    def add_session(self, session_id: str, metadata: Dict[str, Any] = None):
        """添加 session 資訊"""
        self.sessions[session_id] = {
            "session_id": session_id,
            "created_at": datetime.now(),
            "metadata": metadata or {},
            "is_connected": False,
            "is_listening": False
        }
        logger.debug(f"➕ Session 已加入: {session_id}")
    
    def remove_session(self, session_id: str):
        """移除 session"""
        self._cleanup_session_resources(session_id)
        logger.debug(f"➖ Session 已移除: {session_id}")
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取得 session 資訊"""
        return self.sessions.get(session_id)
    
    def get_room_status(self) -> Dict[str, Any]:
        """取得房間狀態"""
        participant_count = 0
        if self.room and self.room.remote_participants:
            participant_count = len(self.room.remote_participants)
        
        return {
            "room_name": self.livekit_config.room_name,
            "is_active": self.is_connected,
            "participant_count": participant_count,
            "active_sessions": list(self.sessions.keys()),
            "created_at": datetime.now() if self.is_connected else None
        }
    
    async def cleanup(self):
        """清理資源"""
        try:
            # 停止所有音訊串流
            for session_id in list(self.sessions.keys()):
                self._cleanup_session_resources(session_id)
            
            # 斷開房間連線
            if self.room and self.is_connected:
                await self.room.disconnect()
            
            # 清理 Store 訂閱
            if self.store_subscription:
                self.store_subscription.dispose()
            
            logger.info("✅ LiveKit Room Manager 已清理")
            
        except Exception as e:
            logger.error(f"清理失敗: {e}")


# 模組級單例
room_manager = LiveKitRoomManager()