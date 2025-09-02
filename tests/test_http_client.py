#!/usr/bin/env python3
"""
HTTP SSE 客戶端測試程式 - 簡化版
測試 HTTP SSE API 的麥克風音訊串流
"""

import os
import sys
import time
import threading
import signal
import json
from typing import Optional, Dict, Any

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import requests
import pyaudio
from sseclient import SSEClient  # pip install sseclient-py

from src.utils.id_provider import new_id
from src.utils.logger import logger
from src.config.manager import ConfigManager


class HTTPSSEClient:
    """HTTP SSE 客戶端實現 - 簡化版"""

    def __init__(self):
        """初始化 HTTP SSE 客戶端"""
        # 載入配置
        self.config = ConfigManager()
        
        # API 設定
        self.host = self.config.api.http_sse.host
        self.port = self.config.api.http_sse.port
        self.base_url = f"http://{self.host}:{self.port}/api/v1"
        
        # 會話資訊
        self.request_id: str = new_id()
        self.session_id: Optional[str] = None
        self.sse_url: Optional[str] = None
        self.is_running = False
        
        # 音訊設定（從配置載入）
        self.FORMAT = pyaudio.paInt16  # 對應 config 的 "int16"
        self.CHANNELS = self.config.audio.default_channels
        self.RATE = self.config.audio.default_sample_rate
        self.CHUNK = self.config.audio.buffer_size
        
        # PyAudio
        self.audio = None
        self.stream = None
        
        # SSE 連線
        self.sse_thread: Optional[threading.Thread] = None
        self.sse_client: Optional[SSEClient] = None
        
    def initialize(self) -> bool:
        """初始化客戶端"""
        try:
            self.audio = pyaudio.PyAudio()
            self.is_running = True
            logger.info("✅ HTTP SSE 客戶端已初始化")
            logger.info(f"   連接位址: {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"❌ 初始化失敗: {e}")
            return False
    
    def _start_sse_listener(self):
        """啟動 SSE 事件監聽器"""
        if not self.sse_url:
            logger.error("沒有 SSE URL")
            return
        
        def sse_listener():
            """SSE 監聽器執行緒"""
            try:
                logger.info("🔄 正在連接 SSE...")
                logger.debug(f"   SSE URL: {self.sse_url}")
                
                # 建立 SSE 連線
                response = requests.get(self.sse_url, stream=True, headers={'Accept': 'text/event-stream'})
                response.raise_for_status()
                self.sse_client = SSEClient(response)
                
                # 監聽事件
                for event in self.sse_client.events():
                    if not self.is_running:
                        break
                    
                    if event.data:
                        try:
                            data = json.loads(event.data)
                            event_type = event.event or "message"
                            self._handle_sse_event(event_type, data)
                        except json.JSONDecodeError:
                            logger.error(f"無法解析 SSE 事件資料: {event.data}")
                            
            except Exception as e:
                logger.error(f"SSE 監聽器錯誤: {e}")
            finally:
                logger.info("🔌 SSE 連線已關閉")
        
        # 啟動監聽執行緒
        self.sse_thread = threading.Thread(target=sse_listener, daemon=True)
        self.sse_thread.start()
        time.sleep(0.5)  # 等待連線建立
    
    def _handle_sse_event(self, event_type: str, data: Dict[str, Any]):
        """處理 SSE 事件"""
        try:
            if event_type == "connection_ready":
                logger.info("✅ SSE 連線已建立")
            
            elif event_type == "session_created":
                logger.info("✅ 確認 Session 建立")
                logger.debug(f"   Session ID: {data.get('session_id')}")
            
            elif event_type == "listening_started":
                logger.info("✅ 確認開始監聽")
                logger.debug(f"   取樣率: {data.get('sample_rate')}Hz")
            
            elif event_type == "transcribe_done":
                # 轉譯結果
                text = data.get("text", "")
                confidence = data.get("confidence")
                language = data.get("language")
                duration = data.get("duration")
                # 轉譯結果統一格式
                logger.info("")
                logger.info("=" * 60)
                logger.info(f"📝 轉譯結果: {text}")
                if language:
                    logger.info(f"   語言: {language}")
                if confidence:
                    logger.info(f"   信心度: {confidence:.2f}")
                if duration:
                    logger.info(f"   時長: {duration:.2f} 秒")
                logger.info("=" * 60)
                logger.info("")
            
            elif event_type == "play_asr_feedback":
                # ASR 回饋音控制
                command = data.get("command")
                if command == "play":
                    logger.info("🔊 收到 ASR 回饋音播放事件")
                elif command == "stop":
                    logger.info("🔇 收到 ASR 回饋音停止事件")
            
            elif event_type == "error_reported":
                # 錯誤訊息
                error_code = data.get("error_code", "UNKNOWN")
                error_message = data.get("error_message", "未知錯誤")
                logger.error(f"❌ 錯誤 [{error_code}]: {error_message}")
                
        except Exception as e:
            logger.error(f"處理 SSE 事件時發生錯誤: {e}")
    
    def create_session(self):
        """建立會話"""
        try:
            url = f"{self.base_url}/create_session"
            payload = {
                "strategy": "non_streaming",
                "request_id": self.request_id
            }
            
            logger.info("📤 發送建立 Session 請求")
            logger.debug(f"   策略: non_streaming")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self.session_id = result["session_id"]
            self.sse_url = result["sse_url"]
            
            logger.info("✅ Session 建立成功")
            logger.info(f"   Session ID: {self.session_id}")
            
            # 啟動 SSE 監聽器
            self._start_sse_listener()
            return True
            
        except Exception as e:
            logger.error(f"❌ 建立 Session 失敗: {e}")
            return False
    
    def start_listening(self):
        """開始監聽設定"""
        if not self.session_id:
            logger.error("❌ 尚未建立 Session")
            return False
        
        try:
            url = f"{self.base_url}/start_listening"
            payload = {
                "session_id": self.session_id,
                "sample_rate": self.RATE,
                "channels": self.CHANNELS,
                "format": "int16"
            }
            
            logger.info("📤 發送開始監聽請求")
            logger.debug(f"   取樣率: {self.RATE}Hz, 頻道數: {self.CHANNELS}")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"❌ 開始監聽失敗: {e}")
            return False
    
    def wake_activate(self, source: str = "ui"):
        """啟用喚醒"""
        if not self.session_id:
            logger.error("❌ 尚未建立 Session")
            return False
        
        try:
            url = f"{self.base_url}/wake_activated"
            payload = {
                "session_id": self.session_id,
                "source": source
            }
            
            logger.info("🎯 發送喚醒啟用請求")
            logger.debug(f"   來源: {source}")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"❌ 喚醒啟用失敗: {e}")
            return False
    
    def wake_deactivate(self, source: str = "vad_silence_timeout"):
        """停用喚醒"""
        if not self.session_id:
            logger.error("❌ 尚未建立 Session")
            return False
        
        try:
            url = f"{self.base_url}/wake_deactivated"
            payload = {
                "session_id": self.session_id,
                "source": source
            }
            
            logger.info("🛑 發送喚醒停用請求")
            logger.debug(f"   來源: {source}")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"❌ 喚醒停用失敗: {e}")
            return False
    
    def send_audio_chunk(self, audio_data: bytes):
        """發送音訊片段（使用 metadata + separator + binary 格式）"""
        if not self.session_id:
            return False
        
        try:
            # 組合 metadata JSON
            metadata = {
                "session_id": self.session_id,
                "chunk_id": f"chunk_{time.time()}"
            }
            
            # 使用特殊的格式：JSON metadata + 分隔符 + 二進制數據
            metadata_json = json.dumps(metadata).encode('utf-8')
            separator = b'\x00\x00\xFF\xFF'  # 特殊分隔符
            
            # 組合完整消息
            full_message = metadata_json + separator + audio_data
            
            # 發送到伺服器
            url = f"{self.base_url}/emit_audio_chunk"
            response = requests.post(
                url,
                data=full_message,
                headers={"Content-Type": "application/octet-stream"}
            )
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"發送音訊失敗: {e}")
            return False
    
    def start_microphone(self):
        """開始麥克風錄音並發送音訊"""
        try:
            if not self.session_id:
                logger.error("❌ 無法開始音訊串流：沒有有效的 Session ID")
                return
            
            logger.info("🎤 開始麥克風錄音...")
            
            # 開啟麥克風串流
            self.stream = self.audio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )
            
            logger.info("🎤 麥克風已開啟，開始錄音...")
            logger.info("按 Ctrl+C 停止")
            
            # 音訊處理循環
            while self.is_running:
                try:
                    # 讀取音訊資料
                    audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    
                    # 發送音訊（使用新的格式）
                    self.send_audio_chunk(audio_data)
                    
                except Exception as e:
                    if self.is_running:
                        logger.error(f"音訊處理錯誤: {e}")
                        time.sleep(0.1)
                        
        except Exception as e:
            logger.error(f"開啟麥克風失敗: {e}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                logger.info("🎤 麥克風已關閉")
    
    def stop(self):
        """停止客戶端"""
        logger.info("\n🛑 正在停止客戶端...")
        self.is_running = False
        
        # 關閉音訊
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        
        if self.audio:
            try:
                self.audio.terminate()
            except:
                pass
        
        # 關閉 SSE 連線
        if self.sse_client:
            try:
                self.sse_client.close()
            except:
                pass
        
        # 等待 SSE 執行緒結束
        if self.sse_thread and self.sse_thread.is_alive():
            self.sse_thread.join(timeout=2)
        
        logger.info("✅ 客戶端已停止")


def main():
    """主程式"""
    client = HTTPSSEClient()  # 現在不需要參數，從 ConfigManager 載入
    
    # 設定信號處理
    def signal_handler(sig, frame):
        logger.info("\n收到中斷信號")
        client.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 初始化
        if not client.initialize():
            return
        
        # 建立會話
        if not client.create_session():
            return
        
        # 開始監聽
        if not client.start_listening():
            return
        
        # 測試喚醒啟用/停用（可選）
        # 取消註解以下程式碼來測試喚醒功能和 ASR 回饋音
        # if client.wake_activate("test"):
        #     time.sleep(2)  # 等待 ASR 回饋音播放事件
        #     client.wake_deactivate("test")
        #     time.sleep(1)
        
        # 開始麥克風錄音
        client.start_microphone()
        
    except Exception as e:
        logger.error(f"執行錯誤: {e}")
    finally:
        client.stop()


if __name__ == "__main__":
    logger.info("")
    logger.info("=" * 60)
    logger.info("🚀 HTTP SSE 客戶端測試")
    logger.info("🎤 音訊來源: 麥克風")
    logger.info("⚡ 傳輸方式: 二進制（無 base64）")
    logger.info("=" * 60)
    logger.info("")
    
    main()