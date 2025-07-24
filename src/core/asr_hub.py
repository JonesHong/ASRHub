"""
ASR Hub 主要入口類別
協調各模組運作的核心系統
"""

import sys
from typing import Optional, Dict, Any
from src.config.manager import ConfigManager
from src.utils.logger import get_logger


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
        self.logger = get_logger("core")
        
        # 系統資訊
        self.app_name = self.config.system.name
        self.version = self.config.system.version
        self.debug = self.config.system.debug
        
        # 其他配置
        self.api_config = self.config.api
        self.pipeline_config = self.config.pipeline
        self.providers_config = self.config.providers
        self.stream_config = self.config.stream
        
        # 初始化狀態
        self._initialized = False
        
        # 顯示啟動訊息
        self._show_startup_message()
    
    def _show_startup_message(self):
        """使用 pretty-loguru 顯示啟動訊息"""
        # ASCII 藝術標題
        self.logger.ascii_header("ASR HUB", font="slant", width=80)
        
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
            f"喚醒詞：{'啟用' if self.config.wakeword.enabled else '停用'}",
            f"VAD：{'啟用' if self.pipeline_config.operators.vad.enabled else '停用'}",
            f"降噪：{'啟用' if self.pipeline_config.operators.denoise.enabled else '停用'}",
        ]
        
        self.logger.block("系統初始化", system_info, border_style="blue")
        
        # 記錄啟動事件
        self.logger.success(f"{self.app_name} v{self.version} 啟動成功！")
    
    def initialize(self):
        """
        初始化所有子系統
        這個方法將在未來實作各模組的初始化邏輯
        """
        if self._initialized:
            self.logger.warning("系統已經初始化，跳過重複初始化")
            return
        
        self.logger.info("開始初始化子系統...")
        
        # TODO: 初始化 API servers
        # TODO: 初始化 Pipeline manager
        # TODO: 初始化 Provider manager
        # TODO: 初始化 Session manager
        # TODO: 初始化 Stream controller
        
        self._initialized = True
        self.logger.success("所有子系統初始化完成")
    
    def start(self):
        """啟動 ASR Hub 服務"""
        try:
            self.logger.info("正在啟動 ASR Hub 服務...")
            
            # 確保系統已初始化
            if not self._initialized:
                self.initialize()
            
            # TODO: 啟動各個服務
            
            self.logger.success("ASR Hub 服務啟動完成")
            
            # 保持服務運行
            self._run_forever()
            
        except KeyboardInterrupt:
            self.logger.info("收到中斷訊號，準備關閉服務...")
            self.stop()
        except Exception as e:
            self.logger.exception(f"服務啟動失敗：{e}")
            sys.exit(1)
    
    def stop(self):
        """停止 ASR Hub 服務"""
        self.logger.info("正在停止 ASR Hub 服務...")
        
        # TODO: 停止各個服務
        # TODO: 清理資源
        
        self.logger.success("ASR Hub 服務已停止")
    
    def _run_forever(self):
        """保持服務運行"""
        import time
        self.logger.info("服務正在運行中...（按 Ctrl+C 停止）")
        try:
            while True:
                time.sleep(1)
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
                    "port": self.api_config.http_sse.port
                }
                # TODO: 添加其他 API 狀態
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
        print(f"{config.system.name} v{config.system.version}")
        sys.exit(0)
    
    # 建立並啟動 ASR Hub
    hub = ASRHub(config_path=args.config)
    hub.start()


if __name__ == "__main__":
    main()