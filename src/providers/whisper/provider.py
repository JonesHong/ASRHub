"""
ASR Hub Local Whisper Provider
使用 OpenAI Whisper 或 Faster-Whisper 進行本地語音轉文字
"""

import asyncio
import time
import os
from typing import Dict, Any, Optional, List, AsyncGenerator
import numpy as np
from datetime import datetime
from src.providers.base import ProviderBase, TranscriptionResult, StreamingResult
from src.utils.logger import get_logger
from src.core.exceptions import ProviderError, ModelError, AudioFormatError
from src.models.transcript import TranscriptSegment, Word
from src.config.manager import ConfigManager


class WhisperProvider(ProviderBase):
    """
    Local Whisper ASR Provider
    支援 OpenAI Whisper 和 Faster-Whisper
    """
    
    def __init__(self):
        """
        初始化 Whisper Provider
        使用 ConfigManager 獲取配置
        """
        # 從 ConfigManager 獲取配置
        config_manager = ConfigManager()
        whisper_config = config_manager.providers.whisper
        
        # 轉換為字典以兼容父類
        config_dict = whisper_config.to_dict()
        super().__init__(config_dict)
        
        self.logger = get_logger("provider.whisper")
        
        # 模型配置
        self.model_size = whisper_config.model_size
        self.use_faster_whisper = whisper_config.use_faster_whisper
        
        # Whisper 特定參數
        self.beam_size = whisper_config.beam_size
        self.best_of = whisper_config.best_of
        self.temperature = whisper_config.temperature
        self.initial_prompt = whisper_config.initial_prompt
        
        # 模型實例
        self.model = None
        
        # VAD 設定
        self.vad_filter = whisper_config.vad_filter
        
        # 支援的語言
        self.supported_languages = [
            "zh", "en", "es", "fr", "de", "ja", "ko", "ru", "ar", "hi",
            "pt", "it", "tr", "pl", "nl", "sv", "id", "th", "vi", "ms"
        ]
        
        self._processing_lock = asyncio.Lock()
    
    async def _load_model(self):
        """載入 Whisper 模型"""
        try:
            if self.use_faster_whisper:
                await self._load_faster_whisper()
            else:
                await self._load_openai_whisper()
            
            self.logger.success(
                f"Whisper 模型載入成功 - "
                f"模型：{self.model_size}，"
                f"裝置：{self.device}，"
                f"引擎：{'faster-whisper' if self.use_faster_whisper else 'openai-whisper'}"
            )
            
        except Exception as e:
            self.logger.error(f"載入 Whisper 模型失敗：{e}")
            raise ModelError(f"無法載入 Whisper 模型：{str(e)}")
    
    async def _load_faster_whisper(self):
        """載入 Faster-Whisper 模型"""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ModelError(
                "未安裝 faster-whisper。"
                "請執行：pip install faster-whisper"
            )
        
        # 設定計算類型
        compute_type = self.compute_type
        if compute_type == "default":
            if self.device == "cuda":
                compute_type = "float16"
            else:
                compute_type = "int8" if self.model_size != "large" else "float32"
        
        # 建立模型
        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=compute_type,
            download_root=self.model_path
        )
    
    async def _load_openai_whisper(self):
        """載入 OpenAI Whisper 模型"""
        try:
            import whisper
        except ImportError:
            raise ModelError(
                "未安裝 openai-whisper。"
                "請執行：pip install openai-whisper"
            )
        
        # 載入模型
        self.model = whisper.load_model(
            self.model_size,
            device=self.device,
            download_root=self.model_path
        )
    
    async def _unload_model(self):
        """卸載模型"""
        if self.model is not None:
            # 清理 GPU 記憶體
            if self.device == "cuda":
                try:
                    import torch
                    if hasattr(self.model, 'model'):
                        del self.model.model
                    torch.cuda.empty_cache()
                except:
                    pass
            
            self.model = None
            self.logger.info("Whisper 模型已卸載")
    
    async def transcribe(self, 
                        audio_data: bytes, 
                        **kwargs) -> TranscriptionResult:
        """
        執行單次語音轉譯
        
        Args:
            audio_data: 音訊資料（PCM 格式）
            **kwargs: 額外參數
                - language: 指定語言
                - initial_prompt: 初始提示詞
                - temperature: 溫度參數
                
        Returns:
            轉譯結果
        """
        if not self._initialized:
            raise ProviderError("Provider 尚未初始化")
        
        if not self.validate_audio_format(audio_data):
            raise AudioFormatError("無效的音訊格式")
        
        async with self._processing_lock:
            start_time = time.time()
            
            try:
                # 將音訊轉換為 numpy 陣列
                audio_array = self._bytes_to_float32(audio_data)
                
                # 執行轉譯
                if self.use_faster_whisper:
                    result = await self._transcribe_faster_whisper(
                        audio_array, **kwargs
                    )
                else:
                    result = await self._transcribe_openai_whisper(
                        audio_array, **kwargs
                    )
                
                # 記錄處理時間
                result.processing_time = time.time() - start_time
                result.audio_duration = len(audio_array) / self.sample_rate
                
                self.logger.info(
                    f"轉譯完成 - "
                    f"文字長度：{len(result.text)}，"
                    f"處理時間：{result.processing_time:.2f}秒，"
                    f"即時因子：{result.processing_time / result.audio_duration:.2f}x"
                )
                
                return result
                
            except Exception as e:
                self.logger.error(f"轉譯失敗：{e}")
                raise ProviderError(f"Whisper 轉譯失敗：{str(e)}")
    
    async def _transcribe_faster_whisper(self,
                                       audio_array: np.ndarray,
                                       **kwargs) -> TranscriptionResult:
        """使用 Faster-Whisper 進行轉譯"""
        # 設定參數
        language = kwargs.get("language", self.language)
        if language == "auto":
            language = None
        
        # 執行轉譯（在執行緒中運行以避免阻塞）
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            self._run_faster_whisper_transcribe,
            audio_array,
            language,
            kwargs
        )
        
        # 建立結果
        transcript_segments = []
        full_text = []
        
        for segment in segments:
            # 建立詞級別資訊
            words = None
            if hasattr(segment, 'words') and segment.words:
                words = [
                    Word(
                        text=w.word,
                        start_time=w.start,
                        end_time=w.end,
                        confidence=w.probability
                    )
                    for w in segment.words
                ]
            
            # 建立片段
            seg = TranscriptSegment(
                text=segment.text.strip(),
                start_time=segment.start,
                end_time=segment.end,
                confidence=segment.avg_logprob if hasattr(segment, 'avg_logprob') else 0.9,
                words=words,
                language=info.language if hasattr(info, 'language') else language
            )
            
            transcript_segments.append(seg)
            full_text.append(segment.text.strip())
        
        # 建立完整結果
        result = TranscriptionResult(
            text=" ".join(full_text),
            language=info.language if hasattr(info, 'language') else (language or "unknown"),
            confidence=np.mean([seg.confidence for seg in transcript_segments]) if transcript_segments else 0.0,
            metadata={
                "provider": "whisper",
                "model": f"whisper-{self.model_size}",
                "segments": [seg.to_dict() for seg in transcript_segments]
            }
        )
        
        return result
    
    def _run_faster_whisper_transcribe(self,
                                     audio_array: np.ndarray,
                                     language: Optional[str],
                                     kwargs: Dict[str, Any]):
        """在執行緒中執行 Faster-Whisper 轉譯"""
        segments, info = self.model.transcribe(
            audio_array,
            language=language,
            beam_size=kwargs.get("beam_size", self.beam_size),
            temperature=kwargs.get("temperature", self.temperature),
            initial_prompt=kwargs.get("initial_prompt", self.initial_prompt),
            vad_filter=self.vad_filter,
            word_timestamps=True
        )
        
        # 轉換為列表（因為 generator 不能跨執行緒傳遞）
        return list(segments), info
    
    async def _transcribe_openai_whisper(self,
                                       audio_array: np.ndarray,
                                       **kwargs) -> TranscriptionResult:
        """使用 OpenAI Whisper 進行轉譯"""
        # 設定參數
        language = kwargs.get("language", self.language)
        if language == "auto":
            language = None
        
        # 執行轉譯
        loop = asyncio.get_event_loop()
        result_dict = await loop.run_in_executor(
            None,
            self.model.transcribe,
            audio_array,
            language=language,
            temperature=kwargs.get("temperature", self.temperature),
            initial_prompt=kwargs.get("initial_prompt", self.initial_prompt),
            verbose=False
        )
        
        # 解析結果
        segments = result_dict.get("segments", [])
        transcript_segments = []
        
        for segment in segments:
            seg = TranscriptSegment(
                text=segment["text"].strip(),
                start_time=segment["start"],
                end_time=segment["end"],
                confidence=0.9,  # OpenAI Whisper 不提供信心分數
                language=result_dict.get("language", language or "unknown")
            )
            transcript_segments.append(seg)
        
        # 建立完整結果
        result = TranscriptionResult(
            text=result_dict["text"].strip(),
            segments=transcript_segments,
            language=result_dict.get("language", language or "unknown"),
            confidence=0.9,
            provider="whisper",
            model=f"whisper-{self.model_size}"
        )
        
        return result
    
    async def transcribe_stream(self, 
                              audio_stream: AsyncGenerator[bytes, None],
                              **kwargs) -> AsyncGenerator[StreamingResult, None]:
        """
        執行串流語音轉譯
        
        Args:
            audio_stream: 音訊資料串流
            **kwargs: 額外參數
            
        Yields:
            串流轉譯結果
        """
        raise NotImplementedError(
            "Whisper 模型不支援真正的串流轉錄。"
            "請使用 transcribe() 方法進行批次轉錄，"
            "或考慮使用支援串流的 ASR 服務（如 Google Speech-to-Text、Azure Speech）。"
        )
    
    
    def _bytes_to_float32(self, audio_bytes: bytes) -> np.ndarray:
        """
        將音訊位元組轉換為 float32 陣列
        
        Args:
            audio_bytes: PCM 音訊資料
            
        Returns:
            正規化的 float32 陣列
        """
        # 假設輸入是 16-bit PCM
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # 轉換為 float32 並正規化到 [-1, 1]
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        
        return audio_float32
    
    def get_model_info(self) -> Dict[str, Any]:
        """獲取模型資訊"""
        info = super().get_model_info()
        info.update({
            "engine": "faster-whisper" if self.use_faster_whisper else "openai-whisper",
            "model_size": self.model_size,
            "beam_size": self.beam_size,
            "temperature": self.temperature,
            "vad_filter": self.vad_filter
        })
        return info
    
    async def transcribe_file(self, 
                            file_path: str,
                            language: Optional[str] = None,
                            **kwargs) -> TranscriptionResult:
        """
        轉譯音訊檔案
        
        Args:
            file_path: 音訊檔案路徑
            language: 語言代碼（None 表示自動偵測）
            **kwargs: 其他參數
            
        Returns:
            轉譯結果
        """
        if not self._initialized:
            raise ProviderError("Provider 尚未初始化")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"音訊檔案不存在：{file_path}")
        
        self.logger.info(f"開始轉譯檔案：{file_path}")
        
        try:
            # 使用 faster-whisper 或 whisper 直接載入檔案
            if self.use_faster_whisper:
                # Faster-whisper 可以直接處理檔案
                # 我們將在 _transcribe_faster_whisper 中直接處理檔案
                audio_array = None  # 標記為需要從檔案載入
            else:
                # 使用 whisper 的 load_audio 函數
                import whisper
                audio_array = whisper.load_audio(file_path)
                # whisper.load_audio 已經返回 16kHz 的音訊
            
            # 如果有指定語言，加入到 kwargs
            if language:
                kwargs['language'] = language
            
            # 執行轉譯
            async with self._processing_lock:
                start_time = time.time()
                
                if self.use_faster_whisper:
                    # 對於 faster-whisper，直接傳遞檔案路徑
                    result = await self._transcribe_faster_whisper_file(
                        file_path, **kwargs
                    )
                else:
                    result = await self._transcribe_openai_whisper(
                        audio_array, **kwargs
                    )
                
                # 記錄處理時間
                result.processing_time = time.time() - start_time
                # 使用 result 中的 audio_duration 如果有的話
                if not hasattr(result, 'audio_duration'):
                    result.audio_duration = 0  # 將在轉譯函數中設定
                
                self.logger.info(
                    f"檔案轉譯完成 - "
                    f"檔案：{os.path.basename(file_path)}，"
                    f"文字長度：{len(result.text)}，"
                    f"處理時間：{result.processing_time:.2f}秒，"
                    f"即時因子：{result.processing_time / result.audio_duration:.2f}x"
                )
                
                return result
            
        except Exception as e:
            self.logger.error(f"檔案轉譯失敗：{e}")
            raise ProviderError(f"Whisper 檔案轉譯失敗：{str(e)}")
    
    async def _transcribe_faster_whisper_file(self,
                                             file_path: str,
                                             **kwargs) -> TranscriptionResult:
        """使用 Faster-Whisper 直接從檔案進行轉譯"""
        # 設定參數
        language = kwargs.get("language", self.language)
        if language == "auto":
            language = None
        
        # 執行轉譯（在執行緒中運行以避免阻塞）
        loop = asyncio.get_event_loop()
        
        def transcribe_with_file():
            # Faster-whisper 可以直接接受檔案路徑
            segments, info = self.model.transcribe(
                file_path,
                language=language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                temperature=self.temperature,
                initial_prompt=kwargs.get("initial_prompt")
            )
            return list(segments), info  # 轉換為列表以避免生成器問題
        
        segments, info = await loop.run_in_executor(None, transcribe_with_file)
        
        # 建立結果
        transcript_segments = []
        full_text = []
        
        for segment in segments:
            # 建立詞級別資訊
            words = None
            if hasattr(segment, 'words') and segment.words:
                words = [
                    Word(
                        text=w.word,
                        start_time=w.start,
                        end_time=w.end,
                        confidence=w.probability
                    )
                    for w in segment.words
                ]
            
            # 建立片段
            seg = TranscriptSegment(
                text=segment.text.strip(),
                start_time=segment.start,
                end_time=segment.end,
                confidence=segment.avg_logprob if hasattr(segment, 'avg_logprob') else 0.9,
                words=words,
                language=info.language if hasattr(info, 'language') else language
            )
            
            transcript_segments.append(seg)
            full_text.append(segment.text.strip())
        
        # 建立完整結果
        result = TranscriptionResult(
            text=" ".join(full_text),
            language=info.language if hasattr(info, 'language') else (language or "unknown"),
            confidence=np.mean([seg.confidence for seg in transcript_segments]) if transcript_segments else 0.0,
            metadata={
                "provider": "whisper",
                "model": f"whisper-{self.model_size}",
                "segments": [seg.to_dict() for seg in transcript_segments]
            }
        )
        
        # 設定音訊時長（從最後一個 segment 的結束時間）
        if transcript_segments:
            result.audio_duration = transcript_segments[-1].end_time
        else:
            result.audio_duration = 0
        
        return result
    
    async def warmup(self):
        """預熱模型"""
        if not self._initialized:
            await self.initialize()
        
        self.logger.debug("開始預熱 Whisper 模型")
        
        # 使用 1 秒的靜音進行預熱
        silence_duration = 1.0
        silence_samples = int(self.sample_rate * silence_duration)
        silence_data = np.zeros(silence_samples, dtype=np.float32)
        silence_bytes = (silence_data * 32767).astype(np.int16).tobytes()
        
        try:
            # 執行一次轉譯
            await self.transcribe(silence_bytes)
            self.logger.debug("Whisper 模型預熱完成")
        except Exception as e:
            self.logger.warning(f"模型預熱失敗：{e}")