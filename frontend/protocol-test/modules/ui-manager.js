// UI 狀態管理模組 - 統一管理所有 UI 元素的狀態和更新
class UIManager {
    constructor() {
        this.elements = {};
        this.status = {
            current: 'ready',
            text: '準備就緒'
        };
        
        this.initializeElements();
        this.initializeStatusElements();
    }
    
    /**
     * 初始化 DOM 元素引用
     */
    initializeElements() {
        this.elements = {
            // 控制按鈕
            protocolSelect: document.getElementById('protocol'),
            autoTranscribeCheckbox: document.getElementById('autoTranscribe'),
            startRecordBtn: document.getElementById('startRecord'),
            stopRecordBtn: document.getElementById('stopRecord'),
            startRecognitionBtn: document.getElementById('startRecognition'),
            
            // 狀態顯示
            status: document.getElementById('status'),
            connectionStatus: document.getElementById('connectionStatus'),
            
            // 音訊相關
            audioPlayer: document.getElementById('audioPlayer'),
            audioInfo: document.getElementById('audioInfo'),
            audioFileInput: document.getElementById('audioFile'),
            fileInfo: document.getElementById('fileInfo'),
            
            // 結果和日誌
            results: document.getElementById('results'),
            logs: document.getElementById('logs')
        };
        
    }
    
    /**
     * 初始化狀態元素
     */
    initializeStatusElements() {
        if (this.elements.status) {
            this.elements.status.classList.add('status-dynamic');
            this.elements.status.dataset.status = 'ready';
        }
    }
    
    /**
     * 更新主要狀態顯示
     */
    updateStatus(text, type = 'ready') {
        this.status.current = type;
        this.status.text = text;
        
        if (this.elements.status) {
            ASRHubCommon.updateStatusWithData(this.elements.status, text, type);
        }
    }
    
    /**
     * 更新進度顯示
     */
    updateProgress(progress) {
        // 如果有進度條元素，更新它
        const progressBar = document.getElementById('uploadProgress');
        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `${Math.round(progress)}%`;
        }
        
