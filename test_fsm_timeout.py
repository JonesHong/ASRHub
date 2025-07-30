#!/usr/bin/env python3
"""
FSM 超時測試工具（簡化版）
直接測試 FSM 狀態機的超時機制，不需要音訊輸入
"""

import os
import sys
import asyncio
from datetime import datetime

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.fsm import StateMachine, State, Event
from src.config.manager import ConfigManager
from src.utils.logger import get_logger


class FSMTimeoutTester:
    """FSM 超時測試器"""
    
    def __init__(self):
        self.logger = get_logger("fsm_timeout_tester")
        self.config_manager = ConfigManager()
        
        # 初始化 FSM
        self.fsm = StateMachine(initial_state=State.IDLE)
        
        # 獲取超時配置
        if hasattr(self.config_manager, 'wake_word_detection'):
            self.wake_timeout = self.config_manager.wake_word_detection.wake_timeout
        else:
            self.wake_timeout = 3.0
        
        self.logger.info(f"超時設定: {self.wake_timeout} 秒")
        
        # 狀態歷史
        self.state_history = []
        self.timeout_task = None
        
        # 設定 FSM 回呼
        self._setup_fsm_callbacks()
    
    def _setup_fsm_callbacks(self):
        """設定 FSM 回呼"""
        # 進入 LISTENING 狀態時啟動超時
        self.fsm.add_on_enter_callback(State.LISTENING, self._on_enter_listening)
        
        # 離開 LISTENING 狀態時取消超時
        self.fsm.add_on_exit_callback(State.LISTENING, self._on_exit_listening)
        
        # 狀態轉換回呼
        self.fsm.add_on_transition_callback(self._on_state_transition)
    
    def _on_state_transition(self, old_state: State, new_state: State, **kwargs):
        """狀態轉換回呼"""
        timestamp = datetime.now()
        event = kwargs.get('event')
        
        self.state_history.append({
            "timestamp": timestamp,
            "old_state": old_state.value,
            "new_state": new_state.value,
            "event": event.value if event else None
        })
        
        self.logger.info(
            f"🔄 [{timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
            f"狀態轉換: {old_state.value} → {new_state.value}"
            f"{f' (事件: {event.value})' if event else ''}"
        )
    
    def _on_enter_listening(self, old_state: State, new_state: State, **kwargs):
        """進入 LISTENING 狀態的回呼"""
        self.logger.info(f"進入 LISTENING 狀態，啟動 {self.wake_timeout} 秒超時計時器")
        
        # 啟動超時任務
        if self.timeout_task:
            self.timeout_task.cancel()
        
        self.timeout_task = asyncio.create_task(self._timeout_handler())
    
    def _on_exit_listening(self, old_state: State, new_state: State, **kwargs):
        """離開 LISTENING 狀態的回呼"""
        self.logger.info("離開 LISTENING 狀態，取消超時計時器")
        
        # 取消超時任務
        if self.timeout_task:
            self.timeout_task.cancel()
            self.timeout_task = None
    
    async def _timeout_handler(self):
        """超時處理器"""
        try:
            await asyncio.sleep(self.wake_timeout)
            
            if self.fsm.is_listening():
                self.logger.warning("⏰ 觸發超時！返回 IDLE 狀態")
                self.fsm.trigger(Event.WAKE_TIMEOUT)
                
        except asyncio.CancelledError:
            self.logger.debug("超時計時器被取消")
    
    async def run_test(self):
        """運行測試"""
        self.logger.info("\n" + "="*60)
        self.logger.info("開始 FSM 超時測試")
        self.logger.info("="*60)
        
        # 步驟 1: 確認初始狀態
        self.logger.info(f"\n步驟 1: 檢查初始狀態")
        current_state = self.fsm.current_state
        self.logger.info(f"當前狀態: {current_state.value}")
        
        if current_state != State.IDLE:
            self.logger.error("系統不在 IDLE 狀態")
            return
        
        # 步驟 2: 觸發喚醒
        self.logger.info(f"\n步驟 2: 觸發喚醒（進入 LISTENING）")
        success = self.fsm.wake(wake_source="ui")
        
        if not success:
            self.logger.error("無法觸發喚醒")
            return
        
        await asyncio.sleep(0.1)  # 讓狀態轉換完成
        
        # 步驟 3: 等待超時
        self.logger.info(f"\n步驟 3: 等待 {self.wake_timeout} 秒，不做任何動作...")
        
        # 顯示倒數計時
        start_time = datetime.now()
        for i in range(int(self.wake_timeout) + 1):
            elapsed = (datetime.now() - start_time).total_seconds()
            remaining = max(0, self.wake_timeout - elapsed)
            
            current_state = self.fsm.current_state
            self.logger.info(
                f"⏱️ 時間: {elapsed:.1f}s / {self.wake_timeout}s | "
                f"剩餘: {remaining:.1f}s | "
                f"狀態: {current_state.value}"
            )
            
            if current_state == State.IDLE and elapsed < self.wake_timeout:
                self.logger.warning("提前返回 IDLE 狀態！")
                break
            
            await asyncio.sleep(1)
        
        # 額外等待確保處理完成
        await asyncio.sleep(0.5)
        
        # 步驟 4: 驗證結果
        self.logger.info(f"\n步驟 4: 驗證測試結果")
        final_state = self.fsm.current_state
        self.logger.info(f"最終狀態: {final_state.value}")
        
        # 分析結果
        self._analyze_results()
    
    def _analyze_results(self):
        """分析測試結果"""
        self.logger.info("\n" + "="*60)
        self.logger.info("測試結果分析")
        self.logger.info("="*60)
        
        # 顯示狀態歷史
        self.logger.info(f"\n📊 狀態轉換歷史 (共 {len(self.state_history)} 次):")
        
        wake_time = None
        timeout_time = None
        
        for i, change in enumerate(self.state_history):
            timestamp = change['timestamp']
            time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]
            
            self.logger.info(
                f"  {i+1}. [{time_str}] "
                f"{change['old_state']} → {change['new_state']}"
                f"{f' (事件: {change['event']})' if change['event'] else ''}"
            )
            
            # 記錄關鍵時間點
            if change['old_state'] == 'idle' and change['new_state'] == 'listening':
                wake_time = timestamp
            elif change['old_state'] == 'listening' and change['new_state'] == 'idle':
                if change['event'] == 'WAKE_TIMEOUT':
                    timeout_time = timestamp
        
        # 驗證結果
        self.logger.info("\n✅ 驗證結果:")
        
        # 檢查喚醒
        if wake_time:
            self.logger.info("  ✓ 成功從 IDLE 進入 LISTENING")
        else:
            self.logger.error("  ✗ 未能進入 LISTENING 狀態")
        
        # 檢查超時
        if timeout_time:
            self.logger.info("  ✓ 成功觸發超時機制")
            
            if wake_time:
                actual_timeout = (timeout_time - wake_time).total_seconds()
                self.logger.info(f"  ✓ 實際超時時間: {actual_timeout:.1f} 秒")
                
                # 驗證超時時間
                if abs(actual_timeout - self.wake_timeout) < 0.5:
                    self.logger.info(f"  ✓ 超時時間符合預期 ({self.wake_timeout} 秒)")
                else:
                    self.logger.warning(
                        f"  ⚠️ 超時時間有偏差 "
                        f"(預期: {self.wake_timeout}s, 實際: {actual_timeout:.1f}s)"
                    )
        else:
            self.logger.error("  ✗ 未觸發超時機制")
        
        # 檢查最終狀態
        final_state = self.fsm.current_state
        if final_state == State.IDLE:
            self.logger.info("  ✓ 最終返回 IDLE 狀態")
        else:
            self.logger.error(f"  ✗ 最終狀態錯誤: {final_state.value}")
        
        self.logger.info("="*60)
    
    async def test_interrupt(self):
        """測試中斷超時的情況"""
        self.logger.info("\n" + "="*60)
        self.logger.info("測試中斷超時")
        self.logger.info("="*60)
        
        # 清空歷史
        self.state_history.clear()
        
        # 觸發喚醒
        self.logger.info("觸發喚醒...")
        self.fsm.wake(wake_source="test")
        await asyncio.sleep(0.1)
        
        # 等待 1 秒
        self.logger.info("等待 1 秒...")
        await asyncio.sleep(1)
        
        # 手動觸發 ASR 開始（應該取消超時）
        self.logger.info("觸發 ASR_START（應該取消超時）...")
        self.fsm.trigger(Event.ASR_START)
        
        # 再等待超過超時時間
        self.logger.info(f"等待 {self.wake_timeout + 1} 秒...")
        await asyncio.sleep(self.wake_timeout + 1)
        
        # 檢查狀態
        final_state = self.fsm.current_state
        self.logger.info(f"最終狀態: {final_state.value}")
        
        if final_state == State.BUSY:
            self.logger.info("✓ 成功中斷超時，進入 BUSY 狀態")
        else:
            self.logger.error(f"✗ 狀態錯誤，預期 BUSY，實際: {final_state.value}")


async def main():
    """主函數"""
    print("🔍 FSM 超時測試工具")
    print(f"測試配置的超時機制")
    print()
    
    tester = FSMTimeoutTester()
    
    try:
        # 測試 1: 正常超時
        await tester.run_test()
        
        # 等待一下
        await asyncio.sleep(2)
        
        # 測試 2: 中斷超時
        await tester.test_interrupt()
        
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n錯誤: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())