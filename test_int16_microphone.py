#!/usr/bin/env python3
"""
完整測試 ASRHub 管道流程

測試項目：
1. 麥克風擷取 (int16 格式)
2. 關鍵字檢測 (OpenWakeWord)
3. VAD 檢測 (Silero VAD)
4. 錄音功能
5. ASR 轉譯 (使用 MVP Provider)

透過 PyStoreX 事件驅動和無狀態服務組合
"""

import time
import signal
import numpy as np
import uuid6

from src.utils.logger import logger
from src.service.microphone_capture.microphone_capture import microphone_capture
from src.service.wakeword.openwakeword import openwakeword
from src.core.audio_queue_manager import audio_queue
from src.interface.audio import AudioChunk
from src.interface.wakeword import WakewordDetection

# 導入 PyStoreX 相關模組
from src.store.main_store import store
from src.store.sessions.sessions_action import create_session, start_listening, receive_audio_chunk
from src.interface.strategy import Strategy


class ASRHubPipelineTest:
    """完整測試 ASRHub 管道流程"""
    
    def __init__(self):
        self.session_id = str(uuid6.uuid7())
        self.is_running = False
        self.start_time = None
        self.action_subscription = None  # PyStoreX action stream 訂閱
        
        # 測試統計
        self.wakeword_count = 0      # 關鍵字檢測次數
        self.vad_speech_count = 0    # VAD 語音檢測次數
        self.vad_silence_count = 0   # VAD 靜音檢測次數
        self.recording_count = 0     # 錄音次數
        self.transcription_count = 0 # 轉譯次數
        self.audio_count = 0         # 音訊 chunks 數
        
        # 音訊格式檢查
        self.received_dtypes = set()
        self.audio_ranges = []
        
        # 最近的轉譯結果
        self.last_transcriptions = []
        
        # 設定信號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """優雅停止"""
        logger.info("🛑 接收到停止信號...")
        self.stop_test()
    
    def on_wakeword_detected(self, detection: WakewordDetection):
        """喚醒詞檢測回調"""
        if not self.start_time:
            return
            
        current_time = time.time() - self.start_time
        # 不要在這裡增加計數，因為會在 handle_action 中計數
        # self.wakeword_count += 1
        
        logger.info(f"🎯 檢測到喚醒詞: {detection.keyword} (信心度: {detection.confidence:.4f}) @ {current_time:.2f}s")
        
        # 記錄檢測時的音訊統計
        if self.audio_ranges:
            recent_range = self.audio_ranges[-5:]  # 最近5個audio chunk的範圍
            avg_range = np.mean([r[1] - r[0] for r in recent_range])
            logger.info(f"   📊 最近音訊範圍平均: {avg_range:.1f}")
        
        # 透過 PyStoreX 觸發喚醒事件
        from src.store.sessions.sessions_action import wake_activated
        action = wake_activated(self.session_id, "wakeword")
        store.dispatch(action)
    
    def setup_store_listeners(self):
        """設定 Store 事件監聽器"""
        # 監聽 VAD 事件
        def on_vad_speech(state):
            """VAD 檢測到語音"""
            self.vad_speech_count += 1
            current_time = time.time() - self.start_time if self.start_time else 0
            logger.info(f"🎤 VAD: 檢測到語音 @ {current_time:.2f}s (總計: {self.vad_speech_count} 次)")
        
        def on_vad_silence(state):
            """VAD 檢測到靜音"""
            self.vad_silence_count += 1
            current_time = time.time() - self.start_time if self.start_time else 0
            logger.debug(f"🤫 VAD: 檢測到靜音 @ {current_time:.2f}s (總計: {self.vad_silence_count} 次)")
        
        def on_recording_started(state):
            """開始錄音"""
            self.recording_count += 1
            current_time = time.time() - self.start_time if self.start_time else 0
            logger.info(f"⏺️ 開始錄音 @ {current_time:.2f}s (第 {self.recording_count} 次)")
        
        def on_recording_stopped(state):
            """停止錄音"""
            current_time = time.time() - self.start_time if self.start_time else 0
            logger.info(f"⏹️ 停止錄音 @ {current_time:.2f}s")
        
        def on_transcription_done(state):
            """轉譯完成"""
            self.transcription_count += 1
            current_time = time.time() - self.start_time if self.start_time else 0
            
            # 嘗試從 state 取得轉譯結果
            try:
                from src.store.sessions.sessions_selector import get_session_by_id
                session = get_session_by_id(state, self.session_id)
                if session and hasattr(session, 'transcription_result'):
                    result = session.transcription_result
                    if result and hasattr(result, 'full_text'):
                        text = result.full_text.strip()
                        if text:
                            self.last_transcriptions.append(text)
                            logger.info(f"📝 轉譯結果: \"{text}\" @ {current_time:.2f}s")
                        else:
                            logger.warning(f"📝 轉譯結果為空 @ {current_time:.2f}s")
                else:
                    logger.info(f"📝 轉譯完成 @ {current_time:.2f}s (總計: {self.transcription_count} 次)")
            except Exception as e:
                logger.debug(f"無法取得轉譯結果: {e}")
                logger.info(f"📝 轉譯完成 @ {current_time:.2f}s (總計: {self.transcription_count} 次)")
        
        # 訂閱事件的處理函數
        def handle_action(action):
            """處理 Store 的 action 事件"""
            # action 可能是 dict 或 Action 物件
            if hasattr(action, 'type'):
                action_type = action.type
            else:
                action_type = action.get('type', '') if isinstance(action, dict) else ''
            
            # 輸出以追蹤問題 (除非是非常頻繁的 action)
            if 'Receive Audio Chunk' not in action_type and 'Emit Audio Chunk' not in action_type:
                logger.debug(f"收到 action: {action_type}")
            
            # 根據 action 類型處理不同事件 - 使用完全匹配
            if action_type == '[Session] Vad Speech Detected':
                # 獲取當前狀態
                state = store.get_state()
                on_vad_speech(state)
            elif action_type == '[Session] Vad Silence Detected':
                state = store.get_state()
                on_vad_silence(state)
            elif action_type == '[Session] Record Started':
                state = store.get_state()
                on_recording_started(state)
            elif action_type == '[Session] Record Stopped':
                state = store.get_state()
                on_recording_stopped(state)
            elif action_type == '[Session] Transcribe Done':
                state = store.get_state()
                on_transcription_done(state)
            elif action_type == '[Session] Wake Activated':
                # 也計數喚醒事件
                self.wakeword_count += 1
                logger.info(f"🎯 喚醒事件觸發 (總計: {self.wakeword_count} 次)")
        
        # 訂閱 action stream
        self.action_subscription = store._action_subject.subscribe(handle_action)
    
    def _audio_callback_with_monitoring(self, audio_data: np.ndarray, sample_rate: int):
        """音訊回調 - 監控格式並傳送到系統"""
        if not self.session_id or not self.is_running:
            return
            
        try:
            self.audio_count += 1
            
            # 檢查音訊格式
            self.received_dtypes.add(str(audio_data.dtype))
            
            # 記錄音訊範圍
            audio_min, audio_max = audio_data.min(), audio_data.max()
            self.audio_ranges.append((audio_min, audio_max))
            if len(self.audio_ranges) > 100:  # 只保留最近100個
                self.audio_ranges.pop(0)
            
            # 每50個chunk報告一次格式資訊
            if self.audio_count % 50 == 0:
                current_time = time.time() - self.start_time
                logger.info(f"📊 音訊統計 @ {current_time:.1f}s:")
                logger.info(f"   • 總音訊 chunks: {self.audio_count}")
                logger.info(f"   • 檢測到的 dtypes: {self.received_dtypes}")
                logger.info(f"   • 當前音訊範圍: [{audio_min}, {audio_max}]")
                logger.info(f"   • 音訊佇列大小: {audio_queue.size(self.session_id)}")
                logger.info(f"   • 喚醒詞檢測: {self.wakeword_count} 次")
            
            # 創建 AudioChunk 並發送到系統
            audio_chunk = AudioChunk(
                data=audio_data.tobytes(),
                sample_rate=sample_rate,
                channels=1,
                timestamp=None
            )
            
            # 透過 PyStoreX 分發事件 - 只需要 session_id 和音訊資料
            action = receive_audio_chunk(
                session_id=self.session_id,
                audio_data=audio_data.tobytes()
            )
            store.dispatch(action)
            
        except Exception as e:
            logger.error(f"音訊回調錯誤: {e}")
    
    def start_test(self):
        """啟動測試"""
        logger.info("🚀 啟動 ASRHub 完整管道測試")
        logger.info("=" * 60)
        
        # 設定 Store 事件監聽器
        self.setup_store_listeners()
        logger.info("✅ Store 事件監聽器已設定")
        
        # 初始化服務
        if not openwakeword.is_initialized():
            openwakeword.initialize()
        
        # 設定麥克風參數（現在應該強制 int16）
        success = microphone_capture.set_parameters(
            sample_rate=16000,
            channels=1,
            chunk_size=1024
        )
        
        if not success:
            raise RuntimeError("無法設定麥克風參數")
        
        # 顯示麥克風設定
        logger.info(f"📱 麥克風設定:")
        logger.info(f"   • Sample Rate: 16000 Hz")
        logger.info(f"   • Channels: 1")
        logger.info(f"   • Chunk Size: 1024")
        logger.info(f"   • Format: int16 (強制)")
        
        # 建立 session 和設定音訊配置
        # 根據正確的事件順序：
        # 1. CREATE_SESSION - 只需要 strategy
        # 2. START_LISTENING - 設定音訊參數 (sample_rate, channels, format)
        # 3. RECEIVE_AUDIO_CHUNK - 接收音訊資料
        
        # Step 1: 建立 session (只需要 strategy)
        create_action = create_session(
            strategy=Strategy.NON_STREAMING
        )
        store.dispatch(create_action)
        
        # 從 store 取得新建立的 session_id
        from src.store.sessions.sessions_selector import get_all_sessions
        all_sessions = get_all_sessions(store.state)
        
        # 取得最新的 session_id (最後加入的)
        if all_sessions:
            session_ids = list(all_sessions.keys())
            if session_ids:
                self.session_id = session_ids[-1]  # 使用最新的
                logger.info(f"使用 Store 中的 session_id: {self.session_id}")
        
        # Step 2: 使用 START_LISTENING 設定音訊配置
        # 這是正確設定音訊參數的地方
        listen_action = start_listening(
            session_id=self.session_id,
            sample_rate=16000,
            channels=1,
            format="int16"
        )
        store.dispatch(listen_action)
        logger.info(f"已為 session {self.session_id} 設定音訊配置")
        
        # 開始監聽服務
        logger.info(f"🔍 開始 OpenWakeWord 監聽，session_id: {self.session_id}")
        wakeword_success = openwakeword.start_listening(
            session_id=self.session_id,
            callback=self.on_wakeword_detected
        )
        logger.info(f"✅ OpenWakeWord 監聽狀態: {wakeword_success}")
        
        if not wakeword_success:
            raise RuntimeError("無法啟動 OpenWakeword 服務")
        
        # 啟動麥克風擷取
        logger.info("🎙️ 開始麥克風擷取...")
        success = microphone_capture.start_capture(callback=self._audio_callback_with_monitoring)
        
        if not success:
            raise RuntimeError("無法啟動麥克風擷取")
        
        self.is_running = True
        self.start_time = time.time()
        
        logger.info("🎯 ASRHub 管道測試進行中...")
        logger.info("📝 測試項目:")
        logger.info("   • 麥克風擷取 (int16 格式)")
        logger.info("   • 關鍵字檢測 (OpenWakeWord)")
        logger.info("   • VAD 檢測 (Silero VAD)")
        logger.info("   • 錄音功能")
        logger.info("   • ASR 轉譯 (MVP Provider)")
        logger.info("")
        logger.info("💡 測試流程:")
        logger.info("   1. 說出關鍵字觸發喚醒")
        logger.info("   2. VAD 會檢測語音活動")
        logger.info("   3. 系統自動錄音")
        logger.info("   4. 靜音後停止錄音並轉譯")
        logger.info("")
        logger.info("⏹️  按 Ctrl+C 停止測試")
        logger.info("=" * 60)
        
        # 測試迴圈
        self.run_test_loop()
    
    def run_test_loop(self):
        """主測試迴圈"""
        try:
            while self.is_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("收到中斷信號")
        finally:
            self.stop_test()
    
    def stop_test(self):
        """停止測試"""
        if not self.is_running:
            return
            
        logger.info("🛑 停止測試...")
        self.is_running = False
        
        # 停止服務
        microphone_capture.stop_capture()
        openwakeword.stop_listening(self.session_id)
        
        # 清理訂閱
        if hasattr(self, 'action_subscription'):
            self.action_subscription.dispose()
            logger.debug("已清理 action stream 訂閱")
        
        # 顯示最終統計
        if self.start_time:
            total_time = time.time() - self.start_time
            logger.info("=" * 60)
            logger.info("📊 最終測試統計:")
            logger.info(f"   • 總運行時間: {total_time:.1f} 秒")
            logger.info(f"   • 總音訊 chunks: {self.audio_count}")
            logger.info(f"   • 檢測到的音訊格式: {self.received_dtypes}")
            logger.info("")
            
            # 功能統計
            logger.info("📈 功能測試結果:")
            logger.info(f"   • 關鍵字檢測: {self.wakeword_count} 次")
            logger.info(f"   • VAD 語音檢測: {self.vad_speech_count} 次")
            logger.info(f"   • VAD 靜音檢測: {self.vad_silence_count} 次")
            logger.info(f"   • 錄音次數: {self.recording_count} 次")
            logger.info(f"   • 轉譯次數: {self.transcription_count} 次")
            
            # 音訊範圍統計
            if self.audio_ranges:
                all_ranges = [r[1] - r[0] for r in self.audio_ranges]
                logger.info("")
                logger.info("📊 音訊動態範圍統計:")
                logger.info(f"   • 最小範圍: {min(all_ranges):.1f}")
                logger.info(f"   • 最大範圍: {max(all_ranges):.1f}")
                logger.info(f"   • 平均範圍: {np.mean(all_ranges):.1f}")
            
            # 轉譯結果
            if self.last_transcriptions:
                logger.info("")
                logger.info("📝 最近的轉譯結果:")
                for i, text in enumerate(self.last_transcriptions[-5:], 1):  # 顯示最後5個
                    logger.info(f"   {i}. \"{text}\"")
            
            # 功能狀態評估
            logger.info("")
            logger.info("✅ 功能狀態:")
            
            if self.wakeword_count > 0:
                detection_rate = self.wakeword_count / total_time * 60
                logger.info(f"   • 關鍵字檢測: 正常 ({detection_rate:.2f} 次/分鐘)")
            else:
                logger.warning("   • 關鍵字檢測: ⚠️ 未檢測到")
            
            if self.vad_speech_count > 0:
                logger.info(f"   • VAD 檢測: 正常")
            else:
                logger.warning("   • VAD 檢測: ⚠️ 未檢測到語音")
            
            if self.recording_count > 0:
                logger.info(f"   • 錄音功能: 正常")
            else:
                logger.warning("   • 錄音功能: ⚠️ 未觸發錄音")
            
            if self.transcription_count > 0:
                logger.info(f"   • ASR 轉譯: 正常 (MVP Provider)")
            else:
                logger.warning("   • ASR 轉譯: ⚠️ 未執行轉譯")
        
        logger.info("=" * 60)
        logger.info("✅ ASRHub 管道測試完成")


def main():
    """主程式"""
    test = ASRHubPipelineTest()
    try:
        test.start_test()
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}")
        test.stop_test()


if __name__ == "__main__":
    main()