"""
ASR Hub Stream Controller
控制和協調音訊流的處理
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime
from src.utils.logger import logger
from src.core.exceptions import StreamError, SessionError
from src.core.session_manager import SessionManager
from src.pipeline.manager import PipelineManager
from src.providers.manager import ProviderManager
from src.models.audio import AudioChunk
from src.models.session import SessionState
from src.config.manager import ConfigManager


class StreamController:
    """
    串流控制器
    負責協調音訊流的接收、處理和轉譯
    """
    
    def __init__(self,
                 session_manager: SessionManager,
                 pipeline_manager: PipelineManager,
                 provider_manager: ProviderManager):
        """
        初始化 Stream Controller
        使用 ConfigManager 獲取配置
        
        Args:
            session_manager: Session 管理器
            pipeline_manager: Pipeline 管理器
            provider_manager: Provider 管理器
        """
        self.config_manager = ConfigManager()
        self.session_manager = session_manager
        self.pipeline_manager = pipeline_manager
        self.provider_manager = provider_manager
        
        self.logger = logger
        
        # 串流配置
        stream_config = self.config_manager.stream
        self.buffer_size = stream_config.buffer.size
        self.silence_timeout = stream_config.silence_timeout
        self.max_segment_duration = stream_config.max_segment_duration
        self.enable_vad = stream_config.enable_vad
        
        # 活動串流追蹤
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        
        self._initialized = False
    
    async def initialize(self):
        """初始化 Stream Controller"""
        if self._initialized:
            return
        
        self.logger.info("初始化 Stream Controller...")
        
        # 確保相關管理器已初始化
        if not self.session_manager or not self.pipeline_manager or not self.provider_manager:
            raise StreamError("相關管理器未正確初始化")
        
        self._initialized = True
        self.logger.success("Stream Controller 初始化完成")
    
    async def start_stream(self,
                          session_id: str,
                          **kwargs) -> Dict[str, Any]:
        """
        開始新的音訊串流
        
        Args:
            session_id: Session ID
            **kwargs: 額外參數
                - pipeline: Pipeline 名稱（預設 "default"）
                - provider: Provider 名稱（預設使用預設 Provider）
                - language: 語言代碼
                - sample_rate: 取樣率
                - channels: 聲道數
                
        Returns:
            串流資訊
            
        Raises:
            StreamError: 如果啟動失敗
        """
        # 檢查 Session 是否存在
        session = self.session_manager.get_session(session_id)
        if not session:
            raise SessionError(f"Session {session_id} 不存在")
        
        # 檢查是否已有活動串流
        if session_id in self.active_streams:
            raise StreamError(f"Session {session_id} 已有活動串流")
        
        try:
            # 獲取 Pipeline 和 Provider
            pipeline_name = kwargs.get("pipeline", "default")
            pipeline = self.pipeline_manager.get_pipeline(pipeline_name)
            if not pipeline:
                raise StreamError(f"Pipeline '{pipeline_name}' 不存在")
            
            provider_name = kwargs.get("provider")
            provider = self.provider_manager.get_provider(provider_name)
            if not provider:
                raise StreamError(f"Provider '{provider_name or 'default'}' 不存在")
            
            # 建立串流資訊
            stream_info = {
                "session_id": session_id,
                "pipeline": pipeline,
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
            
            # 更新 Session 狀態
            self.session_manager.update_session_state(session_id, SessionState.LISTENING)
            
            # 儲存串流資訊
            self.active_streams[session_id] = stream_info
            
            self.logger.info(
                f"串流已啟動 - Session: {session_id}, "
                f"Pipeline: {pipeline_name}, "
                f"Provider: {provider_name or 'default'}"
            )
            
            return {
                "session_id": session_id,
                "stream_id": f"stream_{session_id}_{int(stream_info['start_time'].timestamp())}",
                "pipeline": pipeline_name,
                "provider": provider_name or self.provider_manager.default_provider,
                "config": stream_info["config"]
            }
            
        except Exception as e:
            self.logger.error(f"啟動串流失敗：{e}")
            # 清理狀態
            if session_id in self.active_streams:
                del self.active_streams[session_id]
            raise StreamError(f"無法啟動串流：{str(e)}")
    
    async def process_audio_chunk(self,
                                 session_id: str,
                                 audio_chunk: bytes) -> Optional[Dict[str, Any]]:
        """
        處理音訊片段
        
        Args:
            session_id: Session ID
            audio_chunk: 音訊資料片段
            
        Returns:
            處理結果（如果有）
            
        Raises:
            StreamError: 如果處理失敗
        """
        if session_id not in self.active_streams:
            raise StreamError(f"Session {session_id} 沒有活動串流")
        
        stream_info = self.active_streams[session_id]
        
        try:
            # 更新 Session 狀態為 BUSY
            self.session_manager.update_session_state(session_id, SessionState.BUSY)
            
            # 通過 Pipeline 處理音訊
            pipeline = stream_info["pipeline"]
            processed_audio = await pipeline.process(
                audio_chunk,
                **stream_info["config"]
            )
            
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
                    
                    # 更新 Session 狀態回 LISTENING
                    self.session_manager.update_session_state(session_id, SessionState.LISTENING)
                    
                    return result
            
            # 更新 Session 狀態回 LISTENING
            self.session_manager.update_session_state(session_id, SessionState.LISTENING)
            
            return None
            
        except Exception as e:
            self.logger.error(f"處理音訊片段失敗：{e}")
            # 恢復 Session 狀態
            self.session_manager.update_session_state(session_id, SessionState.LISTENING)
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
                        # 通過 Pipeline 處理
                        processed = await stream_info["pipeline"].process(
                            chunk,
                            **stream_info["config"]
                        )
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
            self.logger.error(f"處理音訊串流失敗：{e}")
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
            
            # 更新 Session 狀態
            self.session_manager.update_session_state(session_id, SessionState.IDLE)
            
            # 清理串流資訊
            del self.active_streams[session_id]
            
            self.logger.info(
                f"串流已停止 - Session: {session_id}, "
                f"持續時間: {duration:.2f}秒, "
                f"片段數: {stream_info['segment_count']}"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(f"停止串流失敗：{e}")
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
        self.logger.info("清理 Stream Controller...")
        
        # 停止所有活動串流
        for session_id in list(self.active_streams.keys()):
            try:
                await self.stop_stream(session_id)
            except Exception as e:
                self.logger.error(f"停止串流 {session_id} 時發生錯誤：{e}")
        
        self.active_streams.clear()
        self._initialized = False
        self.logger.info("Stream Controller 清理完成")
    
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