// 🧘 Zen 版本 - 簡潔、專注、可靠
// 應用程式主邏輯 - 最小化複雜度，最大化穩定性
// Version: 2.0

console.log('===== app.js 載入開始 =====');
console.log('時間戳:', new Date().toISOString());

class FSMTestApp {
    constructor() {
        console.log('🚀 FSMTestApp 啟動');
        this.fcm = null;
        this.diagram = null;
        this.history = [];
        this.historyIndex = -1;
        this.hookLogs = [];
        this.scenarios = {};
        this.durationInterval = null;

        // 延遲初始化，確保 DOM 完全載入
        setTimeout(() => this.init(), 100);
    }

    init() {
        console.log('📦 開始初始化...');

        try {
            // 步驟 1: 驗證環境
            if (!this.validateEnvironment()) {
                console.error('❌ 環境驗證失敗');
                return;
            }

            // 步驟 2: 生成 UI 元素
            this.generateUIElements();

            // 步驟 3: 初始化核心組件
            this.initializeCore();

            // 步驟 4: 設置事件監聽
            this.setupEventListeners();

            // 步驟 5: 設置 FCM hooks
            this.setupFCMHooks();

            // 步驟 6: 定義測試場景
            this.defineScenarios();

            // 步驟 7: 初始渲染
            this.updateUI();

            console.log('✅ 初始化完成');
        } catch (error) {
            console.error('❌ 初始化錯誤:', error);
            this.showError('初始化失敗: ' + error.message);
        }
    }

    validateEnvironment() {
        console.log('🔍 驗證環境...');

        const required = {
            'FCMState': typeof FCMState !== 'undefined',
            'FCMEvent': typeof FCMEvent !== 'undefined',
            'FCMEndTrigger': typeof FCMEndTrigger !== 'undefined',
            'FCMController': typeof FCMController !== 'undefined',
            'createStrategy': typeof createStrategy !== 'undefined'
        };

        let allValid = true;
        for (const [name, exists] of Object.entries(required)) {
            console.log(`  ${name}: ${exists ? '✓' : '✗'}`);
            if (!exists) allValid = false;
        }

        // 檢查 DOM 元素
        const elements = [
            'modeSelector',
            'eventButtonsContainer',
            'endTriggerContainer',
            'currentState',
            'availableEvents',
            'historyList'
        ];

        console.log('🔍 檢查 DOM 元素...');
        for (const id of elements) {
            const exists = document.getElementById(id) !== null;
            console.log(`  #${id}: ${exists ? '✓' : '✗'}`);
        }

        return allValid;
    }

    generateUIElements() {
        console.log('🎨 生成 UI 元素...');

        // 生成事件按鈕
        this.generateEventButtons();

        // 生成結束觸發選項
        this.generateEndTriggerOptions();
    }

    generateEventButtons() {
        const container = document.getElementById('eventButtonsContainer');
        if (!container) {
            console.warn('⚠️ 找不到事件按鈕容器');
            return;
        }

        // 使用 fsm.js 中定義的 EventLabels

        container.innerHTML = '';
        let count = 0;

        Object.keys(FCMEvent).forEach(key => {
            const eventName = FCMEvent[key];
            const button = document.createElement('button');
            button.className = 'event-btn';

            // 特殊樣式
            if (eventName === 'ERROR') button.classList.add('danger');
            if (eventName === 'RESET') button.classList.add('primary');

            button.dataset.event = eventName;
            button.textContent = EventLabels[key] || key;

            container.appendChild(button);
            count++;
        });

        console.log(`  ✓ 生成 ${count} 個事件按鈕`);
    }

    generateEndTriggerOptions() {
        const container = document.getElementById('endTriggerContainer');
        if (!container) {
            console.warn('⚠️ 找不到結束觸發容器');
            return;
        }

        // 使用 fsm.js 中定義的 TriggerLabels

        container.innerHTML = '';
        let count = 0;

        Object.keys(FCMEndTrigger).forEach((key, index) => {
            const triggerValue = FCMEndTrigger[key];

            const label = document.createElement('label');
            label.className = 'trigger-option';

            const input = document.createElement('input');
            input.type = 'radio';
            input.name = 'endTrigger';
            input.value = triggerValue;
            if (index === 0) input.checked = true;

            const span = document.createElement('span');
            span.textContent = TriggerLabels[key] || key;

            label.appendChild(input);
            label.appendChild(span);
            container.appendChild(label);
            count++;
        });

        console.log(`  ✓ 生成 ${count} 個觸發選項`);
    }

