#!/usr/bin/env python3
"""
喚醒詞觸發的自動錄音流程測試
整合 WakeWord → VAD → Recording 的完整流程
"""

import asyncio
import sys
import os
import time
import numpy as np
import pyaudio
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import queue
import threading

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.pipeline.operators.wakeword import OpenWakeWordOperator
from src.pipeline.operators.vad import SileroVADOperator
from src.pipeline.operators.recording import RecordingOperator
from src.core.fsm import StateMachine, State
from src.utils.logger import logger

# 設定中文字體（跨平台）
import platform
if platform.system() == "Windows":
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "sans-serif"]
else:
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# 解決 Windows 中文顯示問題
import matplotlib
matplotlib.use('TkAgg')



# 擴展狀態定義
class ExtendedState(State):
    """擴展的狀態定義"""
    IDLE = "idle"              # 待機，等待喚醒
    LISTENING = "listening"    # 監聽中，VAD 啟用
    RECORDING = "recording"    # 錄音中，VAD 控制結束
    PROCESSING = "processing"  # 處理中，錄音已結束


class WakeRecordFlow:
    """喚醒詞觸發的自動錄音流程"""
    
    def __init__(self):
        # 初始化 Operators
        self.wakeword_operator = OpenWakeWordOperator()
        
        # VAD 配置
        vad_config = {
            'threshold': 0.3,
            'min_silence_duration': 0.3,
            'min_speech_duration': 0.1,
            'adaptive_threshold': True,
            'smoothing_window': 3
        }
        self.vad_operator = SileroVADOperator(vad_config)
        
        self.recording_operator = RecordingOperator({
            'silence_countdown': 1.8,  # 靜音倒數秒數
            'vad_controlled': True,    # 啟用 VAD 控制
            'storage': {
                'type': 'file',
                'path': 'wake_recordings'
            }
        })
        
        # 狀態機
        self.fsm = StateMachine(initial_state=ExtendedState.IDLE)
        self._setup_fsm_transitions()
        
        # 音訊參數
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1280  # WakeWord 需要的大小
        self.format = pyaudio.paInt16
        
        # PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = None
        
        # 狀態
        self.is_running = False
        self.is_recording = False
        self.current_session_id = None
        
        # 倒數計時器
        self.countdown_visualizer = CountdownVisualizer()
        self.countdown_task = None
        
        # 視覺化
        self.audio_queue = queue.Queue()
        self.fig = None
        self.axes = None
        
        # 統計
        self.flow_stats = {
            'wake_detections': 0,
            'recordings_completed': 0,
            'auto_stops': 0,
            'manual_stops': 0,
            'total_speech_duration': 0.0,
            'total_recording_duration': 0.0
        }
    
    def _setup_fsm_transitions(self):
        """設定狀態轉換"""
        # IDLE → LISTENING (喚醒詞檢測)
        self.fsm.add_transition(
            from_state=ExtendedState.IDLE,
            to_state=ExtendedState.LISTENING,
            event='wake_detected'
        )
        
        # LISTENING → RECORDING (開始錄音)
        self.fsm.add_transition(
            from_state=ExtendedState.LISTENING,
            to_state=ExtendedState.RECORDING,
            event='start_recording'
        )
        
        # RECORDING → PROCESSING (VAD 倒數結束)
        self.fsm.add_transition(
            from_state=ExtendedState.RECORDING,
            to_state=ExtendedState.PROCESSING,
            event='recording_complete'
        )
        
        # PROCESSING → IDLE (處理完成)
        self.fsm.add_transition(
            from_state=ExtendedState.PROCESSING,
            to_state=ExtendedState.IDLE,
            event='processing_complete'
        )
        
        # 任何狀態 → IDLE (重置)
        for state in [ExtendedState.LISTENING, ExtendedState.RECORDING, ExtendedState.PROCESSING]:
            self.fsm.add_transition(
                from_state=state,
                to_state=ExtendedState.IDLE,
                event='reset'
            )
    
    async def setup(self):
        """設定流程環境"""
        logger.info("設定喚醒錄音流程...")
        
        try:
            # 創建錄音目錄
            Path('wake_recordings').mkdir(exist_ok=True)
            
            # 初始化所有 Operators
            await self.wakeword_operator.start()
            await self.vad_operator.start()
            await self.recording_operator.start()
            
            # 設定回調
            self.wakeword_operator.set_detection_callback(self.on_wake_detected)
            self.vad_operator.set_speech_callbacks(
                result_callback=self.on_vad_result
            )
            self.recording_operator.set_callbacks(
                recording_complete_callback=self.on_recording_complete
            )
            
            logger.info("✓ 喚醒錄音流程設定完成")
            
        except Exception as e:
            logger.error(f"設定失敗: {e}")
            raise
    
    async def cleanup(self):
        """清理資源"""
        logger.info("清理流程資源...")
        
        try:
            # 停止音訊流
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            
            self.p.terminate()
            
            # 停止所有 Operators
            await self.wakeword_operator.stop()
            await self.vad_operator.stop()
            await self.recording_operator.stop()
            
            logger.info("✓ 流程資源清理完成")
            
        except Exception as e:
            logger.error(f"清理錯誤: {e}")
    
    async def start(self):
        """開始流程"""
        logger.info("開始喚醒錄音流程")
        logger.info("請說出喚醒詞：'嗨，高醫' 或 'hi kmu'")
        
        # 開啟音訊流
        self.stream = self.p.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        
        self.is_running = True
        
        # 啟動音訊處理線程
        audio_thread = threading.Thread(target=self._audio_processing_loop)
        audio_thread.daemon = True
        audio_thread.start()
        
        # 啟動視覺化
        await self._start_visualization()
    
    def _audio_processing_loop(self):
        """音訊處理迴圈"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.is_running:
            try:
                # 讀取音訊
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # 根據狀態處理音訊
                current_state = self.fsm.get_state()
                
                if current_state == ExtendedState.IDLE:
                    # 待機狀態：只處理喚醒詞
                    loop.run_until_complete(self._process_wakeword(audio_data))
                    
                elif current_state in [ExtendedState.LISTENING, ExtendedState.RECORDING]:
                    # 監聽/錄音狀態：並行處理 VAD 和錄音
                    loop.run_until_complete(self._process_recording_and_vad(audio_data))
                
                # 視覺化資料
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                self.audio_queue.put({
                    'audio': audio_np,
                    'timestamp': time.time(),
                    'state': current_state,
                    'wake_score': getattr(self.wakeword_operator, 'latest_score', 0),
                    'vad_state': self.vad_operator.get_state() if current_state != ExtendedState.IDLE else None,
                    'recording_info': self.recording_operator.get_recording_info() if self.is_recording else None,
                    'countdown': self.countdown_visualizer.countdown_value
                })
                
            except Exception as e:
                logger.error(f"音訊處理錯誤: {e}")
                time.sleep(0.01)
        
        loop.close()
    
    async def _process_wakeword(self, audio_data: bytes):
        """處理喚醒詞檢測"""
        result = await self.wakeword_operator.process(
            audio_data,
            sample_rate=self.sample_rate,
            session_id="wake_session"
        )
    
    async def _process_recording_and_vad(self, audio_data: bytes):
        """並行處理錄音和 VAD"""
        # 並行處理
        recording_task = self.recording_operator.process(audio_data)
        vad_task = self.vad_operator.process(audio_data)
        
        await asyncio.gather(recording_task, vad_task)
    
    async def on_wake_detected(self, wake_event: dict):
        """喚醒詞檢測回調"""
        logger.info("🎤 檢測到喚醒詞，開始錄音...")
        
        self.flow_stats['wake_detections'] += 1
        
        # 狀態轉換：IDLE → LISTENING
        self.fsm.transition('wake_detected')
        
        # 生成 session ID
        self.current_session_id = f"wake_rec_{int(time.time())}"
        
        # 短暫延遲後開始錄音（讓用戶準備）
        await asyncio.sleep(0.5)
        
        # 開始錄音
        await self.recording_operator.start_recording(
            session_id=self.current_session_id
        )
        self.is_recording = True
        
        # 狀態轉換：LISTENING → RECORDING
        self.fsm.transition('start_recording')
        
        # 重置 VAD 狀態
        await self.vad_operator.reset_state()
        
        logger.info("開始錄音，請說話...")
    
    async def on_vad_result(self, vad_result: dict):
        """VAD 結果回調"""
        if self.is_recording and self.fsm.get_state() == ExtendedState.RECORDING:
            # 將 VAD 結果傳遞給錄音 Operator
            await self.recording_operator.on_vad_result(vad_result)
            
            # 更新倒數計時視覺化
            if not vad_result['speech_detected']:
                # 開始或更新倒數
                if self.recording_operator.is_countdown_active:
                    remaining_time = self.recording_operator.silence_countdown_duration
                    self.countdown_visualizer.update_countdown(remaining_time)
                    
                    # 如果還沒有倒數任務，創建一個
                    if not self.countdown_task or self.countdown_task.done():
                        self.countdown_task = asyncio.create_task(
                            self._countdown_animation()
                        )
            else:
                # 檢測到語音，重置倒數
                self.countdown_visualizer.update_countdown(0)
                if self.countdown_task and not self.countdown_task.done():
                    self.countdown_task.cancel()
    
    async def _countdown_animation(self):
        """倒數動畫"""
        start_time = time.time()
        duration = self.recording_operator.silence_countdown_duration
        
        while self.is_recording:
            elapsed = time.time() - start_time
            remaining = max(0, duration - elapsed)
            
            self.countdown_visualizer.update_countdown(remaining)
            
            if remaining <= 0:
                break
            
            await asyncio.sleep(0.1)
    
    async def on_recording_complete(self, info: dict):
        """錄音完成回調"""
        logger.info(f"錄音完成: 時長 {info['duration']:.2f}s")
        
        self.is_recording = False
        self.flow_stats['recordings_completed'] += 1
        
        # 判斷是否自動停止
        if info['duration'] < 60:  # 假設最大錄音時長是 60 秒
            self.flow_stats['auto_stops'] += 1
        else:
            self.flow_stats['manual_stops'] += 1
        
        self.flow_stats['total_recording_duration'] += info['duration']
        
        # 狀態轉換：RECORDING → PROCESSING
        self.fsm.transition('recording_complete')
        
        # 模擬處理過程
        await asyncio.sleep(1.0)
        
        # 狀態轉換：PROCESSING → IDLE
        self.fsm.transition('processing_complete')
        
        logger.info("返回待機狀態，等待下一次喚醒...")
    
    async def _start_visualization(self):
        """啟動視覺化"""
        logger.info("啟動流程視覺化...")
        
        # 設定圖表
        plt.style.use("dark_background")
        self.fig, self.axes = plt.subplots(4, 1, figsize=(12, 12))
        
        # 音訊波形
        ax1 = self.axes[0]
        ax1.set_title("音訊波形")
        ax1.set_xlabel("樣本")
        ax1.set_ylabel("振幅")
        ax1.grid(True, alpha=0.3)
        self.audio_line, = ax1.plot([], [], 'b-', alpha=0.7)
        
        # 喚醒詞分數
        ax2 = self.axes[1]
        ax2.set_title("喚醒詞檢測")
        ax2.set_xlabel("時間")
        ax2.set_ylabel("分數")
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 1.1)
        self.wake_scatter = ax2.scatter([], [], c='r', s=50)
        
        # 狀態和倒數
        ax3 = self.axes[2]
        ax3.set_title("系統狀態")
        ax3.axis('off')
        self.state_text = ax3.text(0.05, 0.5, "", fontsize=14, verticalalignment='center')
        
        # 統計資訊
        ax4 = self.axes[3]
        ax4.set_title("流程統計")
        ax4.axis('off')
        self.stats_text = ax4.text(0.05, 0.5, "", fontsize=12, verticalalignment='center')
        
        plt.tight_layout()
        
        # 啟動動畫
        ani = FuncAnimation(self.fig, self._update_plot, interval=100, blit=False)
        
        try:
            plt.show()
        except KeyboardInterrupt:
            logger.info("視覺化被用戶中斷")
        finally:
            self.is_running = False
    
    def _update_plot(self, frame):
        """更新圖表"""
        # 處理佇列
        latest_data = None
        while not self.audio_queue.empty():
            try:
                latest_data = self.audio_queue.get_nowait()
            except queue.Empty:
                break
        
        if latest_data:
            # 更新音訊波形
            audio_data = latest_data['audio']
            self.audio_line.set_data(range(len(audio_data)), audio_data)
            self.axes[0].set_xlim(0, len(audio_data))
            self.axes[0].set_ylim(-32768, 32767)
            
            # 更新狀態顯示
            state = latest_data['state']
            countdown = latest_data['countdown']
            
            state_text = f"""
