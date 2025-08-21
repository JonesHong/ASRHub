/**
 * Countdown Timer Manager
 * 管理倒數計時器的視覺化顯示和邏輯控制
 */

class CountdownTimerManager {
    constructor() {
        // 狀態管理
        this.isActive = false;
        this.isPaused = false;
        this.duration = 1.8; // 預設倒數時間（秒）
        this.remainingTime = 0;
        this.startTime = null;
        this.pausedTime = 0;
        
        // UI 元素引用
        this.countdownCircle = null;
        this.countdownProgress = null;
        this.countdownText = null;
        this.countdownLabel = null;
        this.durationSlider = null;
        this.durationValue = null;
        
        // 動畫和視覺效果
        this.animationFrameId = null;
        this.progressCircumference = 283; // 2 * Math.PI * 45 (radius=45)
        
        // 回調函數
        this.onCountdownStart = null;     // 倒數開始回調
        this.onCountdownTick = null;      // 倒數每秒回調
        this.onCountdownFinish = null;    // 倒數完成回調
        this.onCountdownCancel = null;    // 倒數取消回調
        this.onDurationChange = null;     // 時長變化回調
        
        // 音效（可選）
        this.tickSound = null;
        this.finishSound = null;
        
        // 狀態歷史
        this.countdownHistory = [];
        this.maxHistoryLength = 20;
    }
    
    /**
     * 初始化倒數計時器管理器
     */
    initialize() {
        console.log('CountdownTimerManager: 初始化倒數計時器管理器...');
        
        try {
            // 獲取 UI 元素
            this.countdownCircle = document.getElementById('countdownCircle');
            this.countdownProgress = document.getElementById('countdownProgress');
            this.countdownText = document.getElementById('countdownText');
            this.countdownLabel = document.getElementById('countdownLabel');
            this.durationSlider = document.getElementById('countdownDuration');
            this.durationValue = document.getElementById('countdownDurationValue');
            
            // 設置事件監聽器
            this.setupEventListeners();
            
            // 初始化 UI 狀態
            this.updateUI();
            
            console.log('✓ CountdownTimerManager: 倒數計時器管理器初始化完成');
            
        } catch (error) {
            console.error('CountdownTimerManager: 初始化失敗', error);
        }
    }
    
    /**
     * 設置事件監聽器
     */
    setupEventListeners() {
        // 倒數時長滑桿
        if (this.durationSlider) {
            this.durationSlider.addEventListener('input', (e) => {
                const newDuration = parseFloat(e.target.value);
                this.setDuration(newDuration);
            });
        }
    }
    
    /**
     * 設置倒數時長
     */
    setDuration(duration) {
        const oldDuration = this.duration;
        this.duration = duration;
        
        // 更新時長顯示
        if (this.durationValue) {
            this.durationValue.textContent = duration.toFixed(1);
        }
        
        console.log(`CountdownTimerManager: 倒數時長更新為 ${duration} 秒`);
        
        // 如果正在倒數，根據新時長調整
        if (this.isActive && !this.isPaused) {
            const elapsed = (Date.now() - this.startTime) / 1000;
            this.remainingTime = Math.max(0, this.duration - elapsed);
        }
        
        // 觸發時長變化回調
        if (this.onDurationChange && oldDuration !== duration) {
            this.onDurationChange({
                oldDuration: oldDuration,
                newDuration: duration,
                timestamp: Date.now()
            });
        }
        
        this.updateDisplay();
    }
    
    /**
     * 開始倒數計時
     */
    startCountdown(customDuration = null) {
        try {
            // 如果已經在倒數中，先停止
            if (this.isActive) {
                this.cancelCountdown();
            }
            
            // 設置倒數參數
            const duration = customDuration || this.duration;
            this.duration = duration;
            this.remainingTime = duration;
            this.startTime = Date.now();
            this.pausedTime = 0;
            this.isActive = true;
            this.isPaused = false;
            
            console.log(`✓ CountdownTimerManager: 開始倒數計時 ${duration} 秒`);
            
            // 記錄到歷史
            this.addToHistory({
                action: 'start',
                duration: duration,
                timestamp: Date.now()
            });
            
            // 觸發開始回調
            if (this.onCountdownStart) {
                this.onCountdownStart({
                    duration: duration,
                    timestamp: Date.now()
                });
            }
            
            // 開始動畫循環
            this.startAnimation();
            
            // 更新 UI 狀態
            this.updateUI();
            
        } catch (error) {
            console.error('CountdownTimerManager: 開始倒數失敗', error);
        }
    }
    
    /**
     * 暫停倒數計時
     */
    pauseCountdown() {
        if (!this.isActive || this.isPaused) {
            console.log('CountdownTimerManager: 倒數計時未啟動或已暫停');
            return;
        }
        
        this.isPaused = true;
        this.pausedTime = Date.now();
        
        console.log('CountdownTimerManager: 倒數計時已暫停');
        
        // 停止動畫
        this.stopAnimation();
        
        // 記錄到歷史
        this.addToHistory({
            action: 'pause',
            remainingTime: this.remainingTime,
            timestamp: Date.now()
        });
        
        this.updateUI();
    }
    
