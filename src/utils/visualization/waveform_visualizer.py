"""波形視覺化主控制器

組合不同的視覺化面板，提供完整的音訊視覺化介面。
"""

import time
import threading
from typing import Optional, Dict, Any, Callable
import numpy as np
import gradio as gr

from .base import VisualizationPanel
from .panels import (
    RealtimeWaveformPanel,
    HistoryTimelinePanel,
    VADDetectorPanel,
    WakewordTriggerPanel,
    EnergySpectrumPanel
)
from src.service.microphone_capture import microphone_service
from src.utils.logger import logger


class WaveformVisualizer:
    """波形視覺化控制器。
    
    整合多個視覺化面板，提供完整的音訊分析介面。
    支援模組化設計，可以動態切換下半部面板。
    """
    
    def __init__(self, sample_rate: int = 16000):
        """初始化視覺化器。
        
        Args:
            sample_rate: 音訊取樣率
        """
        self.sample_rate = sample_rate
        
        # 上半部：固定為即時波形
        self.upper_panel = RealtimeWaveformPanel(
            duration=5.0,
            sample_rate=sample_rate
        )
        
        # 下半部：可切換的面板
        self.lower_panel = None
        self.available_panels = {
            'history': HistoryTimelinePanel(),
            'vad': VADDetectorPanel(),
            'wakeword': WakewordTriggerPanel(),
            'spectrum': EnergySpectrumPanel()
        }
        
        # 預設使用歷史面板
        self.set_lower_panel('history')
        
        # 控制狀態
        self._is_running = False
        self._update_thread = None
        self._audio_callback = None
        
        # Gradio 介面
        self.interface = None
        
    def set_lower_panel(self, panel_type: str):
        """設定下半部面板。
        
        Args:
            panel_type: 面板類型 ('history', 'vad', 'wakeword', 'spectrum')
        """
        if panel_type in self.available_panels:
            self.lower_panel = self.available_panels[panel_type]
            logger.info(f"Lower panel set to: {panel_type}")
        else:
            logger.warning(f"Unknown panel type: {panel_type}")
    
    def set_audio_callback(self, callback: Callable):
        """設定音訊處理回調。
        
        Args:
            callback: 處理音訊的回調函數
        """
        self._audio_callback = callback
    
    def update_audio(self, chunk):
        """更新音訊資料。
        
        Args:
            chunk: AudioChunk 物件
        """
        if hasattr(self.upper_panel, 'update'):
            self.upper_panel.update(chunk)
        if hasattr(self.lower_panel, 'update'):
            self.lower_panel.update(chunk)
    
    def update_vad_state(self, is_active: bool):
        """更新 VAD 狀態。
        
        Args:
            is_active: 是否偵測到語音
        """
        if isinstance(self.lower_panel, VADDetectorPanel):
            self.lower_panel.update(vad_active=is_active)
    
    def update_wakeword_detection(self, confidence: float):
        """更新喚醒詞偵測結果。
        
        Args:
            confidence: 偵測信心分數
        """
        if isinstance(self.lower_panel, WakewordTriggerPanel):
            self.lower_panel.update(detection_score=confidence)
    
    def create_interface(self) -> gr.Blocks:
        """創建 Gradio 介面。
        
        Returns:
            Gradio Blocks 實例
        """
        with gr.Blocks(title="ASR Hub Audio Visualizer") as interface:
            gr.Markdown("# 🎙️ ASR Hub Audio Visualizer")
            
            with gr.Row():
                # 控制按鈕
                with gr.Column(scale=1):
                    gr.Markdown("## Controls")
                    
                    # 麥克風控制
                    start_btn = gr.Button("▶️ Start Capture", variant="primary")
                    stop_btn = gr.Button("⏹️ Stop Capture", variant="stop")
                    clear_btn = gr.Button("🗑️ Clear Display")
                    
                    # 面板選擇
                    gr.Markdown("### Lower Panel")
                    panel_selector = gr.Radio(
                        choices=['history', 'vad', 'wakeword', 'spectrum'],
                        value='history',
                        label="Panel Type"
                    )
                    
                    # 音訊參數
                    gr.Markdown("### Audio Settings")
                    sample_rate_input = gr.Number(
                        value=self.sample_rate,
                        label="Sample Rate (Hz)"
                    )
                    
                    # 狀態顯示
                    status_text = gr.Textbox(
                        value="Ready",
                        label="Status",
                        interactive=False
                    )
                
                # 視覺化面板
                with gr.Column(scale=3):
                    gr.Markdown("## Visualization")
                    
                    # 上半部：即時波形
                    upper_plot = self.upper_panel.create_component()
                    
                    # 下半部：可切換面板
                    lower_plot = self.lower_panel.create_component()
                    
                    # 統計資訊
                    with gr.Row():
                        stats_text = gr.Textbox(
                            value="No data",
                            label="Statistics",
                            interactive=False
                        )
            
            # 定義更新函數（用於 Timer）
            def update_visualization():
                """更新視覺化顯示。"""
                if not self._is_running:
                    return self.upper_panel.update(None), self.lower_panel.update(None), "No data", "⚫ Stopped"
                
                try:
                    # 讀取音訊資料
                    audio_chunk = microphone_service.read_chunk()
                    
                    # 更新上半部波形
                    upper_fig = self.upper_panel.update(audio_chunk)
                    
                    # 更新下半部（根據面板類型）
                    if isinstance(self.lower_panel, HistoryTimelinePanel):
                        # 歷史面板：添加段落（示例）
                        lower_fig = self.lower_panel.update()
                    elif isinstance(self.lower_panel, VADDetectorPanel):
                        # VAD 面板：計算 VAD 分數
                        if audio_chunk is not None:
                            vad_score = np.abs(audio_chunk).mean() * 2  # 簡單的能量計算
                            lower_fig = self.lower_panel.update(vad_score)
                        else:
                            lower_fig = self.lower_panel.update()
                    elif isinstance(self.lower_panel, WakewordTriggerPanel):
                        # 喚醒詞面板
                        lower_fig = self.lower_panel.update()
                    elif isinstance(self.lower_panel, EnergySpectrumPanel):
                        # 頻譜面板
                        lower_fig = self.lower_panel.update(audio_chunk, self.sample_rate)
                    else:
                        lower_fig = self.lower_panel.update()
                    
                    # 計算統計
                    if audio_chunk is not None:
                        rms = np.sqrt(np.mean(audio_chunk**2))
                        peak = np.max(np.abs(audio_chunk))
                        stats = f"RMS: {rms:.4f} | Peak: {peak:.4f}"
                    else:
                        stats = "No data"
                    
                    return upper_fig, lower_fig, stats, "🔴 Capturing..."
                    
                except Exception as e:
                    logger.error(f"Visualization update error: {e}")
                    return None, None, "Error", str(e)
            
            # 事件處理
            def start_capture():
                """開始擷取音訊。"""
                self._is_running = True
                
                # 設定麥克風參數
                microphone_service.set_parameters(
                    sample_rate=self.sample_rate,
                    channels=1,
                    chunk_size=1024
                )
                
                # 開始擷取
                microphone_service.start_capture(callback=self._audio_callback)
                
                # 返回初始狀態
                return self.upper_panel.update(None), self.lower_panel.update(None), "Starting...", "🔴 Starting..."
            
            def stop_capture():
                """停止擷取音訊。"""
                self._is_running = False
                microphone_service.stop_capture()
                return "⚫ Stopped"  # 返回單一值給 status_text
            
            def clear_display():
                """清空顯示。"""
                self.upper_panel.clear()
                self.lower_panel.clear()
                upper_fig = self.upper_panel.update(None)
                lower_fig = self.lower_panel.update(None)
                return upper_fig, lower_fig, "Cleared"
            
            def change_panel(panel_type):
                """切換下半部面板。"""
                self.set_lower_panel(panel_type)
                return self.lower_panel.update()
            
            # 綁定事件
            start_output = start_btn.click(
                fn=start_capture,
                inputs=[],
                outputs=[upper_plot, lower_plot, stats_text, status_text]
            )
            
            stop_btn.click(
                fn=stop_capture,
                inputs=[],
                outputs=[status_text],
                cancels=[start_output]
            )
            
            clear_btn.click(
                fn=clear_display,
                inputs=[],
                outputs=[upper_plot, lower_plot, status_text]
            )
            
            panel_selector.change(
                fn=change_panel,
                inputs=[panel_selector],
                outputs=[lower_plot]
            )
            
            sample_rate_input.change(
                fn=lambda sr: setattr(self, 'sample_rate', int(sr)),
                inputs=[sample_rate_input],
                outputs=[]
            )
            
            # 添加 Timer 進行定期更新（每 100ms）
            timer = gr.Timer(0.1)
            timer.tick(
                fn=update_visualization,
                inputs=[],
                outputs=[upper_plot, lower_plot, stats_text, status_text]
            )
        
        self.interface = interface
        return interface
    
    def launch(self, **kwargs):
        """啟動 Gradio 介面。
        
        Args:
            **kwargs: 傳遞給 gradio.launch() 的參數
        """
        if self.interface is None:
            self.create_interface()
        
        # 預設參數
        launch_kwargs = {
            'server_name': '127.0.0.1',  # 使用 localhost 而不是 0.0.0.0
            'server_port': 7860,
            'share': False,
            'inbrowser': True
        }
        launch_kwargs.update(kwargs)
        
        # 處理顯示的 URL
        display_host = 'localhost' if launch_kwargs['server_name'] in ['0.0.0.0', '127.0.0.1'] else launch_kwargs['server_name']
        logger.info(f"Launching visualizer at http://{display_host}:{launch_kwargs['server_port']}")
        self.interface.launch(**launch_kwargs)
    
    def close(self):
        """關閉視覺化器。"""
        if self._is_running:
            self.stop_capture()
        
        if self.interface:
            self.interface.close()