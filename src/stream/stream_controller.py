"""
ASR Hub Stream Controller
控制和協調音訊流的處理
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List, Union
from datetime import datetime
from src.utils.logger import logger
from src.core.exceptions import StreamError, SessionError
from src.store import get_global_store
from src.store.sessions import sessions_actions, sessions_selectors
from src.providers.manager import ProviderManager
from src.audio import AudioChunk
from src.store.sessions.sessions_state import FSMStateEnum
from src.config.manager import ConfigManager

# 模組級變數
config_manager = ConfigManager()
store = get_global_store()


class StreamController:
    """
    串流控制器
    負責協調音訊流的接收、處理和轉譯
    """
    
    def __init__(self,
                 provider_manager: ProviderManager = None):
        """
        初始化 Stream Controller
        使用模組級變數
        
        Args:
            provider_manager: Provider 管理器
        """
        self.provider_manager = provider_manager
        
        
        # 串流配置
        stream_config = config_manager.stream
        self.buffer_size = stream_config.buffer.size
        self.silence_timeout = stream_config.silence_timeout
        self.max_segment_duration = stream_config.max_segment_duration
        self.enable_vad = stream_config.enable_vad
        
        # 活動串流追蹤
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        
        self._initialized = False
        
        # 註冊事件處理器（如果需要）
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """註冊 PyStoreX 事件處理器"""
        # 未來可以在這裡註冊事件監聽器
        # 例如：監聽 session 狀態變化、音訊事件等
        pass
    
    async def initialize(self):
        """初始化 Stream Controller"""
        if self._initialized:
            return
        
        logger.info("初始化 Stream Controller...")
        
        # 確保相關管理器已初始化
        if not store or not self.provider_manager:
            raise StreamError("相關管理器未正確初始化")
        
        self._initialized = True
        logger.success("Stream Controller 初始化完成")
    
    async def start_stream(self,
                          session_id: str,
                          **kwargs) -> Dict[str, Any]:
        """
        開始新的音訊串流
        
        Args:
            session_id: Session ID
            **kwargs: 額外參數
                - provider: Provider 名稱（預設使用預設 Provider）
                - language: 語言代碼
                - sample_rate: 取樣率
                - channels: 聲道數
                
        Returns:
            串流資訊
            
        Raises:
            StreamError: 如果啟動失敗
        """
        # 使用 selector 檢查 Session 是否存在
        state = store.get_state() if store else None
        session = sessions_selectors.get_session(session_id)(state) if state else None
        if not session:
            raise SessionError(f"Session {session_id} 不存在")
        
        # 檢查是否已有活動串流
        if session_id in self.active_streams:
            raise StreamError(f"Session {session_id} 已有活動串流")
        
        try:
            # 獲取 Provider
            
            provider_name = kwargs.get("provider")
            provider = self.provider_manager.get_provider(provider_name)
            if not provider:
                raise StreamError(f"Provider '{provider_name or 'default'}' 不存在")
            
            # 建立串流資訊
            stream_info = {
                "session_id": session_id,
                "provider": provider,
                "start_time": datetime.now(),
                "config": {
                    "language": kwargs.get("language", "auto"),
                    "sample_rate": kwargs.get("sample_rate", 16000),
                    "channels": kwargs.get("channels", 1),
                    "encoding": kwargs.get("encoding", "linear16")
                },
                "buffer": [],
                "total_duration": 0.0,
                "segment_count": 0,
                "transcription_results": []
            }
            
            # 使用 PyStoreX 更新 Session 狀態
            store.dispatch(sessions_actions.update_session_state(session_id, FSMStateEnum.LISTENING.value))
            
            # 儲存串流資訊
            self.active_streams[session_id] = stream_info
            
            logger.info(
                f"串流已啟動 - Session: {session_id}, "
                f"Provider: {provider_name or 'default'}"
            )
            
            return {
                "session_id": session_id,
                "stream_id": f"stream_{session_id}_{int(stream_info['start_time'].timestamp())}",
                "provider": provider_name or self.provider_manager.default_provider,
                "config": stream_info["config"]
            }
            
        except Exception as e:
            logger.error(f"啟動串流失敗：{e}")
            # 清理狀態
            if session_id in self.active_streams:
                del self.active_streams[session_id]
            raise StreamError(f"無法啟動串流：{str(e)}")
    
    async def process_audio_chunk(self,
                                 session_id: str,
                                 audio_chunk: Union[bytes, 'AudioChunk']) -> Optional[Dict[str, Any]]:
        """
        處理音訊片段
        
        Args:
            session_id: Session ID
            audio_chunk: 音訊資料片段（bytes 或 AudioChunk）
            
        Returns:
            處理結果（如果有）
            
        Raises:
            StreamError: 如果處理失敗
        """
        if session_id not in self.active_streams:
            raise StreamError(f"Session {session_id} 沒有活動串流")
        
        stream_info = self.active_streams[session_id]
        
        try:
            # 使用 PyStoreX 更新 Session 狀態為 BUSY
            store.dispatch(sessions_actions.update_session_state(session_id, FSMStateEnum.BUSY.value))
            
            # 如果是原始 bytes，建立 AudioChunk 物件
            if isinstance(audio_chunk, bytes):
                from src.audio import AudioChunk as AC
                from src.audio import AudioContainerFormat, AudioEncoding
                
                # 使用預設值或從配置取得
                audio_chunk = AC(
                    data=audio_chunk,
                    sample_rate=stream_info["config"].get("sample_rate", 16000),
                    channels=stream_info["config"].get("channels", 1),
                    format=stream_info["config"].get("format", AudioContainerFormat.PCM),
                    encoding=stream_info["config"].get("encoding", AudioEncoding.LINEAR16),
                    bits_per_sample=stream_info["config"].get("bits_per_sample", 16)
                )
            
            # 記錄音訊格式資訊
            if hasattr(audio_chunk, 'sample_rate'):
                logger.debug(
                    f"處理音訊片段 - Session: {session_id}, "
                    f"格式: {audio_chunk.sample_rate}Hz, {audio_chunk.channels}ch, "
                    f"{audio_chunk.bits_per_sample}bit"
                )
            
            # 音訊處理由 SessionEffects 管理，這裡直接傳遞
            processed_audio = audio_chunk.data if hasattr(audio_chunk, 'data') else audio_chunk
            
            if processed_audio:
                # 添加到緩衝
                stream_info["buffer"].append(processed_audio)
                
                # 計算音訊時長
                sample_rate = stream_info["config"]["sample_rate"]
                channels = stream_info["config"]["channels"]
                bytes_per_sample = 2  # 16-bit
                duration = len(processed_audio) / (sample_rate * channels * bytes_per_sample)
                stream_info["total_duration"] += duration
                
                # 檢查是否需要進行轉譯
                buffer_duration = self._calculate_buffer_duration(stream_info)
                
                if buffer_duration >= self.max_segment_duration:
                    # 執行轉譯
                    result = await self._transcribe_buffer(stream_info)
                    
                    # 清空緩衝
                    stream_info["buffer"].clear()
                    
                    # 更新統計
                    stream_info["segment_count"] += 1
                    
                    # 使用 PyStoreX 更新 Session 狀態回 LISTENING
                    store.dispatch(sessions_actions.update_session_state(session_id, FSMStateEnum.LISTENING.value))
                    
                    return result
            
            # 使用 PyStoreX 更新 Session 狀態回 LISTENING
            store.dispatch(sessions_actions.update_session_state(session_id, FSMStateEnum.LISTENING.value))
            
            return None
            
        except Exception as e:
            logger.error(f"處理音訊片段失敗：{e}")
            # 使用 PyStoreX 恢復 Session 狀態
            store.dispatch(sessions_actions.update_session_state(session_id, FSMStateEnum.LISTENING.value))
            raise StreamError(f"音訊處理失敗：{str(e)}")
    
    async def process_audio_stream(self,
                                  session_id: str,
                                  audio_stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        處理音訊串流
        
        Args:
            session_id: Session ID
            audio_stream: 音訊資料串流
            
        Yields:
            轉譯結果
            
        Raises:
            StreamError: 如果處理失敗
        """
        if session_id not in self.active_streams:
            raise StreamError(f"Session {session_id} 沒有活動串流")
        
        stream_info = self.active_streams[session_id]
        
        try:
            # 建立處理過的音訊串流
            async def processed_stream():
                async for chunk in audio_stream:
                    if chunk:
                        # 直接使用原始音訊
                        processed = chunk
                        if processed:
                            yield processed
            
            # 使用 Provider 進行串流轉譯
            provider = stream_info["provider"]
            async for result in provider.transcribe_stream(
                processed_stream(),
                language=stream_info["config"]["language"]
            ):
                # 記錄結果
                stream_info["transcription_results"].append({
                    "timestamp": datetime.now(),
                    "result": result
                })
                
                # 更新統計
                stream_info["segment_count"] += 1
                
                # 返回格式化的結果
                yield {
                    "session_id": session_id,
                    "segment_id": stream_info["segment_count"],
                    "text": result.text,
                    "is_final": result.is_final,
                    "confidence": result.confidence,
                    "timestamp": result.timestamp,
                    "metadata": result.metadata
                }
                
        except Exception as e:
            logger.error(f"處理音訊串流失敗：{e}")
            raise StreamError(f"串流處理失敗：{str(e)}")
    
    async def stop_stream(self, session_id: str) -> Dict[str, Any]:
        """
        停止音訊串流
        
        Args:
            session_id: Session ID
            
        Returns:
            串流統計資訊
            
        Raises:
            StreamError: 如果停止失敗
        """
        if session_id not in self.active_streams:
            raise StreamError(f"Session {session_id} 沒有活動串流")
        
        stream_info = self.active_streams[session_id]
        
        try:
            # 處理剩餘的緩衝資料
            if stream_info["buffer"]:
                await self._transcribe_buffer(stream_info)
            
            # 計算統計資訊
            end_time = datetime.now()
            duration = (end_time - stream_info["start_time"]).total_seconds()
            
            stats = {
                "session_id": session_id,
                "start_time": stream_info["start_time"].isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration,
                "total_audio_duration": stream_info["total_duration"],
                "segment_count": stream_info["segment_count"],
                "transcription_count": len(stream_info["transcription_results"])
            }
            
            # 使用 PyStoreX 更新 Session 狀態
            store.dispatch(sessions_actions.update_session_state(session_id, FSMStateEnum.IDLE.value))
            
            # 清理串流資訊
            del self.active_streams[session_id]
            
            logger.info(
                f"串流已停止 - Session: {session_id}, "
                f"持續時間: {duration:.2f}秒, "
                f"片段數: {stream_info['segment_count']}"
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"停止串流失敗：{e}")
            raise StreamError(f"無法停止串流：{str(e)}")
    
    def _calculate_buffer_duration(self, stream_info: Dict[str, Any]) -> float:
        """
        計算緩衝區中的音訊時長
        
        Args:
            stream_info: 串流資訊
            
        Returns:
            音訊時長（秒）
        """
        if not stream_info["buffer"]:
            return 0.0
        
        total_bytes = sum(len(chunk) for chunk in stream_info["buffer"])
        sample_rate = stream_info["config"]["sample_rate"]
        channels = stream_info["config"]["channels"]
        bytes_per_sample = 2  # 16-bit
        
        duration = total_bytes / (sample_rate * channels * bytes_per_sample)
        return duration
    
    async def _transcribe_buffer(self, stream_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        轉譯緩衝區中的音訊
        
        Args:
            stream_info: 串流資訊
            
        Returns:
            轉譯結果
        """
        # 合併緩衝區中的音訊
        audio_data = b"".join(stream_info["buffer"])
        
        # 使用 Provider 進行轉譯
        provider = stream_info["provider"]
        result = await provider.transcribe(
            audio_data,
            language=stream_info["config"]["language"]
        )
        
        # 記錄結果
        stream_info["transcription_results"].append({
            "timestamp": datetime.now(),
            "result": result
        })
        
        # 返回格式化的結果
        return {
            "session_id": stream_info["session_id"],
            "segment_id": stream_info["segment_count"] + 1,
            "text": result.text,
            "segments": [
                {
                    "text": seg.text,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "confidence": seg.confidence
                }
                for seg in result.segments
            ],
            "language": result.language,
            "confidence": result.confidence,
            "processing_time": result.processing_time,
            "audio_duration": result.audio_duration
        }
    
    def get_active_streams(self) -> List[str]:
        """
        獲取所有活動串流的 Session ID
        
        Returns:
            Session ID 列表
        """
        return list(self.active_streams.keys())
    
    def get_stream_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取串流資訊
        
        Args:
            session_id: Session ID
            
        Returns:
            串流資訊，如果不存在則返回 None
        """
        if session_id not in self.active_streams:
            return None
        
        stream_info = self.active_streams[session_id]
        
        return {
            "session_id": session_id,
            "start_time": stream_info["start_time"].isoformat(),
            "config": stream_info["config"],
            "total_duration": stream_info["total_duration"],
            "segment_count": stream_info["segment_count"],
            "buffer_size": len(stream_info["buffer"]),
            "transcription_count": len(stream_info["transcription_results"])
        }
    
    async def cleanup(self):
        """清理所有資源"""
        logger.info("清理 Stream Controller...")
        
        # 停止所有活動串流
        for session_id in list(self.active_streams.keys()):
            try:
                await self.stop_stream(session_id)
            except Exception as e:
                logger.error(f"停止串流 {session_id} 時發生錯誤：{e}")
        
        self.active_streams.clear()
        self._initialized = False
        logger.info("Stream Controller 清理完成")
    
    def get_status(self) -> Dict[str, Any]:
        """
        獲取 Stream Controller 狀態
        
        Returns:
            狀態資訊
        """
        return {
            "initialized": self._initialized,
            "active_stream_count": len(self.active_streams),
            "active_sessions": self.get_active_streams(),
            "config": {
                "buffer_size": self.buffer_size,
                "silence_timeout": self.silence_timeout,
                "max_segment_duration": self.max_segment_duration,
                "enable_vad": self.enable_vad
            }
        }