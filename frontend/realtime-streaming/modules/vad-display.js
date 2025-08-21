/**
 * VAD Display Manager
 * 管理 VAD (Voice Activity Detection) 的視覺化顯示和狀態管理
 */

class VADDisplayManager {
    constructor() {
        // 狀態管理
        this.isActive = false;
        this.currentProbability = 0.0;
        this.threshold = 0.5;
        
        // 語音檢測狀態
        this.speechDetected = false;
        this.speechStartTime = null;
        this.speechDuration = 0;
        this.silenceStartTime = null;
        this.silenceDuration = 0;
        
        // UI 元素引用
        this.vadIndicator = null;
        this.vadProbabilityDisplay = null;
        this.vadThresholdSlider = null;
        this.vadThresholdValue = null;
        
        // 回調函數
        this.onSpeechStart = null;      // 語音開始回調
        this.onSpeechEnd = null;        // 語音結束回調
        this.onSilenceStart = null;     // 靜音開始回調
        this.onThresholdChange = null;  // 閾值變化回調
        this.onVADUpdate = null;        // VAD 更新回調
        
        // 歷史記錄
        this.probabilityHistory = [];
        this.maxHistoryLength = 100;
        
        // 平滑處理
        this.smoothingWindow = 3;
        this.recentProbabilities = [];
        
        // 視覺效果
        this.animationFrameId = null;
        this.pulseIntensity = 0;
    }
    
    /**
     * 初始化 VAD 顯示管理器
     */
    initialize() {
        console.log('VADDisplayManager: 初始化 VAD 顯示管理器...');
        
        try {
            // 獲取 UI 元素
            this.vadIndicator = document.getElementById('vadIndicator');
            this.vadProbabilityDisplay = document.getElementById('vadProbability');
            this.vadThresholdSlider = document.getElementById('vadThreshold');
            this.vadThresholdValue = document.getElementById('vadThresholdValue');
            
            // 設置事件監聽器
            this.setupEventListeners();
            
            // 初始化 UI 狀態
            this.updateUI();
            
            // 開始動畫循環
            this.startAnimation();
            
            console.log('✓ VADDisplayManager: VAD 顯示管理器初始化完成');
            
        } catch (error) {
            console.error('VADDisplayManager: 初始化失敗', error);
        }
    }
    
    /**
     * 設置事件監聽器
     */
    setupEventListeners() {
        // VAD 閾值滑桿
        if (this.vadThresholdSlider) {
            this.vadThresholdSlider.addEventListener('input', (e) => {
                const newThreshold = parseFloat(e.target.value);
                this.setThreshold(newThreshold);
            });
        }
    }
    
    /**
     * 設置 VAD 閾值
     */
    setThreshold(threshold) {
        this.threshold = threshold;
        
        // 更新閾值顯示
        if (this.vadThresholdValue) {
            this.vadThresholdValue.textContent = threshold.toFixed(1);
        }
        
        console.log(`VADDisplayManager: VAD 閾值更新為 ${threshold}`);
        
        // 觸發閾值變化回調
        if (this.onThresholdChange) {
            this.onThresholdChange({
                threshold: threshold,
                timestamp: Date.now()
            });
        }
        
        // 重新評估當前語音狀態
        this.evaluateSpeechState(this.currentProbability);
    }
    
    /**
     * 處理 VAD 結果更新
     */
    handleVADUpdate(data) {
        try {
            const { speech_probability, speech_detected, timestamp } = data;
            
            // 更新當前機率
            this.currentProbability = speech_probability || 0.0;
            
            // 添加到歷史記錄
            this.addToHistory(this.currentProbability, timestamp);
            
            // 平滑處理
            const smoothedProbability = this.applySmoothingFilter(this.currentProbability);
            
            // 更新 UI 顯示
            this.updateProbabilityDisplay(smoothedProbability);
            
            // 評估語音狀態
            this.evaluateSpeechState(smoothedProbability, speech_detected);
            
            // 觸發 VAD 更新回調
            if (this.onVADUpdate) {
                this.onVADUpdate({
                    probability: smoothedProbability,
                    speechDetected: this.speechDetected,
                    speechDuration: this.speechDuration,
                    silenceDuration: this.silenceDuration,
                    timestamp: timestamp || Date.now()
                });
            }
            
        } catch (error) {
            console.error('VADDisplayManager: 處理 VAD 更新失敗', error);
        }
    }
    
