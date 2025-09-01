#!/usr/bin/env python3
"""
麥克風 Effects 流程完整測試 (含視覺化 Dashboard)

測試完整的 SessionEffects 流程搭配真實麥克風輸入
- 麥克風擷取音訊
- 完整的音訊處理管線
- PyStoreX 狀態管理
- FSM 狀態轉換
- 所有服務整合測試
- 即時視覺化 Dashboard (matplotlib)
"""

import time
import signal
import sys
from typing import Optional
import numpy as np
import uuid6
import threading
from collections import deque

# Matplotlib 設定
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
import matplotlib.patches as patches
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
plt.style.use('dark_background')

# PyStoreX and Store setup
from src.store.main_store import main_store
from src.store.sessions import sessions_action as actions

# Effects integration  
from src.store.sessions.sessions_effect import SessionEffects

# Microphone service
from src.service.microphone_capture.microphone_capture import microphone_capture

# VAD and Wakeword services
from src.service.vad.silero_vad import silero_vad
from src.service.wakeword.openwakeword import openwakeword
from src.core.audio_queue_manager import audio_queue
from src.interface.vad import VADState, VADResult
from src.interface.wake import WakewordDetection

# Configuration and logging
from src.config.manager import ConfigManager
from src.utils.logger import logger
from src.interface.strategy import Strategy