        // 也可以在狀態文字中顯示進度
        if (progress < 100) {
            this.updateStatus(`上傳中... ${Math.round(progress)}%`, 'processing');
        }
    }
    
    /**
     * 更新連線狀態
     */
    updateConnectionStatus(connected, protocol = '') {
        if (!this.elements.connectionStatus) return;
        
        if (connected) {
            const protocolText = protocol ? ` (${protocol})` : '';
            this.elements.connectionStatus.innerHTML = `<i class="fas fa-circle text-green-500 mr-2"></i>已連接${protocolText}`;
            this.elements.connectionStatus.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200';
        } else {
            this.elements.connectionStatus.innerHTML = '<i class="fas fa-circle text-red-500 mr-2"></i>未連接';
            this.elements.connectionStatus.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200';
        }
    }
    
    /**
     * 設定錄音狀態的按鈕
     */
    setRecordingState(isRecording) {
        if (isRecording) {
            this.elements.startRecordBtn.disabled = true;
            this.elements.stopRecordBtn.disabled = false;
            this.elements.stopRecordBtn.classList.add('recording');
            this.elements.startRecognitionBtn.disabled = true;
        } else {
            this.elements.startRecordBtn.disabled = false;
            this.elements.stopRecordBtn.disabled = true;
            this.elements.stopRecordBtn.classList.remove('recording');
            this.elements.startRecognitionBtn.disabled = false;
        }
    }
    
    /**
     * 設定處理狀態的按鈕
     */
    setProcessingState(isProcessing) {
        if (isProcessing) {
            this.elements.startRecordBtn.disabled = true;
            this.elements.stopRecordBtn.disabled = true;
            this.elements.startRecognitionBtn.disabled = true;
        } else {
            this.elements.startRecordBtn.disabled = false;
            this.elements.stopRecordBtn.disabled = true;
            this.elements.startRecognitionBtn.disabled = false;
        }
    }
    
    /**
     * 顯示音訊播放器和資訊
     */
    displayAudioInfo(audioSource, isFileUpload = false) {
        if (!audioSource) return;
        
        const audioUrl = URL.createObjectURL(audioSource);
        this.elements.audioPlayer.src = audioUrl;
        this.elements.audioPlayer.style.display = 'block';
        
        const sourceType = isFileUpload ? '檔案' : '錄音';
        const formattedSize = ASRHubCommon.formatFileSize(audioSource.size);
        this.elements.audioInfo.textContent = `音訊${sourceType}大小: ${formattedSize}`;
    }
    
    /**
     * 顯示檔案選擇資訊
     */
    displayFileInfo(text, hasFile = false) {
        if (!this.elements.fileInfo) return;
        
        this.elements.fileInfo.textContent = text;
        
        if (hasFile) {
            this.elements.fileInfo.classList.add('has-file');
        } else {
            this.elements.fileInfo.classList.remove('has-file');
        }
    }
    
    /**
     * 清除檔案相關的 UI 狀態
     */
    clearFileState() {
        this.displayFileInfo('');
        if (this.elements.audioFileInput) {
            this.elements.audioFileInput.value = '';
        }
    }
    
    /**
     * 顯示辨識結果
     */
    displayResults(text) {
        if (!this.elements.results) return;
        
        if (text) {
            this.elements.results.textContent = text;
            this.elements.results.classList.add('has-content');
        } else {
            this.elements.results.textContent = '';
            this.elements.results.classList.remove('has-content');
        }
    }
    
    /**
     * 清除辨識結果
     */
    clearResults() {
        this.displayResults('');
    }
    
    /**
     * 添加日誌條目
     */
    addLog(message, type = 'info') {
        if (!this.elements.logs) return;
        
        ASRHubCommon.addLogEntry(this.elements.logs, message, type);
        
        // 限制日誌條目數量
        if (this.elements.logs.children.length > 100) {
            this.elements.logs.removeChild(this.elements.logs.firstChild);
        }
    }
    
    /**
     * 獲取當前選擇的協議
     */
    getSelectedProtocol() {
        return this.elements.protocolSelect?.value || 'websocket';
    }
    
    /**
     * 設定協議選擇器的值
     */
    setSelectedProtocol(protocol) {
        if (this.elements.protocolSelect) {
            this.elements.protocolSelect.value = protocol;
        }
    }
    
    /**
     * 獲取自動辨識開關狀態
     */
    getAutoTranscribeEnabled() {
        return this.elements.autoTranscribeCheckbox?.checked || false;
    }
    
    /**
     * 設定自動辨識開關狀態
     */
    setAutoTranscribeEnabled(enabled) {
        if (this.elements.autoTranscribeCheckbox) {
            this.elements.autoTranscribeCheckbox.checked = enabled;
        }
    }
    
    /**
     * 獲取選中的音訊檔案
     */
    getSelectedAudioFile() {
        return this.elements.audioFileInput?.files[0] || null;
    }
    
    /**
     * 設定事件監聽器
     */
    setEventListeners(callbacks) {
        // 協議切換
        if (callbacks.onProtocolChange && this.elements.protocolSelect) {
            this.elements.protocolSelect.addEventListener('change', (e) => {
                callbacks.onProtocolChange(e.target.value);
            });
        }
        
        // 自動辨識開關
        if (callbacks.onAutoTranscribeChange && this.elements.autoTranscribeCheckbox) {
            this.elements.autoTranscribeCheckbox.addEventListener('change', (e) => {
                callbacks.onAutoTranscribeChange(e.target.checked);
            });
        }
        
        // 錄音控制
        if (callbacks.onStartRecording && this.elements.startRecordBtn) {
            this.elements.startRecordBtn.addEventListener('click', callbacks.onStartRecording);
        }
        
        if (callbacks.onStopRecording && this.elements.stopRecordBtn) {
            this.elements.stopRecordBtn.addEventListener('click', callbacks.onStopRecording);
        }
        
        // 辨識控制
        if (callbacks.onStartRecognition && this.elements.startRecognitionBtn) {
            this.elements.startRecognitionBtn.addEventListener('click', callbacks.onStartRecognition);
        }
        
        // 檔案選擇
        if (callbacks.onFileSelect && this.elements.audioFileInput) {
            this.elements.audioFileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    callbacks.onFileSelect(file);
                }
            });
        }
    }
    
    /**
     * 顯示通知
     */
    showNotification(message, type = 'info', duration = 3000) {
        ASRHubCommon.showNotification(message, type, duration);
    }
    
    /**
     * 獲取狀態文字映射
     */
    getStatusText(state) {
        // 檢查是否為中文狀態（後端已翻譯）
        if (this.isChineseText(state)) {
            return state; // 直接返回中文狀態
        }
        
        const stateMapping = {
            // 大寫狀態值 (後端 FSM 狀態 - 舊版或回退)
            'IDLE': '閒置',
            'LISTENING': '監聽中',
            'ACTIVATED': '已激活',
            'RECORDING': '錄音中',
            'TRANSCRIBING': '轉譯中',
            'STREAMING': '串流中',
            'COMPLETED': '辨識完成',
            'ERROR': '錯誤',
            'BUSY': '忙碌中',
            'PROCESSING': '處理中',
            'RECOVERING': '恢復中',
            'ANY': '任意',
            
            // 小寫狀態值 (前端內部狀態)
            'ready': '準備就緒',
            'connecting': '連接中',
            'recording': '錄音中',
            'uploading': '上傳中',
            'processing': '處理中',
            'analyzing': '分析中',
            'complete': '辨識完成',
            'error': '發生錯誤',
            'busy': '處理中',
            'transcribing': '辨識中',
            'listening': '等待喚醒',
            'idle': '準備就緒',
            'completed': '辨識完成'
        };
        
        return stateMapping[state] || state || '未知狀態';
    }
    
    /**
     * 檢查是否為中文文字
     */
    isChineseText(text) {
        if (!text || typeof text !== 'string') return false;
        // 檢查是否包含中文字符
        return /[\u4e00-\u9fff]/.test(text);
    }
    
    /**
     * 重置 UI 到初始狀態
     */
    reset() {
        this.updateStatus('準備就緒', 'ready');
        this.updateConnectionStatus(false);
        this.setRecordingState(false);
        this.setProcessingState(false);
        this.clearResults();
        this.clearFileState();
        
        // 隱藏音訊播放器
        if (this.elements.audioPlayer) {
            this.elements.audioPlayer.style.display = 'none';
            this.elements.audioPlayer.src = '';
        }
        
        // 清除音訊資訊
        if (this.elements.audioInfo) {
            this.elements.audioInfo.textContent = '';
        }
    }
    
    /**
     * 獲取 DOM 元素
     */
    getElement(name) {
        return this.elements[name];
    }
    
    /**
     * 獲取當前狀態
     */
    getCurrentStatus() {
        return { ...this.status };
    }
}

// 導出到全域
window.UIManager = UIManager;