    /**
     * 評估語音狀態
     */
    evaluateSpeechState(probability, externalDetection = null) {
        const currentTime = Date.now();
        
        // 決定語音檢測狀態（優先使用外部檢測結果）
        const isSpeechDetected = externalDetection !== null ? 
            externalDetection : 
            probability > this.threshold;
        
        // 語音狀態變化處理
        if (isSpeechDetected && !this.speechDetected) {
            // 語音開始
            this.speechDetected = true;
            this.speechStartTime = currentTime;
            this.silenceStartTime = null;
            this.silenceDuration = 0;
            
            console.log(`✓ VADDisplayManager: 語音檢測開始 (機率: ${probability.toFixed(3)})`);
            
            // 觸發語音開始回調
            if (this.onSpeechStart) {
                this.onSpeechStart({
                    probability: probability,
                    timestamp: currentTime
                });
            }
            
        } else if (!isSpeechDetected && this.speechDetected) {
            // 語音結束，靜音開始
            this.speechDetected = false;
            this.silenceStartTime = currentTime;
            this.speechDuration = this.speechStartTime ? 
                currentTime - this.speechStartTime : 0;
            
            console.log(`✓ VADDisplayManager: 語音檢測結束，靜音開始 (語音時長: ${this.speechDuration}ms)`);
            
            // 觸發語音結束回調
            if (this.onSpeechEnd) {
                this.onSpeechEnd({
                    probability: probability,
                    speechDuration: this.speechDuration,
                    timestamp: currentTime
                });
            }
            
            // 觸發靜音開始回調
            if (this.onSilenceStart) {
                this.onSilenceStart({
                    probability: probability,
                    timestamp: currentTime
                });
            }
        }
        
        // 更新持續時間
        if (this.speechDetected && this.speechStartTime) {
            this.speechDuration = currentTime - this.speechStartTime;
        }
        
        if (!this.speechDetected && this.silenceStartTime) {
            this.silenceDuration = currentTime - this.silenceStartTime;
        }
        
        // 更新視覺指示器
        this.updateVADIndicator(isSpeechDetected, probability);
    }
    
    /**
     * 應用平滑濾波器
     */
    applySmoothingFilter(newProbability) {
        // 添加到最近機率陣列
        this.recentProbabilities.push(newProbability);
        
        // 限制陣列長度
        if (this.recentProbabilities.length > this.smoothingWindow) {
            this.recentProbabilities.shift();
        }
        
        // 計算移動平均
        const sum = this.recentProbabilities.reduce((acc, val) => acc + val, 0);
        return sum / this.recentProbabilities.length;
    }
    
    /**
     * 更新機率顯示
     */
    updateProbabilityDisplay(probability) {
        if (this.vadProbabilityDisplay) {
            this.vadProbabilityDisplay.textContent = probability.toFixed(3);
            
            // 根據機率調整顏色
            if (probability > this.threshold) {
                this.vadProbabilityDisplay.className = 'text-sm text-green-600 dark:text-green-400 font-bold';
            } else if (probability > this.threshold * 0.7) {
                this.vadProbabilityDisplay.className = 'text-sm text-yellow-600 dark:text-yellow-400';
            } else {
                this.vadProbabilityDisplay.className = 'text-sm text-gray-600 dark:text-gray-400';
            }
        }
    }
    
    /**
     * 更新 VAD 指示器
     */
    updateVADIndicator(isSpeechDetected, probability) {
        if (!this.vadIndicator) return;
        
        // 移除所有狀態類別
        this.vadIndicator.classList.remove('vad-active', 'vad-inactive', 'bg-green-500', 'bg-gray-400');
        
        if (isSpeechDetected) {
            // 語音檢測狀態
            this.vadIndicator.classList.add('vad-active', 'bg-green-500');
            this.pulseIntensity = Math.min(1.0, probability * 2); // 根據機率調整脈動強度
        } else {
            // 靜音狀態
            this.vadIndicator.classList.add('vad-inactive', 'bg-gray-400');
            this.pulseIntensity = 0;
        }
    }
    