class MicrophoneEffectsFlowTest:
    """完整的麥克風到Effects流程測試器 (含視覺化)"""
    
    def __init__(self, enable_dashboard=True):
        self.session_id: Optional[str] = None
        self.is_running = False
        self.config = ConfigManager()
        self.effects = SessionEffects()
        self.enable_dashboard = enable_dashboard
        
        # 初始化基本屬性
        self.window_sec = 15.0  # 預設視窗大小
        self.start_time = None
        
        # VAD 和 Wakeword 狀態
        self.current_vad_state = VADState.SILENCE
        self.current_vad_probability = 0.0
        self.wakeword_detections = []
        self.speech_regions = []
        self.speech_start_time = None
        
        # FSM 和錄音狀態
        self.current_fsm_state = "IDLE"
        self.recording_start_time = None
        self.is_recording = False
        
        # Dashboard 相關
        if self.enable_dashboard:
            self._init_dashboard()
            # 確保新增的文字元件被初始化
            if not hasattr(self, 'volume_text'):
                self.volume_text = None
            if not hasattr(self, 'wakeword_latest_text'):
                self.wakeword_latest_text = None
            if not hasattr(self, 'vad_state_text'):
                self.vad_state_text = None
            if not hasattr(self, 'fsm_state_text'):
                self.fsm_state_text = None
            if not hasattr(self, 'recording_duration_text'):
                self.recording_duration_text = None
        else:
            # 非 Dashboard 模式也需要初始化這些屬性
            self.wakeword_count = 0
            self.last_wakeword_confidence = 0.0
            self.last_vad_probability = 0.0
        
        # 設定信號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _init_dashboard(self):
        """初始化視覺化 Dashboard"""
        # 創建圖形窗口
        self.fig = plt.figure(figsize=(16, 10), facecolor='#1a1a1a')
        self.fig.suptitle('🎙️ ASRHub Effects 流程監控 Dashboard', fontsize=18, color='white', fontweight='bold')
        
        # 使用 GridSpec 建立布局 - 上半部完整聲波圖，下半部左右分割
        gs = GridSpec(2, 2, height_ratios=[1, 1], width_ratios=[1, 1], 
                     hspace=0.3, wspace=0.25)
        
        # 上半部：麥克風聲波圖（橫跨整個寬度）
        self.ax_waveform = self.fig.add_subplot(gs[0, :])
        self._setup_waveform_plot()
        
        # 下左：Wakeword 檢測
        self.ax_wakeword = self.fig.add_subplot(gs[1, 0])
        self._setup_wakeword_plot()
        
        # 下右：VAD 檢測
        self.ax_vad = self.fig.add_subplot(gs[1, 1])
        self._setup_vad_plot()
        
        # 數據緩衝區
        self.window_sec = 15.0  # 顯示最近15秒的數據
        self.sample_rate = 16000
        self.chunk_size = 1024
        
        # 計算緩衝區大小
        points_per_sec = self.sample_rate / self.chunk_size  # 約 15.625
        buffer_size = int(self.window_sec * points_per_sec * 1.2)  # 預留20%餘裕
        
        # 波形緩衝（儲存原始音訊）
        self.waveform_buffer = np.zeros(self.chunk_size)
        
        # Wakeword 緩衝
        self.wakeword_confidence_buffer = deque(maxlen=buffer_size)
        self.wakeword_time_buffer = deque(maxlen=buffer_size)
        self.wakeword_detection_events = []  # 儲存檢測事件
        
        # VAD 緩衝
        self.vad_probability_buffer = deque(maxlen=buffer_size)
        self.vad_time_buffer = deque(maxlen=buffer_size)
        
        # 時間追蹤
        self.start_time = time.time()
        
        # 統計數據
        self.wakeword_count = 0
        self.last_wakeword_confidence = 0.0
        self.last_vad_probability = 0.0
        
        # 平滑參數
        self.smoothing_window = 3  # 移動平均窗口
        self.interpolation_rate = 0.3  # 插值速率
        
        # 自動縮放參數
        self.auto_scale = True
        self.y_margin = 1.2
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    
    def _setup_waveform_plot(self):
        """設定聲波圖（上半部）"""
        self.ax_waveform.set_title('📊 即時麥克風聲波', color='white', fontsize=14, fontweight='bold')
        self.ax_waveform.set_ylabel('振幅', fontsize=11)
        self.ax_waveform.set_xlabel('樣本點', fontsize=11)
        self.ax_waveform.set_ylim(-5000, 5000)
        self.ax_waveform.grid(True, alpha=0.3, color='gray')
        self.ax_waveform.set_facecolor('#2a2a2a')
        
        # 波形線條和填充
        self.line_waveform, = self.ax_waveform.plot([], [], 'cyan', linewidth=0.8, alpha=0.9)
        self.fill_waveform = None
        
        # 狀態文字（顯示在左上角）
        self.status_text = self.ax_waveform.text(
            0.02, 0.98, '🔄 系統準備就緒',
            transform=self.ax_waveform.transAxes,
            fontsize=11, va='top', color='white',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#333333', alpha=0.8)
        )
        
        # FSM 狀態文字（顯示在中上方）
        self.fsm_state_text = self.ax_waveform.text(
            0.5, 0.98, 'FSM: IDLE',
            transform=self.ax_waveform.transAxes,
            fontsize=11, va='top', ha='center', color='yellow',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#4a4a4a', alpha=0.8)
        )
        
        # 音量指示器（顯示在右上角）
        self.volume_text = self.ax_waveform.text(
            0.98, 0.98, '音量: 0.00',
            transform=self.ax_waveform.transAxes,
            fontsize=11, va='top', ha='right', color='white',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#444444', alpha=0.8)
        )
        
        # 錄音時長指示器（顯示在中下方）
        self.recording_duration_text = self.ax_waveform.text(
            0.5, 0.02, '',
            transform=self.ax_waveform.transAxes,
            fontsize=11, va='bottom', ha='center', color='red',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#333333', alpha=0.8)
        )
    
    def _setup_wakeword_plot(self):
        """設定 Wakeword 檢測圖（下左）"""
        self.ax_wakeword.set_title('🎯 Wakeword 喚醒詞檢測', color='white', fontsize=13, fontweight='bold')
        self.ax_wakeword.set_xlabel('時間 (秒)', fontsize=11)
        self.ax_wakeword.set_ylabel('檢測信心度', fontsize=11)
        self.ax_wakeword.set_ylim(0, 1.1)
        self.ax_wakeword.set_xlim(0, self.window_sec)
        
        # 閾值線
        self.ax_wakeword.axhline(y=0.3, color='yellow', linestyle='--', alpha=0.6, 
                                 label='檢測閾值 (0.3)', linewidth=1.5)
        self.ax_wakeword.grid(True, alpha=0.3, color='gray')
        self.ax_wakeword.set_facecolor('#2a2a2a')
        
        # 信心度曲線
        self.line_wakeword, = self.ax_wakeword.plot([], [], 'lime', linewidth=1.2, 
                                                    label='即時信心度', alpha=0.9)
        
        # 圖例
        self.ax_wakeword.legend(loc='upper right', fontsize=9, framealpha=0.7)
        
        # 統計文字（顯示在左下角）
        self.wakeword_stats_text = self.ax_wakeword.text(
            0.02, 0.02, '檢測次數: 0',
            transform=self.ax_wakeword.transAxes,
            fontsize=10, va='bottom', color='white',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#333333', alpha=0.8)
        )
        
        # 最新檢測文字（顯示在右下角）
        self.wakeword_latest_text = self.ax_wakeword.text(
            0.98, 0.02, '等待檢測...',
            transform=self.ax_wakeword.transAxes,
            fontsize=10, va='bottom', ha='right', color='#aaaaaa',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#333333', alpha=0.8)
        )
    
    def _setup_vad_plot(self):
        """設定 VAD 檢測圖（下右）"""
        self.ax_vad.set_title('🔊 VAD 語音活動檢測', color='white', fontsize=13, fontweight='bold')
        self.ax_vad.set_xlabel('時間 (秒)', fontsize=11)
        self.ax_vad.set_ylabel('語音概率', fontsize=11)
        self.ax_vad.set_ylim(0, 1.1)
        self.ax_vad.set_xlim(0, self.window_sec)
        
        # 閾值線
        self.ax_vad.axhline(y=0.5, color='yellow', linestyle='--', alpha=0.6, 
                           label='語音閾值 (0.5)', linewidth=1.5)
        self.ax_vad.grid(True, alpha=0.3, color='gray')
        self.ax_vad.set_facecolor('#2a2a2a')
        
        # VAD 概率曲線
        self.line_vad, = self.ax_vad.plot([], [], 'orange', linewidth=1.2, 
                                          label='VAD 概率', alpha=0.9)
        
        # 圖例
        self.ax_vad.legend(loc='upper right', fontsize=9, framealpha=0.7)
        
        # 統計文字（顯示在左下角）
        self.vad_stats_text = self.ax_vad.text(
            0.02, 0.02, '語音段: 0',
            transform=self.ax_vad.transAxes,
            fontsize=10, va='bottom', color='white',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#333333', alpha=0.8)
        )
        
        # 狀態文字（顯示在右下角）
        self.vad_state_text = self.ax_vad.text(
            0.98, 0.02, '🔇 靜音',
            transform=self.ax_vad.transAxes,
            fontsize=10, va='bottom', ha='right', color='#aaaaaa',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#333333', alpha=0.8)
        )
    
    def _signal_handler(self, signum, frame):
        """優雅地停止測試"""
        logger.info("🛑 接收到停止信號，正在優雅關閉...")
        self.stop_test()
    
    def on_wakeword_detected(self, detection: WakewordDetection):
        """Wakeword 檢測回調"""
        if not self.start_time:
            return
            
        current_time = time.time() - self.start_time
        self.wakeword_count += 1
        
        logger.info(f"🎯 檢測到喚醒詞: {detection.keyword} (信心度: {detection.confidence:.3f})")
        
        self.wakeword_detections.append({
            'time': current_time,
            'keyword': detection.keyword,
            'confidence': detection.confidence
        })
    
    def on_vad_change(self, result: VADResult):
        """VAD 狀態變化回調"""
        if not self.start_time:
            return
            
        current_time = time.time() - self.start_time
        
        self.current_vad_state = result.state
        self.current_vad_probability = result.probability
        
        if result.state == VADState.SPEECH:
            if self.speech_start_time is None:
                self.speech_start_time = current_time
                logger.info(f"🔊 檢測到語音開始 @ {current_time:.2f}s")
        elif result.state == VADState.SILENCE:
            if self.speech_start_time is not None:
                duration = current_time - self.speech_start_time
                self.speech_regions.append((self.speech_start_time, current_time))
                logger.info(f"🔇 檢測到語音結束 (持續 {duration:.2f}s)")
                self.speech_start_time = None
        
    def _audio_callback(self, audio_data: np.ndarray, sample_rate: int):
        """麥克風音訊回調函數 - 將音訊送入Effects處理"""
        if not self.session_id or not self.is_running:
            return
            
        try:
            from src.interface.audio import AudioChunk
            
            # 更新波形緩衝（用於 Dashboard）
            if self.enable_dashboard:
                self.waveform_buffer = audio_data
                
                # 更新時間和緩衝
                current_time = time.time() - self.start_time
                
                # 更新 Wakeword 信心度（模擬衰減）
                if len(self.wakeword_detections) > 0:
                    last_detection = self.wakeword_detections[-1]
                    if current_time - last_detection['time'] < 1.0:
                        decay = np.exp(-(current_time - last_detection['time']) * 3)
                        confidence = last_detection['confidence'] * decay
                    else:
                        confidence = 0
                else:
                    confidence = 0
                
                self.wakeword_confidence_buffer.append(confidence)
                self.wakeword_time_buffer.append(current_time)
                self.last_wakeword_confidence = confidence
                
                # 更新 VAD 概率
                self.vad_probability_buffer.append(self.current_vad_probability)
                self.vad_time_buffer.append(current_time)
                self.last_vad_probability = self.current_vad_probability
            
            # 創建 AudioChunk 對象，包含音訊規格
            audio_chunk = AudioChunk(
                data=audio_data.tobytes(),  # 轉換為 bytes
                sample_rate=sample_rate,     # 傳入採樣率
                channels=1,                  # 單聲道
                timestamp=None               # 會自動設定時間戳
            )
            
            # 使用正確的 action creator (PyStoreX 格式)
            action = actions.receive_audio_chunk(
                self.session_id,
                audio_chunk  # 傳送 AudioChunk 對象
            )
            
            # 透過 PyStoreX 分發事件
            main_store.dispatch(action)
            
        except Exception as e:
            logger.error(f"❌ 音訊回調處理錯誤: {e}")
    
    def setup_session(self):
        """建立測試 session"""
        logger.info(f"🎯 準備建立測試 session")
        
        # 創建 session (使用正確的 action creator)
        # 注意：create_session 只接受 strategy 參數，session_id 會在 reducer 中自動生成
        create_action = actions.create_session(Strategy.NON_STREAMING)
        main_store.dispatch(create_action)
        
        # 從 store 中獲取新創建的 session
        # 等待一下讓 reducer 處理完成
        time.sleep(0.1)
        
        # 獲取最新創建的 session
        state = main_store.state
        
        # sessions 在 state['sessions']['sessions'] 裡面
        sessions_state = state.get('sessions', {})
        sessions_map = sessions_state.get('sessions', {})
        
        # 獲取所有 session_ids
        if sessions_map:
            # 獲取最新創建的 session (最後一個 key)
            session_ids = list(sessions_map.keys())
            if session_ids:
                self.session_id = session_ids[-1]  # 使用最新的
                logger.info(f"✅ 使用新創建的 session: {self.session_id}")
                
                # 確保使用相同的 session_id
                logger.info(f"📍 Session ID 確認: {self.session_id}")
            else:
                # 如果沒有 session，手動生成一個
                self.session_id = str(uuid6.uuid7())
                logger.warning(f"⚠️ 無法從 store 獲取 session_id，使用自生成的: {self.session_id}")
        else:
            # 如果沒有 session，手動生成一個
            self.session_id = str(uuid6.uuid7())
            logger.warning(f"⚠️ 無法從 store 獲取 session_id，使用自生成的: {self.session_id}")
        
        # 初始化 VAD 和 Wakeword 服務
        if not silero_vad.is_initialized():
            silero_vad._ensure_initialized()
        if not openwakeword.is_initialized():
            openwakeword.initialize()
        
        # 開始監聽服務
        logger.info(f"🔍 開始 VAD 監聽，session_id: {self.session_id}")
        vad_success = silero_vad.start_listening(
            session_id=self.session_id,
            callback=self.on_vad_change
        )
        logger.info(f"✅ VAD 監聽狀態: {vad_success}")
        
        logger.info(f"🔍 開始 Wakeword 監聽，session_id: {self.session_id}")
        wakeword_success = openwakeword.start_listening(
            session_id=self.session_id,
            callback=self.on_wakeword_detected
        )
        logger.info(f"✅ Wakeword 監聽狀態: {wakeword_success}")
        
        # 開始聆聽
        listen_action = actions.start_listen(
            self.session_id,
            16000,  # sample_rate
            1,      # channels
            "int16" # format
        )
        main_store.dispatch(listen_action)
        
        # 讓 Effects 有時間初始化
        time.sleep(0.5)
        
    def setup_microphone(self):
        """設定麥克風參數"""
        # 設定音訊參數（與session配置一致）
        success = microphone_capture.set_parameters(
            sample_rate=16000,
            channels=1,
            chunk_size=1024
        )
        
        if not success:
            raise RuntimeError("無法設定麥克風參數")
        
        # 顯示可用裝置
        devices = microphone_capture.get_devices()
        logger.info("🎤 可用音訊裝置:")
        for device in devices:
            logger.info(f"  [{device['index']}] {device['name']} "
                       f"({device['channels']} ch, {device['sample_rate']} Hz)")
        
        # 使用預設裝置或讓用戶選擇
        if devices:
            default_device = devices[0]['index']
            microphone_capture.set_device(default_device)
            logger.info(f"✅ 使用音訊裝置: {devices[0]['name']}")
    
    def start_test(self):
        """啟動完整測試流程"""
        try:
            logger.info("🚀 啟動麥克風Effects流程測試")
            logger.info("=" * 60)
            
            # 初始化時間
            self.start_time = time.time()
            
            # 1. 建立session
            self.setup_session()
            
            # 2. 設定麥克風
            self.setup_microphone()
            
            # 3. 開始音訊擷取
            logger.info("🎙️ 開始麥克風擷取...")
            success = microphone_capture.start_capture(callback=self._audio_callback)
            
            if not success:
                raise RuntimeError("無法啟動麥克風擷取")
            
            self.is_running = True
            
            logger.info("🎯 測試進行中...")
            logger.info("📝 監控以下項目:")
            logger.info("   • 麥克風音訊輸入")
            logger.info("   • SessionEffects 處理")
            logger.info("   • 音訊轉換和增強")
            logger.info("   • VAD 語音活動偵測")
            logger.info("   • DeepFilterNet 降噪")
            logger.info("   • FSM 狀態轉換")
            logger.info("   • Provider Pool 管理")
            logger.info("")
            logger.info("💡 對著麥克風說話來觸發處理流程")
            logger.info("⏹️  按 Ctrl+C 停止測試")
            logger.info("=" * 60)
            
            # 4. 主測試迴圈
            self.run_test_loop()
            
        except Exception as e:
            logger.error(f"❌ 測試啟動失敗: {e}")
            self.stop_test()
            raise
    
    def update_plot(self, frame):
        """更新 Dashboard 圖表"""
        if not self.is_running:
            return []
        
        try:
            current_time = time.time() - self.start_time
            
            # ==================== 更新波形圖 ====================
            x1 = np.arange(len(self.waveform_buffer))
            self.line_waveform.set_data(x1, self.waveform_buffer)
            self.ax_waveform.set_xlim(0, len(self.waveform_buffer))
            
            # 移除舊的填充
            if self.fill_waveform:
                self.fill_waveform.remove()
                self.fill_waveform = None
            
            # 添加新的填充效果
            if len(self.waveform_buffer) > 0:
                self.fill_waveform = self.ax_waveform.fill_between(
                    x1, 0, self.waveform_buffer,
                    color='cyan', alpha=0.3
                )
                
                # 自動調整 Y 軸範圍
                if self.auto_scale:
                    max_val = np.max(np.abs(self.waveform_buffer))
                    if max_val > 0:
                        y_limit = max_val * self.y_margin
                        current_ylim = self.ax_waveform.get_ylim()
                        if abs(current_ylim[1] - y_limit) > y_limit * 0.2:
                            self.ax_waveform.set_ylim(-y_limit, y_limit)
                
                # 計算音量
                rms = np.sqrt(np.mean(self.waveform_buffer.astype(float) ** 2))
                volume_normalized = min(1.0, rms / 10000)
                self.volume_text.set_text(f'音量: {volume_normalized:.2f}')
                
                # 根據音量改變顏色
                if volume_normalized > 0.7:
                    self.volume_text.set_color('red')
                elif volume_normalized > 0.4:
                    self.volume_text.set_color('yellow')
                else:
                    self.volume_text.set_color('white')
            
            # 更新狀態文字
            if self.current_vad_state == VADState.SPEECH:
                status_icon = '🔊'
                status_color = '#66ff66'
                status_msg = '語音活動中'
            else:
                status_icon = '🎤'
                status_color = '#ffffff'
                status_msg = '監聽中'
            
            self.status_text.set_text(f'{status_icon} {status_msg} | 運行時間: {current_time:.1f}秒')
            
            # 更新 FSM 狀態（從 store 獲取）
            try:
                current_state = main_store.state
                sessions_state = current_state.get('sessions', {})
                sessions_map = sessions_state.get('sessions', {})
                
                if self.session_id and self.session_id in sessions_map:
                    session = sessions_map[self.session_id]
                    fsm_state = session.get('status', 'UNKNOWN')
                    self.current_fsm_state = fsm_state
                    
                    # 根據狀態設定顏色
                    state_colors = {
                        'IDLE': 'gray',
                        'LISTENING': 'cyan',
                        'WAKEWORD_DETECTED': 'lime',
                        'RECORDING': 'red',
                        'PROCESSING': 'yellow',
                        'STREAMING': 'orange',
                        'COMPLETE': 'green',
                        'ERROR': 'red'
                    }
                    color = state_colors.get(fsm_state, 'white')
                    
                    self.fsm_state_text.set_text(f'FSM: {fsm_state}')
                    self.fsm_state_text.set_color(color)
                    
                    # 檢查是否在錄音
                    if fsm_state == 'RECORDING':
                        if not self.is_recording:
                            self.is_recording = True
                            self.recording_start_time = current_time
                    else:
                        if self.is_recording:
                            self.is_recording = False
                            self.recording_start_time = None
                    
                    # 更新錄音時長
                    if self.is_recording and self.recording_start_time is not None:
                        recording_duration = current_time - self.recording_start_time
                        self.recording_duration_text.set_text(
                            f'🔴 錄音中: {recording_duration:.1f}秒'
                        )
                        self.recording_duration_text.set_visible(True)
                    else:
                        self.recording_duration_text.set_visible(False)
                        
            except Exception as e:
                logger.debug(f"無法獲取 FSM 狀態: {e}")
            
            # ==================== 更新 Wakeword 信心度曲線 ====================
            if len(self.wakeword_confidence_buffer) > 0:
                time_array = np.array(list(self.wakeword_time_buffer))
                conf_array = np.array(list(self.wakeword_confidence_buffer))
                
                # 應用平滑
                if self.smoothing_window > 1 and len(conf_array) > self.smoothing_window:
                    kernel = np.ones(self.smoothing_window) / self.smoothing_window
                    conf_smoothed = np.convolve(conf_array, kernel, mode='same')
                    conf_array = conf_smoothed
                
                self.line_wakeword.set_data(time_array, conf_array)
                self._update_x_axis(self.ax_wakeword, time_array)
                
                # 添加填充效果
                for patch in self.ax_wakeword.collections[:]:
                    patch.remove()
                
                if len(time_array) > 1:
                    # 高信心度區域（>0.3）用暖色填充
                    high_conf_mask = conf_array > 0.3
                    if np.any(high_conf_mask):
                        self.ax_wakeword.fill_between(
                            time_array, 0.3, conf_array,
                            where=high_conf_mask,
                            color='green', alpha=0.3,
                            interpolate=True
                        )
                    
                    # 低信心度區域用冷色填充
                    low_conf_mask = conf_array <= 0.3
                    if np.any(low_conf_mask):
                        self.ax_wakeword.fill_between(
                            time_array, 0, conf_array,
                            where=low_conf_mask,
                            color='blue', alpha=0.2,
                            interpolate=True
                        )
                
                # 繪製檢測事件標記
                for rect in self.ax_wakeword.patches[:]:
                    if isinstance(rect, patches.Rectangle):
                        rect.remove()
                
                # 獲取視窗範圍
                x_lim = self.ax_wakeword.get_xlim()
                for detection in self.wakeword_detections[-10:]:  # 只顯示最近10個檢測
                    if x_lim[0] <= detection['time'] <= x_lim[1]:
                        # 在檢測時間點畫一個綠色矩形
                        rect = patches.Rectangle(
                            (detection['time'] - 0.1, 0), 0.2, detection['confidence'],
                            linewidth=2, facecolor='lime', edgecolor='green', alpha=0.7
                        )
                        self.ax_wakeword.add_patch(rect)
                
                # 更新統計
                self.wakeword_stats_text.set_text(f'檢測次數: {self.wakeword_count}')
                
                # 更新最新檢測
                if self.wakeword_detections:
                    latest = self.wakeword_detections[-1]
                    time_ago = current_time - latest['time']
                    self.wakeword_latest_text.set_text(
                        f"✅ {latest['keyword']} ({time_ago:.1f}秒前)"
                    )
                    self.wakeword_latest_text.set_color('#66ff66')
                else:
                    self.wakeword_latest_text.set_text('等待檢測...')
                    self.wakeword_latest_text.set_color('#aaaaaa')
            
            # ==================== 更新 VAD 概率曲線 ====================
            if len(self.vad_probability_buffer) > 0:
                time_array = np.array(list(self.vad_time_buffer))
                prob_array = np.array(list(self.vad_probability_buffer))
                
                # 應用平滑
                if self.smoothing_window > 1 and len(prob_array) > self.smoothing_window:
                    kernel = np.ones(self.smoothing_window) / self.smoothing_window
                    prob_smoothed = np.convolve(prob_array, kernel, mode='same')
                    prob_array = prob_smoothed
                
                self.line_vad.set_data(time_array, prob_array)
                self._update_x_axis(self.ax_vad, time_array)
                
                # 添加填充效果
                for patch in self.ax_vad.collections[:]:
                    patch.remove()
                
                if len(time_array) > 1:
                    # 高概率區域（語音）用暖色填充
                    high_prob_mask = prob_array > 0.5
                    if np.any(high_prob_mask):
                        self.ax_vad.fill_between(
                            time_array, 0.5, prob_array,
                            where=high_prob_mask,
                            color='orange', alpha=0.3,
                            interpolate=True
                        )
                    
                    # 低概率區域（靜音）用冷色填充
                    low_prob_mask = prob_array <= 0.5
                    if np.any(low_prob_mask):
                        self.ax_vad.fill_between(
                            time_array, 0, prob_array,
                            where=low_prob_mask,
                            color='blue', alpha=0.2,
                            interpolate=True
                        )
                
                # 繪製語音區域
                for rect in self.ax_vad.patches[:]:
                    if isinstance(rect, patches.Rectangle):
                        rect.remove()
                
                # 獲取視窗範圍
                x_lim = self.ax_vad.get_xlim()
                for start, end in self.speech_regions:
                    if end >= x_lim[0] and start <= x_lim[1]:
                        visible_start = max(start, x_lim[0])
                        visible_end = min(end, x_lim[1])
                        rect = patches.Rectangle(
                            (visible_start, 0), visible_end - visible_start, 1.1,
                            linewidth=0, facecolor='red', alpha=0.15
                        )
                        self.ax_vad.add_patch(rect)
                
                # 如果當前正在說話，顯示正在進行的區域
                if self.speech_start_time is not None:
                    if self.speech_start_time <= x_lim[1]:
                        visible_start = max(self.speech_start_time, x_lim[0])
                        visible_end = min(current_time, x_lim[1])
                        rect = patches.Rectangle(
                            (visible_start, 0), visible_end - visible_start, 1.1,
                            linewidth=1, facecolor='yellow', alpha=0.2, linestyle='--'
                        )
                        self.ax_vad.add_patch(rect)
                
                # 更新統計
                speech_count = len(self.speech_regions)
                total_speech_time = sum(end - start for start, end in self.speech_regions)
                if self.speech_start_time is not None:
                    total_speech_time += (current_time - self.speech_start_time)
                
                self.vad_stats_text.set_text(
                    f'語音段: {speech_count} | 總時長: {total_speech_time:.1f}秒'
                )
                
                # 更新狀態
                if self.current_vad_state == VADState.SPEECH:
                    self.vad_state_text.set_text('🔊 說話中')
                    self.vad_state_text.set_color('#ff6666')
                else:
                    self.vad_state_text.set_text('🔇 靜音')
                    self.vad_state_text.set_color('#aaaaaa')
            
        except Exception as e:
            logger.error(f"更新圖表錯誤: {e}")
        
        # 返回所有需要更新的元素
        artists = [self.line_waveform, self.line_wakeword, self.line_vad,
                  self.status_text, self.volume_text, self.fsm_state_text,
                  self.recording_duration_text,
                  self.wakeword_stats_text, self.wakeword_latest_text,
                  self.vad_stats_text, self.vad_state_text]
        
        if self.fill_waveform:
            artists.append(self.fill_waveform)
        
        return artists
    
    def _update_x_axis(self, ax, time_array):
        """更新 X 軸範圍"""
        if len(time_array) > 0:
            data_max = max(time_array)
            if data_max <= self.window_sec:
                x_min = 0
                x_max = self.window_sec
            else:
                x_max = data_max + 0.5
                x_min = max(0, data_max - self.window_sec)
            ax.set_xlim(x_min, x_max)
    
    def run_test_loop(self):
        """主測試迴圈"""
        try:
            if self.enable_dashboard:
                # 使用 matplotlib 動畫
                ani = animation.FuncAnimation(
                    self.fig, self.update_plot,
                    interval=50,  # 50ms 更新一次
                    blit=True,
                    cache_frame_data=False
                )
                plt.show()  # 這會阻塞直到窗口關閉
            else:
                # 原本的文字模式
                while self.is_running:
                    # 顯示當前狀態
                    current_state = main_store.state
                    sessions_state = current_state.get('sessions', {})
                    sessions_map = sessions_state.get('sessions', {})
                    
                    if self.session_id and self.session_id in sessions_map:
                        session_state = sessions_map[self.session_id]
                        status = session_state.get('status', 'unknown')
                        
                        # 每5秒顯示一次狀態
                        if int(time.time()) % 5 == 0:
                            logger.info(f"📊 Session {self.session_id[:8]}... 狀態: {status}")
                    
                    time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("🛑 收到中斷信號")
        finally:
            self.stop_test()
    
    def stop_test(self):
        """停止測試並清理資源"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        logger.info("🧹 清理測試資源...")
        
        # 1. 停止麥克風擷取
        if microphone_capture.is_capturing():
            microphone_capture.stop_capture()
            logger.info("✅ 麥克風擷取已停止")
        
        # 2. 停止服務
        if self.session_id:
            silero_vad.stop_listening(self.session_id)
            openwakeword.stop_listening(self.session_id)
            logger.info("✅ VAD 和 Wakeword 服務已停止")
        
        # 3. 停止 session（如果存在）
        if self.session_id:
            try:
                # 停止錄音 (使用正確的 action)
                stop_record_action = actions.record_stopped(self.session_id)
                main_store.dispatch(stop_record_action)
                
                # 刪除 session
                delete_action = actions.delete_session(self.session_id)
                main_store.dispatch(delete_action)
                
                logger.info(f"✅ Session {self.session_id[:8]}... 已清理")
                
            except Exception as e:
                logger.warning(f"⚠️ Session 清理時出現問題: {e}")
        
        # 4. 關閉圖形窗口
        if self.enable_dashboard:
            plt.close('all')
        
        logger.info("🏁 測試完成")


def show_usage():
    """顯示使用說明"""
    print("""
