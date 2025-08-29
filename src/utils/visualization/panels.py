"""視覺化面板實現

各種可替換的視覺化面板模組。
"""

import time
from typing import Any, Optional, List, Tuple
import numpy as np
import gradio as gr
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.animation as animation
from collections import deque

from .base import VisualizationPanel


class RealtimeWaveformPanel(VisualizationPanel):
    """即時波形面板。
    
    顯示麥克風即時音訊波形。
    """
    
    def __init__(self, duration: float = 5.0, sample_rate: int = 16000):
        """初始化即時波形面板。
        
        Args:
            duration: 顯示的時間長度（秒）
            sample_rate: 取樣率
        """
        super().__init__(title="Realtime Waveform")
        self.duration = duration
        self.sample_rate = sample_rate
        self.samples_to_show = int(duration * sample_rate)
        
        # 初始化資料緩衝
        self.waveform_data = deque(maxlen=self.samples_to_show)
        self.waveform_data.extend([0] * self.samples_to_show)
        
    def create_component(self) -> gr.Plot:
        """創建 Gradio Plot 組件。"""
        return gr.Plot(label=self.title, show_label=True)
    
    def update(self, audio_data: Optional[np.ndarray]) -> Figure:
        """更新波形顯示。
        
        Args:
            audio_data: 音訊資料 numpy array 或 AudioChunk
            
        Returns:
            matplotlib Figure
        """
        fig = plt.figure(figsize=(12, 3))
        ax = fig.add_subplot(111)
        
        if audio_data is not None:
            # 處理 AudioChunk 或 numpy array
            if hasattr(audio_data, 'to_numpy'):
                # AudioChunk 物件
                audio_array = audio_data.to_numpy()
            else:
                # numpy array
                audio_array = audio_data
            
            # 更新緩衝區
            self.waveform_data.extend(audio_array.flatten())
            
        # 繪製波形
        waveform = np.array(self.waveform_data)
        time_axis = np.linspace(0, self.duration, len(waveform))
        
        ax.plot(time_axis, waveform, color='#2E86AB', linewidth=0.5)
        ax.fill_between(time_axis, waveform, 0, alpha=0.3, color='#A23B72')
        
        # 設定軸標籤和範圍
        ax.set_xlabel('Time (seconds)')
        ax.set_ylabel('Amplitude')
        ax.set_ylim([-1, 1])
        ax.set_xlim([0, self.duration])
        ax.grid(True, alpha=0.3)
        ax.set_title(f'{self.title} - Sample Rate: {self.sample_rate} Hz')
        
        plt.tight_layout()
        return fig
    
    def clear(self):
        """清空波形資料。"""
        self.waveform_data.clear()
        self.waveform_data.extend([0] * self.samples_to_show)


class HistoryTimelinePanel(VisualizationPanel):
    """歷史時間軸面板。
    
    顯示錄音歷史的時間軸視圖。
    """
    
    def __init__(self, max_segments: int = 10):
        """初始化歷史時間軸面板。
        
        Args:
            max_segments: 最大顯示段數
        """
        super().__init__(title="Recording History")
        self.max_segments = max_segments
        self.segments = []  # [(start_time, end_time, session_id, amplitude_data)]
        
    def create_component(self) -> gr.Plot:
        """創建 Gradio Plot 組件。"""
        return gr.Plot(label=self.title, show_label=True)
    
    def add_segment(self, start_time: float, end_time: float, 
                   session_id: str, audio_data: Optional[np.ndarray] = None):
        """添加一個錄音段。
        
        Args:
            start_time: 開始時間（時間戳）
            end_time: 結束時間（時間戳）
            session_id: Session ID
            audio_data: 音訊資料（可選）
        """
        # 計算振幅摘要
        if audio_data is not None:
            # 降採樣到固定點數以便顯示
            points = 1000
            if len(audio_data) > points:
                indices = np.linspace(0, len(audio_data) - 1, points, dtype=int)
                amplitude = audio_data[indices]
            else:
                amplitude = audio_data
        else:
            amplitude = None
            
        self.segments.append({
            'start': start_time,
            'end': end_time,
            'session_id': session_id,
            'amplitude': amplitude
        })
        
        # 限制段數
        if len(self.segments) > self.max_segments:
            self.segments = self.segments[-self.max_segments:]
    
    def update(self, new_segment: Optional[dict] = None) -> Figure:
        """更新時間軸顯示。
        
        Args:
            new_segment: 新的段資訊
            
        Returns:
            matplotlib Figure
        """
        if new_segment:
            self.add_segment(**new_segment)
            
        fig = plt.figure(figsize=(12, 3))
        ax = fig.add_subplot(111)
        
        if not self.segments:
            ax.text(0.5, 0.5, 'No recordings yet', 
                   ha='center', va='center', fontsize=12, color='gray')
            ax.set_xlim([0, 1])
            ax.set_ylim([0, 1])
        else:
            # 找出時間範圍
            all_times = []
            for seg in self.segments:
                all_times.extend([seg['start'], seg['end']])
            
            min_time = min(all_times)
            max_time = max(all_times)
            time_range = max_time - min_time if max_time > min_time else 1
            
            # 繪製每個段
            for i, seg in enumerate(self.segments):
                y_pos = i * 0.1
                start_norm = (seg['start'] - min_time) / time_range
                duration = (seg['end'] - seg['start']) / time_range
                
                # 繪製段矩形
                rect = plt.Rectangle((start_norm, y_pos), duration, 0.08,
                                    facecolor='#4ECDC4', edgecolor='#2E86AB',
                                    alpha=0.7)
                ax.add_patch(rect)
                
                # 添加標籤
                label = f"{seg['session_id'][:8]}"
                ax.text(start_norm + duration/2, y_pos + 0.04, label,
                       ha='center', va='center', fontsize=8)
                
                # 如果有振幅資料，在矩形內繪製迷你波形
                if seg['amplitude'] is not None:
                    amp = seg['amplitude']
                    x = np.linspace(start_norm, start_norm + duration, len(amp))
                    y = y_pos + 0.04 + amp * 0.03
                    ax.plot(x, y, color='#2E86AB', linewidth=0.5, alpha=0.5)
            
            ax.set_xlim([0, 1])
            ax.set_ylim([-0.1, self.max_segments * 0.1])
            
            # 添加時間標籤
            ax.set_xlabel('Time')
            ax.set_yticks([])
            
        ax.set_title(self.title)
        ax.grid(True, alpha=0.3, axis='x')
        
        plt.tight_layout()
        return fig
    
    def clear(self):
        """清空歷史記錄。"""
        self.segments.clear()


