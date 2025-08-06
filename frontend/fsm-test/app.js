// 應用程式主邏輯
class FSMTestApp {
    constructor() {
        this.fcm = null;
        this.diagram = null;
        this.history = [];
        this.historyIndex = -1;
        this.hookLogs = [];
        this.scenarios = {};
        this.durationInterval = null;
        
        this.init();
    }
    
    init() {
        // 初始化 FCM
        const initialMode = document.getElementById('modeSelector').value;
        const strategy = createStrategy(initialMode);
        this.fcm = new FCMController(strategy);
        
        // 初始化狀態圖
        this.diagram = new StateDiagram('stateDiagram');
        
        // 設置事件監聽器
        this.setupEventListeners();
        
        // 設置 FCM hooks
        this.setupFCMHooks();
        
        // 定義測試場景
        this.defineScenarios();
        
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
        
        // 刷新圖表（如果按鈕存在）
        const refreshBtn = document.getElementById('refreshDiagram');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                const mode = document.getElementById('modeSelector').value;
                this.diagram.render(mode, this.fcm.state);
            });
        }
        
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
        // 為每個狀態添加進入和退出 hooks
        Object.keys(FCMState).forEach(state => {
            this.fcm.addHook(state, 'enter', async (context) => {
                this.logHook(`進入 ${state}`, context);
            });
            
            this.fcm.addHook(state, 'exit', async (context) => {
                this.logHook(`退出 ${state}`, context);
            });
        });
        
        // 特定狀態的特殊 hooks
        this.fcm.addHook(FCMState.RECORDING, 'enter', async (context) => {
            this.logHook('🎙️ 開始錄音', context);
        });
        
        this.fcm.addHook(FCMState.STREAMING, 'enter', async (context) => {
            this.logHook('📡 開始串流', context);
        });
        
        this.fcm.addHook(FCMState.ERROR, 'enter', async (context) => {
            this.logHook('⚠️ 錯誤發生', context);
        });
    }
    
    defineScenarios() {
        // 批次處理完整流程
        this.scenarios['batch-flow'] = [
            { event: FCMEvent.UPLOAD_FILE, delay: 500, description: '上傳檔案' },
            { event: FCMEvent.TRANSCRIPTION_DONE, delay: 2000, description: '轉譯完成' }
        ];
        
        // 喚醒詞 → 錄音流程
        this.scenarios['wake-record-flow'] = [
            { event: FCMEvent.START_LISTENING, delay: 500, description: '開始監聽' },
            { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1500, description: '檢測到喚醒詞' },
            { event: FCMEvent.START_RECORDING, delay: 500, description: '開始錄音' },
            { event: FCMEvent.END_RECORDING, delay: 3000, description: '結束錄音' },
            { event: FCMEvent.TRANSCRIPTION_DONE, delay: 1500, description: '轉譯完成' }
        ];
        
        // 串流處理流程
        this.scenarios['streaming-flow'] = [
            { event: FCMEvent.START_LISTENING, delay: 500, description: '開始監聽' },
            { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1500, description: '檢測到喚醒詞' },
            { event: FCMEvent.START_STREAMING, delay: 500, description: '開始串流' },
            { event: FCMEvent.END_STREAMING, delay: 3000, description: '結束串流' }
        ];
        
        // 錯誤恢復流程
        this.scenarios['error-recovery'] = [
            { event: FCMEvent.START_LISTENING, delay: 500, description: '開始監聽' },
            { event: FCMEvent.ERROR, delay: 1000, description: '發生錯誤' },
            { event: FCMEvent.RECOVER, delay: 1500, description: '嘗試恢復' },
            { event: FCMEvent.RESET, delay: 1000, description: '重置系統' }
        ];
        
        // VAD 超時流程
        this.scenarios['vad-timeout'] = [
            { event: FCMEvent.START_LISTENING, delay: 500, description: '開始監聽' },
            { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1000, description: '檢測到喚醒詞' },
            { event: FCMEvent.START_RECORDING, delay: 500, description: '開始錄音' },
            { event: FCMEvent.TIMEOUT, delay: 2000, description: 'VAD 超時' },
            { event: FCMEvent.END_RECORDING, delay: 500, description: '超時結束錄音' },
            { event: FCMEvent.TRANSCRIPTION_DONE, delay: 1000, description: '轉譯完成' }
        ];
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
        
        this.history.forEach((item, index) => {
            const div = document.createElement('div');
            div.className = `history-item ${index === this.historyIndex ? 'active' : ''}`;
            
            const time = new Date(item.timestamp).toLocaleTimeString();
            const trigger = item.context?.trigger ? ` (${item.context.trigger})` : '';
            
            div.innerHTML = `
                <span class="history-time">${time}</span>
                <span class="history-transition">
                    ${item.oldState} → ${item.newState}
                </span>
                <span class="history-event">${item.event}${trigger}</span>
            `;
            
            div.addEventListener('click', () => {
                this.historyIndex = index;
                this.navigateHistory(0);
            });
            
            historyList.appendChild(div);
        });
        
        // 更新導航按鈕狀態
        document.getElementById('prevStep').disabled = this.historyIndex <= 0;
        document.getElementById('nextStep').disabled = this.historyIndex >= this.history.length - 1;
        
        // 更新位置顯示
        const historyCountElement = document.getElementById('historyCount');
        if (historyCountElement) {
            historyCountElement.textContent = this.history.length;
        }
    }
    
    switchMode(mode) {
        const strategy = createStrategy(mode);
        this.fcm.setStrategy(strategy);
        this.fcm.reset();
        
        // 更新圖表模式標籤（如果元素存在）
        const diagramModeElement = document.getElementById('diagramMode');
        if (diagramModeElement) {
            const modeLabels = {
                'batch': '批次處理',
                'non-streaming': '非串流實時',
                'streaming': '串流實時'
            };
            diagramModeElement.textContent = modeLabels[mode];
        }
        
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
        stateElement.className = `state-badge state-${this.fcm.state.toLowerCase()}`;
        
        // 更新可用事件
        this.updateAvailableEvents();
        
        // 更新狀態描述
        this.updateStateDescription();
        
        // 更新事件按鈕狀態
        this.updateEventButtons();
        
        // 開始更新狀態持續時間
        this.startDurationUpdate();
    }
    
    updateAvailableEvents() {
        const availableEvents = this.fcm.getAvailableEvents();
        const listElement = document.getElementById('availableEvents');
        
        listElement.innerHTML = availableEvents
            .map(event => `<span style="
                padding: 4px 8px;
                background: var(--background);
                border-radius: 4px;
                font-size: 14px;
                color: var(--text-secondary);
                display: inline-block;
            ">${event}</span>`)
            .join('');
    }
    
    updateStateDescription() {
        const descriptionElement = document.getElementById('stateDescription');
        if (descriptionElement) {
            const description = StateDescriptions[this.fcm.state] || '未知狀態';
            descriptionElement.textContent = description;
        }
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
            const durationElement = document.getElementById('stateDuration');
            if (durationElement) {
                const duration = Math.floor(this.fcm.getStateDuration() / 1000);
                durationElement.textContent = duration;
            }
        }, 100);
    }
    
    logHook(message, context) {
        const log = {
            message,
            context,
            timestamp: Date.now()
        };
        
        this.hookLogs.push(log);
        
        // 更新 UI
        const hookList = document.getElementById('hookLogs');
        const li = document.createElement('li');
        li.textContent = `${new Date(log.timestamp).toLocaleTimeString()} - ${message}`;
        hookList.appendChild(li);
        
        // 保持最新的 10 條
        if (hookList.children.length > 10) {
            hookList.removeChild(hookList.firstChild);
        }
    }
    
    async runScenario(scenarioName) {
        const scenario = this.scenarios[scenarioName];
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
        const progressDiv = document.getElementById('scenarioProgress');
        if (!progressDiv) {
            console.warn('Progress bar element not found');
            return;
        }
        const progressFill = progressDiv.querySelector('.progress-fill');
        const progressText = progressDiv.querySelector('.progress-text');
        progressDiv.style.display = 'flex';
        
        // 執行場景步驟
        for (let i = 0; i < scenario.length; i++) {
            const step = scenario[i];
            const progress = ((i + 1) / scenario.length) * 100;
            
            progressFill.style.width = `${progress}%`;
            progressText.textContent = `步驟 ${i + 1}/${scenario.length}: ${step.description}`;
            
            await this.triggerEvent(step.event);
            await new Promise(resolve => setTimeout(resolve, step.delay));
        }
        
        // 隱藏進度
        setTimeout(() => {
            progressDiv.style.display = 'none';
        }, 1000);
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.app = new FSMTestApp();
        console.log('FSM Test App initialized successfully');
    } catch (error) {
        console.error('Failed to initialize FSM Test App:', error);
    }
    
    // 初始化暗色模式切換
    const darkModeToggle = document.getElementById('darkModeToggle');
    const body = document.body;
    
    if (darkModeToggle) {
        console.log('Dark mode toggle button found');
        
        // 檢查本地存儲的主題設定
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark') {
            body.classList.remove('light-mode');
            body.classList.add('dark-mode');
            darkModeToggle.textContent = '☀️';
        }
        
        darkModeToggle.addEventListener('click', () => {
            console.log('Dark mode toggle clicked');
            if (body.classList.contains('dark-mode')) {
                body.classList.remove('dark-mode');
                body.classList.add('light-mode');
                darkModeToggle.textContent = '🌙';
                localStorage.setItem('theme', 'light');
                console.log('Switched to light mode');
            } else {
                body.classList.remove('light-mode');
                body.classList.add('dark-mode');
                darkModeToggle.textContent = '☀️';
                localStorage.setItem('theme', 'dark');
                console.log('Switched to dark mode');
            }
        });
    } else {
        console.warn('Dark mode toggle button not found');
    }
});