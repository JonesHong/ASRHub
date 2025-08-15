"""
Sessions 域的 Effects 實現
"""

import asyncio
from pystorex import create_effect
from reactivex import timer
from reactivex import operators as ops

from .sessions_actions import (
    wake_triggered, start_recording, start_streaming, reset_fsm,
    session_error, transcription_done, begin_transcription, end_recording
)


class SessionEffects:
    """Session 相關的 Effects"""
    
    def __init__(self, logger=None):
        self.logger = logger
    
    @create_effect
    def wake_window_timer(self, action_stream):
        """喚醒視窗計時器 Effect
        
        當檢測到喚醒詞後，啟動30秒計時器。
        如果在30秒內沒有開始錄音或串流，則重置 FSM。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == wake_triggered.type),
            ops.flat_map(lambda action: 
                timer(30.0).pipe(  # 30秒超時
                    ops.map(lambda _: reset_fsm(action.payload["session_id"])),
                    ops.take_until(
                        action_stream.pipe(
                            ops.filter(lambda b: 
                                b.type in [start_recording.type, start_streaming.type, reset_fsm.type] and
                                b.payload.get("session_id") == action.payload["session_id"]
                            )
                        )
                    )
                )
            )
        )
    
    @create_effect
    def auto_transcription_trigger(self, action_stream):
        """自動轉譯觸發 Effect
        
        當錄音結束時，自動開始轉譯流程。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == end_recording.type),
            ops.delay(0.1),  # 小延遲確保狀態已更新
            ops.map(lambda a: begin_transcription(a.payload["session_id"]))
        )
    
    @create_effect
    def mock_transcription_result(self, action_stream):
        """模擬轉譯結果 Effect
        
        為了演示目的，模擬轉譯過程並返回結果。
        在實際系統中，這應該被真實的 ASR provider Effect 替代。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == begin_transcription.type),
            ops.delay(1.0),  # 模擬1秒轉譯時間
            ops.map(lambda a: transcription_done(
                a.payload["session_id"],
                f"模擬轉譯結果 (時間: {asyncio.get_event_loop().time():.1f})"
            ))
        )
    
    @create_effect(dispatch=False)
    def session_logging(self, action_stream):
        """Session 事件日誌 Effect
        
        記錄所有 Session 相關的重要事件。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type.startswith("[Session]")),
            ops.do_action(lambda action: self._log_action(action))
        )
    
    @create_effect(dispatch=False)
    def session_metrics(self, action_stream):
        """Session 指標收集 Effect
        
        收集 Session 相關的業務指標。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                wake_triggered.type,
                transcription_done.type,
                session_error.type
            ]),
            ops.do_action(lambda action: self._collect_metrics(action))
        )
    
    def _log_action(self, action):
        """記錄 Action 到日誌"""
        if self.logger:
            self.logger.info(f"Session Event: {action.type} | Payload: {action.payload}")
        else:
            print(f"Session Event: {action.type} | Session: {action.payload.get('session_id', 'N/A')}")
    
    def _collect_metrics(self, action):
        """收集業務指標"""
        if action.type == wake_triggered.type:
            # 記錄喚醒詞檢測指標
            confidence = action.payload.get("confidence", 0)
            trigger_type = action.payload.get("trigger", "unknown")
            if self.logger:
                self.logger.info(f"Wake word detected: {trigger_type} (confidence: {confidence})")
        
        elif action.type == transcription_done.type:
            # 記錄轉譯完成指標
            result_length = len(action.payload.get("result", ""))
            if self.logger:
                self.logger.info(f"Transcription completed: {result_length} characters")
        
        elif action.type == session_error.type:
            # 記錄錯誤指標
            error = action.payload.get("error", "unknown")
            if self.logger:
                self.logger.error(f"Session error: {error}")


class SessionTimerEffects:
    """Session 計時器相關的 Effects"""
    
    @create_effect
    def session_timeout(self, action_stream):
        """會話超時 Effect
        
        長時間未活動的會話將被自動重置。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [wake_triggered.type, start_recording.type]),
            ops.group_by(lambda a: a.payload["session_id"]),
            ops.flat_map(lambda group: group.pipe(
                ops.debounce(300.0),  # 5分鐘無活動
                ops.map(lambda a: reset_fsm(a.payload["session_id"]))
            ))
        )
    
    @create_effect
    def recording_timeout(self, action_stream):
        """錄音超時 Effect
        
        錄音時間過長時自動結束錄音。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [start_recording.type, start_streaming.type]),
            ops.flat_map(lambda action:
                timer(30.0).pipe(  # 30秒錄音超時
                    ops.map(lambda _: end_recording(
                        action.payload["session_id"],
                        "timeout",
                        30.0
                    )),
                    ops.take_until(
                        action_stream.pipe(
                            ops.filter(lambda b:
                                b.type in [end_recording.type, reset_fsm.type] and
                                b.payload.get("session_id") == action.payload["session_id"]
                            )
                        )
                    )
                )
            )
        )