    /**
     * 恢復倒數計時
     */
    resumeCountdown() {
        if (!this.isActive || !this.isPaused) {
            console.log('CountdownTimerManager: 倒數計時未暫停');
            return;
        }
        
        // 調整開始時間以考慮暫停時間
        const pauseDuration = Date.now() - this.pausedTime;
        this.startTime += pauseDuration;
        this.isPaused = false;
        this.pausedTime = 0;
        
        console.log('CountdownTimerManager: 倒數計時已恢復');
        
        // 記錄到歷史
        this.addToHistory({
            action: 'resume',
            remainingTime: this.remainingTime,
            timestamp: Date.now()
        });
        
        // 重新開始動畫
        this.startAnimation();
        
        this.updateUI();
    }
    
    /**
     * 取消倒數計時
     */
    cancelCountdown(reason = 'manual') {
        if (!this.isActive) {
            console.log('CountdownTimerManager: 沒有進行中的倒數計時');
            return;
        }
        
        console.log(`CountdownTimerManager: 倒數計時已取消 (原因: ${reason})`);
        
        // 記錄到歷史
        this.addToHistory({
            action: 'cancel',
            reason: reason,
            remainingTime: this.remainingTime,
            timestamp: Date.now()
        });
        
        // 觸發取消回調
        if (this.onCountdownCancel) {
            this.onCountdownCancel({
                reason: reason,
                remainingTime: this.remainingTime,
                timestamp: Date.now()
            });
        }
        
        // 重置狀態
        this.resetState();
    }
    
    /**
     * 完成倒數計時
     */
    finishCountdown() {
        if (!this.isActive) {
            return;
        }
        
        console.log('✓ CountdownTimerManager: 倒數計時完成');
        
        // 記錄到歷史
        this.addToHistory({
            action: 'finish',
            duration: this.duration,
            timestamp: Date.now()
        });
        
        // 觸發完成回調
        if (this.onCountdownFinish) {
            this.onCountdownFinish({
                duration: this.duration,
                timestamp: Date.now()
            });
        }
        
        // 播放完成音效（如果有）
        if (this.finishSound) {
            this.finishSound.play().catch(e => {
                console.log('CountdownTimerManager: 無法播放完成音效', e);
            });
        }
        
        // 重置狀態
        this.resetState();
    }
    
    /**
     * 重置狀態
     */
    resetState() {
        this.isActive = false;
        this.isPaused = false;
        this.remainingTime = 0;
        this.startTime = null;
        this.pausedTime = 0;
        
        // 停止動畫
        this.stopAnimation();
        
        // 更新 UI
        this.updateUI();
    }
    
