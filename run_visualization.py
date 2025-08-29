#!/usr/bin/env python3
"""視覺化啟動腳本

快速啟動音訊視覺化介面。
"""

import sys
import os
import argparse

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.visualization import WaveformVisualizer
from src.utils.logger import logger


def main():
    """主函數。"""
    parser = argparse.ArgumentParser(description='ASR Hub Audio Visualizer')
    parser.add_argument('--port', type=int, default=7860, help='Server port')
    parser.add_argument('--share', action='store_true', help='Create public link')
    parser.add_argument('--sample-rate', type=int, default=16000, help='Sample rate')
    parser.add_argument('--panel', choices=['history', 'vad', 'wakeword', 'spectrum'], 
                       default='history', help='Default lower panel')
    
    args = parser.parse_args()
    
    logger.info("=" * 50)
    logger.info("ASR Hub Audio Visualizer")
    logger.info("=" * 50)
    logger.info(f"Port: {args.port}")
    logger.info(f"Share: {args.share}")
    logger.info(f"Sample Rate: {args.sample_rate}")
    logger.info(f"Default Panel: {args.panel}")
    logger.info("=" * 50)
    
    # 創建視覺化器
    visualizer = WaveformVisualizer(sample_rate=args.sample_rate)
    
    # 設定預設面板
    visualizer.set_lower_panel(args.panel)
    
    # 啟動介面
    try:
        visualizer.launch(
            server_port=args.port,
            share=args.share,
            inbrowser=not args.share  # 如果分享則不自動開啟瀏覽器
        )
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        visualizer.close()


if __name__ == "__main__":
    main()