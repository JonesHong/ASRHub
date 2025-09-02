#!/usr/bin/env python3
"""
WebRTC/LiveKit 測試客戶端 - 完整版
使用 DataChannel 進行控制，測試 ASR Hub WebRTC API
"""

import os
import sys
import asyncio
import json
import signal
import time
from typing import Optional, Dict, Any
from datetime import datetime
import threading

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import aiohttp
import pyaudio
import numpy as np
from livekit import rtc

from src.utils.id_provider import new_id
from src.utils.logger import logger
from src.config.manager import ConfigManager
from src.api.webrtc.signals import (
    DataChannelTopics,
    DataChannelCommands,
    DataChannelEvents,
)


class WebRTCLiveKitClient:
    """WebRTC/LiveKit 測試客戶端 - 使用 DataChannel 控制"""
    
    def __init__(self):
        """初始化客戶端"""
        # 載入配置
        self.config = ConfigManager()
        
        # API 設定
        self.host = self.config.api.webrtc.host
        self.port = self.config.api.webrtc.port
        self.base_url = f"http://{self.host}:{self.port}/api/webrtc"
        
        # Session 資訊
        self.session_id: Optional[str] = None
        self.token: Optional[str] = None
        self.room_name: Optional[str] = None
        self.livekit_url: Optional[str] = None
        
        # LiveKit 房間
        self.room: Optional[rtc.Room] = None
        self.audio_source: Optional[rtc.AudioSource] = None
        self.audio_track: Optional[rtc.LocalAudioTrack] = None
        
        # 音訊設定
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = self.config.audio.default_channels
        self.RATE = self.config.audio.default_sample_rate
        self.CHUNK = self.config.audio.buffer_size
        
        # PyAudio
        self.audio = None
        self.stream = None
        
        # 控制標誌
        self.is_running = False
        self.is_recording = False
        
        # 統計
        self.stats = {
            "audio_chunks_sent": 0,
            "transcriptions_received": 0,
            "errors": 0
        }
    
    async def initialize(self) -> bool:
        """初始化客戶端"""
        try:
            self.audio = pyaudio.PyAudio()
            self.is_running = True
            logger.info("✅ WebRTC/LiveKit 客戶端已初始化")
            logger.info(f"   連接位址: {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"❌ 初始化失敗: {e}")
            return False
    
    async def create_session(self, strategy: str = "non_streaming") -> bool:
        """建立 session (唯一的 REST 端點)"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/create_session"
                data = {
                    "strategy": strategy,
                    "metadata": {
                        "client": "test_webrtc_livekit",
                        "timestamp": datetime.now().isoformat()
                    }
                }
                
                logger.info("📤 發送建立 Session 請求")
                logger.debug(f"   策略: {strategy}")
                
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.session_id = result["session_id"]
                        self.token = result["token"]
                        self.room_name = result["room_name"]
                        self.livekit_url = result["livekit_url"]
                        
                        logger.info(f"✅ Session 建立成功")
                        logger.info(f"   Session ID: {self.session_id}")
                        logger.info(f"   Room: {self.room_name}")
                        logger.info(f"   LiveKit URL: {self.livekit_url}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"❌ 建立 Session 失敗: {response.status} - {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 建立 Session 失敗: {e}")
            return False
    
    async def connect_room(self) -> bool:
        """連線到 LiveKit 房間"""
        if not self.token or not self.livekit_url:
            logger.error("❌ 缺少 token 或 LiveKit URL")
            return False
        
        try:
            # 建立 Room 實例
            self.room = rtc.Room()
            
            # 設定事件處理器
            self._setup_event_handlers()
            
            # 連線到房間
            logger.info(f"🔄 連線到 LiveKit 房間...")
            await self.room.connect(self.livekit_url, self.token)
            
            logger.info(f"✅ 已連線到房間: {self.room_name}")
            
            # 等待連線穩定
            await asyncio.sleep(0.5)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 連線失敗: {e}")
            return False
    
    def _setup_event_handlers(self):
        """設定事件處理器"""
        @self.room.on("room_connected")
        def on_room_connected():
            logger.info("📡 房間連線成功")
        
        @self.room.on("room_disconnected")
        def on_room_disconnected():
            logger.info("📡 房間已斷線")
            self.is_running = False
        
        @self.room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            logger.info(f"👤 參與者加入: {participant.identity}")
        
        @self.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            logger.info(f"👤 參與者離開: {participant.identity}")
        
        @self.room.on("data_received")
        def on_data_received(data_packet: rtc.DataPacket):
            """接收 DataChannel 訊息"""
            asyncio.create_task(self._handle_data_message(data_packet))
    
    async def _handle_data_message(self, data_packet: rtc.DataPacket):
        """處理 DataChannel 訊息"""
        try:
            message = json.loads(data_packet.data.decode())
            topic = data_packet.topic
            
            if topic == DataChannelTopics.ASR_RESULT:
                # ASR 結果
                if message.get("type") == DataChannelEvents.TRANSCRIBE_DONE:
                    text = message.get("text", "")
                    language = message.get("language", "unknown")
                    confidence = message.get("confidence")
                    
                    logger.info("")
                    logger.info("=" * 60)
                    logger.info(f"📝 轉譯結果: {text}")
                    if language:
                        logger.info(f"   語言: {language}")
                    if confidence:
                        logger.info(f"   信心度: {confidence:.2f}")
                    logger.info("=" * 60)
                    logger.info("")
                    
                    self.stats["transcriptions_received"] += 1
                    
            elif topic == DataChannelTopics.STATUS:
                # 狀態更新
                event_type = message.get("type")
                data = message.get("data", {})
                
                if event_type == DataChannelEvents.LISTENING_STARTED:
                    logger.info("✅ 確認開始監聽")
                    logger.debug(f"   取樣率: {data.get('sample_rate')}Hz")
                    
                elif event_type == DataChannelEvents.WAKE_STATUS_CHANGED:
                    wake_active = data.get("wake_active")
                    if wake_active:
                        logger.info("✅ 確認喚醒啟用")
                    else:
                        logger.info("✅ 確認喚醒停用")
                    
                elif event_type == DataChannelEvents.STATUS_UPDATE:
                    logger.info(f"📊 狀態更新: {data}")
                    
                elif event_type == DataChannelEvents.STATS_UPDATE:
                    logger.info(f"📈 統計更新: {data}")
                    
                # 處理 ASR 回饋音事件
                elif event_type == DataChannelEvents.PLAY_ASR_FEEDBACK:
                    command = message.get("command", "unknown")
                    session_id = message.get("session_id")
                    if command == "play":
                        logger.info("🔊 收到 ASR 回饋音播放事件")
                    elif command == "stop":
                        logger.info("🔇 收到 ASR 回饋音停止事件")
                    else:
                        logger.info(f"❓ 收到未知的 ASR 回饋音指令: {command}")
                    
            elif topic == DataChannelTopics.ERROR:
                # 錯誤訊息
                error_code = message.get("error_code", "UNKNOWN")
                error_message = message.get("error_message", "未知錯誤")
                logger.error(f"❌ 錯誤 [{error_code}]: {error_message}")
                self.stats["errors"] += 1
                
        except json.JSONDecodeError as e:
            logger.error(f"解析 DataChannel 訊息失敗: {e}")
        except Exception as e:
            logger.error(f"處理 DataChannel 訊息失敗: {e}")
    
    async def send_control_command(self, command: str, params: Dict[str, Any] = None) -> bool:
        """透過 DataChannel 發送控制命令"""
        if not self.room or not self.room.local_participant:
            logger.error("❌ 尚未連線到房間")
            return False
        
        try:
            message = {
                "command": command,
                "params": params or {},
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info("📤 發送控制命令")
            logger.debug(f"   命令: {command}")
            
            # 透過 DataChannel 發送
            await self.room.local_participant.publish_data(
                json.dumps(message).encode(),
                reliable=True,
                topic=DataChannelTopics.CONTROL
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 發送控制命令失敗: {e}")
            return False
    
    async def start_listening(self) -> bool:
        """開始監聽（透過 DataChannel）"""
        params = {
            "sample_rate": self.RATE,
            "channels": self.CHANNELS,
            "format": "int16"
        }
        return await self.send_control_command(DataChannelCommands.START_LISTENING, params)
    
    async def activate_wake(self, source: str = "manual") -> bool:
        """啟用喚醒（透過 DataChannel）"""
        params = {"source": source}
        return await self.send_control_command(DataChannelCommands.WAKE_ACTIVATED, params)
    
    async def deactivate_wake(self, source: str = "manual") -> bool:
        """停用喚醒（透過 DataChannel）"""
        params = {"source": source}
        return await self.send_control_command(DataChannelCommands.WAKE_DEACTIVATED, params)
    
    async def clear_buffer(self) -> bool:
        """清除音訊緩衝（透過 DataChannel）"""
        return await self.send_control_command(DataChannelCommands.CLEAR_AUDIO_BUFFER)
    
    async def get_status(self) -> bool:
        """查詢狀態（透過 DataChannel）"""
        return await self.send_control_command(DataChannelCommands.GET_STATUS)
    
    async def get_stats(self) -> bool:
        """查詢統計（透過 DataChannel）"""
        return await self.send_control_command(DataChannelCommands.GET_STATS)
    
    async def publish_audio(self) -> bool:
        """發布音訊軌道"""
        if not self.room:
            logger.error("❌ 尚未連線到房間")
            return False
        
        try:
            # 建立音訊源（16kHz, 單聲道）
            self.audio_source = rtc.AudioSource(self.RATE, self.CHANNELS)
            
            # 建立音訊軌道
            self.audio_track = rtc.LocalAudioTrack.create_audio_track(
                "microphone",
                self.audio_source
            )
            
            # 設定 track 選項
            options = rtc.TrackPublishOptions()
            options.source = rtc.TrackSource.SOURCE_MICROPHONE
            
            # 發布軌道
            publication = await self.room.local_participant.publish_track(
                self.audio_track,
                options
            )
            
            logger.info(f"✅ 音訊軌道已發布: {publication.sid}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 發布音訊軌道失敗: {e}")
            return False
    
    async def start_microphone(self):
        """開始麥克風錄音並發送音訊"""
        if not self.audio_source:
            logger.error("❌ 尚未建立音訊源")
            return
        
        try:
            logger.info(f"🎤 開始麥克風錄音...")
            
            # 開啟麥克風串流
            self.stream = self.audio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )
            
            self.is_recording = True
            logger.info("🎤 麥克風已開啟，開始錄音...")
            logger.info("按 Ctrl+C 停止")
            
            # 音訊處理循環
            while self.is_running and self.is_recording:
                try:
                    # 讀取音訊資料
                    audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    
                    # 轉換為 numpy array
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    
                    # 建立 AudioFrame
                    frame = rtc.AudioFrame(
                        data=audio_array.tobytes(),
                        sample_rate=self.RATE,
                        num_channels=self.CHANNELS,
                        samples_per_channel=len(audio_array) // self.CHANNELS
                    )
                    
                    # 發送音訊幀
                    await self.audio_source.capture_frame(frame)
                    
                    self.stats["audio_chunks_sent"] += 1
                    
                    # 顯示音量指示器（可選）
                    volume = np.abs(audio_array).mean()
                    bars = "█" * int(volume / 1000)
                    print(f"\r🎤 {bars:20}", end="", flush=True)
                    
                except Exception as e:
                    logger.error(f"音訊處理錯誤: {e}")
                    await asyncio.sleep(0.01)
                    
        except Exception as e:
            logger.error(f"❌ 麥克風錄音失敗: {e}")
        finally:
            self.is_recording = False
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            logger.info("\n🎤 麥克風已關閉")
    
    async def stop(self):
        """停止客戶端"""
        self.is_running = False
        self.is_recording = False
        
        # 關閉音訊
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.audio:
            self.audio.terminate()
        
        # 斷開房間連線
        if self.room:
            await self.room.disconnect()
        
        logger.info("✅ 客戶端已停止")
    
    def print_stats(self):
        """顯示統計資訊"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 統計資訊:")
        logger.info(f"   音訊片段發送: {self.stats['audio_chunks_sent']}")
        logger.info(f"   轉譯結果接收: {self.stats['transcriptions_received']}")
        logger.info(f"   錯誤數量: {self.stats['errors']}")
        logger.info("=" * 60)


