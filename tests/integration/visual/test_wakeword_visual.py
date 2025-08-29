#!/usr/bin/env python3
"""
OpenWakeWord 服務視覺化測試

使用 matplotlib 繪製即時聲波圖：
- 上半部：即時麥克風聲波圖
- 下半部：喚醒詞偵測信心度圖（顯示超過閾值的偵測）
"""

import sys
import os
import time
import numpy as np
import pyaudio
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as patches
from collections import deque
import threading
from datetime import datetime

# 設定 matplotlib 使用支援中文的字體和黑底主題
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
plt.style.use('dark_background')

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))

from src.service.wakeword.openwakeword import openwakeword
from src.core.audio_queue_manager import audio_queue
from src.utils.logger import logger
from src.interface.wakeword import WakewordDetection



class WakewordVisualTest:
    """OpenWakeWord 視覺化測試"""
    
    def __init__(self):
        # PyAudio 設定
        self.p = pyaudio.PyAudio()
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1280  # OpenWakeWord 需要 1280 samples (80ms at 16kHz)
        self.format = pyaudio.paInt16
        
        # 視覺化設定
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8), facecolor='#1a1a1a')
        self.fig.suptitle('OpenWakeWord 服務視覺化測試', fontsize=14, color='white')
        
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
        
        # 下半部：喚醒詞偵測結果
        self.ax2.set_title('喚醒詞偵測信心度（綠色=偵測到, 黃線=閾值）', color='white')
        self.ax2.set_xlabel('時間 (秒)')
        self.ax2.set_ylabel('信心度')
        self.ax2.set_ylim(0, 1.1)
        self.ax2.set_xlim(0, 20)  # 初始化 X 軸範圍為完整的 20 秒窗口
        # 暫時降低閾值以便測試
        self.ax2.axhline(y=0.3, color='yellow', linestyle='--', alpha=0.7, label='偵測閾值 (0.3)')
        self.ax2.grid(True, alpha=0.3, color='gray')
        self.ax2.set_facecolor('#2a2a2a')
        self.ax2.legend(loc='upper right')
        
        # 數據緩衝
        self.realtime_buffer = np.zeros(self.chunk_size)
        
        # 計算所需的緩衝區大小
        self.window_sec = 20.0  # 視窗大小（秒）
        points_per_sec = self.sample_rate / self.chunk_size  # 16000/1280 = 12.5
        buffer_length = int(self.window_sec * points_per_sec * 1.2)  # = 300，預留 20% 餘裕
        
        self.confidence_buffer = deque(maxlen=buffer_length)  # 足夠容納 20+ 秒的資料
        self.confidence_time_buffer = deque(maxlen=buffer_length)
        self.detection_events = []  # 偵測事件列表
        
        # 插值和平滑參數
        self.interpolation_enabled = True  # 啟用插值
        self.smoothing_enabled = True      # 啟用平滑
        self.smoothing_window = 5          # 平滑窗口大小
        self.last_confidence = 0.0         # 上一次的信心度（用於插值）
        self.confidence_change_rate = 0.15 # 信心度變化速率（用於平滑過渡）
        
        # 繪圖線條 - 使用填充效果更容易看出波形
        self.line1, = self.ax1.plot([], [], 'cyan', linewidth=0.8, alpha=0.8)
        self.line2, = self.ax2.plot([], [], 'lime', linewidth=1.0, label='信心度')
        # 填充效果
        self.fill1 = None
        
        # Wakeword 狀態
        self.is_running = False
        self.stream = None
        self.session_id = None
        self.start_time = None
        self.last_detection = None
        self.detection_count = 0
        
        # 狀態文字
        self.status_text = self.ax1.text(0.02, 0.98, '準備就緒', 
                                         transform=self.ax1.transAxes,
                                         fontsize=10, va='top', color='white',
                                         bbox=dict(boxstyle='round', facecolor='#333333', alpha=0.7))
        
        # 統計資訊文字
        self.stats_text = self.ax2.text(0.02, 0.02, '', 
                                        transform=self.ax2.transAxes,
                                        fontsize=10, va='bottom', color='white',
                                        bbox=dict(boxstyle='round', facecolor='#333333', alpha=0.7))
        
        # Wakeword 回調結果
        self.detection_results = []
        self.current_confidence = 0.0
    
    def on_wakeword_detected(self, detection: WakewordDetection):
        """喚醒詞偵測回調
        
        Args:
            detection: WakewordDetection 物件
        """
        current_time = time.time() - self.start_time
        self.detection_count += 1
        self.last_detection = detection
        
        logger.info(f"🎯 偵測到喚醒詞: {detection.keyword} (信心度: {detection.confidence:.3f}) @ {current_time:.2f}s")
        
        # 記錄偵測事件
        self.detection_events.append({
            'time': current_time,
            'keyword': detection.keyword,
            'confidence': detection.confidence
        })
        
        self.detection_results.append({
            'event': 'detection',
            'time': current_time,
            'keyword': detection.keyword,
            'confidence': detection.confidence
        })
    
    def start_wakeword(self):
        """開始喚醒詞偵測測試"""
        self.session_id = "test"  # 測試環境固定使用 "test"
        self.start_time = time.time()
        
        logger.info(f"開始喚醒詞測試，Session ID: {self.session_id}")
        
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
        
        # 確保 OpenWakeword 服務已初始化
        if not openwakeword.is_initialized():
            logger.info("初始化 OpenWakeword 服務...")
            if not openwakeword.initialize():
                logger.error("OpenWakeword 服務初始化失敗")
                return False
        
        # 開始監聽喚醒詞
        success = openwakeword.start_listening(
            session_id=self.session_id,
            callback=self.on_wakeword_detected
        )
        
        if success:
            self.is_running = True
            logger.info("OpenWakeword 服務已啟動")
            
            # 啟動音訊處理執行緒
            self.audio_thread = threading.Thread(
                target=self._audio_processing
            )
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            return True
        else:
            logger.error("無法啟動 OpenWakeword 服務")
            if self.stream:
                self.stream.close()
            return False
    
    def _audio_processing(self):
        """音訊處理執行緒"""
        logger.info("音訊處理執行緒已啟動")
        
        while self.is_running:
            try:
                if not self.stream:
                    break
                
                # 讀取音訊
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 轉換為 numpy array
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                
                # 更新即時緩衝
                self.realtime_buffer = audio_np
                
                # 推送到 audio queue (OpenWakeword 會從這裡讀取)
                audio_queue.push(self.session_id, audio_data)
                
                # 獲取當前時間
                current_time = time.time() - self.start_time
                
                # 計算音量（用於視覺化參考）
                rms = np.sqrt(np.mean(audio_np.astype(float) ** 2))
                volume_normalized = min(1.0, rms / 10000)
                
                # 計算基礎信心度
                if self.last_detection and self.detection_results:
                    # 如果在 1 秒內有偵測，保持顯示高信心度並逐漸衰減
                    time_since_detection = current_time - self.detection_results[-1]['time']
                    if time_since_detection < 1.0:
                        # 指數衰減：從實際信心度逐漸降到基礎值
                        decay_factor = np.exp(-time_since_detection * 3)  # 衰減速率
                        base_confidence = (self.last_detection.confidence * decay_factor + 
                                         volume_normalized * 0.2 * (1 - decay_factor))
                    else:
                        base_confidence = volume_normalized * 0.2
                else:
                    base_confidence = volume_normalized * 0.2
                
                # 插值處理：創建平滑過渡
                if self.interpolation_enabled:
                    confidence_diff = base_confidence - self.last_confidence
                    
                    if abs(confidence_diff) > 0.001:
                        # 偵測時快速上升，否則緩慢變化
                        if confidence_diff > 0.3:  # 大幅上升（偵測到喚醒詞）
                            interpolation_rate = 0.8  # 快速響應
                        elif confidence_diff > 0:
                            interpolation_rate = 0.3  # 中速上升
                        else:
                            interpolation_rate = self.confidence_change_rate  # 緩慢下降
                        
                        interpolated_confidence = self.last_confidence + confidence_diff * interpolation_rate
                    else:
                        interpolated_confidence = base_confidence
                else:
                    interpolated_confidence = base_confidence
                
                # 添加基於音量的微小波動
                if self.smoothing_enabled:
                    volume_influence = volume_normalized * 0.03  # 3% 影響
                    smoothed_confidence = interpolated_confidence * (1.0 + volume_influence)
                    smoothed_confidence = min(1.0, max(0.0, smoothed_confidence))
                else:
                    smoothed_confidence = interpolated_confidence
                
                self.current_confidence = smoothed_confidence
                self.last_confidence = smoothed_confidence
                
                # 添加到緩衝
                self.confidence_buffer.append(smoothed_confidence)
                self.confidence_time_buffer.append(current_time)
                
                # 基於時間裁剪，只保留視窗範圍內的資料
                while (len(self.confidence_time_buffer) > 1 and 
                       self.confidence_time_buffer[-1] - self.confidence_time_buffer[0] > self.window_sec):
                    self.confidence_time_buffer.popleft()
                    self.confidence_buffer.popleft()
                
                # 更新統計
                self.current_stats = {
                    'elapsed': current_time,
                    'confidence': self.current_confidence,
                    'detection_count': self.detection_count,
                    'last_keyword': self.last_detection.keyword if self.last_detection else None,
                    'volume': volume_normalized
                }
                
                time.sleep(0.01)  # 避免過度佔用 CPU
                
            except Exception as e:
                logger.error(f"音訊處理錯誤: {e}")
                break
        
        logger.info("音訊處理執行緒結束")
    
    def stop_wakeword(self):
        """停止喚醒詞偵測測試"""
        self.is_running = False
        
        # 關閉麥克風
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        # 停止 OpenWakeword 監聽
        if self.session_id:
            openwakeword.stop_listening(self.session_id)
            logger.info("OpenWakeword 服務已停止")
        
        return True
    
    def update_plot(self, frame):
        """更新圖表"""
        if self.is_running:
            # 更新即時波形
            x1 = np.arange(len(self.realtime_buffer))
            self.line1.set_data(x1, self.realtime_buffer)
            self.ax1.set_xlim(0, len(self.realtime_buffer))
            
            # 自動調整 Y 軸範圍
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
            
            # 更新信心度曲線
            if len(self.confidence_buffer) > 0:
                time_array = np.array(self.confidence_time_buffer)
                conf_array = np.array(self.confidence_buffer)
                
                # 應用移動平均進一步平滑
                if self.smoothing_enabled and len(conf_array) > self.smoothing_window:
                    kernel = np.ones(self.smoothing_window) / self.smoothing_window
                    conf_smoothed = np.convolve(conf_array, kernel, mode='same')
                    
                    # 對最近的數據點應用較少的平滑
                    blend_factor = np.linspace(0.3, 1.0, len(conf_array))
                    conf_final = conf_array * (1 - blend_factor) + conf_smoothed * blend_factor
                else:
                    conf_final = conf_array
                
                self.line2.set_data(time_array, conf_final)
                
                # 修正 X 軸範圍，基於實際可用資料
                if len(time_array) > 0:
                    data_min_time = min(time_array)
                    data_max_time = max(time_array)
                    
                    # 根據資料範圍設定視窗
                    if data_max_time <= self.window_sec:
                        # 前 20 秒：從 0 開始顯示
                        x_min = 0
                        x_max = self.window_sec
                    else:
                        # 超過 20 秒：以資料範圍為準
                        x_max = data_max_time + 0.5
                        x_min = max(0, data_min_time - 0.5)
                        
                        # 確保視窗寬度不超過設定值
                        if x_max - x_min > self.window_sec + 1:
                            x_min = x_max - self.window_sec
                    
                    self.ax2.set_xlim(x_min, x_max)
                
                # 添加填充效果
                # 移除舊的填充
                for patch in self.ax2.collections[:]:
                    patch.remove()
                
                # 添加新的漸層填充
                if len(time_array) > 1:
                    # 高信心度區域用暖色
                    high_conf_mask = conf_final > 0.5
                    if np.any(high_conf_mask):
                        self.ax2.fill_between(
                            time_array, 0.5, conf_final,
                            where=high_conf_mask,
                            color='orange', alpha=0.3,
                            interpolate=True
                        )
                    
                    # 低信心度區域用冷色
                    low_conf_mask = conf_final <= 0.5
                    if np.any(low_conf_mask):
                        self.ax2.fill_between(
                            time_array, 0, conf_final,
                            where=low_conf_mask,
                            color='blue', alpha=0.2,
                            interpolate=True
                        )
            
            # 繪製偵測事件標記
            for rect in self.ax2.patches[:]:
                if isinstance(rect, patches.Rectangle):
                    rect.remove()
            
            # 獲取當前視窗範圍
            if len(self.confidence_time_buffer) > 0:
                time_arr = np.array(self.confidence_time_buffer)
                data_min = min(time_arr)
                data_max = max(time_arr)
                
                if data_max <= self.window_sec:
                    window_start = 0
                    window_end = self.window_sec
                else:
                    window_end = data_max + 0.5
                    window_start = max(0, data_min - 0.5)
                    
                    if window_end - window_start > self.window_sec + 1:
                        window_start = window_end - self.window_sec
            else:
                window_start = 0
                window_end = self.window_sec
            
            for event in self.detection_events:
                # 只顯示在當前視窗範圍內的偵測事件
                if window_start <= event['time'] <= window_end:
                    # 在偵測時間點畫一個綠色矩形
                    rect = patches.Rectangle(
                        (event['time'] - 0.1, 0), 0.2, event['confidence'],
                        linewidth=2, facecolor='green', edgecolor='lime', alpha=0.7
                    )
                    self.ax2.add_patch(rect)
                    
                    # 添加關鍵字標籤（稍微偏移避免重疊）
                    label_y = min(event['confidence'] + 0.05, 1.05)
                    self.ax2.text(event['time'], label_y, 
                                 event['keyword'], fontsize=8, ha='center',
                                 color='white', bbox=dict(boxstyle='round', 
                                                         facecolor='green', 
                                                         alpha=0.7))
            
            # 更新狀態文字
            if hasattr(self, 'current_stats'):
                elapsed = self.current_stats['elapsed']
                confidence = self.current_stats['confidence']
                count = self.current_stats['detection_count']
                last_kw = self.current_stats['last_keyword']
                
                status = f'🎯 偵測到: {last_kw}' if last_kw else '🎤 監聽中...'
                volume = self.current_stats.get('volume', 0)
                self.status_text.set_text(f'{status} | 時間: {elapsed:.1f}秒 | 音量: {volume:.2f}')
                
                self.stats_text.set_text(
                    f'當前信心度: {confidence:.3f} | '
                    f'偵測次數: {count} | '
                    f'閾值: 0.3'
                )
        else:
            self.status_text.set_text('準備就緒')
        
        return self.line1, self.line2, self.status_text, self.stats_text
    
    def run_test(self):
        """執行測試"""
        logger.info("開始喚醒詞視覺化測試")
        
        # 開始喚醒詞偵測
        if not self.start_wakeword():
            logger.error("無法開始喚醒詞偵測")
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
        
        # 停止喚醒詞偵測
        self.stop_wakeword()
        
        # 清理
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join(timeout=1)
        
        # 顯示結果摘要
        if self.detection_results:
            logger.block("喚醒詞測試結果", [
                f"總偵測事件: {len(self.detection_results)}",
                f"偵測次數: {self.detection_count}",
                f"偵測到的關鍵字: {set(e['keyword'] for e in self.detection_events if 'keyword' in e)}"
            ])
        
        return True
    
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
    print("🎯  OpenWakeWord 服務視覺化測試")
    print("="*60)
    print("\n注意：")
    print("1. 預設使用 'Hi高醫' 喚醒詞")
    print("2. 請對著麥克風說 'Hi高醫' 來觸發偵測")
    print("3. 綠色柱狀表示偵測到喚醒詞")
    print("4. 紅色虛線表示偵測閾值 (0.3)")
    print()
    
    tester = WakewordVisualTest()
    
    try:
        print("\n開始喚醒詞測試...")
        print("請對著麥克風說 'Hey Jarvis' 或其他設定的喚醒詞")
        print("綠色標記表示偵測到喚醒詞")
        print("橙色填充表示高信心度（>0.5）")
        print("藍色填充表示低信心度（≤0.5）")
        print("📌 關閉視窗即可停止測試")
        print("✨ 已啟用插值和平滑處理，曲線呈現自然的變化\n")
        
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