    initializeCore() {
        console.log('⚙️ 初始化核心組件...');

        // 初始化 FCM
        const initialMode = document.getElementById('modeSelector')?.value || 'batch';
        const strategy = createStrategy(initialMode);
        this.fcm = new FCMController(strategy);
        console.log('  ✓ FCM 控制器已創建');

        // 初始化狀態圖（安全模式）
        try {
            if (typeof StateDiagram !== 'undefined') {
                this.diagram = new StateDiagram('stateDiagram');
                this.diagram.render(initialMode, this.fcm.state);
                console.log('  ✓ 狀態圖已創建');
            } else {
                console.warn('  ⚠️ StateDiagram 未定義，跳過圖表');
                this.diagram = { render: () => { } };
            }
        } catch (error) {
            console.warn('  ⚠️ 狀態圖初始化失敗:', error.message);
            this.diagram = { render: () => { } };
        }
    }

    setupEventListeners() {
        console.log('🎯 設置事件監聽器...');

        // 模式選擇器
        const modeSelector = document.getElementById('modeSelector');
        if (modeSelector) {
            modeSelector.addEventListener('change', (e) => {
                this.switchMode(e.target.value);
            });
        }

        // 事件按鈕（使用事件委託）
        const eventContainer = document.getElementById('eventButtonsContainer');
        if (eventContainer) {
            eventContainer.addEventListener('click', (e) => {
                if (e.target.classList.contains('event-btn')) {
                    const event = e.target.dataset.event;
                    this.triggerEvent(event);
                }
            });
        }

        // 歷史導航
        const prevBtn = document.getElementById('prevStep');
        const nextBtn = document.getElementById('nextStep');
        const clearBtn = document.getElementById('clearHistory');

        if (prevBtn) prevBtn.addEventListener('click', () => this.navigateHistory(-1));
        if (nextBtn) nextBtn.addEventListener('click', () => this.navigateHistory(1));
        if (clearBtn) clearBtn.addEventListener('click', () => this.clearHistory());

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

        console.log('  ✓ 事件監聽器設置完成');
    }

    setupFCMHooks() {
        // 簡化的 hooks 設置
        Object.keys(FCMState).forEach(state => {
            this.fcm.addHook(state, 'enter', async (context) => {
                this.logHook(`進入 ${state}`, context);
            });
        });
    }

    defineScenarios() {
        // 批次處理流程
        this.scenarios['batch-flow'] = [
            { event: FCMEvent.UPLOAD_FILE, delay: 1000, description: '上傳檔案' },
            { event: FCMEvent.UPLOAD_DONE, delay: 1500, description: '上傳完成' },
            { event: FCMEvent.BEGIN_TRANSCRIPTION, delay: 1500, description: '開始轉譯' },
            { event: FCMEvent.TRANSCRIPTION_DONE, delay: 2000, description: '轉譯完成' }
        ];
        
        // 喚醒→錄音流程 (非串流模式)
        this.scenarios['wake-record-flow'] = [
            { event: FCMEvent.START_LISTENING, delay: 1000, description: '開始監聽' },
            { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1500, description: '檢測到喚醒詞' },
            { event: FCMEvent.START_RECORDING, delay: 1000, description: '開始錄音' },
            { event: FCMEvent.END_RECORDING, delay: 3000, description: '結束錄音' },
            { event: FCMEvent.TRANSCRIPTION_DONE, delay: 1500, description: '轉譯完成' }
        ];
        
        // 串流處理流程
        this.scenarios['streaming-flow'] = [
            { event: FCMEvent.START_LISTENING, delay: 1000, description: '開始監聽' },
            { event: FCMEvent.WAKE_WORD_TRIGGERED, delay: 1500, description: '檢測到喚醒詞' },
            { event: FCMEvent.START_STREAMING, delay: 1000, description: '開始串流' },
            { event: FCMEvent.END_STREAMING, delay: 3000, description: '結束串流' }
        ];
        
        // 錯誤恢復流程
        this.scenarios['error-recovery'] = [
            { event: FCMEvent.START_LISTENING, delay: 1000, description: '開始監聽' },
            { event: FCMEvent.ERROR, delay: 1500, description: '發生錯誤' },
            { event: FCMEvent.RECOVER, delay: 1500, description: '嘗試恢復' },
            { event: FCMEvent.RESET, delay: 1500, description: '重置系統' }
        ];
        
    }

