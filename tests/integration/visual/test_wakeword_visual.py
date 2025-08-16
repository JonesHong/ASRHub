#!/usr/bin/env python3
"""
ASR Hub 喚醒詞整合測試工具
測試 OpenWakeWordOperator 與 SystemListener 的整合功能
"""

import asyncio
import os
import sys
import numpy as np
import pyaudio
from datetime import datetime
import queue
import threading
from typing import Dict, Any, Optional
import time

# 添加 src 到路徑以便導入模組
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))

from src.pipeline.operators.wakeword import OpenWakeWordOperator
from src.core.system_listener import SystemListener
from src.store import get_global_store
from src.store.sessions import sessions_actions
from src.utils.logger import logger
from src.config.manager import ConfigManager
from src.utils.visualization import WakeWordVisualization
from pystorex.middleware import LoggerMiddleware
from src.store.sessions.sessions_selectors import (
    get_session
)


class WakeWordIntegrationTester:
    """喚醒詞整合測試器"""
    
    def __init__(self):
        """初始化測試器"""
        
        # 音訊參數
        self.chunk_size = 1280
        self.sample_rate = 16000
        self.channels = 1
        self.format = pyaudio.paInt16
        
        # 喚醒詞設定
        self.wake_word = "hi_kmu"  # 預設喚醒詞
        self.score_threshold = 0.5  # 檢測閾值
        
        # 測試組件
        self.wakeword_operator = None
        self.system_listener = None
        self.store = None  # 使用 store 替代 session_manager
        
        # 音訊處理
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_running = False
        
        # 資料儲存
        self.detection_events = []
        self.score_history = []
        
        # 視覺化
        self.visualization = WakeWordVisualization()
        self.timestamps = []
        
        # 統計資訊
        self.stats = {
            "total_detections": 0,
            "false_positives": 0,
            "missed_detections": 0,
            "avg_score": 0.0,
            "max_score": 0.0,
            "min_score": 1.0,
            "start_time": None
        }
        
        # PyStoreX 監控相關
        self.state_subscription = None
        self.action_log = []
        self.state_changes = []
        self.test_session_id = "test_session"
    
    async def setup(self):
        """設定測試環境"""
        logger.info("設定喚醒詞整合測試環境...")
        
        try:
            # 初始化 Store 並啟用 LoggerMiddleware
            self.store = get_global_store()
            
            # 應用 LoggerMiddleware 進行調試（如果尚未應用）
            if not hasattr(self.store, '_logger_middleware_applied'):
                self.store.apply_middleware(LoggerMiddleware)
                self.store._logger_middleware_applied = True
                logger.info("✓ LoggerMiddleware 已啟用")
            
            # 設置狀態監控訂閱
            self._setup_state_monitoring()
            
            # 創建測試 session
            await self._create_test_session()
            
            # 初始化 OpenWakeWord Operator
            self.wakeword_operator = OpenWakeWordOperator()
            self.wakeword_operator.set_detection_callback(self._on_detection)
            await self.wakeword_operator.start()
            
            # 初始化 System Listener
            self.system_listener = SystemListener()
            self.system_listener.register_event_handler("wake_detected", self._on_system_wake)
            self.system_listener.register_event_handler("state_changed", self._on_state_change)
            await self.system_listener.start()
            
            logger.info("✓ 測試環境設定完成")
            
        except Exception as e:
            logger.error(f"設定失敗: {e}")
            raise
    
    def _setup_state_monitoring(self):
        """設置 PyStoreX 狀態監控
        
        使用 store.select() 和 subscribe() 來追蹤狀態變化
        """
        logger.info("設置 PyStoreX 狀態監控...")
        
        # 監聽完整狀態變化
        self.state_subscription = self.store._state_subject.subscribe(
            lambda state: self._on_state_update(state)
        )
        
        # 監聽特定 session 的狀態變化
        if hasattr(self.store, 'select'):
            # 使用 selector 監聽特定 session
            # get_session 返回一個 selector，需要正確使用它
            session_selector = get_session(self.test_session_id)
            self.session_subscription = self.store.select(
                session_selector
            ).subscribe(
                lambda session_data: self._on_session_update(session_data)
            )
        
        # 監聽 action 流（用於記錄所有 dispatch 的 actions）
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
        
        # 調試輸出（可選）
        if hasattr(state, 'sessions') and state.sessions:
            session_count = len(state.sessions.get('sessions', {}))
            logger.debug(f"[{timestamp}] State updated - Sessions: {session_count}")
    
    def _on_session_update(self, session_data):
        """處理特定 session 的更新"""
        # session_data 可能是單個 session 物件，而不是 tuple
        if session_data:
            # 如果是 tuple/list 格式（包含前後狀態）
            if isinstance(session_data, (tuple, list)) and len(session_data) > 1:
                prev_session, curr_session = session_data
            else:
                # 否則當作當前 session 處理
                curr_session = session_data
            
            if curr_session and isinstance(curr_session, dict):
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                logger.info(
                    f"[{timestamp}] Session {self.test_session_id} updated:\n"
                    f"  FSM State: {curr_session.get('fsm_state')}\n"
                    f"  Mode: {curr_session.get('mode')}\n"
                    f"  Audio Buffer Size: {len(curr_session.get('audio_buffer', []))}"
                )
    
    def _on_action_dispatched(self, action):
        """處理 action dispatch 事件"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # 記錄 action
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
            "[Session] Wake Triggered",
            "[Session] Start Recording", 
            "[Session] End Recording",
            "[Session] Speech Detected",
            "[Session] Silence Detected",
            "[Session] Transcription Done"
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
        
        # 設置為 active session
        # self.store.dispatch(
        #     sessions_actions.set_active_session(self.test_session_id)
        # )
        
        logger.info(f"✓ 測試 session {self.test_session_id} 已創建")
    
    async def cleanup(self):
        """清理測試環境"""
        logger.info("清理測試環境...")
        
        try:
            # 停止音訊處理
            self.is_running = False
            
            # 清理 PyStoreX 訂閱
            if self.state_subscription:
                self.state_subscription.dispose()
            if hasattr(self, 'session_subscription') and self.session_subscription:
                self.session_subscription.dispose()
            if hasattr(self, 'action_subscription') and self.action_subscription:
                self.action_subscription.dispose()
            
            # 清理 SystemListener
            if self.system_listener:
                try:
                    await self.system_listener.stop()
                except Exception as e:
                    logger.error(f"停止 SystemListener 時發生錯誤: {e}")
            
            # 清理 WakeWord Operator
            if self.wakeword_operator:
                try:
                    await self.wakeword_operator.stop()
                except Exception as e:
                    logger.error(f"停止 WakeWordOperator 時發生錯誤: {e}")
            
            # 清理音訊流
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except Exception as e:
                    logger.error(f"關閉音訊流時發生錯誤: {e}")
            
            # 清理 PyAudio
            if hasattr(self, 'p') and self.p:
                try:
                    self.p.terminate()
                except Exception as e:
                    logger.error(f"終止 PyAudio 時發生錯誤: {e}")
            
            logger.info("✓ 測試環境清理完成")
            
        except Exception as e:
            logger.error(f"清理過程中發生未預期的錯誤: {e}")
    
    def start_audio_capture(self):
        """開始音訊捕獲"""
        try:
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
                    self.sample_rate = test_rate
                    logger.info(f"使用採樣率: {test_rate} Hz")
                    break
                except Exception as e:
                    logger.warning(f"無法使用採樣率 {test_rate}: {e}")
                    continue
            
            if not self.stream:
                raise Exception("無法開啟音訊流")
            
            self.is_running = True
            self.stats["start_time"] = datetime.now()
            
            # 啟動音訊處理線程
            audio_thread = threading.Thread(target=self._audio_processing_loop)
            audio_thread.daemon = True
            audio_thread.start()
            
            logger.info("✓ 音訊捕獲已啟動")
            
        except Exception as e:
            logger.error(f"音訊捕獲啟動失敗: {e}")
            raise
    
    def _audio_processing_loop(self):
        """音訊處理主迴圈"""
        logger.info("開始音訊處理迴圈...")
        
        # 為這個線程創建新的事件循環
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            while self.is_running:
                try:
                    # 檢查流是否還有效
                    if not self.stream or not hasattr(self.stream, 'read'):
                        logger.warning("音訊流無效，退出處理迴圈")
                        break
                    
                    # 讀取音訊資料
                    audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    if not audio_data:
                        time.sleep(0.01)
                        continue
                    
                    # 轉換為 numpy array
                    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    
                    # 檢查 wakeword_operator 是否有效
                    if not self.wakeword_operator:
                        continue
                    
                    # 在線程中運行 async 函數
                    try:
                        result = loop.run_until_complete(
                            self.wakeword_operator.process(
                                audio_data,
                                sample_rate=self.sample_rate,
                                session_id=self.test_session_id
                            )
                        )
                        
                        # Dispatch audio_chunk_received action 到 PyStoreX
                        # if self.store:
                        #     self.store.dispatch(
                        #         sessions_actions.audio_chunk_received(
                        #             self.test_session_id,
                        #             len(audio_data)
                        #         )
                        #     )
                    except Exception as e:
                        logger.error(f"喚醒詞處理錯誤: {e}")
                        continue
                    
                    # 獲取最新分數
                    try:
                        latest_score = self.wakeword_operator.get_latest_score()
                        if latest_score is not None:
                            current_time = time.time()
                            self.score_history.append(latest_score)
                            self.timestamps.append(current_time)
                            
                            # 更新統計
                            if latest_score > self.stats["max_score"]:
                                self.stats["max_score"] = latest_score
                            if latest_score < self.stats["min_score"]:
                                self.stats["min_score"] = latest_score
                            
                            # 計算平均分數
                            if self.score_history:
                                self.stats["avg_score"] = sum(self.score_history) / len(self.score_history)
                            
                            # 將資料放入視覺化佇列
                            if hasattr(self, 'visualization') and self.visualization:
                                self.visualization.add_data({
                                    "audio": audio_np,
                                    "score": latest_score,
                                    "timestamp": current_time,
                                    "wake_word": self.wake_word,
                                    "threshold": self.score_threshold
                                })
                    except Exception as e:
                        logger.error(f"分數處理錯誤: {e}")
                    
                except Exception as e:
                    logger.error(f"音訊處理錯誤: {e}")
                    time.sleep(0.01)
        
        except Exception as e:
            logger.error(f"音訊處理迴圈發生嚴重錯誤: {e}")
        finally:
            # 關閉循環
            try:
                loop.close()
            except Exception as e:
                logger.error(f"關閉事件循環時發生錯誤: {e}")
            
            logger.info("音訊處理迴圈已結束")
    
    async def _on_detection(self, detection: Dict[str, Any]):
        """喚醒詞偵測回呼"""
        self.stats["total_detections"] += 1
        self.detection_events.append({
            "timestamp": datetime.now(),
            "detection": detection,
            "source": "operator"
        })
        
        logger.info(
            f"🎯 Operator 偵測到喚醒詞！"
            f"模型: {detection.get('model')}, "
            f"分數: {detection.get('score', 0):.3f}"
        )
        
        # Dispatch wake_triggered action 到 PyStoreX
        if self.store:
            self.store.dispatch(
                sessions_actions.wake_triggered(
                    self.test_session_id,
                    confidence=detection.get('score', 0),
                    trigger="wake_word"
                )
            )
    
    async def _on_system_wake(self, wake_data: Dict[str, Any]):
        """系統喚醒事件回呼"""
        self.detection_events.append({
            "timestamp": datetime.now(),
            "detection": wake_data,
            "source": "system"
        })
        
        logger.info(
            f"🔔 SystemListener 偵測到喚醒！"
            f"來源: {wake_data.get('source')}"
        )
    
    async def _on_state_change(self, state_data: Dict[str, Any]):
        """狀態變更事件回呼"""
        logger.info(
            f"🔄 系統狀態變更: "
            f"{state_data.get('old_state')} -> {state_data.get('new_state')}"
        )
    
    def start_visualization(self):
        """啟動視覺化監控"""
        logger.info("啟動視覺化監控...")
        
        # 設定圖表
        self.visualization.setup_plot()
        
        # 啟動動畫
        self.visualization.start_animation(self._update_plot, interval=100)
    
    def _update_plot(self, frame):
        """更新圖表"""
        try:
            # 獲取最新數據
            latest_data = self.visualization.get_latest_data()
            
            if latest_data:
                # 更新音訊波形
                audio_data = latest_data['audio']
                if hasattr(self.visualization, 'update_audio_plot'):
                    self.visualization.update_audio_plot(audio_data)
                
                # 更新分數歷史
                current_score = latest_data['score']
                current_time = latest_data['timestamp']
                threshold = latest_data.get('threshold', 0.5)
                
                # 更新喚醒詞檢測圖表
                if hasattr(self.visualization, 'update_wakeword_plot'):
                    self.visualization.update_wakeword_plot(current_score, current_time, threshold)
                
                # 更新統計文字
                if hasattr(self.visualization, 'texts') and 'stats' in self.visualization.texts:
                    runtime = (datetime.now() - self.stats["start_time"]).total_seconds() if self.stats["start_time"] else 0
                    total_detections = len(self.detection_events)
                    avg_score = sum(self.score_history) / len(self.score_history) if self.score_history else 0
                    max_score = max(self.score_history) if self.score_history else 0
                    
                    stats_text = (
                        f"[{self.wake_word}] 運行: {self.visualization.format_time(runtime)} | "
                        f"檢測: {total_detections} 次 | 平均: {avg_score:.3f} | 最高: {max_score:.3f}\n"
                        f"當前: {current_score:.3f} | 閾值: {threshold:.3f}"
                    )
                    
                    self.visualization.texts['stats'].set_text(stats_text)
        
        except Exception as e:
            logger.error(f"更新圖表時發生錯誤: {e}")
        
        return []
    
    def print_test_results(self):
        """打印測試結果"""
        print("\n" + "="*60)
        print("📊 喚醒詞整合測試結果")
        print("="*60)
        
        runtime = (datetime.now() - self.stats["start_time"]).total_seconds() if self.stats["start_time"] else 0
        
        print(f"🕒 運行時間: {runtime:.1f} 秒")
        print(f"🎯 總偵測次數: {self.stats['total_detections']}")
        print(f"📈 平均分數: {self.stats['avg_score']:.3f}")
        print(f"📊 最高分數: {self.stats['max_score']:.3f}")
        print(f"📉 最低分數: {self.stats['min_score']:.3f}")
        print(f"📋 偵測事件數: {len(self.detection_events)}")
        
        if self.detection_events:
            print(f"\n🔍 最近 5 個偵測事件:")
            for event in self.detection_events[-5:]:
                timestamp = event["timestamp"].strftime("%H:%M:%S.%f")[:-3]
                source = event["source"]
                detection = event["detection"]
                score = detection.get("score", "N/A")
                print(f"  [{timestamp}] {source}: {score}")
        
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
            "[Session] Wake Triggered",
            "[Session] Start Recording",
            "[Session] End Recording",
            "[Session] Speech Detected",
            "[Session] Silence Detected",
            "[Session] Transcription Done"
        ]]
        
        if important_actions:
            print(f"\n  🎯 最近 5 個重要 Actions:")
            for action in important_actions[-5:]:
                print(f"    [{action['timestamp']}] {action['type']}")
        
        print("="*60)


async def main():
    """主函數"""
    print("🚀 ASR Hub 喚醒詞整合測試工具")
    print("請確保已安裝 openwakeword 和相關依賴")
    print("請說出喚醒詞：'嗨，高醫' 或 'hi kmu'")
    print("按 Ctrl+C 結束測試\n")
    
    tester = WakeWordIntegrationTester()
    
    try:
        # 設定測試環境
        await tester.setup()
        
        # 開始音訊捕獲
        tester.start_audio_capture()
        
        # 啟動視覺化（這會阻塞直到窗口關閉）
        tester.start_visualization()
        
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n測試錯誤: {e}")
    finally:
        # 清理資源
        await tester.cleanup()
        
        # 打印結果
        tester.print_test_results()


if __name__ == "__main__":
    # 檢查必要的環境變數
    if not os.environ.get("HF_TOKEN"):
        print("⚠️  警告: 未設定 HF_TOKEN 環境變數")
        print("如果需要下載 HuggingFace 模型，請設定此變數")
        print("export HF_TOKEN=your_token_here\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程式被用戶中斷")
    except Exception as e:
        print(f"\n程式錯誤: {e}")
        sys.exit(1)