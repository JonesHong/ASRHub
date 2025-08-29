#!/usr/bin/env python3
"""
錄音服務視覺化測試

使用 matplotlib 繪製即時聲波圖：
- 上半部：即時麥克風聲波圖
- 下半部：歷史聲波圖（隨時間延長）
"""

import sys
import os
import time
import numpy as np
import pyaudio
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import threading
from datetime import datetime

# 設定 matplotlib 使用支援中文的字體和黑底主題
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
plt.style.use('dark_background')

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))

from src.service.recording.recording import recording
from src.core.audio_queue_manager import audio_queue
from src.utils.logger import logger


class RecordingVisualTest:
    """錄音視覺化測試"""
    
    def __init__(self):
        # PyAudio 設定
        self.p = pyaudio.PyAudio()
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024
        self.format = pyaudio.paInt16
        
        # 視覺化設定
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8), facecolor='#1a1a1a')
        self.fig.suptitle('錄音服務視覺化測試', fontsize=14, color='white')
        
        # 上半部：即時麥克風波形
        self.ax1.set_title('即時麥克風輸入', color='white')
        self.ax1.set_ylabel('振幅')
        # 初始設定較小的範圍，會自動調整
        self.ax1.set_ylim(-5000, 5000)
        self.ax1.grid(True, alpha=0.3, color='gray')
        self.ax1.set_facecolor('#2a2a2a')
        
        # 啟用自動縮放
        self.auto_scale = True
        self.y_margin = 1.2  # Y軸邊界的倍數
        
        # 下半部：歷史波形
        self.ax2.set_title('錄音歷史', color='white')
        self.ax2.set_xlabel('時間 (秒)')
        self.ax2.set_ylabel('振幅')
        # 初始設定較小的範圍，會自動調整
        self.ax2.set_ylim(-5000, 5000)
        self.ax2.grid(True, alpha=0.3, color='gray')
        self.ax2.set_facecolor('#2a2a2a')
        
        # 數據緩衝
        self.realtime_buffer = np.zeros(self.chunk_size)
        self.history_buffer = deque(maxlen=self.sample_rate * 30)  # 30秒歷史
        self.time_buffer = deque(maxlen=self.sample_rate * 30)
        
        # 繪圖線條 - 使用填充效果更容易看出波形
        self.line1, = self.ax1.plot([], [], 'cyan', linewidth=0.8, alpha=0.8)
        self.line2, = self.ax2.plot([], [], 'orange', linewidth=0.5, alpha=0.8)
        # 填充效果
        self.fill1 = None
        self.fill2 = None
        
        # 狀態
        self.is_recording = False
        self.stream = None
        self.session_id = None
        self.start_time = None
        
        # 狀態文字
        self.status_text = self.ax1.text(0.02, 0.98, '準備就緒', 
                                         transform=self.ax1.transAxes,
                                         fontsize=10, va='top', color='white',
                                         bbox=dict(boxstyle='round', facecolor='#333333', alpha=0.7))
        
        # 統計資訊文字
        self.stats_text = self.ax2.text(0.02, 0.98, '', 
                                        transform=self.ax2.transAxes,
                                        fontsize=10, va='top', color='white',
                                        bbox=dict(boxstyle='round', facecolor='#333333', alpha=0.7))
    
    def start_recording(self):
        """開始錄音"""
        self.session_id = "test"  # 測試環境固定使用 "test"
        self.start_time = time.time()
        
        logger.info(f"開始錄音測試，Session ID: {self.session_id}")
        
        # 開啟麥克風
        try:
            self.stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            logger.info(f"麥克風已開啟: {self.sample_rate}Hz")
        except Exception as e:
            logger.error(f"無法開啟麥克風: {e}")
            return False
        
        # 開始錄音服務
        success = recording.start_recording(
            session_id=self.session_id,
            metadata={'test': True, 'continuous': True}
        )
        
        if success:
            self.is_recording = True
            logger.info("錄音服務已啟動")
            
            # 啟動音訊處理執行緒
            self.audio_thread = threading.Thread(
                target=self._audio_processing
            )
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            return True
        else:
            logger.error("無法啟動錄音服務")
            if self.stream:
                self.stream.close()
            return False
    
    def _audio_processing(self):
        """音訊處理執行緒"""
        logger.info("音訊處理執行緒已啟動")
        
        while self.is_recording:
            try:
                if not self.stream:
                    break
                
                # 讀取音訊
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 轉換為 numpy array
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                
                # 更新即時緩衝
                self.realtime_buffer = audio_np
                
                # 添加到歷史緩衝
                current_time = time.time() - self.start_time
                for sample in audio_np:
                    self.history_buffer.append(sample)
                    self.time_buffer.append(current_time)
                    current_time += 1.0 / self.sample_rate
                
                # 推送到 audio queue
                audio_queue.push(self.session_id, audio_data)
                
                # 計算音量
                rms = np.sqrt(np.mean(audio_np.astype(float) ** 2))
                volume_db = 20 * np.log10(max(rms, 1)) if rms > 0 else -60
                
                # 更新狀態
                elapsed = time.time() - self.start_time
                self.current_stats = {
                    'elapsed': elapsed,
                    'volume_db': volume_db,
                    'samples': len(self.history_buffer)
                }
                
            except Exception as e:
                logger.error(f"音訊處理錯誤: {e}")
                break
        
        logger.info("音訊處理執行緒結束")
    
    def stop_recording(self):
        """停止錄音"""
        self.is_recording = False
        
        # 關閉麥克風
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        # 停止錄音服務
        if self.session_id:
            info = recording.stop_recording(self.session_id)
            if info:
                logger.info(f"錄音已停止，檔案: {info.get('filepath')}")
                return info
        
        return None
    
    def update_plot(self, frame):
        """更新圖表"""
        if self.is_recording:
            # 更新即時波形
            x1 = np.arange(len(self.realtime_buffer))
            self.line1.set_data(x1, self.realtime_buffer)
            self.ax1.set_xlim(0, len(self.realtime_buffer))
            
            # 自動調整上方圖表的 Y 軸範圍
            if self.auto_scale and len(self.realtime_buffer) > 0:
                max_val = np.max(np.abs(self.realtime_buffer))
                if max_val > 0:
                    y_limit = max_val * self.y_margin
                    current_ylim = self.ax1.get_ylim()
                    if abs(current_ylim[1] - y_limit) > y_limit * 0.2:
                        self.ax1.set_ylim(-y_limit, y_limit)
            
            # 移除舊的填充
            if self.fill1:
                self.fill1.remove()
                self.fill1 = None
            
            # 添加新的填充效果
            if len(self.realtime_buffer) > 0:
                self.fill1 = self.ax1.fill_between(
                    x1, 0, self.realtime_buffer,
                    color='cyan', alpha=0.3
                )
            
            # 更新歷史波形
            if len(self.history_buffer) > 0:
                # 降採樣顯示（避免太多點）
                step = max(1, len(self.history_buffer) // 5000)
                history_array = np.array(self.history_buffer)[::step]
                time_array = np.array(self.time_buffer)[::step]
                
                self.line2.set_data(time_array, history_array)
                self.ax2.set_xlim(0, max(time_array) if len(time_array) > 0 else 1)
                
                # 自動調整下方圖表的 Y 軸範圍
                if self.auto_scale and len(history_array) > 0:
                    max_val = np.max(np.abs(history_array))
                    if max_val > 0:
                        y_limit = max_val * self.y_margin
                        current_ylim = self.ax2.get_ylim()
                        if abs(current_ylim[1] - y_limit) > y_limit * 0.2:
                            self.ax2.set_ylim(-y_limit, y_limit)
                
                # 移除舊的填充
                if self.fill2:
                    self.fill2.remove()
                    self.fill2 = None
                
                # 添加填充效果到歷史波形
                if len(history_array) > 0:
                    self.fill2 = self.ax2.fill_between(
                        time_array, 0, history_array,
                        color='orange', alpha=0.2
                    )
            
            # 更新狀態文字
            if hasattr(self, 'current_stats'):
                elapsed = self.current_stats['elapsed']
                volume = self.current_stats['volume_db']
                samples = self.current_stats['samples']
                
                self.status_text.set_text(f'錄音中... {elapsed:.1f}秒')
                self.stats_text.set_text(
                    f'音量: {volume:.1f} dB | '
                    f'樣本數: {samples:,} | '
                    f'緩衝大小: {audio_queue.size(self.session_id)} chunks'
                )
        else:
            self.status_text.set_text('準備就緒')
        
        return self.line1, self.line2, self.status_text, self.stats_text
    
    def run_test(self):
        """執行測試"""
        logger.info("開始錄音視覺化測試")
        
        # 開始錄音
        if not self.start_recording():
            logger.error("無法開始錄音")
            return False
        
        # 設定動畫
        ani = animation.FuncAnimation(
            self.fig, self.update_plot,
            interval=50,  # 50ms 更新一次
            blit=True,
            cache_frame_data=False
        )
        
        # 顯示圖表
        plt.tight_layout()
        plt.show()
        
        # 停止錄音
        info = self.stop_recording()
        
        # 清理
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join(timeout=1)
        
        return info is not None
    
    def cleanup(self):
        """清理資源"""
        if self.stream:
            self.stream.close()
        if self.p:
            self.p.terminate()
        plt.close('all')


def main():
    """主函數"""
    print("="*60)
    print("🎙️  錄音服務視覺化測試")
    print("="*60)
    
    tester = RecordingVisualTest()
    
    try:
        print("\n開始錄音測試...")
        print("請對著麥克風說話")
        print("📌 關閉視窗即可停止測試\n")
        
        # 執行測試
        success = tester.run_test()
        
        if success:
            print("\n✅ 測試成功完成")
        else:
            print("\n❌ 測試失敗")
    
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n測試錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        tester.cleanup()
        print("\n測試結束")


if __name__ == "__main__":
    main()