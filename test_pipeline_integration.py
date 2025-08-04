#!/usr/bin/env python3
"""
Pipeline 整合測試工具
測試 WakeWord → VAD → Recording 的完整流程
以及多 Operator 串聯功能
"""

import asyncio
import sys
import os
import time
import numpy as np
import pyaudio
from typing import Dict, Any, Optional, List
from pathlib import Path
import psutil
import queue
import threading

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# 只在需要繪製效能圖表時導入 matplotlib
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from src.pipeline.manager import PipelineManager
from src.pipeline.operators.wakeword import OpenWakeWordOperator
from src.pipeline.operators.vad import SileroVADOperator
from src.pipeline.operators.recording import RecordingOperator
from src.pipeline.operators.sample_rate import SampleRateAdjustmentOperator
from src.core.fsm import StateMachine, State
from src.utils.logger import logger

# 使用統一的視覺化工具
from src.utils.visualization import PipelineVisualization


class PipelineIntegrationTester:
    """Pipeline 整合測試器"""
    
    def __init__(self):
        # Pipeline 管理器
        self.pipeline_manager = PipelineManager()
        
        # 音訊參數
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1280
        self.format = pyaudio.paInt16
        
        # PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_running = False
        
        # 測試結果
        self.test_results = []
        
        # 視覺化
        self.visualization = PipelineVisualization()
        
        # 效能監控
        self.process_monitor = psutil.Process()
        self.performance_data = {
            'cpu': [],
            'memory': [],
            'latency': [],
            'timestamps': []
        }
    
    async def setup(self):
        """設定測試環境"""
        logger.info("設定 Pipeline 測試環境...")
        
        try:
            # 初始化 Pipeline 管理器
            await self.pipeline_manager.start()
            
            logger.info("✓ Pipeline 測試環境設定完成")
            
        except Exception as e:
            logger.error(f"設定失敗: {e}")
            raise
    
    async def cleanup(self):
        """清理測試環境"""
        logger.info("清理測試環境...")
        
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            
            self.p.terminate()
            
            # 停止所有 pipelines
            await self.pipeline_manager.stop()
            
            logger.info("✓ 測試環境清理完成")
            
        except Exception as e:
            logger.error(f"清理錯誤: {e}")
    
    async def test_basic_pipeline(self):
        """測試基本 Pipeline 功能"""
        logger.info("\n=== 測試基本 Pipeline 功能 ===")
        
        # 創建簡單 pipeline: SampleRate → VAD
        pipeline_config = {
            'name': 'basic_pipeline',
            'operators': [
                {
                    'type': 'sample_rate_adjustment',
                    'config': {
                        'target_rate': 16000,
                        'quality': 'high'
                    }
                },
                {
                    'type': 'vad',
                    'config': {
                        'threshold': 0.5,
                        'min_silence_duration': 0.5
                    }
                }
            ]
        }
        
        pipeline_id = await self.pipeline_manager.create_pipeline(pipeline_config)
        
        # 生成測試音訊
        test_audio = self._generate_test_audio(3.0)
        
        # 處理音訊
        start_time = time.time()
        
        chunk_size_bytes = self.chunk_size * 2
        for i in range(0, len(test_audio), chunk_size_bytes):
            chunk = test_audio[i:i + chunk_size_bytes]
            result = await self.pipeline_manager.process(pipeline_id, chunk)
            
        processing_time = time.time() - start_time
        
        # 獲取 pipeline 統計
        stats = self.pipeline_manager.get_pipeline_stats(pipeline_id)
        
        result = {
            'test_name': '基本 Pipeline',
            'pipeline_id': pipeline_id,
            'processing_time': processing_time,
            'processed_chunks': stats.get('processed_chunks', 0),
            'success': True
        }
        
        self.test_results.append(result)
        logger.info(f"基本 Pipeline 測試完成，處理時間: {processing_time:.3f}s")
        
        # 清理
        await self.pipeline_manager.remove_pipeline(pipeline_id)
    
    async def test_complete_pipeline(self):
        """測試完整 Pipeline (WakeWord → VAD → Recording)"""
        logger.info("\n=== 測試完整 Pipeline ===")
        
        # 創建完整 pipeline
        pipeline_config = {
            'name': 'complete_pipeline',
            'operators': [
                {
                    'type': 'sample_rate_adjustment',
                    'config': {
                        'target_rate': 16000
                    }
                },
                {
                    'type': 'wakeword',
                    'config': {
                        'model_path': 'models/hi_kmu_0721.onnx',
                        'threshold': 0.5
                    }
                },
                {
                    'type': 'vad',
                    'config': {
                        'threshold': 0.5,
                        'min_silence_duration': 0.5
                    }
                },
                {
                    'type': 'recording',
                    'config': {
                        'vad_controlled': True,
                        'silence_countdown': 1.8,
                        'storage': {
                            'type': 'memory'
                        }
                    }
                }
            ]
        }
        
        pipeline_id = await self.pipeline_manager.create_pipeline(pipeline_config)
        
        # 獲取 pipeline 參考
        pipeline = self.pipeline_manager.pipelines.get(pipeline_id)
        
        # 設定事件處理
        wake_detected = False
        recording_completed = False
        
        async def on_wake(event):
            nonlocal wake_detected
            wake_detected = True
            logger.info("Pipeline 檢測到喚醒詞")
        
        async def on_recording(event):
            nonlocal recording_completed
            recording_completed = True
            logger.info("Pipeline 錄音完成")
        
        # 註冊事件處理器
        # TODO: 實作事件系統
        
        # 測試場景：模擬喚醒詞 → 語音 → 靜音
        logger.info("模擬喚醒詞觸發場景...")
        
        # 這裡應該使用實際的喚醒詞音訊
        # 為了測試，我們使用模擬音訊
        test_duration = 5.0
        test_audio = self._generate_speech(test_duration)
        
        # 處理音訊
        chunk_size_bytes = self.chunk_size * 2
        for i in range(0, len(test_audio), chunk_size_bytes):
            chunk = test_audio[i:i + chunk_size_bytes]
            await self.pipeline_manager.process(pipeline_id, chunk)
            await asyncio.sleep(0.032)
        
        result = {
            'test_name': '完整 Pipeline',
            'pipeline_id': pipeline_id,
            'wake_detected': wake_detected,
            'recording_completed': recording_completed,
            'success': True
        }
        
        self.test_results.append(result)
        
        # 清理
        await self.pipeline_manager.remove_pipeline(pipeline_id)
    
    async def test_multiple_pipelines(self):
        """測試多個 Pipeline 並行運行"""
        logger.info("\n=== 測試多個 Pipeline 並行 ===")
        
        num_pipelines = 3
        pipeline_ids = []
        
        # 創建多個 pipeline
        for i in range(num_pipelines):
            config = {
                'name': f'parallel_pipeline_{i}',
                'operators': [
                    {
                        'type': 'vad',
                        'config': {
                            'threshold': 0.5 + i * 0.1  # 不同的閾值
                        }
                    }
                ]
            }
            
            pipeline_id = await self.pipeline_manager.create_pipeline(config)
            pipeline_ids.append(pipeline_id)
        
        # 並行處理音訊
        test_audio = self._generate_speech_with_silence(5.0)
        chunk_size_bytes = self.chunk_size * 2
        
        tasks = []
        for i in range(0, len(test_audio), chunk_size_bytes):
            chunk = test_audio[i:i + chunk_size_bytes]
            
            # 每個 pipeline 處理相同的音訊
            for pipeline_id in pipeline_ids:
                task = self.pipeline_manager.process(pipeline_id, chunk)
                tasks.append(task)
        
        # 等待所有任務完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 統計成功率
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        total_tasks = len(tasks)
        
        result = {
            'test_name': '多 Pipeline 並行',
            'num_pipelines': num_pipelines,
            'total_tasks': total_tasks,
            'success_count': success_count,
            'success_rate': success_count / total_tasks,
            'success': success_count == total_tasks
        }
        
        self.test_results.append(result)
        logger.info(f"並行測試完成，成功率: {result['success_rate']:.2%}")
        
        # 清理
        for pipeline_id in pipeline_ids:
            await self.pipeline_manager.remove_pipeline(pipeline_id)
    
    async def test_error_recovery(self):
        """測試錯誤恢復能力"""
        logger.info("\n=== 測試錯誤恢復 ===")
        
        # 創建包含故障 operator 的 pipeline
        pipeline_config = {
            'name': 'error_test_pipeline',
            'operators': [
                {
                    'type': 'vad',
                    'config': {
                        'threshold': 0.5
                    }
                },
                {
                    'type': 'faulty_operator',  # 不存在的 operator
                    'config': {}
                }
            ]
        }
        
        # 嘗試創建應該失敗的 pipeline
        try:
            pipeline_id = await self.pipeline_manager.create_pipeline(pipeline_config)
            pipeline_created = True
        except Exception as e:
            pipeline_created = False
            logger.info(f"Pipeline 創建失敗（預期行為）: {e}")
        
        # 創建正常的 pipeline
        normal_config = {
            'name': 'normal_pipeline',
            'operators': [
                {
                    'type': 'vad',
                    'config': {'threshold': 0.5}
                }
            ]
        }
        
        pipeline_id = await self.pipeline_manager.create_pipeline(normal_config)
        
        # 測試處理無效資料
        invalid_data = b"invalid_audio_data"
        error_occurred = False
        
        try:
            await self.pipeline_manager.process(pipeline_id, invalid_data)
        except Exception as e:
            error_occurred = True
            logger.info(f"處理無效資料時發生錯誤（預期行為）: {e}")
        
        # 確認 pipeline 仍然可用
        valid_audio = self._generate_silence(0.1)
        can_process_after_error = True
        
        try:
            await self.pipeline_manager.process(pipeline_id, valid_audio)
        except Exception:
            can_process_after_error = False
        
        result = {
            'test_name': '錯誤恢復',
            'faulty_pipeline_rejected': not pipeline_created,
            'error_on_invalid_data': error_occurred,
            'recovery_after_error': can_process_after_error,
            'success': not pipeline_created and can_process_after_error
        }
        
        self.test_results.append(result)
        
        # 清理
        await self.pipeline_manager.remove_pipeline(pipeline_id)
    
    async def test_performance_stress(self):
        """壓力測試和效能監控"""
        logger.info("\n=== 壓力測試 ===")
        
        # 創建高負載 pipeline
        pipeline_config = {
            'name': 'stress_test_pipeline',
            'operators': [
                {'type': 'sample_rate_adjustment', 'config': {'target_rate': 16000}},
                {'type': 'vad', 'config': {'threshold': 0.5}},
                {'type': 'recording', 'config': {'storage': {'type': 'memory'}}}
            ]
        }
        
        pipeline_id = await self.pipeline_manager.create_pipeline(pipeline_config)
        
        # 測試參數
        test_duration = 10.0  # 秒
        chunk_duration = self.chunk_size / self.sample_rate
        total_chunks = int(test_duration / chunk_duration)
        
        # 重置效能資料
        self.performance_data = {
            'cpu': [],
            'memory': [],
            'latency': [],
            'timestamps': []
        }
        
        logger.info(f"開始 {test_duration}s 壓力測試...")
        
        # 生成測試音訊
        test_audio = self._generate_speech_with_silence(test_duration)
        chunk_size_bytes = self.chunk_size * 2
        
        # 處理音訊並監控效能
        start_time = time.time()
        
        for i in range(0, len(test_audio), chunk_size_bytes):
            chunk = test_audio[i:i + chunk_size_bytes]
            
            # 記錄處理前狀態
            chunk_start = time.time()
            cpu_percent = self.process_monitor.cpu_percent(interval=0)
            memory_mb = self.process_monitor.memory_info().rss / 1024 / 1024
            
            # 處理音訊
            await self.pipeline_manager.process(pipeline_id, chunk)
            
            # 記錄處理延遲
            latency = time.time() - chunk_start
            
            # 保存效能資料
            self.performance_data['cpu'].append(cpu_percent)
            self.performance_data['memory'].append(memory_mb)
            self.performance_data['latency'].append(latency * 1000)  # ms
            self.performance_data['timestamps'].append(time.time() - start_time)
        
        total_time = time.time() - start_time
        
        # 計算統計
        avg_cpu = np.mean(self.performance_data['cpu'])
        max_cpu = np.max(self.performance_data['cpu'])
        avg_memory = np.mean(self.performance_data['memory'])
        max_memory = np.max(self.performance_data['memory'])
        avg_latency = np.mean(self.performance_data['latency'])
        max_latency = np.max(self.performance_data['latency'])
        
        result = {
            'test_name': '壓力測試',
            'duration': test_duration,
            'total_chunks': total_chunks,
            'avg_cpu_percent': avg_cpu,
            'max_cpu_percent': max_cpu,
            'avg_memory_mb': avg_memory,
            'max_memory_mb': max_memory,
            'avg_latency_ms': avg_latency,
            'max_latency_ms': max_latency,
            'realtime_factor': total_time / test_duration,
            'success': avg_latency < 50 and avg_cpu < 80  # 延遲 < 50ms, CPU < 80%
        }
        
        self.test_results.append(result)
        
        logger.info(f"壓力測試完成:")
        logger.info(f"  平均 CPU: {avg_cpu:.1f}%")
        logger.info(f"  平均記憶體: {avg_memory:.1f} MB")
        logger.info(f"  平均延遲: {avg_latency:.1f} ms")
        logger.info(f"  即時係數: {result['realtime_factor']:.2f}x")
        
        # 清理
        await self.pipeline_manager.remove_pipeline(pipeline_id)
    
    async def test_24hour_stability(self):
        """24 小時穩定性測試（模擬）"""
        logger.info("\n=== 長時間穩定性測試（模擬） ===")
        
        # 創建測試 pipeline
        pipeline_config = {
            'name': 'stability_test_pipeline',
            'operators': [
                {'type': 'vad', 'config': {'threshold': 0.5}},
                {'type': 'recording', 'config': {'storage': {'type': 'memory'}}}
            ]
        }
        
        pipeline_id = await self.pipeline_manager.create_pipeline(pipeline_config)
        
        # 模擬 24 小時（實際運行 1 分鐘）
        simulated_hours = 24
        actual_duration = 60  # 秒
        chunks_per_hour = 100  # 每小時處理的塊數
        
        logger.info(f"開始穩定性測試（模擬 {simulated_hours} 小時）...")
        
        initial_memory = self.process_monitor.memory_info().rss / 1024 / 1024
        errors = 0
        processed_chunks = 0
        
        start_time = time.time()
        
        while time.time() - start_time < actual_duration:
            try:
                # 生成隨機音訊
                chunk = self._generate_random_audio(self.chunk_size * 2)
                await self.pipeline_manager.process(pipeline_id, chunk)
                processed_chunks += 1
                
            except Exception as e:
                errors += 1
                logger.warning(f"處理錯誤: {e}")
            
            # 模擬時間間隔
            await asyncio.sleep(actual_duration / (simulated_hours * chunks_per_hour))
        
        # 最終記憶體
        final_memory = self.process_monitor.memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory
        
        result = {
            'test_name': '穩定性測試',
            'simulated_hours': simulated_hours,
            'actual_duration': actual_duration,
            'processed_chunks': processed_chunks,
            'errors': errors,
            'error_rate': errors / max(1, processed_chunks),
            'memory_growth_mb': memory_growth,
            'success': errors == 0 and memory_growth < 100
        }
        
        self.test_results.append(result)
        
        logger.info(f"穩定性測試完成:")
        logger.info(f"  處理塊數: {processed_chunks}")
        logger.info(f"  錯誤數: {errors}")
        logger.info(f"  記憶體增長: {memory_growth:.1f} MB")
        
        # 清理
        await self.pipeline_manager.remove_pipeline(pipeline_id)
    
    def _generate_test_audio(self, duration: float) -> bytes:
        """生成測試音訊"""
        samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, samples)
        audio = 0.3 * np.sin(2 * np.pi * 440 * t)
        return (audio * 20000).astype(np.int16).tobytes()
    
    def _generate_speech(self, duration: float) -> bytes:
        """生成模擬語音"""
        samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, samples)
        speech = np.zeros(samples)
        
        for f0 in [120, 200, 300]:
            speech += 0.3 * np.sin(2 * np.pi * f0 * t)
            for h in range(2, 5):
                speech += 0.1 / h * np.sin(2 * np.pi * f0 * h * t)
        
        envelope = 0.7 + 0.3 * np.sin(2 * np.pi * 3 * t)
        speech *= envelope
        
        return (speech / np.max(np.abs(speech)) * 25000).astype(np.int16).tobytes()
    
    def _generate_silence(self, duration: float) -> bytes:
        """生成靜音"""
        samples = int(duration * self.sample_rate)
        return np.zeros(samples, dtype=np.int16).tobytes()
    
    def _generate_speech_with_silence(self, duration: float) -> bytes:
        """生成語音和靜音交替的音訊"""
        # 簡化實作，交替生成語音和靜音
        half_duration = duration / 2
        speech = self._generate_speech(half_duration)
        silence = self._generate_silence(half_duration)
        return speech + silence
    
    def _generate_random_audio(self, size: int) -> bytes:
        """生成隨機音訊資料"""
        return np.random.randint(-5000, 5000, size=size//2, dtype=np.int16).tobytes()
    
    def print_test_results(self):
        """打印測試結果"""
        print("\n" + "="*60)
        print("📊 Pipeline 整合測試結果")
        print("="*60)
        
        for result in self.test_results:
            test_name = result['test_name']
            success = result.get('success', False)
            status = "✅ 通過" if success else "❌ 失敗"
            
            print(f"\n{test_name}: {status}")
            for key, value in result.items():
                if key not in ['test_name', 'success']:
                    if isinstance(value, float):
                        print(f"  {key}: {value:.3f}")
                    else:
                        print(f"  {key}: {value}")
        
        # 總結
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.get('success', False))
        
        print("\n" + "-"*60)
        print(f"總計: {passed_tests}/{total_tests} 測試通過")
        
        # 效能總結
        stress_result = next((r for r in self.test_results if r['test_name'] == '壓力測試'), None)
        if stress_result:
            print("\n效能總結:")
            print(f"  平均 CPU 使用率: {stress_result['avg_cpu_percent']:.1f}%")
            print(f"  平均處理延遲: {stress_result['avg_latency_ms']:.1f} ms")
            print(f"  即時處理能力: {stress_result['realtime_factor']:.2f}x")
        
        print("="*60)
    
    def plot_performance_data(self):
        """繪製效能資料圖表"""
        if not self.performance_data['timestamps']:
            return
            
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib 未安裝，無法繪製效能圖表")
            return
        
        fig, axes = plt.subplots(3, 1, figsize=(10, 10))
        
        # CPU 使用率
        ax1 = axes[0]
        ax1.plot(self.performance_data['timestamps'], self.performance_data['cpu'])
        ax1.set_title('CPU 使用率')
        ax1.set_xlabel('時間 (秒)')
        ax1.set_ylabel('CPU %')
        ax1.grid(True)
        
        # 記憶體使用
        ax2 = axes[1]
        ax2.plot(self.performance_data['timestamps'], self.performance_data['memory'])
        ax2.set_title('記憶體使用')
        ax2.set_xlabel('時間 (秒)')
        ax2.set_ylabel('記憶體 (MB)')
        ax2.grid(True)
        
        # 處理延遲
        ax3 = axes[2]
        ax3.plot(self.performance_data['timestamps'], self.performance_data['latency'])
        ax3.set_title('處理延遲')
        ax3.set_xlabel('時間 (秒)')
        ax3.set_ylabel('延遲 (ms)')
        ax3.grid(True)
        
        plt.tight_layout()
        plt.savefig('pipeline_performance.png')
        logger.info("效能圖表已保存至 pipeline_performance.png")


async def main():
    """主函數"""
    print("🔧 Pipeline 整合測試工具")
    print("-" * 60)
    
    tester = PipelineIntegrationTester()
    
    try:
        # 設定測試環境
        await tester.setup()
        
        # 執行測試套件
        tests = [
            ("基本 Pipeline", tester.test_basic_pipeline),
            ("完整 Pipeline", tester.test_complete_pipeline),
            ("多 Pipeline 並行", tester.test_multiple_pipelines),
            ("錯誤恢復", tester.test_error_recovery),
            ("壓力測試", tester.test_performance_stress),
        ]
        
        # 詢問是否執行長時間測試
        if input("\n是否執行長時間穩定性測試（需要 1 分鐘）？(y/n): ").lower() == 'y':
            tests.append(("穩定性測試", tester.test_24hour_stability))
        
        for test_name, test_func in tests:
            print(f"\n執行測試: {test_name}")
            try:
                await test_func()
            except Exception as e:
                logger.error(f"測試失敗: {e}")
                import traceback
                traceback.print_exc()
        
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
        
        # 繪製效能圖表
        if input("\n是否生成效能圖表？(y/n): ").lower() == 'y':
            tester.plot_performance_data()


if __name__ == "__main__":
    asyncio.run(main())