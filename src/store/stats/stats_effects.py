"""
Stats 域的 Effects 實現
"""

import time
from pystorex import create_effect
from reactivex import timer, interval
from reactivex import operators as ops
from src.utils.logger import logger

from .stats_actions import (
    # 統計重置和初始化
    initialize_stats,
    
    # Session 統計
    session_created_stat,
    session_destroyed_stat,
    update_active_sessions_peak,
    
    # 喚醒詞統計
    wake_word_detected_stat,
    wake_word_false_positive_stat,
    
    # 錄音統計
    recording_completed_stat,
    recording_failed_stat,
    
    # 轉譯統計
    transcription_completed_stat,
    transcription_failed_stat,
    
    # 錯誤統計
    error_occurred_stat,
    
    # 性能統計
    update_response_time_stat,
    update_memory_usage_stat
)


class StatsEffects:
    """Stats 相關的 Effects"""
    
    def __init__(self, metrics_client=None):
        self.metrics_client = metrics_client
    
    @create_effect(dispatch=False)
    def stats_logging(self, action_stream):
        """統計事件日誌 Effect
        
        記錄所有統計相關的重要事件。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type.startswith("[Stats]")),
            ops.do_action(lambda action: self._log_stats_action(action))
        )
    
    @create_effect(dispatch=False)
    def performance_monitoring(self, action_stream):
        """性能監控 Effect
        
        監控系統性能指標並發送到外部監控系統。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                update_response_time_stat.type,
                update_memory_usage_stat.type,
                transcription_completed_stat.type,
                recording_completed_stat.type
            ]),
            ops.do_action(lambda action: self._send_performance_metrics(action))
        )
    
    @create_effect(dispatch=False)
    def quality_monitoring(self, action_stream):
        """品質監控 Effect
        
        監控系統品質指標，如成功率、準確率等。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                wake_word_detected_stat.type,
                wake_word_false_positive_stat.type,
                recording_failed_stat.type,
                transcription_failed_stat.type
            ]),
            ops.do_action(lambda action: self._monitor_quality_metrics(action))
        )
    
    @create_effect(dispatch=False)
    def error_alerting(self, action_stream):
        """錯誤告警 Effect
        
        監控錯誤事件並觸發告警。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type == error_occurred_stat.type),
            ops.do_action(lambda action: self._handle_error_alert(action))
        )
    
    @create_effect(dispatch=False)
    def session_lifecycle_tracking(self, action_stream):
        """會話生命週期追蹤 Effect
        
        追蹤會話的創建和銷毀，監控會話健康狀況。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                session_created_stat.type,
                session_destroyed_stat.type,
                update_active_sessions_peak.type
            ]),
            ops.do_action(lambda action: self._track_session_lifecycle(action))
        )
    
    @create_effect(dispatch=False)
    def wake_word_analysis(self, action_stream):
        """喚醒詞分析 Effect
        
        分析喚醒詞檢測的準確性和性能。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type in [
                wake_word_detected_stat.type,
                wake_word_false_positive_stat.type
            ]),
            ops.buffer_with_time(60.0),  # 每分鐘收集一次
            ops.filter(lambda buffer: len(buffer) > 0),
            ops.do_action(lambda actions: self._analyze_wake_word_performance(actions))
        )
    
    def _log_stats_action(self, action):
        """記錄統計 Action 到日誌"""
        if logger:
            logger.info(f"Stats Event: {action.type} | Payload: {action.payload}")
        else:
            print(f"Stats Event: {action.type} | Data: {action.payload}")
    
    def _send_performance_metrics(self, action):
        """發送性能指標到監控系統"""
        if not self.metrics_client:
            return
        
        try:
            if action.type == update_response_time_stat.type:
                self.metrics_client.gauge(
                    f"asr.performance.{action.payload['operation']}.response_time",
                    action.payload["duration"]
                )
            
            elif action.type == update_memory_usage_stat.type:
                self.metrics_client.gauge(
                    "asr.performance.memory_usage",
                    action.payload["usage"]
                )
            
            elif action.type == transcription_completed_stat.type:
                self.metrics_client.histogram(
                    "asr.transcription.duration",
                    action.payload["duration"]
                )
                self.metrics_client.histogram(
                    "asr.transcription.result_length",
                    action.payload["result_length"]
                )
            
            elif action.type == recording_completed_stat.type:
                self.metrics_client.histogram(
                    "asr.recording.duration",
                    action.payload["duration"]
                )
                
        except Exception as e:
            if logger:
                logger.error(f"Failed to send performance metrics: {e}")
    
    def _monitor_quality_metrics(self, action):
        """監控品質指標"""
        try:
            if action.type == wake_word_detected_stat.type:
                confidence = action.payload["confidence"]
                trigger_type = action.payload["trigger_type"]
                
                if self.metrics_client:
                    self.metrics_client.histogram("asr.wake_word.confidence", confidence)
                    self.metrics_client.increment(f"asr.wake_word.detected.{trigger_type}")
                
                # 低置信度告警
                if confidence < 0.7:
                    if logger:
                        logger.warning(
                            f"Low wake word confidence: {confidence:.2f} "
                            f"(session: {action.payload['session_id']})"
                        )
            
            elif action.type == wake_word_false_positive_stat.type:
                if self.metrics_client:
                    self.metrics_client.increment("asr.wake_word.false_positive")
                
                if logger:
                    logger.warning(
                        f"Wake word false positive detected "
                        f"(session: {action.payload['session_id']})"
                    )
            
            elif action.type in [recording_failed_stat.type, transcription_failed_stat.type]:
                operation = "recording" if action.type == recording_failed_stat.type else "transcription"
                
                if self.metrics_client:
                    self.metrics_client.increment(f"asr.{operation}.failed")
                
                if logger:
                    logger.warning(
                        f"{operation.capitalize()} failed: {action.payload['error']} "
                        f"(session: {action.payload['session_id']})"
                    )
                    
        except Exception as e:
            if logger:
                logger.error(f"Failed to monitor quality metrics: {e}")
    
    def _handle_error_alert(self, action):
        """處理錯誤告警"""
        try:
            error_type = action.payload["error_type"]
            error_message = action.payload["error_message"]
            session_id = action.payload["session_id"]
            
            if self.metrics_client:
                self.metrics_client.increment(f"asr.errors.{error_type}")
            
            # 根據錯誤類型決定告警級別
            alert_level = self._get_error_alert_level(error_type)
            
            if alert_level == "critical":
                if logger:
                    logger.critical(
                        f"Critical error in session {session_id}: "
                        f"{error_type} - {error_message}"
                    )
                # 這裡可以集成告警系統發送緊急通知
                
            elif alert_level == "warning":
                if logger:
                    logger.warning(
                        f"Warning in session {session_id}: "
                        f"{error_type} - {error_message}"
                    )
                    
        except Exception as e:
            if logger:
                logger.error(f"Failed to handle error alert: {e}")
    
    def _track_session_lifecycle(self, action):
        """追蹤會話生命週期"""
        try:
            if action.type == session_created_stat.type:
                if self.metrics_client:
                    self.metrics_client.increment("asr.sessions.created")
                
                if logger:
                    logger.info(f"Session created: {action.payload['session_id']}")
            
            elif action.type == session_destroyed_stat.type:
                if self.metrics_client:
                    self.metrics_client.increment("asr.sessions.destroyed")
                
                if logger:
                    logger.info(f"Session destroyed: {action.payload['session_id']}")
            
            elif action.type == update_active_sessions_peak.type:
                peak_count = action.payload["count"]
                
                if self.metrics_client:
                    self.metrics_client.gauge("asr.sessions.active_peak", peak_count)
                
                if logger:
                    logger.info(f"New active sessions peak: {peak_count}")
                    
        except Exception as e:
            if logger:
                logger.error(f"Failed to track session lifecycle: {e}")
    
    def _analyze_wake_word_performance(self, actions):
        """分析喚醒詞性能"""
        try:
            if not actions:
                return
            
            detected_count = len([a for a in actions if a.type == wake_word_detected_stat.type])
            false_positive_count = len([a for a in actions if a.type == wake_word_false_positive_stat.type])
            
            total_detections = detected_count + false_positive_count
            accuracy = detected_count / total_detections * 100 if total_detections > 0 else 0
            
            if self.metrics_client:
                self.metrics_client.gauge("asr.wake_word.accuracy_percent", accuracy)
                self.metrics_client.gauge("asr.wake_word.detections_per_minute", detected_count)
                self.metrics_client.gauge("asr.wake_word.false_positives_per_minute", false_positive_count)
            
            if logger:
                logger.info(
                    f"Wake word performance (last minute): "
                    f"Accuracy: {accuracy:.1f}%, "
                    f"Detections: {detected_count}, "
                    f"False positives: {false_positive_count}"
                )
                
        except Exception as e:
            if logger:
                logger.error(f"Failed to analyze wake word performance: {e}")
    
    def _get_error_alert_level(self, error_type: str) -> str:
        """根據錯誤類型獲取告警級別"""
        critical_errors = {
            "system_failure",
            "memory_overflow",
            "disk_full",
            "network_timeout"
        }
        
        if error_type in critical_errors:
            return "critical"
        else:
            return "warning"


class StatsReportingEffects:
    """統計報告相關的 Effects"""
    
    def __init__(self):
        pass
    
    @create_effect
    def periodic_stats_report(self, action_stream):
        """定期統計報告 Effect
        
        每小時生成一次統計報告。
        """
        return interval(3600.0).pipe(  # 每小時
            ops.map(lambda _: initialize_stats())  # 觸發統計初始化作為報告信號
        )
    
    @create_effect(dispatch=False)
    def stats_persistence(self, action_stream):
        """統計數據持久化 Effect
        
        定期保存統計數據到文件或資料庫。
        """
        return action_stream.pipe(
            ops.filter(lambda a: a.type.startswith("[Stats]")),
            ops.sample(300.0),  # 每5分鐘採樣一次
            ops.do_action(lambda action: self._persist_stats(action))
        )
    
    def _persist_stats(self, action):
        """持久化統計數據"""
        try:
            # 這裡可以實現將統計數據保存到文件或資料庫的邏輯
            timestamp = time.time()
            if logger:
                logger.debug(f"Persisting stats at {timestamp}: {action.type}")
        except Exception as e:
            if logger:
                logger.error(f"Failed to persist stats: {e}")