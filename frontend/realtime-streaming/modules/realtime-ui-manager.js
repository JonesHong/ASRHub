/**
 * Realtime UI Manager
 * 管理實時串流介面的整體 UI 狀態和協調各個組件
 */

class RealtimeUIManager {
    constructor() {
        // UI 組件引用
        this.audioVisualizer = null;
        this.micButton = null;
        this.micIcon = null;
        this.micStatus = null;
        this.connectionStatus = null;
        
        // 狀態管理
        this.currentState = 'disconnected'; // disconnected, connected, streaming, recording, processing
        this.isStreamingActive = false;
        this.isRecordingActive = false;
        this.connectionState = 'disconnected';
        
        // 視覺化
        this.audioVisualizerContext = null;
        this.visualizerAnimationId = null;
        this.visualizerData = new Uint8Array(256);
        
        // 事件日誌
        this.eventLogs = [];
        this.maxLogEntries = 100;
        this.logContainer = null;
        
        // 回調函數
        this.onStateChange = null;
        this.onMicButtonClick = null;
        this.onUIUpdate = null;
        
        // UI 狀態映射
        this.stateConfig = {
            disconnected: {
                micButton: { enabled: false, class: 'bg-gray-400', text: '未連接' },
                micIcon: 'fa-microphone-slash',
                connectionStatus: { class: 'status-disconnected', text: '未連接', icon: 'fa-circle text-red-500' }
            },
            connected: {
                micButton: { enabled: true, class: 'bg-green-500 hover:bg-green-600', text: '點擊開始音訊串流' },
                micIcon: 'fa-microphone',
                connectionStatus: { class: 'status-connected', text: '已連接', icon: 'fa-circle text-green-500' }
            },
            streaming: {
                micButton: { enabled: true, class: 'bg-blue-500 hover:bg-blue-600 streaming', text: '音訊串流中...' },
                micIcon: 'fa-microphone',
                connectionStatus: { class: 'status-connected', text: '串流中', icon: 'fa-circle text-blue-500' }
            },
            recording: {
                micButton: { enabled: true, class: 'bg-red-500 hover:bg-red-600 recording', text: '錄音中...' },
                micIcon: 'fa-stop',
                connectionStatus: { class: 'status-connected', text: '錄音中', icon: 'fa-circle text-red-500' }
            },
            processing: {
                micButton: { enabled: false, class: 'bg-yellow-500', text: '處理中...' },
                micIcon: 'fa-cog fa-spin',
                connectionStatus: { class: 'status-connected', text: '處理中', icon: 'fa-circle text-yellow-500' }
            }
        };
    }
    
