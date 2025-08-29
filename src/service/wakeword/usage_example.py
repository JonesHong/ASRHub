"""
OpenWakeword 使用範例

展示如何使用簡化後的 API 進行關鍵字偵測
"""

from src.service.wakeword import openwakeword
from src.core.audio_queue_manager import audio_queue
import time
import numpy as np


def main():
    """主要示範程式"""
    
    # 1. 定義不同 session 的回調函數
    # （服務會在第一次使用時自動初始化）
    def on_wakeword_session1(detection):
        print(f"[Session 1] 偵測到關鍵字: {detection.keyword}")
        print(f"  信心度: {detection.confidence:.3f}")
        # 這裡可以執行 session1 特定的動作
        # 例如：開始錄音、切換狀態等
    
    def on_wakeword_session2(detection):
        print(f"[Session 2] 偵測到關鍵字: {detection.keyword}")
        print(f"  時間: {detection.timestamp}")
        # 這裡可以執行 session2 特定的動作
    
    # 2. 開始監聽不同的 sessions
    session_id_1 = "user_123"
    session_id_2 = "user_456"
    
    # 開始監聽 session 1 (使用預設模型)
    success = openwakeword.start_listening(
        session_id=session_id_1,
        callback=on_wakeword_session1
    )
    print(f"Session 1 監聽狀態: {'成功' if success else '失敗'}")
    
    # 開始監聽 session 2 (可選：指定自訂模型)
    success = openwakeword.start_listening(
        session_id=session_id_2,
        callback=on_wakeword_session2,
        model_path=None  # 使用預設模型，或指定 "path/to/custom_model.onnx"
    )
    print(f"Session 2 監聽狀態: {'成功' if success else '失敗'}")
    
    # 3. 模擬推送音訊到 audio_queue
    print("\n模擬推送音訊...")
    
    # 這裡應該是從實際的音訊源取得資料
    # 此處只是示範
    sample_rate = 16000
    duration = 1  # 1 秒
    
    for i in range(5):
        # 產生模擬音訊資料
        audio_chunk = np.random.randn(sample_rate * duration).astype(np.float32)
        
        # 推送到不同 session 的 queue
        audio_queue.push(session_id_1, audio_chunk)
        audio_queue.push(session_id_2, audio_chunk)
        
        print(f"推送音訊區塊 {i+1}/5")
        time.sleep(1)
    
    # 4. 檢查監聽狀態
    print("\n檢查監聽狀態:")
    print(f"Session 1 是否在監聽: {openwakeword.is_listening(session_id_1)}")
    print(f"Session 2 是否在監聽: {openwakeword.is_listening(session_id_2)}")
    print(f"所有活動 sessions: {openwakeword.get_active_sessions()}")
    
    # 5. 停止特定 session
    print(f"\n停止 Session 1...")
    openwakeword.stop_listening(session_id_1)
    print(f"剩餘活動 sessions: {openwakeword.get_active_sessions()}")
    
    # 6. 讓 Session 2 繼續運行一會兒
    print("\nSession 2 繼續運行...")
    time.sleep(3)
    
    # 7. 停止所有 sessions（或透過 shutdown）
    print("\n停止所有 sessions...")
    openwakeword.stop_listening(session_id_2)
    
    # 或者直接關閉整個服務
    # openwakeword.shutdown()
    
    print("示範結束")


if __name__ == "__main__":
    main()