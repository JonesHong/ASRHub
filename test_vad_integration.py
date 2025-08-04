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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline.operators.vad import SileroVADOperator
from src.pipeline.operators.vad.events import VADEvent, VADEventData
from src.pipeline.operators.vad.statistics import VADFrame, VADStatisticsCollector
from src.pipeline.operators.audio_format.scipy_operator import ScipyAudioFormatOperator
from src.models.audio_format import AudioMetadata, AudioFormat
from src.utils.logger import logger
from src.utils.visualization import VADVisualization

# logger = logger


class VADIntegrationTester:
    """VAD 功能整合測試"""
    
    def __init__(self):
        # 初始化 VAD operator
        self.vad_operator = SileroVADOperator()
        
        # 更新配置以適合測試
        self.vad_operator.update_config({
            'threshold': 0.08,  # 大幅降低門檻值以適應合成語音
            'min_silence_duration': 0.2,
            'min_speech_duration': 0.05,
            'adaptive_threshold': False,  # 關閉自適應閾值
            'smoothing_window': 2
        })
        
        # 音訊格式轉換器
        # VAD 需要的格式
        self.vad_format = AudioMetadata(
            sample_rate=16000,
            channels=1,
            format=AudioFormat.INT16
        )
        self.format_converter = ScipyAudioFormatOperator(
            operator_id='vad_converter',
            target_metadata=self.vad_format
        )
        
        # 麥克風輸入參數（系統實際格式）
        self.mic_sample_rate = 48000  # 48kHz
        self.mic_channels = 2         # 立體聲
        self.mic_format = pyaudio.paInt16  # PyAudio 使用 16位元
        
        # VAD 處理參數
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 512  # Silero VAD 需要 512 樣本
        self.format = pyaudio.paInt16
        
        # 計算麥克風的 chunk 大小（考慮採樣率差異）
        self.mic_chunk_size = int(self.chunk_size * self.mic_sample_rate / self.sample_rate)
        logger.info(f"音訊參數: VAD chunk_size={self.chunk_size}, 麥克風 chunk_size={self.mic_chunk_size}")
        
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
        
        # 測試模式
        self.test_mode = None  # 'realtime', 'file', 'synthetic'
        
    async def setup(self):
        """設定測試環境"""
        logger.info("設定 VAD 測試環境...")
        
        try:
            # 初始化格式轉換器
            await self.format_converter.start()
            
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
            
            # 停止格式轉換器
            if self.format_converter:
                await self.format_converter.stop()
            
            logger.info("✓ 測試環境清理完成")
            
        except Exception as e:
            logger.error(f"清理錯誤: {e}")
    
    async def test_realtime(self):
        """即時音訊測試"""
        logger.info("開始即時音訊 VAD 測試")
        self.test_mode = 'realtime'
        
        # 開啟音訊流（使用麥克風實際參數）
        logger.info(f"開啟音訊流: format={self.mic_format}, channels={self.mic_channels}, rate={self.mic_sample_rate}, buffer={self.mic_chunk_size}")
        self.stream = self.p.open(
            format=self.mic_format,
            channels=self.mic_channels,
            rate=self.mic_sample_rate,
            input=True,
            frames_per_buffer=self.mic_chunk_size
        )
        logger.info(f"音訊流已開啟: is_active={self.stream.is_active()}")
        
        self.is_running = True
        
        # 啟動音訊處理線程
        logger.info("正在啟動音訊處理線程...")
        audio_thread = threading.Thread(target=self._audio_processing_loop)
        audio_thread.daemon = True
        audio_thread.start()
        logger.info("音訊處理線程已啟動")
        
        # 啟動視覺化
        await self._start_visualization()
    
    async def test_audio_file(self, file_path: str):
        """測試音訊檔案"""
        logger.info(f"測試音訊檔案: {file_path}")
        self.test_mode = 'file'
        
        # TODO: 實作音訊檔案測試
        pass
    
    async def test_synthetic_audio(self):
        """測試合成音訊（純語音、純靜音、混合）"""
        logger.info("開始合成音訊測試")
        self.test_mode = 'synthetic'
        
        # 設定視覺化（如果需要的話）
        # 註：合成音訊測試通常不需要視覺化，所以我們跳過視覺化設定
        
        test_cases = [
            ("純靜音", self._generate_silence, 3.0),
            ("純語音", self._generate_speech, 3.0),
            ("語音+靜音", self._generate_speech_with_silence, 5.0),
            ("噪音環境", self._generate_noisy_speech, 5.0)
        ]
        
        for name, generator, duration in test_cases:
            logger.info(f"\n測試場景: {name}")
            logger.info("-" * 40)
            
            # 重置統計
            self.statistics_collector.reset()
            await self.vad_operator.flush()
            
            # 生成測試音訊
            audio_data = generator(duration)
            
            # 處理音訊
            start_time = time.time()
            await self._process_audio_data(audio_data)
            processing_time = time.time() - start_time
            
            # 輸出結果
            stats = self.statistics_collector.get_statistics()
            logger.info(f"處理時間: {processing_time:.3f}s")
            logger.info(f"總幀數: {stats.total_frames}")
            logger.info(f"語音幀數: {stats.speech_frames}")
            logger.info(f"靜音幀數: {stats.silence_frames}")
            logger.info(f"語音比例: {stats.speech_frames / max(1, stats.total_frames):.2%}")
            logger.info(f"語音段落數: {len(stats.speech_segments)}")
            
            if stats.speech_segments:
                logger.info(f"平均段落時長: {stats.average_segment_duration:.3f}s")
                logger.info(f"最長段落: {stats.max_segment_duration:.3f}s")
            
            await asyncio.sleep(0.5)
    
    def _audio_processing_loop(self):
        """音訊處理迴圈（在線程中運行）"""
        logger.info("音訊處理線程啟動")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        frame_count = 0
        while self.is_running:
            try:
                # 檢查 stream 是否仍然開啟
                if not self.stream or not self.stream.is_active():
                    logger.info("音訊流已關閉，退出處理循環")
                    break
                    
                # 讀取音訊 - 使用正確的 mic_chunk_size
                audio_data = self.stream.read(self.mic_chunk_size, exception_on_overflow=False)
                frame_count += 1
                
                if frame_count <= 5:  # 只記錄前5幀
                    logger.info(f"讀取到第 {frame_count} 幀音訊: {len(audio_data)} bytes")
                
                # 轉換為 numpy array（考慮立體聲）
                audio_np = np.frombuffer(audio_data, dtype=np.int16).reshape(-1, self.mic_channels)
                
                # 處理音訊
                try:
                    loop.run_until_complete(self._process_audio_chunk(audio_data, audio_np))
                except Exception as process_error:
                    logger.error(f"處理音訊塊時發生錯誤: {process_error}", exc_info=True)
                    if frame_count <= 5:
                        raise  # 前5幀的錯誤需要立即報告
                
            except Exception as e:
                if self.is_running:  # 只在仍在運行時報錯
                    logger.error(f"音訊處理錯誤: {e}")
                    time.sleep(0.01)
                else:
                    break
        
        loop.close()
    
    async def _process_audio_chunk(self, audio_data: bytes, audio_np: np.ndarray):
        """處理單個音訊塊"""
        # 記錄處理開始時間
        start_time = time.time()
        
        # 記錄開始處理
        chunk_number = getattr(self, '_chunk_count', 0) + 1
        self._chunk_count = chunk_number
        if chunk_number <= 5:
            logger.info(f"開始處理音訊塊 #{chunk_number}")
        
        # 創建麥克風音訊的元數據
        mic_metadata = {
            'metadata': AudioMetadata(
                sample_rate=self.mic_sample_rate,
                channels=self.mic_channels,
                format=AudioFormat.INT16
            )
        }
        
        # 轉換音訊格式（48kHz 立體聲 16bit -> 16kHz 單聲道 16bit）
        if chunk_number <= 5:
            logger.info(f"開始音訊格式轉換... 輸入大小: {len(audio_data)} bytes")
        converted_audio = await self.format_converter.process(audio_data, **mic_metadata)
        if chunk_number <= 5:
            if converted_audio:
                logger.info(f"音訊格式轉換完成，輸出大小: {len(converted_audio)} bytes")
                # 計算預期大小
                expected_size = len(audio_data) * 16000 // 48000 // 2  # 採樣率降低 + 立體轉單聲道
                logger.info(f"預期輸出大小: {expected_size} bytes")
            else:
                logger.error("音訊格式轉換返回 None")
        
        if converted_audio is None:
            logger.error("音訊格式轉換失敗")
            return
        
        # 轉換後的音訊為 numpy array（用於視覺化）
        converted_np = np.frombuffer(converted_audio, dtype=np.int16)
        
        # 計算音訊能量（用於調試）
        audio_energy = np.abs(converted_np).mean()
        
        # 創建 VAD 元數據
        vad_metadata = {
            'metadata': self.vad_format
        }
        
        # 執行 VAD
        if chunk_number <= 5:
            logger.info("開始 VAD 處理...")
        
        # VAD 需要 kwargs 作為字典傳遞，不要解包
        result = await self.vad_operator.process(converted_audio, metadata=self.vad_format)
        
        if chunk_number <= 5:
            logger.info("VAD 處理完成")
        
        # 記錄處理時間
        processing_time = time.time() - start_time
        self.statistics_collector.add_processing_time(processing_time)
        
        # 獲取 VAD 狀態
        vad_state = self.vad_operator.get_info()
        
        # 調試輸出
        if chunk_number <= 5:
            logger.info(f"音訊處理 #{chunk_number}: 原始={len(audio_data)} bytes, 轉換後={len(converted_audio)} bytes, 能量={audio_energy:.4f}, VAD狀態={vad_state.get('in_speech', False)}, 語音機率={vad_state.get('speech_probability', 0):.4f}")
        
        # 將資料加入視覺化佇列（使用轉換後的音訊）
        self.visualization.add_data({
            'audio': converted_np,
            'vad_state': vad_state,
            'timestamp': time.time(),
            'speech_prob': vad_state.get('speech_probability', 0),
            'threshold': self.vad_operator.threshold
        })
    
    async def _process_audio_data(self, audio_data: np.ndarray):
        """處理完整的音訊資料"""
        # 轉換為 bytes
        audio_bytes = audio_data.astype(np.int16).tobytes()
        
        # 分塊處理
        chunk_size_bytes = self.chunk_size * 2  # int16
        
        for i in range(0, len(audio_bytes), chunk_size_bytes):
            chunk = audio_bytes[i:i + chunk_size_bytes]
            if len(chunk) == chunk_size_bytes:
                await self.vad_operator.process(chunk)
    
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
        
        # 記錄時間戳
        current_time = time.time()
        
        # 調試輸出 - 顯示所有 VAD 結果
        logger.info(f"VAD 結果: 機率={vad_result['speech_probability']:.3f}, 檢測={vad_result['speech_detected']}")
        
        # 只在即時模式下更新視覺化（當視覺化已經被設定時）
        if self.test_mode == 'realtime' and hasattr(self.visualization, 'lines') and 'vad' in self.visualization.lines:
            self.visualization.update_vad_plot(
                vad_result['speech_probability'], 
                current_time, 
                self.vad_operator.threshold
            )
    
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
            
            # 不需要再次更新 VAD 圖表，因為已經在回調中更新了
            # 只需要確保圖表重繪
            
            # 獲取當前閾值
            threshold = latest_data.get('threshold', self.vad_operator.threshold)
            
            # 更新統計
            stats = self.statistics_collector.get_statistics()
            recent_stats = self.statistics_collector.get_recent_statistics(window_seconds=10)
            
            # 獲取 VAD 狀態
            vad_state = latest_data.get('vad_state', {})
            
            # 使用簡潔的格式
            speech_ratio = stats.speech_frames / max(1, stats.total_frames)
            is_speaking = '[說話中]' if vad_state.get('is_speaking', False) else '[靜音]'
            
            # 計算累積時長
            total_duration = time.time() - self.statistics_collector.start_time if hasattr(self.statistics_collector, 'start_time') else 0
            speech_duration = stats.total_speech_duration
            silence_duration = total_duration - speech_duration
            
            stats_text = (
                f"處理: {stats.total_frames} 幀 | 語音: {stats.speech_frames} ({speech_ratio:.1%}) | "
                f"最近10秒: {recent_stats.get('speech_ratio', 0):.1%}\n"
                f"{is_speaking} | 語音: {self.visualization.format_time(speech_duration)} | "
                f"靜音: {self.visualization.format_time(silence_duration)} | "
                f"閾值: {threshold:.3f}"
            )
            self.visualization.texts['stats'].set_text(stats_text)
        
        return []
    
    def _generate_silence(self, duration: float) -> np.ndarray:
        """生成純靜音"""
        samples = int(duration * self.sample_rate)
        return np.zeros(samples)
    
    def _generate_speech(self, duration: float) -> np.ndarray:
        """生成模擬語音（使用更強的噪音信號）"""
        samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, samples)
        
        # 使用更接近真實語音的噪音模式
        # 產生強烈的寬頻噪音（類似語音頻譜）
        speech = np.random.normal(0, 5000, samples)
        
        # 加入一些週期性元素
        for freq in [100, 200, 300, 400]:
            speech += 1000 * np.sin(2 * np.pi * freq * t)
        
        # 使用更明顯的振幅調製
        envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 2 * t)
        envelope = np.maximum(envelope, 0.3)  # 保持最低振幅
        speech *= envelope
        
        # 加入更多變化的噪音
        noise_envelope = np.random.uniform(0.8, 1.2, samples)
        speech *= noise_envelope
        
        # 正規化到接近滿刻度
        speech = np.clip(speech, -32000, 32000)
        
        return speech
    
    def _generate_speech_with_silence(self, duration: float) -> np.ndarray:
        """生成語音和靜音交替的音訊"""
        samples = int(duration * self.sample_rate)
        audio = np.zeros(samples)
        
        # 交替的語音和靜音段
        segments = [
            (0.0, 0.5, 'silence'),
            (0.5, 2.0, 'speech'),
            (2.0, 2.5, 'silence'),
            (2.5, 4.0, 'speech'),
            (4.0, 5.0, 'silence')
        ]
        
        for start, end, type_ in segments:
            start_idx = int(start * self.sample_rate)
            end_idx = int(end * self.sample_rate)
            
            if type_ == 'speech':
                segment_duration = end - start
                speech = self._generate_speech(segment_duration)
                audio[start_idx:end_idx] = speech[:end_idx - start_idx]
        
        return audio
    
    def _generate_noisy_speech(self, duration: float) -> np.ndarray:
        """生成帶噪音的語音"""
        # 生成語音
        speech = self._generate_speech_with_silence(duration)
        
        # 添加白噪音
        noise = np.random.normal(0, 1000, len(speech))
        
        # 混合（SNR 約 10dB）
        noisy_speech = speech + noise
        
        # 限制範圍
        noisy_speech = np.clip(noisy_speech, -32768, 32767)
        
        return noisy_speech
    
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
    print("請選擇測試模式:")
    print("1. 即時音訊測試")
    print("2. 音訊檔案測試")
    print("3. 合成音訊測試")
    
    choice = input("\n請輸入選擇 (1-3): ").strip()
    
    tester = VADIntegrationTester()
    
    try:
        # 設定測試環境
        await tester.setup()
        
        if choice == "1":
            print("\n開始即時音訊測試...")
            print("請對著麥克風說話，按 Ctrl+C 結束測試")
            await tester.test_realtime()
            
        elif choice == "2":
            file_path = input("請輸入音訊檔案路徑: ").strip()
            await tester.test_audio_file(file_path)
            
        elif choice == "3":
            print("\n開始合成音訊測試...")
            await tester.test_synthetic_audio()
            
        else:
            print("無效的選擇")
            return
        
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