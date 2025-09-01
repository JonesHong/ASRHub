#!/usr/bin/env python3
"""
HTTP SSE 客戶端測試程式 - 簡化版
測試 HTTP SSE API 的麥克風音訊串流
"""

import sys
import time
import threading
import signal
import json
from typing import Optional, Dict, Any

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
            logger.info(f"✅ HTTP SSE 客戶端已初始化，連接到 {self.base_url}")
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
                logger.info(f"📡 連接到 SSE: {self.sse_url}")
                
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
                logger.info("📡 SSE 連線已關閉")
        
        # 啟動監聽執行緒
        self.sse_thread = threading.Thread(target=sse_listener, daemon=True)
        self.sse_thread.start()
        time.sleep(0.5)  # 等待連線建立
    
    def _handle_sse_event(self, event_type: str, data: Dict[str, Any]):
        """處理 SSE 事件"""
        try:
            if event_type == "connection_ready":
                logger.info("✅ SSE 連線就緒")
            
            elif event_type == "session_created":
                logger.info(f"✅ 確認會話建立: {data.get('session_id')}")
            
            elif event_type == "listening_started":
                logger.info(f"✅ 確認開始監聽: {data.get('sample_rate')}Hz")
            
            elif event_type == "transcribe_done":
                # 轉譯結果
                text = data.get("text", "")
                confidence = data.get("confidence")
                logger.info("")
                logger.info("=" * 60)
                logger.info(f"📝 轉譯結果: {text}")
                if confidence:
                    logger.info(f"   信心度: {confidence:.2f}")
                logger.info("=" * 60)
                logger.info("")
            
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
            
            logger.info(f"📤 發送建立會話請求")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self.session_id = result["session_id"]
            self.sse_url = result["sse_url"]
            
            logger.info(f"✅ 會話已建立: {self.session_id}")
            
            # 啟動 SSE 監聽器
            self._start_sse_listener()
            return True
            
        except Exception as e:
            logger.error(f"建立會話失敗: {e}")
            return False
    
    def start_listening(self):
        """開始監聽設定"""
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        try:
            url = f"{self.base_url}/start_listening"
            payload = {
                "session_id": self.session_id,
                "sample_rate": self.RATE,
                "channels": self.CHANNELS,
                "format": "int16"
            }
            
            logger.info(f"📤 發送開始監聽請求")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"開始監聽失敗: {e}")
            return False
    
    def send_audio_chunk(self, audio_data: bytes):
        """發送音訊片段（二進制傳輸）"""
        if not self.session_id:
            return False
        
        try:
            # 使用二進制傳輸（無 base64 編碼）
            url = f"{self.base_url}/emit_audio_chunk"
            params = {
                "session_id": self.session_id,
                "sample_rate": self.RATE,
                "channels": self.CHANNELS,
                "format": "int16"
            }
            
            response = requests.post(
                url, 
                data=audio_data,
                params=params,
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
                logger.error("無法開始音訊串流：沒有有效的 session_id")
                return
            
            logger.info(f"🎤 開始麥克風錄音...")
            
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
                    
                    # 直接發送二進制音訊
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
        logger.info("🛑 正在停止客戶端...")
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
        
        # 開始麥克風錄音
        client.start_microphone()
        
    except Exception as e:
        logger.error(f"執行錯誤: {e}")
    finally:
        client.stop()


if __name__ == "__main__":
    logger.info("🚀 HTTP SSE 客戶端測試 - 簡化版")
    logger.info("=" * 60)
    logger.info("🎤 音訊來源: 麥克風")
    logger.info("⚡ 傳輸方式: 二進制（無 base64）")
    logger.info("=" * 60)
    
    main()