"""
Redis Pub/Sub 伺服器實現

支援三個核心事件流程：
1. create_session - 建立新的 ASR session
2. start_listening - 設定音訊參數
3. receive_audio_chunk - 接收音訊資料並觸發轉譯

轉譯完成後會發布 transcribe_done 事件回 Redis。
"""

import json
import base64
import time
from datetime import datetime
from typing import Optional, Dict, Any

from redis_toolkit import RedisToolkit, RedisConnectionConfig, RedisOptions
from pydantic import ValidationError

from src.api.redis.channels import (
    RedisChannels,
    channels,
)

from src.api.redis.models import (
    EmitAudioChunkMessage,
    CreateSessionMessage,
    StartListeningMessage,
    DeleteSessionMessage,
    WakeActivateMessage,
    WakeDeactivateMessage,
    SessionCreatedMessage,
    ListeningStartedMessage,
    WakeActivatedMessage,
    WakeDeactivatedMessage,
    # AudioReceivedMessage,
    TranscribeDoneMessage,
    PlayASRFeedbackMessage,
    ErrorMessage,
)

from src.store.main_store import store
from src.store.sessions.sessions_action import (
    create_session,
    start_listening,
    receive_audio_chunk,
    transcribe_done,
    delete_session,
    wake_activated,
    play_asr_feedback,
)
from src.store.sessions.sessions_selector import get_session_by_id, get_all_sessions, get_session_last_transcription
from src.config.manager import ConfigManager
from src.utils.logger import logger

# Redis 客戶端實例（全域變數）
redis_publisher: Optional[RedisToolkit] = None
redis_subscriber: Optional[RedisToolkit] = None
store_subscription = None  # Store action stream 訂閱


