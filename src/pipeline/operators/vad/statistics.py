"""
VAD 統計收集和分析
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
from collections import deque

from src.utils.logger import logger


@dataclass
class VADFrame:
    """VAD 幀數據"""
    timestamp: float
    speech_probability: float
    is_speech: bool
    threshold: float
    duration: float = 0.032  # 預設 32ms 一幀


@dataclass 
class VADStatistics:
    """VAD 統計數據"""
    # 基本統計
    total_frames: int = 0
    speech_frames: int = 0
    silence_frames: int = 0
    
    # 時長統計
    total_duration: float = 0.0
    total_speech_duration: float = 0.0
    total_silence_duration: float = 0.0
    
    # 語音段落統計
    speech_segments: List[Tuple[float, float]] = field(default_factory=list)
    average_segment_duration: float = 0.0
    max_segment_duration: float = 0.0
    min_segment_duration: float = float('inf')
    
    # 準確率統計
    false_positives: int = 0  # 誤判為語音
    false_negatives: int = 0  # 誤判為靜音
    
    # 機率統計
    avg_speech_probability: float = 0.0
    speech_probability_std: float = 0.0
    
    # 延遲統計
    processing_times: List[float] = field(default_factory=list)
    avg_processing_time: float = 0.0
    max_processing_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'total_frames': self.total_frames,
            'speech_frames': self.speech_frames,
            'silence_frames': self.silence_frames,
            'speech_ratio': self.speech_frames / max(1, self.total_frames),
            'total_duration': self.total_duration,
            'total_speech_duration': self.total_speech_duration,
            'total_silence_duration': self.total_silence_duration,
            'num_speech_segments': len(self.speech_segments),
            'average_segment_duration': self.average_segment_duration,
            'max_segment_duration': self.max_segment_duration,
            'min_segment_duration': self.min_segment_duration if self.min_segment_duration != float('inf') else 0,
            'false_positives': self.false_positives,
            'false_negatives': self.false_negatives,
            'avg_speech_probability': self.avg_speech_probability,
            'speech_probability_std': self.speech_probability_std,
            'avg_processing_time_ms': self.avg_processing_time * 1000,
            'max_processing_time_ms': self.max_processing_time * 1000
        }


class VADStatisticsCollector:
    """VAD 統計收集器"""
    
    def __init__(self, window_size: int = 1000):
        """
        初始化統計收集器
        
        Args:
            window_size: 滑動窗口大小（幀數）
        """
        self.window_size = window_size
        self.frame_buffer = deque(maxlen=window_size)
        self.statistics = VADStatistics()
        
        # 當前語音段落
        self.current_segment_start: Optional[float] = None
        self.in_speech = False
        
        # 機率歷史
        self.probability_history = deque(maxlen=window_size)
        
        # 處理時間記錄
        self.last_process_time: Optional[float] = None
    
    def add_frame(self, frame: VADFrame):
        """
        添加一幀數據
        
        Args:
            frame: VAD 幀數據
        """
        # 添加到緩衝區
        self.frame_buffer.append(frame)
        self.probability_history.append(frame.speech_probability)
        
        # 更新基本統計
        self.statistics.total_frames += 1
        if frame.is_speech:
            self.statistics.speech_frames += 1
        else:
            self.statistics.silence_frames += 1
        
        # 更新時長統計
        self.statistics.total_duration += frame.duration
        if frame.is_speech:
            self.statistics.total_speech_duration += frame.duration
        else:
            self.statistics.total_silence_duration += frame.duration
        
        # 更新語音段落
        self._update_speech_segments(frame)
        
        # 更新機率統計
        self._update_probability_stats()
    
    def add_processing_time(self, processing_time: float):
        """
        添加處理時間記錄
        
        Args:
            processing_time: 處理時間（秒）
        """
        self.statistics.processing_times.append(processing_time)
        
        # 限制歷史記錄大小
        if len(self.statistics.processing_times) > self.window_size:
            self.statistics.processing_times = self.statistics.processing_times[-self.window_size:]
        
        # 更新統計
        self.statistics.avg_processing_time = np.mean(self.statistics.processing_times)
        self.statistics.max_processing_time = np.max(self.statistics.processing_times)
    
    def _update_speech_segments(self, frame: VADFrame):
        """更新語音段落統計"""
        if frame.is_speech and not self.in_speech:
            # 語音開始
            self.current_segment_start = frame.timestamp
            self.in_speech = True
            
        elif not frame.is_speech and self.in_speech:
            # 語音結束
            if self.current_segment_start is not None:
                segment_duration = frame.timestamp - self.current_segment_start
                self.statistics.speech_segments.append(
                    (self.current_segment_start, frame.timestamp)
                )
                
                # 更新段落時長統計
                durations = [end - start for start, end in self.statistics.speech_segments]
                self.statistics.average_segment_duration = np.mean(durations)
                self.statistics.max_segment_duration = max(durations)
                self.statistics.min_segment_duration = min(durations)
                
            self.in_speech = False
            self.current_segment_start = None
    
    def _update_probability_stats(self):
        """更新機率統計"""
        if self.probability_history:
            self.statistics.avg_speech_probability = np.mean(self.probability_history)
            self.statistics.speech_probability_std = np.std(self.probability_history)
    
    def mark_false_positive(self):
        """標記誤判為語音"""
        self.statistics.false_positives += 1
    
    def mark_false_negative(self):
        """標記誤判為靜音"""
        self.statistics.false_negatives += 1
    
    def get_recent_statistics(self, window_seconds: float = 10.0) -> Dict[str, Any]:
        """
        獲取最近時間窗口的統計
        
        Args:
            window_seconds: 時間窗口（秒）
            
        Returns:
            統計信息字典
        """
        if not self.frame_buffer:
            return {}
        
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # 過濾最近的幀
        recent_frames = [f for f in self.frame_buffer if f.timestamp >= cutoff_time]
        
        if not recent_frames:
            return {}
        
        # 計算統計
        speech_frames = sum(1 for f in recent_frames if f.is_speech)
        total_frames = len(recent_frames)
        
        return {
            'window_seconds': window_seconds,
            'total_frames': total_frames,
            'speech_frames': speech_frames,
            'silence_frames': total_frames - speech_frames,
            'speech_ratio': speech_frames / total_frames if total_frames > 0 else 0,
            'avg_probability': np.mean([f.speech_probability for f in recent_frames]),
            'std_probability': np.std([f.speech_probability for f in recent_frames])
        }
    
    def get_statistics(self) -> VADStatistics:
        """獲取完整統計信息"""
        return self.statistics
    
    def reset(self):
        """重置統計"""
        self.frame_buffer.clear()
        self.probability_history.clear()
        self.statistics = VADStatistics()
        self.current_segment_start = None
        self.in_speech = False
        logger.debug("VAD 統計已重置")
    
    def get_accuracy_metrics(self, 
                           ground_truth_speech_frames: Optional[int] = None,
                           ground_truth_silence_frames: Optional[int] = None) -> Dict[str, float]:
        """
        計算準確率指標
        
        Args:
            ground_truth_speech_frames: 實際語音幀數
            ground_truth_silence_frames: 實際靜音幀數
            
        Returns:
            準確率指標字典
        """
        metrics = {}
        
        if ground_truth_speech_frames is not None:
            # 召回率 (Recall): 正確檢測到的語音 / 實際語音
            recall = self.statistics.speech_frames / ground_truth_speech_frames
            metrics['recall'] = min(1.0, recall)  # 限制在 0-1 範圍
            
            # 精確率 (Precision): 正確檢測到的語音 / 檢測為語音的總數
            if self.statistics.speech_frames > 0:
                precision = (self.statistics.speech_frames - self.statistics.false_positives) / self.statistics.speech_frames
                metrics['precision'] = max(0.0, precision)
            else:
                metrics['precision'] = 0.0
        
        if ground_truth_silence_frames is not None:
            # 特異性 (Specificity): 正確檢測到的靜音 / 實際靜音
            specificity = self.statistics.silence_frames / ground_truth_silence_frames
            metrics['specificity'] = min(1.0, specificity)
        
        # F1 分數
        if 'precision' in metrics and 'recall' in metrics:
            if metrics['precision'] + metrics['recall'] > 0:
                f1_score = 2 * (metrics['precision'] * metrics['recall']) / (metrics['precision'] + metrics['recall'])
                metrics['f1_score'] = f1_score
            else:
                metrics['f1_score'] = 0.0
        
        # 總體準確率
        if ground_truth_speech_frames is not None and ground_truth_silence_frames is not None:
            total_ground_truth = ground_truth_speech_frames + ground_truth_silence_frames
            correct_predictions = (
                min(self.statistics.speech_frames, ground_truth_speech_frames) +
                min(self.statistics.silence_frames, ground_truth_silence_frames)
            )
            metrics['accuracy'] = correct_predictions / total_ground_truth
        
        return metrics