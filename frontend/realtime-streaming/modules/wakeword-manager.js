/**
 * Wake Word Manager
 * 管理喚醒詞檢測邏輯和手動喚醒功能
 */

class WakeWordManager {
    constructor() {
        // 狀態管理
        this.enabled = true;
        this.isActive = false;
        this.cooldownPeriod = 2000; // 2秒冷卻期
        this.lastTriggerTime = 0;
        
        // 檢測配置
        this.threshold = 0.5;
        this.confidence = 0.0;
        this.currentModel = null;
        
        // 回調函數
        this.onWakeWordDetected = null;  // 喚醒詞檢測回調
        this.onManualWake = null;        // 手動喚醒回調
        this.onConfidenceUpdate = null;  // 信心度更新回調
        this.onStateChange = null;       // 狀態變化回調
        this.onError = null;             // 錯誤回調
        
        // UI 元素引用
        this.enableToggle = null;
        this.manualWakeBtn = null;
        this.confidenceDisplay = null;
        this.statusIndicator = null;
        
        // 歷史記錄
        this.detectionHistory = [];
        this.maxHistoryLength = 50;
    }
    
    /**
     * 初始化喚醒詞管理器
     */
    initialize() {
        console.log('WakeWordManager: 初始化喚醒詞管理器...');
        
        try {
            // 獲取 UI 元素
            this.enableToggle = document.getElementById('wakewordEnabled');
            this.manualWakeBtn = document.getElementById('manualWakeBtn');
            this.confidenceDisplay = document.getElementById('wakeConfidence');
            this.statusIndicator = document.getElementById('wakeIndicator');
            
            // 設置事件監聽器
            this.setupEventListeners();
            
            // 初始化 UI 狀態
            this.updateUI();
            
            console.log('✓ WakeWordManager: 喚醒詞管理器初始化完成');
            
        } catch (error) {
            console.error('WakeWordManager: 初始化失敗', error);
            if (this.onError) {
                this.onError('喚醒詞管理器初始化失敗: ' + error.message);
            }
        }
    }
    
    /**
     * 設置事件監聽器
     */
    setupEventListeners() {
        // 喚醒詞啟用開關
        if (this.enableToggle) {
            this.enableToggle.addEventListener('change', (e) => {
                this.setEnabled(e.target.checked);
            });
        }
        
        // 手動喚醒按鈕
        if (this.manualWakeBtn) {
            this.manualWakeBtn.addEventListener('click', () => {
                this.triggerManualWake();
            });
        }
    }
    
    /**
     * 設置啟用狀態
     */
    setEnabled(enabled) {
        const wasEnabled = this.enabled;
        this.enabled = enabled;
        
        console.log(`WakeWordManager: 喚醒詞檢測 ${enabled ? '啟用' : '停用'}`);
        
        // 更新 UI
        this.updateUI();
        
        // 觸發狀態變化回調
        if (this.onStateChange && wasEnabled !== enabled) {
            this.onStateChange({
                type: 'enabled_changed',
                enabled: this.enabled,
                timestamp: Date.now()
            });
        }
        
        // 如果停用，重置信心度
        if (!enabled) {
            this.updateConfidence(0.0, null);
        }
    }
    
    /**
     * 觸發手動喚醒
     */
    triggerManualWake() {
        try {
            const currentTime = Date.now();
            
            // 檢查冷卻期
            if (currentTime - this.lastTriggerTime < this.cooldownPeriod) {
                const remainingCooldown = Math.ceil((this.cooldownPeriod - (currentTime - this.lastTriggerTime)) / 1000);
                console.log(`WakeWordManager: 手動喚醒在冷卻期中，還需等待 ${remainingCooldown} 秒`);
                return;
            }
            
            this.lastTriggerTime = currentTime;
            
            console.log('✓ WakeWordManager: 手動喚醒觸發');
            
            // 記錄檢測歷史
            this.addToHistory({
                type: 'manual',
                confidence: 1.0,
                model: 'manual_trigger',
                timestamp: currentTime
            });
            
            // 觸發喚醒回調
            if (this.onManualWake) {
                this.onManualWake({
                    type: 'manual',
                    confidence: 1.0,
                    trigger: 'manual_button',
                    timestamp: currentTime
                });
            }
            
            // 臨時視覺反饋
            this.showWakeDetection('手動觸發', 1.0);
            
        } catch (error) {
            console.error('WakeWordManager: 手動喚醒失敗', error);
            if (this.onError) {
                this.onError('手動喚醒失敗: ' + error.message);
            }
        }
    }
    
