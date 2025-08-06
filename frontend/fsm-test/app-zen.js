// Zen 版本的應用程式邏輯 - 精簡版
class FSMTestAppZen {
    constructor() {
        this.fcm = null;
        this.diagram = null;
        this.history = [];
        this.historyIndex = -1;
        this.hookLogs = [];
        this.durationInterval = null;
        
        this.init();
    }
    
    init() {
        // 初始化 FCM
        const initialMode = document.getElementById('modeSelector').value;
        const strategy = createStrategy(initialMode);
        this.fcm = new FCMController(strategy);
        
        // 初始化狀態圖
        this.diagram = new StateDiagramZen('stateDiagram');
        
        // 設置事件監聽器
        this.setupEventListeners();
        
        // 設置 FCM hooks
        this.setupFCMHooks();
        
        // 初始渲染
        this.updateUI();
        this.diagram.render(initialMode, this.fcm.state);
    }
    
    setupEventListeners() {
        // 模式選擇器
        document.getElementById('modeSelector').addEventListener('change', (e) => {
            this.switchMode(e.target.value);
        });
        
        // 事件按鈕
        document.querySelectorAll('.event-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const event = e.target.dataset.event;
                this.triggerEvent(event);
            });
        });
        
        // 歷史導航
        document.getElementById('prevStep').addEventListener('click', () => {
            this.navigateHistory(-1);
        });
        
        document.getElementById('nextStep').addEventListener('click', () => {
            this.navigateHistory(1);
        });
        
        document.getElementById('clearHistory').addEventListener('click', () => {
            this.clearHistory();
        });
        
        // 測試場景按鈕
        document.querySelectorAll('.scenario-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scenario = e.target.dataset.scenario;
                this.runScenario(scenario);
            });
        });
        
        // FCM 狀態變更監聽
        this.fcm.addEventListener((change) => {
            this.onStateChange(change);
        });
    }
    
    setupFCMHooks() {
        // 簡化的 hooks
        this.fcm.addHook(FCMState.RECORDING, 'enter', async (context) => {
            this.addHookLog('🎙️ 開始錄音');
        });
        
        this.fcm.addHook(FCMState.STREAMING, 'enter', async (context) => {
            this.addHookLog('📡 開始串流');
        });
        
        this.fcm.addHook(FCMState.ERROR, 'enter', async (context) => {
            this.addHookLog('⚠️ 錯誤發生');
        });
    }
    
    async triggerEvent(eventName) {
        // 獲取結束觸發原因（如果適用）
        let context = {};
        if (eventName === FCMEvent.END_RECORDING || eventName === FCMEvent.END_STREAMING) {
            const endTrigger = document.querySelector('input[name="endTrigger"]:checked').value;
            context.trigger = endTrigger;
        }
        
        // 觸發事件
        await this.fcm.handleEvent(eventName, context);
    }
    
    onStateChange(change) {
        // 添加到歷史
        this.addToHistory(change);
        
        // 更新 UI
        this.updateUI();
        
        // 更新狀態圖
        const mode = document.getElementById('modeSelector').value;
        this.diagram.render(mode, this.fcm.state);
    }
    
    addToHistory(change) {
        // 如果不在歷史末尾，刪除後續歷史
        if (this.historyIndex < this.history.length - 1) {
            this.history = this.history.slice(0, this.historyIndex + 1);
        }
        
        // 添加新歷史
        this.history.push({
            ...change,
            id: this.history.length
        });
        
        this.historyIndex = this.history.length - 1;
        this.updateHistoryDisplay();
    }
    
    navigateHistory(direction) {
        const newIndex = this.historyIndex + direction;
        
        if (newIndex >= 0 && newIndex < this.history.length) {
            this.historyIndex = newIndex;
            const historyItem = this.history[newIndex];
            
            // 恢復到歷史狀態
            this.fcm.state = historyItem.newState;
            this.updateUI();
            
            // 更新狀態圖
            const mode = document.getElementById('modeSelector').value;
            this.diagram.render(mode, this.fcm.state);
            
            this.updateHistoryDisplay();
        }
    }
    
    clearHistory() {
        this.history = [];
        this.historyIndex = -1;
        this.hookLogs = [];
        this.updateHistoryDisplay();
        document.getElementById('hookLogs').innerHTML = '';
    }
    
    updateHistoryDisplay() {
        const historyList = document.getElementById('historyList');
        historyList.innerHTML = '';
        
        // 只顯示最近的10條
        const recentHistory = this.history.slice(-10);
        
        recentHistory.forEach((item, index) => {
            const actualIndex = this.history.length - 10 + index;
            const div = document.createElement('div');
            div.className = `history-item ${actualIndex === this.historyIndex ? 'active' : ''}`;
            
            const time = new Date(item.timestamp).toLocaleTimeString('zh-TW', { 
                hour: '2-digit', 
                minute: '2-digit', 
                second: '2-digit' 
            });
            
            div.innerHTML = `
                <span class="history-time">${time}</span>
                <span class="history-event">${item.oldState}→${item.newState}</span>
            `;
            
            div.addEventListener('click', () => {
                this.historyIndex = actualIndex;
                this.navigateHistory(0);
            });
            
            historyList.appendChild(div);
        });
        
        // 更新導航按鈕狀態
        document.getElementById('prevStep').disabled = this.historyIndex <= 0;
        document.getElementById('nextStep').disabled = this.historyIndex >= this.history.length - 1;
        
        // 更新歷史數量
        document.getElementById('historyCount').textContent = this.history.length;
    }
    
    switchMode(mode) {
        const strategy = createStrategy(mode);
        this.fcm.setStrategy(strategy);
        this.fcm.reset();
        
        // 清除歷史
        this.clearHistory();
        
        // 更新 UI
        this.updateUI();
        this.diagram.render(mode, this.fcm.state);
    }
    
    updateUI() {
        // 更新當前狀態顯示
        const stateElement = document.getElementById('currentState');
        stateElement.textContent = this.fcm.state;
        stateElement.className = `current-state state-${this.fcm.state.toLowerCase()}`;
        
        // 更新可用事件
        this.updateAvailableEvents();
        
        // 更新事件按鈕狀態
        this.updateEventButtons();
        
        // 開始更新狀態持續時間
        this.startDurationUpdate();
    }
    
    updateAvailableEvents() {
        const availableEvents = this.fcm.getAvailableEvents();
        const container = document.getElementById('availableEvents');
        
        container.innerHTML = availableEvents
            .map(event => `<span class="event-tag">${event}</span>`)
            .join('');
    }
    
    updateEventButtons() {
        const availableEvents = this.fcm.getAvailableEvents();
        
        document.querySelectorAll('.event-btn').forEach(btn => {
            const event = btn.dataset.event;
            btn.disabled = !availableEvents.includes(event);
        });
    }
    
    startDurationUpdate() {
        // 清除舊的定時器
        if (this.durationInterval) {
            clearInterval(this.durationInterval);
        }
        
        // 設置新的定時器
        this.durationInterval = setInterval(() => {
            const duration = Math.floor(this.fcm.getStateDuration() / 1000);
            document.getElementById('stateDuration').textContent = duration;
        }, 100);
    }
    
    addHookLog(message) {
        this.hookLogs.push({
            message,
            timestamp: Date.now()
        });
        
        // 更新 UI
        const hookList = document.getElementById('hookLogs');
        const div = document.createElement('div');
        div.className = 'hook-item';
        div.textContent = `${new Date().toLocaleTimeString('zh-TW', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        })} ${message}`;
        hookList.appendChild(div);
        
        // 保持最新的 5 條
        if (hookList.children.length > 5) {
            hookList.removeChild(hookList.firstChild);
        }
        
        // 自動滾動到底部
        hookList.scrollTop = hookList.scrollHeight;
    }
    
    async runScenario(scenarioName) {
        const scenarios = {
            'batch-flow': [
                { event: FCMEvent.UPLOAD_FILE, delay: 500 },
                { event: FCMEvent.TRANSCRIPTION_DONE, delay: 2000 }
            ],
            'wake-record-flow': [
                { event: FCMEvent.START_LISTENING, delay: 500 },
                { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1500 },
                { event: FCMEvent.START_RECORDING, delay: 500 },
                { event: FCMEvent.END_RECORDING, delay: 3000 },
                { event: FCMEvent.TRANSCRIPTION_DONE, delay: 1500 }
            ],
            'streaming-flow': [
                { event: FCMEvent.START_LISTENING, delay: 500 },
                { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1500 },
                { event: FCMEvent.START_STREAMING, delay: 500 },
                { event: FCMEvent.END_STREAMING, delay: 3000 }
            ],
            'error-recovery': [
                { event: FCMEvent.START_LISTENING, delay: 500 },
                { event: FCMEvent.ERROR, delay: 1000 },
                { event: FCMEvent.RECOVER, delay: 1500 },
                { event: FCMEvent.RESET, delay: 1000 }
            ],
            'vad-timeout': [
                { event: FCMEvent.START_LISTENING, delay: 500 },
                { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1000 },
                { event: FCMEvent.START_RECORDING, delay: 500 },
                { event: FCMEvent.TIMEOUT, delay: 2000 },
                { event: FCMEvent.END_RECORDING, delay: 500 },
                { event: FCMEvent.TRANSCRIPTION_DONE, delay: 1000 }
            ]
        };
        
        const scenario = scenarios[scenarioName];
        if (!scenario) return;
        
        // 重置狀態
        this.fcm.reset();
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // 根據場景設置適當的模式
        if (scenarioName === 'batch-flow') {
            document.getElementById('modeSelector').value = 'batch';
            this.switchMode('batch');
        } else if (scenarioName === 'streaming-flow') {
            document.getElementById('modeSelector').value = 'streaming';
            this.switchMode('streaming');
        } else {
            document.getElementById('modeSelector').value = 'non-streaming';
            this.switchMode('non-streaming');
        }
        
        // 顯示進度
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        progressBar.classList.add('active');
        
        // 執行場景步驟
        for (let i = 0; i < scenario.length; i++) {
            const step = scenario[i];
            const progress = ((i + 1) / scenario.length) * 100;
            
            progressFill.style.width = `${progress}%`;
            progressText.textContent = `步驟 ${i + 1}/${scenario.length}`;
            
            await this.triggerEvent(step.event);
            await new Promise(resolve => setTimeout(resolve, step.delay));
        }
        
        // 隱藏進度
        setTimeout(() => {
            progressBar.classList.remove('active');
        }, 1000);
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new FSMTestAppZen();
});