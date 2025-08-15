"""
ASRHub + PyStoreX 整合概念驗證（POC）
使用新的 feature-based Redux 架構
展示如何使用 PyStoreX 管理 FSM 狀態和事件
需要安裝：pip install pystorex reactivex
"""

# 添加專案根目錄到 Python 路徑
import os
import sys
import time  # 保留 time.sleep 使用
import asyncio


from src.utils.logger import logger
from src.utils.time_provider import TimeProvider

from src.store import (
    # Store 配置
    ASRHubStore,
    configure_global_store,
    get_global_store,
    
    # Sessions 域
    FSMStateEnum,
    create_session,
    start_listening,
    wake_triggered,
    start_recording,
    end_recording,
    start_streaming,
    end_streaming,
    begin_transcription,
    transcription_done,
    reset_fsm,
    audio_chunk_received,
    session_error,
    destroy_session,
    
    # Sessions Selectors
    get_session,
    get_active_session,
    get_session_fsm_state,
    get_sessions_by_state,
    get_session_states_summary,
    get_active_sessions,
    can_create_new_session,
    
    # Stats 域
    session_created_stat,
    session_destroyed_stat,
    wake_word_detected_stat,
    recording_started_stat,
    recording_completed_stat,
    transcription_requested_stat,
    transcription_completed_stat,
    audio_chunk_received_stat,
    error_occurred_stat,
    update_response_time_stat,
    
    # Stats Selectors
    get_stats_summary,
    get_system_health_score,
    get_performance_metrics,
    get_quality_metrics
)


