"""WebRTC 信令定義 - 基於 Action 定義保持協議一致性"""

from src.interface.action import InputAction, OutputAction


class WebRTCSignals:
    """WebRTC 信令定義 - 最小化 REST，使用 DataChannel 控制"""
    
    # === API 路徑前綴 ===
    API_PREFIX = "/api/webrtc"
    
    # === 唯一的 REST 端點 ===
    CREATE_SESSION = f"{API_PREFIX}/{InputAction.CREATE_SESSION}"      # POST - 建立新 session 並取得 token


class DataChannelTopics:
    """DataChannel 主題定義 - 組織不同類型的訊息"""
    
    # === 控制命令主題 (Client → Server) ===
    CONTROL = "control"                    # 控制命令通道
    AUDIO_METADATA = "audio_metadata"      # 音訊元資料通道
    
    # === 狀態回報主題 (Server → Client) ===
    STATUS = "status"                      # 狀態更新通道
    ASR_RESULT = "asr_result"             # ASR 結果通道
    ERROR = "error"                        # 錯誤訊息通道


class DataChannelCommands:
    """DataChannel 控制命令 - 透過 DataChannel 發送的命令"""
    
    # === 基於 InputAction 的控制命令 ===
    START_LISTENING = InputAction.START_LISTENING      # 開始監聽
    WAKE_ACTIVATED = InputAction.WAKE_ACTIVATED        # 啟用喚醒
    WAKE_DEACTIVATED = InputAction.WAKE_DEACTIVATED    # 停用喚醒
    CLEAR_AUDIO_BUFFER = InputAction.CLEAR_AUDIO_BUFFER # 清除音訊緩衝
    
    # === 查詢命令 ===
    GET_STATUS = "get_status"              # 查詢 session 狀態
    GET_STATS = "get_stats"                # 查詢統計資訊


class DataChannelEvents:
    """DataChannel 事件類型 - 透過 DataChannel 廣播的事件"""
    
    # === 基於 OutputAction 的事件 ===
    TRANSCRIBE_DONE = OutputAction.TRANSCRIBE_DONE         # 轉譯完成
    PLAY_ASR_FEEDBACK = OutputAction.PLAY_ASR_FEEDBACK     # 播放 ASR 回饋音
    ERROR_REPORTED = OutputAction.ERROR_REPORTED           # 錯誤已回報
    
    # === 狀態確認事件 ===
    LISTENING_STARTED = "listening_started"    # 開始監聽確認
    WAKE_STATUS_CHANGED = "wake_status_changed" # 喚醒狀態變更
    BUFFER_CLEARED = "buffer_cleared"          # 緩衝區已清除
    STATUS_UPDATE = "status_update"            # 狀態更新
    STATS_UPDATE = "stats_update"              # 統計更新


class LiveKitEventTypes:
    """LiveKit 事件類型定義"""
    
    # === LiveKit 連線事件 ===
    ROOM_CONNECTED = "room_connected"              # 房間連線成功
    ROOM_DISCONNECTED = "room_disconnected"        # 房間斷線
    
    # === 參與者事件 ===
    PARTICIPANT_JOINED = "participant_joined"      # 參與者加入
    PARTICIPANT_LEFT = "participant_left"          # 參與者離開
    
    # === 軌道事件 ===
    TRACK_PUBLISHED = "track_published"            # 軌道發布
    TRACK_SUBSCRIBED = "track_subscribed"          # 訂閱軌道
    
    # === 數據通道事件 ===
    DATA_RECEIVED = "data_received"                # 接收到數據訊息