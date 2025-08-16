"""
ASR Hub 計時器服務
管理各種超時和計時器邏輯
"""

import asyncio
from typing import Dict, Callable, Optional, Any
from src.utils.logger import logger
from src.store import get_global_store
from src.store.sessions import sessions_actions
from src.store.sessions.sessions_state import FSMStateEnum
from src.config.manager import ConfigManager


class TimerService:
    """計時器服務，管理 Session 相關的各種計時器"""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        初始化計時器服務
        
        Args:
            session_id: 會話 ID（用於 PyStoreX）
        """
        self.session_id = session_id
        self.store = get_global_store() if session_id else None
        self.timers: Dict[str, asyncio.Task] = {}
        self.config = ConfigManager()
        
        # 預設超時時間（毫秒）
        self.default_timeouts = {
            'awake': 8000,          # 喚醒視窗超時
            'llm_claim': 3000,      # LLM 接手等待時間
            'tts_claim': 3000,      # TTS 接手等待時間
            'recording': -1,        # 錄音上限（-1 無上限）
            'streaming': -1,        # 串流上限（-1 無上限）
            'session_idle': 600000, # 會話閒置超時（10分鐘）
            'vad_silence': 2000,    # VAD 靜音超時
        }
        
        logger.info("計時器服務初始化完成")
    
    async def start_awake_timer(self):
        """喚醒視窗計時器"""
        timeout = self._get_timeout('awake')
        if timeout > 0 and self.session_id:
            await self._start_timer('awake', timeout, self._handle_awake_timeout)
            logger.debug(f"啟動喚醒視窗計時器：{timeout}ms")
    
    async def start_llm_claim_timer(self):
        """LLM 接手等待計時器"""
        timeout = self._get_timeout('llm_claim')
        if timeout > 0:
            await self._start_timer('llm_claim', timeout, self._handle_llm_timeout)
            logger.debug(f"啟動 LLM 接手計時器：{timeout}ms")
    
    async def start_tts_claim_timer(self):
        """TTS 接手等待計時器"""
        timeout = self._get_timeout('tts_claim')
        if timeout > 0:
            await self._start_timer('tts_claim', timeout, self._handle_tts_timeout)
            logger.debug(f"啟動 TTS 接手計時器：{timeout}ms")
    
    async def start_recording_timer(self):
        """錄音上限計時器"""
        timeout = self._get_timeout('recording')
        if timeout > 0 and self.session_id:
            await self._start_timer('recording', timeout, self._handle_recording_timeout)
            logger.debug(f"啟動錄音計時器：{timeout}ms")
    
    async def start_streaming_timer(self):
        """串流上限計時器"""
        timeout = self._get_timeout('streaming')
        if timeout > 0 and self.session_id:
            await self._start_timer('streaming', timeout, self._handle_streaming_timeout)
            logger.debug(f"啟動串流計時器：{timeout}ms")
    
    async def start_session_idle_timer(self):
        """會話閒置計時器"""
        timeout = self._get_timeout('session_idle')
        if timeout > 0 and self.session_id:
            await self._start_timer('session_idle', timeout, self._handle_session_idle_timeout)
            logger.debug(f"啟動會話閒置計時器：{timeout}ms")
    
    async def start_vad_silence_timer(self):
        """VAD 靜音計時器"""
        timeout = self._get_timeout('vad_silence')
        if timeout > 0:
            await self._start_timer('vad_silence', timeout, self._handle_vad_silence_timeout)
            logger.debug(f"啟動 VAD 靜音計時器：{timeout}ms")
    
    def restart_vad_timer(self):
        """重新啟動 VAD 計時器（檢測到語音時）"""
        if 'vad_silence' in self.timers:
            self.cancel_timer('vad_silence')
            # 重新啟動
            asyncio.create_task(self.start_vad_silence_timer())
            logger.debug("重置 VAD 靜音計時器")
    
    async def on_speech_detected(self):
        """當檢測到語音時的處理"""
        # 取消 VAD 靜音計時器
        self.cancel_timer('vad_silence')
        logger.debug("檢測到語音，取消 VAD 靜音計時器")
    
    async def on_silence_detected(self):
        """當檢測到靜音時的處理"""
        # 啟動 VAD 靜音計時器
        await self.start_vad_silence_timer()
        logger.debug("檢測到靜音，啟動 VAD 靜音計時器")
    
    async def on_transcription_start(self):
        """當開始轉譯時的處理"""
        # 啟動 LLM 接手計時器
        await self.start_llm_claim_timer()
    
    async def on_llm_response_start(self):
        """當 LLM 開始回應時的處理"""
        # 取消 LLM 計時器，啟動 TTS 計時器
        self.cancel_timer('llm_claim')
        await self.start_tts_claim_timer()
    
    async def on_tts_start(self):
        """當 TTS 開始播放時的處理"""
        # 取消 TTS 計時器
        self.cancel_timer('tts_claim')
    
    async def _start_timer(self, name: str, timeout_ms: int, handler):
        """
        通用計時器啟動
        
        Args:
            name: 計時器名稱
            timeout_ms: 超時時間（毫秒）
            handler: 超時處理器（回調函數）
        """
        # 取消現有計時器
        if name in self.timers:
            self.timers[name].cancel()
            logger.debug(f"取消現有計時器：{name}")
        
        async def timer_task():
            try:
                await asyncio.sleep(timeout_ms / 1000)
                logger.info(f"計時器 {name} 超時（{timeout_ms}ms）")
                
                if callable(handler):
                    # 如果是回調函數，直接調用
                    await handler()
                else:
                    logger.warning(f"計時器 {name} 超時但沒有處理器")
            except asyncio.CancelledError:
                logger.debug(f"計時器 {name} 被取消")
                raise
            except Exception as e:
                logger.error(f"計時器 {name} 處理錯誤：{e}")
        
        self.timers[name] = asyncio.create_task(timer_task())
    
    async def _handle_awake_timeout(self):
        """喚醒視窗超時處理"""
        if self.store and self.session_id:
            logger.info("喚醒視窗超時，重置 FSM")
            self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
    
    async def _handle_llm_timeout(self):
        """LLM 超時處理"""
        if self.store and self.session_id:
            # 檢查當前狀態
            state = self.store.state
            if hasattr(state, 'sessions') and state.sessions:
                sessions = state.sessions.get('sessions', {})
                session = sessions.get(self.session_id)
                if session and session.get('fsm_state') == FSMStateEnum.TRANSCRIBING:
                    # 沒有 LLM 接手，回到 ACTIVATED
                    logger.info("LLM 接手超時，返回喚醒視窗")
                    self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
    
    async def _handle_tts_timeout(self):
        """TTS 超時處理"""
        if self.store and self.session_id:
            # 檢查當前狀態
            state = self.store.state
            if hasattr(state, 'sessions') and state.sessions:
                sessions = state.sessions.get('sessions', {})
                session = sessions.get(self.session_id)
                if session and session.get('fsm_state') == FSMStateEnum.BUSY:
                    # 沒有 TTS 接手，回到 ACTIVATED
                    logger.info("TTS 接手超時，返回喚醒視窗")
                    self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
    
    async def _handle_vad_silence_timeout(self):
        """VAD 靜音超時處理"""
        if self.store and self.session_id:
            # 檢查當前狀態
            state = self.store.state
            if hasattr(state, 'sessions') and state.sessions:
                sessions = state.sessions.get('sessions', {})
                session = sessions.get(self.session_id)
                
                if session:
                    fsm_state = session.get('fsm_state')
                    if fsm_state == FSMStateEnum.RECORDING:
                        logger.info("VAD 靜音超時，結束錄音")
                        self.store.dispatch(
                            sessions_actions.end_recording(
                                self.session_id,
                                trigger="vad_timeout",
                                duration=0
                            )
                        )
                    elif fsm_state == FSMStateEnum.STREAMING:
                        logger.info("VAD 靜音超時，結束串流")
                        self.store.dispatch(
                            sessions_actions.end_streaming(self.session_id)
                        )
    
    async def _handle_recording_timeout(self):
        """錄音超時處理"""
        if self.store and self.session_id:
            logger.info("錄音超時，強制結束")
            self.store.dispatch(
                sessions_actions.end_recording(
                    self.session_id,
                    trigger="timeout",
                    duration=0
                )
            )
    
    async def _handle_streaming_timeout(self):
        """串流超時處理"""
        if self.store and self.session_id:
            logger.info("串流超時，強制結束")
            self.store.dispatch(
                sessions_actions.end_streaming(self.session_id)
            )
    
    async def _handle_session_idle_timeout(self):
        """會話閒置超時處理"""
        if self.store and self.session_id:
            logger.info("會話閒置超時，重置")
            self.store.dispatch(sessions_actions.reset_fsm(self.session_id))
    
    def cancel_timer(self, name: str):
        """
        取消計時器
        
        Args:
            name: 計時器名稱
        """
        if name in self.timers:
            self.timers[name].cancel()
            del self.timers[name]
            logger.debug(f"取消計時器：{name}")
    
    def cancel_all_timers(self):
        """取消所有計時器"""
        for timer in self.timers.values():
            timer.cancel()
        self.timers.clear()
        logger.debug("取消所有計時器")
    
    def _get_timeout(self, timer_type: str) -> int:
        """
        獲取超時時間配置
        
        Args:
            timer_type: 計時器類型
            
        Returns:
            超時時間（毫秒）
        """
        # 優先從配置文件讀取
        if hasattr(self.config, 'timers') and hasattr(self.config.timers, timer_type):
            return getattr(self.config.timers, timer_type)
        
        # 使用預設值
        return self.default_timeouts.get(timer_type, -1)