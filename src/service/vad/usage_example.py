"""SileroVAD 使用範例
展示簡化後的 API 使用方式
"""

from src.service.vad.silero_vad import silero_vad
from src.interface.vad import VADState


def on_vad_state_change(result):
    """當 VAD 狀態變化時的回調函數
    
    Args:
        result: VADResult 物件，包含 state 和 probability
    """
    if result.state == VADState.SPEECH:
        print(f"偵測到語音 (信心度: {result.probability:.2f})")
    elif result.state == VADState.SILENCE:
        print(f"偵測到靜音 (信心度: {1-result.probability:.2f})")
    else:
        print("不確定狀態")


def main():
    """主要使用範例"""
    
    # 範例 1: 基本使用
    session_id = "user_123"
    
    # 開始監聽
    # 服務會自動初始化，從 audio_queue 拉取音訊
    success = silero_vad.start_listening(
        session_id=session_id,
        callback=on_vad_state_change
    )
    
    if success:
        print(f"開始監聽 session: {session_id}")
        
        # 檢查是否正在監聽
        if silero_vad.is_listening(session_id):
            print("確認正在監聽中")
        
        # ... 執行其他邏輯 ...
        
        # 停止監聽
        silero_vad.stop_listening(session_id)
        print(f"停止監聽 session: {session_id}")
    
    
    # 範例 2: 使用自定義模型
    custom_session = "user_456"
    
    success = silero_vad.start_listening(
        session_id=custom_session,
        callback=on_vad_state_change,
        model_path="models/custom_vad_model.onnx"  # 可選的自定義模型
    )
    
    if success:
        print(f"使用自定義模型監聽: {custom_session}")
        # ...
        silero_vad.stop_listening(custom_session)
    
    
    # 範例 3: 錯誤處理
    from src.interface.exceptions import (
        VADInitializationError,
        VADSessionError,
        VADModelError
    )
    
    try:
        # 嘗試開始監聽
        success = silero_vad.start_listening(
            session_id="test_session",
            callback=on_vad_state_change
        )
    except VADInitializationError as e:
        print(f"服務初始化失敗: {e}")
    except VADSessionError as e:
        print(f"Session 錯誤: {e}")
    except VADModelError as e:
        print(f"模型錯誤: {e}")
    except Exception as e:
        print(f"未預期錯誤: {e}")
    
    
    # 範例 4: 取得 session 狀態
    state_info = silero_vad.get_session_state("user_123")
    print(f"Session 狀態: {state_info}")
    
    
    # 範例 5: 關閉服務
    silero_vad.shutdown()
    print("VAD 服務已關閉")


if __name__ == "__main__":
    main()