    /**
     * 開始動畫循環
     */
    startAnimation() {
        const animate = () => {
            // 更新脈動效果
            if (this.vadIndicator && this.pulseIntensity > 0) {
                const opacity = 0.5 + (Math.sin(Date.now() * 0.01) * 0.3 * this.pulseIntensity);
                this.vadIndicator.style.opacity = opacity;
            } else if (this.vadIndicator) {
                this.vadIndicator.style.opacity = 1;
            }
            
            this.animationFrameId = requestAnimationFrame(animate);
        };
        
        animate();
    }
    
    /**
     * 停止動畫循環
     */
    stopAnimation() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }
    
    /**
     * 添加到歷史記錄
     */
    addToHistory(probability, timestamp) {
        this.probabilityHistory.push({
            probability: probability,
            timestamp: timestamp || Date.now()
        });
        
        // 限制歷史記錄長度
        if (this.probabilityHistory.length > this.maxHistoryLength) {
            this.probabilityHistory.shift();
        }
    }
    
    /**
     * 更新 UI 狀態
     */
    updateUI() {
        // 更新閾值顯示
        if (this.vadThresholdSlider) {
            this.vadThresholdSlider.value = this.threshold;
        }
        
        if (this.vadThresholdValue) {
            this.vadThresholdValue.textContent = this.threshold.toFixed(1);
        }
        
        // 初始化機率顯示
        this.updateProbabilityDisplay(0.0);
        
        // 初始化指示器
        this.updateVADIndicator(false, 0.0);
    }
    
    /**
     * 設置回調函數
     */
    setCallbacks({
        onSpeechStart = null,
        onSpeechEnd = null,
        onSilenceStart = null,
        onThresholdChange = null,
        onVADUpdate = null
    } = {}) {
        this.onSpeechStart = onSpeechStart;
        this.onSpeechEnd = onSpeechEnd;
        this.onSilenceStart = onSilenceStart;
        this.onThresholdChange = onThresholdChange;
        this.onVADUpdate = onVADUpdate;
    }
    
    /**
     * 獲取狀態資訊
     */
    getStatus() {
        return {
            isActive: this.isActive,
            speechDetected: this.speechDetected,
            currentProbability: this.currentProbability,
            threshold: this.threshold,
            speechDuration: this.speechDuration,
            silenceDuration: this.silenceDuration,
            historyLength: this.probabilityHistory.length
        };
    }
    
    /**
     * 獲取機率歷史
     */
    getHistory(limit = 50) {
        return this.probabilityHistory.slice(-limit);
    }
    
    /**
     * 清空歷史記錄
     */
    clearHistory() {
        this.probabilityHistory = [];
        this.recentProbabilities = [];
        console.log('VADDisplayManager: 機率歷史已清空');
    }
    
    /**
     * 重置狀態
     */
    reset() {
        this.speechDetected = false;
        this.speechStartTime = null;
        this.speechDuration = 0;
        this.silenceStartTime = null;
        this.silenceDuration = 0;
        this.currentProbability = 0.0;
        this.pulseIntensity = 0;
        
        // 重置 UI
        this.updateProbabilityDisplay(0.0);
        this.updateVADIndicator(false, 0.0);
        
        console.log('VADDisplayManager: 狀態已重置');
    }
    
    /**
     * 清理資源
     */
    cleanup() {
        console.log('VADDisplayManager: 清理資源...');
        
        // 停止動畫
        this.stopAnimation();
        
        // 移除事件監聽器
        if (this.vadThresholdSlider) {
            this.vadThresholdSlider.removeEventListener('input', this.setThreshold);
        }
        
        // 重置狀態
        this.reset();
        this.clearHistory();
        
        console.log('✓ VADDisplayManager: 資源清理完成');
    }
}

// 導出到全域
window.VADDisplayManager = VADDisplayManager;