    /**
     * 處理來自後端的喚醒詞檢測事件
     */
    handleWakeWordDetection(data) {
        try {
            if (!this.enabled) {
                console.log('WakeWordManager: 喚醒詞檢測已停用，忽略檢測結果');
                return;
            }
            
            const { confidence, trigger, model } = data;
            const currentTime = Date.now();
            
            // 檢查冷卻期
            if (currentTime - this.lastTriggerTime < this.cooldownPeriod) {
                console.log('WakeWordManager: 喚醒詞檢測在冷卻期中，忽略檢測結果');
                return;
            }
            
            // 檢查信心度閾值
            if (confidence >= this.threshold) {
                this.lastTriggerTime = currentTime;
                
                console.log(`✓ WakeWordManager: 喚醒詞檢測成功 - 模型: ${model || trigger}, 信心度: ${confidence.toFixed(3)}`);
                
                // 記錄檢測歷史
                this.addToHistory({
                    type: 'automatic',
                    confidence: confidence,
                    model: model || trigger,
                    timestamp: currentTime
                });
                
                // 觸發喚醒檢測回調
                if (this.onWakeWordDetected) {
                    this.onWakeWordDetected({
                        type: 'automatic',
                        confidence: confidence,
                        trigger: trigger,
                        model: model,
                        timestamp: currentTime
                    });
                }
                
                // 顯示檢測結果
                this.showWakeDetection(model || trigger, confidence);
            }
            
            // 更新信心度顯示（不論是否超過閾值）
            this.updateConfidence(confidence, model || trigger);
            
        } catch (error) {
            console.error('WakeWordManager: 處理喚醒詞檢測失敗', error);
            if (this.onError) {
                this.onError('處理喚醒詞檢測失敗: ' + error.message);
            }
        }
    }
    
    /**
     * 更新信心度顯示
     */
    updateConfidence(confidence, model) {
        this.confidence = confidence;
        this.currentModel = model;
        
        // 更新 UI 顯示
        if (this.confidenceDisplay) {
            if (confidence > 0.01) {
                this.confidenceDisplay.textContent = `${(confidence * 100).toFixed(1)}%`;
                this.confidenceDisplay.parentElement.classList.add('opacity-100');
                this.confidenceDisplay.parentElement.classList.remove('opacity-50');
            } else {
                this.confidenceDisplay.textContent = '待機中';
                this.confidenceDisplay.parentElement.classList.add('opacity-50');
                this.confidenceDisplay.parentElement.classList.remove('opacity-100');
            }
        }
        
        // 觸發信心度更新回調
        if (this.onConfidenceUpdate) {
            this.onConfidenceUpdate({
                confidence: confidence,
                model: model,
                timestamp: Date.now()
            });
        }
    }
    
    /**
     * 顯示喚醒檢測視覺反饋
     */
    showWakeDetection(model, confidence) {
        // 更新狀態指示器
        if (this.statusIndicator) {
            this.statusIndicator.classList.add('wake-detected');
            
            // 3秒後移除檢測狀態
            setTimeout(() => {
                if (this.statusIndicator) {
                    this.statusIndicator.classList.remove('wake-detected');
                }
            }, 3000);
        }
        
        // 更新信心度顯示
        if (this.confidenceDisplay) {
            this.confidenceDisplay.textContent = `${model} (${(confidence * 100).toFixed(1)}%)`;
            this.confidenceDisplay.classList.add('text-yellow-600', 'font-bold');
            
            // 5秒後恢復正常顯示
            setTimeout(() => {
                if (this.confidenceDisplay) {
                    this.confidenceDisplay.classList.remove('text-yellow-600', 'font-bold');
                }
            }, 5000);
        }
    }
    
