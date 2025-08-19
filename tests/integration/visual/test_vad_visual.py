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

from src.operators.vad import SileroVADOperator
from src.operators.vad.events import VADEvent, VADEventData
from src.operators.vad.statistics import VADFrame, VADStatisticsCollector
from src.operators.audio_format.scipy_operator import ScipyAudioFormatOperator
from src.audio import AudioMetadata, AudioSampleFormat
from src.utils.logger import logger
from src.utils.visualization import VADVisualization
from src.store import get_global_store
from src.store.sessions import sessions_actions
from pystorex.middleware import LoggerMiddleware
from src.store.sessions.sessions_selectors import (
    get_session
)
from datetime import datetime


class VADIntegrationTester:
    """VAD 功能整合測試"""
    
    def __init__(self):
        # PyStoreX 相關（初始化時先設為 None）
        self.store = None
        self.state_subscription = None
        self.session_subscription = None
        self.action_subscription = None
        self.action_log = []
        self.state_changes = []
        self.test_session_id = "test_vad"
        
        # 初始化 VAD operator（稍後會注入 store）
        self.vad_operator = None
        
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
            # 初始化 Store 並啟用 LoggerMiddleware
            self.store = get_global_store()
            
            # 應用 LoggerMiddleware 進行調試（如果尚未應用）
            # if not hasattr(self.store, '_logger_middleware_applied'):
            #     self.store.apply_middleware(LoggerMiddleware)
            #     self.store._logger_middleware_applied = True
            #     logger.info("✓ LoggerMiddleware 已啟用")
            
            # 設置狀態監控訂閱
            self._setup_state_monitoring()
            
            # 創建測試 session
            await self._create_test_session()
            
            # 初始化 VAD operator（不再需要注入 store）
            self.vad_operator = SileroVADOperator()
            
            # 更新配置以適合測試
            self.vad_operator.update_config({
                'threshold': 0.5,  # 標準門檻值
                'min_silence_duration': 0.3,
                'min_speech_duration': 0.1,
                'adaptive_threshold': False,  # 關閉自適應閾值避免過度敏感
                'smoothing_window': 10  # 增大平滑窗口減少抖動
            })
            
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
            
            # 清理 PyStoreX 訂閱
            if self.state_subscription:
                self.state_subscription.dispose()
            if self.session_subscription:
                self.session_subscription.dispose()
            if self.action_subscription:
                self.action_subscription.dispose()
            
            # 停止音訊流
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                except Exception as e:
                    logger.error(f"關閉音訊流時發生錯誤: {e}")
            
            # 清理 PyAudio
            if hasattr(self, 'p') and self.p:
                try:
                    self.p.terminate()
                except Exception as e:
                    logger.error(f"終止 PyAudio 時發生錯誤: {e}")
            
            # 停止 VAD operator
            if self.vad_operator:
                try:
                    await self.vad_operator.stop()
                except Exception as e:
                    logger.error(f"停止 VAD operator 時發生錯誤: {e}")
            
            logger.info("✓ 測試環境清理完成")
            
        except Exception as e:
            logger.error(f"清理過程中發生未預期的錯誤: {e}")
    
    def _setup_state_monitoring(self):
        """設置 PyStoreX 狀態監控"""
        logger.info("設置 PyStoreX 狀態監控...")
        
        # 監聽完整狀態變化
        self.state_subscription = self.store._state_subject.subscribe(
            lambda state: self._on_state_update(state)
        )
        
        # 監聽特定 session 的狀態變化
        if hasattr(self.store, 'select'):
            session_selector = get_session(self.test_session_id)
            self.session_subscription = self.store.select(
                session_selector
            ).subscribe(
                lambda session_data: self._on_session_update(session_data)
            )
        
        # 監聽 action 流
        if hasattr(self.store, 'action_stream'):
            self.action_subscription = self.store.action_stream.subscribe(
                lambda action: self._on_action_dispatched(action)
            )
        
        logger.info("✓ 狀態監控已設置")
    
    def _on_state_update(self, state):
        """處理狀態更新事件"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # 記錄狀態變化
        self.state_changes.append({
            "timestamp": timestamp,
            "state": state
        })
        
        # 只保留最近 100 條記錄
        if len(self.state_changes) > 100:
            self.state_changes = self.state_changes[-100:]
    
    def _on_session_update(self, session_data):
        """處理特定 session 的更新"""
        if session_data:
            if isinstance(session_data, (tuple, list)) and len(session_data) > 1:
                prev_session, curr_session = session_data
            else:
                prev_session = None
                curr_session = session_data
            
            if curr_session and isinstance(curr_session, dict):
                # 只在狀態有顯著變化時記錄
                if prev_session and isinstance(prev_session, dict):
                    # 檢查是否有重要的狀態變化
                    fsm_changed = prev_session.get('fsm_state') != curr_session.get('fsm_state')
                    vad_changed = prev_session.get('vad_state') != curr_session.get('vad_state')
                    
                    if fsm_changed or vad_changed:
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        logger.info(
                            f"[{timestamp}] Session {self.test_session_id} state changed:\n"
                            f"  FSM State: {prev_session.get('fsm_state')} → {curr_session.get('fsm_state')}\n"
                            f"  VAD State: {prev_session.get('vad_state')} → {curr_session.get('vad_state')}"
                        )
    
    def _on_action_dispatched(self, action):
        """處理 action dispatch 事件"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # 記錄 action（但不包括太頻繁的）
        if action.type != "[Session] Audio Chunk Received":
            self.action_log.append({
                "timestamp": timestamp,
                "type": action.type,
                "payload": action.payload
            })
        
        # 只保留最近 200 條 action
        if len(self.action_log) > 200:
            self.action_log = self.action_log[-200:]
        
        # 對重要 action 進行特殊處理和記錄
        important_actions = [
            "[Session] Speech Detected",
            "[Session] Silence Started",    # 新增：靜音開始事件
            "[Session] Silence Detected",
            "[Session] VAD State Changed",
            "[Session] Start Recording",
            "[Session] End Recording"
        ]
        
        if action.type in important_actions:
            logger.info(
                f"🎯 [{timestamp}] Action: {action.type}\n"
                f"   Payload: {action.payload}"
            )
    
    async def _create_test_session(self):
        """創建測試用的 session"""
        logger.info(f"創建測試 session: {self.test_session_id}")
        
        # Dispatch create_session action
        self.store.dispatch(
            sessions_actions.create_session(
                self.test_session_id,
                strategy="streaming"  # 使用串流模式以啟用所有功能
            )
        )
        
        # 等待一下讓 SessionEffects 處理 create_session 並創建 timer
        await asyncio.sleep(0.5)
        
        # 確認 timer 已創建
        from src.core.timer_manager import timer_manager
        timer = timer_manager.get_timer(self.test_session_id)
        if timer:
            logger.info(f"✓ 測試 session {self.test_session_id} 已創建，Timer 已初始化")
        else:
            logger.warning(f"⚠️ Timer 未創建，手動創建 timer")
            await timer_manager.create_timer(self.test_session_id)
            logger.info(f"✓ 手動創建 timer 成功")
        
        logger.info(f"✓ 測試 session {self.test_session_id} 已完全準備就緒")
    
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
            format=AudioSampleFormat.INT16
        )
        
        # 執行 VAD
        result = await self.vad_operator.process(audio_data, metadata=metadata, session_id=self.test_session_id)
        
        # 獲取 VAD 狀態
        vad_state = self.vad_operator.get_info()
        
        # Dispatch audio_chunk_received action 到 PyStoreX
        # 註解掉以減少日誌輸出頻率
        # if self.store:
        #     self.store.dispatch(
        #         sessions_actions.audio_chunk_received(
        #             self.test_session_id,
        #             chunk_size=len(audio_data),  # 只傳遞大小
        #             timestamp=time.time()
        #         )
        #     )
        
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
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        confidence = event_data.get('speech_probability', 0)
        
        logger.info(
            f"\n{'='*50}\n"
            f"🎤 [{timestamp}] 偵測到語音開始！\n"
            f"   信心度: {confidence:.1%}\n"
            f"   閾值: {self.vad_operator.threshold:.3f}\n"
            f"{'='*50}"
        )
        
        # Dispatch speech_detected action 到 PyStoreX
        if self.store:
            self.store.dispatch(
                sessions_actions.speech_detected(
                    self.test_session_id,
                    confidence=confidence
                )
            )
    
    async def _on_speech_end(self, event_data: Dict[str, Any]):
        """語音結束事件 - 只記錄，不觸發倒數"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        duration = event_data.get('speech_duration', 0)
        
        logger.info(
            f"\n{'='*50}\n"
            f"🔇 [{timestamp}] 語音結束，進入靜音狀態\n"
            f"   語音持續時長: {duration:.2f} 秒\n"
            f"   等待靜音確認: {self.vad_operator.min_silence_duration} 秒\n"
            f"{'='*50}"
        )
        
        # 注意：不要在這裡 dispatch silence_detected！
        # silence_detected 應該由 VAD operator 在靜音持續一定時間後自動觸發
        # 這樣倒數計時器才會在正確的時機開始
    
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
        
        # PyStoreX 統計
        print(f"\n📦 PyStoreX 統計:")
        print(f"  📨 總 Actions 數: {len(self.action_log)}")
        print(f"  🔄 狀態變化數: {len(self.state_changes)}")
        
        # 顯示最常見的 action 類型
        if self.action_log:
            action_types = {}
            for action in self.action_log:
                action_type = action["type"]
                action_types[action_type] = action_types.get(action_type, 0) + 1
            
            print(f"\n  📊 Action 類型分布:")
            sorted_types = sorted(action_types.items(), key=lambda x: x[1], reverse=True)
            for action_type, count in sorted_types[:5]:
                print(f"    {action_type}: {count} 次")
        
        # 顯示最近的重要 actions
        important_actions = [a for a in self.action_log if a["type"] in [
            "[Session] Speech Detected",
            "[Session] Silence Started",    # 新增：靜音開始事件
            "[Session] Silence Detected",
            "[Session] VAD State Changed",
            "[Session] Start Recording",
            "[Session] End Recording"
        ]]
        
        if important_actions:
            print(f"\n  🎯 最近 5 個重要 Actions:")
            for action in important_actions[-5:]:
                print(f"    [{action['timestamp']}] {action['type']}")
        
        print("="*60)


async def main():
    """主函數"""
    print("\n" + "="*60)
    print("🎯 VAD 整合測試工具")
    print("="*60)
    print("\n📍 專注監控以下關鍵事件：")
    print("  • 🎤 語音開始偵測")
    print("  • 🔇 靜音達到閾值")
    print("  • 📊 狀態變化")
    print("\n請對著麥克風說話，觀察 VAD 檢測效果")
    print("按 Ctrl+C 或關閉視窗結束測試")
    print("="*60 + "\n")
    
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