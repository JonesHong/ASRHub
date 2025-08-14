"""
ASR Hub 主要入口類別
協調各模組運作的核心系統
"""

import sys
import asyncio
from typing import Optional, Dict, Any
import warnings

# 忽略 ctranslate2 的 pkg_resources 棄用警告
warnings.filterwarnings('ignore', 
                       message='.*pkg_resources is deprecated as an API.*',
                       category=DeprecationWarning)
from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.utils.logger import setup_global_exception_handler
from src.core.session_manager import SessionManager
from src.core.fsm import StateMachine, State
from src.pipeline.manager import PipelineManager
from src.providers.manager import ProviderManager
from src.stream.stream_controller import StreamController
from src.api.http_sse.server import SSEServer
from src.api.websocket.server import WebSocketServer
from src.api.socketio.server import SocketIOServer


class ASRHub:
    """
    ASR Hub 主系統類別
    負責初始化和協調所有子系統
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化 ASR Hub
        
        Args:
            config_path: 自定義配置檔案路徑，如果不提供則使用預設路徑
        """
        # 獲取配置（單例模式）
        self.config = ConfigManager(config_path)
        
        # 建立 logger
        self.logger = logger
        
        # 設置全域異常處理
        setup_global_exception_handler()
        
        # 系統資訊
        self.app_name = self.config.system.name
        self.version = self.config.system.version
        self.debug = self.config.system.debug
        
        # 其他配置
        self.api_config = self.config.api
        self.pipeline_config = self.config.pipeline
        self.providers_config = self.config.providers
        self.stream_config = self.config.stream
        
        # 核心元件
        self.session_manager = None
        self.pipeline_manager = None
        self.provider_manager = None
        self.stream_controller = None
        self.api_servers = {}
        
        # 初始化狀態
        self._initialized = False
        self._running = False
        
        # 顯示啟動訊息
        self._show_startup_message()
    
    def _show_startup_message(self):
        """使用 pretty-loguru 顯示啟動訊息"""
        # ASCII 藝術標題 - 使用簡單的日誌訊息替代
        self.logger.info("="*80)
        self.logger.info("    ASR HUB    ")
        self.logger.info("="*80)
        
        # 系統資訊區塊
        system_info = [
            f"應用名稱：{self.app_name}",
            f"版本：{self.version}",
            f"模式：{self.config.system.mode}",
            f"除錯模式：{'啟用' if self.debug else '停用'}",
            "",
            "===== API 配置 =====",
            f"HTTP SSE：{'啟用' if True else '停用'} (Port: {self.api_config.http_sse.port})",
            f"WebSocket：{'啟用' if self.api_config.websocket.enabled else '停用'}",
            f"gRPC：{'啟用' if self.api_config.grpc.enabled else '停用'}",
            f"Socket.IO：{'啟用' if self.api_config.socketio.enabled else '停用'}",
            f"Redis：{'啟用' if self.api_config.redis.enabled else '停用'}",
            "",
            "===== Provider 配置 =====",
            f"預設 Provider：{self.providers_config.default}",
            f"Whisper：{'啟用' if self.providers_config.whisper.enabled else '停用'}",
            f"FunASR：{'啟用' if self.providers_config.funasr.enabled else '停用'}",
            f"Vosk：{'啟用' if self.providers_config.vosk.enabled else '停用'}",
            "",
            "===== 其他功能 =====",
            f"喚醒詞：{'啟用' if hasattr(self.config, 'wake_word_detection') and self.config.wake_word_detection.enabled else '停用'}",
            f"VAD：{'啟用' if self.pipeline_config.operators.vad.enabled else '停用'}",
            f"降噪：{'啟用' if self.pipeline_config.operators.denoise.enabled else '停用'}",
        ]
        
        # 使用 ASCII 標題顯示啟動畫面
        self.logger.ascii_header(
            self.app_name,
            font="slant"
        )
        
        # 使用 info 顯示版本和描述資訊
        self.logger.info(f"📍 版本：v{self.version}")
        self.logger.info(f"📋 描述：Unified Speech Recognition Middleware")
        self.logger.info("=" * 60)
        
        # 使用視覺化區塊顯示系統配置
        api_status = {
            "HTTP SSE": f"{'✓' if True else '✗'} Port {self.api_config.http_sse.port}",
            "WebSocket": '✓' if self.api_config.websocket.enabled else '✗',
            "Socket.IO": '✓' if self.api_config.socketio.enabled else '✗',
            "gRPC": '✓' if self.api_config.grpc.enabled else '✗',
            "Redis": '✓' if self.api_config.redis.enabled else '✗',
        }
        
        self.logger.block("API SERVICES", api_status, border_style="blue")
        
        # 顯示 Provider 狀態
        provider_status = {
            "Default": self.providers_config.default,
            "Whisper": '✓ Enabled' if self.providers_config.whisper.enabled else '✗ Disabled',
            "FunASR": '✓ Enabled' if self.providers_config.funasr.enabled else '✗ Disabled',
            "Vosk": '✓ Enabled' if self.providers_config.vosk.enabled else '✗ Disabled',
        }
        
        self.logger.block("PROVIDERS", provider_status, border_style="green")
        
        # 顯示 Pipeline 功能
        pipeline_features = {
            "Wake Word": '✓' if hasattr(self.config, 'wake_word_detection') and self.config.wake_word_detection.enabled else '✗',
            "VAD": '✓' if self.pipeline_config.operators.vad.enabled else '✗',
            "Denoise": '✓' if self.pipeline_config.operators.denoise.enabled else '✗',
        }
        
        self.logger.block("PIPELINE FEATURES", pipeline_features, border_style="yellow")
        
        # 記錄啟動事件
        self.logger.success(f"{self.app_name} v{self.version} 啟動成功！")
    
    async def initialize(self):
        """
        初始化所有子系統
        """
        if self._initialized:
            self.logger.warning("系統已經初始化，跳過重複初始化")
            return
        
        self.logger.info("開始初始化子系統...")
        
        try:
            # 初始化 Session Manager
            self.logger.debug("初始化 Session Manager...")
            self.session_manager = SessionManager(
                max_sessions=self.config.performance.thread_pool.max_workers * 10,
                session_timeout=int(self.stream_config.silence_timeout * 10)
            )
            
            # 初始化 Pipeline Manager
            self.logger.debug("初始化 Pipeline Manager...")
            self.pipeline_manager = PipelineManager()
            await self.pipeline_manager.initialize()
            
            # 初始化 Provider Manager
            self.logger.debug("初始化 Provider Manager...")
            self.provider_manager = ProviderManager()
            await self.provider_manager.initialize()
            
            # 初始化 Stream Controller
            self.logger.debug("初始化 Stream Controller...")
            self.stream_controller = StreamController(
                self.session_manager,
                self.pipeline_manager,
                self.provider_manager
            )
            
            # 初始化 API Servers
            await self._initialize_api_servers()
            
            self._initialized = True
            self.logger.success("所有子系統初始化完成")
            
        except Exception as e:
            self.logger.error(f"子系統初始化失敗：{e}")
            raise
    
    async def _initialize_api_servers(self):
        """初始化 API 伺服器"""
        # HTTP SSE Server (always enabled)
        if True:  # SSE 總是啟用
            self.logger.debug("初始化 HTTP SSE Server...")
            self.api_servers["http_sse"] = SSEServer(self.session_manager, self.provider_manager, self.pipeline_manager)
        
        # WebSocket Server
        if self.api_config.websocket.enabled:
            self.logger.debug("初始化 WebSocket Server...")
            self.api_servers["websocket"] = WebSocketServer(
                self.session_manager,
                self.pipeline_manager,
                self.provider_manager
            )
        
        # Socket.IO Server
        if self.api_config.socketio.enabled:
            self.logger.debug("初始化 Socket.IO Server...")
            self.api_servers["socketio"] = SocketIOServer(
                self.session_manager,
                self.pipeline_manager,
                self.provider_manager
            )
        
        # TODO: 初始化其他 API servers (gRPC, Redis)
    
    async def start(self):
        """啟動 ASR Hub 服務"""
        try:
            self.logger.info("正在啟動 ASR Hub 服務...")
            
            # 直接調用非同步方法
            await self._async_start()
            
        except KeyboardInterrupt:
            self.logger.info("收到中斷訊號，準備關閉服務...")
            await self.stop()
        except Exception as e:
            self.logger.exception(f"服務啟動失敗：{e}")
            raise
    
    async def _async_start(self):
        """非同步啟動服務"""
        # 確保系統已初始化
        if not self._initialized:
            await self.initialize()
        
        # 啟動各個 API 服務
        for name, server in self.api_servers.items():
            self.logger.debug(f"啟動 {name} server...")
            await server.start()
        
        self._running = True
        self.logger.success("ASR Hub 服務啟動完成")
        
        # 保持服務運行
        await self._run_forever()
    
    async def stop(self):
        """停止 ASR Hub 服務"""
        self.logger.info("正在停止 ASR Hub 服務...")
        self._running = False
        
        # 停止所有 API 服務
        for name, server in self.api_servers.items():
            self.logger.debug(f"停止 {name} server...")
            await server.stop()
        
        # 清理資源
        if self.stream_controller:
            await self.stream_controller.cleanup()
        if self.provider_manager:
            await self.provider_manager.cleanup()
        if self.pipeline_manager:
            await self.pipeline_manager.cleanup()
        
        self.logger.success("ASR Hub 服務已停止")
    
    async def _run_forever(self):
        """保持服務運行"""
        self.logger.info("服務正在運行中...（按 Ctrl+C 停止）")
        try:
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        獲取系統狀態
        
        Returns:
            包含系統各項狀態的字典
        """
        return {
            "system": {
                "name": self.app_name,
                "version": self.version,
                "mode": self.config.system.mode,
                "initialized": self._initialized
            },
            "api": {
                "http_sse": {
                    "enabled": True,
                    "port": self.api_config.http_sse.port,
                    "running": "http_sse" in self.api_servers and self.api_servers["http_sse"].is_running()
                },
                "websocket": {
                    "enabled": self.api_config.websocket.enabled,
                    "port": self.api_config.websocket.port if self.api_config.websocket.enabled else None,
                    "running": "websocket" in self.api_servers and self.api_servers["websocket"].is_running()
                },
                "socketio": {
                    "enabled": self.api_config.socketio.enabled,
                    "port": self.api_config.socketio.port if self.api_config.socketio.enabled else None,
                    "running": "socketio" in self.api_servers and self.api_servers["socketio"].is_running()
                }
            },
            "providers": {
                "default": self.providers_config.default,
                "available": []  # TODO: 列出可用的 providers
            }
        }


def main():
    """命令列入口點"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ASR Hub - 統一的語音辨識中介系統")
    parser.add_argument(
        "-c", "--config",
        type=str,
        help="配置檔案路徑"
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="顯示版本資訊"
    )
    
    args = parser.parse_args()
    
    if args.version:
        config = ConfigManager()
        logger.info(f"{config.system.name} v{config.system.version}")
        sys.exit(0)
    
    # 建立並啟動 ASR Hub
    hub = ASRHub(config_path=args.config)
    
    # 使用 asyncio 運行
    asyncio.run(hub.start())


if __name__ == "__main__":
    main()