    /**
     * 添加到歷史記錄
     */
    addToHistory(detection) {
        this.detectionHistory.unshift(detection);
        
        // 限制歷史記錄長度
        if (this.detectionHistory.length > this.maxHistoryLength) {
            this.detectionHistory = this.detectionHistory.slice(0, this.maxHistoryLength);
        }
    }
    
    /**
     * 更新 UI 狀態
     */
    updateUI() {
        // 更新啟用開關
        if (this.enableToggle) {
            this.enableToggle.checked = this.enabled;
        }
        
        // 更新手動喚醒按鈕狀態
        if (this.manualWakeBtn) {
            this.manualWakeBtn.disabled = !this.enabled;
        }
        
        // 更新狀態指示器
        if (this.statusIndicator) {
            if (this.enabled) {
                this.statusIndicator.classList.remove('bg-gray-400');
                this.statusIndicator.classList.add('bg-blue-500');
            } else {
                this.statusIndicator.classList.remove('bg-blue-500', 'wake-detected');
                this.statusIndicator.classList.add('bg-gray-400');
            }
        }
        
        // 更新信心度顯示
        if (this.confidenceDisplay && !this.enabled) {
            this.confidenceDisplay.textContent = '已停用';
            this.confidenceDisplay.parentElement.classList.add('opacity-50');
        }
    }
    
    /**
     * 設置回調函數
     */
    setCallbacks({
        onWakeWordDetected = null,
        onManualWake = null,
        onConfidenceUpdate = null,
        onStateChange = null,
        onError = null
    } = {}) {
        this.onWakeWordDetected = onWakeWordDetected;
        this.onManualWake = onManualWake;
        this.onConfidenceUpdate = onConfidenceUpdate;
        this.onStateChange = onStateChange;
        this.onError = onError;
    }
    
    /**
     * 更新配置
     */
    updateConfig({
        threshold = null,
        cooldownPeriod = null
    } = {}) {
        if (threshold !== null) {
            this.threshold = threshold;
            console.log(`WakeWordManager: 更新閾值為 ${threshold}`);
        }
        
        if (cooldownPeriod !== null) {
            this.cooldownPeriod = cooldownPeriod;
            console.log(`WakeWordManager: 更新冷卻期為 ${cooldownPeriod}ms`);
        }
    }
    
    /**
     * 獲取狀態資訊
     */
    getStatus() {
        return {
            enabled: this.enabled,
            isActive: this.isActive,
            confidence: this.confidence,
            currentModel: this.currentModel,
            threshold: this.threshold,
            cooldownPeriod: this.cooldownPeriod,
            lastTriggerTime: this.lastTriggerTime,
            detectionCount: this.detectionHistory.length
        };
    }
    
    /**
     * 獲取檢測歷史
     */
    getHistory(limit = 10) {
        return this.detectionHistory.slice(0, limit);
    }
    
    /**
     * 清空歷史記錄
     */
    clearHistory() {
        this.detectionHistory = [];
        console.log('WakeWordManager: 檢測歷史已清空');
    }
    
    /**
     * 清理資源
     */
    cleanup() {
        console.log('WakeWordManager: 清理資源...');
        
        // 移除事件監聽器
        if (this.enableToggle) {
            this.enableToggle.removeEventListener('change', this.setEnabled);
        }
        
        if (this.manualWakeBtn) {
            this.manualWakeBtn.removeEventListener('click', this.triggerManualWake);
        }
        
        // 重置狀態
        this.enabled = false;
        this.isActive = false;
        this.confidence = 0.0;
        this.currentModel = null;
        this.detectionHistory = [];
        
        console.log('✓ WakeWordManager: 資源清理完成');
    }
}

// 導出到全域
window.WakeWordManager = WakeWordManager;