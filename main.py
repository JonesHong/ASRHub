#!/usr/bin/env python3
"""
ASR Hub 主程式入口
"""

import asyncio
import sys
from pathlib import Path
import warnings

# 忽略 ctranslate2 的 pkg_resources 棄用警告
# 這是一個已知的上游問題，將在 ctranslate2 未來版本中修復
warnings.filterwarnings('ignore', 
                       message='.*pkg_resources is deprecated as an API.*',
                       category=DeprecationWarning)
from src.core.asr_hub import ASRHub
from src.utils.logger import logger, setup_global_exception_handler

# 設定專案根目錄
PROJECT_ROOT = Path(__file__).parent
sys.path.append(str(PROJECT_ROOT))


async def main():
    """主程式入口"""
    # 設定全域異常處理器
    setup_global_exception_handler()
    # logger 已經在頂部導入
    
    try:
        logger.info("=" * 50)
        logger.info("ASR Hub 啟動中...")
        logger.info("=" * 50)
        
        # 配置檔路徑
        config_path = PROJECT_ROOT / "config" / "config.yaml"
        
        # 建立 ASR Hub 實例
        asr_hub = ASRHub(config_path=str(config_path))
        
        # 啟動服務
        await asr_hub.start()
        
        logger.success("ASR Hub 啟動完成！")
        logger.info("HTTP SSE Server 運行在 http://localhost:8080")
        logger.info("按 Ctrl+C 停止服務")
        
        # 保持運行
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("\n收到停止信號...")
        
        # 停止服務
        await asr_hub.stop()
        logger.success("ASR Hub 已安全停止")
        
    except Exception as e:
        logger.error(f"啟動失敗：{e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服務已停止")
    except Exception as e:
        print(f"錯誤：{e}")
        sys.exit(1)