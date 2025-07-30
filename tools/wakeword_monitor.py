#!/usr/bin/env python3
"""
喚醒詞監控工具
提供簡單的命令行介面來監控喚醒詞偵測狀態
"""

import asyncio
import os
import sys
import time
from datetime import datetime
import argparse
from typing import Dict, Any, Optional

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.pipeline.operators.wakeword import OpenWakeWordOperator
from src.core.system_listener import SystemListener
from src.core.session_manager import SessionManager
from src.utils.logger import get_logger


class WakeWordMonitor:
    """喚醒詞監控器"""
    
    def __init__(self, show_scores: bool = False, threshold: float = 0.5):
        """
        初始化監控器
        
        Args:
            show_scores: 是否顯示實時分數
            threshold: 偵測閾值
        """
        self.logger = get_logger("wakeword_monitor")
        self.show_scores = show_scores
        self.threshold = threshold
        
        # 組件
        self.wakeword_operator = None
        self.system_listener = None
        self.session_manager = None
        
        # 統計
        self.stats = {
            "start_time": None,
            "total_detections": 0,
            "last_detection": None,
            "highest_score": 0.0,
            "score_samples": 0,
            "avg_score": 0.0
        }
        
        self.is_running = False
    
    async def start(self):
        """啟動監控器"""
        print("🚀 啟動喚醒詞監控器...")
        
        try:
            # 初始化組件
            self.session_manager = SessionManager()
            
            # 初始化喚醒詞偵測器
            self.wakeword_operator = OpenWakeWordOperator()
            # 如果需要覆蓋閾值，可以在初始化後更新
            if self.threshold != 0.5:  # 如果不是預設值
                self.wakeword_operator.update_config({"threshold": self.threshold})
            self.wakeword_operator.set_detection_callback(self._on_detection)
            await self.wakeword_operator.start()
            
            # 初始化系統監聽器
            self.system_listener = SystemListener()
            self.system_listener.register_event_handler("wake_detected", self._on_system_wake)
            self.system_listener.register_event_handler("state_changed", self._on_state_change)
            await self.system_listener.start()
            
            self.stats["start_time"] = datetime.now()
            self.is_running = True
            
            print("✅ 監控器啟動成功")
            print(f"🎯 偵測閾值: {self.threshold}")
            print(f"📊 顯示分數: {'是' if self.show_scores else '否'}")
            print("🎤 請說出喚醒詞：'嗨，高醫' 或 'hi kmu'")
            print("💡 按 Ctrl+C 停止監控\n")
            
            # 開始監控迴圈
            await self._monitoring_loop()
            
        except Exception as e:
            self.logger.error(f"啟動失敗: {e}")
            raise
    
    async def stop(self):
        """停止監控器"""
        print("\n🛑 停止監控器...")
        
        self.is_running = False
        
        try:
            if self.system_listener:
                await self.system_listener.stop()
            
            if self.wakeword_operator:
                await self.wakeword_operator.stop()
            
            print("✅ 監控器已停止")
            
        except Exception as e:
            self.logger.error(f"停止錯誤: {e}")
    
    async def _monitoring_loop(self):
        """監控主迴圈"""
        last_status_time = time.time()
        status_interval = 10  # 每 10 秒顯示一次狀態
        
        try:
            while self.is_running:
                current_time = time.time()
                
                # 定期顯示狀態
                if current_time - last_status_time >= status_interval:
                    self._show_status()
                    last_status_time = current_time
                
                # 如果需要顯示分數，獲取最新分數
                if self.show_scores and self.wakeword_operator:
                    score = self.wakeword_operator.get_latest_score()
                    if score is not None:
                        self._update_score_stats(score)
                        
                        # 只顯示高於一定閾值的分數以減少輸出
                        if score > 0.1:
                            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                            print(f"[{timestamp}] 分數: {score:.3f}", end='\r')
                
                # 短暫休眠
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n用戶中斷監控")
        except Exception as e:
            self.logger.error(f"監控迴圈錯誤: {e}")
    
    def _show_status(self):
        """顯示監控狀態"""
        if not self.stats["start_time"]:
            return
        
        runtime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        print(f"\n📊 監控狀態 ({datetime.now().strftime('%H:%M:%S')})")
        print(f"⏱️  運行時間: {runtime:.1f} 秒")
        print(f"🎯 總偵測次數: {self.stats['total_detections']}")
        print(f"📈 最高分數: {self.stats['highest_score']:.3f}")
        print(f"📊 平均分數: {self.stats['avg_score']:.3f}")
        
        if self.stats["last_detection"]:
            last_detection_ago = (datetime.now() - self.stats["last_detection"]).total_seconds()
            print(f"🕒 上次偵測: {last_detection_ago:.1f} 秒前")
        else:
            print("🕒 上次偵測: 無")
        
        print("-" * 50)
    
    def _update_score_stats(self, score: float):
        """更新分數統計"""
        self.stats["score_samples"] += 1
        
        if score > self.stats["highest_score"]:
            self.stats["highest_score"] = score
        
        # 計算移動平均
        alpha = 0.01  # 平滑因子
        if self.stats["avg_score"] == 0:
            self.stats["avg_score"] = score
        else:
            self.stats["avg_score"] = alpha * score + (1 - alpha) * self.stats["avg_score"]
    
    async def _on_detection(self, detection: Dict[str, Any]):
        """喚醒詞偵測回呼"""
        self.stats["total_detections"] += 1
        self.stats["last_detection"] = datetime.now()
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        model = detection.get("model", "unknown")
        score = detection.get("score", 0)
        
        print(f"\n🎯 [{timestamp}] 偵測到喚醒詞！")
        print(f"   模型: {model}")
        print(f"   分數: {score:.3f}")
        print(f"   閾值: {self.threshold}")
        print("   " + "="*30)
    
    def _on_system_wake(self, wake_data: Dict[str, Any]):
        """系統喚醒事件回呼"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        source = wake_data.get("source", "unknown")
        
        print(f"\n🔔 [{timestamp}] 系統喚醒事件")
        print(f"   來源: {source}")
        print("   " + "="*30)
    
    def _on_state_change(self, state_data: Dict[str, Any]):
        """狀態變更事件回呼"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        old_state = state_data.get("old_state", "unknown")
        new_state = state_data.get("new_state", "unknown")
        
        print(f"\n🔄 [{timestamp}] 狀態變更")
        print(f"   {old_state} -> {new_state}")
        print("   " + "="*30)
    
    def print_final_stats(self):
        """打印最終統計"""
        if not self.stats["start_time"]:
            return
        
        runtime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        print("\n" + "="*50)
        print("📈 最終統計報告")
        print("="*50)
        print(f"⏱️  總運行時間: {runtime:.1f} 秒")
        print(f"🎯 總偵測次數: {self.stats['total_detections']}")
        print(f"📊 偵測頻率: {self.stats['total_detections'] / max(runtime, 1):.2f} 次/秒")
        print(f"📈 最高分數: {self.stats['highest_score']:.3f}")
        print(f"📊 平均分數: {self.stats['avg_score']:.3f}")
        print(f"🔢 分數樣本數: {self.stats['score_samples']}")
        
        if self.stats["last_detection"]:
            print(f"🕒 最後偵測時間: {self.stats['last_detection'].strftime('%H:%M:%S')}")
        
        print("="*50)


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description="喚醒詞監控工具")
    parser.add_argument(
        "--show-scores", 
        action="store_true", 
        help="顯示實時偵測分數"
    )
    parser.add_argument(
        "--threshold", 
        type=float, 
        default=0.5, 
        help="偵測閾值 (預設: 0.5)"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="詳細輸出"
    )
    
    args = parser.parse_args()
    
    print("🎤 ASR Hub 喚醒詞監控工具")
    print("="*40)
    
    # 檢查環境
    if not os.environ.get("HF_TOKEN"):
        print("⚠️  警告: 未設定 HF_TOKEN 環境變數")
        print("如果需要下載模型，請設定: export HF_TOKEN=your_token")
        print()
    
    monitor = WakeWordMonitor(
        show_scores=args.show_scores,
        threshold=args.threshold
    )
    
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n❌ 監控錯誤: {e}")
    finally:
        asyncio.run(monitor.stop())
        monitor.print_final_stats()


if __name__ == "__main__":
    main()