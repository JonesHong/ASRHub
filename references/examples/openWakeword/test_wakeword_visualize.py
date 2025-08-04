#!/usr/bin/env python3
"""
openWakeWord 視覺化診斷程式（基於 test_kmu.py 的處理邏輯）
顯示即時分數和音頻波形，幫助診斷檢測問題
"""

import os
import numpy as np
import pyaudio
import collections
from functools import partial
import time
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from huggingface_hub import hf_hub_download, HfFolder
from openwakeword.model import Model
from openwakeword.utils import download_models
import queue
import threading
import scipy.signal

# 設定中文字體
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class WakeWordVisualizer:
    def __init__(self):
        self.chunk_size = 1280
        self.sample_rate = 16000
        self.channels = 1
        self.format = pyaudio.paInt16  # 使用 Int16 格式
        
        # 使用與 test_kmu.py 相同的狀態管理
        self.state = collections.defaultdict(partial(collections.deque, maxlen=60))
        
        # 數據儲存
        self.audio_queue = queue.Queue()
        self.audio_history = collections.deque(maxlen=16000)  # 1秒的音頻
        self.detection_markers = []  # 儲存檢測標記的位置
        
        # 初始化模型
        self.model = self._init_model()
        
        # 初始化音頻
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_running = False
        
        # 儲存實際的採樣率（可能不是 16kHz）
        self.actual_sample_rate = None

    def _init_model(self):
        """初始化模型（只載入 KMU 模型）"""
        print("=== 初始化模型 ===")
        download_models()
        
        # 只使用 KMU 模型，與 test_kmu.py 相同
        hf_token = os.environ.get("HF_TOKEN") or HfFolder.get_token()
        
        if hf_token:
            print("載入 KMU 模型...")
            try:
                model_path = hf_hub_download(
                    repo_id="JTBTechnology/kmu_wakeword",
                    filename="hi_kmu_0721.onnx",
                    token=hf_token,
                    repo_type="model"
                )
                # 直接用下載的模型路徑載入
                model = Model(wakeword_models=[model_path], inference_framework="onnx")
                print(f"✓ 模型載入成功")
                return model
            except Exception as e:
                print(f"✗ 模型載入失敗: {e}")
                return None
        else:
            print("✗ 未找到 HF_TOKEN")
            return None

    def process_audio_chunk(self, audio_data):
        """處理音頻塊（基於 test_kmu.py 的邏輯）"""
        # 模擬 Gradio 的 (sample_rate, audio_data) 格式
        audio = (self.actual_sample_rate, audio_data)
        
        # 只打印一次調試信息
        if not hasattr(self, '_process_debug_printed'):
            self._process_debug_printed = False
        
        # 重採樣到 16kHz（如果需要）
        if audio[0] != 16000:
            data = scipy.signal.resample(audio[1], int(float(audio[1].shape[0])/audio[0]*16000))
            if not self._process_debug_printed:
                print(f"\n=== 重採樣處理 ===")
                print(f"原始採樣率: {audio[0]} Hz")
                print(f"目標採樣率: 16000 Hz")
                print(f"原始樣本數: {audio[1].shape[0]}")
                print(f"重採樣後樣本數: {data.shape[0]}")
                self._process_debug_printed = True
        else:
            data = audio[1]
        
        # 處理預測（與 test_kmu.py 相同的邏輯）
        predictions = []
        for i in range(0, data.shape[0], 1280):
            # 處理聲道（雖然我們是單聲道，但保持相同邏輯）
            if len(data.shape) == 2 or data.shape[-1] == 2:
                chunk = data[i:i+1280][:, 0]  # 只取一個聲道
            else:
                chunk = data[i:i+1280]
            
            if chunk.shape[0] == 1280:
                prediction = self.model.predict(chunk)
                for key in prediction:
                    # 如果 deque 是空的，填充零
                    if len(self.state[key]) == 0:
                        self.state[key].extend(np.zeros(60))
                    
                    # 添加預測
                    self.state[key].append(prediction[key])
                predictions.append(prediction)
        
        return predictions

    def audio_callback(self):
        """音頻處理線程"""
        # 嘗試不同的採樣率
        for test_rate in [16000, 44100, 48000]:
            try:
                self.stream = self.p.open(
                    format=self.format,
                    channels=self.channels,
                    rate=test_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size,
                )
                self.actual_sample_rate = test_rate
                print(f"使用採樣率: {test_rate} Hz")
                break
            except Exception as e:
                print(f"無法使用採樣率 {test_rate}: {e}")
                continue
        
        if not self.stream:
            print("無法開啟音頻流")
            return
        
        print("\n開始錄音...")
        print("請說出喚醒詞：'嗨，高醫' 或 'hi kmu'\n")
        
        # 調試標誌（只打印一次）
        debug_printed = False
        
        while self.is_running:
            try:
                # 讀取音頻
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 調試：打印 PyAudio 原始音頻屬性（只打印一次）
                if not debug_printed:
                    print(f"\n=== PyAudio 原始音頻屬性 [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ===")
                    print(f"audio_data 類型: {type(audio_data)}")
                    print(f"audio_data 長度: {len(audio_data)} bytes")
                    print(f"預期樣本數: {self.chunk_size}")
                    print(f"格式: {self.format} (pyaudio.paInt16)")
                    print(f"實際採樣率: {self.actual_sample_rate} Hz")
                    
                    # 轉換前的 Int16 數據
                    raw_int16 = np.frombuffer(audio_data, dtype=np.int16)
                    print(f"\n轉換前 (Int16):")
                    print(f"  數據類型: {raw_int16.dtype}")
                    print(f"  數據形狀: {raw_int16.shape}")
                    print(f"  數據範圍: [{raw_int16.min()}, {raw_int16.max()}]")
                    print(f"  前5個樣本: {raw_int16[:5]}")
                
                # 轉換為 float32 
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                
                # 調試：檢查音頻的實際範圍
                if not debug_printed:
                    actual_max = np.abs(audio_np).max()
                    print(f"\n音頻範圍分析:")
                    print(f"  最大絕對值: {actual_max}")
                    print(f"  是否需要正規化: {actual_max > 1.0}")
                
                # 轉換為 float32 但不正規化（匹配 Gradio 的行為）
                # Gradio 似乎直接使用 int16 值作為 float
                audio_np = audio_np.astype(np.float32)
                
                # 調試：打印轉換後的音頻屬性（只打印一次）
                if not debug_printed:
                    print(f"\n轉換後 (Float32 - 不正規化):")
                    print(f"  數據類型: {audio_np.dtype}")
                    print(f"  數據形狀: {audio_np.shape}")
                    print(f"  數據範圍: [{audio_np.min():.3f}, {audio_np.max():.3f}]")
                    print(f"  前5個樣本: {audio_np[:5]}")
                    
                    # 檢查是否需要正規化
                    if np.abs(audio_np).max() > 10:
                        print(f"  注意：保持原始範圍，類似 Gradio 的行為")
                    print("=" * 60)
                    debug_printed = True
                
                # 儲存音頻歷史
                self.audio_history.extend(audio_np)
                
                # 處理音頻（使用 test_kmu.py 的邏輯）
                predictions = self.process_audio_chunk(audio_np)
                
                # 儲存數據供視覺化使用
                if self.state:
                    # 獲取最新的分數
                    model_name = list(self.state.keys())[0]
                    if len(self.state[model_name]) > 0:
                        score = self.state[model_name][-1]
                        self.audio_queue.put((audio_np, score, model_name))
                        
                        # 如果分數高，打印訊息
                        current_time = time.time()
                        
                        if score > 0.5:
                            # 檢查是否在冷卻期內
                            if current_time - self.last_detection_time > self.detection_cooldown:
                                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                print(f"[{timestamp}] 🎯 檢測到喚醒詞！分數: {score:.3f}")
                                self.last_detection_time = current_time
                                # 記錄檢測位置（用於圖表標記）
                                if len(self.state[model_name]) > 0:
                                    self.detection_markers.append(len(self.state[model_name]) - 1)
                        elif score > 0.3:  # 低分數活動（僅用於調試）
                            if not hasattr(self, '_low_score_logged'):
                                self._low_score_logged = True
                                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                print(f"[{timestamp}] 檢測到低分活動: {score:.3f}")
                
            except Exception as e:
                print(f"音頻處理錯誤: {e}")
        
        self.stream.close()

    def update_plot(self, frame):
        """更新圖表"""
        # 清空佇列並更新數據
        latest_score = None
        while not self.audio_queue.empty():
            try:
                audio_chunk, score, model_name = self.audio_queue.get_nowait()
                latest_score = score
            except queue.Empty:
                break
        
        # 更新分數圖（使用 state 中的完整歷史）
        if self.state:
            model_name = list(self.state.keys())[0]
            scores = list(self.state[model_name])
            if len(scores) > 0:
                self.score_line.set_data(range(len(scores)), scores)
                self.ax1.set_xlim(0, max(60, len(scores)))
                
                # 動態調整 y 軸範圍
                max_score = max(scores) if scores else 1.0
                self.ax1.set_ylim(0, max(1.0, max_score * 1.1))
        
        # 更新音頻波形
        if len(self.audio_history) > 0:
            audio_data = list(self.audio_history)[-self.sample_rate:]  # 最後1秒
            self.audio_line.set_data(range(len(audio_data)), audio_data)
            self.ax2.set_xlim(0, len(audio_data))
        
        return self.score_line, self.audio_line

    def run(self):
        """執行視覺化"""
        if not self.model:
            print("模型載入失敗")
            return
        
        # 設置圖表
        plt.style.use("dark_background")
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        
        # 分數圖
        self.ax1.set_xlabel("時間 (幀)")
        self.ax1.set_ylabel("檢測分數")
        self.ax1.set_title("喚醒詞檢測分數 - hi_kmu_0721")
        self.ax1.grid(True, alpha=0.3)
        (self.score_line,) = self.ax1.plot([], [], "g-", linewidth=2)
        self.ax1.axhline(y=0.5, color="r", linestyle="--", label="閾值")
        self.ax1.legend()
        
        # 音頻波形圖
        self.ax2.set_xlabel("樣本")
        self.ax2.set_ylabel("振幅")
        self.ax2.set_title("音頻波形 (最近1秒)")
        self.ax2.grid(True, alpha=0.3)
        (self.audio_line,) = self.ax2.plot([], [], "b-", alpha=0.7)
        # 調整 y 軸範圍以適應實際的音頻數據範圍（約 -200 到 200）
        self.ax2.set_ylim(-500, 500)
        
        plt.tight_layout()
        
        # 啟動音頻處理線程
        self.is_running = True
        self.last_detection_time = 0  # 記錄上次檢測時間
        self.detection_cooldown = 0.8  # 冷卻期 0.8 秒
        audio_thread = threading.Thread(target=self.audio_callback)
        audio_thread.start()
        
        # 啟動動畫
        ani = FuncAnimation(self.fig, self.update_plot, interval=50, blit=True)
        
        try:
            plt.show()
        except KeyboardInterrupt:
            print("\n結束視覺化")
        finally:
            self.is_running = False
            audio_thread.join()
            self.p.terminate()
        
        # 顯示統計
        if self.state:
            model_name = list(self.state.keys())[0]
            scores = list(self.state[model_name])
            if scores:
                print(f"\n=== 統計資訊 ===")
                print(f"模型: {model_name}")
                print(f"最高分數: {max(scores):.3f}")
                print(f"平均分數: {np.mean(scores):.3f}")
                # 計算實際的喚醒詞檢測次數（考慮冷卻期）
                detection_count = 0
                last_detection = -self.detection_cooldown
                for i, s in enumerate(scores):
                    if s > 0.5:
                        # 計算時間差（假設每幀約 50ms）
                        time_diff = (i - last_detection) * 0.05
                        if time_diff >= self.detection_cooldown:
                            detection_count += 1
                            last_detection = i
                
                print(f"超過閾值次數: {sum(1 for s in scores if s > 0.5)} (原始)")
                print(f"實際檢測次數: {detection_count} (考慮冷卻期)")


def main():
    visualizer = WakeWordVisualizer()
    visualizer.run()


if __name__ == "__main__":
    main()