當前狀態: {self._get_state_display(state)}

"""
            
            if state == ExtendedState.RECORDING and countdown > 0:
                # 顯示倒數計時
                bar = self.countdown_visualizer.get_progress_bar()
                state_text += f"靜音倒數: {bar} {countdown:.1f}s\n"
            
            if latest_data['recording_info'] and latest_data['recording_info']['is_recording']:
                duration = latest_data['recording_info']['duration']
                state_text += f"錄音時長: {duration:.1f}s\n"
            
            self.state_text.set_text(state_text)
            
            # 更新統計
            stats_text = f"""
喚醒次數: {self.flow_stats['wake_detections']}
完成錄音: {self.flow_stats['recordings_completed']}
自動停止: {self.flow_stats['auto_stops']}
手動停止: {self.flow_stats['manual_stops']}
總錄音時長: {self.flow_stats['total_recording_duration']:.1f}s
"""
            self.stats_text.set_text(stats_text)
        
        return self.audio_line, self.state_text, self.stats_text
    
    def _get_state_display(self, state):
        """獲取狀態顯示文字"""
        state_map = {
            ExtendedState.IDLE: "🟢 待機中（等待喚醒詞）",
            ExtendedState.LISTENING: "🟡 監聽中（準備錄音）",
            ExtendedState.RECORDING: "🔴 錄音中（VAD 監控）",
            ExtendedState.PROCESSING: "🔵 處理中"
        }
        return state_map.get(state, state)
    
    def print_flow_statistics(self):
        """打印流程統計"""
        print("\n" + "="*60)
        print("📊 喚醒錄音流程統計")
        print("="*60)
        
        print(f"\n喚醒詞檢測:")
        print(f"  總檢測次數: {self.flow_stats['wake_detections']}")
        
        print(f"\n錄音統計:")
        print(f"  完成錄音數: {self.flow_stats['recordings_completed']}")
        print(f"  自動停止: {self.flow_stats['auto_stops']}")
        print(f"  手動停止: {self.flow_stats['manual_stops']}")
        print(f"  總錄音時長: {self.flow_stats['total_recording_duration']:.1f}s")
        
        if self.flow_stats['recordings_completed'] > 0:
            avg_duration = self.flow_stats['total_recording_duration'] / self.flow_stats['recordings_completed']
            print(f"  平均錄音時長: {avg_duration:.1f}s")
        
        print("="*60)


class CountdownVisualizer:
    """倒數計時器視覺化"""
    
    def __init__(self):
        self.countdown_value = 0
        self.max_countdown = 1.8
    
    def update_countdown(self, remaining_time: float):
        """更新倒數顯示"""
        self.countdown_value = remaining_time
    
    def get_progress_bar(self) -> str:
        """獲取進度條字符串"""
        if self.countdown_value <= 0:
            return ""
        
        progress = self.countdown_value / self.max_countdown
        bar_length = int(progress * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        return f"[{bar}]"
    
    def print_countdown(self):
        """打印倒數（終端模式）"""
        bar = self.get_progress_bar()
        print(f"\r倒數計時: {bar} {self.countdown_value:.1f}s", end="", flush=True)


async def test_scenarios():
    """測試不同場景"""
    print("\n🧪 測試場景模式")
    print("1. 正常對話：說話 → 短暫停頓 → 繼續說話")
    print("2. 結束對話：說話 → 靜音 1.8s → 自動停止")
    print("3. 長對話：持續說話直到最大時長")
    print("4. 噪音干擾：背景噪音測試")
    
    # TODO: 實作測試場景
    pass


async def main():
    """主函數"""
    print("🎙️ 喚醒詞觸發自動錄音流程")
    print("-" * 60)
    print("說出喚醒詞開始錄音，靜音 1.8 秒自動停止")
    print("支援的喚醒詞：'嗨，高醫' 或 'hi kmu'")
    print("-" * 60)
    
    flow = WakeRecordFlow()
    
    try:
        # 設定流程
        await flow.setup()
        
        # 檢查環境變數
        if not os.environ.get("HF_TOKEN"):
            print("\n⚠️  警告: 未設定 HF_TOKEN 環境變數")
            print("如果需要下載模型，請設定: export HF_TOKEN=your_token")
        
        # 開始流程
        await flow.start()
        
    except KeyboardInterrupt:
        print("\n流程被用戶中斷")
    except Exception as e:
        print(f"\n流程錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理資源
        await flow.cleanup()
        
        # 打印統計
        flow.print_flow_statistics()


if __name__ == "__main__":
    asyncio.run(main())