class ASRHubPOC:
    """ASR Hub PyStoreX 概念驗證"""
    
    def __init__(self):
        self.store = None
        self.session_counter = 0
        
    def setup_store(self):
        """設置 Redux Store"""
        print("🔧 設置 ASR Hub Redux Store...")
        
        # 配置 Store
        self.store = configure_global_store(logger=logger)
        
        # 訂閱狀態變更
        self.store.subscribe(self._on_state_change)
        
        print("✅ Redux Store 設置完成")
        print("📊 初始狀態已就緒")
        
    def _on_state_change(self, new_state=None):
        """狀態變更監聽器
        
        RxPy 會傳遞新狀態作為參數
        """
        try:
            # 使用傳入的新狀態或從 store 獲取
            state = new_state if new_state is not None else self.store.get_state()
            
            if state and 'sessions' in state and 'sessions' in state['sessions']:
                active_count = len([
                    s for s in state['sessions']['sessions'].values()
                    if s['fsm_state'] != FSMStateEnum.IDLE
                ])
                if active_count > 0:
                    print(f"📈 狀態更新 - 活躍會話: {active_count}")
        except Exception as e:
            logger.warning(f"狀態變更監聽器錯誤: {e}")
    
    def create_test_session(self) -> str:
        """創建測試會話"""
        self.session_counter += 1
        session_id = f"poc_session_{self.session_counter:03d}"
        
        print(f"\n👤 創建會話: {session_id}")
        
        # 檢查是否可以創建新會話
        can_create_selector = can_create_new_session()
        state = self.store.get_state()
        
        if not can_create_selector(state):
            print("❌ 無法創建會話：已達到最大會話數限制")
            return None
            
        # 創建會話和統計
        self.store.dispatch(create_session(session_id))
        self.store.dispatch(session_created_stat(session_id))
        
        # 調試：檢查統計狀態
        state = self.store.get_state()
        if 'stats' in state:
            print(f"   📍 調試 - 創建會話後 sessions_created: {state['stats'].get('sessions_created', 'N/A')}")
        
        # 驗證會話創建
        session_selector = get_session(session_id)
        session = session_selector(self.store.get_state())
        
        if session:
            print(f"✅ 會話創建成功 - 狀態: {session['fsm_state'].value}")
            return session_id
        else:
            print("❌ 會話創建失敗")
            return None
    
    def simulate_fsm_workflow(self, session_id: str):
        """模擬 FSM 工作流程"""
        print(f"\n🎬 開始 FSM 工作流程模擬 - 會話: {session_id}")
        
        try:
            # 1. 開始監聽
            print("1️⃣ 開始監聽...")
            self.store.dispatch(start_listening(session_id))
            self._print_session_state(session_id)
            time.sleep(0.2)
            
            # 2. 檢測喚醒詞
            print("2️⃣ 檢測到喚醒詞...")
            confidence = 0.92
            self.store.dispatch(wake_triggered(
                session_id, 
                confidence=confidence, 
                trigger="voice_activation"
            ))
            self.store.dispatch(wake_word_detected_stat(
                session_id, 
                confidence=confidence, 
                trigger_type="voice_activation"
            ))
            self._print_session_state(session_id)
            time.sleep(0.2)
            
            # 3. 開始錄音
            print("3️⃣ 開始錄音...")
            self.store.dispatch(start_recording(session_id, "voice_activation"))
            self.store.dispatch(recording_started_stat(session_id, "voice_activation"))
            self._print_session_state(session_id)
            
            # 4. 模擬音訊數據
            print("4️⃣ 接收音訊數據...")
            for i in range(3):
                chunk_size = 1024 * (i + 1)
                self.store.dispatch(audio_chunk_received(session_id, chunk_size))
                self.store.dispatch(audio_chunk_received_stat(session_id, chunk_size))
                time.sleep(0.1)
            
            # 5. 結束錄音
            print("5️⃣ 結束錄音...")
            recording_duration = 2.5
            self.store.dispatch(end_recording(session_id, "voice_end", recording_duration))
            self.store.dispatch(recording_completed_stat(
                session_id, 
                duration=recording_duration, 
                trigger="voice_end"
            ))
            self._print_session_state(session_id)
            time.sleep(0.2)
            
            # 6. 開始轉譯
            print("6️⃣ 開始轉譯...")
            start_time = TimeProvider.now()
            self.store.dispatch(begin_transcription(session_id))
            self.store.dispatch(transcription_requested_stat(session_id, "whisper"))
            self._print_session_state(session_id)
            time.sleep(1.0)  # 模擬轉譯時間
            
            # 7. 完成轉譯
            print("7️⃣ 完成轉譯...")
            transcription_result = "這是一個模擬的語音轉譯結果"
            transcription_duration = TimeProvider.now() - start_time
            
            self.store.dispatch(transcription_done(session_id, transcription_result))
            self.store.dispatch(transcription_completed_stat(
                session_id, 
                duration=transcription_duration, 
                result_length=len(transcription_result)
            ))
            self.store.dispatch(update_response_time_stat(
                "transcription", 
                transcription_duration
            ))
            
            self._print_session_state(session_id)
            print(f"📝 轉譯結果: {transcription_result}")
            
            print("✅ FSM 工作流程完成")
            
        except Exception as e:
            print(f"❌ FSM 工作流程錯誤: {e}")
            self.store.dispatch(session_error(session_id, str(e)))
            self.store.dispatch(error_occurred_stat(session_id, "workflow_error", str(e)))
    
    def simulate_error_scenario(self, session_id: str):
        """模擬錯誤場景"""
        print(f"\n⚠️ 模擬錯誤場景 - 會話: {session_id}")
        
        # 模擬網路錯誤
        error_message = "網路連接超時"
        self.store.dispatch(session_error(session_id, error_message))
        self.store.dispatch(error_occurred_stat(session_id, "network_timeout", error_message))
        
        self._print_session_state(session_id)
        
        # 重置 FSM
        print("🔄 重置 FSM...")
        self.store.dispatch(reset_fsm(session_id))
        self._print_session_state(session_id)
    
    def _print_session_state(self, session_id: str):
        """打印會話狀態"""
        try:
            session_selector = get_session(session_id)
            state = self.store.get_state()
            session = session_selector(state)
            
            if session:
                fsm_state = session['fsm_state'].value
                audio_size = len(session['audio_buffer'])
                error = session.get('error', 'None')
                print(f"   📊 狀態: {fsm_state} | 音訊: {audio_size}B | 錯誤: {error}")
        except Exception as e:
            print(f"   ❌ 無法獲取會話狀態: {e}")
    
    def demonstrate_multi_session(self):
        """演示多會話管理"""
        print("\n👥 多會話管理演示")
        
        session_ids = []
        for i in range(3):
            session_id = self.create_test_session()
            if session_id:
                session_ids.append(session_id)
                
                # 為每個會話設置不同狀態
                if i == 0:
                    self.store.dispatch(start_listening(session_id))
                elif i == 1:
                    self.store.dispatch(start_listening(session_id))
                    self.store.dispatch(wake_triggered(session_id, confidence=0.88, trigger="manual"))
                elif i == 2:
                    self.store.dispatch(start_listening(session_id))
                    self.store.dispatch(wake_triggered(session_id, confidence=0.95, trigger="hotword"))
                    self.store.dispatch(start_recording(session_id, "hotword"))
        
        # 顯示狀態摘要
        state = self.store.get_state()
        summary = get_session_states_summary(state)
        
        print("\n📊 會話狀態摘要:")
        for state_name, count in summary.items():
            if count > 0:
                print(f"   {state_name}: {count} 個會話")
        
        # 清理會話
        for session_id in session_ids:
            self.store.dispatch(destroy_session(session_id))
            self.store.dispatch(session_destroyed_stat(session_id))
        
        print("🧹 會話已清理")
    
    def show_statistics(self):
        """顯示統計信息"""
        print("\n📈 系統統計信息")
        
        state = self.store.get_state()
        
        # 統計摘要
        stats_summary_selector = get_stats_summary()
        summary = stats_summary_selector(state)
        
        # 調試：直接查看 stats 域
        if 'stats' in state and state['stats']:
            print(f"📍 調試 - sessions_created: {state['stats'].get('sessions_created', 'N/A')}")
            print(f"📍 調試 - sessions_destroyed: {state['stats'].get('sessions_destroyed', 'N/A')}")
        
        print("📊 統計摘要:")
        for key, value in summary.items():
            print(f"   {key}: {value}")
        
        # 系統健康評分
        health_score = get_system_health_score(state)
        print(f"\n🏥 系統健康評分: {health_score:.2f}%")
        
        # 性能指標
        performance_selector = get_performance_metrics()
        perf_metrics = performance_selector(state)
        
        print("\n⚡ 性能指標:")
        for key, value in perf_metrics.items():
            print(f"   {key}: {value}")
        
        # 品質指標
        quality_selector = get_quality_metrics()
        quality_metrics = quality_selector(state)
        
        print("\n🎯 品質指標:")
        for key, value in quality_metrics.items():
            print(f"   {key}: {value}")
    
    def run_complete_poc(self):
        """運行完整的 POC 演示"""
        print("🚀 ASR Hub + PyStoreX POC 演示開始")
        print("=" * 60)
        
        # 設置 Store
        self.setup_store()
        
        # 創建測試會話並運行工作流程
        session_id = self.create_test_session()
        if session_id:
            self.simulate_fsm_workflow(session_id)
            self.simulate_error_scenario(session_id)
            # 銷毀第一個會話
            self.store.dispatch(destroy_session(session_id))
            self.store.dispatch(session_destroyed_stat(session_id))
            print(f"🧹 會話 {session_id} 已銷毀")
        
        # 多會話演示
        self.demonstrate_multi_session()
        
        # 顯示統計信息
        self.show_statistics()
        
        print("\n" + "=" * 60)
        print("🎉 POC 演示完成！")
        
        # 最終狀態
        final_state = self.store.get_state()
        print(f"\n📋 最終狀態:")
        if final_state and 'sessions' in final_state and final_state['sessions']:
            sessions_count = len(final_state['sessions'].get('sessions', {}))
            print(f"   會話總數: {sessions_count}")
        else:
            print(f"   會話總數: 0")
        
        if final_state and 'stats' in final_state and final_state['stats']:
            started_at = final_state['stats'].get('stats_started_at')
            if started_at:
                runtime = TimeProvider.now() - started_at
                print(f"   運行時間: {runtime:.2f}秒")
            else:
                print(f"   運行時間: N/A（統計未初始化）")
        else:
            print(f"   運行時間: N/A")


def main():
    """主函數"""
    poc = ASRHubPOC()
    poc.run_complete_poc()


if __name__ == "__main__":
    main()