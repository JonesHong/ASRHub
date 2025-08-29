from dataclasses import dataclass

# === 轉譯策略 (Transcription Strategies) ===
class Strategy:
    """
    轉譯策略類別，定義不同的轉譯策略。
    """
    BATCH = "batch"  # 一次性轉譯。上傳音訊檔案或者是 Chunk, Buffer後一次性轉譯，簡單沒有複雜邏輯
    NON_STREAMING = "non_streaming"  # 非流式實時
    STREAMING = "streaming"  # 流式實時

# === 策略 Plugin ===
@dataclass
class StrategyPlugin:
    name: str
    states: list
    transitions: list

def make_transition(trigger, source, dest):
    """
    幫助函數：創建轉換字典，單純只是為了視覺上減少文字量
    Args:
        trigger: 觸發事件
        source: 來源狀態
        dest: 目標狀態
    """
    return {"trigger": trigger, "source": source, "dest": dest}
