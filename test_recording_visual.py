#!/usr/bin/env python3
"""
視覺化錄音功能測試
專注測試 RecordingOperator 並顯示即時聲波圖
"""

import asyncio
import sys
import os
import time
import numpy as np
import pyaudio
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from pathlib import Path

# 設置 matplotlib 支持中文
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Noto Sans CJK TC', 'WenQuanYi Micro Hei', 'Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
from collections import deque
from typing import Optional

# 添加 src 到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline.operators.recording import RecordingOperator
from src.utils.logger import logger
from src.pipeline.operators.audio_format.scipy_operator import ScipyAudioFormatOperator
from src.models.audio_format import AudioMetadata, AudioFormat



class RecordingVisualTester:
    """視覺化錄音測試器"""
    
    def __init__(self):
        # RecordingOperator 會從 ConfigManager 讀取配置
        self.recording_operator = None
        
        # 音訊格式轉換器
        # Recording 需要的格式
        self.recording_format = AudioMetadata(
            sample_rate=16000,
            channels=1,
            format=AudioFormat.INT16
        )
        self.format_converter = None  # 將在 setup 中初始化
        
        # PyAudio
        self.p = pyaudio.PyAudio()
        
        # 檢測預設設備的採樣率
        try:
            device_info = self.p.get_default_input_device_info()
            self.device_sample_rate = int(device_info['defaultSampleRate'])
            logger.info(f"預設麥克風採樣率: {self.device_sample_rate} Hz")
        except:
            self.device_sample_rate = 16000
            logger.warning("無法獲取設備資訊，假設採樣率為 16000 Hz")
            
        # 音訊參數
        self.target_sample_rate = 16000  # RecordingOperator 期望的採樣率
        self.channels = 1
        self.chunk_size = 1024
        self.format = pyaudio.paInt16
        
        # 計算麥克風的 chunk 大小（考慮採樣率差異）
        self.mic_chunk_size = int(self.chunk_size * self.device_sample_rate / self.target_sample_rate)
        logger.info(f"音訊參數: Recording chunk_size={self.chunk_size}, 麥克風 chunk_size={self.mic_chunk_size}")
        
        # 音訊流
        self.stream = None
        self.is_recording = False
        
        # 視覺化相關
        self.fig = None
        self.ax_waveform = None
        self.ax_volume = None
        self.line_waveform = None
        self.line_volume = None
        self.bar_volume = None
        
        # 資料緩衝
        self.waveform_buffer = deque(maxlen=int(self.target_sample_rate * 2))  # 2秒的波形
        self.volume_history = deque(maxlen=100)  # 音量歷史
        self.time_history = deque(maxlen=100)
        
    async def setup(self):
        """設定測試環境"""
        logger.info("設定錄音測試環境...")
        
        # 創建測試目錄
        Path('test_recordings').mkdir(exist_ok=True)
        
        # 初始化格式轉換器（如果需要重採樣）
        if self.device_sample_rate != self.target_sample_rate:
            # 設備音訊格式
            self.device_format = AudioMetadata(
                sample_rate=self.device_sample_rate,
                channels=self.channels,
                format=AudioFormat.INT16
            )
            self.format_converter = ScipyAudioFormatOperator(
                operator_id='recording_converter',
                target_metadata=self.recording_format
            )
            await self.format_converter.start()
            logger.info(f"音訊格式轉換器已初始化: {self.device_sample_rate}Hz -> {self.target_sample_rate}Hz")
        
        # 初始化 RecordingOperator
        self.recording_operator = RecordingOperator()
        
        # 強制設定為檔案儲存模式（測試用）
        self.recording_operator.storage_type = 'file'
        self.recording_operator.storage_path = Path('test_recordings')
        
        await self.recording_operator.start()  # 使用 start() 而不是 initialize()
        
        logger.info("✓ 測試環境設定完成")
    
    async def cleanup(self):
        """清理測試環境"""
        logger.info("清理測試環境...")
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.recording_operator:
            await self.recording_operator.stop()  # 使用 stop() 而不是 cleanup()
        
        if self.format_converter:
            await self.format_converter.stop()
        
        self.p.terminate()
        
        logger.info("✓ 測試環境清理完成")
    
    def setup_visualization(self):
        """設定視覺化圖表"""
        # 設定圖表樣式
        plt.style.use('dark_background')
        
        # 創建圖表
        self.fig, (self.ax_waveform, self.ax_volume) = plt.subplots(
            2, 1, 
            figsize=(12, 8),
            gridspec_kw={'height_ratios': [3, 1]}
        )
        
        # 設定波形圖
        self.ax_waveform.set_title('Real-time Audio Waveform', fontsize=16, pad=10)
        self.ax_waveform.set_xlabel('Time (seconds)')
        self.ax_waveform.set_ylabel('Amplitude')
        self.ax_waveform.set_ylim(-32768, 32767)
        self.ax_waveform.grid(True, alpha=0.3)
        
        # 初始化波形線
        x_data = np.linspace(0, 2, len(self.waveform_buffer)) if self.waveform_buffer else [0]
        y_data = list(self.waveform_buffer) if self.waveform_buffer else [0]
        self.line_waveform, = self.ax_waveform.plot(x_data, y_data, color='cyan', linewidth=0.5)
        
        # 設定音量圖
        self.ax_volume.set_title('Volume History', fontsize=14, pad=5)
        self.ax_volume.set_xlabel('Time (seconds)')
        self.ax_volume.set_ylabel('Volume (dB)')
        self.ax_volume.set_ylim(-60, 0)
        self.ax_volume.grid(True, alpha=0.3)
        
        # 初始化音量線
        self.line_volume, = self.ax_volume.plot([], [], color='lime', linewidth=2)
        
        # 添加音量條
        self.bar_volume = self.ax_volume.axhspan(-60, -60, alpha=0.3, color='green')
        
        # 調整布局
        plt.tight_layout()
        
        # 設定窗口標題
        self.fig.canvas.manager.set_window_title('ASRHub Recording Visualization Test')
    
    def update_visualization(self, audio_data):
        """更新視覺化資料"""
        # 轉換為 numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        
        # 計算音訊能量（用於調試）
        audio_energy = np.abs(audio_np).mean()
        
        # 更新波形緩衝
        self.waveform_buffer.extend(audio_np)
        
        # 計算音量 (dB)
        if len(audio_np) > 0:
            rms = np.sqrt(np.mean(audio_np.astype(float) ** 2))
            volume_db = 20 * np.log10(max(rms, 1)) - 60  # 歸一化到 -60 到 0 dB
        else:
            volume_db = -60
        
        # 更新音量歷史
        current_time = time.time()
        self.volume_history.append(volume_db)
        self.time_history.append(current_time)
        
        # 更新波形圖
        if len(self.waveform_buffer) > 0:
            x_data = np.linspace(0, len(self.waveform_buffer) / self.target_sample_rate, 
                               len(self.waveform_buffer))
            self.line_waveform.set_data(x_data, list(self.waveform_buffer))
            self.ax_waveform.set_xlim(0, max(2, x_data[-1]))
        
        # 更新音量圖
        if len(self.time_history) > 1:
            # 轉換為相對時間
            times = np.array(self.time_history) - self.time_history[0]
            volumes = list(self.volume_history)
            
            self.line_volume.set_data(times, volumes)
            self.ax_volume.set_xlim(max(0, times[-1] - 10), times[-1] + 0.5)
            
            # 更新音量條
            self.bar_volume.remove()
            bar_color = 'red' if volume_db > -20 else 'yellow' if volume_db > -40 else 'green'
            self.bar_volume = self.ax_volume.axhspan(
                -60, volume_db, 
                alpha=0.3, 
                color=bar_color
            )
        
        # 更新錄音資訊
        recording_info = self.recording_operator.get_info() if hasattr(self.recording_operator, 'get_info') else self.recording_operator.get_recording_info()
        if recording_info.get('is_recording', False):
            status_text = (
                f"[Recording] | "
                f"Duration: {recording_info.get('duration', 0):.1f}s | "
                f"Size: {recording_info.get('bytes_recorded', 0) / 1024:.1f} KB | "
                f"Volume: {volume_db:.1f} dB"
            )
        else:
            status_text = "[Recording Stopped]"
        
        self.fig.suptitle(status_text, fontsize=12, y=0.98)
        
        # 重繪圖表
        self.fig.canvas.draw_idle()
    
    async def test_visual_recording(self, duration: float = 10.0):
        """視覺化錄音測試"""
        logger.info(f"\n{'='*60}")
        logger.info(f"視覺化錄音測試 ({duration} 秒)")
        logger.info(f"{'='*60}")
        
        session_id = f"visual_{int(time.time())}"
        
        # 設定視覺化
        self.setup_visualization()
        
        # 開始錄音
        await self.recording_operator.start_recording(session_id)
        logger.info(f"錄音開始 (session_id: {session_id})")
        
        # 開啟麥克風（使用設備實際參數）
        logger.info(f"開啟音訊流: format={self.format}, channels={self.channels}, rate={self.device_sample_rate}, buffer={self.mic_chunk_size}")
        self.stream = self.p.open(
            format=self.format,
            channels=self.channels,
            rate=self.device_sample_rate,
            input=True,
            frames_per_buffer=self.mic_chunk_size
        )
        logger.info(f"音訊流已開啟: is_active={self.stream.is_active()}")
        
        start_time = time.time()
        self.is_recording = True
        frame_count = 0
        
        logger.info("請對著麥克風說話...")
        
        # 使用非阻塞方式顯示圖表
        plt.ion()
        plt.show()
        
        # 錄音主迴圈
        while time.time() - start_time < duration and self.is_recording:
            try:
                frame_count += 1
                # 讀取音訊 - 使用正確的 mic_chunk_size
                audio_data = self.stream.read(self.mic_chunk_size, exception_on_overflow=False)
                
                if frame_count <= 5:  # 只記錄前5幀
                    logger.info(f"讀取到第 {frame_count} 幀音訊: {len(audio_data)} bytes")
                
                # 如果需要重採樣
                if self.format_converter:
                    # 創建設備音訊的元數據
                    device_metadata = {
                        'metadata': AudioMetadata(
                            sample_rate=self.device_sample_rate,
                            channels=self.channels,
                            format=AudioFormat.INT16
                        )
                    }
                    # 轉換音訊格式
                    converted_audio = await self.format_converter.process(audio_data, **device_metadata)
                    if converted_audio:
                        audio_data = converted_audio
                    else:
                        logger.error("音訊格式轉換失敗")
                        continue
                
                # 創建音訊元數據
                recording_metadata = {
                    'metadata': AudioMetadata(
                        sample_rate=self.target_sample_rate,
                        channels=self.channels,
                        format=AudioFormat.INT16
                    )
                }
                
                # 傳遞給 RecordingOperator
                result = await self.recording_operator.process(audio_data, **recording_metadata)
                
                if frame_count <= 5:
                    logger.info(f"錄音處理完成，結果: {result is not None}")
                
                # 更新視覺化 - 使用原始音訊數據
                original_audio_np = np.frombuffer(audio_data, dtype=np.int16)
                self.update_visualization(audio_data)
                
                # 讓 matplotlib 處理事件
                plt.pause(0.001)
                
            except Exception as e:
                logger.error(f"音訊處理錯誤: {e}")
                break
        
        # 停止錄音
        self.is_recording = False
        recorded_data = await self.recording_operator.stop_recording(session_id)
        
        # 關閉音訊流
        self.stream.stop_stream()
        self.stream.close()
        self.stream = None
        
        # 顯示結果
        duration_actual = time.time() - start_time
        
        if recorded_data:
            logger.info(f"\n錄音完成:")
            logger.info(f"  實際錄音時長: {duration_actual:.2f} 秒")
            logger.info(f"  音訊資料大小: {len(recorded_data) / 1024:.1f} KB")
            logger.info(f"  預期音訊長度: {len(recorded_data) / (self.target_sample_rate * 2):.2f} 秒")
            logger.info(f"  儲存位置: test_recordings/{session_id}_*.wav")
            logger.info(f"  處理幀數: {frame_count}")
        else:
            logger.error("錄音失敗，沒有收到資料")
        
        # 保持圖表顯示一段時間
        logger.info("\n按關閉視窗結束...")
        plt.ioff()
        plt.show()
        
        return len(recorded_data) > 0


async def main():
    """主函數"""
    print("🎙️  RecordingOperator 視覺化測試")
    print("=" * 60)
    
    tester = RecordingVisualTester()
    
    try:
        # 設定測試環境
        await tester.setup()
        
        # 詢問錄音時長
        while True:
            try:
                duration = input("\n請輸入錄音時長（秒，5-60）[預設: 10]: ").strip()
                if not duration:
                    duration = 10.0
                else:
                    duration = float(duration)
                    
                if 5 <= duration <= 60:
                    break
                else:
                    print("請輸入 5-60 之間的數字")
            except ValueError:
                print("請輸入有效的數字")
        
        # 執行視覺化錄音測試
        success = await tester.test_visual_recording(duration)
        print(f"\n測試結果: {'✅ 成功' if success else '❌ 失敗'}")
    
    except KeyboardInterrupt:
        print("\n\n測試被用戶中斷")
        logger.info("用戶中斷測試")
    except Exception as e:
        print(f"\n測試錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理資源
        await tester.cleanup()
        print("\n測試結束")


if __name__ == "__main__":
    asyncio.run(main())