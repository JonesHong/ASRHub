// FCM 狀態定義
const FCMState = {
    IDLE: 'IDLE',
    LISTENING: 'LISTENING',
    ACTIVATED: 'ACTIVATED',  // 系統被激活（可由關鍵字/按鈕/視覺觸發）
    RECORDING: 'RECORDING',
    STREAMING: 'STREAMING',
    UPLOADING: 'UPLOADING',
    WAITING_TRANSCRIBE: 'WAITING_TRANSCRIBE',
    TRANSCRIBING: 'TRANSCRIBING',
    PROCESSING: 'PROCESSING',
    ERROR: 'ERROR',
    RECOVERING: 'RECOVERING'
};

// FCM 事件定義
const FCMEvent = {
    START_LISTENING: 'START_LISTENING',
    WAKE_TRIGGERED: 'WAKE_TRIGGERED',  // 統一的觸發喚醒事件
    START_RECORDING: 'START_RECORDING',
    END_RECORDING: 'END_RECORDING',
    START_STREAMING: 'START_STREAMING',
    END_STREAMING: 'END_STREAMING',
    UPLOAD_FILE: 'UPLOAD_FILE',
    UPLOAD_DONE: 'UPLOAD_DONE',
    BEGIN_TRANSCRIPTION: 'BEGIN_TRANSCRIPTION',
    TRANSCRIPTION_DONE: 'TRANSCRIPTION_DONE',
    TIMEOUT: 'TIMEOUT',
    RESET: 'RESET',
    ERROR: 'ERROR',
    RECOVER: 'RECOVER'
};

// 喚醒觸發方式
const FCMWakeTrigger = {
    KEYWORD: 'KEYWORD',     // 關鍵字/喚醒詞
    BUTTON: 'BUTTON',       // 按鈕觸發
    VISION: 'VISION'        // 視覺觸發
};

// 結束觸發原因
const FCMEndTrigger = {
    VAD_TIMEOUT: 'VAD_TIMEOUT',  // VAD 偵測到靜音超時
    BUTTON: 'BUTTON',             // 按鈕結束
    VISION: 'VISION'              // 視覺結束
};

// 狀態描述
const StateDescriptions = {
    IDLE: '閒置等待 - 系統準備接收新的任務',
    LISTENING: '等待觸發 - 監聽關鍵字/等待按鈕/視覺觸發',
    ACTIVATED: '已激活 - 系統被觸發激活，準備開始錄音或串流',
    RECORDING: '錄音中 - 收集音訊數據到緩衝區（非串流模式）',
    STREAMING: '串流中 - 即時串流音訊到 ASR Provider（串流模式）',
    TRANSCRIBING: '轉譯中 - 將錄音完成的音訊進行轉譯（非串流模式）',
    PROCESSING: '批次處理中 - 處理上傳的音訊檔案',
    ERROR: '錯誤狀態 - 系統發生錯誤',
    RECOVERING: '恢復中 - 嘗試從錯誤中恢復'
};

// 事件按鈕的顯示名稱
const EventLabels = {
    START_LISTENING: '開始監聽',
    WAKE_TRIGGERED: '觸發喚醒',
    START_RECORDING: '開始錄音',
    END_RECORDING: '結束錄音',
    START_STREAMING: '開始串流',
    END_STREAMING: '結束串流',
    UPLOAD_FILE: '上傳檔案',
    UPLOAD_DONE: '上傳完成',
    BEGIN_TRANSCRIPTION: '開始轉譯',
    TRANSCRIPTION_DONE: '轉譯完成',
    TIMEOUT: '超時',
    RESET: '重置',
    ERROR: '錯誤',
    RECOVER: '恢復'
};

// 喚醒觸發方式的顯示名稱
const WakeTriggerLabels = {
    KEYWORD: '關鍵字',
    BUTTON: '按鈕',
    VISION: '視覺'
};

// 結束觸發原因的顯示名稱
const EndTriggerLabels = {
    VAD_TIMEOUT: 'VAD超時',
    BUTTON: '按鈕',
    VISION: '視覺'
};

// 模式標籤
const ModeLabels = {
    'batch': '批次處理',
    'non-streaming': '非串流實時',
    'streaming': '串流實時'
};

// 策略模式基類
class FCMStrategy {
    transition(state, event, context = {}) {
        // 通用錯誤處理
        if (event === FCMEvent.ERROR && state !== FCMState.ERROR) {
            return FCMState.ERROR;
        }
        if (state === FCMState.ERROR && event === FCMEvent.RECOVER) {
            return FCMState.RECOVERING;
        }
        if (state === FCMState.RECOVERING && event === FCMEvent.RESET) {
            return FCMState.IDLE;
        }
        if (event === FCMEvent.RESET) {
            return FCMState.IDLE;
        }

        return this.specificTransition(state, event, context);
    }

    specificTransition(state, event, context) {
        return state; // 預設不轉換
    }

    getAvailableEvents(state) {
        const common = [FCMEvent.RESET, FCMEvent.ERROR];
        const specific = this.getSpecificEvents(state);
        return [...new Set([...common, ...specific])];
    }

    getSpecificEvents(state) {
        return [];
    }
}

// 批次模式策略
class BatchModeStrategy extends FCMStrategy {
    specificTransition(state, event, context) {
        const transitions = {
        [`${FCMState.IDLE}_${FCMEvent.UPLOAD_FILE}`]: FCMState.UPLOADING,
        [`${FCMState.UPLOADING}_${FCMEvent.UPLOAD_DONE}`]: FCMState.WAITING_TRANSCRIBE,
        [`${FCMState.WAITING_TRANSCRIBE}_${FCMEvent.BEGIN_TRANSCRIPTION}`]: FCMState.PROCESSING,
        [`${FCMState.PROCESSING}_${FCMEvent.TRANSCRIPTION_DONE}`]: FCMState.IDLE,
        };

        const key = `${state}_${event}`;
        return transitions[key] || state;
    }