class RedisServer:
    """Redis Pub/Sub 伺服器"""

    def __init__(self):
        """初始化 Redis 伺服器"""
        self.config_manager = ConfigManager()
        self.redis_config = self.config_manager.api.redis

        if not self.redis_config.enabled:
            logger.info("Redis 服務已停用")
            return

        self.subscriber = None
        self.subscriber = None
        self.store_subscription = None
        self.is_running = False

    def initialize(self):
        """初始化 Redis 連接和訂閱"""
        global redis_publisher, redis_subscriber, store_subscription

        if not self.redis_config.enabled:
            return False

        try:
            # 建立連接配置
            config = RedisConnectionConfig(
                host=self.redis_config.host,
                port=self.redis_config.port,
                db=self.redis_config.db,
                password=self.redis_config.password if self.redis_config.password else None,
            )

            options = RedisOptions(
                is_logger_info=False
            )

            # 建立發布者（用於發送訊息）
            self.publisher = RedisToolkit(config=config, options=options)
            redis_publisher = self.publisher
            logger.info(
                f"✅ Redis 發布者已連接到 {self.redis_config.host}:{self.redis_config.port}"
            )

            # 建立訂閱者（用於接收訊息）
            self.subscriber = RedisToolkit(
                channels=channels,  # 訂閱的頻道列表
                message_handler=self._message_handler,  # 訊息處理函數
                config=config,
                options=options,
            )
            redis_subscriber = self.subscriber
            logger.info(f"✅ Redis 訂閱者已訂閱 {len(channels)} 個頻道")

            # 設定 Store 事件監聽
            self._setup_store_listeners()

            self.is_running = True
            return True

        except Exception as e:
            logger.error(f"❌ Redis 初始化失敗: {e}")
            return False

    def _message_handler(self, channel: str, message: Any):
        """處理從 Redis 訂閱收到的消息
        
        Args:
            channel: Redis 頻道名稱
            message: 訊息內容（已自動反序列化）
        """
        try:
            # message 已經被 redis-toolkit 自動反序列化
            data = message

            # 如果 data 是字串，嘗試解析為 JSON
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    # 如果不是 JSON，保持原樣
                    pass

            logger.debug(f"📨 收到訊息 [{channel}]: {type(data).__name__}")

            # 根據頻道處理不同的訊息
            if channel == RedisChannels.REQUEST_CREATE_SESSION:
                self._handle_create_session(data)

            elif channel == RedisChannels.REQUEST_START_LISTENING:
                self._handle_start_listening(data)

            elif channel == RedisChannels.REQUEST_EMIT_AUDIO_CHUNK:
                self._handle_emit_audio_chunk(data)

            elif channel == RedisChannels.REQUEST_WAKE_ACTIVATE:
                self._handle_wake_activate(data)

            elif channel == RedisChannels.REQUEST_WAKE_DEACTIVATE:
                self._handle_wake_deactivate(data)

            # elif channel == RedisChannels.REQUEST_DELETE_SESSION:
            #     self._handle_delete_session(data)

            else:
                logger.warning(f"未知的頻道: {channel}")

        except Exception as e:
            logger.error(f"處理 Redis 訊息時發生錯誤: {e}")
            self._send_error(None, "MESSAGE_PROCESSING_ERROR", str(e))

    def _handle_create_session(self, data: Any):
        """處理建立 Session 請求"""
        try:
            # 驗證訊息格式
            if isinstance(data, dict):
                message = CreateSessionMessage(**data)
            else:
                raise ValueError("訊息格式錯誤，預期為 JSON 物件")

            # 分發到 PyStoreX Store，傳入 request_id（不生成 session_id，讓 reducer 生成）
            action = create_session(
                strategy=message.strategy, 
                request_id=message.request_id
            )
            logger.info(f"[Server] Dispatching action type: {action.type}, payload: {action.payload}")
            store.dispatch(action)
            
            # 從 state 獲取 reducer 創建的 session_id
            state = store.state
            sessions_data = state.get("sessions", {})
            
            # 獲取真正的 sessions dict
            # state.get("sessions") 返回的是 SessionsState，需要再取其中的 sessions 欄位
            if hasattr(sessions_data, 'get') and 'sessions' in sessions_data:
                sessions = sessions_data.get('sessions', {})
            else:
                sessions = sessions_data
            
            session_id = None
            
            # 找到有對應 request_id 的 session
            # 處理 immutables.Map 和 dict 兩種情況
            for sid, session in sessions.items():
                # 獲取 request_id - 兼容 Map 和 dict
                session_request_id = None
                if hasattr(session, 'get'):
                    session_request_id = session.get('request_id')
                elif hasattr(session, '__getitem__'):
                    try:
                        session_request_id = session['request_id']
                    except (KeyError, TypeError):
                        pass
                
                if session_request_id == message.request_id:
                    session_id = sid
                    logger.info(f"Found session {sid} with request_id {message.request_id}")
                    break
            
            # 如果找不到，嘗試從 SessionEffects 的映射獲取（fallback）
            if not session_id:
                from src.store.sessions.sessions_effect import SessionEffects
                session_id = SessionEffects.get_session_id_by_request_id(message.request_id)
            
            if session_id:
                logger.info(f"📝 Store 建立了 session: {session_id} (request_id: {message.request_id})")
            else:
                logger.error(f"❌ 無法從 Store 取得新建立的 session_id (request_id: {message.request_id})")
                self._send_error(None, "SESSION_CREATION_FAILED", "Failed to get session_id from store")
                return

            # 回應 session 建立成功
            response = SessionCreatedMessage(
                session_id=session_id,
                timestamp=datetime.now().isoformat(),
                request_id=message.request_id
            )

            self.publisher.publisher(RedisChannels.RESPONSE_SESSION_CREATED, response.model_dump())

            logger.info(f"✅ Session 建立成功: {session_id} (策略: {message.strategy}, request_id: {message.request_id})")

        except ValidationError as e:
            logger.error(f"建立 Session 訊息格式錯誤: {e}")
            self._send_error(None, "VALIDATION_ERROR", str(e))
        except Exception as e:
            logger.error(f"建立 Session 失敗: {e}")
            self._send_error(None, "CREATE_SESSION_ERROR", str(e))

    def _handle_start_listening(self, data: Any):
        """處理開始監聽請求"""
        try:
            # 驗證訊息格式
            message = StartListeningMessage(**data)
            
            # 檢查 session 是否存在
            session = get_session_by_id(message.session_id)(store.state)
            if not session:
                logger.error(f"❌ Session {message.session_id} 不存在，無法設定音訊配置")
                self._send_error(message.session_id, "SESSION_NOT_FOUND", f"Session {message.session_id} not found")
                return
            
            logger.info(f"📋 為 session {message.session_id} 設定音訊配置...")

            action = start_listening(
                session_id=message.session_id,
                sample_rate=message.sample_rate,
                channels=message.channels,
                format=message.format,
            )
            store.dispatch(action)
            
            # 發送開始監聽成功確認
            response = ListeningStartedMessage(
                session_id=message.session_id,
                sample_rate=message.sample_rate,
                channels=message.channels,
                format=message.format,
                timestamp=datetime.now().isoformat(),
            )
            self.publisher.publisher(
                RedisChannels.RESPONSE_LISTENING_STARTED,
                response.model_dump()
            )

            logger.info(
                f"✅ 開始監聽 session {message.session_id}: {message.sample_rate}Hz, {message.channels}ch, {message.format}"
            )

        except ValidationError as e:
            logger.error(f"開始監聽訊息格式錯誤: {e}")
            self._send_error(None, "VALIDATION_ERROR", str(e))
        except Exception as e:
            logger.error(f"開始監聽失敗: {e}")
            self._send_error(None, "START_LISTENING_ERROR", str(e))

    def _handle_emit_audio_chunk(self, data: Any):
        """處理發送音訊資料（支持二進制和 base64 兩種格式）"""
        try:
            session_id = None
            audio_bytes = None
            
            # 檢查是否為二進制格式
            if isinstance(data, bytes):
                # 處理二進制格式：元數據 + 分隔符 + 音訊數據
                separator = b'\x00\x00\xFF\xFF'
                
                try:
                    # 找到分隔符位置
                    separator_idx = data.index(separator)
                    
                    # 解析元數據
                    metadata_bytes = data[:separator_idx]
                    metadata = json.loads(metadata_bytes.decode('utf-8'))
                    
                    # 提取音訊數據
                    audio_bytes = data[separator_idx + len(separator):]
                    session_id = metadata['session_id']
                    
                    logger.debug(f"📦 收到二進制音訊，大小: {len(audio_bytes)} bytes（無 base64 開銷）")
                    
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(f"解析二進制消息失敗: {e}")
                    self._send_error(None, "BINARY_PARSE_ERROR", str(e))
                    return
                    
            else:
                # 處理傳統的 base64 格式（向後相容）
                message = EmitAudioChunkMessage(**data)
                session_id = message.session_id
                
                try:
                    # 使用 base64 直接解碼
                    audio_bytes = base64.b64decode(message.audio_data)
                    logger.debug(f"📦 收到 base64 音訊，解碼後: {len(audio_bytes)} bytes")
                except Exception as e:
                    logger.error(f"Base64 解碼失敗: {e}")
                    self._send_error(session_id, "AUDIO_DECODE_ERROR", str(e))
                    return
            
            # 檢查 session 是否存在
            session = get_session_by_id(session_id)(store.state)
            if not session:
                logger.error(f"❌ Session {session_id} 不存在，無法處理音訊")
                self._send_error(session_id, "SESSION_NOT_FOUND", f"Session {session_id} not found")
                return
                
            # 客戶端 emit 服務端 receive
            action = receive_audio_chunk(
                session_id=session_id, audio_data=audio_bytes
            )
            store.dispatch(action)

            # 可選：回應確認收到音訊（通常不需要，除非客戶端需要確認）
            # response = AudioReceivedMessage(
            #     session_id=session_id,
            #     timestamp=datetime.now().isoformat()
            # )
            # self.subscriber.publish(
            #     RedisChannels.RESPONSE_AUDIO_RECEIVED,
            #     response.dict()
            # )

            logger.debug(
                f"📥 收到音訊資料 [session: {session_id}]: {len(audio_bytes)} bytes"
            )

        except ValidationError as e:
            logger.error(f"音訊訊息格式錯誤: {e}")
            self._send_error(None, "VALIDATION_ERROR", str(e))
        except Exception as e:
            logger.error(f"處理音訊失敗: {e}")
            self._send_error(None, "AUDIO_PROCESSING_ERROR", str(e))

    def _handle_delete_session(self, data: Any):
        """處理刪除 Session 請求"""
        try:
            # 驗證訊息格式
            message = DeleteSessionMessage(**data)

            action = delete_session(session_id=message.session_id)
            store.dispatch(action)

            logger.info(f"✅ Session 已刪除: {message.session_id}")

        except ValidationError as e:
            logger.error(f"刪除 Session 訊息格式錯誤: {e}")
            self._send_error(None, "VALIDATION_ERROR", str(e))
        except Exception as e:
            logger.error(f"刪除 Session 失敗: {e}")
            self._send_error(None, "DELETE_SESSION_ERROR", str(e))

    def _handle_wake_activate(self, data: Any):
        """處理喚醒啟用請求"""
        try:
            # 驗證訊息格式
            message = WakeActivateMessage(**data)
            
            # 檢查 session 是否存在
            session = get_session_by_id(message.session_id)(store.state)
            if not session:
                logger.error(f"❌ Session {message.session_id} 不存在，無法啟用喚醒")
                self._send_error(message.session_id, "SESSION_NOT_FOUND", f"Session {message.session_id} not found")
                return

            action = wake_activated(session_id=message.session_id, source=message.source)
            store.dispatch(action)
            
            # 發送喚醒啟用成功確認
            response = WakeActivatedMessage(
                session_id=message.session_id,
                source=message.source,
                timestamp=datetime.now().isoformat(),
            )
            self.publisher.publisher(
                RedisChannels.RESPONSE_WAKE_ACTIVATED,
                response.model_dump()
            )

            logger.info(f"🎯 喚醒啟用 [session: {message.session_id}]: 來源={message.source}")

        except ValidationError as e:
            logger.error(f"喚醒啟用訊息格式錯誤: {e}")
            self._send_error(None, "VALIDATION_ERROR", str(e))
        except Exception as e:
            logger.error(f"喚醒啟用失敗: {e}")
            self._send_error(None, "WAKE_ACTIVATE_ERROR", str(e))

    def _handle_wake_deactivate(self, data: Any):
        """處理喚醒停用請求"""
        try:
            # 驗證訊息格式
            message = WakeDeactivateMessage(**data)
            
            # 檢查 session 是否存在
            session = get_session_by_id(message.session_id)(store.state)
            if not session:
                logger.error(f"❌ Session {message.session_id} 不存在，無法停用喚醒")
                self._send_error(message.session_id, "SESSION_NOT_FOUND", f"Session {message.session_id} not found")
                return

            action = wake_deactivated(session_id=message.session_id, source=message.source)
            store.dispatch(action)
            
            # 發送喚醒停用成功確認
            response = WakeDeactivatedMessage(
                session_id=message.session_id,
                source=message.source,
                timestamp=datetime.now().isoformat(),
            )
            self.publisher.publisher(
                RedisChannels.RESPONSE_WAKE_DEACTIVATED,
                response.model_dump()
            )

            logger.info(f"🛑 喚醒停用 [session: {message.session_id}]: 來源={message.source}")

        except ValidationError as e:
            logger.error(f"喚醒停用訊息格式錯誤: {e}")
            self._send_error(None, "VALIDATION_ERROR", str(e))
        except Exception as e:
            logger.error(f"喚醒停用失敗: {e}")
            self._send_error(None, "WAKE_DEACTIVATE_ERROR", str(e))

    def _setup_store_listeners(self):
        """設定 Store 事件監聽器"""
        global store_subscription


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
                logger.info(f"📡 [Redis] 處理 Store action: {action_type}")

            # 監聽轉譯完成事件 - 使用正確的 action type 字串
            if action_type == transcribe_done.type:
                self._handle_transcribe_done(payload)

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
                    self._handle_asr_feedback_play(payload)
                elif command == "stop":
                    self._handle_asr_feedback_stop(payload)
                else:
                    logger.warning(f"未知的 ASR 回饋音 command: {command}, payload type: {type(payload)}")

        # 訂閱 Store 的 action stream
        self.store_subscription = store._action_subject.subscribe(handle_store_action)
        store_subscription = self.store_subscription
        # logger.debug("Store 事件監聽器已設定")  # 改為 debug 級別，避免重複顯示

    def _handle_transcribe_done(self, payload: Dict[str, Any]):
        """處理轉譯完成事件，發布到 Redis"""
        try:
            session_id = payload.get("session_id")
            if not session_id:
                logger.warning("轉譯完成事件缺少 session_id")
                return

            # 從 payload 直接取得 result（TranscriptionResult）
            result = payload.get("result")
            
            # 如果 payload 沒有 result，嘗試從 Store 取得
            if not result:
                # 從 Store 取得最後的轉譯結果
                last_transcription = get_session_last_transcription(session_id)(store.state)
                if last_transcription:
                    # 使用儲存的轉譯結果
                    text = last_transcription.get("full_text", "")
                    language = last_transcription.get("language")
                    duration = last_transcription.get("duration")
                    processing_time = last_transcription.get("processing_time")
                else:
                    logger.warning(f"Session {session_id} 沒有轉譯結果")
                    return
            else:
                # 直接從 result 物件提取資料
                text = ""
                language = None
                duration = None
                processing_time = None
                
                if result:
                    if hasattr(result, "full_text"):
                        text = result.full_text.strip() if result.full_text else ""
                    if hasattr(result, "language"):
                        language = result.language
                    if hasattr(result, "duration"):
                        duration = result.duration
                    if hasattr(result, "processing_time"):
                        processing_time = result.processing_time

            if not text:
                logger.warning(f"Session {session_id} 的轉譯結果為空")
                return

            # 發布轉譯結果到 Redis
            response = TranscribeDoneMessage(
                session_id=session_id,
                text=text,
                confidence=None,  # TranscriptionResult 沒有 confidence 欄位
                language=language,
                duration=duration,
                timestamp=datetime.now().isoformat(),
            )

            self.publisher.publisher(RedisChannels.RESPONSE_TRANSCRIBE_DONE, response.model_dump())

            logger.info(f'📤 轉譯結果已發布 [session: {session_id}]: "{text[:100]}..."')

        except Exception as e:
            logger.error(f"處理轉譯完成事件失敗: {e}")
            self._send_error(session_id if 'session_id' in locals() else None, "TRANSCRIBE_DONE_ERROR", str(e))

    def _handle_asr_feedback_play(self, payload: Dict[str, Any]):
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

            # 發布播放 ASR 回饋音指令到 Redis
            response = PlayASRFeedbackMessage(
                session_id=session_id, command="play", timestamp=datetime.now().isoformat()
            )

            self.publisher.publisher(RedisChannels.RESPONSE_PLAY_ASR_FEEDBACK, response.model_dump())

            logger.info(f"🔊 ASR 回饋音播放指令已發布 [session: {session_id}]")

        except Exception as e:
            logger.error(f"處理 ASR 回饋音播放事件失敗: {e}")

    def _handle_asr_feedback_stop(self, payload: Dict[str, Any]):
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

            # 發布停止 ASR 回饋音指令到 Redis
            response = PlayASRFeedbackMessage(
                session_id=session_id, command="stop", timestamp=datetime.now().isoformat()
            )

            self.publisher.publisher(RedisChannels.RESPONSE_PLAY_ASR_FEEDBACK, response.model_dump())

            logger.info(f"🔇 ASR 回饋音停止指令已發布 [session: {session_id}]")

        except Exception as e:
            logger.error(f"處理 ASR 回饋音停止事件失敗: {e}")

    def _send_error(self, session_id: Optional[str], error_code: str, error_message: str):
        """發送錯誤訊息到 Redis"""
        try:
            if not self.subscriber:
                return

            error = ErrorMessage(
                session_id=session_id,
                error_code=error_code,
                error_message=error_message,
                timestamp=datetime.now().isoformat(),
            )

            self.publisher.publisher(RedisChannels.RESPONSE_ERROR, error.model_dump())

            logger.debug(f"❌ 錯誤訊息已發送: {error_code}")

        except Exception as e:
            logger.error(f"發送錯誤訊息失敗: {e}")

    def stop(self):
        """停止 Redis 伺服器"""
        if not self.is_running:
            return

        logger.info("🛑 正在停止 Redis 伺服器...")
        self.is_running = False

        # 清理 Store 訂閱
        if self.store_subscription:
            self.store_subscription.dispose()
            logger.debug("已清理 Store 訂閱")

        # 清理 Redis 連接
        if self.subscriber:
            try:
                self.subscriber.cleanup()
            except:
                pass

        if self.subscriber:
            try:
                self.subscriber.cleanup()
            except:
                pass

        logger.info("✅ Redis 伺服器已停止")


# 模組級單例
redis_server = RedisServer()


def initialize():
    """初始化 Redis 伺服器（供 main.py 調用）"""
    return redis_server.initialize()


def stop():
    """停止 Redis 伺服器（供 main.py 調用）"""
    redis_server.stop()


# 測試用主程式
if __name__ == "__main__":
    import asyncio

    async def test_server():
        """測試 Redis 伺服器"""
        logger.info("🚀 啟動 Redis 伺服器測試...")

        if initialize():
            logger.info("✅ Redis 伺服器已啟動")

            # 保持運行
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("收到中斷信號")
        else:
            logger.error("❌ Redis 伺服器啟動失敗")

        stop()
        logger.info("測試完成")

    asyncio.run(test_server())
