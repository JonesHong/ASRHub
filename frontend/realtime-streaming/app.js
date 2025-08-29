/**
 * Real-time Streaming App Main Entry Point
 * 實時串流應用程式主要入口點
 * 整合所有模組並建立完整的音訊串流pipeline
 */

class RealTimeStreamingApp {
    constructor() {
        // 核心管理器
        this.protocolAdapter = null;
        this.audioStreamManager = null;
        this.wakeWordManager = null;
        this.vadDisplay = null;
        this.countdownTimer = null;
        this.asrResultDisplay = null;
        this.uiManager = null;
        
        // 應用狀態
        this.isInitialized = false;
        this.isConnected = false;
        this.currentProtocol = 'websocket';
        this.sessionId = null;
        this.currentSessionId = null;  // 當前會話 ID
        this.audioChunkId = 0;  // 音訊塊序號
        
        // 配置
        this.config = {
            server: {
                host: 'localhost',
                port: 8000,
                ssl: false
            },
            audio: {
                sampleRate: 16000,
                bufferSize: 4096,
                channels: 1
            },
            vad: {
                threshold: 0.5,
                smoothingWindow: 3
            },
            wakeword: {
                enabled: true,
                threshold: 0.5,
                cooldownPeriod: 2000
            },
            recording: {
                maxDuration: 30000,  // 30 seconds
                autoStop: true
            }
        };
        
        // 事件日誌
        this.eventLog = [];
        this.maxLogEntries = 100;
    }
    
    /**
     * 初始化應用程式
     */
    async initialize() {
        console.log('RealTimeStreamingApp: 開始初始化...');
        
        try {
            // 初始化所有管理器
            await this.initializeManagers();
            
            // 設置管理器間的回調連接
            this.setupManagerCallbacks();
            
            // 設置 UI 事件監聽器
            this.setupUIEventListeners();
            
            // 初始化協議連接
            await this.initializeProtocolConnection();
            
            this.isInitialized = true;
            this.logEvent('應用程式初始化完成', 'success');
            
            console.log('✓ RealTimeStreamingApp: 應用程式初始化完成');
            
        } catch (error) {
            console.error('RealTimeStreamingApp: 初始化失敗', error);
            this.logEvent(`初始化失敗: ${error.message}`, 'error');
            throw error;
        }
    }
    
    /**
     * 初始化所有管理器
     */
    async initializeManagers() {
        console.log('RealTimeStreamingApp: 初始化管理器...');
        
        // 初始化協議適配器
        this.protocolAdapter = window.ProtocolAdapterFactory.create(this.currentProtocol);
        
        // 初始化音訊串流管理器
        this.audioStreamManager = new window.AudioStreamManager();
        await this.audioStreamManager.initialize(this.config.audio);
        
        // 初始化喚醒詞管理器
        this.wakeWordManager = new window.WakeWordManager();
        this.wakeWordManager.initialize();
        this.wakeWordManager.updateConfig(this.config.wakeword);
        
        // 初始化 VAD 顯示管理器
        this.vadDisplay = new window.VADDisplayManager();
        this.vadDisplay.initialize();
        
        // 初始化倒數計時器
        this.countdownTimer = new window.CountdownTimerManager();
        this.countdownTimer.initialize();
        
        // 初始化 ASR 結果顯示器
        this.asrResultDisplay = new window.ASRResultDisplayManager();
        this.asrResultDisplay.initialize();
        
        // 初始化 UI 管理器
        this.uiManager = new window.RealtimeUIManager();
        this.uiManager.initialize();
        
        // 設置 UI 管理器回調
        this.uiManager.setCallbacks({
            onMicButtonClick: (currentState) => {
                this.handleMicButtonClick(currentState);
            }
        });
        
        console.log('✓ RealTimeStreamingApp: 所有管理器初始化完成');
    }
    
