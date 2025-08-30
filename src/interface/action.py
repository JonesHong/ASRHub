# src/interface/action.py

class Action:
    """
    事件 (Events: verbs, triggers)
    定義系統中的各種事件類型
    包括會話管理、音訊處理、上傳、喚醒、錄音、轉譯、串流、LLM、TTS等操作
    """

    # Session lifecycle
    CREATE_SESSION = "create_session"
    """建立 Session (必選參數: strategy)"""
    DELETE_SESSION = "delete_session"
    """刪除 Session (必選參數: session_id)"""
    SESSION_EXPIRED = "session_expired"
    """Session 過期 (必選參數: session_id)"""
    RESET_SESSION = "reset_session"
    """重置 Session (必選參數: session_id)"""

    # Audio data
    EMIT_AUDIO_CHUNK = "emit_audio_chunk"
    """發送音訊分塊 (必選參數: session_id, audio_data)"""
    RECEIVE_AUDIO_CHUNK = "receive_audio_chunk"
    """收到音訊分塊 (必選參數: session_id, audio_data)"""
    CLEAR_AUDIO_BUFFER = "clear_audio_buffer" 
    """清除音訊緩衝區 (必選參數: session_id)"""

    # Upload / batch
    UPLOAD_STARTED = "upload_started"
    """開始上傳，設定音訊元資料 (必選參數: session_id, file_name, sample_rate, channels, format)"""
    UPLOAD_COMPLETED = "upload_completed"
    """上傳完成 (必選參數: session_id, file_name)"""

    # Wake / listen
    START_LISTENING = "start_listening"
    """開始監聽 (必選參數: session_id, sample_rate, channels, format)"""
    WAKE_ACTIVATED = "wake_activated"
    """啟用喚醒 (必選參數: session_id, source)，來源可為 UI/visual (外部) 或 keyword (內部)"""
    WAKE_DEACTIVATED = "wake_deactivated"
    """停用喚醒 (必選參數: session_id, source)"""

    # VAD
    VAD_SPEECH_DETECTED = "vad_speech_detected"
    """偵測到語音 (必選參數: session_id)"""
    VAD_SILENCE_DETECTED = "vad_silence_detected"
    """偵測到靜音 (必選參數: session_id)"""
    SILENCE_TIMEOUT = "silence_timeout"
    """偵測到長時間靜音 (必選參數: session_id)"""

    # Recording
    RECORD_STARTED = "record_started"
    """錄音開始 (必選參數: session_id)"""
    RECORD_STOPPED = "record_stopped"
    """錄音停止 (必選參數: session_id)"""
    
    # Playback
    PLAY_ASR_FEEDBACK = "play_asr_feedback"
    """播放 ASR 回饋音 (必選參數: session_id, command)"""

    # Transcription
    TRANSCRIBE_STARTED = "transcribe_started"
    """開始轉譯 (必選參數: session_id)"""
    TRANSCRIBE_DONE = "transcribe_done"
    """完成轉譯 (必選參數: session_id)"""

    # Streaming ASR
    ASR_STREAM_STARTED = "asr_stream_started"
    """開始串流 ASR (必選參數: session_id)"""
    ASR_STREAM_STOPPED = "asr_stream_stopped"
    """停止串流 ASR (必選參數: session_id)"""

    # LLM
    LLM_REPLY_STARTED = "llm_reply_started"
    """開始 LLM 回覆 (必選參數: session_id)"""
    LLM_REPLYING = "llm_replying"
    """LLM 回覆中 (必選參數: session_id)"""
    LLM_REPLY_COMPLETED = "llm_reply_completed"
    """完成 LLM 回覆 (必選參數: session_id)"""
    LLM_REPLY_TIMEOUT = "llm_reply_timeout"
    """回覆超時 (必選參數: session_id)"""

    # TTS
    TTS_PLAYBACK_STARTED = "tts_playback_started"
    """開始播放 TTS (必選參數: session_id)"""
    TTS_PLAYING = "tts_playing"
    """TTS 播放中 (必選參數: session_id)"""
    TTS_PLAYBACK_COMPLETED = "tts_playback_completed"
    """完成播放 TTS (必選參數: session_id)"""
    TTS_PLAYBACK_TIMEOUT = "tts_playback_timeout"
    """播放超時 (必選參數: session_id)"""

    # Interrupts / error
    REPLY_INTERRUPTED = "reply_interrupted"
    """使用者中斷回覆 (必選參數: session_id)"""
    ERROR_OCCURRED = "error_occurred"
    """發生錯誤 (必選參數: session_id)"""
    ERROR_RAISED = "error_raised"
    """內部錯誤 (必選參數: session_id, error)"""
    ERROR_REPORTED = "error_reported"
    """錯誤已回報 (必選參數: session_id)"""


