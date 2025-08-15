"""
ASR Hub 計時器服務
管理各種超時和計時器邏輯
"""

import asyncio
from typing import Dict, Callable, Optional, Any
from src.utils.logger import logger
from src.core.fsm import FSMController, FSMEvent
from src.config.manager import ConfigManager


class TimerService:
    """計時器服務，管理 FSM 相關的各種計時器"""
    
    def __init__(self, fsm_controller: Optional[FSMController] = None):
        """
        初始化計時器服務
        
        Args:
            fsm_controller: FSM 控制器實例
        """
        self.fsm = fsm_controller
        self.timers: Dict[str, asyncio.Task] = {}
        self.config = ConfigManager()
        self.logger = logger
        
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
        
        self.logger.info("計時器服務初始化完成")
    
    async def start_awake_timer(self):
        """喚醒視窗計時器"""
        timeout = self._get_timeout('awake')
        if timeout > 0:
            await self._start_timer('awake', timeout, FSMEvent.TIMEOUT)
            self.logger.debug(f"啟動喚醒視窗計時器：{timeout}ms")
    
    async def start_llm_claim_timer(self):
        """LLM 接手等待計時器"""
        timeout = self._get_timeout('llm_claim')
        await self._start_timer('llm_claim', timeout, self._handle_llm_timeout)
        self.logger.debug(f"啟動 LLM 接手計時器：{timeout}ms")
    
    async def start_tts_claim_timer(self):
        """TTS 接手等待計時器"""
        timeout = self._get_timeout('tts_claim')
        await self._start_timer('tts_claim', timeout, self._handle_tts_timeout)
        self.logger.debug(f"啟動 TTS 接手計時器：{timeout}ms")
    
    async def start_recording_timer(self):
        """錄音上限計時器"""
        timeout = self._get_timeout('recording')
        if timeout > 0:
            await self._start_timer('recording', timeout, FSMEvent.END_RECORDING)
            self.logger.debug(f"啟動錄音計時器：{timeout}ms")
    
    async def start_streaming_timer(self):
        """串流上限計時器"""
        timeout = self._get_timeout('streaming')
        if timeout > 0:
            await self._start_timer('streaming', timeout, FSMEvent.END_ASR_STREAMING)
            self.logger.debug(f"啟動串流計時器：{timeout}ms")
    
    async def start_session_idle_timer(self):
        """會話閒置計時器"""
        timeout = self._get_timeout('session_idle')
        if timeout > 0:
            await self._start_timer('session_idle', timeout, FSMEvent.RESET)
            self.logger.debug(f"啟動會話閒置計時器：{timeout}ms")
    
    async def start_vad_silence_timer(self, callback: Optional[Callable] = None):
        """
        VAD 靜音計時器
        
        Args:
            callback: 超時回調函數
        """
        timeout = self._get_timeout('vad_silence')
        if timeout > 0:
            handler = callback or self._handle_vad_silence_timeout
            await self._start_timer('vad_silence', timeout, handler)
            self.logger.debug(f"啟動 VAD 靜音計時器：{timeout}ms")
    
    async def reset_timer(self, name: str):
        """
        重置計時器（取消並重新啟動）
        
        Args:
            name: 計時器名稱
        """
        if name in self.timers:
            self.cancel_timer(name)
        
        # 根據名稱重新啟動對應的計時器
        timer_methods = {
            'awake': self.start_awake_timer,
            'llm_claim': self.start_llm_claim_timer,
            'tts_claim': self.start_tts_claim_timer,
            'recording': self.start_recording_timer,
            'streaming': self.start_streaming_timer,
            'session_idle': self.start_session_idle_timer,
            'vad_silence': self.start_vad_silence_timer,
        }
        
        if name in timer_methods:
            await timer_methods[name]()
            self.logger.debug(f"重置計時器：{name}")
    
    async def _start_timer(self, name: str, timeout_ms: int, handler):
        """
        通用計時器啟動
        
        Args:
            name: 計時器名稱
            timeout_ms: 超時時間（毫秒）
            handler: 超時處理器（可以是 FSMEvent 或回調函數）
        """
        # 取消現有計時器
        if name in self.timers:
            self.timers[name].cancel()
            self.logger.debug(f"取消現有計時器：{name}")
        
        async def timer_task():
            try:
                await asyncio.sleep(timeout_ms / 1000)
                self.logger.info(f"計時器 {name} 超時（{timeout_ms}ms）")
                
                if callable(handler):
                    # 如果是回調函數，直接調用
                    await handler()
                elif self.fsm:
                    # 如果是 FSMEvent，觸發事件
                    await self.fsm.handle_event(handler, timer=name)
                else:
                    self.logger.warning(f"計時器 {name} 超時但沒有 FSM 控制器")
            except asyncio.CancelledError:
                self.logger.debug(f"計時器 {name} 被取消")
                raise
            except Exception as e:
                self.logger.error(f"計時器 {name} 處理錯誤：{e}")
        
        self.timers[name] = asyncio.create_task(timer_task())
    
    async def _handle_llm_timeout(self):
        """LLM 超時處理"""
        if self.fsm:
            from src.core.fsm import FSMState
            if self.fsm.state == FSMState.TRANSCRIBING:
                # 沒有 LLM 接手，回到 ACTIVATED
                self.logger.info("LLM 接手超時，返回喚醒視窗")
                await self.fsm.handle_event(FSMEvent.TIMEOUT, timer='llm_claim')
        else:
            self.logger.warning("LLM 超時但沒有 FSM 控制器")
    
    async def _handle_tts_timeout(self):
        """TTS 超時處理"""
        if self.fsm:
            from src.core.fsm import FSMState
            if self.fsm.state == FSMState.BUSY:
                # 沒有 TTS 接手，回到 ACTIVATED
                self.logger.info("TTS 接手超時，返回喚醒視窗")
                await self.fsm.handle_event(FSMEvent.TIMEOUT, timer='tts_claim')
        else:
            self.logger.warning("TTS 超時但沒有 FSM 控制器")
    
    async def _handle_vad_silence_timeout(self):
        """VAD 靜音超時處理"""
        if self.fsm:
            from src.core.fsm import FSMState, FSMEndTrigger
            
            if self.fsm.state == FSMState.RECORDING:
                self.logger.info("VAD 靜音超時，結束錄音")
                await self.fsm.handle_event(
                    FSMEvent.END_RECORDING,
                    trigger=FSMEndTrigger.VAD_TIMEOUT
                )
            elif self.fsm.state == FSMState.STREAMING:
                self.logger.info("VAD 靜音超時，結束串流")
                await self.fsm.handle_event(
                    FSMEvent.END_ASR_STREAMING,
                    trigger=FSMEndTrigger.VAD_TIMEOUT
                )
        else:
            self.logger.warning("VAD 靜音超時但沒有 FSM 控制器")
    
    def cancel_timer(self, name: str):
        """
        取消計時器
        
        Args:
            name: 計時器名稱
        """
        if name in self.timers:
            self.timers[name].cancel()
            del self.timers[name]
            self.logger.debug(f"取消計時器：{name}")
    
    def cancel_all_timers(self):
        """取消所有計時器"""
        for timer in self.timers.values():
            timer.cancel()
        self.timers.clear()
        self.logger.debug("取消所有計時器")
    
    def _get_timeout(self, timer_type: str) -> int:
        """
        獲取超時時間配置
        
        Args:
            timer_type: 計時器類型
            
        Returns:
            超時時間（毫秒）
        """
        # 嘗試從配置中獲取
        try:
            if hasattr(self.config, 'realtime'):
                realtime_config = self.config.realtime
                
                # 根據不同的計時器類型獲取配置
                timeout_map = {
                    'awake': lambda: realtime_config.fcm.awakeTimeoutMs,
                    'llm_claim': lambda: realtime_config.fcm.llmClaimTtl,
                    'tts_claim': lambda: realtime_config.fcm.ttsClaimTtl,
                    'recording': lambda: realtime_config.fcm.maxRecordingMs,
                    'streaming': lambda: realtime_config.fcm.maxStreamingMs,
                    'session_idle': lambda: realtime_config.fcm.sessionIdleTimeoutMs,
                    'vad_silence': lambda: int(realtime_config.vad.silence_duration * 1000),
                }
                
                if timer_type in timeout_map:
                    timeout = timeout_map[timer_type]()
                    if timeout is not None:
                        return timeout
        except Exception as e:
            self.logger.debug(f"無法從配置獲取 {timer_type} 超時時間：{e}")
        
        # 返回預設值
        return self.default_timeouts.get(timer_type, 5000)
    
    def get_active_timers(self) -> Dict[str, bool]:
        """
        獲取活動計時器狀態
        
        Returns:
            計時器狀態字典
        """
        return {
            name: not task.done() 
            for name, task in self.timers.items()
        }
    
    def get_timer_info(self) -> Dict[str, Any]:
        """
        獲取計時器詳細資訊
        
        Returns:
            計時器資訊字典
        """
        return {
            "active_timers": list(self.timers.keys()),
            "timer_status": self.get_active_timers(),
            "configured_timeouts": {
                timer_type: self._get_timeout(timer_type)
                for timer_type in self.default_timeouts.keys()
            }
        }