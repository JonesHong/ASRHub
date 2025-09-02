#!/usr/bin/env python3
"""
ASR Hub 主程式入口

基於 PyStoreX 事件驅動架構和無狀態服務
支援多種通訊協定：Redis、HTTP SSE、WebSocket、Socket.IO
"""

import asyncio
import sys
import signal
import socket
import subprocess
import platform
from pathlib import Path
import warnings


# 全域過濾含有 "pkg_resources is deprecated" 的 UserWarning
warnings.filterwarnings(
    "ignore",
    message=".*pkg_resources is deprecated.*",
    category=UserWarning
)
warnings.filterwarnings(
    "ignore",
    message=".*cupyx.jit.rawkernel is experimental.*",
    category=FutureWarning
)

from src.utils.logger import logger, setup_global_exception_handler
from src.config.manager import ConfigManager
from src.utils.id_provider import new_id

# 設定專案根目錄
PROJECT_ROOT = Path(__file__).parent
sys.path.append(str(PROJECT_ROOT))


class ASRHubServer:
    """ASR Hub 伺服器管理器"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.is_running = False
        self.redis_enabled = False
        self.http_sse_enabled = False
        self.webrtc_enabled = False
        
    def check_and_clean_ports(self):
        """檢查並清理所有被占用的 port"""
        logger.info("🔍 檢查連接埠占用狀態...")
        
        # 收集需要檢查的 ports
        ports_to_check = []
        
        # Redis port
        # if hasattr(self.config.api, 'redis') and self.config.api.redis.enabled:
        #     ports_to_check.append((
        #         self.config.api.redis.port,
        #         "Redis",
        #         self.config.api.redis.host
        #     ))
        
        # HTTP SSE port
        if hasattr(self.config.api, 'http_sse') and self.config.api.http_sse.enabled:
            ports_to_check.append((
                self.config.api.http_sse.port,
                "HTTP SSE",
                self.config.api.http_sse.host
            ))
        
        # WebSocket port
        if hasattr(self.config.api, 'websocket') and self.config.api.websocket.enabled:
            ports_to_check.append((
                self.config.api.websocket.port,
                "WebSocket",
                self.config.api.websocket.host
            ))
        
        # Socket.IO port
        if hasattr(self.config.api, 'socketio') and self.config.api.socketio.enabled:
            ports_to_check.append((
                self.config.api.socketio.port,
                "Socket.IO",
                self.config.api.socketio.host
            ))
        
        # WebRTC port
        if hasattr(self.config.api, 'webrtc') and self.config.api.webrtc.enabled:
            ports_to_check.append((
                self.config.api.webrtc.port,
                "WebRTC",
                self.config.api.webrtc.host
            ))
        
        # 檢查並清理每個 port
        for port, service_name, host in ports_to_check:
            self._check_and_kill_port(port, service_name, host)
        
        logger.success("✅ 連接埠檢查完成")
    
    def _check_and_kill_port(self, port: int, service_name: str, host: str = "127.0.0.1"):
        """檢查單個 port 並在必要時 kill 占用的程序"""
        # 檢查 port 是否被占用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        
        # 如果 host 是 127.0.0.1，檢查 127.0.0.1
        check_host = "127.0.0.1" if host == "127.0.0.1" else host
        
        try:
            result = sock.connect_ex((check_host, port))
            sock.close()
            
            if result == 0:
                # Port 被占用
                logger.warning(f"⚠️  Port {port} ({service_name}) 已被占用，嘗試清理...")
                
                # 根據作業系統使用不同的命令
                system = platform.system()
                
                try:
                    if system == "Windows":
                        # Windows: 使用 netstat 找出 PID，然後 taskkill
                        cmd = f"netstat -ano | findstr :{port}"
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                        lines = result.stdout.strip().split('\n')
                        
                        for line in lines:
                            if f":{port}" in line and "LISTENING" in line:
                                parts = line.split()
                                if parts:
                                    pid = parts[-1]
                                    if pid and pid.isdigit():
                                        # Kill 進程
                                        kill_cmd = f"taskkill /F /PID {pid}"
                                        subprocess.run(kill_cmd, shell=True, capture_output=True)
                                        logger.info(f"   ✅ 已終止占用 port {port} 的進程 (PID: {pid})")
                                        break
                    
                    elif system == "Linux" or system == "Darwin":  # Linux or macOS
                        # Unix-like: 使用 lsof 或 fuser
                        try:
                            # 嘗試使用 lsof
                            cmd = f"lsof -ti:{port}"
                            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                            
                            if result.stdout.strip():
                                pids = result.stdout.strip().split('\n')
                                for pid in pids:
                                    if pid:
                                        # Kill 進程
                                        kill_cmd = f"kill -9 {pid}"
                                        subprocess.run(kill_cmd, shell=True, capture_output=True)
                                        logger.info(f"   ✅ 已終止占用 port {port} 的進程 (PID: {pid})")
                        except:
                            # 如果 lsof 不可用，嘗試 fuser
                            try:
                                cmd = f"fuser -k {port}/tcp"
                                subprocess.run(cmd, shell=True, capture_output=True)
                                logger.info(f"   ✅ 已使用 fuser 清理 port {port}")
                            except:
                                logger.warning(f"   ⚠️  無法自動清理 port {port}，請手動檢查")
                    
                    # 等待一下讓 port 釋放
                    import time
                    time.sleep(0.5)
                    
                    # 再次檢查 port 是否已釋放
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((check_host, port))
                    sock.close()
                    
                    if result != 0:
                        logger.success(f"   ✅ Port {port} ({service_name}) 已成功釋放")
                    else:
                        logger.warning(f"   ⚠️  Port {port} ({service_name}) 仍被占用，可能需要手動處理")
                        
                except Exception as e:
                    logger.error(f"   ❌ 清理 port {port} 時發生錯誤: {e}")
            else:
                logger.info(f"   ✅ Port {port} ({service_name}) 未被占用")
                
        except Exception as e:
            # 連接失敗表示 port 未被占用（這是好事）
            logger.info(f"   ✅ Port {port} ({service_name}) 未被占用")
        finally:
            sock.close()
    
    def initialize_services(self):
        """初始化所有服務"""
        logger.info("🔧 正在初始化服務...")
        
        # 統一顯示所有服務的載入狀態
        services_loaded = []
        
        # 初始化 PyStoreX Store
        from src.store.main_store import main_store
        services_loaded.append("✅ PyStoreX Store")
        
        # 初始化音訊服務
        from src.service.audio_converter.service import audio_converter_service
        services_loaded.append("✅ 音訊轉換服務")
        
        # 初始化 VAD 服務
        from src.service.vad import silero_vad
        if silero_vad.__class__.__name__ != 'DisabledService':
            services_loaded.append("✅ Silero VAD")
        
        # 初始化 Wakeword 服務
        from src.service.wakeword import openwakeword
        if openwakeword.__class__.__name__ != 'DisabledService':
            services_loaded.append("✅ OpenWakeWord")
        
        # 初始化錄音服務
        from src.service.recording import recording
        if recording.__class__.__name__ != 'DisabledService':
            services_loaded.append("✅ 錄音服務")
        
        # 初始化麥克風服務
        from src.service.microphone_capture import microphone_capture
        if microphone_capture.__class__.__name__ != 'DisabledService':
            # 確保服務在啟動時就被初始化（而不是延遲到停止時）
            # 呼叫一個安全的方法來觸發實際載入
            if hasattr(microphone_capture, 'is_capturing'):
                microphone_capture.is_capturing()  # 這會觸發延遲載入
            services_loaded.append("✅ 麥克風擷取")
        
        # 初始化計時器服務
        from src.service.timer import timer_service
        if timer_service.__class__.__name__ != 'DisabledService':
            services_loaded.append("✅ 計時器服務")
        
        # 初始化 Provider Pool（延遲載入模式）
        from src.provider.provider_manager import get_provider_manager
        provider_manager = get_provider_manager()
        services_loaded.append("✅ Provider Pool")
        
        # 統一顯示所有已載入服務
        # 使用 block 顯示已載入服務
        logger.block("服務初始化完成", services_loaded)
    
    async def initialize_and_warm_up_providers(self):
        """初始化並 warm up provider pool"""
        try:
            logger.info("🔥 開始 Provider Pool warm up...")
            
            from src.provider.provider_manager import get_provider_manager
            provider_manager = get_provider_manager()
            
            # Provider Pool 負責模型載入，支援等待模式
            await self._run_in_thread(
                lambda: provider_manager.warm_up(wait_for_completion=True)
            )
            
            logger.success("✅ Provider Pool warm up 完成")
            
        except Exception as e:
            logger.warning(f"⚠️ Provider warm up 失敗: {e}")
            logger.info("   首次 ASR 請求會觸發模型載入")
    
    async def _run_in_thread(self, func):
        """在執行緒中執行同步函數"""
        import asyncio
        import functools
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)
    
    def initialize_api_servers(self):
        """初始化 API 伺服器"""
        logger.info("🌐 正在初始化 API 伺服器...")
        
        api_servers = []
        
        # Redis Pub/Sub
        if hasattr(self.config.api, 'redis') and self.config.api.redis.enabled:
            try:
                from src.api.redis.server import initialize as init_redis
                init_redis()
                self.redis_enabled = True
                api_servers.append(f"✅ Redis Pub/Sub ({self.config.api.redis.host}:{self.config.api.redis.port})")
            except Exception as e:
                api_servers.append(f"❌ Redis 初始化失敗: {e}")
        else:
            api_servers.append("⏭️  Redis Pub/Sub 已停用")
        
        # HTTP SSE
        if hasattr(self.config.api, 'http_sse') and self.config.api.http_sse.enabled:
            try:
                # 在背景執行緒啟動 HTTP SSE 伺服器
                import threading
                import asyncio
                
                def run_http_sse_server():
                    """在獨立執行緒中運行 HTTP SSE 伺服器"""
                    from src.api.http_sse.server import http_sse_server
                    
                    # 創建新的事件循環
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # 初始化並啟動伺服器
                    loop.run_until_complete(http_sse_server.initialize())
                    loop.run_until_complete(http_sse_server.start())
                
                http_thread = threading.Thread(
                    target=run_http_sse_server,
                    daemon=True,
                    name="HTTPSSEServer"
                )
                http_thread.start()
                
                # 等待伺服器啟動
                import time
                time.sleep(1)
                
                self.http_sse_enabled = True
                api_servers.append(f"✅ HTTP SSE 伺服器 (http://{self.config.api.http_sse.host}:{self.config.api.http_sse.port})")
            except Exception as e:
                api_servers.append(f"❌ HTTP SSE 初始化失敗: {e}")
        else:
            api_servers.append("⏭️  HTTP SSE 已停用")
        
        # WebSocket (未來實作)
        if hasattr(self.config.api, 'websocket') and self.config.api.websocket.enabled:
            api_servers.append(f"⏸️  WebSocket 伺服器待實作 (port: {self.config.api.websocket.port})")
        else:
            api_servers.append("⏭️  WebSocket 已停用")
        
        # Socket.IO (未來實作)
        if hasattr(self.config.api, 'socketio') and self.config.api.socketio.enabled:
            api_servers.append(f"⏸️  Socket.IO 伺服器待實作 (port: {self.config.api.socketio.port})")
        else:
            api_servers.append("⏭️  Socket.IO 已停用")
        
        # WebRTC (LiveKit)
        if hasattr(self.config.api, 'webrtc') and self.config.api.webrtc.enabled:
            try:
                # 在背景執行緒啟動 WebRTC 伺服器
                import threading
                import asyncio
                
                def run_webrtc_server():
                    """在獨立執行緒中運行 WebRTC 伺服器"""
                    from src.api.webrtc.server import webrtc_server
                    
                    # 創建新的事件循環
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # 初始化並啟動伺服器
                    loop.run_until_complete(webrtc_server.initialize())
                    loop.run_until_complete(webrtc_server.start())
                
                webrtc_thread = threading.Thread(
                    target=run_webrtc_server,
                    daemon=True,
                    name="WebRTCServer"
                )
                webrtc_thread.start()
                
                # 等待伺服器啟動
                import time
                time.sleep(1)
                
                self.webrtc_enabled = True
                api_servers.append(f"✅ WebRTC 伺服器 (http://{self.config.api.webrtc.host}:{self.config.api.webrtc.port})")
                api_servers.append(f"   LiveKit: {self.config.api.webrtc.livekit.url}")
            except Exception as e:
                api_servers.append(f"❌ WebRTC 初始化失敗: {e}")
        else:
            api_servers.append("⏭️  WebRTC (LiveKit) 已停用")
        
        # 使用 block 顯示 API 伺服器狀態
        logger.block("API 伺服器狀態", api_servers)
    
    async def start(self):
        """啟動伺服器"""
        logger.block("ASR Hub", [
            "🚀 ASR Hub 啟動中...",
            "基於 PyStoreX 事件驅動架構",
            "支援多種通訊協定"
        ])
        
        # 檢查並清理被占用的 ports
        self.check_and_clean_ports()
        
        # 初始化服務
        self.initialize_services()
        
        # Provider Pool 負責模型預載
        await self.initialize_and_warm_up_providers()
        
        # 初始化 API 伺服器
        self.initialize_api_servers()
        
        self.is_running = True
        
        # 顯示啟用的服務
        enabled_services = []
        if self.redis_enabled:
            enabled_services.append(f"📡 Redis: {self.config.api.redis.host}:{self.config.api.redis.port}")
        if self.http_sse_enabled:
            enabled_services.append(f"🌐 HTTP SSE: http://{self.config.api.http_sse.host}:{self.config.api.http_sse.port}")
        if self.webrtc_enabled:
            enabled_services.append(f"🎥 WebRTC: http://{self.config.api.webrtc.host}:{self.config.api.webrtc.port}")

        if enabled_services:
            enabled_services.append("")
            enabled_services.append("⏹️  按 Ctrl+C 停止服務")
            
            logger.block("🎉 ASR Hub 啟動完成", enabled_services)
        else:
            logger.warning("⚠️  沒有啟用任何通訊協定")
            logger.info("⏹️  按 Ctrl+C 停止服務")
        
    async def stop(self):
        """停止伺服器"""
        if not self.is_running:
            return
        
        logger.info("🛑 正在停止 ASR Hub...")
        self.is_running = False
        
        # 停止各個服務
        try:
            # 停止麥克風擷取
            from src.service.microphone_capture import microphone_capture
            if hasattr(microphone_capture, 'stop_capture'):
                microphone_capture.stop_capture()
            
            # 停止 Provider Pool
            from src.provider.provider_manager import get_provider_manager
            provider_manager = get_provider_manager()
            if hasattr(provider_manager, 'shutdown'):
                provider_manager.shutdown()
            
            logger.success("✅ ASR Hub 已安全停止")
        except Exception as e:
            logger.error(f"停止服務時發生錯誤: {e}")


async def main():
    """主程式入口"""
    # 設定全域異常處理器
    setup_global_exception_handler()
    
    server = ASRHubServer()
    
    # 設定信號處理
    def signal_handler(signum, frame):
        logger.info("\n收到停止信號...")
        asyncio.create_task(server.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 啟動服務
        await server.start()
        
        # 保持運行
        while server.is_running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"執行錯誤：{e}")
        raise
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服務已停止")
    except Exception as e:
        print(f"錯誤：{e}")
        sys.exit(1)