class InputAction(Action):
    """
    外部觸發（UI、音訊流）
    """
    CREATE_SESSION = Action.CREATE_SESSION
    """建立 Session (必選參數: strategy)"""
    DELETE_SESSION = Action.DELETE_SESSION
    """刪除 Session (必選參數: session_id)"""
    START_LISTENING = Action.START_LISTENING
    """開始監聽 (必選參數: session_id, sample_rate, channels, format)"""
    EMIT_AUDIO_CHUNK = Action.EMIT_AUDIO_CHUNK
    """發送音訊分塊 (必選參數: session_id, audio_data)"""
    WAKE_ACTIVATED = Action.WAKE_ACTIVATED
    """喚醒啟用 (必選參數: session_id, source) 客戶或者或外部服務喚醒(UI按鈕、視覺辨識) """
    WAKE_DEACTIVATED = Action.WAKE_DEACTIVATED 
    """喚醒停用 (必選參數: session_id, source) 客戶或者或外部服務取消喚醒(UI按鈕、視覺辨識)"""
    UPLOAD_STARTED = Action.UPLOAD_STARTED 
    """開始上傳音訊檔案 (必選參數: session_id, file_name, sample_rate, channels, format)"""
    UPLOAD_COMPLETED = Action.UPLOAD_COMPLETED
    """上傳完成 (必選參數: session_id, file_name)"""
    LLM_REPLY_STARTED = Action.LLM_REPLY_STARTED
    """開始 LLM 回覆 (必選參數: session_id)"""
    LLM_REPLYING = Action.LLM_REPLYING
    """LLM 回覆中 (必選參數: session_id)"""
    LLM_REPLY_COMPLETED = Action.LLM_REPLY_COMPLETED
    """完成 LLM 回覆 (必選參數: session_id)"""
    TTS_PLAYBACK_STARTED = Action.TTS_PLAYBACK_STARTED
    """開始播放 TTS (必選參數: session_id)"""
    TTS_PLAYING = Action.TTS_PLAYING
    """TTS 播放中 (必選參數: session_id)"""
    TTS_PLAYBACK_COMPLETED = Action.TTS_PLAYBACK_COMPLETED
    """完成播放 TTS (必選參數: session_id)"""
    REPLY_INTERRUPTED = Action.REPLY_INTERRUPTED
    """使用者中斷回覆 (必選參數: session_id)"""
    ERROR_OCCURRED = Action.ERROR_OCCURRED
    """發生錯誤 (必選參數: session_id)"""
    
    


class InternalAction(Action):
    """
    內部觸發，FSM 自身或 pipeline module 的回饋（VAD、LLM、TTS、系統）
    """
    SESSION_EXPIRED = Action.SESSION_EXPIRED
    """Session 過期 (必選參數: session_id)"""
    RESET_SESSION = Action.RESET_SESSION
    """重置 Session (必選參數: session_id)"""
    RECEIVE_AUDIO_CHUNK = Action.RECEIVE_AUDIO_CHUNK
    """收到音訊分塊 (必選參數: session_id, audio_data)"""
    CLEAR_AUDIO_BUFFER = Action.CLEAR_AUDIO_BUFFER
    """清除音訊緩衝區 (必選參數: session_id)"""
    WAKE_ACTIVATED = Action.WAKE_ACTIVATED 
    """喚醒啟用 (必選參數: session_id, source) 透過 openWakeWord或者關鍵字喚醒"""
    WAKE_DEACTIVATED = Action.WAKE_DEACTIVATED
    """喚醒停用 (必選參數: session_id, source)"""
    VAD_SPEECH_DETECTED = Action.VAD_SPEECH_DETECTED
    """偵測到語音 (必選參數: session_id)"""
    VAD_SILENCE_DETECTED = Action.VAD_SILENCE_DETECTED
    """偵測到靜音 (必選參數: session_id)"""
    SILENCE_TIMEOUT = Action.SILENCE_TIMEOUT
    """偵測到長時間靜音 (必選參數: session_id) VAD 偵測到長時間靜音，停用喚醒"""
    RECORD_STARTED = Action.RECORD_STARTED
    """錄音開始 (必選參數: session_id)"""
    RECORD_STOPPED = Action.RECORD_STOPPED
    """錄音停止 (必選參數: session_id)"""
    TRANSCRIBE_STARTED = Action.TRANSCRIBE_STARTED
    """開始轉譯 (必選參數: session_id)"""
    TRANSCRIBE_DONE = Action.TRANSCRIBE_DONE
    """完成轉譯 (必選參數: session_id)"""
    ASR_STREAM_STARTED = Action.ASR_STREAM_STARTED
    """開始串流 ASR (必選參數: session_id)"""
    ASR_STREAM_STOPPED = Action.ASR_STREAM_STOPPED
    """停止串流 ASR (必選參數: session_id)"""
    LLM_REPLY_TIMEOUT = Action.LLM_REPLY_TIMEOUT
    """回覆超時 (必選參數: session_id)"""
    TTS_PLAYBACK_TIMEOUT = Action.TTS_PLAYBACK_TIMEOUT
    """播放超時 (必選參數: session_id)"""
    ERROR_RAISED = Action.ERROR_RAISED
    """內部錯誤 (必選參數: session_id)"""
    


class OutputAction(Action):
    """
    系統輸出，要發給 client 或其他服務的事件（結果、通知）
    """
    PLAY_ASR_FEEDBACK = Action.PLAY_ASR_FEEDBACK
    """播放 ASR 回饋音 (必選參數: session_id, command)"""
    TRANSCRIBE_DONE = Action.TRANSCRIBE_DONE
    """完成轉譯 (必選參數: session_id)"""
    ERROR_REPORTED = Action.ERROR_REPORTED
    """錯誤已回報 (必選參數: session_id)"""
