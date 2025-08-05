#!/usr/bin/env python3
"""
VAD 整合測試工具
測試 SileroVADOperator 的功能和準確性
"""

import asyncio
import sys
import os
import time
import numpy as np
import pyaudio
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))

from src.pipeline.operators.vad import SileroVADOperator
from src.pipeline.operators.vad.events import VADEvent, VADEventData
from src.pipeline.operators.vad.statistics import VADFrame, VADStatisticsCollector
from src.pipeline.operators.audio_format.scipy_operator import ScipyAudioFormatOperator
from src.models.audio_format import AudioMetadata, AudioFormat
from src.utils.logger import logger
from src.utils.visualization import VADVisualization


class VADIntegrationTester:
    """VAD 功能整合測試"""
    
    def __init__(self):
        # 初始化 VAD operator
        self.vad_operator = SileroVADOperator()
        
        # 更新配置以適合測試
        self.vad_operator.update_config({
            'threshold': 0.5,  # 標準門檻值
            'min_silence_duration': 0.3,
            'min_speech_duration': 0.1,
            'adaptive_threshold': True,
            'smoothing_window': 3
        })
        
        # 音訊參數
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 512  # Silero VAD 需要 512 樣本
        self.format = pyaudio.paInt16
        
        # PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_running = False
        
        # 資料收集
        self.vad_results = []
        self.statistics_collector = VADStatisticsCollector()
        self.statistics_collector.start_time = time.time()
        
        # 視覺化
        self.visualization = VADVisualization()
        
    async def setup(self):
        """設定測試環境"""
        logger.info("設定 VAD 測試環境...")
        
        try:
            # 初始化 VAD operator
            await self.vad_operator.start()
            
            # 設定事件回調
            self.vad_operator.set_speech_callbacks(
                start_callback=self._on_speech_start,
                end_callback=self._on_speech_end,
                result_callback=self._on_vad_result
            )
            
            logger.info("✓ VAD 測試環境設定完成")
            
        except Exception as e:
            logger.error(f"設定失敗: {e}")
            raise
    
    async def cleanup(self):
        """清理測試環境"""
        logger.info("清理測試環境...")
        
        try:
            # 先停止處理循環
            self.is_running = False
            
            # 等待一小段時間讓線程結束
            await asyncio.sleep(0.1)
            
            # 停止音訊流
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            
            # 清理 PyAudio
            if self.p:
                self.p.terminate()
            
            # 停止 VAD operator
            if self.vad_operator:
                await self.vad_operator.stop()
            
            logger.info("✓ 測試環境清理完成")
            
        except Exception as e:
            logger.error(f"清理錯誤: {e}")
    
    async def test_realtime(self):
        """即時音訊測試"""
        logger.info("開始即時音訊 VAD 測試")
        
        # 開啟音訊流
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
        
        self.is_running = True
        
        # 啟動音訊處理線程
        audio_thread = threading.Thread(target=self._audio_processing_loop)
        audio_thread.daemon = True
        audio_thread.start()
        
        # 啟動視覺化
        await self._start_visualization()
    
    def _audio_processing_loop(self):
        """音訊處理迴圈（在線程中運行）"""
        logger.info("音訊處理線程啟動")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.is_running:
            try:
                # 讀取音訊
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 處理音訊
                loop.run_until_complete(self._process_audio_chunk(audio_data))
                
            except Exception as e:
                if self.is_running:
                    logger.error(f"音訊處理錯誤: {e}")
                    time.sleep(0.01)
        
        loop.close()
    
    async def _process_audio_chunk(self, audio_data: bytes):
        """處理單個音訊塊"""
        # 轉換為 numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        
        # 創建元數據
        metadata = AudioMetadata(
            sample_rate=self.sample_rate,
            channels=self.channels,
            format=AudioFormat.INT16
        )
        
        # 執行 VAD
        result = await self.vad_operator.process(audio_data, metadata=metadata)
        
        # 獲取 VAD 狀態
        vad_state = self.vad_operator.get_info()
        
        # 將資料加入視覺化佇列
        self.visualization.add_data({
            'audio': audio_np,
            'vad_state': vad_state,
            'timestamp': time.time(),
            'speech_prob': vad_state.get('speech_probability', 0),
            'threshold': self.vad_operator.threshold
        })
    
    async def _on_speech_start(self, event_data: Dict[str, Any]):
        """語音開始事件"""
        logger.info(f"🎤 語音開始 (機率: {event_data.get('speech_probability', 0):.3f})")
    
    async def _on_speech_end(self, event_data: Dict[str, Any]):
        """語音結束事件"""
        duration = event_data.get('speech_duration', 0)
        logger.info(f"🔇 語音結束 (時長: {duration:.3f}s)")
    
    async def _on_vad_result(self, vad_result: Dict[str, Any]):
        """VAD 結果事件"""
        # 收集統計
        frame = VADFrame(
            timestamp=vad_result['timestamp'],
            speech_probability=vad_result['speech_probability'],
            is_speech=vad_result['speech_detected'],
            threshold=self.vad_operator.threshold
        )
        self.statistics_collector.add_frame(frame)
    
    async def _start_visualization(self):
        """啟動視覺化"""
        logger.info("啟動 VAD 視覺化監控...")
        
        # 設定圖表
        self.visualization.setup_plot()
        
        # 啟動動畫
        self.visualization.start_animation(self._update_plot, interval=100)
    
    def _update_plot(self, frame):
        """更新圖表"""
        # 獲取最新數據
        latest_data = self.visualization.get_latest_data()
        
        if latest_data:
            # 更新音訊波形
            audio_data = latest_data['audio']
            self.visualization.update_audio_plot(audio_data)
            
            # 更新 VAD 圖表
            vad_prob = latest_data['speech_prob']
            timestamp = latest_data['timestamp']
            threshold = latest_data.get('threshold', self.vad_operator.threshold)
            self.visualization.update_vad_plot(vad_prob, timestamp, threshold)
            
            # 更新統計
            stats = self.statistics_collector.get_statistics()
            recent_stats = self.statistics_collector.get_recent_statistics(window_seconds=10)
            
            # 獲取 VAD 狀態
            vad_state = latest_data.get('vad_state', {})
            
            # 使用簡潔的格式
            speech_ratio = stats.speech_frames / max(1, stats.total_frames)
            is_speaking = '[說話中]' if vad_state.get('in_speech', False) else '[靜音]'
            
            # 計算累積時長
            total_duration = time.time() - self.statistics_collector.start_time
            speech_duration = stats.total_speech_duration
            silence_duration = total_duration - speech_duration
            
            stats_text = (
                f"處理: {stats.total_frames} 幀 | 語音: {stats.speech_frames} ({speech_ratio:.1%}) | "
                f"最近10秒: {recent_stats.get('speech_ratio', 0):.1%}\n"
                f"{is_speaking} | 語音: {self.visualization.format_time(speech_duration)} | "
                f"靜音: {self.visualization.format_time(silence_duration)} | "
                f"閾值: {threshold:.3f}"
            )
            
            if hasattr(self.visualization, 'texts') and 'stats' in self.visualization.texts:
                self.visualization.texts['stats'].set_text(stats_text)
        
        return []
    
    def print_test_results(self):
        """打印測試結果"""
        stats = self.statistics_collector.get_statistics()
        
        print("\n" + "="*60)
        print("📊 VAD 測試結果")
        print("="*60)
        
        print(f"\n基本統計:")
        print(f"  總處理幀數: {stats.total_frames}")
        print(f"  語音幀數: {stats.speech_frames}")
        print(f"  靜音幀數: {stats.silence_frames}")
        print(f"  語音比例: {stats.speech_frames / max(1, stats.total_frames):.2%}")
        
        print(f"\n語音段落:")
        print(f"  段落數量: {len(stats.speech_segments)}")
        if stats.speech_segments:
            print(f"  總語音時長: {stats.total_speech_duration:.3f}s")
            print(f"  平均段落時長: {stats.average_segment_duration:.3f}s")
            print(f"  最長段落: {stats.max_segment_duration:.3f}s")
            print(f"  最短段落: {stats.min_segment_duration:.3f}s")
        
        print(f"\n處理效能:")
        if stats.processing_times:
            print(f"  平均處理時間: {stats.avg_processing_time * 1000:.3f}ms")
            print(f"  最大處理時間: {stats.max_processing_time * 1000:.3f}ms")
        
        print("="*60)


async def main():
    """主函數"""
    print("🎯 VAD 整合測試工具")
    print("請對著麥克風說話，觀察 VAD 檢測效果")
    print("按 Ctrl+C 或關閉視窗結束測試")
    
    tester = VADIntegrationTester()
    
    try:
        # 設定測試環境
        await tester.setup()
        
        # 執行即時測試
        await tester.test_realtime()
        
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n測試錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理資源
        await tester.cleanup()
        
        # 打印結果
        tester.print_test_results()


if __name__ == "__main__":
    asyncio.run(main())