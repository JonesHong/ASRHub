# === 狀態 (States: nouns/adjectives/ing) ===
class State:
    """
    定義系統中的各種狀態類型
    包括空閒、處理中、忙碌、錯誤等狀態
    """
    # Top-level
    IDLE = "idle"
    """閒置中，等待使用者輸入或指令"""
    PROCESSING = "processing" 
    """正在處理使用者請求或系統任務(抽象狀態，包含子狀態機)"""
    BUSY = "busy" 
    """系統忙碌，無法處理新請求，通常是等待外部系統完成任務，如:LLM, TTS"""
    ERROR = "error" 
    """系統發生錯誤，需人工介入或自動恢復"""

    # Common Sub States
    RECORDING = "recording"
    """正在錄製使用者語音輸入"""
    TRANSCRIBING = "transcribing"
    """正在轉譯使用者語音輸入"""
    # STREAMING = "streaming"
    # """正在串流處理使用者語音輸入"""
    UPLOADING = "uploading"
    """正在上傳音訊檔案"""
    ACTIVATED = "activated"
    """喚醒後 (等待語音/指令中)"""

