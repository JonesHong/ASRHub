#!/usr/bin/env python3
"""
ASR Hub 喚醒詞整合測試工具
測試 OpenWakeWordOperator 與 SystemListener 的整合功能
"""

import asyncio
import os
import sys
import numpy as np
import pyaudio
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import queue
import threading
from typing import Dict, Any, Optional
import time

# 添加 src 到路徑以便導入模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.pipeline.operators.wakeword import OpenWakeWordOperator
from src.core.system_listener import SystemListener
from src.core.session_manager import SessionManager
from src.utils.logger import get_logger
from src.config.manager import ConfigManager

# 設定中文字體
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class WakeWordIntegrationTester:
    """喚醒詞整合測試器"""
    
    def __init__(self):
        """初始化測試器"""
        self.logger = get_logger("wakeword_tester")
        
        # 音訊參數
        self.chunk_size = 1280
        self.sample_rate = 16000
        self.channels = 1
        self.format = pyaudio.paInt16
        
        # 測試組件
        self.wakeword_operator = None
        self.system_listener = None
        self.session_manager = None
        
        # 音訊處理
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_running = False
        
        # 資料儲存
        self.audio_queue = queue.Queue()
        self.detection_events = []
        self.score_history = []
        self.timestamps = []
        
        # 統計資訊
        self.stats = {
            "total_detections": 0,
            "false_positives": 0,
            "missed_detections": 0,
            "avg_score": 0.0,
            "max_score": 0.0,
            "min_score": 1.0,
            "start_time": None
        }
    
    async def setup(self):
        """設定測試環境"""
        self.logger.info("設定喚醒詞整合測試環境...")
        
        try:
            # 初始化 Session Manager
            self.session_manager = SessionManager()
            
            # 初始化 OpenWakeWord Operator
            self.wakeword_operator = OpenWakeWordOperator()
            self.wakeword_operator.set_detection_callback(self._on_detection)
            await self.wakeword_operator.start()
            
            # 初始化 System Listener
            self.system_listener = SystemListener()
            self.system_listener.register_event_handler("wake_detected", self._on_system_wake)
            self.system_listener.register_event_handler("state_changed", self._on_state_change)
            await self.system_listener.start()
            
            self.logger.info("✓ 測試環境設定完成")
            
        except Exception as e:
            self.logger.error(f"設定失敗: {e}")
            raise
    
    async def cleanup(self):
        """清理測試環境"""
        self.logger.info("清理測試環境...")
        
        try:
            if self.system_listener:
                await self.system_listener.stop()
            
            if self.wakeword_operator:
                await self.wakeword_operator.stop()
            
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            
            self.p.terminate()
            
            self.logger.info("✓ 測試環境清理完成")
            
        except Exception as e:
            self.logger.error(f"清理錯誤: {e}")
    
    def start_audio_capture(self):
        """開始音訊捕獲"""
        try:
            # 嘗試不同的採樣率
            for test_rate in [16000, 44100, 48000]:
                try:
                    self.stream = self.p.open(
                        format=self.format,
                        channels=self.channels,
                        rate=test_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size,
                    )
                    self.sample_rate = test_rate
                    self.logger.info(f"使用採樣率: {test_rate} Hz")
                    break
                except Exception as e:
                    self.logger.warning(f"無法使用採樣率 {test_rate}: {e}")
                    continue
            
            if not self.stream:
                raise Exception("無法開啟音訊流")
            
            self.is_running = True
            self.stats["start_time"] = datetime.now()
            
            # 啟動音訊處理線程
            audio_thread = threading.Thread(target=self._audio_processing_loop)
            audio_thread.daemon = True
            audio_thread.start()
            
            self.logger.info("✓ 音訊捕獲已啟動")
            
        except Exception as e:
            self.logger.error(f"音訊捕獲啟動失敗: {e}")
            raise
    
    def _audio_processing_loop(self):
        """音訊處理主迴圈"""
        self.logger.info("開始音訊處理迴圈...")
        
        # 為這個線程創建新的事件循環
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.is_running:
            try:
                # 讀取音訊資料
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 轉換為 numpy array
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                
                # 同步處理音訊（喚醒詞偵測）
                # 在線程中運行 async 函數
                result = loop.run_until_complete(
                    self.wakeword_operator.process(
                        audio_data,
                        sample_rate=self.sample_rate,
                        session_id="test_session"
                    )
                )
                
                # 獲取最新分數
                latest_score = self.wakeword_operator.get_latest_score()
                if latest_score is not None:
                    current_time = time.time()
                    self.score_history.append(latest_score)
                    self.timestamps.append(current_time)
                    
                    # 更新統計
                    if latest_score > self.stats["max_score"]:
                        self.stats["max_score"] = latest_score
                    if latest_score < self.stats["min_score"]:
                        self.stats["min_score"] = latest_score
                    
                    # 計算平均分數
                    if self.score_history:
                        self.stats["avg_score"] = sum(self.score_history) / len(self.score_history)
                    
                    # 將資料放入佇列供視覺化使用
                    self.audio_queue.put({
                        "audio": audio_np,
                        "score": latest_score,
                        "timestamp": current_time
                    })
                
            except Exception as e:
                self.logger.error(f"音訊處理錯誤: {e}")
                time.sleep(0.01)  # 短暫休眠避免 CPU 100%
        
        # 關閉循環
        loop.close()
    
    async def _on_detection(self, detection: Dict[str, Any]):
        """喚醒詞偵測回呼"""
        self.stats["total_detections"] += 1
        self.detection_events.append({
            "timestamp": datetime.now(),
            "detection": detection,
            "source": "operator"
        })
        
        self.logger.info(
            f"🎯 Operator 偵測到喚醒詞！"
            f"模型: {detection.get('model')}, "
            f"分數: {detection.get('score', 0):.3f}"
        )
    
    def _on_system_wake(self, wake_data: Dict[str, Any]):
        """系統喚醒事件回呼"""
        self.detection_events.append({
            "timestamp": datetime.now(),
            "detection": wake_data,
            "source": "system"
        })
        
        self.logger.info(
            f"🔔 SystemListener 偵測到喚醒！"
            f"來源: {wake_data.get('source')}"
        )
    
    def _on_state_change(self, state_data: Dict[str, Any]):
        """狀態變更事件回呼"""
        self.logger.info(
            f"🔄 系統狀態變更: "
            f"{state_data.get('old_state')} -> {state_data.get('new_state')}"
        )
    
    def start_visualization(self):
        """啟動視覺化監控"""
        self.logger.info("啟動視覺化監控...")
        
        # 設定圖表
        plt.style.use("dark_background")
        self.fig, (self.ax1, self.ax2, self.ax3) = plt.subplots(3, 1, figsize=(12, 10))
        
        # 分數圖
        self.ax1.set_xlabel("時間 (秒)")
        self.ax1.set_ylabel("偵測分數")
        self.ax1.set_title("喚醒詞偵測分數")
        self.ax1.grid(True, alpha=0.3)
        self.score_line, = self.ax1.plot([], [], "g-", linewidth=2, label="分數")
        self.ax1.axhline(y=0.5, color="r", linestyle="--", label="閾值")
        self.ax1.legend()
        self.ax1.set_ylim(0, 1.0)
        
        # 音訊波形圖
        self.ax2.set_xlabel("樣本")
        self.ax2.set_ylabel("振幅")
        self.ax2.set_title("音訊波形 (最近 1 秒)")
        self.ax2.grid(True, alpha=0.3)
        self.audio_line, = self.ax2.plot([], [], "b-", alpha=0.7)
        self.ax2.set_ylim(-1000, 1000)
        
        # 統計圖表
        self.ax3.set_title("偵測統計")
        self.ax3.axis('off')
        
        plt.tight_layout()
        
        # 啟動動畫
        ani = FuncAnimation(self.fig, self._update_plot, interval=100, blit=False)
        
        try:
            plt.show()
        except KeyboardInterrupt:
            self.logger.info("視覺化被用戶中斷")
        finally:
            self.is_running = False
    
    def _update_plot(self, frame):
        """更新圖表"""
        current_time = time.time()
        
        # 處理音訊佇列
        latest_audio = None
        while not self.audio_queue.empty():
            try:
                latest_audio = self.audio_queue.get_nowait()
            except queue.Empty:
                break
        
        # 更新分數圖
        if self.timestamps and self.score_history:
            # 只顯示最近 30 秒的資料
            cutoff_time = current_time - 30
            recent_indices = [i for i, t in enumerate(self.timestamps) if t >= cutoff_time]
            
            if recent_indices:
                recent_times = [self.timestamps[i] - self.timestamps[recent_indices[0]] for i in recent_indices]
                recent_scores = [self.score_history[i] for i in recent_indices]
                
                self.score_line.set_data(recent_times, recent_scores)
                self.ax1.set_xlim(0, max(30, recent_times[-1]) if recent_times else 30)
        
        # 更新音訊波形圖
        if latest_audio:
            audio_data = latest_audio["audio"]
            self.audio_line.set_data(range(len(audio_data)), audio_data)
            self.ax2.set_xlim(0, len(audio_data))
        
        # 更新統計資訊
        runtime = (datetime.now() - self.stats["start_time"]).total_seconds() if self.stats["start_time"] else 0
        
        stats_text = f"""
        運行時間: {runtime:.1f} 秒
        總偵測次數: {self.stats['total_detections']}
        平均分數: {self.stats['avg_score']:.3f}
        最高分數: {self.stats['max_score']:.3f}
        最低分數: {self.stats['min_score']:.3f}
        偵測事件: {len(self.detection_events)}
        """
        
        self.ax3.clear()
        self.ax3.text(0.1, 0.5, stats_text, fontsize=12, verticalalignment='center')
        self.ax3.axis('off')
        
        return self.score_line, self.audio_line
    
    def print_test_results(self):
        """打印測試結果"""
        print("\n" + "="*60)
        print("📊 喚醒詞整合測試結果")
        print("="*60)
        
        runtime = (datetime.now() - self.stats["start_time"]).total_seconds() if self.stats["start_time"] else 0
        
        print(f"🕒 運行時間: {runtime:.1f} 秒")
        print(f"🎯 總偵測次數: {self.stats['total_detections']}")
        print(f"📈 平均分數: {self.stats['avg_score']:.3f}")
        print(f"📊 最高分數: {self.stats['max_score']:.3f}")
        print(f"📉 最低分數: {self.stats['min_score']:.3f}")
        print(f"📋 偵測事件數: {len(self.detection_events)}")
        
        if self.detection_events:
            print(f"\n🔍 最近 5 個偵測事件:")
            for event in self.detection_events[-5:]:
                timestamp = event["timestamp"].strftime("%H:%M:%S.%f")[:-3]
                source = event["source"]
                detection = event["detection"]
                score = detection.get("score", "N/A")
                print(f"  [{timestamp}] {source}: {score}")
        
        print("="*60)


async def main():
    """主函數"""
    print("🚀 ASR Hub 喚醒詞整合測試工具")
    print("請確保已安裝 openwakeword 和相關依賴")
    print("請說出喚醒詞：'嗨，高醫' 或 'hi kmu'")
    print("按 Ctrl+C 結束測試\n")
    
    tester = WakeWordIntegrationTester()
    
    try:
        # 設定測試環境
        await tester.setup()
        
        # 開始音訊捕獲
        tester.start_audio_capture()
        
        # 啟動視覺化（這會阻塞直到窗口關閉）
        tester.start_visualization()
        
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n測試錯誤: {e}")
    finally:
        # 清理資源
        await tester.cleanup()
        
        # 打印結果
        tester.print_test_results()


if __name__ == "__main__":
    # 檢查必要的環境變數
    if not os.environ.get("HF_TOKEN"):
        print("⚠️  警告: 未設定 HF_TOKEN 環境變數")
        print("如果需要下載 HuggingFace 模型，請設定此變數")
        print("export HF_TOKEN=your_token_here\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程式被用戶中斷")
    except Exception as e:
        print(f"\n程式錯誤: {e}")
        sys.exit(1)