"""
音訊處理 Handlers

處理音訊資料接收、緩衝區管理、metadata 處理等
"""

from typing import Dict, Any
from pystorex import to_dict
from src.utils.logger import logger

from .base import (
    ensure_state_dict,
    format_session_id,
    get_session_from_state,
    update_session_timestamp,
    BaseHandler
)


def handle_audio_chunk(state: Any, action: Any) -> Dict[str, Any]:
    """處理音訊資料 - 只更新統計信息，實際音訊由 AudioQueueManager 管理
    
    Args:
        state: 當前狀態
        action: audio_chunk_received action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found when processing audio chunk")
        return state
    
    session = to_dict(sessions[session_id])
    
    # 只更新統計信息
    chunk_size = action.payload.get("chunk_size", 0)  # 音訊塊大小
    timestamp = action.payload.get("timestamp")
    
    new_session = update_session_timestamp({
        **session,
        "audio_bytes_received": session.get("audio_bytes_received", 0) + chunk_size,
        "audio_chunks_count": session.get("audio_chunks_count", 0) + 1,
        "last_audio_timestamp": timestamp,
    })
    
    logger.debug(
        f"Audio chunk processed for session {format_session_id(session_id)}: "
        f"{chunk_size} bytes, total: {new_session['audio_bytes_received']} bytes"
    )
    
    return {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }


def handle_clear_audio_buffer(state: Any, action: Any) -> Dict[str, Any]:
    """處理清除音訊統計 - 實際音訊清除由 AudioQueueManager 處理
    
    Args:
        state: 當前狀態
        action: clear_audio_buffer action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload["session_id"]
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found when clearing audio buffer")
        return state
    
    session = to_dict(sessions[session_id])
    
    new_session = update_session_timestamp({
        **session,
        "audio_bytes_received": 0,
        "audio_chunks_count": 0,
        "last_audio_timestamp": None,
    })
    
    logger.info(f"🗑️ Audio buffer cleared for session {format_session_id(session_id)}")
    
    return {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }


def handle_audio_metadata(state: Any, action: Any) -> Dict[str, Any]:
    """處理音訊 metadata
    
    當前端分析音訊檔案並發送 metadata 時：
    1. 儲存音訊 metadata
    2. 根據 metadata 制定轉換策略
    3. 儲存策略供後續使用
    
    Args:
        state: 當前狀態
        action: audio_metadata action
        
    Returns:
        更新後的狀態
    """
    # 確保 state 為字典格式
    state = ensure_state_dict(state)
    
    sessions = to_dict(state.get("sessions", {}))
    session_id = action.payload["session_id"]
    received_metadata = action.payload["audio_metadata"]
    
    if session_id not in sessions:
        logger.warning(f"Session {format_session_id(session_id)} not found when processing audio metadata")
        return state
    
    session = to_dict(sessions[session_id])
    
    # 記錄接收到的 metadata
    logger.block(
        "Audio Metadata Received",
        [
            f"Session: {format_session_id(session_id)}...",
            f"File: {received_metadata.get('filename', 'unknown')}",
            f"Format: {received_metadata.get('detectedFormat', 'unknown')}",
            f"Sample Rate: {received_metadata.get('sampleRate', 0)} Hz",
            f"Channels: {received_metadata.get('channels', 0)}",
            f"Duration: {received_metadata.get('duration', 0):.1f}s",
            f"Needs Conversion: {received_metadata.get('needsConversion', False)}",
        ],
    )
    
    # 制定轉換策略
    conversion_strategy = create_conversion_strategy(received_metadata)
    
    # 記錄轉換策略
    logger.block(
        "Conversion Strategy Created",
        [
            f"Session: {format_session_id(session_id)}...",
            f"Target Sample Rate: {conversion_strategy['targetSampleRate']} Hz",
            f"Target Channels: {conversion_strategy['targetChannels']} ch",
            f"Target Format: {conversion_strategy['targetFormat']}",
            f"Priority: {conversion_strategy['priority']}",
            f"Estimated Processing Time: {conversion_strategy['estimatedProcessingTime']:.1f}s",
            f"Conversion Steps: {' → '.join(conversion_strategy['conversionSteps']) if conversion_strategy['conversionSteps'] else 'None'}",
        ],
    )
    
    # 更新 session 狀態
    new_session = update_session_timestamp({
        **session,
        "audio_metadata": received_metadata,
        "conversion_strategy": conversion_strategy
    })
    
    return {
        **state,
        "sessions": {**sessions, session_id: new_session}
    }


def create_conversion_strategy(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """根據音訊 metadata 制定轉換策略
    
    Args:
        metadata: 前端發送的音訊 metadata
        
    Returns:
        轉換策略字典
    """
    # 目標格式（Whisper 的最佳參數）
    target_sample_rate = 16000
    target_channels = 1
    target_format = "pcm_float32"
    
    # 獲取當前格式參數
    current_sample_rate = metadata.get("sampleRate", 44100)
    current_channels = metadata.get("channels", 2)
    current_format = metadata.get("detectedFormat", "MP3").lower()
    needs_conversion = metadata.get("needsConversion", True)
    
    # 計算轉換步驟
    conversion_steps = []
    
    # 1. 格式解碼（如果需要）
    if current_format in ["mp3", "aac", "m4a", "flac", "ogg"]:
        conversion_steps.append(f"解碼 {current_format.upper()}")
    
    # 2. 採樣率轉換
    if current_sample_rate != target_sample_rate:
        conversion_steps.append(f"降採樣 {current_sample_rate}Hz → {target_sample_rate}Hz")
    
    # 3. 聲道轉換
    if current_channels != target_channels:
        if current_channels > target_channels:
            conversion_steps.append(f"混音 {current_channels}ch → {target_channels}ch")
        else:
            conversion_steps.append(f"複製聲道 {current_channels}ch → {target_channels}ch")
    
    # 4. 格式轉換
    conversion_steps.append(f"轉換為 {target_format}")
    
    # 估算處理時間（基於檔案時長和複雜度）
    duration = metadata.get("duration", 0.0)
    file_size = metadata.get("fileSize", 0)
    
    # 基礎處理時間（通常是實際時長的 10-30%）
    base_time = duration * 0.2
    
    # 根據轉換複雜度調整
    complexity_factor = len(conversion_steps) * 0.1
    size_factor = (file_size / (1024 * 1024)) * 0.05  # 每 MB 增加 0.05 秒
    
    estimated_time = max(0.5, base_time + complexity_factor + size_factor)
    
    # 確定優先級
    if duration > 300:  # 超過 5 分鐘
        priority = "low"
    elif needs_conversion and len(conversion_steps) > 2:
        priority = "medium"
    else:
        priority = "high"
    
    return {
        "needsConversion": needs_conversion or len(conversion_steps) > 1,
        "targetSampleRate": target_sample_rate,
        "targetChannels": target_channels,
        "targetFormat": target_format,
        "conversionSteps": conversion_steps,
        "estimatedProcessingTime": estimated_time,
        "priority": priority,
    }