    getSpecificEvents(state) {
        switch (state) {
            case FCMState.IDLE:
                return [FCMEvent.UPLOAD_FILE];
            case FCMState.UPLOADING:
                return [FCMEvent.UPLOAD_DONE];
            case FCMState.WAITING_TRANSCRIBE:
                return [FCMEvent.BEGIN_TRANSCRIPTION];
            case FCMState.PROCESSING:
                return [FCMEvent.TRANSCRIPTION_DONE];
            default:
                return [];
        }
    }
}

// 非串流實時模式策略
class NonStreamingStrategy extends FCMStrategy {
    specificTransition(state, event, context) {
        const transitions = {
            [`${FCMState.IDLE}_${FCMEvent.START_LISTENING}`]: FCMState.LISTENING,
            [`${FCMState.LISTENING}_${FCMEvent.WAKE_TRIGGERED}`]: FCMState.ACTIVATED,
            [`${FCMState.ACTIVATED}_${FCMEvent.START_RECORDING}`]: FCMState.RECORDING,
            [`${FCMState.RECORDING}_${FCMEvent.END_RECORDING}`]: FCMState.TRANSCRIBING,
            [`${FCMState.TRANSCRIBING}_${FCMEvent.TRANSCRIPTION_DONE}`]: FCMState.IDLE,
        };

        const key = `${state}_${event}`;
        return transitions[key] || state;
    }

    getSpecificEvents(state) {
        switch (state) {
            case FCMState.IDLE:
                return [FCMEvent.START_LISTENING];
            case FCMState.LISTENING:
                return [FCMEvent.WAKE_TRIGGERED];
            case FCMState.ACTIVATED:
                return [FCMEvent.START_RECORDING];
            case FCMState.RECORDING:
                return [FCMEvent.END_RECORDING];
            case FCMState.TRANSCRIBING:
                return [FCMEvent.TRANSCRIPTION_DONE];
            default:
                return [];
        }
    }
}

// 串流實時模式策略
class StreamingStrategy extends FCMStrategy {
    specificTransition(state, event, context) {
        const transitions = {
            [`${FCMState.IDLE}_${FCMEvent.START_LISTENING}`]: FCMState.LISTENING,
            [`${FCMState.LISTENING}_${FCMEvent.WAKE_TRIGGERED}`]: FCMState.ACTIVATED,
            [`${FCMState.ACTIVATED}_${FCMEvent.START_STREAMING}`]: FCMState.STREAMING,
            [`${FCMState.STREAMING}_${FCMEvent.END_STREAMING}`]: FCMState.IDLE,
        };

        const key = `${state}_${event}`;
        return transitions[key] || state;
    }

    getSpecificEvents(state) {
        switch (state) {
            case FCMState.IDLE:
                return [FCMEvent.START_LISTENING];
            case FCMState.LISTENING:
                return [FCMEvent.WAKE_TRIGGERED];
            case FCMState.ACTIVATED:
                return [FCMEvent.START_STREAMING];
            case FCMState.STREAMING:
                return [FCMEvent.END_STREAMING];
            default:
                return [];
        }
    }
}

// FCM 控制器
class FCMController {
    constructor(strategy) {
        this.state = FCMState.IDLE;
        this.strategy = strategy;
        this.stateHooks = {
            enter: {},
            exit: {}
        };
        this.listeners = [];
        this.stateStartTime = Date.now();
    }

    addHook(state, hookType, callback) {
        if (!this.stateHooks[hookType][state]) {
            this.stateHooks[hookType][state] = [];
        }
        this.stateHooks[hookType][state].push(callback);
    }

    addEventListener(callback) {
        this.listeners.push(callback);
    }

    removeEventListener(callback) {
        const index = this.listeners.indexOf(callback);
        if (index > -1) {
            this.listeners.splice(index, 1);
        }
    }

    async handleEvent(event, context = {}) {
        const oldState = this.state;
        const newState = this.strategy.transition(oldState, event, context);

        if (newState !== oldState) {
            // 執行退出 hooks
            await this.runHooks(oldState, 'exit', { newState, event, context });

            // 更新狀態
            this.state = newState;
            this.stateStartTime = Date.now();

            // 執行進入 hooks
            await this.runHooks(newState, 'enter', { oldState, event, context });

            // 通知監聽器
            this.notifyListeners({
                oldState,
                newState,
                event,
                context,
                timestamp: Date.now()
            });
        }

        return this.state;
    }

    async runHooks(state, hookType, context) {
        const hooks = this.stateHooks[hookType][state] || [];
        for (const hook of hooks) {
            try {
                await hook(context);
            } catch (error) {
                console.error(`Hook error (${hookType} ${state}):`, error);
            }
        }
    }

    notifyListeners(change) {
        for (const listener of this.listeners) {
            try {
                listener(change);
            } catch (error) {
                console.error('Listener error:', error);
            }
        }
    }

    getAvailableEvents() {
        return this.strategy.getAvailableEvents(this.state);
    }

    getStateDuration() {
        return Date.now() - this.stateStartTime;
    }

    setStrategy(strategy) {
        this.strategy = strategy;
    }

    reset() {
        this.handleEvent(FCMEvent.RESET);
    }
}

// 策略工廠
function createStrategy(mode) {
    switch (mode) {
        case 'batch':
            return new BatchModeStrategy();
        case 'non-streaming':
            return new NonStreamingStrategy();
        case 'streaming':
            return new StreamingStrategy();
        default:
            return new BatchModeStrategy();
    }
}