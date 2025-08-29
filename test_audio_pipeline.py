#!/usr/bin/env python3
"""
音訊處理管線測試
逐步測試每個處理階段，找出掉幀問題的根源

測試流程：
1. 麥克風原始擷取 → 錄音 (raw.wav)
2. 麥克風 → 音訊增強 → 錄音 (enhanced.wav)
3. 麥克風 → 降噪 → 錄音 (denoised.wav)
4. 麥克風 → 增強 → 降噪 → 錄音 (full_pipeline.wav)
"""

import time
import signal
import numpy as np
import wave
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import threading

from src.utils.logger import logger
from src.service.microphone_capture.microphone_capture import microphone_capture
from src.service.audio_enhancer import audio_enhancer
from src.core.audio_queue_manager import audio_queue

# DeepFilterNet 是可選的
try:
    from src.service.denoise.deepfilternet_denoiser import deepfilternet_denoiser
    HAS_DEEPFILTERNET = True
except (ImportError, AttributeError) as e:
    logger.warning(f"DeepFilterNet not available: {e}")
    deepfilternet_denoiser = None
    HAS_DEEPFILTERNET = False


class AudioPipelineTest:
    """音訊處理管線測試"""
    
    def __init__(self):
        self.is_running = False
        self.current_test = None
        self.session_id = "pipeline_test"
        self.audio_buffer = []
        self.chunk_count = 0
        self.dropped_frames = 0
        self.last_timestamp = None
        
        # 設定信號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # 測試參數
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024
        self.test_duration = 5  # 每個測試錄音5秒
        
        # 輸出目錄
        self.output_dir = Path("recordings/pipeline_test")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _signal_handler(self, signum, frame):
        """優雅停止"""
        logger.info("🛑 接收到停止信號...")
        self.stop_test()
    
    def stop_test(self):
        """停止當前測試"""
        self.is_running = False
        
    def save_audio(self, audio_data: np.ndarray, filename: str, test_name: str):
        """儲存音訊到檔案"""
        filepath = self.output_dir / filename
        
        # 確保是 int16 格式
        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32767).astype(np.int16)
        
        # 寫入 WAV 檔案
        with wave.open(str(filepath), 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # int16 = 2 bytes
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        logger.info(f"✅ {test_name} 音訊已儲存: {filepath}")
        
        # 計算統計資訊
        duration = len(audio_data) / self.sample_rate
        logger.info(f"📊 統計:")
        logger.info(f"   • 時長: {duration:.2f} 秒")
        logger.info(f"   • 樣本數: {len(audio_data)}")
        logger.info(f"   • 音訊範圍: [{audio_data.min()}, {audio_data.max()}]")
        logger.info(f"   • RMS: {np.sqrt(np.mean(audio_data.astype(float)**2)):.1f}")
        
        return filepath
    
    def test_raw_capture(self):
        """測試1: 原始麥克風擷取"""
        logger.info("=" * 60)
        logger.info("📝 測試1: 原始麥克風擷取")
        logger.info("=" * 60)
        
        self.current_test = "raw"
        self.audio_buffer = []
        self.chunk_count = 0
        self.dropped_frames = 0
        self.last_timestamp = None
        
        def audio_callback(audio_data: np.ndarray, sample_rate: int):
            """音訊回調"""
            if not self.is_running:
                return
                
            current_time = time.time()
            
            # 檢查是否有掉幀
            if self.last_timestamp:
                expected_interval = self.chunk_size / sample_rate
                actual_interval = current_time - self.last_timestamp
                if actual_interval > expected_interval * 1.5:  # 超過預期間隔的1.5倍
                    self.dropped_frames += 1
                    logger.warning(f"⚠️ 可能掉幀! 間隔: {actual_interval:.3f}s (預期: {expected_interval:.3f}s)")
            
            self.last_timestamp = current_time
            self.chunk_count += 1
            self.audio_buffer.append(audio_data)
            
            # 每50個chunk報告一次
            if self.chunk_count % 50 == 0:
                logger.info(f"   收到 chunks: {self.chunk_count}, 掉幀: {self.dropped_frames}")
        
        # 設定麥克風
        microphone_capture.set_parameters(
            sample_rate=self.sample_rate,
            channels=self.channels,
            chunk_size=self.chunk_size
        )
        
        # 開始擷取
        logger.info("🎙️ 開始原始音訊擷取...")
        self.is_running = True
        microphone_capture.start_capture(callback=audio_callback)
        
        # 錄音指定時間
        start_time = time.time()
        while self.is_running and (time.time() - start_time) < self.test_duration:
            time.sleep(0.1)
        
        self.is_running = False
        microphone_capture.stop_capture()
        
        # 合併音訊
        if self.audio_buffer:
            combined_audio = np.concatenate(self.audio_buffer)
            self.save_audio(combined_audio, "1_raw.wav", "原始音訊")
            logger.info(f"📊 總chunks: {self.chunk_count}, 總掉幀: {self.dropped_frames}")
            return combined_audio
        else:
            logger.error("❌ 沒有收到音訊資料")
            return None
    
    def test_enhanced_capture(self):
        """測試2: 音訊增強"""
        logger.info("=" * 60)
        logger.info("📝 測試2: 音訊增強處理")
        logger.info("=" * 60)
        
        self.current_test = "enhanced"
        self.audio_buffer = []
        self.chunk_count = 0
        self.dropped_frames = 0
        self.last_timestamp = None
        
        def audio_callback(audio_data: np.ndarray, sample_rate: int):
            """音訊回調 - 加上增強處理"""
            if not self.is_running:
                return
            
            current_time = time.time()
            
            # 檢查掉幀
            if self.last_timestamp:
                expected_interval = self.chunk_size / sample_rate
                actual_interval = current_time - self.last_timestamp
                if actual_interval > expected_interval * 1.5:
                    self.dropped_frames += 1
                    logger.warning(f"⚠️ 可能掉幀! 間隔: {actual_interval:.3f}s")
            
            self.last_timestamp = current_time
            
            # 音訊增強
            try:
                enhanced, report = audio_enhancer.auto_enhance(
                    audio_data.tobytes(),
                    purpose="asr"
                )
                
                # 轉回 numpy array
                enhanced_array = np.frombuffer(enhanced, dtype=np.int16)
                self.audio_buffer.append(enhanced_array)
                
                # 每50個chunk報告一次增強效果
                if self.chunk_count % 50 == 0:
                    logger.info(f"   增強報告: {report}")
                
            except Exception as e:
                logger.error(f"增強失敗: {e}")
                self.audio_buffer.append(audio_data)
            
            self.chunk_count += 1
        
        # 開始擷取
        logger.info("🎙️ 開始增強音訊擷取...")
        self.is_running = True
        microphone_capture.start_capture(callback=audio_callback)
        
        # 錄音指定時間
        start_time = time.time()
        while self.is_running and (time.time() - start_time) < self.test_duration:
            time.sleep(0.1)
        
        self.is_running = False
        microphone_capture.stop_capture()
        
        # 合併音訊
        if self.audio_buffer:
            combined_audio = np.concatenate(self.audio_buffer)
            self.save_audio(combined_audio, "2_enhanced.wav", "增強音訊")
            logger.info(f"📊 總chunks: {self.chunk_count}, 總掉幀: {self.dropped_frames}")
            return combined_audio
        else:
            logger.error("❌ 沒有收到音訊資料")
            return None
    
    def test_denoised_capture(self):
        """測試3: 降噪處理"""
        if not HAS_DEEPFILTERNET:
            logger.warning("⚠️ DeepFilterNet 不可用，跳過降噪測試")
            return None
            
        logger.info("=" * 60)
        logger.info("📝 測試3: 降噪處理")
        logger.info("=" * 60)
        
        self.current_test = "denoised"
        self.audio_buffer = []
        self.chunk_count = 0
        self.dropped_frames = 0
        self.last_timestamp = None
        
        # 累積緩衝區（降噪需要較大的音訊片段）
        accumulation_buffer = []
        accumulation_size = 8  # 累積8個chunks再處理
        
        def audio_callback(audio_data: np.ndarray, sample_rate: int):
            """音訊回調 - 加上降噪處理"""
            if not self.is_running:
                return
            
            current_time = time.time()
            
            # 檢查掉幀
            if self.last_timestamp:
                expected_interval = self.chunk_size / sample_rate
                actual_interval = current_time - self.last_timestamp
                if actual_interval > expected_interval * 1.5:
                    self.dropped_frames += 1
                    logger.warning(f"⚠️ 可能掉幀! 間隔: {actual_interval:.3f}s")
            
            self.last_timestamp = current_time
            self.chunk_count += 1
            
            # 累積音訊片段
            accumulation_buffer.append(audio_data)
            
            # 當累積足夠的片段時進行降噪
            if len(accumulation_buffer) >= accumulation_size:
                try:
                    # 合併累積的音訊
                    combined = np.concatenate(accumulation_buffer)
                    
                    # 降噪處理
                    denoised, denoise_report = deepfilternet_denoiser.auto_denoise(
                        combined.tobytes(),
                        purpose="asr",
                        sample_rate=sample_rate
                    )
                    
                    # 轉回 numpy array
                    denoised_array = np.frombuffer(denoised, dtype=np.int16)
                    self.audio_buffer.append(denoised_array)
                    
                    # 清空累積緩衝區
                    accumulation_buffer.clear()
                    
                    # 報告降噪效果
                    if self.chunk_count % 50 == 0:
                        logger.info(f"   降噪報告: {denoise_report}")
                    
                except Exception as e:
                    logger.error(f"降噪失敗: {e}")
                    # 失敗時直接使用原始音訊
                    self.audio_buffer.append(combined)
                    accumulation_buffer.clear()
        
        # 開始擷取
        logger.info("🎙️ 開始降噪音訊擷取...")
        self.is_running = True
        microphone_capture.start_capture(callback=audio_callback)
        
        # 錄音指定時間
        start_time = time.time()
        while self.is_running and (time.time() - start_time) < self.test_duration:
            time.sleep(0.1)
        
        self.is_running = False
        microphone_capture.stop_capture()
        
        # 處理剩餘的累積音訊
        if accumulation_buffer:
            combined = np.concatenate(accumulation_buffer)
            self.audio_buffer.append(combined)
        
        # 合併音訊
        if self.audio_buffer:
            combined_audio = np.concatenate(self.audio_buffer)
            self.save_audio(combined_audio, "3_denoised.wav", "降噪音訊")
            logger.info(f"📊 總chunks: {self.chunk_count}, 總掉幀: {self.dropped_frames}")
            return combined_audio
        else:
            logger.error("❌ 沒有收到音訊資料")
            return None
    
    def test_full_pipeline(self):
        """測試4: 完整處理管線（增強+降噪）"""
        logger.info("=" * 60)
        logger.info("📝 測試4: 完整處理管線（增強+降噪）")
        logger.info("=" * 60)
        
        self.current_test = "full"
        self.audio_buffer = []
        self.chunk_count = 0
        self.dropped_frames = 0
        self.last_timestamp = None
        
        # 累積緩衝區
        accumulation_buffer = []
        accumulation_size = 8
        
        def audio_callback(audio_data: np.ndarray, sample_rate: int):
            """音訊回調 - 完整處理管線"""
            if not self.is_running:
                return
            
            current_time = time.time()
            
            # 檢查掉幀
            if self.last_timestamp:
                expected_interval = self.chunk_size / sample_rate
                actual_interval = current_time - self.last_timestamp
                if actual_interval > expected_interval * 1.5:
                    self.dropped_frames += 1
                    logger.warning(f"⚠️ 可能掉幀! 間隔: {actual_interval:.3f}s")
            
            self.last_timestamp = current_time
            self.chunk_count += 1
            
            # 累積音訊片段
            accumulation_buffer.append(audio_data)
            
            # 當累積足夠的片段時進行處理
            if len(accumulation_buffer) >= accumulation_size:
                try:
                    # 合併累積的音訊
                    combined = np.concatenate(accumulation_buffer)
                    
                    # 步驟1: 音訊增強
                    enhanced, enhance_report = audio_enhancer.auto_enhance(
                        combined.tobytes(),
                        purpose="asr"
                    )
                    
                    # 步驟2: 降噪（如果可用）
                    if HAS_DEEPFILTERNET:
                        denoised, denoise_report = deepfilternet_denoiser.auto_denoise(
                            enhanced,
                            purpose="asr",
                            sample_rate=sample_rate
                        )
                        final_audio = np.frombuffer(denoised, dtype=np.int16)
                        
                        if self.chunk_count % 50 == 0:
                            logger.info(f"   增強: {enhance_report}")
                            logger.info(f"   降噪: {denoise_report}")
                    else:
                        final_audio = np.frombuffer(enhanced, dtype=np.int16)
                        if self.chunk_count % 50 == 0:
                            logger.info(f"   增強: {enhance_report}")
                    
                    self.audio_buffer.append(final_audio)
                    accumulation_buffer.clear()
                    
                except Exception as e:
                    logger.error(f"處理失敗: {e}")
                    self.audio_buffer.append(combined)
                    accumulation_buffer.clear()
        
        # 開始擷取
        logger.info("🎙️ 開始完整管線音訊擷取...")
        self.is_running = True
        microphone_capture.start_capture(callback=audio_callback)
        
        # 錄音指定時間
        start_time = time.time()
        while self.is_running and (time.time() - start_time) < self.test_duration:
            time.sleep(0.1)
        
        self.is_running = False
        microphone_capture.stop_capture()
        
        # 處理剩餘的累積音訊
        if accumulation_buffer:
            combined = np.concatenate(accumulation_buffer)
            self.audio_buffer.append(combined)
        
        # 合併音訊
        if self.audio_buffer:
            combined_audio = np.concatenate(self.audio_buffer)
            self.save_audio(combined_audio, "4_full_pipeline.wav", "完整管線音訊")
            logger.info(f"📊 總chunks: {self.chunk_count}, 總掉幀: {self.dropped_frames}")
            return combined_audio
        else:
            logger.error("❌ 沒有收到音訊資料")
            return None
    
    def run_all_tests(self):
        """執行所有測試"""
        logger.info("🚀 開始音訊處理管線測試")
        logger.info(f"測試參數: {self.sample_rate}Hz, {self.channels}ch, {self.chunk_size} samples/chunk")
        logger.info(f"每個測試錄音 {self.test_duration} 秒")
        logger.info(f"輸出目錄: {self.output_dir}")
        logger.info("")
        
        # 測試1: 原始音訊
        logger.info("請對著麥克風說話...")
        time.sleep(1)
        self.test_raw_capture()
        time.sleep(1)
        
        # 測試2: 音訊增強
        logger.info("\n請繼續對著麥克風說話...")
        time.sleep(1)
        self.test_enhanced_capture()
        time.sleep(1)
        
        # 測試3: 降噪
        logger.info("\n請繼續對著麥克風說話...")
        time.sleep(1)
        self.test_denoised_capture()
        time.sleep(1)
        
        # 測試4: 完整管線
        logger.info("\n請繼續對著麥克風說話...")
        time.sleep(1)
        self.test_full_pipeline()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有測試完成！")
        logger.info(f"請檢查 {self.output_dir} 目錄中的音訊檔案：")
        logger.info("  1_raw.wav - 原始音訊")
        logger.info("  2_enhanced.wav - 增強後音訊")
        logger.info("  3_denoised.wav - 降噪後音訊")
        logger.info("  4_full_pipeline.wav - 完整處理後音訊")
        logger.info("\n比較這些檔案可以找出掉幀問題的來源")
        logger.info("=" * 60)


def main():
    """主程式"""
    test = AudioPipelineTest()
    try:
        test.run_all_tests()
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
    finally:
        test.stop_test()


if __name__ == "__main__":
    main()