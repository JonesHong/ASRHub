#!/usr/bin/env python3
"""
Redis 客戶端測試程式
測試 Redis API 的完整流程：
1. 建立會話
2. 設定音訊參數
3. 從麥克風讀取音訊並發送
4. 接收轉譯結果
"""

import sys
import time
import base64
import threading
import signal
from datetime import datetime
from typing import Optional, Dict, Any

import pyaudio
import numpy as np
from redis_toolkit import RedisToolkit, RedisConnectionConfig, RedisOptions

# 從 channels 匯入所有需要的訊息類型
from src.api.redis.channels import (
    RedisChannels,
    CreateSessionMessage,
    StartListeningMessage,
    EmitAudioChunkMessage,
    SessionCreatedMessage,
    ListeningStartedMessage,
    WakeActivatedMessage as WakeActivatedResponseMessage,
    WakeDeactivatedMessage as WakeDeactivatedResponseMessage,
    TranscribeDoneMessage,
    PlayASRFeedbackMessage,
    ErrorMessage,
    WakeActivateMessage,
    WakeDeactivateMessage,
)
from src.interface.strategy import Strategy
from src.interface.wake import WakeActivateSource, WakeDeactivateSource
from src.utils.id_provider import new_id
from src.utils.logger import logger


class RedisClient:
    """Redis 客戶端實現"""

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0, wait_confirmations: bool = True):
        """初始化 Redis 客戶端
        
        Args:
            host: Redis 主機
            port: Redis 連接埠
            db: Redis 資料庫編號
            wait_confirmations: 是否等待確認訊息（預設 True）
        """
        self.host = host
        self.port = port
        self.db = db
        self.wait_confirmations = wait_confirmations
        
        # Redis 連接
        self.subscriber: Optional[RedisToolkit] = None
        self.publisher: Optional[RedisToolkit] = None
        
        # 會話資訊
        self.request_id: str = new_id()
        self.session_id: Optional[str] = None
        self.is_running = False
        
        # 音訊設定
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.CHUNK = 1024
        
        # PyAudio
        self.audio = None
        self.stream = None
        
        # 事件（可選擇性使用）
        self.session_created_event = threading.Event()
        self.listening_started_event = threading.Event()
        self.wake_activated_event = threading.Event()
        self.wake_deactivated_event = threading.Event()
        
    def initialize(self) -> bool:
        """初始化 Redis 連接"""
        try:
            # 建立連接配置
            config = RedisConnectionConfig(
                host=self.host,
                port=self.port,
                db=self.db
            )
            
            options = RedisOptions(
                is_logger_info=False,
            )
            
            # 訂閱的頻道列表（包含所有確認頻道）
            output_channels = [
                RedisChannels.RESPONSE_SESSION_CREATED,
                RedisChannels.RESPONSE_LISTENING_STARTED,      # 可選擇性處理
                RedisChannels.RESPONSE_WAKE_ACTIVATED,         # 可選擇性處理
                RedisChannels.RESPONSE_WAKE_DEACTIVATED,       # 可選擇性處理
                RedisChannels.RESPONSE_TRANSCRIBE_DONE,
                RedisChannels.RESPONSE_PLAY_ASR_FEEDBACK,
                RedisChannels.RESPONSE_ERROR,
            ]
            
            # 建立訂閱者（監聽伺服器的回應）
            self.subscriber = RedisToolkit(
                channels=output_channels,
                message_handler=self._message_handler,
                config=config,
                options=options
            )
            logger.info(f"✅ Redis 訂閱者已訂閱 {len(output_channels)} 個頻道")
            
            # 建立發布者（發送請求到伺服器）
            self.publisher = RedisToolkit(
                config=config,
                options=options
            )
            logger.info(f"✅ Redis 發布者已連接到 {self.host}:{self.port}")
            
            # 初始化 PyAudio
            self.audio = pyaudio.PyAudio()
            
            self.is_running = True
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失敗: {e}")
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
            
            logger.debug(f"📨 收到訊息 [{channel}]")
            
            # 處理不同的回應訊息
            if channel == RedisChannels.RESPONSE_SESSION_CREATED:
                self._handle_session_created(data)
            
            elif channel == RedisChannels.RESPONSE_LISTENING_STARTED:
                self._handle_listening_started(data)
            
            elif channel == RedisChannels.RESPONSE_WAKE_ACTIVATED:
                self._handle_wake_activated(data)
            
            elif channel == RedisChannels.RESPONSE_WAKE_DEACTIVATED:
                self._handle_wake_deactivated(data)
                
            elif channel == RedisChannels.RESPONSE_TRANSCRIBE_DONE:
                self._handle_transcribe_done(data)
                
            elif channel == RedisChannels.RESPONSE_PLAY_ASR_FEEDBACK:
                self._handle_asr_feedback(data)
                
            elif channel == RedisChannels.RESPONSE_ERROR:
                self._handle_error(data)
                
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")
    
    def _handle_session_created(self, data: Any):
        """處理會話建立回應"""
        try:
            logger.debug(f"收到會話建立回應: {data}")
            
            # 檢查是否有 request_id（新格式）
            if 'request_id' in data:
                response = SessionCreatedMessage(**data)
                if response.request_id != self.request_id:
                    logger.debug(f"忽略非本次請求的回應: {response.request_id} != {self.request_id}")
                    return  # 忽略非本次請求的回應
                # 更新 session_id（即使已經收到過，用最新的）
                old_session_id = self.session_id
                self.session_id = response.session_id
                if old_session_id and old_session_id != self.session_id:
                    logger.warning(f"⚠️ Session ID 已更新: {old_session_id} → {self.session_id}")
                logger.info(f"✅ 會話已建立: {self.session_id} (request_id: {self.request_id})")
                self.session_created_event.set()
            else:
                # 舊格式（沒有 request_id）- 可能是舊的測試訊息
                logger.warning(f"收到舊格式的會話建立回應（沒有 request_id），忽略: {data}")
                return
        except Exception as e:
            logger.error(f"處理會話建立回應失敗: {e}")
            import traceback
            traceback.print_exc()
    
    
    def _handle_listening_started(self, data: Any):
        """處理開始監聽回應"""
        try:
            response = ListeningStartedMessage(**data)
            logger.info(f"✅ 確認開始監聽: {response.sample_rate}Hz, {response.channels}ch")
            self.listening_started_event.set()
        except Exception as e:
            logger.error(f"處理開始監聽回應失敗: {e}")
    
    def _handle_wake_activated(self, data: Any):
        """處理喚醒啟用回應"""
        try:
            response = WakeActivatedResponseMessage(**data)
            logger.info(f"✅ 確認喚醒啟用: 來源={response.source}")
            self.wake_activated_event.set()
        except Exception as e:
            logger.error(f"處理喚醒啟用回應失敗: {e}")
    
    def _handle_wake_deactivated(self, data: Any):
        """處理喚醒停用回應"""
        try:
            response = WakeDeactivatedResponseMessage(**data)
            logger.info(f"✅ 確認喚醒停用: 來源={response.source}")
            self.wake_deactivated_event.set()
        except Exception as e:
            logger.error(f"處理喚醒停用回應失敗: {e}")
    
    def _handle_transcribe_done(self, data: Any):
        """處理轉譯完成"""
        try:
            response = TranscribeDoneMessage(**data)
            logger.info(f"")
            logger.info(f"=" * 60)
            logger.info(f"📝 轉譯結果: {response.text}")
            if response.confidence:
                logger.info(f"   信心度: {response.confidence:.2f}")
            if response.language:
                logger.info(f"   語言: {response.language}")
            logger.info(f"=" * 60)
            logger.info(f"")
        except Exception as e:
            logger.error(f"處理轉譯結果失敗: {e}")
    
    def _handle_asr_feedback(self, data: Any):
        """處理 ASR 回饋音控制"""
        try:
            response = PlayASRFeedbackMessage(**data)
            if response.command == "play":
                logger.info(f"🔊 ASR 回饋音: 播放")
            elif response.command == "stop":
                logger.info(f"🔇 ASR 回饋音: 停止")
        except Exception as e:
            logger.error(f"處理 ASR 回饋音失敗: {e}")
    
    def _handle_error(self, data: Any):
        """處理錯誤訊息"""
        try:
            error = ErrorMessage(**data)
            logger.error(f"❌ 錯誤 [{error.error_code}]: {error.error_message}")
        except Exception as e:
            logger.error(f"處理錯誤訊息失敗: {e}")
    
    def create_session(self, strategy: str = "non_streaming"):
        """建立會話"""
        message = CreateSessionMessage(strategy=Strategy.NON_STREAMING, request_id=self.request_id)
        self.publisher.publisher(
            RedisChannels.REQUEST_CREATE_SESSION,
            message.model_dump()
        )
        logger.info(f"📤 發送建立會話請求 (策略: {strategy}, request_id: {self.request_id})")
        
        # 等待會話建立
        if not self.session_created_event.wait(timeout=5):
            logger.error("建立會話超時")
            return False
        
        logger.info(f"📋 會話建立完成，session_id: {self.session_id}")
        return True
    
    def start_listening(self):
        """開始監聽設定"""
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        # 等待一下確保收到所有回應，避免使用舊的 session_id
        import time
        time.sleep(0.5)
        
        logger.info(f"📤 準備發送開始監聽請求，session_id: {self.session_id}")
        
        self.listening_started_event.clear()
        
        message = StartListeningMessage(
            session_id=self.session_id,
            sample_rate=self.RATE,
            channels=self.CHANNELS,
            format="int16"
        )
        self.publisher.publisher(
            RedisChannels.REQUEST_START_LISTENING,
            message.model_dump()
        )
        logger.info(f"📤 已發送開始監聽請求 (session: {self.session_id}, {self.RATE}Hz, {self.CHANNELS}ch)")
        
        # 根據設定決定是否等待確認
        if self.wait_confirmations:
            if not self.listening_started_event.wait(timeout=5):
                logger.warning("開始監聽確認超時，但繼續執行")
        
        return True
    
    def start_audio_stream(self):
        """開始音訊串流"""
        try:
            if not self.session_id:
                logger.error("無法開始音訊串流：沒有有效的 session_id")
                return
                
            logger.info(f"🎤 開始音訊串流，session_id: {self.session_id}")
            
            # 開啟麥克風串流
            self.stream = self.audio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )
            
            logger.info(f"🎤 麥克風已開啟，開始錄音... (session: {self.session_id})")
            logger.info("按 Ctrl+C 停止")
            
            # 音訊處理循環
            while self.is_running:
                try:
                    # 讀取音訊資料
                    audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    
                    # 音訊編碼為 base64
                    audio_encoded = base64.b64encode(audio_data).decode('utf-8')
                    
                    # 建立訊息
                    message = EmitAudioChunkMessage(
                        session_id=self.session_id,
                        audio_data=audio_encoded,
                    )
                    
                    # 發送音訊資料
                    self.publisher.publisher(
                        RedisChannels.REQUEST_EMIT_AUDIO_CHUNK,
                        message.model_dump()
                    )
                    
                except Exception as e:
                    if self.is_running:
                        logger.error(f"音訊處理錯誤: {e}")
                        time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"開啟音訊串流失敗: {e}")
        finally:
            self.stop_audio_stream()
    
    def wake_activate(self, source: str = WakeActivateSource.UI):
        """發送喚醒啟用請求
        
        Args:
            source: 啟用來源 (visual, ui, keyword)
        """
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        self.wake_activated_event.clear()
        
        message = WakeActivateMessage(
            session_id=self.session_id,
            source=source
        )
        self.publisher.publisher(
            RedisChannels.REQUEST_WAKE_ACTIVATE,
            message.model_dump()
        )
        logger.info(f"🎯 發送喚醒啟用請求 (session: {self.session_id}, source: {source})")
        
        # 根據設定決定是否等待確認
        if self.wait_confirmations:
            if not self.wake_activated_event.wait(timeout=5):
                logger.warning("喚醒啟用確認超時，但繼續執行")
        
        return True
    
    def wake_deactivate(self, source: str = WakeDeactivateSource.VAD_SILENCE_TIMEOUT):
        """發送喚醒停用請求
        
        Args:
            source: 停用來源 (visual, ui, vad_silence_timeout)
        """
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        self.wake_deactivated_event.clear()
        
        message = WakeDeactivateMessage(
            session_id=self.session_id,
            source=source
        )
        self.publisher.publisher(
            RedisChannels.REQUEST_WAKE_DEACTIVATE,
            message.model_dump()
        )
        logger.info(f"🛑 發送喚醒停用請求 (session: {self.session_id}, source: {source})")
        
        # 根據設定決定是否等待確認
        if self.wait_confirmations:
            if not self.wake_deactivated_event.wait(timeout=5):
                logger.warning("喚醒停用確認超時，但繼續執行")
        
        return True
    
    def stop_audio_stream(self):
        """停止音訊串流"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
                logger.info("🎤 麥克風已關閉")
            except:
                pass
    
    def stop(self):
        """停止客戶端"""
        logger.info("🛑 正在停止客戶端...")
        self.is_running = False
        
        # 停止音訊
        self.stop_audio_stream()
        
        if self.audio:
            try:
                self.audio.terminate()
            except:
                pass
        
        # 清理 Redis 連接
        if self.subscriber:
            try:
                self.subscriber.cleanup()
            except:
                pass
        
        if self.publisher:
            try:
                self.publisher.cleanup()
            except:
                pass
        
        logger.info("✅ 客戶端已停止")


def main(wait_confirmations=True):
    """主程式
    
    Args:
        wait_confirmations: 是否等待確認訊息（預設 True）
    """
    client = RedisClient(wait_confirmations=wait_confirmations)
    
    # 設定信號處理
    def signal_handler(sig, frame):
        logger.info("\n收到中斷信號")
        client.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 初始化
        if not client.initialize():
            logger.error("初始化失敗")
            return
        
        # 建立會話
        if not client.create_session():
            logger.error("建立會話失敗")
            return
        
        # 開始監聽
        if not client.start_listening():
            logger.error("開始監聽失敗")
            return
        
        # 測試喚醒啟用/停用（可選）
        # 取消註解以下程式碼來測試喚醒功能
        # client.wake_activate(WakeActivateSource.UI)
        # import time
        # time.sleep(2)
        # client.wake_deactivate(WakeDeactivateSource.VAD_SILENCE_TIMEOUT)
        
        # 開始音訊串流
        client.start_audio_stream()
        
    except Exception as e:
        logger.error(f"執行錯誤: {e}")
    finally:
        client.stop()


if __name__ == "__main__":
    logger.info("🚀 Redis 客戶端測試")
    logger.info("=" * 60)
    main()