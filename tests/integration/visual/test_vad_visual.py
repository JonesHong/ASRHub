#!/usr/bin/env python3
"""
VAD 服務視覺化測試

使用 matplotlib 繪製即時聲波圖：
- 上半部：即時麥克風聲波圖
- 下半部：VAD 檢測結果（語音活動區域標記）
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

from src.service.vad.silero_vad import silero_vad
from src.core.audio_queue_manager import audio_queue
from src.utils.logger import logger
from src.interface.vad import VADState, VADResult


class VADVisualTest:
    """VAD 視覺化測試"""
    
    def __init__(self):
        # PyAudio 設定
        self.p = pyaudio.PyAudio()
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 512  # VAD 需要較小的 chunk
        self.format = pyaudio.paInt16
        
        # 視覺化設定
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8), facecolor='#1a1a1a')
        self.fig.suptitle('VAD 服務視覺化測試', fontsize=14, color='white')
        
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
        
        # 下半部：VAD 檢測結果
        self.ax2.set_title('VAD 檢測結果（紅色=語音, 藍色=靜音）', color='white')
        self.ax2.set_xlabel('時間 (秒)')
        self.ax2.set_ylabel('語音概率')
        self.ax2.set_ylim(0, 1.1)
        self.ax2.set_xlim(0, 20)  # 初始化 X 軸範圍為完整的 20 秒窗口
        self.ax2.axhline(y=0.5, color='yellow', linestyle='--', alpha=0.5, label='閾值')
        self.ax2.grid(True, alpha=0.3, color='gray')
        self.ax2.set_facecolor('#2a2a2a')
        self.ax2.legend(loc='upper right')
        
        # 數據緩衝
        self.realtime_buffer = np.zeros(self.chunk_size)
        
        # 計算所需的緩衝區大小
        self.window_sec = 20.0  # 視窗大小（秒）
        points_per_sec = self.sample_rate / self.chunk_size  # 16000/512 ≈ 31.25
        buffer_length = int(self.window_sec * points_per_sec * 1.2)  # ≈ 750，預留 20% 餘裕
        
        self.vad_probability_buffer = deque(maxlen=buffer_length)  # 足夠容納 20+ 秒的資料
        self.vad_time_buffer = deque(maxlen=buffer_length)
        
        # 插值和平滑參數
        self.interpolation_enabled = True  # 啟用插值
        self.smoothing_enabled = True      # 啟用平滑
        self.smoothing_window = 5          # 平滑窗口大小
        self.last_probability = 0.0        # 上一次的概率值（用於插值）
        self.probability_change_rate = 0.1  # 概率變化速率（用於平滑過渡）
        self.speech_regions = []  # 語音區域列表
        
        # 繪圖線條 - 使用填充效果更容易看出波形
        self.line1, = self.ax1.plot([], [], 'cyan', linewidth=0.8, alpha=0.8)
        # 添加填充效果
        self.fill1 = None
        self.line2, = self.ax2.plot([], [], 'lime', linewidth=1.0, label='VAD 概率')
        
        # VAD 狀態
        self.is_running = False
        self.stream = None
        self.session_id = None
        self.start_time = None
        self.current_vad_state = VADState.SILENCE
        self.current_probability = 0.0
        self.speech_start_time = None
        
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
        
        # VAD 回調結果
        self.vad_results = []
    
    def on_vad_change(self, result: VADResult):
        """VAD 狀態變化回調
        
        Args:
            result: VAD 檢測結果
        """
        current_time = time.time() - self.start_time
        
        # 更新當前狀態和概率
        self.current_vad_state = result.state
        self.current_probability = result.probability
        
        if result.state == VADState.SPEECH:
            if self.speech_start_time is None:
                self.speech_start_time = current_time
                logger.info(f"🔊 檢測到語音開始 @ {current_time:.2f}s (概率: {result.probability:.3f})")
                self.vad_results.append({
                    'event': 'speech_start',
                    'time': current_time,
                    'probability': result.probability
                })
        elif result.state == VADState.SILENCE:
            if self.speech_start_time is not None:
                end_time = current_time
                duration = end_time - self.speech_start_time
                logger.info(f"🔇 檢測到語音結束 @ {end_time:.2f}s (持續 {duration:.2f}s)")
                
                # 記錄語音區域
                self.speech_regions.append((self.speech_start_time, end_time))
                
                self.vad_results.append({
                    'event': 'speech_end',
                    'time': end_time,
                    'duration': duration
                })
                self.speech_start_time = None
    
    def start_vad(self):
        """開始 VAD 測試"""
        self.session_id = f"vad_test_{int(time.time())}"
        self.start_time = time.time()
        
        logger.info(f"開始 VAD 測試，Session ID: {self.session_id}")
        
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
        
        # 確保 VAD 服務已初始化
        if not silero_vad.is_initialized():
            logger.info("初始化 Silero VAD 服務...")
            if not silero_vad._ensure_initialized():
                logger.error("VAD 服務初始化失敗")
                return False
        
        # 開始 VAD 監聽
        success = silero_vad.start_listening(
            session_id=self.session_id,
            callback=self.on_vad_change
        )
        
        if success:
            self.is_running = True
            logger.info("VAD 服務已啟動")
            
            # 啟動音訊處理執行緒
            self.audio_thread = threading.Thread(
                target=self._audio_processing
            )
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            return True
        else:
            logger.error("無法啟動 VAD 服務")
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
                
                # 推送到 audio queue (VAD 會從這裡讀取)
                audio_queue.push(self.session_id, audio_data)
                
                # 獲取當前時間
                current_time = time.time() - self.start_time
                
                # 計算音量作為概率的參考（實際概率來自 VAD）
                rms = np.sqrt(np.mean(audio_np.astype(float) ** 2))
                volume_normalized = min(1.0, rms / 10000)  # 正規化到 0-1
                
                # 獲取基礎 VAD 概率
                base_probability = self.current_probability
                
                # 插值處理：在狀態轉換時創建平滑過渡
                if self.interpolation_enabled:
                    # 計算目標概率和當前顯示概率的差異
                    probability_diff = base_probability - self.last_probability
                    
                    # 使用漸進式插值，避免突然跳躍
                    if abs(probability_diff) > 0.001:  # 更敏感的閾值
                        # 根據狀態調整變化速率
                        if self.current_vad_state == VADState.SPEECH:
                            # 語音狀態時，向上變化較快（快速響應語音開始）
                            if probability_diff > 0:
                                interpolation_rate = 0.5  # 快速上升
                            else:
                                interpolation_rate = 0.2  # 緩慢下降
                        else:
                            # 靜音狀態時，向下變化較快（快速響應語音結束）
                            if probability_diff < 0:
                                interpolation_rate = 0.5  # 快速下降
                            else:
                                interpolation_rate = 0.2  # 緩慢上升
                        
                        # 計算插值後的概率
                        interpolated_probability = self.last_probability + probability_diff * interpolation_rate
                    else:
                        interpolated_probability = base_probability
                else:
                    interpolated_probability = base_probability
                
                # 添加基於音量的微小波動（模擬連續性）
                # 這讓概率曲線即使在穩定狀態下也有輕微變化
                if self.smoothing_enabled:
                    # 使用音量來調節概率的微小變化
                    volume_influence = volume_normalized * 0.05  # 最多影響 5%
                    
                    # 根據當前狀態添加自然波動，但不強制限制範圍
                    if self.current_vad_state == VADState.SPEECH:
                        # 語音狀態：在實際概率基礎上添加音量相關的波動
                        # 概率會在 (base * 0.95) 到 (base * 1.05) 之間波動
                        smoothed_probability = interpolated_probability * (1.0 + volume_influence)
                        # 只限制上限，不限制下限
                        smoothed_probability = min(1.0, smoothed_probability)
                    else:
                        # 靜音狀態：在實際概率基礎上減少音量相關的波動
                        # 概率會在 (base * 0.95) 到 (base * 1.0) 之間波動
                        smoothed_probability = interpolated_probability * (1.0 - volume_influence)
                        # 只限制下限，不限制上限
                        smoothed_probability = max(0.0, smoothed_probability)
                else:
                    smoothed_probability = interpolated_probability
                
                # 更新上一次的概率值
                self.last_probability = smoothed_probability
                
                # 添加到緩衝
                self.vad_probability_buffer.append(smoothed_probability)
                self.vad_time_buffer.append(current_time)
                
                # 基於時間裁剪，只保留視窗範圍內的資料
                while (len(self.vad_time_buffer) > 1 and 
                       self.vad_time_buffer[-1] - self.vad_time_buffer[0] > self.window_sec):
                    self.vad_time_buffer.popleft()
                    self.vad_probability_buffer.popleft()
                
                # 更新統計
                self.current_stats = {
                    'elapsed': current_time,
                    'vad_probability': smoothed_probability,  # 使用平滑後的概率
                    'vad_state': self.current_vad_state,
                    'speech_count': len(self.speech_regions),
                    'volume': volume_normalized
                }
                
                time.sleep(0.01)  # 避免過度佔用 CPU
                
            except Exception as e:
                logger.error(f"音訊處理錯誤: {e}")
                break
        
        logger.info("音訊處理執行緒結束")
    
    def stop_vad(self):
        """停止 VAD 測試"""
        self.is_running = False
        
        # 關閉麥克風
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        # 停止 VAD 監聽
        if self.session_id:
            silero_vad.stop_listening(self.session_id)
            logger.info("VAD 服務已停止")
        
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
                    # 根據實際振幅調整範圍
                    y_limit = max_val * self.y_margin
                    # 平滑調整，避免跳動
                    current_ylim = self.ax1.get_ylim()
                    if abs(current_ylim[1] - y_limit) > y_limit * 0.2:
                        self.ax1.set_ylim(-y_limit, y_limit)
            
            # 移除舊的填充
            if self.fill1:
                self.fill1.remove()
                self.fill1 = None
            
            # 添加新的填充效果（讓波形更明顯）
            if len(self.realtime_buffer) > 0:
                self.fill1 = self.ax1.fill_between(
                    x1, 0, self.realtime_buffer,
                    color='cyan', alpha=0.3
                )
            
            # 更新 VAD 概率曲線
            if len(self.vad_probability_buffer) > 0:
                time_array = np.array(self.vad_time_buffer)
                prob_array = np.array(self.vad_probability_buffer)
                
                # 應用移動平均進一步平滑（可選）
                if self.smoothing_enabled and len(prob_array) > self.smoothing_window:
                    # 使用卷積進行移動平均
                    kernel = np.ones(self.smoothing_window) / self.smoothing_window
                    # 保持邊界值
                    prob_smoothed = np.convolve(prob_array, kernel, mode='same')
                    
                    # 對最近的數據點應用較少的平滑，保持響應性
                    blend_factor = np.linspace(0.3, 1.0, len(prob_array))
                    prob_final = prob_array * (1 - blend_factor) + prob_smoothed * blend_factor
                else:
                    prob_final = prob_array
                
                self.line2.set_data(time_array, prob_final)
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
                else:
                    # 沒有數據時顯示 0 到 20 秒
                    self.ax2.set_xlim(0, self.window_sec)
                
                # 添加填充效果，讓曲線更有「山峰」的感覺
                # 移除舊的填充
                for patch in self.ax2.collections[:]:
                    patch.remove()
                
                # 添加新的漸層填充
                if len(time_array) > 1:
                    # 高概率區域（語音）用暖色
                    high_prob_mask = prob_final > 0.5
                    if np.any(high_prob_mask):
                        self.ax2.fill_between(
                            time_array, 0.5, prob_final,
                            where=high_prob_mask,
                            color='orange', alpha=0.3,
                            interpolate=True
                        )
                    
                    # 低概率區域（靜音）用冷色
                    low_prob_mask = prob_final <= 0.5
                    if np.any(low_prob_mask):
                        self.ax2.fill_between(
                            time_array, 0, prob_final,
                            where=low_prob_mask,
                            color='blue', alpha=0.2,
                            interpolate=True
                        )
            
            # 繪製語音區域
            for rect in self.ax2.patches[:]:
                if isinstance(rect, patches.Rectangle):
                    rect.remove()
            
            # 獲取當前時間和視窗範圍
            current_time = time.time() - self.start_time if self.start_time else 0
            
            # 使用與 X 軸相同的視窗範圍
            if len(self.vad_time_buffer) > 0:
                time_arr = np.array(self.vad_time_buffer)
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
            
            for start, end in self.speech_regions:
                # 只顯示在當前視窗範圍內的區域
                if end >= window_start and start <= window_end:
                    # 裁剪到視窗範圍內
                    visible_start = max(start, window_start)
                    visible_end = min(end, window_end)
                    rect = patches.Rectangle(
                        (visible_start, 0), visible_end - visible_start, 1.1,
                        linewidth=0, facecolor='red', alpha=0.2
                    )
                    self.ax2.add_patch(rect)
            
            # 如果當前正在說話，顯示正在進行的區域
            if self.speech_start_time is not None:
                current_end = current_time
                if current_end >= window_start and self.speech_start_time <= window_end:
                    # 裁剪到視窗範圍內
                    visible_start = max(self.speech_start_time, window_start)
                    visible_end = min(current_end, window_end)
                    rect = patches.Rectangle(
                        (visible_start, 0), visible_end - visible_start, 1.1,
                        linewidth=1, facecolor='yellow', alpha=0.3, linestyle='--'
                    )
                    self.ax2.add_patch(rect)
            
            # 更新狀態文字
            if hasattr(self, 'current_stats'):
                elapsed = self.current_stats['elapsed']
                prob = self.current_stats['vad_probability']
                state = self.current_stats['vad_state']
                speech_count = self.current_stats['speech_count']
                volume = self.current_stats['volume']
                
                status = '🔊 說話中' if state == VADState.SPEECH else '🔇 靜音'
                self.status_text.set_text(f'{status} | 時間: {elapsed:.1f}秒 | 音量: {volume:.2f}')
                
                # 計算統計
                total_speech_time = sum(end - start for start, end in self.speech_regions)
                if self.speech_start_time is not None:
                    # 加上當前正在說話的時間
                    total_speech_time += (elapsed - self.speech_start_time)
                
                self.stats_text.set_text(
                    f'VAD 概率: {prob:.3f} | '
                    f'語音段數: {speech_count} | '
                    f'總語音時長: {total_speech_time:.1f}秒'
                )
        else:
            self.status_text.set_text('準備就緒')
        
        return self.line1, self.line2, self.status_text, self.stats_text
    
    def run_test(self):
        """執行測試"""
        logger.info("開始 VAD 視覺化測試")
        
        # 開始 VAD
        if not self.start_vad():
            logger.error("無法開始 VAD")
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
        
        # 停止 VAD
        self.stop_vad()
        
        # 清理
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join(timeout=1)
        
        # 顯示結果摘要
        if self.vad_results:
            logger.block("VAD 測試結果", [
                f"總檢測事件: {len(self.vad_results)}",
                f"語音段數: {len(self.speech_regions)}",
                f"總語音時長: {sum(end - start for start, end in self.speech_regions):.1f} 秒"
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
    print("🎤  VAD 服務視覺化測試")
    print("="*60)
    
    tester = VADVisualTest()
    
    try:
        print("\n開始 VAD 測試...")
        print("請間歇性地對著麥克風說話")
        print("紅色區域表示檢測到語音")
        print("黃色虛線區域表示正在說話")
        print("橙色填充表示高概率（語音）")
        print("藍色填充表示低概率（靜音）")
        print("📌 關閉視窗即可停止測試")
        print("✨ 已啟用插值和平滑處理，曲線呈現自然的山峰形狀\n")
        
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