    /**
     * 設置管理器間的回調連接
     */
    setupManagerCallbacks() {
        console.log('RealTimeStreamingApp: 設置管理器回調連接...');
        
        // 音訊串流管理器回調
        this.audioStreamManager.setCallbacks({
            onAudioData: (audioData) => {
                this.handleAudioData(audioData);
            },
            onVolumeLevel: (volumeData) => {
                this.uiManager.updateVisualizerData(volumeData.frequencyData);
            },
            onStreamStart: (audioFormat) => {
                this.logEvent('音訊串流開始', 'info');
                this.uiManager.handleStreamingChange(true);
                
                // 發送 start_listening 事件到後端，包含音訊格式
                this.sendStartListeningEvent(audioFormat);
            },
            onStreamStop: () => {
                this.logEvent('音訊串流停止', 'info');
                this.uiManager.handleStreamingChange(false);
                
                // 發送 stop_listening 事件到後端
                this.sendStopListeningEvent();
            },
            onError: (error) => {
                this.logEvent(`音訊串流錯誤: ${error}`, 'error');
            }
        });
        
        // 喚醒詞管理器回調
        this.wakeWordManager.setCallbacks({
            onWakeWordDetected: (data) => {
                this.handleWakeWordDetected(data);
            },
            onManualWake: (data) => {
                this.handleManualWake(data);
            },
            onConfidenceUpdate: (data) => {
                this.uiManager.updateWakeWordConfidence(data.confidence);
            }
        });
        
        // VAD 顯示管理器回調
        this.vadDisplay.setCallbacks({
            onSpeechStart: (data) => {
                this.handleSpeechStart(data);
            },
            onSpeechEnd: (data) => {
                this.handleSpeechEnd(data);
            },
            onSilenceStart: (data) => {
                this.handleSilenceStart(data);
            },
            onVADUpdate: (data) => {
                this.uiManager.updateVisualizerData(data.frequencyData || []);
            }
        });
        
        // 倒數計時器回調
        this.countdownTimer.setCallbacks({
            onStart: (data) => {
                this.logEvent(`倒數計時開始: ${data.duration}ms`, 'info');
                this.sendToBackend('countdown_started', data);
            },
            onTick: (data) => {
                this.uiManager.updateCountdownProgress(data.progress);
            },
            onComplete: () => {
                this.handleCountdownComplete();
            },
            onCancel: () => {
                this.logEvent('倒數計時取消', 'info');
                this.sendToBackend('countdown_cancelled', {});
            }
        });
        
        // ASR 結果顯示器回調
        this.asrResultDisplay.setCallbacks({
            onResultAdded: (result) => {
                this.uiManager.updateLatestResult(result.text);
            },
            onStatsUpdate: (stats) => {
                this.uiManager.updateResultStats(stats);
            }
        });
        
        console.log('✓ RealTimeStreamingApp: 管理器回調連接完成');
    }
    
