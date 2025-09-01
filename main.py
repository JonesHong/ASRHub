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
        
    def check_and_clean_ports(self):
        """檢查並清理所有被占用的 port"""
        logger.info("🔍 檢查 API port 占用狀況...")
        
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
        
        # 檢查並清理每個 port
        for port, service_name, host in ports_to_check:
            self._check_and_kill_port(port, service_name, host)
        
        logger.success("✅ Port 檢查完成")
    
    def _check_and_kill_port(self, port: int, service_name: str, host: str = "0.0.0.0"):
        """檢查單個 port 並在必要時 kill 占用的程序"""
        # 檢查 port 是否被占用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        
        # 如果 host 是 0.0.0.0，檢查 127.0.0.1
        check_host = "127.0.0.1" if host == "0.0.0.0" else host
        
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
        logger.info("🔧 初始化服務...")
        
        # 初始化 PyStoreX Store
        from src.store.main_store import main_store
        logger.info("✅ PyStoreX Store 已初始化")
        
        # 初始化音訊服務
        from src.service.audio_converter.service import audio_converter_service
        logger.info("✅ 音訊轉換服務已初始化")
        
        # 初始化 VAD 服務
        from src.service.vad import silero_vad
        if silero_vad.__class__.__name__ != 'DisabledService':
            logger.info("✅ Silero VAD 服務已初始化")
        else:
            logger.info("⏭️  Silero VAD 服務已停用")
        
        # 初始化 Wakeword 服務
        from src.service.wakeword import openwakeword
        if openwakeword.__class__.__name__ != 'DisabledService':
            logger.info("✅ OpenWakeWord 服務已初始化")
        else:
            logger.info("⏭️  OpenWakeWord 服務已停用")
        
        # 初始化錄音服務
        from src.service.recording import recording
        if recording.__class__.__name__ != 'DisabledService':
            logger.info("✅ 錄音服務已初始化")
        else:
            logger.info("⏭️  錄音服務已停用")
        
        # 初始化麥克風服務
        from src.service.microphone_capture import microphone_capture
        if microphone_capture.__class__.__name__ != 'DisabledService':
            logger.info("✅ 麥克風擷取服務已初始化")
        else:
            logger.info("⏭️  麥克風擷取服務已停用")
        
        # 初始化計時器服務
        from src.service.timer import timer_service
        if timer_service.__class__.__name__ != 'DisabledService':
            logger.info("✅ 計時器服務已初始化")
        else:
            logger.info("⏭️  計時器服務已停用")
        
        # 初始化 Provider Pool（延遲載入模式）
        from src.provider.provider_manager import get_provider_manager
        provider_manager = get_provider_manager()
        logger.info("✅ Provider Pool Manager 已初始化（延遲載入模式）")
    
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
        logger.info("🌐 初始化 API 伺服器...")
        
        # Redis Pub/Sub
        if hasattr(self.config.api, 'redis') and self.config.api.redis.enabled:
            try:
                from src.api.redis.server import initialize as init_redis
                init_redis()
                self.redis_enabled = True
                logger.info(f"✅ Redis Pub/Sub 已啟用 ({self.config.api.redis.host}:{self.config.api.redis.port})")
            except Exception as e:
                logger.error(f"❌ Redis 初始化失敗: {e}")
        else:
            logger.info("⏭️  Redis Pub/Sub 已停用")
        
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
                logger.info(f"✅ HTTP SSE 伺服器已啟用 (http://{self.config.api.http_sse.host}:{self.config.api.http_sse.port})")
            except Exception as e:
                logger.error(f"❌ HTTP SSE 初始化失敗: {e}")
        else:
            logger.info("⏭️  HTTP SSE 已停用")
        
        # WebSocket (未來實作)
        if hasattr(self.config.api, 'websocket') and self.config.api.websocket.enabled:
            logger.info(f"⏸️  WebSocket 伺服器待實作 (port: {self.config.api.websocket.port})")
        else:
            logger.info("⏭️  WebSocket 已停用")
        
        # Socket.IO (未來實作)
        if hasattr(self.config.api, 'socketio') and self.config.api.socketio.enabled:
            logger.info(f"⏸️  Socket.IO 伺服器待實作 (port: {self.config.api.socketio.port})")
        else:
            logger.info("⏭️  Socket.IO 已停用")
    
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
        
        logger.success("🎉 ASR Hub 啟動完成！")
        
        # 顯示啟用的服務
        enabled_services = []
        if self.redis_enabled:
            enabled_services.append(f"Redis: {self.config.api.redis.host}:{self.config.api.redis.port}")
        if self.http_sse_enabled:
            enabled_services.append(f"HTTP SSE: http://{self.config.api.http_sse.host}:{self.config.api.http_sse.port}")

        if enabled_services:
            logger.info("📡 已啟用的通訊協定:")
            for service in enabled_services:
                logger.info(f"   • {service}")
        else:
            logger.warning("⚠️  沒有啟用任何通訊協定")
        
        logger.info("⏹️  按 Ctrl+C 停止服務")
        
        # 顯示最終狀態
        logger.info("🎉 所有服務已啟動完成")
        
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