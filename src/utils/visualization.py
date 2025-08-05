#!/usr/bin/env python3
"""
ASR Hub 統一視覺化工具

此模組提供所有視覺化需求的統一介面和一致的視覺設計。
支援 VAD、喚醒詞檢測、錄音監控和 Pipeline 整合視覺化。

主要特性：
- 統一的視覺風格和配色方案
- 跨平台中文字體支援
- 實時數據更新和動畫
- 可擴展的基礎類別設計

Classes:
    BaseVisualization: 基礎視覺化類別，提供通用功能
    VADVisualization: VAD 專用視覺化
    WakeWordVisualization: 喚醒詞檢測視覺化
    RecordingVisualization: 錄音狀態監控視覺化
    PipelineVisualization: Pipeline 整合視覺化
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.animation import FuncAnimation
from typing import List, Tuple, Optional, Dict, Any
import queue
import time
import platform
from scipy import signal

# 設定中文字體
if platform.system() == "Windows":
    # Windows 系統的中文字體優先順序
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Microsoft JhengHei", "SimHei", "KaiTi", "FangSong", "Arial Unicode MS"]
    # 確保 monospace 字體也支援中文
    plt.rcParams["font.monospace"] = ["Consolas", "Courier New", "Microsoft YaHei Mono"]
else:
    # Linux/Mac 系統
    plt.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei", "DejaVu Sans", "sans-serif"]
    plt.rcParams["font.monospace"] = ["DejaVu Sans Mono", "monospace"]
    
plt.rcParams["axes.unicode_minus"] = False

# 強制 matplotlib 重新載入字體快取
try:
    from matplotlib import font_manager
    font_manager._rebuild()
except:
    pass

# 嘗試使用適當的後端
try:
    matplotlib.use('TkAgg')
except:
    try:
        matplotlib.use('Qt5Agg')
    except:
        matplotlib.use('Agg')


class BaseVisualization:
    """基礎視覺化類別"""
    
    # 統一的視覺化配置
    AUDIO_Y_RANGE = (-20000, 20000)  # 音波圖 Y軸範圍
    AUDIO_Y_TICKS = [-20000, -10000, 0, 10000, 20000]  # Y軸刻度
    FIGURE_SIZE = (12, 10)  # 圖形大小
    STYLE = "dark_background"  # 統一風格
    
    # 顏色配置
    COLORS = {
        'audio': '#00bfff',      # 深天藍色 - 音訊波形
        'vad': '#00ff00',        # 綠色 - VAD 狀態
        'wakeword': '#ff69b4',   # 粉紅色 - 喚醒詞
        'recording': '#ff0000',  # 紅色 - 錄音狀態
        'threshold': '#ffa500',  # 橙色 - 閾值線
        'grid': '#333333',       # 深灰色 - 網格
    }
    
    # 聲譜圖顏色配置（從 visualization_colormap.py 整合）
    SPECTROGRAM_COLORMAPS = {
        'viridis': {
            'cmap': 'viridis',
            'vmin': -60,
            'vmax': -10,
            'description': '綠到黃，對比度高，色盲友好'
        },
        'plasma': {
            'cmap': 'plasma',
            'vmin': -60,
            'vmax': -10,
            'description': '紫到黃，視覺效果好'
        },
        'inferno': {
            'cmap': 'inferno',
            'vmin': -60,
            'vmax': -10,
            'description': '黑到黃，類似火焰'
        },
        'magma': {
            'cmap': 'magma',
            'vmin': -60,
            'vmax': -10,
            'description': '黑到白，經典選擇'
        },
        'jet': {
            'cmap': 'jet',
            'vmin': -70,
            'vmax': 0,
            'description': '藍到紅，傳統聲譜圖配色'
        },
        'cool': {
            'cmap': 'cool',
            'vmin': -60,
            'vmax': -10,
            'description': '藍到粉紅，柔和'
        },
        'turbo': {
            'cmap': 'turbo',
            'vmin': -60,
            'vmax': -10,
            'description': '改進版 jet，更好的感知均勻性'
        }
    }
    
    # 預設聲譜圖配色
    DEFAULT_COLORMAP = 'turbo'  # 目前使用的配色
    
    def __init__(self, title: str):
        self.title = title
        self.fig = None
        self.axes = None
        self.lines = {}
        self.texts = {}
        self.data_queue = queue.Queue()
        self.is_running = False
        
    def setup_plot(self, num_subplots: int = 2) -> Tuple[plt.Figure, List[plt.Axes]]:
        """設定圖表"""
        plt.style.use(self.STYLE)
        
        # 創建圖形和子圖
        self.fig, self.axes = plt.subplots(num_subplots, 1, figsize=self.FIGURE_SIZE)
        self.fig.suptitle(self.title, fontsize=16)
        
        # 設定第一個子圖 - 音訊波形（統一格式）
        ax_audio = self.axes[0]
        ax_audio.set_title("麥克風音訊波形", fontsize=14)
        ax_audio.set_xlabel("樣本", fontsize=12)
        ax_audio.set_ylabel("振幅", fontsize=12)
        ax_audio.set_ylim(*self.AUDIO_Y_RANGE)
        ax_audio.set_yticks(self.AUDIO_Y_TICKS)
        ax_audio.grid(True, alpha=0.3, color=self.COLORS['grid'])
        
        # 創建音訊線條
        self.lines['audio'], = ax_audio.plot([], [], 
                                             color=self.COLORS['audio'], 
                                             linewidth=1.5, 
                                             alpha=0.8,
                                             label="音訊波形")
        ax_audio.legend(loc='upper right')
        
        # 返回供子類別設定其他子圖
        return self.fig, self.axes
    
    def update_audio_plot(self, audio_data: np.ndarray, ax_index: int = 0):
        """更新音訊波形圖"""
        if audio_data is not None and len(audio_data) > 0:
            x_data = np.arange(len(audio_data))
            self.lines['audio'].set_data(x_data, audio_data)
            self.axes[ax_index].set_xlim(0, len(audio_data))
            
    def add_threshold_line(self, ax_index: int, y_value: float, label: str = "閾值"):
        """添加閾值線"""
        ax = self.axes[ax_index]
        line = ax.axhline(y=y_value, 
                         color=self.COLORS['threshold'], 
                         linestyle='--', 
                         linewidth=2,
                         label=label)
        return line
    
    def add_status_text(self, ax_index: int, x: float = 0.05, y: float = 0.5):
        """添加狀態文字"""
        ax = self.axes[ax_index]
        
        # 嘗試使用標題的字體屬性
        try:
            font_prop = ax.title.get_fontproperties()
        except:
            # 備選方案：明確指定字體
            font_prop = self._get_chinese_font()
        
        text = ax.text(x, y, "", 
                      transform=ax.transAxes,
                      fontsize=11, 
                      verticalalignment='center',
                      fontproperties=font_prop,
                      bbox=dict(boxstyle="round,pad=0.5", 
                               facecolor='black', 
                               alpha=0.7))
        return text
    
    def _get_chinese_font(self):
        """獲取可用的中文字體（備選方案）"""
        from matplotlib import font_manager
        
        # 根據平台選擇字體
        if platform.system() == "Windows":
            font_names = ["Microsoft YaHei", "SimHei", "KaiTi", "FangSong"]
        elif platform.system() == "Darwin":  # macOS
            font_names = ["PingFang SC", "Hiragino Sans GB", "STHeiti"]
        else:  # Linux
            font_names = ["WenQuanYi Micro Hei", "Noto Sans CJK SC", "DejaVu Sans"]
        
        # 尋找可用的字體
        for font_name in font_names:
            try:
                return font_manager.FontProperties(family=font_name)
            except:
                continue
        
        # 返回預設字體
        return font_manager.FontProperties()
    
    def format_chinese_safe(self, text: str) -> str:
        """
        確保中文文字能正確顯示
        如果當前環境無法顯示中文，返回 ASCII 安全的表示
        """
        try:
            # 測試是否能正確編碼/解碼
            text.encode('utf-8').decode('utf-8')
            return text
        except:
            # 如果失敗，使用 Unicode 轉義序列或英文替代
            replacements = {
                '麥克風音訊波形': 'Microphone Audio Waveform',
                '喚醒詞檢測': 'Wake Word Detection',
                '語音檢測': 'Voice Activity Detection',
                '音量級別': 'Volume Level',
                '振幅': 'Amplitude',
                '樣本': 'Samples',
                '時間': 'Time',
                '秒': 's',
                '檢測閾值': 'Detection Threshold',
                '語音機率': 'Speech Probability',
                '檢測置信度': 'Detection Confidence',
                '系統狀態': 'System Status',
                '錄音狀態': 'Recording Status',
                '統計資訊': 'Statistics'
            }
            
            for cn, en in replacements.items():
                text = text.replace(cn, en)
            
            return text
    
    def format_time(self, seconds: float) -> str:
        """格式化時間顯示"""
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        else:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
    
    def create_compact_stats(self, title: str, stats_dict: Dict[str, str], width: int = 50) -> str:
        """創建緊湊的統計顯示（單行格式）"""
        # 構建統計字串
        stats_items = []
        for key, value in stats_dict.items():
            stats_items.append(f"{key}: {value}")
        
        # 用 | 分隔各項
        stats_line = " │ ".join(stats_items)
        
        # 確保不超過寬度
        if len(stats_line) > width - 4:
            stats_line = stats_line[:width - 7] + "..."
            
        return f"[{title}] {stats_line}"
    
    def start_animation(self, update_func, interval: int = 100):
        """啟動動畫"""
        self.is_running = True
        ani = FuncAnimation(self.fig, update_func, interval=interval, blit=False, cache_frame_data=False)
        
        try:
            plt.show()
        except KeyboardInterrupt:
            self.is_running = False
        finally:
            self.is_running = False
            
    def add_data(self, data: Dict[str, Any]):
        """添加數據到佇列"""
        self.data_queue.put(data)
        
    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """獲取最新數據"""
        latest_data = None
        while not self.data_queue.empty():
            try:
                latest_data = self.data_queue.get_nowait()
            except queue.Empty:
                break
        return latest_data


class VADVisualization(BaseVisualization):
    """VAD 專用視覺化"""
    
    def __init__(self):
        super().__init__("VAD 即時監控")
        self.vad_history = []
        self.time_history = []
        self.max_history_points = 200
        
    def setup_plot(self) -> Tuple[plt.Figure, List[plt.Axes]]:
        """設定 VAD 特定的圖表"""
        fig, axes = super().setup_plot(3)
        
        # 第二個子圖 - VAD 狀態
        ax_vad = axes[1]
        ax_vad.set_title("VAD 語音檢測狀態", fontsize=14)
        ax_vad.set_xlabel("時間 (秒)", fontsize=12)
        ax_vad.set_ylabel("語音機率", fontsize=12)
        ax_vad.set_ylim(-0.1, 1.1)
        ax_vad.grid(True, alpha=0.3, color=self.COLORS['grid'])
        
        self.lines['vad'], = ax_vad.plot([], [], 
                                        color=self.COLORS['vad'], 
                                        linewidth=2, 
                                        label="語音機率")
        self.lines['vad_threshold'] = self.add_threshold_line(1, 0.5, "檢測閾值")
        ax_vad.legend(loc='upper right')
        
        # 第三個子圖 - 統計資訊
        ax_stats = axes[2]
        ax_stats.set_title("即時統計資訊", fontsize=14)
        ax_stats.axis('off')
        self.texts['stats'] = self.add_status_text(2, 0.05, 0.5)
        
        plt.tight_layout()
        return fig, axes
        
    def update_vad_plot(self, vad_prob: float, timestamp: float, threshold: float):
        """更新 VAD 圖表"""
        self.vad_history.append(vad_prob)
        self.time_history.append(timestamp)
        
        # 保持歷史記錄長度
        if len(self.vad_history) > self.max_history_points:
            self.vad_history.pop(0)
            self.time_history.pop(0)
            
        # 更新 VAD 線條
        if self.time_history:
            start_time = self.time_history[0]
            relative_times = [t - start_time for t in self.time_history]
            self.lines['vad'].set_data(relative_times, self.vad_history)
            
            # 調整 x 軸範圍
            if relative_times:
                self.axes[1].set_xlim(max(0, relative_times[-1] - 10), relative_times[-1] + 0.5)
                
            # 更新閾值線
            self.lines['vad_threshold'].set_ydata([threshold, threshold])


class WakeWordVisualization(BaseVisualization):
    """喚醒詞專用視覺化"""
    
    def __init__(self):
        super().__init__("喚醒詞檢測監控")
        self.detection_history = []
        self.time_history = []
        self.max_history_points = 200
        
    def setup_plot(self) -> Tuple[plt.Figure, List[plt.Axes]]:
        """設定喚醒詞特定的圖表"""
        fig, axes = super().setup_plot(3)
        
        # 第二個子圖 - 喚醒詞檢測
        ax_wake = axes[1]
        ax_wake.set_title("喚醒詞檢測狀態", fontsize=14)
        ax_wake.set_xlabel("時間 (秒)", fontsize=12)
        ax_wake.set_ylabel("檢測置信度", fontsize=12)
        ax_wake.set_ylim(-0.1, 1.1)
        ax_wake.grid(True, alpha=0.3, color=self.COLORS['grid'])
        
        self.lines['wakeword'], = ax_wake.plot([], [], 
                                              color=self.COLORS['wakeword'], 
                                              linewidth=2, 
                                              label="檢測置信度")
        self.lines['wake_threshold'] = self.add_threshold_line(1, 0.5, "檢測閾值")
        ax_wake.legend(loc='upper right')
        
        # 第三個子圖 - 統計資訊
        ax_stats = axes[2]
        ax_stats.set_title("檢測統計", fontsize=14)
        ax_stats.axis('off')
        self.texts['stats'] = self.add_status_text(2, 0.05, 0.5)
        
        plt.tight_layout()
        return fig, axes


class RecordingVisualization(BaseVisualization):
    """錄音專用視覺化"""
    
    def __init__(self):
        super().__init__("錄音狀態監控")
        # 聲譜圖用
        self.spectrogram_data = []
        self.max_spec_frames = 100  # 最多顯示100幀（約3秒）
        self.sample_rate = 16000
        self.spec_image = None
        
    def setup_plot(self) -> Tuple[plt.Figure, List[plt.Axes]]:
        """設定錄音特定的圖表（兩個子圖版本）"""
        # 只創建兩個子圖
        fig, axes = super().setup_plot(2)
        
        # 調整圖形大小
        fig.set_size_inches(12, 8)
        
        # 第二個子圖 - 聲譜圖
        ax_spec = axes[1]
        ax_spec.set_title("即時聲譜圖 (Spectrogram)", fontsize=14)
        ax_spec.set_xlabel("時間 (秒)", fontsize=12)
        ax_spec.set_ylabel("頻率 (Hz)", fontsize=12)
        
        # 初始化空的聲譜圖
        dummy_data = np.zeros((257, 10))  # 257 是 FFT bins, 10 是時間幀
        
        # 使用更適合語音的配色方案
        # 可選: 'viridis', 'plasma', 'inferno', 'magma', 'turbo', 'jet'
        self.spec_image = ax_spec.imshow(
            dummy_data,
            aspect='auto',
            origin='lower',
            cmap='turbo',  # turbo 配色提供更好的對比度
            extent=[0, 3, 0, 8000],  # 時間0-3秒，頻率0-8000Hz
            interpolation='bilinear'
        )
        
        # 添加顏色條
        cbar = plt.colorbar(self.spec_image, ax=ax_spec)
        cbar.set_label('功率 (dB)', fontsize=10)
        
        ax_spec.set_ylim(0, 8000)  # 只顯示到8kHz
        
        # 在主標題下方添加統計資訊文字
        self.texts['stats'] = fig.text(0.5, 0.94, "[等待錄音]", 
                                       ha='center', 
                                       fontsize=11, 
                                       color='white',
                                       bbox=dict(boxstyle="round,pad=0.5", 
                                                facecolor='black', 
                                                alpha=0.7))
        
        plt.tight_layout(rect=[0, 0, 1, 0.93])  # 留出頂部空間給統計文字
        return fig, axes
    
    def update_spectrogram(self, audio_data: np.ndarray):
        """更新聲譜圖"""
        if audio_data is None or len(audio_data) < 512:
            return
            
        try:
            # 計算短時傅立葉變換 (STFT)
            # 使用較小的窗口以獲得更好的時間解析度
            nperseg = 512  # 窗口大小
            noverlap = 384  # 重疊
            
            frequencies, times, Sxx = signal.spectrogram(
                audio_data, 
                fs=self.sample_rate,
                window='hann',
                nperseg=nperseg,
                noverlap=noverlap,
                mode='magnitude'
            )
            
            # 轉換為 dB
            Sxx_db = 10 * np.log10(Sxx + 1e-10)
            
            # 限制頻率範圍到 8kHz
            freq_mask = frequencies <= 8000
            frequencies = frequencies[freq_mask]
            Sxx_db = Sxx_db[freq_mask, :]
            
            # 添加到歷史數據
            self.spectrogram_data.append(Sxx_db)
            
            # 保持固定長度
            if len(self.spectrogram_data) > self.max_spec_frames:
                self.spectrogram_data.pop(0)
            
            # 合併所有幀
            if self.spectrogram_data:
                combined_spec = np.hstack(self.spectrogram_data)
                
                # 更新圖像數據
                if self.spec_image:
                    self.spec_image.set_data(combined_spec)
                    self.spec_image.set_clim(vmin=-60, vmax=-10)  # 調整動態範圍以提高對比度
                    
                    # 更新時間軸
                    total_frames = combined_spec.shape[1]
                    time_per_frame = len(audio_data) / self.sample_rate / Sxx_db.shape[1]
                    total_time = total_frames * time_per_frame
                    self.spec_image.set_extent([0, total_time, 0, 8000])
                    
                    # 更新 x 軸範圍
                    if hasattr(self, 'axes') and len(self.axes) > 1:
                        self.axes[1].set_xlim(0, total_time)
                        
        except Exception as e:
            print(f"聲譜圖更新錯誤: {e}")


class PipelineVisualization(BaseVisualization):
    """Pipeline 整合視覺化（多個操作器）"""
    
    def __init__(self):
        super().__init__("Pipeline 整合監控")
        self.wakeword_history = []
        self.vad_history = []
        self.time_history = []
        self.max_history_points = 200
        
    def setup_plot(self) -> Tuple[plt.Figure, List[plt.Axes]]:
        """設定 Pipeline 特定的圖表（4個子圖）"""
        plt.style.use(self.STYLE)
        
        # 創建 4 個子圖
        self.fig, self.axes = plt.subplots(4, 1, figsize=(12, 12))
        self.fig.suptitle(self.title, fontsize=16)
        
        # 第一個子圖 - 音訊波形（使用基礎類別設定）
        ax_audio = self.axes[0]
        ax_audio.set_title("麥克風音訊波形", fontsize=14)
        ax_audio.set_xlabel("樣本", fontsize=12)
        ax_audio.set_ylabel("振幅", fontsize=12)
        ax_audio.set_ylim(*self.AUDIO_Y_RANGE)
        ax_audio.set_yticks(self.AUDIO_Y_TICKS)
        ax_audio.grid(True, alpha=0.3, color=self.COLORS['grid'])
        
        self.lines['audio'], = ax_audio.plot([], [], 
                                             color=self.COLORS['audio'], 
                                             linewidth=1.5, 
                                             alpha=0.8,
                                             label="音訊波形")
        ax_audio.legend(loc='upper right')
        
        # 第二個子圖 - 喚醒詞檢測
        ax_wake = self.axes[1]
        ax_wake.set_title("喚醒詞檢測", fontsize=14)
        ax_wake.set_xlabel("時間 (秒)", fontsize=12)
        ax_wake.set_ylabel("檢測分數", fontsize=12)
        ax_wake.set_ylim(-0.1, 1.1)
        ax_wake.grid(True, alpha=0.3, color=self.COLORS['grid'])
        
        self.lines['wakeword'], = ax_wake.plot([], [], 
                                              color=self.COLORS['wakeword'], 
                                              linewidth=2, 
                                              label="喚醒詞分數")
        self.lines['wake_threshold'] = ax_wake.axhline(y=0.5, 
                                                       color=self.COLORS['threshold'], 
                                                       linestyle='--', 
                                                       label="喚醒閾值")
        ax_wake.legend(loc='upper right')
        
        # 第三個子圖 - VAD 狀態
        ax_vad = self.axes[2]
        ax_vad.set_title("VAD 語音檢測", fontsize=14)
        ax_vad.set_xlabel("時間 (秒)", fontsize=12)
        ax_vad.set_ylabel("語音機率", fontsize=12)
        ax_vad.set_ylim(-0.1, 1.1)
        ax_vad.grid(True, alpha=0.3, color=self.COLORS['grid'])
        
        self.lines['vad'], = ax_vad.plot([], [], 
                                        color=self.COLORS['vad'], 
                                        linewidth=2, 
                                        label="語音機率")
        self.lines['vad_threshold'] = ax_vad.axhline(y=0.3, 
                                                     color=self.COLORS['threshold'], 
                                                     linestyle='--', 
                                                     label="VAD閾值")
        ax_vad.legend(loc='upper right')
        
        # 第四個子圖 - 系統狀態
        ax_stats = self.axes[3]
        ax_stats.set_title("系統狀態", fontsize=14)
        ax_stats.axis('off')
        self.texts['stats'] = self.add_status_text(3, 0.05, 0.5)
        
        plt.tight_layout()
        return self.fig, self.axes
        
    def update_pipeline_plots(self, wake_score: float, vad_prob: float, 
                            timestamp: float, wake_threshold: float, vad_threshold: float):
        """更新 Pipeline 圖表"""
        # 添加到歷史記錄
        self.wakeword_history.append(wake_score)
        self.vad_history.append(vad_prob)
        self.time_history.append(timestamp)
        
        # 保持歷史記錄長度
        if len(self.wakeword_history) > self.max_history_points:
            self.wakeword_history.pop(0)
            self.vad_history.pop(0)
            self.time_history.pop(0)
            
        # 更新圖表
        if self.time_history:
            start_time = self.time_history[0]
            relative_times = [t - start_time for t in self.time_history]
            
            # 更新喚醒詞線條
            self.lines['wakeword'].set_data(relative_times, self.wakeword_history)
            # 更新 VAD 線條
            self.lines['vad'].set_data(relative_times, self.vad_history)
            
            # 調整 x 軸範圍
            if relative_times:
                x_max = relative_times[-1] + 0.5
                x_min = max(0, relative_times[-1] - 10)
                self.axes[1].set_xlim(x_min, x_max)
                self.axes[2].set_xlim(x_min, x_max)
                
            # 更新閾值線
            self.lines['wake_threshold'].set_ydata([wake_threshold, wake_threshold])
            self.lines['vad_threshold'].set_ydata([vad_threshold, vad_threshold])