async def main():
    """主測試流程"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("🚀 WebRTC/LiveKit 客戶端測試")
    logger.info("🎤 音訊來源: 麥克風")
    logger.info("⚡ 傳輸方式: WebRTC DataChannel")
    logger.info("=" * 60)
    logger.info("")
    
    client = WebRTCLiveKitClient()
    
    # 設定信號處理
    def signal_handler(sig, frame):
        logger.info("\n⚠️ 收到中斷信號，正在停止...")
        asyncio.create_task(client.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 1. 初始化
        logger.info("1️⃣ 初始化客戶端...")
        if not await client.initialize():
            return
        
        # 2. 建立 Session（唯一的 REST 端點）
        logger.info("2️⃣ 建立 Session...")
        if not await client.create_session(strategy="whisper"):
            return
        
        # 3. 連線到 LiveKit 房間
        logger.info("3️⃣ 連線到 LiveKit 房間...")
        if not await client.connect_room():
            return
        
        # 4. 發布音訊軌道
        logger.info("4️⃣ 發布音訊軌道...")
        if not await client.publish_audio():
            return
        
        # 5. 透過 DataChannel 開始監聽
        logger.info("5️⃣ 開始監聽（透過 DataChannel）...")
        if not await client.start_listening():
            return
        
        # 等待確認
        await asyncio.sleep(1)
        
        # 6. 查詢狀態（透過 DataChannel）
        logger.info("6️⃣ 查詢狀態...")
        await client.get_status()
        await asyncio.sleep(0.5)
        
        # 測試喚醒啟用/停用（可選）
        # 取消註解以下程式碼來測試喚醒功能
        # if not await client.activate_wake("test"):
        #     logger.warning("⚠️ 喚醒啟用失敗")
        # await asyncio.sleep(2)  # 等待事件廣播
        # if not await client.deactivate_wake("test"):
        #     logger.warning("⚠️ 喚醒停用失敗")
        # await asyncio.sleep(1)
        
        # 7. 開始麥克風錄音（如果可用）
        logger.info("7️⃣ 開始麥克風錄音...")
        await client.start_microphone()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ 測試中斷")
    except Exception as e:
        logger.error(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 顯示統計
        client.print_stats()
        
        # 清理
        logger.info("\n🧹 清理資源...")
        await client.stop()
        logger.info("\n✅ 測試完成")


if __name__ == "__main__":
    asyncio.run(main())