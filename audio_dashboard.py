#!/usr/bin/env python3
"""
ASR Hub 音訊監控 Dashboard

使用 matplotlib 製作的整合式監控介面：
- 上半部：即時麥克風聲波圖
- 下半部左側：Wakeword 偵測狀態
- 下半部右側：VAD 語音活動偵測
"""

import sys
import os
import time
import numpy as np
import pyaudio
import threading
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as patches
from matplotlib.gridspec import GridSpec
from collections import deque
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

# 設定 matplotlib 使用支援中文的字體和黑底主題
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
plt.style.use('dark_background')

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from src.service.wakeword.openwakeword import openwakeword
from src.service.vad.silero_vad import silero_vad
from src.core.audio_queue_manager import audio_queue
from src.utils.logger import logger
from src.interface.audio import AudioChunk
from src.interface.vad import VADState, VADResult
from src.interface.wakeword import WakewordDetection


@dataclass
class DashboardConfig:
    """Dashboard 配置"""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1280  # OpenWakeWord 需要 1280 samples
    vad_chunk_size: int = 512  # VAD 需要較小的 chunk
    format: int = pyaudio.paInt16
    window_seconds: float = 10.0  # 顯示的時間窗口
    update_interval: int = 50  # 更新間隔 (ms)


class AudioDashboard:
    """整合式音訊監控 Dashboard"""
    
    def __init__(self, config: Optional[DashboardConfig] = None):
        self.config = config or DashboardConfig()
        
        # PyAudio 設定
        self.p = pyaudio.PyAudio()
        
        # 初始化服務
        self._init_services()
        
        # 初始化介面
        self._init_ui()
        
        # 數據緩衝
        self._init_buffers()
        
        # 音訊流
        self.stream = None
        self.is_running = False
        self.audio_thread = None
        
        # 統計資訊
        self.wake_count = 0
        self.speech_duration = 0
        self.last_wake_time = None
        self.speech_start_time = None
        self.speech_regions = []
        
    def _init_services(self):
        """初始化服務"""
        logger.info("初始化 Wakeword 和 VAD 服務...")
        
        self.session_id = f"dashboard_{int(time.time())}"
        self.start_time = time.time()
        
        # 初始化 VAD 服務
        if not silero_vad.is_initialized():
            logger.info("初始化 Silero VAD 服務...")
            if not silero_vad._ensure_initialized():
                logger.warning("⚠️ VAD 服務初始化失敗")
            else:
                logger.info("✅ VAD 服務已初始化")
        
        # 初始化 Wakeword 服務
        if not openwakeword.is_initialized():
            logger.info("初始化 OpenWakeword 服務...")
            if not openwakeword.initialize():
                logger.warning("⚠️ Wakeword 服務初始化失敗")
            else:
                logger.info("✅ Wakeword 服務已初始化")
        
        # VAD 和 Wakeword 狀態
        self.current_vad_state = VADState.SILENCE
        self.current_vad_probability = 0.0
        self.wakeword_detections = []
    
    def _init_ui(self):
        """初始化使用者介面"""
        # 創建圖形窗口，使用 GridSpec 進行佈局
        self.fig = plt.figure(figsize=(16, 10), facecolor='#0f0f0f')
        gs = GridSpec(2, 2, figure=self.fig, height_ratios=[1, 1], width_ratios=[1, 1])
        
        # 設定主標題
        self.fig.suptitle('🎙️ ASR Hub 音訊監控 Dashboard', 
                          fontsize=16, fontweight='bold', color='#00ff88')
        
        # 上半部：麥克風聲波圖（橫跨整個寬度）
        self.ax_waveform = self.fig.add_subplot(gs[0, :])
        self._setup_waveform_plot()
        
        # 下半部左側：Wakeword 偵測
        self.ax_wakeword = self.fig.add_subplot(gs[1, 0])
        self._setup_wakeword_plot()
        
        # 下半部右側：VAD 偵測
        self.ax_vad = self.fig.add_subplot(gs[1, 1])
        self._setup_vad_plot()
        
        # 調整佈局
        plt.tight_layout(rect=[0, 0.03, 1, 0.97])
        
    def _setup_waveform_plot(self):
        """設定聲波圖"""
        self.ax_waveform.set_title('🎵 即時麥克風聲波', fontsize=12, color='#00ccff')
        self.ax_waveform.set_ylabel('振幅', fontsize=10)
        self.ax_waveform.set_xlabel('時間 (秒)', fontsize=10)
        self.ax_waveform.set_ylim(-10000, 10000)
        self.ax_waveform.grid(True, alpha=0.2, linestyle='--', color='#404040')
        self.ax_waveform.set_facecolor('#1a1a1a')
        
        # 創建波形線
        x_data = np.linspace(0, self.config.window_seconds, 
                           int(self.config.window_seconds * self.config.sample_rate))
        self.waveform_line, = self.ax_waveform.plot(x_data, np.zeros_like(x_data), 
                                                    color='#00ff88', linewidth=0.8)
        
        # 添加 RMS 能量線
        self.rms_line, = self.ax_waveform.plot([], [], 'r-', alpha=0.7, 
                                              linewidth=2, label='RMS 能量')
        self.ax_waveform.legend(loc='upper right', fontsize=9)
        
    def _setup_wakeword_plot(self):
        """設定 Wakeword 偵測圖"""
        self.ax_wakeword.set_title('🔊 喚醒詞偵測', fontsize=12, color='#ffcc00')
        self.ax_wakeword.set_ylabel('信心度', fontsize=10)
        self.ax_wakeword.set_xlabel('時間 (秒)', fontsize=10)
        self.ax_wakeword.set_ylim(0, 1.1)
        self.ax_wakeword.set_xlim(0, self.config.window_seconds)
        
        # 添加閾值線
        self.ax_wakeword.axhline(y=0.5, color='yellow', linestyle='--', 
                                alpha=0.5, linewidth=1, label='偵測閾值')
        
        self.ax_wakeword.grid(True, alpha=0.2, linestyle='--', color='#404040')
        self.ax_wakeword.set_facecolor('#1a1a1a')
        
        # 創建信心度線
        self.wake_line, = self.ax_wakeword.plot([], [], 'g-', linewidth=1.5, 
                                               label='信心度')
        
        # 添加偵測標記
        self.wake_scatter = self.ax_wakeword.scatter([], [], c='red', s=100, 
                                                    zorder=5, label='偵測到')
        
        # 統計文字
        self.wake_text = self.ax_wakeword.text(0.02, 0.95, '', 
                                              transform=self.ax_wakeword.transAxes,
                                              fontsize=9, color='white',
                                              verticalalignment='top')
        
        self.ax_wakeword.legend(loc='upper right', fontsize=9)
        
    def _setup_vad_plot(self):
        """設定 VAD 偵測圖"""
        self.ax_vad.set_title('🗣️ 語音活動偵測 (VAD)', fontsize=12, color='#ff6666')
        self.ax_vad.set_ylabel('語音概率', fontsize=10)
        self.ax_vad.set_xlabel('時間 (秒)', fontsize=10)
        self.ax_vad.set_ylim(0, 1.1)
        self.ax_vad.set_xlim(0, self.config.window_seconds)
        
        # 添加閾值線
        self.ax_vad.axhline(y=0.5, color='yellow', linestyle='--', 
                          alpha=0.5, linewidth=1, label='偵測閾值')
        
        self.ax_vad.grid(True, alpha=0.2, linestyle='--', color='#404040')
        self.ax_vad.set_facecolor('#1a1a1a')
        
        # 創建概率線
        self.vad_line, = self.ax_vad.plot([], [], 'b-', linewidth=1.5, 
                                         label='語音概率')
        
        # 添加語音區域填充
        self.vad_fill = None
        
        # 狀態指示器
        self.vad_status = self.ax_vad.text(0.98, 0.95, '⚪ 靜音', 
                                          transform=self.ax_vad.transAxes,
                                          fontsize=10, color='white',
                                          horizontalalignment='right',
                                          verticalalignment='top',
                                          bbox=dict(boxstyle='round,pad=0.3',
                                                  facecolor='gray', alpha=0.5))
        
        # 統計文字
        self.vad_text = self.ax_vad.text(0.02, 0.95, '', 
                                        transform=self.ax_vad.transAxes,
                                        fontsize=9, color='white',
                                        verticalalignment='top')
        
        self.ax_vad.legend(loc='upper right', fontsize=9)
        
    def _init_buffers(self):
        """初始化數據緩衝"""
        buffer_size = int(self.config.window_seconds * self.config.sample_rate)
        points_per_sec = self.config.sample_rate / self.config.chunk_size
        
        # 聲波緩衝
        self.audio_buffer = deque(maxlen=buffer_size)
        self.audio_buffer.extend(np.zeros(buffer_size))
        
        # RMS 緩衝
        self.rms_buffer = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        
        # Wakeword 緩衝
        self.wake_times = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        self.wake_confidence = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        
        # VAD 緩衝
        self.vad_times = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        self.vad_probability = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        self.vad_state = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        
        # 時間軸
        self.time_axis = deque(maxlen=int(self.config.window_seconds * points_per_sec))
        
        # 初始化緩衝
        for _ in range(int(self.config.window_seconds * points_per_sec)):
            self.wake_times.append(0)
            self.wake_confidence.append(0)
            self.vad_times.append(0)
            self.vad_probability.append(0)
            self.vad_state.append(False)
            self.time_axis.append(0)
            
        self.current_time = 0
        
    def on_wakeword_detected(self, detection: WakewordDetection):
        """Wakeword 檢測回調"""
        if not self.start_time:
            return
            
        current_time = time.time() - self.start_time
        self.wake_count += 1
        self.last_wake_time = current_time
        
        logger.info(f"🎯 檢測到喚醒詞: {detection.keyword} (信心度: {detection.confidence:.3f}) @ {current_time:.2f}s")
        
        # 記錄檢測事件
        self.wakeword_detections.append({
            'time': current_time,
            'keyword': detection.keyword,
            'confidence': detection.confidence
        })
    
    def on_vad_change(self, result: VADResult):
        """VAD 狀態變化回調"""
        if not self.start_time:
            return
            
        current_time = time.time() - self.start_time
        
        # 更新當前狀態和概率
        self.current_vad_state = result.state
        self.current_vad_probability = result.probability
        
        if result.state == VADState.SPEECH:
            if self.speech_start_time is None:
                self.speech_start_time = current_time
                logger.info(f"🔊 檢測到語音開始 @ {current_time:.2f}s (概率: {result.probability:.3f})")
        elif result.state == VADState.SILENCE:
            if self.speech_start_time is not None:
                end_time = current_time
                duration = end_time - self.speech_start_time
                logger.info(f"🔇 檢測到語音結束 @ {end_time:.2f}s (持續 {duration:.2f}s)")
                
                # 記錄語音區域
                self.speech_regions.append((self.speech_start_time, end_time))
                self.speech_duration += duration
                self.speech_start_time = None
    
    def _audio_processing(self):
        """音訊處理執行緒"""
        logger.info("音訊處理執行緒已啟動")
        
        while self.is_running:
            try:
                if not self.stream:
                    break
                
                # 讀取音訊
                audio_data = self.stream.read(self.config.chunk_size, exception_on_overflow=False)
                
                # 轉換為 numpy array
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                
                # 更新聲波緩衝
                self.audio_buffer.extend(audio_np)
                
                # 計算 RMS
                rms = np.sqrt(np.mean(audio_np.astype(float) ** 2))
                self.rms_buffer.append(rms)
                
                # 推送到 audio queue (VAD 和 Wakeword 會從這裡讀取)
                audio_queue.push(self.session_id, audio_data)
                
                # 更新時間
                self.current_time = time.time() - self.start_time
                self.time_axis.append(self.current_time)
                
                # 更新緩衝（使用回調獲得的值）
                self.wake_times.append(self.current_time)
                if len(self.wakeword_detections) > 0:
                    # 檢查最近的檢測
                    last_detection = self.wakeword_detections[-1]
                    if self.current_time - last_detection['time'] < 1.0:
                        # 衰減顯示
                        decay = np.exp(-(self.current_time - last_detection['time']) * 3)
                        self.wake_confidence.append(last_detection['confidence'] * decay)
                    else:
                        self.wake_confidence.append(0)
                else:
                    self.wake_confidence.append(0)
                
                self.vad_times.append(self.current_time)
                self.vad_probability.append(self.current_vad_probability)
                self.vad_state.append(self.current_vad_state == VADState.SPEECH)
                
                time.sleep(0.01)  # 避免過度佔用 CPU
                
            except Exception as e:
                if self.is_running:
                    logger.error(f"音訊處理錯誤: {e}")
                break
        
        logger.info("音訊處理執行緒結束")
    
    def update_plot(self, frame):
        """更新圖表"""
        try:
            # 更新聲波圖
            audio_array = np.array(self.audio_buffer)
            time_array = np.linspace(max(0, self.current_time - self.config.window_seconds),
                                   self.current_time, len(audio_array))
            self.waveform_line.set_data(time_array, audio_array)
            
            # 更新 RMS
            if len(self.rms_buffer) > 0:
                rms_array = np.array(self.rms_buffer) * 100  # 放大以便顯示
                rms_time = np.linspace(max(0, self.current_time - self.config.window_seconds),
                                     self.current_time, len(rms_array))
                self.rms_line.set_data(rms_time, rms_array)
            
            # 自動調整 Y 軸範圍
            if len(audio_array) > 0:
                max_val = np.max(np.abs(audio_array))
                if max_val > 0:
                    self.ax_waveform.set_ylim(-max_val * 1.2, max_val * 1.2)
            
            # 調整 X 軸範圍
            self.ax_waveform.set_xlim(max(0, self.current_time - self.config.window_seconds),
                                     self.current_time)
            
            # 更新 Wakeword 圖
            wake_time_array = np.array(list(self.wake_times))
            wake_conf_array = np.array(list(self.wake_confidence))
            self.wake_line.set_data(wake_time_array, wake_conf_array)
            
            # 標記偵測點
            detect_mask = wake_conf_array > 0.5
            if np.any(detect_mask):
                self.wake_scatter.set_offsets(np.c_[wake_time_array[detect_mask], 
                                                   wake_conf_array[detect_mask]])
            else:
                self.wake_scatter.set_offsets(np.empty((0, 2)))
            
            # 更新統計
            self.wake_text.set_text(f'偵測次數: {self.wake_count}')
            
            # 調整 Wakeword X 軸
            self.ax_wakeword.set_xlim(max(0, self.current_time - self.config.window_seconds),
                                     self.current_time)
            
            # 更新 VAD 圖
            vad_time_array = np.array(list(self.vad_times))
            vad_prob_array = np.array(list(self.vad_probability))
            vad_state_array = np.array(list(self.vad_state))
            
            self.vad_line.set_data(vad_time_array, vad_prob_array)
            
            # 填充語音區域
            if self.vad_fill:
                self.vad_fill.remove()
            self.vad_fill = self.ax_vad.fill_between(vad_time_array, 0, vad_prob_array,
                                                    where=(vad_prob_array > 0.5),
                                                    alpha=0.3, color='red')
            
            # 更新狀態指示器
            if len(vad_state_array) > 0 and vad_state_array[-1]:
                self.vad_status.set_text('🔴 說話中')
                self.vad_status.set_bbox(dict(boxstyle='round,pad=0.3',
                                             facecolor='red', alpha=0.7))
            else:
                self.vad_status.set_text('⚪ 靜音')
                self.vad_status.set_bbox(dict(boxstyle='round,pad=0.3',
                                             facecolor='gray', alpha=0.5))
            
            # 更新統計
            speech_percent = (self.speech_duration / max(1, self.current_time)) * 100
            self.vad_text.set_text(f'語音時間: {self.speech_duration:.1f}秒 ({speech_percent:.1f}%)')
            
            # 調整 VAD X 軸
            self.ax_vad.set_xlim(max(0, self.current_time - self.config.window_seconds),
                                self.current_time)
            
        except Exception as e:
            logger.error(f"更新圖表錯誤: {e}")
            
        return [self.waveform_line, self.rms_line, self.wake_line, self.wake_scatter,
                self.vad_line, self.vad_fill]
    
    def run(self):
        """執行 Dashboard"""
        try:
            # 開啟麥克風串流
            self.stream = self.p.open(
                format=self.config.format,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=self.config.chunk_size
            )
            
            # 開始監聽服務
            vad_success = silero_vad.start_listening(
                session_id=self.session_id,
                callback=self.on_vad_change
            )
            
            wakeword_success = openwakeword.start_listening(
                session_id=self.session_id,
                callback=self.on_wakeword_detected
            )
            
            if vad_success and wakeword_success:
                self.is_running = True
                logger.info("🎙️ Dashboard 已啟動，開始監聽...")
                
                # 啟動音訊處理執行緒
                self.audio_thread = threading.Thread(target=self._audio_processing)
                self.audio_thread.daemon = True
                self.audio_thread.start()
                
                # 啟動動畫
                ani = animation.FuncAnimation(
                    self.fig, 
                    self.update_plot,
                    interval=self.config.update_interval,
                    blit=True,
                    cache_frame_data=False
                )
                
                plt.show()
            else:
                logger.error("無法啟動監聽服務")
            
        except Exception as e:
            logger.error(f"執行錯誤: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理資源"""
        self.is_running = False
        
        # 停止服務
        if hasattr(self, 'session_id'):
            silero_vad.stop_listening(self.session_id)
            openwakeword.stop_listening(self.session_id)
            logger.info("服務已停止")
        
        # 關閉音訊流
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        # 等待執行緒結束
        if self.audio_thread:
            self.audio_thread.join(timeout=1)
        
        self.p.terminate()
        logger.info("Dashboard 已關閉")


def main():
    """主程式"""
    print("""
╔════════════════════════════════════════════════╗
║      🎙️ ASR Hub 音訊監控 Dashboard 🎙️          ║
╠════════════════════════════════════════════════╣
║  上半部：即時麥克風聲波圖                       ║
║  下半部左側：Wakeword 喚醒詞偵測               ║
║  下半部右側：VAD 語音活動偵測                  ║
╠════════════════════════════════════════════════╣
║  按 Ctrl+C 或關閉視窗結束程式                  ║
╚════════════════════════════════════════════════╝
    """)
    
    try:
        dashboard = AudioDashboard()
        dashboard.run()
    except KeyboardInterrupt:
        print("\n程式已終止")
    except Exception as e:
        print(f"錯誤: {e}")


if __name__ == "__main__":
    main()