    async triggerEvent(eventName) {
        console.log('🔔 觸發事件:', eventName);

        let context = {};
        if (eventName === FCMEvent.END_RECORDING || eventName === FCMEvent.END_STREAMING) {
            const trigger = document.querySelector('input[name="endTrigger"]:checked');
            if (trigger) context.trigger = trigger.value;
        }

        await this.fcm.handleEvent(eventName, context);
    }

    onStateChange(change) {
        this.addToHistory(change);
        this.updateUI();

        // 安全地更新圖表
        if (this.diagram && this.diagram.render) {
            try {
                const mode = document.getElementById('modeSelector')?.value || 'batch';
                this.diagram.render(mode, this.fcm.state);
            } catch (error) {
                console.warn('圖表更新失敗:', error.message);
            }
        }
    }

    addToHistory(change) {
        if (this.historyIndex < this.history.length - 1) {
            this.history = this.history.slice(0, this.historyIndex + 1);
        }

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

            this.fcm.state = historyItem.newState;
            this.updateUI();

            if (this.diagram && this.diagram.render) {
                const mode = document.getElementById('modeSelector')?.value || 'batch';
                this.diagram.render(mode, this.fcm.state);
            }

            this.updateHistoryDisplay();
        }
    }

    clearHistory() {
        this.history = [];
        this.historyIndex = -1;
        this.hookLogs = [];
        this.updateHistoryDisplay();

        const hookLogs = document.getElementById('hookLogs');
        if (hookLogs) hookLogs.innerHTML = '';
    }

    updateHistoryDisplay() {
        const historyList = document.getElementById('historyList');
        if (!historyList) return;

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
        const prevBtn = document.getElementById('prevStep');
        const nextBtn = document.getElementById('nextStep');

        if (prevBtn) prevBtn.disabled = this.historyIndex <= 0;
        if (nextBtn) nextBtn.disabled = this.historyIndex >= this.history.length - 1;

        // 更新計數
        const historyCount = document.getElementById('historyCount');
        if (historyCount) historyCount.textContent = this.history.length;
    }

    switchMode(mode) {
        console.log('🔄 切換模式:', mode);

        const strategy = createStrategy(mode);
        this.fcm.setStrategy(strategy);
        this.fcm.reset();

        this.clearHistory();
        this.updateUI();

        if (this.diagram && this.diagram.render) {
            this.diagram.render(mode, this.fcm.state);
        }
    }

    updateUI() {
        // 更新當前狀態
        const stateElement = document.getElementById('currentState');
        if (stateElement) {
            stateElement.textContent = this.fcm.state;
            stateElement.className = `current-state state-${this.fcm.state.toLowerCase()}`;
        }

        // 更新可用事件
        this.updateAvailableEvents();

        // 更新事件按鈕狀態
        this.updateEventButtons();

        // 開始更新持續時間
        this.startDurationUpdate();
    }

    updateAvailableEvents() {
        const container = document.getElementById('availableEvents');
        if (!container) return;

        const availableEvents = this.fcm.getAvailableEvents();

        container.innerHTML = availableEvents
            .map(event => `<span class="available-event">${event}</span>`)
            .join(' ');
    }

    updateEventButtons() {
        const availableEvents = this.fcm.getAvailableEvents();
        const container = document.getElementById('eventButtonsContainer');

        if (!container) return;

        container.querySelectorAll('.event-btn').forEach(btn => {
            const event = btn.dataset.event;
            btn.disabled = !availableEvents.includes(event);
        });
    }

    startDurationUpdate() {
        if (this.durationInterval) {
            clearInterval(this.durationInterval);
        }

        this.durationInterval = setInterval(() => {
            const durationElement = document.getElementById('stateDuration');
            if (durationElement) {
                const duration = Math.floor(this.fcm.getStateDuration() / 1500);
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

        const hookList = document.getElementById('hookLogs');
        if (!hookList) return;

        const div = document.createElement('div');
        div.className = 'hook-log';
        div.textContent = `${new Date(log.timestamp).toLocaleTimeString()} - ${message}`;
        hookList.appendChild(div);

        // 保持最新的 10 條
        if (hookList.children.length > 10) {
            hookList.removeChild(hookList.firstChild);
        }
    }

    async runScenario(scenarioName) {
        const scenario = this.scenarios[scenarioName];
        if (!scenario) {
            console.warn('⚠️ 找不到場景:', scenarioName);
            return;
        }

        console.log('🎬 執行場景:', scenarioName);
        console.log('🔄 重置狀態並切換模式...');
        
        // 根據場景設置適當的模式
        let targetMode = 'non-streaming'; // 預設
        
        if (scenarioName === 'batch-flow') {
            targetMode = 'batch';
        } else if (scenarioName === 'streaming-flow') {
            targetMode = 'streaming';
        } else if (scenarioName === 'wake-record-flow' || scenarioName === 'vad-timeout') {
            targetMode = 'non-streaming';
        }
        
        // 切換到正確的模式
        const modeSelector = document.getElementById('modeSelector');
        if (modeSelector && modeSelector.value !== targetMode) {
            console.log(`  🔄 切換模式: ${modeSelector.value} → ${targetMode}`);
            modeSelector.value = targetMode;
            this.switchMode(targetMode);
        }
        
        // 重置狀態
        this.fcm.reset();
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // 顯示進度
        const progressDiv = document.getElementById('scenarioProgress');
        if (progressDiv) {
            const progressFill = progressDiv.querySelector('.progress-fill');
            const progressText = progressDiv.querySelector('.progress-text');
            progressDiv.style.display = 'flex';
            
            // 執行步驟
            for (let i = 0; i < scenario.length; i++) {
                const step = scenario[i];
                const progress = ((i + 1) / scenario.length) * 100;
                
                console.log(`  🎆 步驟 ${i + 1}/${scenario.length}: ${step.description}`);
                
                if (progressFill) progressFill.style.width = `${progress}%`;
                if (progressText) progressText.textContent = `步驟 ${i + 1}/${scenario.length}: ${step.description}`;
                
                await this.triggerEvent(step.event);
                await new Promise(resolve => setTimeout(resolve, step.delay));
            }
            
            // 隱藏進度
            setTimeout(() => {
                progressDiv.style.display = 'none';
            }, 1500);
        } else {
            // 沒有進度欄的簡單執行
            for (const step of scenario) {
                console.log(`  🎆 ${step.description}`);
                await this.triggerEvent(step.event);
                await new Promise(resolve => setTimeout(resolve, step.delay));
            }
        }

        console.log('  ✓ 場景執行完成');
    }

    showError(message) {
        console.error('❌', message);
        // 可以在這裡添加 UI 錯誤顯示
    }
}

// 🚀 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOM 載入完成 - app.js v2.0');
    console.log('檢查全域變數:');
    console.log('  FCMEvent:', typeof FCMEvent);
    console.log('  FCMEndTrigger:', typeof FCMEndTrigger);
    console.log('  EventLabels:', typeof EventLabels);
    console.log('  TriggerLabels:', typeof TriggerLabels);

    // 給一點時間確保所有腳本都載入
    setTimeout(() => {
        console.log('開始創建 FSMTestApp...');
        try {
            window.app = new FSMTestApp();
            console.log('✅ FSM Test App 啟動成功');
        } catch (error) {
            console.error('❌ FSM Test App 啟動失敗:', error);
            console.error('Stack:', error.stack);
        }
    }, 200);

    // 暗色模式切換（獨立處理）
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        const body = document.body;
        const savedTheme = localStorage.getItem('theme');

        if (savedTheme === 'dark') {
            body.classList.remove('light-mode');
            body.classList.add('dark-mode');
            darkModeToggle.textContent = '☀️';
        }

        darkModeToggle.addEventListener('click', () => {
            if (body.classList.contains('dark-mode')) {
                body.classList.remove('dark-mode');
                body.classList.add('light-mode');
                darkModeToggle.textContent = '🌙';
                localStorage.setItem('theme', 'light');
            } else {
                body.classList.remove('light-mode');
                body.classList.add('dark-mode');
                darkModeToggle.textContent = '☀️';
                localStorage.setItem('theme', 'dark');
            }
        });
    }
});

console.log('📜 app.js 載入完成');