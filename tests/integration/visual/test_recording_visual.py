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
from collections import deque
from typing import Optional
import threading

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))

from src.pipeline.operators.recording import RecordingOperator
from src.utils.logger import logger
from src.models.audio_format import AudioMetadata, AudioFormat
from src.utils.visualization import RecordingVisualization


class RecordingVisualTester:
    """視覺化錄音測試器"""
    
    def __init__(self):
        # RecordingOperator 會從 ConfigManager 讀取配置
        self.recording_operator = None
        
        # PyAudio
        self.p = pyaudio.PyAudio()
        
        # 音訊參數
        self.sample_rate = 16000  # RecordingOperator 期望的採樣率
        self.channels = 1
        self.chunk_size = 1024
        self.format = pyaudio.paInt16
        
        # 音訊流
        self.stream = None
        self.is_recording = False
        
        # 視覺化
        self.visualization = RecordingVisualization()
        
        # 資料緩衝
        self.waveform_buffer = deque(maxlen=int(self.sample_rate * 2))  # 2秒的波形
        
        # 錄音參數
        self.recording_duration = 10.0
        self.start_time = None
        self.loop = None
        
    async def setup(self):
        """設定測試環境"""
        logger.info("設定錄音測試環境...")
        
        # 創建測試目錄
        Path('test_recordings').mkdir(exist_ok=True)
        
        # 初始化錄音 operator
        self.recording_operator = RecordingOperator()
        
        # 強制設定為檔案儲存模式
        self.recording_operator.storage_type = 'file'
        self.recording_operator.storage_path = Path('test_recordings')
        # 確保目錄存在
        self.recording_operator.storage_path.mkdir(exist_ok=True)
        
        await self.recording_operator.start()
        
        logger.info("✓ 測試環境設定完成")
    
    async def cleanup(self):
        """清理測試環境"""
        logger.info("清理測試環境...")
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.recording_operator:
            await self.recording_operator.stop()
        
        self.p.terminate()
        
        logger.info("✓ 測試環境清理完成")
    
    def _update_plot(self, frame):
        """更新圖表（給動畫使用）"""
        # 獲取最新數據
        latest_data = self.visualization.get_latest_data()
        
        if latest_data:
            # 更新音訊波形
            audio_data = latest_data.get('audio')
            if audio_data is not None:
                self.visualization.update_audio_plot(audio_data)
            
            # 更新聲譜圖
            if hasattr(self.visualization, 'update_spectrogram') and audio_data is not None:
                # 使用當前的音訊數據來更新聲譜圖
                if len(audio_data) > 512:  # 需要足夠的數據
                    self.visualization.update_spectrogram(audio_data)
            
            # 更新統計資訊（顯示在圖形頂部）
            if hasattr(self.visualization, 'texts') and 'stats' in self.visualization.texts:
                recording_info = self.recording_operator.get_recording_info()
                if recording_info.get('is_recording', False):
                    duration = recording_info.get('duration', 0)
                    bytes_recorded = recording_info.get('bytes_recorded', 0)
                    size_kb = bytes_recorded / 1024
                    current_volume = latest_data.get('volume_db', -60)
                    
                    # 計算平均音量
                    volume_history = latest_data.get('volume_history', [])
                    avg_volume = sum(volume_history) / len(volume_history) if volume_history else -60
                    
                    stats_text = (
                        f"[錄音中] 時長: {duration:.1f}s | 大小: {size_kb:.1f} KB | "
                        f"當前音量: {current_volume:.1f} dB | 平均音量: {avg_volume:.1f} dB"
                    )
                else:
                    stats_text = "[錄音停止]"
                
                self.visualization.texts['stats'].set_text(stats_text)
        
        return []
    
    def test_visual_recording(self, duration: float = 10.0):
        """視覺化錄音測試 (同步版本)"""
        logger.info(f"\n{'='*60}")
        logger.info(f"視覺化錄音測試 ({duration} 秒)")
        logger.info(f"{'='*60}")
        
        session_id = f"visual_{int(time.time())}"
        
        # 設定視覺化
        self.visualization.setup_plot()
        
        # 創建新的事件循環給線程使用
        self.loop = asyncio.new_event_loop()
        
        # 在背景線程中運行事件循環
        def run_event_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        loop_thread.start()
        
        # 等待循環啟動
        time.sleep(0.1)
        
        # 開始錄音
        future = asyncio.run_coroutine_threadsafe(
            self.recording_operator.start_recording(session_id), 
            self.loop
        )
        future.result()  # 等待完成
        logger.info(f"錄音開始 (session_id: {session_id})")
        
        # 開啟麥克風
        try:
            self.stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            logger.info(f"音訊流已開啟: {self.sample_rate}Hz, {self.channels}ch")
        except Exception as e:
            logger.error(f"無法開啟音訊流: {e}")
            # 嘗試其他採樣率
            for rate in [44100, 48000, 8000]:
                try:
                    self.sample_rate = rate
                    self.stream = self.p.open(
                        format=self.format,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size
                    )
                    logger.info(f"使用備用採樣率: {rate}Hz")
                    break
                except:
                    continue
        
        self.start_time = time.time()
        self.is_recording = True
        self.recording_duration = duration
        
        logger.info("請對著麥克風說話...")
        
        # 啟動音訊處理線程
        audio_thread = threading.Thread(target=self._audio_processing_thread)
        audio_thread.daemon = True
        audio_thread.start()
        
        # 使用非阻塞的方式啟動動畫
        import matplotlib
        matplotlib.use('TkAgg')  # 確保使用 TkAgg 後端
        
        # 創建動畫但不阻塞
        from matplotlib.animation import FuncAnimation
        self.ani = FuncAnimation(
            self.visualization.fig, 
            self._update_plot, 
            interval=100,
            blit=False,
            cache_frame_data=False
        )
        
        # 顯示視窗但不阻塞
        plt.show(block=False)
        
        # 等待錄音完成或視窗關閉
        start_wait = time.time()
        while (time.time() - start_wait < self.recording_duration and 
               self.is_recording and 
               plt.get_fignums()):  # 檢查是否還有開啟的視窗
            plt.pause(0.1)  # 處理 GUI 事件
            
        # 錄音結束
        self.is_recording = False
        logger.info(f"錄音時間到，準備停止...")
        
        # 等待音訊線程結束
        audio_thread.join(timeout=1.0)
        
        # 停止錄音並獲取資料
        logger.info("正在儲存錄音...")
        stop_future = asyncio.run_coroutine_threadsafe(
            self.recording_operator.stop_recording(session_id), 
            self.loop
        )
        recorded_data = stop_future.result()  # 等待完成
        
        # 關閉音訊流
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        # 停止事件循環
        self.loop.call_soon_threadsafe(self.loop.stop)
        time.sleep(0.1)
        self.loop.close()
        
        # 顯示結果
        duration_actual = time.time() - self.start_time
        
        if recorded_data:
            logger.info(f"\n{'='*60}")
            logger.info(f"錄音完成！")
            logger.info(f"{'='*60}")
            logger.info(f"實際錄音時長: {duration_actual:.2f} 秒")
            logger.info(f"音訊資料大小: {len(recorded_data) / 1024:.1f} KB")
            logger.info(f"預期音訊長度: {len(recorded_data) / (self.sample_rate * 2):.2f} 秒")
            logger.info(f"儲存位置: test_recordings/{session_id}_*.wav")
            logger.info(f"{'='*60}")
            
            # 關閉視覺化視窗（如果還開著）
            if plt.get_fignums():
                plt.close('all')
        else:
            logger.error("錄音失敗，沒有收到資料")
        
        return len(recorded_data) > 0 if recorded_data else False
    
    def _audio_processing_thread(self):
        """音訊處理線程"""
        # 初始化音量歷史
        self.volume_history = deque(maxlen=200)
        self.time_history = deque(maxlen=200)
        
        # 定期顯示進度
        last_progress_time = time.time()
        
        while time.time() - self.start_time < self.recording_duration and self.is_recording:
            try:
                if not self.stream:
                    break
                    
                # 讀取音訊
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 轉換為 numpy array
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                
                # 更新波形緩衝
                self.waveform_buffer.extend(audio_np)
                
                # 計算音量 (dB)
                if len(audio_np) > 0:
                    rms = np.sqrt(np.mean(audio_np.astype(float) ** 2))
                    volume_db = 20 * np.log10(max(rms, 1)) - 60
                else:
                    volume_db = -60
                
                # 創建音訊元數據
                metadata = AudioMetadata(
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                    format=AudioFormat.INT16
                )
                
                # 傳遞給 RecordingOperator (使用 run_coroutine_threadsafe)
                if self.loop and self.loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self.recording_operator.process(audio_data, metadata=metadata), 
                        self.loop
                    )
                    # 等待完成，給更多時間
                    try:
                        result = future.result(timeout=1.0)  # 增加到 1 秒
                        # 只在前幾次記錄成功訊息
                        if not hasattr(self, '_process_count'):
                            self._process_count = 0
                        self._process_count += 1
                        if self._process_count <= 5:
                            logger.debug(f"成功處理音訊數據 #{self._process_count}, 大小: {len(audio_data)} bytes")
                    except TimeoutError:
                        logger.warning("RecordingOperator.process() 超時")
                    except Exception as e:
                        logger.error(f"RecordingOperator.process() 錯誤: {e}")
                
                # 更新音量歷史
                current_time = time.time()
                self.volume_history.append(volume_db)
                self.time_history.append(current_time)
                
                # 添加到視覺化佇列
                self.visualization.add_data({
                    'audio': np.array(list(self.waveform_buffer)),
                    'volume_db': volume_db,
                    'timestamp': current_time,
                    'volume_history': list(self.volume_history),
                    'time_history': list(self.time_history)
                })
                
                # 每秒顯示一次進度
                current_time = time.time()
                if current_time - last_progress_time >= 1.0:
                    elapsed = current_time - self.start_time
                    remaining = self.recording_duration - elapsed
                    if remaining > 0:
                        logger.info(f"錄音中... 已錄製 {elapsed:.1f} 秒，剩餘 {remaining:.1f} 秒")
                    last_progress_time = current_time
                
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"音訊處理錯誤: {e}")
                import traceback
                traceback.print_exc()
                break
        
        logger.info("音訊處理線程結束")


def main():
    """主函數 (同步版本)"""
    print("🎙️  RecordingOperator 視覺化測試")
    print("=" * 60)
    
    tester = RecordingVisualTester()
    
    # 創建事件循環用於 setup 和 cleanup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 設定測試環境
        loop.run_until_complete(tester.setup())
        
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
        
        # 執行視覺化錄音測試 (同步版本)
        success = tester.test_visual_recording(duration)
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
        loop.run_until_complete(tester.cleanup())
        loop.close()
        print("\n測試結束")


if __name__ == "__main__":
    main()