class VADDetectorPanel(VisualizationPanel):
    """VAD 檢測面板。
    
    顯示語音活動檢測結果和閾值。
    """
    
    def __init__(self, threshold: float = 0.5):
        """初始化 VAD 檢測面板。
        
        Args:
            threshold: VAD 閾值
        """
        super().__init__(title="Voice Activity Detection")
        self.threshold = threshold
        self.vad_scores = deque(maxlen=200)  # 保存最近的 VAD 分數
        self.is_speech = deque(maxlen=200)   # 保存語音檢測結果
        
    def create_component(self) -> gr.Plot:
        """創建 Gradio Plot 組件。"""
        return gr.Plot(label=self.title, show_label=True)
    
    def update(self, vad_score: Optional[float] = None) -> Figure:
        """更新 VAD 顯示。
        
        Args:
            vad_score: VAD 分數 (0-1)
            
        Returns:
            matplotlib Figure
        """
        if vad_score is not None:
            self.vad_scores.append(vad_score)
            self.is_speech.append(vad_score > self.threshold)
        
        fig = plt.figure(figsize=(12, 3))
        ax = fig.add_subplot(111)
        
        if len(self.vad_scores) > 0:
            x = np.arange(len(self.vad_scores))
            scores = np.array(self.vad_scores)
            speech = np.array(self.is_speech)
            
            # 繪製 VAD 分數
            ax.plot(x, scores, color='#2E86AB', linewidth=2, label='VAD Score')
            
            # 繪製閾值線
            ax.axhline(y=self.threshold, color='red', linestyle='--', 
                      linewidth=1, label=f'Threshold ({self.threshold})')
            
            # 填充語音區域
            ax.fill_between(x, 0, 1, where=speech, 
                           color='green', alpha=0.2, label='Speech Detected')
            
            ax.set_xlim([0, 200])
            ax.set_ylim([0, 1])
        else:
            ax.text(0.5, 0.5, 'Waiting for audio...', 
                   ha='center', va='center', fontsize=12, color='gray')
            ax.set_xlim([0, 200])
            ax.set_ylim([0, 1])
        
        ax.set_xlabel('Time (frames)')
        ax.set_ylabel('VAD Score')
        ax.set_title(self.title)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    def set_threshold(self, threshold: float):
        """設定 VAD 閾值。
        
        Args:
            threshold: 新的閾值
        """
        self.threshold = threshold
    
    def clear(self):
        """清空 VAD 資料。"""
        self.vad_scores.clear()
        self.is_speech.clear()


