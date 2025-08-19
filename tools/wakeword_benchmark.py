#!/usr/bin/env python3
"""
喚醒詞效能基準測試工具
測試不同配置下的偵測準確率和效能
"""

import asyncio
import os
import sys
import time
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np
import statistics

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.operators.wakeword import OpenWakeWordOperator
from src.utils.logger import logger
from src.config.manager import ConfigManager


class WakeWordBenchmark:
    """喚醒詞基準測試器"""
    
    def __init__(self):
        """初始化基準測試器"""
        self.config_manager = ConfigManager()
        
        # 從配置讀取音訊參數        
        # 測試配置
        self.test_configs = [
            {"threshold": 0.3, "name": "低閾值 (0.3)"},
            {"threshold": 0.5, "name": "中等閾值 (0.5)"},
            {"threshold": 0.7, "name": "高閾值 (0.7)"},
        ]
        
        # 測試結果
        self.results: List[Dict[str, Any]] = []
        
        # 模擬音訊資料（用於效能測試）
        self.sample_rate = self.config_manager.pipeline.default_sample_rate
        self.chunk_size = 1280
        self.test_duration = 30  # 秒
    
    def generate_test_audio(self, duration: float) -> bytes:
        """
        生成測試音訊資料
        
        Args:
            duration: 音訊長度（秒）
            
        Returns:
            音訊資料 bytes
        """
        samples = int(duration * self.sample_rate)
        
        # 生成白噪音
        audio_data = np.random.normal(0, 100, samples).astype(np.int16)
        
        return audio_data.tobytes()
    
    async def benchmark_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        測試單個配置
        
        Args:
            config: 測試配置
            
        Returns:
            測試結果
        """
        print(f"\n🧪 測試配置: {config['name']}")
        print("-" * 40)
        
        # 初始化操作器
        operator = OpenWakeWordOperator()
        # 更新閾值設定
        operator.update_config({"threshold": config["threshold"]})
        detections = []
        processing_times = []
        
        # 偵測回呼
        async def on_detection(detection):
            detections.append(detection)
        
        operator.set_detection_callback(on_detection)
        
        try:
            # 啟動操作器
            await operator.start()
            print("✅ 操作器已啟動")
            
            # 生成測試音訊
            test_audio = self.generate_test_audio(self.test_duration)
            total_chunks = len(test_audio) // (self.chunk_size * 2)  # int16 = 2 bytes
            
            print(f"🎵 測試音訊: {self.test_duration} 秒")
            print(f"📦 音訊塊數: {total_chunks}")
            
            # 開始效能測試
            start_time = time.time()
            processed_chunks = 0
            
            for i in range(0, len(test_audio), self.chunk_size * 2):
                chunk = test_audio[i:i + self.chunk_size * 2]
                if len(chunk) < self.chunk_size * 2:
                    break
                
                # 測量處理時間
                chunk_start = time.time()
                
                await operator.process(
                    chunk,
                    sample_rate=self.sample_rate,
                    session_id="benchmark"
                )
                
                chunk_end = time.time()
                processing_times.append(chunk_end - chunk_start)
                processed_chunks += 1
                
                # 顯示進度
                if processed_chunks % 100 == 0:
                    progress = processed_chunks / total_chunks * 100
                    print(f"⏳ 進度: {progress:.1f}%", end='\r')
            
            end_time = time.time()
            total_time = end_time - start_time
            
            print(f"\n✅ 測試完成")
            
            # 計算統計資訊
            avg_processing_time = statistics.mean(processing_times) if processing_times else 0
            max_processing_time = max(processing_times) if processing_times else 0
            min_processing_time = min(processing_times) if processing_times else 0
            
            throughput = processed_chunks / total_time if total_time > 0 else 0
            real_time_factor = (processed_chunks * self.chunk_size / self.sample_rate) / total_time if total_time > 0 else 0
            
            # 分析偵測結果
            detection_count = len(detections)
            detection_scores = [d.get("score", 0) for d in detections]
            avg_score = statistics.mean(detection_scores) if detection_scores else 0
            max_score = max(detection_scores) if detection_scores else 0
            
            result = {
                "config": config,
                "test_duration": self.test_duration,
                "processed_chunks": processed_chunks,
                "total_processing_time": total_time,
                "avg_chunk_processing_time": avg_processing_time,
                "max_chunk_processing_time": max_processing_time,
                "min_chunk_processing_time": min_processing_time,
                "throughput_chunks_per_sec": throughput,
                "real_time_factor": real_time_factor,
                "detection_count": detection_count,
                "avg_detection_score": avg_score,
                "max_detection_score": max_score,
                "timestamp": datetime.now().isoformat()
            }
            
            # 打印結果
            self._print_config_results(result)
            
            return result
            
        except Exception as e:
            logger.error(f"配置測試失敗: {e}")
            return {
                "config": config,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        
        finally:
            # 清理
            await operator.stop()
    
    def _print_config_results(self, result: Dict[str, Any]):
        """打印配置測試結果"""
        print(f"\n📊 {result['config']['name']} 測試結果:")
        print(f"⏱️  總處理時間: {result['total_processing_time']:.2f} 秒")
        print(f"📦 處理塊數: {result['processed_chunks']}")
        print(f"⚡ 吞吐量: {result['throughput_chunks_per_sec']:.1f} 塊/秒")
        print(f"🕒 實時倍數: {result['real_time_factor']:.2f}x")
        print(f"📈 平均塊處理時間: {result['avg_chunk_processing_time']*1000:.2f} ms")
        print(f"📊 最大塊處理時間: {result['max_chunk_processing_time']*1000:.2f} ms")
        print(f"📉 最小塊處理時間: {result['min_chunk_processing_time']*1000:.2f} ms")
        print(f"🎯 偵測次數: {result['detection_count']}")
        print(f"🔢 平均偵測分數: {result['avg_detection_score']:.3f}")
        print(f"📈 最高偵測分數: {result['max_detection_score']:.3f}")
    
    async def run_benchmark(self, output_file: Optional[str] = None):
        """
        執行完整的基準測試
        
        Args:
            output_file: 結果輸出檔案路徑
        """
        print("🚀 開始喚醒詞效能基準測試")
        print("=" * 50)
        
        start_time = datetime.now()
        
        # 測試每個配置
        for config in self.test_configs:
            result = await self.benchmark_config(config)
            self.results.append(result)
        
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        # 打印總結
        self._print_summary(total_time)
        
        # 保存結果
        if output_file:
            self._save_results(output_file)
    
    def _print_summary(self, total_time: float):
        """打印測試總結"""
        print("\n" + "=" * 50)
        print("📈 基準測試總結")
        print("=" * 50)
        print(f"⏱️  總測試時間: {total_time:.1f} 秒")
        print(f"🧪 測試配置數: {len(self.test_configs)}")
        print(f"📊 有效結果數: {len([r for r in self.results if 'error' not in r])}")
        
        # 找出最佳配置
        valid_results = [r for r in self.results if 'error' not in r]
        
        if valid_results:
            # 按實時倍數排序（越高越好）
            best_performance = max(valid_results, key=lambda x: x['real_time_factor'])
            
            # 按偵測分數排序（需要平衡偵測次數和分數）
            best_detection = max(valid_results, key=lambda x: x['avg_detection_score'])
            
            print(f"\n🏆 最佳效能配置: {best_performance['config']['name']}")
            print(f"   實時倍數: {best_performance['real_time_factor']:.2f}x")
            print(f"   吞吐量: {best_performance['throughput_chunks_per_sec']:.1f} 塊/秒")
            
            print(f"\n🎯 最佳偵測配置: {best_detection['config']['name']}")
            print(f"   平均分數: {best_detection['avg_detection_score']:.3f}")
            print(f"   偵測次數: {best_detection['detection_count']}")
        
        print("=" * 50)
    
    def _save_results(self, output_file: str):
        """保存測試結果到檔案"""
        try:
            # 準備輸出資料
            output_data = {
                "benchmark_info": {
                    "test_duration": self.test_duration,
                    "sample_rate": self.sample_rate,
                    "chunk_size": self.chunk_size,
                    "timestamp": datetime.now().isoformat()
                },
                "results": self.results
            }
            
            # 寫入檔案
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 結果已保存到: {output_file}")
            
        except Exception as e:
            logger.error(f"保存結果失敗: {e}")


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description="喚醒詞效能基準測試")
    parser.add_argument(
        "--output", 
        "-o", 
        type=str, 
        help="結果輸出檔案路徑 (JSON格式)"
    )
    parser.add_argument(
        "--duration", 
        "-d", 
        type=int, 
        default=30, 
        help="測試音訊長度（秒，預設: 30）"
    )
    
    args = parser.parse_args()
    
    print("⚡ ASR Hub 喚醒詞效能基準測試工具")
    print("=" * 50)
    
    # 檢查環境
    if not os.environ.get("HF_TOKEN"):
        print("⚠️  警告: 未設定 HF_TOKEN 環境變數")
        print("如果需要下載模型，請設定: export HF_TOKEN=your_token")
        print()
    
    benchmark = WakeWordBenchmark()
    benchmark.test_duration = args.duration
    
    try:
        asyncio.run(benchmark.run_benchmark(args.output))
    except KeyboardInterrupt:
        print("\n❌ 測試被用戶中斷")
    except Exception as e:
        print(f"\n❌ 測試錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()