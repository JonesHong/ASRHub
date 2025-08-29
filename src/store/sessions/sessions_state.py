"""
Sessions State Definition for PyStoreX Store

定義 Session 相關的狀態結構，使用 TypedDict 確保類型安全，
配合 immutables.Map 實現不可變狀態管理。
"""

from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict
import time


class AudioConfig(TypedDict):
    """音訊配置 - 由客戶端提供的音訊參數"""
    sample_rate: int  # 採樣率 (Hz) - 客戶端必須提供
    channels: int  # 聲道數 (1=mono, 2=stereo) - 客戶端必須提供
    format: str  # 格式 (如 'pcm_s16le', 'pcm_f32le') - 客戶端必須提供
    bits_per_sample: Optional[int]  # 每個樣本的位元數 (16, 24, 32)
    endianness: Optional[str]  # 位元組順序 ('little', 'big')
    device_info: Optional[Dict[str, Any]]  # 裝置資訊


class SessionState(TypedDict):
    """單一 Session 的狀態定義"""
    
    # === 基本資訊 ===
    session_id: str  # Session 唯一識別碼 (UUID v7)
    strategy: str  # 轉譯策略: batch, non_streaming, streaming
    status: str  # 當前狀態: idle, listening, processing, transcribing, replying, error
    created_at: float  # 建立時間 (timestamp)
    updated_at: float  # 最後更新時間 (timestamp)
    expires_at: Optional[float]  # 過期時間 (timestamp)
    
    # === 音訊配置 ===
    audio_config: Optional[AudioConfig]  # 音訊配置資訊
    
    # === 狀態標記 ===
    is_wake_active: bool  # 是否處於喚醒狀態
    wake_source: Optional[str]  # 喚醒來源: UI/visual, keyword
    is_recording: bool  # 是否正在錄音
    is_vad_speech: bool  # VAD 是否偵測到語音
    is_transcribing: bool  # 是否正在轉譯
    is_streaming: bool  # 是否為串流模式
    
    # === 上傳相關 ===
    upload_file: Optional[str]  # 上傳的檔案名稱
    upload_progress: float  # 上傳進度 (0.0 - 1.0)
    
    # === 錯誤處理 ===
    error_count: int  # 錯誤計數
    last_error: Optional[str]  # 最後一個錯誤訊息
    
    # === 統計資訊 ===
    audio_chunks_received: int  # 接收的音訊塊數量
    audio_chunks_processed: int  # 已處理的音訊塊數量
    transcriptions_count: int  # 轉譯完成次數
    
    # === 元資料 ===
    metadata: Dict[str, Any]  # 額外的元資料


class SessionsState(TypedDict):
    """所有 Sessions 的狀態容器"""
    
    sessions: Dict[str, SessionState]  # session_id -> SessionState 映射
    active_session_ids: List[str]  # 活躍的 session IDs 列表
    total_created: int  # 總建立的 session 數量
    total_deleted: int  # 總刪除的 session 數量
    last_cleanup_at: float  # 最後清理時間 (timestamp)


def create_initial_session_state(
    session_id: str,
    strategy: str = "non_streaming"
) -> SessionState:
    """
    建立初始的 Session 狀態
    
    Args:
        session_id: Session ID
        strategy: 轉譯策略
        
    Returns:
        初始化的 SessionState
    """
    now = time.time()
    return SessionState(
        # 基本資訊
        session_id=session_id,
        strategy=strategy,
        status="idle",
        created_at=now,
        updated_at=now,
        expires_at=now + 3600,  # 預設 1 小時過期
        
        # 音訊配置
        audio_config=None,
        
        # 狀態標記
        is_wake_active=False,
        wake_source=None,
        is_recording=False,
        is_vad_speech=False,
        is_transcribing=False,
        is_streaming=(strategy == "streaming"),
        
        # 上傳相關
        upload_file=None,
        upload_progress=0.0,
        
        # 錯誤處理
        error_count=0,
        last_error=None,
        
        # 統計資訊
        audio_chunks_received=0,
        audio_chunks_processed=0,
        transcriptions_count=0,
        
        # 元資料
        metadata={}
    )


# 初始狀態
sessions_initial_state = SessionsState(
    sessions={},
    active_session_ids=(),  # 使用 tuple 保持一致性
    total_created=0,
    total_deleted=0,
    last_cleanup_at=time.time()
)


# Session 狀態常數
class SessionStatus:
    """Session 狀態列舉"""
    IDLE = "idle"  # 閒置
    LISTENING = "listening"  # 監聽中
    PROCESSING = "processing"  # 處理中
    TRANSCRIBING = "transcribing"  # 轉譯中
    REPLYING = "replying"  # 回覆中 (LLM/TTS)
    ERROR = "error"  # 錯誤狀態


class WakeSource:
    """喚醒來源列舉"""
    UI = "UI"  # UI 按鈕
    VISUAL = "visual"  # 視覺辨識
    KEYWORD = "keyword"  # 關鍵字喚醒


class TranscriptionStrategy:
    """轉譯策略列舉"""
    BATCH = "batch"  # 批次處理
    NON_STREAMING = "non_streaming"  # 非串流
    STREAMING = "streaming"  # 串流