    /**
     * 初始化 UI 管理器
     */
    initialize() {
        console.log('RealtimeUIManager: 初始化實時 UI 管理器...');
        
        try {
            // 獲取 UI 元素
            this.micButton = document.getElementById('mainMicBtn');
            this.micIcon = document.getElementById('micIcon');
            this.micStatus = document.getElementById('micStatus');
            this.connectionStatus = document.getElementById('connectionStatus');
            this.logContainer = document.getElementById('eventLogs');
            
            // 初始化音訊視覺化器
            this.initializeAudioVisualizer();
            
            // 設置事件監聽器
            this.setupEventListeners();
            
            // 初始化 UI 狀態
            this.updateState('disconnected');
            
            // 添加初始日誌
            this.addLog('系統初始化完成', 'info');
            
            console.log('✓ RealtimeUIManager: 實時 UI 管理器初始化完成');
            
        } catch (error) {
            console.error('RealtimeUIManager: 初始化失敗', error);
            this.addLog(`初始化失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 初始化音訊視覺化器
     */
    initializeAudioVisualizer() {
        try {
            const canvas = document.getElementById('audioVisualizer');
            if (!canvas) {
                console.warn('RealtimeUIManager: 找不到音訊視覺化器畫布');
                return;
            }
            
            this.audioVisualizer = canvas;
            this.audioVisualizerContext = canvas.getContext('2d');
            
            // 設置畫布大小
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width * window.devicePixelRatio;
            canvas.height = rect.height * window.devicePixelRatio;
            this.audioVisualizerContext.scale(window.devicePixelRatio, window.devicePixelRatio);
            
            // 開始視覺化動畫
            this.startVisualizerAnimation();
            
            console.log('✓ RealtimeUIManager: 音訊視覺化器初始化完成');
            
        } catch (error) {
            console.error('RealtimeUIManager: 音訊視覺化器初始化失敗', error);
        }
    }
    
    /**
     * 設置事件監聽器
     */
    setupEventListeners() {
        // 主麥克風按鈕
        if (this.micButton) {
            this.micButton.addEventListener('click', () => {
                if (this.onMicButtonClick) {
                    this.onMicButtonClick(this.currentState);
                }
            });
        }
        
        // 清空日誌按鈕
        const clearLogsBtn = document.getElementById('clearLogs');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => {
                this.clearLogs();
            });
        }
        
        // 視窗大小變化事件
        window.addEventListener('resize', () => {
            this.handleResize();
        });
    }
    
    /**
     * 處理視窗大小變化
     */
    handleResize() {
        if (this.audioVisualizer && this.audioVisualizerContext) {
            const rect = this.audioVisualizer.getBoundingClientRect();
            this.audioVisualizer.width = rect.width * window.devicePixelRatio;
            this.audioVisualizer.height = rect.height * window.devicePixelRatio;
            this.audioVisualizerContext.scale(window.devicePixelRatio, window.devicePixelRatio);
        }
    }
    
    /**
     * 更新 UI 狀態
     */
    updateState(newState, additionalData = {}) {
        try {
            const oldState = this.currentState;
            this.currentState = newState;
            
            console.log(`RealtimeUIManager: 狀態變化 ${oldState} → ${newState}`);
            
            // 獲取狀態配置
            const config = this.stateConfig[newState];
            if (!config) {
                console.warn(`RealtimeUIManager: 未知的狀態: ${newState}`);
                return;
            }
            
            // 更新麥克風按鈕
            this.updateMicButton(config.micButton, config.micIcon);
            
            // 更新連接狀態
            this.updateConnectionStatus(config.connectionStatus);
            
            // 更新特定狀態標記
            this.updateStateFlags(newState);
            
            // 添加狀態變化日誌
            this.addLog(`狀態變更: ${this.getStateDisplayName(newState)}`, 'info');
            
            // 觸發狀態變化回調
            if (this.onStateChange) {
                this.onStateChange({
                    oldState: oldState,
                    newState: newState,
                    additionalData: additionalData,
                    timestamp: Date.now()
                });
            }
            
            // 觸發 UI 更新回調
            if (this.onUIUpdate) {
                this.onUIUpdate({
                    state: newState,
                    config: config,
                    timestamp: Date.now()
                });
            }
            
        } catch (error) {
            console.error('RealtimeUIManager: 更新狀態失敗', error);
            this.addLog(`狀態更新失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 更新麥克風按鈕
     */
    updateMicButton(buttonConfig, iconClass) {
        if (!this.micButton || !this.micIcon || !this.micStatus) return;
        
        // 更新按鈕狀態
        this.micButton.disabled = !buttonConfig.enabled;
        this.micButton.className = `w-32 h-32 rounded-full text-white shadow-lg transform transition-all duration-300 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed ${buttonConfig.class}`;
        
        // 更新圖標
        this.micIcon.className = `fas ${iconClass} text-4xl`;
        
        // 更新狀態文字
        this.micStatus.textContent = buttonConfig.text;
    }
    
    /**
     * 更新連接狀態
     */
    updateConnectionStatus(statusConfig) {
        if (!this.connectionStatus) return;
        
        this.connectionStatus.className = `inline-flex items-center px-3 py-1 rounded-full text-sm ${statusConfig.class}`;
        this.connectionStatus.innerHTML = `
            <i class="fas ${statusConfig.icon} mr-2"></i>
            <span>${statusConfig.text}</span>
        `;
    }
    
    /**
     * 更新狀態標記
     */
    updateStateFlags(state) {
        const body = document.body;
        
        // 移除所有狀態類別
        body.classList.remove('streaming', 'recording', 'processing');
        
        // 添加當前狀態類別
        if (state === 'streaming') {
            body.classList.add('streaming');
            this.isStreamingActive = true;
            this.isRecordingActive = false;
        } else if (state === 'recording') {
            body.classList.add('recording');
            this.isStreamingActive = true;
            this.isRecordingActive = true;
        } else if (state === 'processing') {
            body.classList.add('processing');
            this.isStreamingActive = false;
            this.isRecordingActive = false;
        } else {
            this.isStreamingActive = false;
            this.isRecordingActive = false;
        }
    }
    
    /**
     * 開始視覺化動畫
     */
    startVisualizerAnimation() {
        const draw = () => {
            if (!this.audioVisualizerContext || !this.audioVisualizer) return;
            
            const ctx = this.audioVisualizerContext;
            const canvas = this.audioVisualizer;
            const width = canvas.width / window.devicePixelRatio;
            const height = canvas.height / window.devicePixelRatio;
            
            // 清空畫布
            ctx.clearRect(0, 0, width, height);
            
            // 設置樣式
            ctx.fillStyle = this.isStreamingActive ? 
                'rgba(34, 197, 94, 0.6)' : // 綠色 (streaming)
                'rgba(156, 163, 175, 0.3)'; // 灰色 (inactive)
            
            // 繪製頻率條
            const barWidth = width / this.visualizerData.length;
            
            for (let i = 0; i < this.visualizerData.length; i++) {
                const barHeight = this.isStreamingActive ? 
                    (this.visualizerData[i] / 255) * height : 
                    Math.random() * 0.1 * height; // 靜態時顯示少量隨機波動
                
                ctx.fillRect(i * barWidth, height - barHeight, barWidth - 1, barHeight);
            }
            
            this.visualizerAnimationId = requestAnimationFrame(draw);
        };
        
        draw();
    }
    
    /**
     * 停止視覺化動畫
     */
    stopVisualizerAnimation() {
        if (this.visualizerAnimationId) {
            cancelAnimationFrame(this.visualizerAnimationId);
            this.visualizerAnimationId = null;
        }
    }
    
    /**
     * 更新音訊視覺化數據
     */
    updateVisualizerData(frequencyData) {
        if (frequencyData && frequencyData.length > 0) {
            // 如果提供的數據長度不同，進行重採樣
            if (frequencyData.length !== this.visualizerData.length) {
                for (let i = 0; i < this.visualizerData.length; i++) {
                    const sourceIndex = Math.floor((i / this.visualizerData.length) * frequencyData.length);
                    this.visualizerData[i] = frequencyData[sourceIndex];
                }
            } else {
                this.visualizerData.set(frequencyData);
            }
        }
    }
    
    /**
     * 更新音訊視覺化器（別名方法，為了兼容性）
     */
    updateAudioVisualizer(audioData) {
        // 將音訊數據轉換為頻率數據
        if (audioData instanceof Float32Array || audioData instanceof Uint8Array) {
            // 簡單的振幅映射到視覺化數據
            const visualData = new Uint8Array(this.visualizerData.length);
            const blockSize = Math.floor(audioData.length / visualData.length);
            
            for (let i = 0; i < visualData.length; i++) {
                let sum = 0;
                const startIdx = i * blockSize;
                const endIdx = Math.min(startIdx + blockSize, audioData.length);
                
                for (let j = startIdx; j < endIdx; j++) {
                    // 轉換音訊樣本到視覺化範圍 (0-255)
                    const sample = audioData instanceof Float32Array ? 
                        Math.abs(audioData[j]) * 255 : 
                        audioData[j];
                    sum += sample;
                }
                
                visualData[i] = Math.min(255, sum / blockSize);
            }
            
            this.updateVisualizerData(visualData);
        }
    }
    
    /**
     * 添加事件日誌
     */
    addLog(message, level = 'info', timestamp = null) {
        try {
            const logEntry = {
                id: Date.now() + Math.random(),
                message: message,
                level: level,
                timestamp: timestamp || Date.now()
            };
            
            this.eventLogs.unshift(logEntry);
            
            // 限制日誌數量
            if (this.eventLogs.length > this.maxLogEntries) {
                this.eventLogs = this.eventLogs.slice(0, this.maxLogEntries);
            }
            
            // 更新日誌顯示
            this.updateLogDisplay();
            
            console.log(`[${level.toUpperCase()}] ${message}`);
            
        } catch (error) {
            console.error('RealtimeUIManager: 添加日誌失敗', error);
        }
    }
    
    /**
     * 更新日誌顯示
     */
    updateLogDisplay() {
        if (!this.logContainer) return;
        
        try {
            // 限制顯示最近的日誌條目
            const displayLogs = this.eventLogs.slice(0, 20);
            
            this.logContainer.innerHTML = displayLogs.map(log => {
                const timeStr = new Date(log.timestamp).toLocaleTimeString('zh-TW', {
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
                
                return `
                    <div class="log-item">
                        <span class="log-timestamp">${timeStr}</span>
                        <span class="log-level-${log.level}">[${log.level.toUpperCase()}]</span>
                        <span class="ml-2">${log.message}</span>
                    </div>
                `;
            }).join('');
            
            // 自動滾動到最新日誌
            this.logContainer.scrollTop = 0;
            
        } catch (error) {
            console.error('RealtimeUIManager: 更新日誌顯示失敗', error);
        }
    }
    
    /**
     * 清空日誌
     */
    clearLogs() {
        this.eventLogs = [];
        this.updateLogDisplay();
        this.addLog('事件日誌已清空', 'info');
    }
    
    /**
     * 獲取狀態顯示名稱
     */
    getStateDisplayName(state) {
        const stateNames = {
            disconnected: '未連接',
            connected: '已連接',
            streaming: '音訊串流',
            recording: '錄音中',
            processing: '處理中'
        };
        
        return stateNames[state] || state;
    }
    
    /**
     * 處理連接狀態變化
     */
    handleConnectionChange(isConnected, protocol = null) {
        this.connectionState = isConnected ? 'connected' : 'disconnected';
        
        if (isConnected) {
            this.updateState('connected');
            this.addLog(`已連接到 ${protocol || '後端'}`, 'success');
        } else {
            this.updateState('disconnected');
            this.addLog('連接已斷開', 'warning');
        }
    }
    
    /**
     * 處理音訊串流狀態變化
     */
    handleStreamingChange(isStreaming) {
        if (isStreaming && this.connectionState === 'connected') {
            this.updateState('streaming');
            this.addLog('音訊串流已開始', 'success');
        } else if (!isStreaming && this.currentState === 'streaming') {
            this.updateState('connected');
            this.addLog('音訊串流已停止', 'info');
        }
    }
    
    /**
     * 處理錄音狀態變化
     */
    handleRecordingChange(isRecording) {
        if (isRecording && this.isStreamingActive) {
            this.updateState('recording');
            this.addLog('開始錄音', 'success');
        } else if (!isRecording && this.currentState === 'recording') {
            this.updateState('streaming');
            this.addLog('錄音結束', 'info');
        }
    }
    
    /**
     * 處理處理狀態變化
     */
    handleProcessingChange(isProcessing) {
        if (isProcessing) {
            this.updateState('processing');
            this.addLog('開始處理音訊', 'info');
        } else if (this.currentState === 'processing') {
            // 根據之前的狀態決定恢復到哪個狀態
            const targetState = this.isStreamingActive ? 'streaming' : 'connected';
            this.updateState(targetState);
            this.addLog('音訊處理完成', 'success');
        }
    }
    
    /**
     * 設置回調函數
     */
    setCallbacks({
        onStateChange = null,
        onMicButtonClick = null,
        onUIUpdate = null
    } = {}) {
        this.onStateChange = onStateChange;
        this.onMicButtonClick = onMicButtonClick;
        this.onUIUpdate = onUIUpdate;
    }
    
    /**
     * 獲取當前狀態
     */
    getCurrentState() {
        return {
            currentState: this.currentState,
            isStreamingActive: this.isStreamingActive,
            isRecordingActive: this.isRecordingActive,
            connectionState: this.connectionState,
            logCount: this.eventLogs.length
        };
    }
    
    /**
     * 獲取日誌歷史
     */
    getLogHistory(limit = 50) {
        return this.eventLogs.slice(0, limit);
    }
    
    /**
     * 清理資源
     */
    cleanup() {
        console.log('RealtimeUIManager: 清理資源...');
        
        // 停止視覺化動畫
        this.stopVisualizerAnimation();
        
        // 移除事件監聽器
        if (this.micButton) {
            this.micButton.removeEventListener('click', this.onMicButtonClick);
        }
        
        window.removeEventListener('resize', this.handleResize);
        
        // 清空日誌
        this.eventLogs = [];
        
        // 重置狀態
        this.updateState('disconnected');
        
        console.log('✓ RealtimeUIManager: 資源清理完成');
    }
}

// 導出到全域
window.RealtimeUIManager = RealtimeUIManager;