    /**
     * 開始動畫循環
     */
    startAnimation() {
        const animate = () => {
            if (!this.isActive || this.isPaused) {
                return;
            }
            
            // 計算剩餘時間
            const elapsed = (Date.now() - this.startTime) / 1000;
            this.remainingTime = Math.max(0, this.duration - elapsed);
            
            // 更新顯示
            this.updateDisplay();
            
            // 檢查是否完成
            if (this.remainingTime <= 0) {
                this.finishCountdown();
                return;
            }
            
            // 每秒觸發 tick 回調
            const currentSecond = Math.floor(this.remainingTime);
            if (this.lastTickSecond !== currentSecond) {
                this.lastTickSecond = currentSecond;
                
                if (this.onCountdownTick) {
                    this.onCountdownTick({
                        remainingTime: this.remainingTime,
                        currentSecond: currentSecond,
                        timestamp: Date.now()
                    });
                }
                
                // 播放 tick 音效（最後3秒）
                if (this.tickSound && currentSecond <= 3 && currentSecond > 0) {
                    this.tickSound.play().catch(e => {
                        console.log('CountdownTimerManager: 無法播放 tick 音效', e);
                    });
                }
            }
            
            this.animationFrameId = requestAnimationFrame(animate);
        };
        
        this.lastTickSecond = -1;
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
     * 更新顯示
     */
    updateDisplay() {
        if (!this.countdownText || !this.countdownProgress) {
            return;
        }
        
        if (this.isActive) {
            // 更新倒數文字
            this.countdownText.textContent = this.remainingTime.toFixed(1);
            
            // 計算進度（剩餘時間的反比）
            const progress = this.duration > 0 ? 
                (this.duration - this.remainingTime) / this.duration : 0;
            
            // 更新進度圓環
            const offset = this.progressCircumference * (1 - progress);
            this.countdownProgress.style.strokeDashoffset = offset;
            
            // 根據剩餘時間調整顏色
            if (this.remainingTime <= 1.0) {
                // 最後1秒：紅色警告
                this.countdownProgress.classList.remove('text-orange-500');
                this.countdownProgress.classList.add('text-red-500');
                this.countdownText.classList.add('text-red-500');
            } else if (this.remainingTime <= 3.0) {
                // 最後3秒：橙色警告
                this.countdownProgress.classList.remove('text-red-500');
                this.countdownProgress.classList.add('text-orange-500');
                this.countdownText.classList.remove('text-red-500');
            } else {
                // 正常狀態
                this.countdownProgress.classList.remove('text-red-500', 'text-orange-500');
                this.countdownText.classList.remove('text-red-500');
            }
            
        } else {
            // 未啟動狀態
            this.countdownText.textContent = '--';
            this.countdownProgress.style.strokeDashoffset = this.progressCircumference;
            this.countdownProgress.classList.remove('text-red-500', 'text-orange-500');
            this.countdownText.classList.remove('text-red-500');
        }
    }
    
    /**
     * 更新 UI 狀態
     */
    updateUI() {
        // 更新時長滑桿
        if (this.durationSlider) {
            this.durationSlider.value = this.duration;
        }
        
        if (this.durationValue) {
            this.durationValue.textContent = this.duration.toFixed(1);
        }
        
        // 更新標籤
        if (this.countdownLabel) {
            if (this.isActive) {
                if (this.isPaused) {
                    this.countdownLabel.textContent = '倒數已暫停';
                } else {
                    this.countdownLabel.textContent = '靜音倒數中...';
                }
            } else {
                this.countdownLabel.textContent = '靜音計時器';
            }
        }
        
        // 更新圓環狀態類別
        if (this.countdownCircle) {
            if (this.isActive && !this.isPaused) {
                this.countdownCircle.classList.add('countdown-active');
            } else {
                this.countdownCircle.classList.remove('countdown-active');
            }
            
            if (this.remainingTime <= 1.0) {
                this.countdownCircle.classList.add('countdown-warning');
            } else {
                this.countdownCircle.classList.remove('countdown-warning');
            }
        }
        
        // 更新顯示
        this.updateDisplay();
    }
    
    /**
     * 處理來自後端的倒數事件
     */
    handleCountdownEvent(event) {
        try {
            const { type, duration, reason } = event;
            
            switch (type) {
                case 'countdown_started':
                    this.startCountdown(duration);
                    break;
                    
                case 'countdown_cancelled':
                    this.cancelCountdown(reason);
                    break;
                    
                case 'countdown_finished':
                    this.finishCountdown();
                    break;
                    
                default:
                    console.log(`CountdownTimerManager: 未知的倒數事件類型: ${type}`);
            }
            
        } catch (error) {
            console.error('CountdownTimerManager: 處理倒數事件失敗', error);
        }
    }
    
    /**
     * 添加到歷史記錄
     */
    addToHistory(entry) {
        this.countdownHistory.unshift(entry);
        
        // 限制歷史記錄長度
        if (this.countdownHistory.length > this.maxHistoryLength) {
            this.countdownHistory = this.countdownHistory.slice(0, this.maxHistoryLength);
        }
    }
    
    /**
     * 設置回調函數
     */
    setCallbacks({
        onCountdownStart = null,
        onCountdownTick = null,
        onCountdownFinish = null,
        onCountdownCancel = null,
        onDurationChange = null
    } = {}) {
        this.onCountdownStart = onCountdownStart;
        this.onCountdownTick = onCountdownTick;
        this.onCountdownFinish = onCountdownFinish;
        this.onCountdownCancel = onCountdownCancel;
        this.onDurationChange = onDurationChange;
    }
    
    /**
     * 設置音效
     */
    setSounds({
        tickSound = null,
        finishSound = null
    } = {}) {
        this.tickSound = tickSound;
        this.finishSound = finishSound;
    }
    
    /**
     * 獲取狀態資訊
     */
    getStatus() {
        return {
            isActive: this.isActive,
            isPaused: this.isPaused,
            duration: this.duration,
            remainingTime: this.remainingTime,
            startTime: this.startTime,
            historyLength: this.countdownHistory.length
        };
    }
    
    /**
     * 獲取歷史記錄
     */
    getHistory(limit = 10) {
        return this.countdownHistory.slice(0, limit);
    }
    
    /**
     * 清空歷史記錄
     */
    clearHistory() {
        this.countdownHistory = [];
        console.log('CountdownTimerManager: 倒數歷史已清空');
    }
    
    /**
     * 清理資源
     */
    cleanup() {
        console.log('CountdownTimerManager: 清理資源...');
        
        // 停止倒數和動畫
        this.cancelCountdown('cleanup');
        this.stopAnimation();
        
        // 移除事件監聽器
        if (this.durationSlider) {
            this.durationSlider.removeEventListener('input', this.setDuration);
        }
        
        // 清空歷史
        this.clearHistory();
        
        console.log('✓ CountdownTimerManager: 資源清理完成');
    }
}

// 導出到全域
window.CountdownTimerManager = CountdownTimerManager;