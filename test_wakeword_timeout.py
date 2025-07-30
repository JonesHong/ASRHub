#!/usr/bin/env python3
"""
喚醒詞超時測試工具
測試 3 秒超時機制：偵測到喚醒詞後，如果 3 秒內沒有進一步動作，系統會返回 IDLE 狀態
"""

import os
import sys
import asyncio
import time
from datetime import datetime

# 添加 src 到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.system_listener import SystemListener
from src.core.fsm import State
from src.utils.logger import get_logger


class WakeWordTimeoutTester:
    """喚醒詞超時測試器"""
    
    def __init__(self):
        self.logger = get_logger("timeout_tester")
        self.system_listener = None
        
        # 狀態追蹤
        self.state_history = []
        self.wake_events = []
        self.timeout_events = []
    
    async def setup(self):
        """設定測試環境"""
        self.logger.info("設定超時測試環境...")
        
        # 初始化系統監聽器
        self.system_listener = SystemListener()
        
        # 註冊事件處理器
        self.system_listener.register_event_handler("wake_detected", self._on_wake_detected)
        self.system_listener.register_event_handler("state_changed", self._on_state_changed)
        
        # 從配置讀取超時時間
        wake_timeout = self.system_listener.wake_timeout
        self.logger.info(f"喚醒超時設定: {wake_timeout} 秒")
        
        # 啟動系統監聽器
        await self.system_listener.start()
        
        self.logger.info("✓ 測試環境設定完成")
    
    async def _on_wake_detected(self, event_data):
        """喚醒事件處理器"""
        timestamp = datetime.now()
        self.wake_events.append({
            "timestamp": timestamp,
            "data": event_data
        })
        
        self.logger.info(
            f"🎯 [{timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
            f"喚醒事件 - 來源: {event_data.get('source')}"
        )
    
    async def _on_state_changed(self, event_data):
        """狀態變更事件處理器"""
        timestamp = datetime.now()
        old_state = event_data.get('old_state')
        new_state = event_data.get('new_state')
        
        self.state_history.append({
            "timestamp": timestamp,
            "old_state": old_state,
            "new_state": new_state,
            "event": event_data.get('event')
        })
        
        self.logger.info(
            f"🔄 [{timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
            f"狀態變更: {old_state} → {new_state}"
        )
        
        # 檢測超時事件
        if old_state == "listening" and new_state == "idle":
            self.timeout_events.append({
                "timestamp": timestamp,
                "event": event_data.get('event')
            })
            self.logger.warning(f"⏰ 偵測到超時事件！")
    
    async def trigger_wake_word(self):
        """手動觸發喚醒（模擬）"""
        self.logger.info("🗣️ 模擬喚醒詞觸發...")
        
        # 透過 UI 喚醒來模擬（因為實際喚醒詞需要音訊輸入）
        success = await self.system_listener.wake_from_ui()
        
        if success:
            self.logger.info("✓ 成功觸發喚醒")
        else:
            self.logger.error("✗ 喚醒失敗（可能不在 IDLE 狀態）")
        
        return success
    
    async def run_timeout_test(self):
        """運行超時測試"""
        self.logger.info("\n" + "="*60)
        self.logger.info("開始超時測試")
        self.logger.info("="*60)
        
        # 確保開始於 IDLE 狀態
        current_state = self.system_listener.fsm.get_state()
        self.logger.info(f"當前狀態: {current_state.value}")
        
        if current_state != State.IDLE:
            self.logger.warning("系統不在 IDLE 狀態，等待返回...")
            await asyncio.sleep(5)
        
        # 步驟 1: 觸發喚醒
        self.logger.info("\n步驟 1: 觸發喚醒詞")
        wake_success = await self.trigger_wake_word()
        
        if not wake_success:
            self.logger.error("無法觸發喚醒，測試中止")
            return
        
        # 等待狀態變更
        await asyncio.sleep(0.5)
        
        # 步驟 2: 等待超時
        wake_timeout = self.system_listener.wake_timeout
        self.logger.info(f"\n步驟 2: 等待 {wake_timeout} 秒超時...")
        
        # 顯示倒數計時
        for i in range(int(wake_timeout)):
            remaining = wake_timeout - i
            self.logger.info(f"⏱️ 剩餘時間: {remaining:.0f} 秒")
            await asyncio.sleep(1)
        
        # 額外等待確保超時處理完成
        self.logger.info("等待超時處理...")
        await asyncio.sleep(1)
        
        # 步驟 3: 驗證結果
        self.logger.info("\n步驟 3: 驗證測試結果")
        final_state = self.system_listener.fsm.get_state()
        self.logger.info(f"最終狀態: {final_state.value}")
        
        # 分析結果
        self._analyze_results()
    
    def _analyze_results(self):
        """分析測試結果"""
        self.logger.info("\n" + "="*60)
        self.logger.info("測試結果分析")
        self.logger.info("="*60)
        
        # 狀態歷史
        self.logger.info(f"\n📊 狀態轉換歷史 (共 {len(self.state_history)} 次):")
        for i, state_change in enumerate(self.state_history):
            timestamp = state_change['timestamp'].strftime('%H:%M:%S.%f')[:-3]
            old_state = state_change['old_state']
            new_state = state_change['new_state']
            event = state_change['event']
            
            self.logger.info(
                f"  {i+1}. [{timestamp}] {old_state} → {new_state}"
                f"{f' (事件: {event})' if event else ''}"
            )
        
        # 喚醒事件
        self.logger.info(f"\n🎯 喚醒事件 (共 {len(self.wake_events)} 次):")
        for i, wake in enumerate(self.wake_events):
            timestamp = wake['timestamp'].strftime('%H:%M:%S.%f')[:-3]
            source = wake['data'].get('source', 'unknown')
            self.logger.info(f"  {i+1}. [{timestamp}] 來源: {source}")
        
        # 超時事件
        self.logger.info(f"\n⏰ 超時事件 (共 {len(self.timeout_events)} 次):")
        for i, timeout in enumerate(self.timeout_events):
            timestamp = timeout['timestamp'].strftime('%H:%M:%S.%f')[:-3]
            self.logger.info(f"  {i+1}. [{timestamp}] 超時返回 IDLE")
        
        # 驗證結果
        self.logger.info("\n✅ 驗證結果:")
        
        # 檢查是否有喚醒事件
        if self.wake_events:
            self.logger.info("  ✓ 成功觸發喚醒")
        else:
            self.logger.error("  ✗ 未偵測到喚醒事件")
        
        # 檢查是否有超時事件
        if self.timeout_events:
            self.logger.info("  ✓ 成功觸發超時機制")
            
            # 計算實際超時時間
            if self.wake_events and self.timeout_events:
                wake_time = self.wake_events[-1]['timestamp']
                timeout_time = self.timeout_events[-1]['timestamp']
                actual_timeout = (timeout_time - wake_time).total_seconds()
                
                self.logger.info(f"  ✓ 實際超時時間: {actual_timeout:.1f} 秒")
                
                # 驗證是否接近設定值
                expected_timeout = self.system_listener.wake_timeout
                if abs(actual_timeout - expected_timeout) < 1.0:
                    self.logger.info(f"  ✓ 超時時間符合預期 ({expected_timeout} 秒)")
                else:
                    self.logger.warning(
                        f"  ⚠️ 超時時間偏差較大 "
                        f"(預期: {expected_timeout} 秒, 實際: {actual_timeout:.1f} 秒)"
                    )
        else:
            self.logger.error("  ✗ 未偵測到超時事件")
        
        # 檢查最終狀態
        final_state = self.system_listener.fsm.get_state()
        if final_state == State.IDLE:
            self.logger.info("  ✓ 系統已返回 IDLE 狀態")
        else:
            self.logger.error(f"  ✗ 系統未返回 IDLE 狀態 (當前: {final_state.value})")
        
        self.logger.info("="*60)
    
    async def cleanup(self):
        """清理資源"""
        if self.system_listener:
            await self.system_listener.stop()


async def main():
    """主函數"""
    print("🔍 喚醒詞超時測試工具")
    print("此工具將測試 3 秒超時機制")
    print("測試流程：")
    print("1. 觸發喚醒（進入 LISTENING 狀態）")
    print("2. 等待 3 秒不做任何動作")
    print("3. 驗證系統自動返回 IDLE 狀態")
    print()
    
    tester = WakeWordTimeoutTester()
    
    try:
        # 設定環境
        await tester.setup()
        
        # 等待系統穩定
        await asyncio.sleep(2)
        
        # 運行測試
        await tester.run_timeout_test()
        
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理資源
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())