class WakewordTriggerPanel(VisualizationPanel):
    """喚醒詞觸發面板。
    
    顯示喚醒詞檢測結果。
    """
    
    def __init__(self, keywords: List[str] = None):
        """初始化喚醒詞面板。
        
        Args:
            keywords: 喚醒詞列表
        """
        super().__init__(title="Wakeword Detection")
        self.keywords = keywords or ["hi kumu", "hey assistant"]
        self.detection_history = deque(maxlen=100)
        self.confidence_history = {kw: deque(maxlen=100) for kw in self.keywords}
        
    def create_component(self) -> gr.Plot:
        """創建 Gradio Plot 組件。"""
        return gr.Plot(label=self.title, show_label=True)
    
    def update(self, detection_result: Optional[dict] = None) -> Figure:
        """更新喚醒詞顯示。
        
        Args:
            detection_result: 檢測結果 {'keyword': str, 'confidence': float, 'timestamp': float}
            
        Returns:
            matplotlib Figure
        """
        if detection_result:
            self.detection_history.append(detection_result)
            keyword = detection_result.get('keyword')
            confidence = detection_result.get('confidence', 0)
            
            if keyword in self.confidence_history:
                self.confidence_history[keyword].append(confidence)
        
        # 為所有關鍵詞填充資料
        for kw in self.keywords:
            if kw not in self.confidence_history:
                self.confidence_history[kw] = deque(maxlen=100)
            
            # 如果沒有新資料，添加 0
            if detection_result is None or detection_result.get('keyword') != kw:
                self.confidence_history[kw].append(0)
        
        fig = plt.figure(figsize=(12, 3))
        ax = fig.add_subplot(111)
        
        # 繪製每個關鍵詞的置信度
        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
        for i, keyword in enumerate(self.keywords):
            if len(self.confidence_history[keyword]) > 0:
                scores = np.array(self.confidence_history[keyword])
                x = np.arange(len(scores))
                color = colors[i % len(colors)]
                ax.plot(x, scores, linewidth=2, label=keyword, color=color)
                
                # 標記觸發點
                triggers = scores > 0.5
                if np.any(triggers):
                    trigger_x = x[triggers]
                    trigger_y = scores[triggers]
                    ax.scatter(trigger_x, trigger_y, color=color, s=100, 
                             marker='o', zorder=5, edgecolors='white', linewidth=2)
        
        ax.set_xlim([0, 100])
        ax.set_ylim([0, 1])
        ax.set_xlabel('Time (frames)')
        ax.set_ylabel('Confidence')
        ax.set_title(self.title)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
        # 添加觸發線
        ax.axhline(y=0.5, color='red', linestyle='--', linewidth=1, alpha=0.5)
        
        plt.tight_layout()
        return fig
    
    def clear(self):
        """清空檢測歷史。"""
        self.detection_history.clear()
        for kw in self.confidence_history:
            self.confidence_history[kw].clear()


class EnergySpectrumPanel(VisualizationPanel):
    """能量頻譜面板。
    
    顯示音訊的頻譜分析。
    """
    
    def __init__(self, fft_size: int = 512):
        """初始化能量頻譜面板。
        
        Args:
            fft_size: FFT 大小
        """
        super().__init__(title="Energy Spectrum")
        self.fft_size = fft_size
        self.spectrum_history = deque(maxlen=100)
        
    def create_component(self) -> gr.Plot:
        """創建 Gradio Plot 組件。"""
        return gr.Plot(label=self.title, show_label=True)
    
    def update(self, audio_data: Optional[np.ndarray] = None, 
              sample_rate: int = 16000) -> Figure:
        """更新頻譜顯示。
        
        Args:
            audio_data: 音訊資料
            sample_rate: 取樣率
            
        Returns:
            matplotlib Figure
        """
        fig = plt.figure(figsize=(12, 3))
        ax = fig.add_subplot(111)
        
        if audio_data is not None and len(audio_data) > 0:
            # 計算 FFT
            fft = np.fft.rfft(audio_data[:self.fft_size], n=self.fft_size)
            magnitude = np.abs(fft)
            
            # 轉換為 dB
            magnitude_db = 20 * np.log10(magnitude + 1e-10)
            
            # 保存到歷史
            self.spectrum_history.append(magnitude_db)
            
            # 頻率軸
            freqs = np.fft.rfftfreq(self.fft_size, 1/sample_rate)
            
            # 繪製當前頻譜
            ax.plot(freqs, magnitude_db, color='#2E86AB', linewidth=1.5)
            ax.fill_between(freqs, magnitude_db, -100, alpha=0.3, color='#A23B72')
            
            ax.set_xlim([0, sample_rate/2])
            ax.set_ylim([-80, 20])
            ax.set_xlabel('Frequency (Hz)')
            ax.set_ylabel('Magnitude (dB)')
        else:
            ax.text(0.5, 0.5, 'Waiting for audio...', 
                   ha='center', va='center', fontsize=12, color='gray')
            ax.set_xlim([0, 8000])
            ax.set_ylim([-80, 20])
        
        ax.set_title(self.title)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    def clear(self):
        """清空頻譜歷史。"""
        self.spectrum_history.clear()