    /**
     * 設置 UI 事件監聽器
     */
    setupUIEventListeners() {
        // 協議選擇
        const protocolSelect = document.getElementById('protocol');
        if (protocolSelect) {
            protocolSelect.addEventListener('change', (e) => {
                this.changeProtocol(e.target.value);
            });
        }
        
        // 連接/斷線按鈕
        const connectBtn = document.getElementById('connectBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => {
                if (this.isConnected) {
                    this.disconnect();
                } else {
                    this.connect();
                }
            });
        }
        
        // 主要麥克風按鈕 (在 UI 管理器中設置)
        // 開始/停止串流通過主要麥克風按鈕控制
        
        // 清空結果按鈕
        const clearResultsBtn = document.getElementById('clearResults');
        if (clearResultsBtn) {
            clearResultsBtn.addEventListener('click', () => {
                this.asrResultDisplay.clearResults();
                this.logEvent('ASR 結果已清空', 'info');
            });
        }
    }
    
    /**
     * 初始化協議連接
     */
    async initializeProtocolConnection() {
        try {
            // 設置協議事件監聽器
            this.protocolAdapter.onConnected = (protocol) => {
                this.isConnected = true;
                this.logEvent(`已連接到 ${protocol} 伺服器`, 'success');
                this.uiManager.handleConnectionChange(true, this.currentProtocol);
            };
            
            this.protocolAdapter.onDisconnected = () => {
                this.isConnected = false;
                this.logEvent('與伺服器斷線', 'warning');
                this.uiManager.handleConnectionChange(false);
            };
            
            this.protocolAdapter.onMessage = (data) => {
                this.handleBackendMessage(data);
            };
            
            this.protocolAdapter.onError = (error) => {
                this.logEvent(`協議錯誤: ${error}`, 'error');
            };
            
            // 連接到伺服器
            await this.protocolAdapter.connect();
            
        } catch (error) {
            console.error('RealTimeStreamingApp: 協議連接失敗', error);
            this.logEvent(`協議連接失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 建構伺服器 URL
     */
    buildServerUrl() {
        const { host, port, ssl } = this.config.server;
        const protocol = ssl ? 'https' : 'http';
        return `${protocol}://${host}:${port}`;
    }
    
    /**
     * 發送 start_listening 事件到後端
     */
    sendStartListeningEvent(audioFormat) {
        if (!this.currentSessionId) {
            this.currentSessionId = this.generateSessionId();
        }
        
        // 發送 PyStoreX action 格式的 start_listening 事件
        const action = {
            type: '[Session] Start Listening',
            payload: {
                session_id: this.currentSessionId,
                audio_format: audioFormat,
                protocol: this.currentProtocol,
                timestamp: Date.now()
            }
        };
        
        this.sendToBackend('action', action);
        this.logEvent(`發送 start_listening 事件: ${JSON.stringify(audioFormat)}`, 'info');
    }
    
    /**
     * 發送 stop_listening 事件到後端
     */
    sendStopListeningEvent() {
        if (!this.currentSessionId) {
            console.warn('No active session to stop');
            return;
        }
        
        // 發送 PyStoreX action 格式的 stop_listening 事件
        const action = {
            type: '[Session] Stop Listening',
            payload: {
                session_id: this.currentSessionId,
                timestamp: Date.now()
            }
        };
        
        this.sendToBackend('action', action);
        this.logEvent('發送 stop_listening 事件', 'info');
    }
    
    /**
     * 處理音訊資料
     */
    handleAudioData(audioData) {
        // 發送音訊資料到後端（實時串流）
        if (this.protocolAdapter && this.protocolAdapter.isConnected && this.currentSessionId) {
            // 將 Float32Array 轉換為適合傳輸的格式
            const audioChunk = {
                session_id: this.currentSessionId,
                audio: audioData,  // Float32Array
                timestamp: Date.now()
            };
            
            // 使用協議適配器發送音訊塊
            if (this.protocolAdapter.sendAudioChunk) {
                this.protocolAdapter.sendAudioChunk(
                    this.currentSessionId,
                    audioData.buffer,
                    this.audioChunkId++
                );
            }
        }
        
        // 更新音訊視覺化
        this.uiManager.updateAudioVisualizer(audioData);
    }
    
    /**
     * 處理喚醒詞檢測
     */
    handleWakeWordDetected(data) {
        this.logEvent(`喚醒詞檢測: ${data.model} (${(data.confidence * 100).toFixed(1)}%)`, 'success');
        
        // 發送喚醒事件到後端
        this.sendToBackend('wake_triggered', {
            type: data.type,
            confidence: data.confidence,
            trigger: data.trigger,
            model: data.model,
            timestamp: data.timestamp
        });
        
        // 開始錄音倒數計時
        this.startRecordingCountdown();
    }
    
    /**
     * 處理手動喚醒
     */
    handleManualWake(data) {
        this.logEvent('手動喚醒觸發', 'success');
        
        // 發送手動喚醒事件到後端
        this.sendToBackend('wake_triggered', {
            type: 'manual',
            confidence: 1.0,
            trigger: 'manual_button',
            timestamp: data.timestamp
        });
        
        // 開始錄音倒數計時
        this.startRecordingCountdown();
    }
    
    /**
     * 處理語音開始
     */
    handleSpeechStart(data) {
        this.logEvent(`語音檢測開始 (機率: ${(data.probability * 100).toFixed(1)}%)`, 'info');
        
        // 發送語音檢測事件到後端
        this.sendToBackend('speech_detected', {
            probability: data.probability,
            timestamp: data.timestamp
        });
        
        // 暫停倒數計時器（如果正在運行）
        if (this.countdownTimer.isRunning()) {
            this.countdownTimer.pause();
        }
    }
    
    /**
     * 處理語音結束
     */
    handleSpeechEnd(data) {
        this.logEvent(`語音檢測結束 (時長: ${data.speechDuration}ms)`, 'info');
        
        // 發送靜音檢測事件到後端
        this.sendToBackend('silence_detected', {
            probability: data.probability,
            speechDuration: data.speechDuration,
            timestamp: data.timestamp
        });
    }
    
    /**
     * 處理靜音開始
     */
    handleSilenceStart(data) {
        // 恢復倒數計時器（如果已暫停）
        if (this.countdownTimer.isPaused()) {
            this.countdownTimer.resume();
        }
    }
    
    /**
     * 處理倒數計時完成
     */
    handleCountdownComplete() {
        this.logEvent('錄音倒數計時完成', 'success');
        
        // 發送錄音完成事件到後端
        this.sendToBackend('recording_completed', {
            timestamp: Date.now()
        });
    }
    
    /**
     * 處理麥克風按鈕點擊
     */
    async handleMicButtonClick(currentState) {
        try {
            if (!this.isConnected) {
                this.logEvent('請先連接到後端服務', 'warning');
                return;
            }
            
            switch (currentState) {
                case 'connected':
                    // 開始音訊串流
                    await this.audioStreamManager.startStreaming();
                    this.uiManager.updateState('streaming');
                    break;
                    
                case 'streaming':
                    // 停止音訊串流
                    await this.audioStreamManager.stopStreaming();
                    this.uiManager.updateState('connected');
                    break;
                    
                case 'recording':
                    // 手動停止錄音
                    this.countdownTimer.cancel();
                    this.uiManager.updateState('streaming');
                    break;
                    
                default:
                    console.log(`handleMicButtonClick: 未處理的狀態 ${currentState}`);
            }
        } catch (error) {
            console.error('handleMicButtonClick: 處理失敗', error);
            this.logEvent(`麥克風操作失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 生成會話 ID
     */
    generateSessionId() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 9);
        return `session-${timestamp}-${random}`;
    }
    
    /**
     * 開始錄音倒數計時
     */
    startRecordingCountdown() {
        const duration = this.config.recording.maxDuration;
        this.countdownTimer.start(duration);
        this.logEvent(`開始錄音倒數計時 (${duration / 1000}秒)`, 'info');
    }
    
    /**
     * 處理後端訊息
     */
    handleBackendMessage(message) {
        try {
            const { type, data } = message;
            
            switch (type) {
                case 'session_created':
                    this.sessionId = data.session_id;
                    this.logEvent(`會話建立: ${this.sessionId}`, 'success');
                    break;
                    
                case 'vad_result':
                    this.vadDisplay.handleVADUpdate(data);
                    break;
                    
                case 'wakeword_result':
                    this.wakeWordManager.handleWakeWordDetection(data);
                    break;
                    
                case 'asr_partial':
                    this.asrResultDisplay.addPartialResult(data);
                    break;
                    
                case 'asr_final':
                    this.asrResultDisplay.addFinalResult(data);
                    this.logEvent(`ASR 結果: ${data.text}`, 'success');
                    break;
                    
                case 'recording_started':
                    this.logEvent('後端開始錄音', 'info');
                    break;
                    
                case 'recording_stopped':
                    this.logEvent('後端停止錄音', 'info');
                    break;
                    
                case 'error':
                    this.logEvent(`後端錯誤: ${data.message}`, 'error');
                    break;
                    
                default:
                    console.log('RealTimeStreamingApp: 未知訊息類型', type, data);
            }
            
        } catch (error) {
            console.error('RealTimeStreamingApp: 處理後端訊息失敗', error);
            this.logEvent(`處理後端訊息失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 發送資料到後端
     */
    sendToBackend(eventType, data) {
        if (!this.isConnected || !this.protocolAdapter) {
            console.warn('RealTimeStreamingApp: 未連接到後端，無法發送資料');
            return;
        }
        
        try {
            // 特殊處理 action 類型的訊息
            if (eventType === 'action') {
                // 對於 action 類型，data 本身就是完整的 action 對象
                // 使用正確的格式發送給後端
                const message = {
                    type: 'action',
                    action: data  // data 包含 type 和 payload
                };
                
                if (this.currentProtocol === 'websocket') {
                    this.protocolAdapter.connection.send(JSON.stringify(message));
                } else if (this.currentProtocol === 'socketio') {
                    this.protocolAdapter.connection.emit('action', data);
                } else if (this.currentProtocol === 'http_sse') {
                    this.protocolAdapter.sendAction(data);
                }
            } else {
                // 其他類型的訊息保持原有格式
                if (this.currentProtocol === 'http_sse') {
                    // HTTP SSE 使用 action 格式
                    this.protocolAdapter.sendAction({
                        type: eventType,
                        session_id: this.sessionId,
                        payload: data,
                        timestamp: Date.now()
                    });
                } else {
                    // WebSocket 和 Socket.IO 使用 JSON 格式
                    this.protocolAdapter.connection.send(JSON.stringify({
                        type: eventType,
                        session_id: this.sessionId,
                        data: data,
                        timestamp: Date.now()
                    }));
                }
            }
        } catch (error) {
            console.error('RealTimeStreamingApp: 發送資料到後端失敗', error);
            this.logEvent(`發送資料失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 切換協議
     */
    async changeProtocol(newProtocol) {
        if (newProtocol === this.currentProtocol) return;
        
        this.logEvent(`切換協議到 ${newProtocol.toUpperCase()}`, 'info');
        
        try {
            // 斷開當前連接
            if (this.isConnected) {
                await this.disconnect();
            }
            
            // 更新協議
            this.currentProtocol = newProtocol;
            
            // 重新初始化協議適配器
            this.protocolAdapter = window.ProtocolAdapterFactory.create(this.currentProtocol);
            await this.initializeProtocolConnection();
            
        } catch (error) {
            console.error('RealTimeStreamingApp: 切換協議失敗', error);
            this.logEvent(`切換協議失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 連接到後端
     */
    async connect() {
        try {
            await this.protocolAdapter.connect();
            this.logEvent(`連接到 ${this.currentProtocol.toUpperCase()} 伺服器`, 'info');
        } catch (error) {
            console.error('RealTimeStreamingApp: 連接失敗', error);
            this.logEvent(`連接失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 斷開連接
     */
    async disconnect() {
        try {
            if (this.audioStreamManager.isStreaming()) {
                await this.audioStreamManager.stopStreaming();
            }
            
            await this.protocolAdapter.disconnect();
            this.logEvent('已斷開連接', 'info');
        } catch (error) {
            console.error('RealTimeStreamingApp: 斷開連接失敗', error);
            this.logEvent(`斷開連接失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 切換串流狀態
     */
    async toggleStreaming() {
        try {
            if (this.audioStreamManager.isStreaming()) {
                await this.audioStreamManager.stopStreaming();
                this.logEvent('停止音訊串流', 'info');
            } else {
                await this.audioStreamManager.startStreaming();
                this.logEvent('開始音訊串流', 'info');
            }
        } catch (error) {
            console.error('RealTimeStreamingApp: 切換串流狀態失敗', error);
            this.logEvent(`切換串流狀態失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 記錄事件
     */
    logEvent(message, type = 'info') {
        const event = {
            timestamp: new Date().toISOString(),
            type: type,
            message: message
        };
        
        this.eventLog.unshift(event);
        
        // 限制日誌長度
        if (this.eventLog.length > this.maxLogEntries) {
            this.eventLog = this.eventLog.slice(0, this.maxLogEntries);
        }
        
        // 更新 UI 事件日誌
        if (this.uiManager) {
            this.uiManager.addLog(event.message, event.type, event.timestamp);
        }
        
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
    
    /**
     * 獲取應用狀態
     */
    getStatus() {
        return {
            isInitialized: this.isInitialized,
            isConnected: this.isConnected,
            currentProtocol: this.currentProtocol,
            sessionId: this.sessionId,
            isStreaming: this.audioStreamManager ? this.audioStreamManager.isStreaming() : false,
            eventLogLength: this.eventLog.length
        };
    }
    
    /**
     * 清理資源
     */
    async cleanup() {
        console.log('RealTimeStreamingApp: 開始清理資源...');
        
        try {
            // 停止音訊串流
            if (this.audioStreamManager && this.audioStreamManager.isStreaming()) {
                await this.audioStreamManager.stopStreaming();
            }
            
            // 斷開協議連接
            if (this.protocolAdapter && this.isConnected) {
                await this.protocolAdapter.disconnect();
            }
            
            // 清理所有管理器
            if (this.audioStreamManager) this.audioStreamManager.cleanup();
            if (this.wakeWordManager) this.wakeWordManager.cleanup();
            if (this.vadDisplay) this.vadDisplay.cleanup();
            if (this.countdownTimer) this.countdownTimer.cleanup();
            if (this.asrResultDisplay) this.asrResultDisplay.cleanup();
            if (this.uiManager) this.uiManager.cleanup();
            
            // 重置狀態
            this.isInitialized = false;
            this.isConnected = false;
            this.sessionId = null;
            this.eventLog = [];
            
            console.log('✓ RealTimeStreamingApp: 資源清理完成');
            
        } catch (error) {
            console.error('RealTimeStreamingApp: 清理資源失敗', error);
        }
    }
}

// 全域應用實例
let app = null;

// DOM 載入完成後初始化
document.addEventListener('DOMContentLoaded', async () => {
    console.log('RealTimeStreamingApp: DOM 載入完成，開始初始化應用...');
    
    try {
        app = new RealTimeStreamingApp();
        await app.initialize();
        
        // 將應用實例綁定到 window 物件以便調試
        window.realtimeApp = app;
        
        console.log('✓ RealTimeStreamingApp: 應用程式啟動完成');
        
    } catch (error) {
        console.error('RealTimeStreamingApp: 應用程式啟動失敗', error);
        
        // 顯示錯誤訊息給用戶
        const errorDiv = document.createElement('div');
        errorDiv.className = 'bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4';
        errorDiv.innerHTML = `
            <strong>應用程式啟動失敗：</strong>
            <span>${error.message}</span>
        `;
        document.body.insertBefore(errorDiv, document.body.firstChild);
    }
});

// 頁面卸載時清理資源
window.addEventListener('beforeunload', async () => {
    if (app) {
        await app.cleanup();
    }
});

// 導出到全域
window.RealTimeStreamingApp = RealTimeStreamingApp;