"""Timer 服務使用範例
展示簡化後的計時器 API 使用方式
"""

import time
from src.service.timer.timer import timer


def on_timer_complete(session_id: str):
    """倒數結束時的 callback
    
    Args:
        session_id: 完成倒數的 session ID
    """
    print(f"⏰ [{session_id}] 倒數計時結束！")
    print(f"   可以執行後續動作，例如：")
    print(f"   - 停止錄音")
    print(f"   - 送出 ASR 結果")
    print(f"   - 顯示超時提示")


def main():
    """主要使用範例"""
    
    print("=" * 50)
    print("Timer 服務使用範例")
    print("=" * 50)
    
    # ========== 範例 1: 基本使用 ==========
    print("\n1. 基本倒數計時:")
    
    # 開始倒數（使用預設時間，通常是 60 秒）
    success = timer.start_countdown("user_123", on_timer_complete)
    if success:
        print(f"✅ 開始倒數（預設時間）")
        
        # 檢查剩餘時間
        remaining = timer.get_remaining_time("user_123")
        print(f"   剩餘: {remaining:.1f} 秒")
    
    
    # ========== 範例 2: 指定倒數時間 ==========
    print("\n2. 指定倒數時間:")
    
    # 開始 10 秒倒數
    timer.start_countdown("user_456", on_timer_complete, duration=10)
    print(f"✅ 開始 10 秒倒數")
    
    # 取得計時器資訊
    info = timer.get_timer_info("user_456")
    if info:
        print(f"   總時長: {info.duration} 秒")
        print(f"   剩餘: {info.remaining:.1f} 秒")
        print(f"   狀態: {'執行中' if info.is_running else '停止'}")
    
    
    # ========== 範例 3: 重置倒數 ==========
    print("\n3. 重置倒數計時:")
    
    # 先開始一個倒數
    timer.start_countdown("reset_user", on_timer_complete, duration=30)
    print(f"✅ 開始 30 秒倒數")
    
    time.sleep(2)  # 等待 2 秒
    
    # 重置為原本的時間
    timer.reset_countdown("reset_user")
    print(f"✅ 重置倒數（回到 30 秒）")
    
    # 重置為新的時間
    timer.reset_countdown("reset_user", duration=15)
    print(f"✅ 重置倒數（改為 15 秒）")
    
    
    # ========== 範例 4: 停止和清除 ==========
    print("\n4. 停止和清除計時器:")
    
    timer.start_countdown("stop_user", on_timer_complete, duration=20)
    print(f"✅ 開始 20 秒倒數")
    
    # 停止倒數（保留 session 資料）
    if timer.stop_countdown("stop_user"):
        remaining = timer.get_remaining_time("stop_user")
        print(f"✅ 停止倒數，剩餘: {remaining:.1f} 秒")
    
    # 清除計時器（完全移除）
    if timer.clear_countdown("stop_user"):
        print(f"✅ 清除計時器")
    
    
    # ========== 範例 5: 實際應用場景 ==========
    print("\n5. 實際應用場景:")
    
    # 場景 1: 語音輸入超時
    def speech_timeout_callback(session_id: str):
        print(f"🎤 [{session_id}] 語音輸入超時，停止錄音")
        # 這裡可以停止錄音、處理已收集的音訊
    
    timer.start_countdown("speech_session", speech_timeout_callback, duration=5)
    print("✅ 語音輸入計時器（5秒超時）")
    
    
    # 場景 2: API 請求超時
    def api_timeout_callback(session_id: str):
        print(f"🌐 [{session_id}] API 請求超時，取消請求")
        # 這裡可以取消 API 請求、返回錯誤
    
    timer.start_countdown("api_session", api_timeout_callback, duration=10)
    print("✅ API 請求計時器（10秒超時）")
    
    
    # 場景 3: 遊戲回合計時
    def turn_timeout_callback(session_id: str):
        print(f"🎮 [{session_id}] 回合時間結束，切換玩家")
        # 這裡可以結束當前回合、切換到下一個玩家
    
    timer.start_countdown("game_session", turn_timeout_callback, duration=30)
    print("✅ 遊戲回合計時器（30秒）")
    
    
    # ========== 範例 6: 錯誤處理 ==========
    print("\n6. 錯誤處理:")
    
    from src.interface.exceptions import (
        TimerSessionError,
        TimerConfigError,
        TimerNotFoundError
    )
    
    try:
        # 無效的 session ID
        timer.start_countdown("", on_timer_complete)
    except TimerSessionError as e:
        print(f"❌ Session 錯誤: {e}")
    
    try:
        # 無效的倒數時間
        timer.start_countdown("invalid_timer", on_timer_complete, duration=-5)
    except TimerConfigError as e:
        print(f"❌ 配置錯誤: {e}")
    
    try:
        # 重置不存在的計時器
        timer.reset_countdown("non_existent")
    except TimerNotFoundError as e:
        print(f"❌ 計時器不存在: {e}")
    
    
    # ========== 清理 ==========
    print("\n清理所有計時器...")
    count = timer.clear_all()
    print(f"✅ 清除了 {count} 個計時器")
    
    
    # ========== 關閉服務 ==========
    print("\n關閉 Timer 服務...")
    timer.shutdown()
    print("✅ 服務已關閉")


if __name__ == "__main__":
    main()