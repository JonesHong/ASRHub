#!/usr/bin/env python3
"""
HTTP SSE 客戶端測試程式
測試 HTTP SSE API 的完整流程：
1. 建立會話
2. 設定音訊參數  
3. 從麥克風或檔案讀取音訊並發送
4. 透過 SSE 接收轉譯結果
"""

import sys
import time
import base64
import threading
import signal
import json
import wave
from datetime import datetime
from typing import Optional, Dict, Any, Union
from pathlib import Path

import requests
import pyaudio
import numpy as np
from sseclient import SSEClient  # pip install sseclient-py

from src.interface.strategy import Strategy
from src.interface.wake import WakeActivateSource, WakeDeactivateSource
from src.utils.id_provider import new_id
from src.utils.logger import logger


class HTTPSSEClient:
    """HTTP SSE 客戶端實現"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000, wait_confirmations: bool = True, use_binary: bool = True):
        """初始化 HTTP SSE 客戶端
        
        Args:
            host: HTTP 伺服器主機
            port: HTTP 伺服器連接埠
            wait_confirmations: 是否等待確認訊息（預設 True）
            use_binary: 是否使用二進制傳輸（預設 True，不使用 base64）
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/api/v1"
        self.wait_confirmations = wait_confirmations
        self.use_binary = use_binary
        
        # 會話資訊
        self.request_id: str = new_id()
        self.session_id: Optional[str] = None
        self.sse_url: Optional[str] = None
        self.audio_url: Optional[str] = None
        self.is_running = False
        
        # 音訊設定
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.CHUNK = 1024
        
        # PyAudio
        self.audio = None
        self.stream = None
        
        # SSE 連線
        self.sse_thread: Optional[threading.Thread] = None
        self.sse_client: Optional[SSEClient] = None
        
        # 事件（可選擇性使用）
        self.session_created_event = threading.Event()
        self.listening_started_event = threading.Event()
        self.wake_activated_event = threading.Event()
        self.wake_deactivated_event = threading.Event()
        
    def initialize(self) -> bool:
        """初始化客戶端"""
        try:
            # 初始化 PyAudio
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
                            # 解析事件資料
                            data = json.loads(event.data)
                            # event.event 可能是 None，使用預設值
                            event_type = event.event or "message"
                            self._handle_sse_event(event_type, data)
                        except json.JSONDecodeError:
                            logger.error(f"無法解析 SSE 事件資料: {event.data}")
                        except Exception as e:
                            logger.error(f"處理 SSE 事件時發生錯誤: {e}")
                            
            except Exception as e:
                logger.error(f"SSE 監聽器錯誤: {e}")
            finally:
                logger.info("📡 SSE 連線已關閉")
        
        # 啟動監聽執行緒
        self.sse_thread = threading.Thread(target=sse_listener, daemon=True)
        self.sse_thread.start()
        
        # 等待連線建立
        time.sleep(0.5)
    
    def _handle_sse_event(self, event_type: str, data: Dict[str, Any]):
        """處理 SSE 事件
        
        Args:
            event_type: 事件類型
            data: 事件資料
        """
        try:
            logger.info(f"📨 收到 SSE 事件 [{event_type}]: {data}")
            
            if event_type == "connection_ready":
                logger.info("✅ SSE 連線就緒")
            
            elif event_type == "session_created":
                logger.info(f"✅ 確認會話建立: {data.get('session_id')}")
                self.session_created_event.set()
            
            elif event_type == "listening_started":
                logger.info(f"✅ 確認開始監聽: {data.get('sample_rate')}Hz, {data.get('channels')}ch")
                self.listening_started_event.set()
            
            elif event_type == "wake_activated":
                logger.info(f"✅ 確認喚醒啟用: 來源={data.get('source')}")
                self.wake_activated_event.set()
            
            elif event_type == "wake_deactivated":
                logger.info(f"✅ 確認喚醒停用: 來源={data.get('source')}")
                self.wake_deactivated_event.set()
            
            elif event_type == "transcribe_done":
                self._handle_transcribe_done(data)
            
            elif event_type == "play_asr_feedback":
                self._handle_asr_feedback(data)
            
            elif event_type == "error_reported":
                self._handle_error(data)
            
            elif event_type == "heartbeat":
                logger.debug(f"💓 心跳: seq={data.get('sequence')}")
                
        except Exception as e:
            logger.error(f"處理 SSE 事件時發生錯誤: {e}")
    
    def _handle_transcribe_done(self, data: Dict[str, Any]):
        """處理轉譯完成事件"""
        text = data.get("text", "")
        confidence = data.get("confidence")
        language = data.get("language")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"📝 轉譯結果: {text}")
        if confidence:
            logger.info(f"   信心度: {confidence:.2f}")
        if language:
            logger.info(f"   語言: {language}")
        logger.info("=" * 60)
        logger.info("")
    
    def _handle_asr_feedback(self, data: Dict[str, Any]):
        """處理 ASR 回饋音控制"""
        command = data.get("command")
        if command == "play":
            logger.info("🔊 ASR 回饋音: 播放")
        elif command == "stop":
            logger.info("🔇 ASR 回饋音: 停止")
    
    def _handle_error(self, data: Dict[str, Any]):
        """處理錯誤訊息"""
        error_code = data.get("error_code", "UNKNOWN")
        error_message = data.get("error_message", "未知錯誤")
        logger.error(f"❌ 錯誤 [{error_code}]: {error_message}")
    
    def create_session(self, strategy: str = "non_streaming"):
        """建立會話"""
        try:
            # 發送建立會話請求
            url = f"{self.base_url}/create_session"
            payload = {
                "strategy": strategy,
                "request_id": self.request_id
            }
            
            logger.info(f"📤 發送建立會話請求 (策略: {strategy}, request_id: {self.request_id})")
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            # 解析回應
            result = response.json()
            self.session_id = result["session_id"]
            self.sse_url = result["sse_url"]
            self.audio_url = result["audio_url"]
            
            logger.info(f"✅ 會話已建立: {self.session_id}")
            logger.info(f"   SSE URL: {self.sse_url}")
            logger.info(f"   Audio URL: {self.audio_url}")
            
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
            # 發送開始監聽請求
            url = f"{self.base_url}/start_listening"
            payload = {
                "session_id": self.session_id,
                "sample_rate": self.RATE,
                "channels": self.CHANNELS,
                "format": "int16"
            }
            
            logger.info(f"📤 發送開始監聽請求 (session: {self.session_id}, {self.RATE}Hz, {self.CHANNELS}ch)")
            
            self.listening_started_event.clear()
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            # 根據設定決定是否等待確認
            if self.wait_confirmations:
                if not self.listening_started_event.wait(timeout=5):
                    logger.warning("開始監聽確認超時，但繼續執行")
            
            return True
            
        except Exception as e:
            logger.error(f"開始監聽失敗: {e}")
            return False
    
    def send_audio_chunk(self, audio_data: bytes, chunk_id: Optional[str] = None):
        """發送音訊片段
        
        Args:
            audio_data: 音訊資料（bytes）
            chunk_id: 音訊片段 ID（可選）
        """
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        try:
            # 使用原本的 emit_audio_chunk 端點
            url = f"{self.base_url}/emit_audio_chunk"
            
            if self.use_binary:
                # 使用二進制傳輸（推薦，沒有 base64 編碼開銷）
                # 準備查詢參數（包含 session_id）
                params = {
                    "session_id": self.session_id,
                    "sample_rate": self.RATE,
                    "channels": self.CHANNELS,
                    "format": "int16"
                }
                if chunk_id:
                    params["chunk_id"] = chunk_id
                
                # 直接發送二進制資料
                response = requests.post(
                    url, 
                    data=audio_data,
                    params=params,
                    headers={"Content-Type": "application/octet-stream"}
                )
                response.raise_for_status()
                
            else:
                # 舊的 base64 方法已不再支援，自動切換為二進位模式
                logger.warning("⚠️ Base64 模式已不再支援，自動切換為二進位模式")
                self.use_binary = True
                
                # 改用二進位模式重新發送
                params = {
                    "session_id": self.session_id,
                    "sample_rate": self.RATE,
                    "channels": self.CHANNELS,
                    "format": "int16"
                }
                if chunk_id:
                    params["chunk_id"] = chunk_id
                
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
    
    def start_audio_stream_from_mic(self):
        """從麥克風開始音訊串流"""
        try:
            if not self.session_id:
                logger.error("無法開始音訊串流：沒有有效的 session_id")
                return
            
            logger.info(f"🎤 開始麥克風音訊串流，session_id: {self.session_id}")
            
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
            
            chunk_count = 0
            
            # 音訊處理循環
            while self.is_running:
                try:
                    # 讀取音訊資料
                    audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    
                    # 發送音訊資料
                    chunk_id = f"mic_chunk_{chunk_count}"
                    self.send_audio_chunk(audio_data, chunk_id)
                    chunk_count += 1
                    
                except Exception as e:
                    if self.is_running:
                        logger.error(f"音訊處理錯誤: {e}")
                        time.sleep(0.1)
                        
        except Exception as e:
            logger.error(f"開啟麥克風串流失敗: {e}")
        finally:
            self.stop_audio_stream()
    
    def start_audio_stream_from_file(self, file_path: str):
        """從檔案讀取音訊並發送
        
        Args:
            file_path: 音訊檔案路徑
        """
        try:
            if not self.session_id:
                logger.error("無法開始音訊串流：沒有有效的 session_id")
                return
            
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"檔案不存在: {file_path}")
                return
            
            logger.info(f"📁 從檔案讀取音訊: {file_path}")
            
            # 開啟 WAV 檔案
            with wave.open(str(file_path), 'rb') as wf:
                # 檢查音訊格式
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                
                logger.info(f"   格式: {channels}ch, {framerate}Hz, {sample_width*8}bit")
                
                # 檢查是否需要重新採樣
                if framerate != self.RATE or channels != self.CHANNELS:
                    logger.warning(f"⚠️ 音訊格式不符，預期 {self.CHANNELS}ch {self.RATE}Hz")
                    logger.warning("   建議使用 ffmpeg 轉換格式：")
                    logger.warning(f"   ffmpeg -i {file_path} -ar {self.RATE} -ac {self.CHANNELS} output.wav")
                
                # 讀取並發送音訊
                chunk_count = 0
                frame_size = self.CHUNK
                
                logger.info("📤 開始發送音訊資料...")
                
                while self.is_running:
                    # 讀取音訊片段
                    frames = wf.readframes(frame_size)
                    if not frames:
                        break
                    
                    # 發送音訊資料
                    chunk_id = f"file_chunk_{chunk_count}"
                    self.send_audio_chunk(frames, chunk_id)
                    chunk_count += 1
                    
                    # 模擬即時播放速度
                    time.sleep(frame_size / framerate)
                
                logger.info(f"✅ 音訊檔案發送完成，共 {chunk_count} 個片段")
                
        except Exception as e:
            logger.error(f"讀取音訊檔案失敗: {e}")
    
    def wake_activate(self, source: str = WakeActivateSource.UI):
        """發送喚醒啟用請求
        
        Args:
            source: 啟用來源 (visual, ui, keyword)
        """
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        try:
            url = f"{self.base_url}/wake_activated"
            payload = {
                "session_id": self.session_id,
                "source": source
            }
            
            logger.info(f"🎯 發送喚醒啟用請求 (session: {self.session_id}, source: {source})")
            
            self.wake_activated_event.clear()
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            # 根據設定決定是否等待確認
            if self.wait_confirmations:
                if not self.wake_activated_event.wait(timeout=5):
                    logger.warning("喚醒啟用確認超時，但繼續執行")
            
            return True
            
        except Exception as e:
            logger.error(f"喚醒啟用失敗: {e}")
            return False
    
    def wake_deactivate(self, source: str = WakeDeactivateSource.VAD_SILENCE_TIMEOUT):
        """發送喚醒停用請求
        
        Args:
            source: 停用來源 (visual, ui, vad_silence_timeout)
        """
        if not self.session_id:
            logger.error("尚未建立會話")
            return False
        
        try:
            url = f"{self.base_url}/wake_deactivated"
            payload = {
                "session_id": self.session_id,
                "source": source
            }
            
            logger.info(f"🛑 發送喚醒停用請求 (session: {self.session_id}, source: {source})")
            
            self.wake_deactivated_event.clear()
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            # 根據設定決定是否等待確認
            if self.wait_confirmations:
                if not self.wake_deactivated_event.wait(timeout=5):
                    logger.warning("喚醒停用確認超時，但繼續執行")
            
            return True
            
        except Exception as e:
            logger.error(f"喚醒停用失敗: {e}")
            return False
    
    def stop_audio_stream(self):
        """停止音訊串流"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
                logger.info("🎤 音訊串流已關閉")
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


def main(audio_source: str = "mic", file_path: Optional[str] = None, wait_confirmations: bool = True, use_binary: bool = True):
    """主程式
    
    Args:
        audio_source: 音訊來源 ("mic" 或 "file")
        file_path: 音訊檔案路徑（當 audio_source 為 "file" 時）
        wait_confirmations: 是否等待確認訊息（預設 True）
        use_binary: 是否使用二進制傳輸（預設 True）
    """
    client = HTTPSSEClient(wait_confirmations=wait_confirmations, use_binary=use_binary)
    
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
        # client.wake_activate(WakeActivateSource.UI)
        # time.sleep(2)
        # client.wake_deactivate(WakeDeactivateSource.VAD_SILENCE_TIMEOUT)
        
        # 根據音訊來源開始串流
        if audio_source == "file" and file_path:
            client.start_audio_stream_from_file(file_path)
            # 等待一段時間以接收轉譯結果
            time.sleep(5)
        else:
            # 預設使用麥克風
            client.start_audio_stream_from_mic()
        
    except Exception as e:
        logger.error(f"執行錯誤: {e}")
    finally:
        client.stop()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="HTTP SSE 客戶端測試")
    parser.add_argument(
        "--source",
        choices=["mic", "file"],
        default="mic",
        help="音訊來源：mic（麥克風）或 file（檔案）"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="test_audio/small.wav",
        help="音訊檔案路徑（當 source=file 時使用）"
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="不等待伺服器確認訊息"
    )
    parser.add_argument(
        "--use-base64",
        action="store_true",
        help="使用 base64 編碼傳輸（預設使用二進制）"
    )
    
    args = parser.parse_args()
    
    logger.info("🚀 HTTP SSE 客戶端測試")
    logger.info("=" * 60)
    
    if args.source == "file":
        logger.info(f"📁 音訊來源: 檔案 ({args.file})")
    else:
        logger.info("🎤 音訊來源: 麥克風")
    
    if args.use_base64:
        logger.info("📦 傳輸方式: Base64 編碼")
    else:
        logger.info("⚡ 傳輸方式: 二進制（直接）")
    
    logger.info("=" * 60)
    
    main(
        audio_source=args.source,
        file_path=args.file if args.source == "file" else None,
        wait_confirmations=not args.no_wait,
        use_binary=not args.use_base64
    )