🎙️ 麥克風 Effects 流程測試器 (含視覺化 Dashboard)
    
此測試程式會：
1. 建立一個測試 session 並啟動 FSM
2. 開始麥克風音訊擷取
3. 將音訊透過 SessionEffects 進行完整處理
4. 監控整個處理管線的狀態
5. 顯示即時視覺化 Dashboard (可選)

使用方法：
    python test_microphone_effects_flow.py         # 含 Dashboard
    python test_microphone_effects_flow.py --no-ui # 無 Dashboard

測試期間：
• 對著麥克風說話來觸發音訊處理
• Dashboard 會顯示波形、VAD 和 Wakeword 狀態
• 觀察日誌輸出來監控處理流程  
• 按 Ctrl+C 或關閉視窗停止測試

需要的配置：
• config/config.yaml 中的麥克風設定
• 確保安裝了 sounddevice 或 pyaudio
• 確保安裝了 matplotlib (用於 Dashboard)
• 確保麥克風裝置可用
    """)


def main():
    """主程式入口"""
    try:
        # 檢查是否要顯示 Dashboard
        enable_dashboard = '--no-ui' not in sys.argv
        
        show_usage()
        
        # 建立測試器
        tester = MicrophoneEffectsFlowTest(enable_dashboard=enable_dashboard)
        
        if enable_dashboard:
            logger.info("🎨 Dashboard 模式啟動")
        else:
            logger.info("📝 純文字模式啟動")
        
        # 啟動測試
        tester.start_test()
        
    except KeyboardInterrupt:
        logger.info("🛑 程式被中斷")
    except Exception as e:
        logger.error(f"❌ 程式執行錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()