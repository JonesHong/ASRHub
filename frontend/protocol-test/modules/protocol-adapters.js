// 協議適配器模組 - 為不同通訊協議提供統一接口
// 基礎協議適配器抽象類
class ProtocolAdapter {
    constructor() {
        this.connection = null;
        this.sessionId = null;
        this.isConnected = false;
        
        // 事件處理器
        this.onConnected = null;
        this.onDisconnected = null;
        this.onMessage = null;
        this.onError = null;
    }
    
    // 抽象方法 - 子類必須實現
    async connect() {
        throw new Error('connect() 方法必須在子類中實現');
    }
    
    async disconnect() {
        throw new Error('disconnect() 方法必須在子類中實現');
    }
    
    async sendEvent(eventType, payload) {
        throw new Error('sendEvent() 方法必須在子類中實現');
    }
    
    async sendAudioChunk(sessionId, chunk, chunkId) {
        throw new Error('sendAudioChunk() 方法必須在子類中實現');
    }
    
    async sendAudioData(sessionId, audioSource, isFileUpload, progressCallback) {
        throw new Error('sendAudioData() 方法必須在子類中實現');
    }
    
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
    
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    /**
     * 分塊發送音訊數據的通用方法
     * 供 WebSocket 和 Socket.IO 適配器使用
     */
    async sendAudioDataInChunks(sessionId, audioSource, progressCallback, protocolName, config = {}) {
        const arrayBuffer = await audioSource.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        const chunkSize = config.chunkSize || 4096;  // 使用配置的分塊大小
        const progressInterval = config.progressInterval || 10;  // 使用配置的進度間隔
        let sentChunks = 0;
        
        console.log(`[${protocolName}] 開始上傳音訊數據，總大小: ${uint8Array.length} bytes，分塊大小: ${chunkSize}`);
        
        for (let i = 0; i < uint8Array.length; i += chunkSize) {
            const chunk = uint8Array.slice(i, i + chunkSize);
            const chunkId = Math.floor(i / chunkSize);
            
            await this.sendAudioChunk(sessionId, chunk, chunkId);
            
            // 每隔配置的間隔記錄一次
            if (chunkId % progressInterval === 0) {
                console.log(`[${protocolName}] 發送音訊塊 ${chunkId}`);
            }
            
            sentChunks++;
            
            // 進度回調
            if (progressCallback) {
                const progress = Math.round((i + chunk.length) / uint8Array.length * 100);
                progressCallback(progress);
            }
            
            // 控制發送速度
            await this.sleep(5);
        }
        
        console.log(`[${protocolName}] 音訊上傳完成，共 ${uint8Array.length} bytes，${sentChunks} 個分塊`);
    }
}

// WebSocket 協議適配器
class WebSocketAdapter extends ProtocolAdapter {
    constructor() {
        super();
        this.wsUrl = 'ws://localhost:8765';
    }
    
    async connect() {
        return new Promise((resolve, reject) => {
            try {
                this.connection = new WebSocket(this.wsUrl);
                
                this.connection.onopen = () => {
                    this.isConnected = true;
                    if (this.onConnected) {
                        this.onConnected('WebSocket');
                    }
                    resolve();
                };
                
                this.connection.onerror = (error) => {
                    this.isConnected = false;
                    if (this.onError) {
                        this.onError('WebSocket 連接錯誤');
                    }
                    reject(error);
                };
                
                this.connection.onmessage = (event) => {
                    this.handleMessage(event.data);
                };
                
                this.connection.onclose = () => {
                    this.isConnected = false;
                    if (this.onDisconnected) {
                        this.onDisconnected();
                    }
                };
                
                // 設定連接超時
                setTimeout(() => {
                    if (this.connection && this.connection.readyState === WebSocket.CONNECTING) {
                        this.connection.close();
                        reject(new Error('WebSocket 連接超時'));
                    }
                }, 10000);
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    async disconnect() {
        if (this.connection && this.connection.readyState === WebSocket.OPEN) {
            this.connection.close();
        }
        this.connection = null;
        this.isConnected = false;
    }
    
    async sendEvent(eventType, payload) {
        if (this.connection && this.connection.readyState === WebSocket.OPEN) {
            // 發送包含 event 和 data 的結構
            // WebSocket 需要 event 欄位來識別事件類型
            this.connection.send(JSON.stringify({
                event: eventType,
                data: payload
            }));
        } else {
            throw new Error('WebSocket 未連接');
        }
    }
    
    async sendAudioChunk(sessionId, chunk, chunkId) {
        if (this.connection && this.connection.readyState === WebSocket.OPEN) {
            // 發送包含 event 和 data 的結構
            const payload = {
                session_id: sessionId,
                audio: this.arrayBufferToBase64(chunk),
                chunk_id: chunkId
            };
            this.connection.send(JSON.stringify({
                event: 'chunk/data',
                data: payload
            }));
        } else {
            throw new Error('WebSocket 未連接');
        }
    }
    
    async sendAudioData(sessionId, audioSource, isFileUpload, progressCallback, config = {}) {
        // WebSocket 協議：使用統一的分塊發送方法
        await this.sendAudioDataInChunks(sessionId, audioSource, progressCallback, 'WebSocket', config);
    }
    
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            
            // 處理新的事件結構
            if (this.onMessage) {
                this.onMessage(message);
            }
            
            console.log(`收到 WebSocket 訊息: ${message.type}`);
        } catch (error) {
            if (this.onError) {
                this.onError(`解析 WebSocket 訊息失敗: ${error.message}`);
            }
        }
    }
}

// Socket.IO 協議適配器
class SocketIOAdapter extends ProtocolAdapter {
    constructor() {
        super();
        this.socketioUrl = 'http://localhost:8766';
        this.socketioNamespace = '/asr';
    }
    
    async connect() {
        return new Promise((resolve, reject) => {
            try {
                this.connection = io(this.socketioUrl, {
                    path: '/socket.io/',
                    transports: ['websocket']
                });
                
                const namespace = this.connection.io.socket(this.socketioNamespace);
                this.connection = namespace;
                
                this.connection.on('connect', () => {
                    this.isConnected = true;
                    if (this.onConnected) {
                        this.onConnected(`Socket.IO (${this.connection.id})`);
                    }
                    resolve();
                });
                
                this.connection.on('connect_error', (error) => {
                    this.isConnected = false;
                    if (this.onError) {
                        this.onError(`Socket.IO 連接錯誤: ${error.message}`);
                    }
                    reject(error);
                });
                
                // 監聽新的獨立事件類型
                const eventTypes = [
                    'session/create', 'session/start', 'session/stop', 'session/destroy',
                    'recording/start', 'recording/end',
                    'chunk/upload/start', 'chunk/upload/done', 'chunk/data',
                    'file/upload', 'file/upload/done',
                    'transcript', 'status', 'error'
                ];
                
                eventTypes.forEach(eventType => {
                    this.connection.on(eventType, (data) => {
                        if (this.onMessage) {
                            this.onMessage({
                                type: eventType,
                                payload: data
                            });
                        }
                    });
                });
                
                // 向後兼容：監聽 final_result 事件
                this.connection.on('final_result', (data) => {
                    if (this.onMessage) {
                        this.onMessage({
                            type: 'final_result',
                            payload: data
                        });
                    }
                });
                
                // 監聽其他事件
                this.connection.on('audio_received', (data) => {
                    console.log(`音訊塊已接收: ${data.size} bytes`);
                });
                
                this.connection.on('error', (data) => {
                    if (this.onError) {
                        this.onError(`Socket.IO 錯誤: ${data.error}`);
                    }
                });
                
                this.connection.on('disconnect', () => {
                    this.isConnected = false;
                    if (this.onDisconnected) {
                        this.onDisconnected();
                    }
                });
                
                // 設定連接超時
                setTimeout(() => {
                    if (!this.isConnected && this.connection) {
                        this.connection.disconnect();
                        reject(new Error('Socket.IO 連接超時'));
                    }
                }, 10000);
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    async disconnect() {
        if (this.connection && this.connection.connected) {
            this.connection.disconnect();
        }
        this.connection = null;
        this.isConnected = false;
    }
    
    async sendEvent(eventType, payload) {
        if (this.connection && this.connection.connected) {
            // 包裝 payload 以符合後端期望的格式
            this.connection.emit(eventType, { payload });
        } else {
            throw new Error('Socket.IO 未連接');
        }
    }
    
    async sendAudioChunk(sessionId, chunk, chunkId) {
        if (this.connection && this.connection.connected) {
            // 使用正確的事件名稱 audio/chunk（後端路由定義）
            this.connection.emit('audio/chunk', {
                session_id: sessionId,
                audio: this.arrayBufferToBase64(chunk),
                chunk_id: chunkId
            });
        } else {
            throw new Error('Socket.IO 未連接');
        }
    }
    
    async sendAudioData(sessionId, audioSource, isFileUpload, progressCallback, config = {}) {
        // Socket.IO 協議：使用統一的分塊發送方法
        await this.sendAudioDataInChunks(sessionId, audioSource, progressCallback, 'Socket.IO', config);
    }
}

// HTTP SSE 協議適配器
class HTTPSSEAdapter extends ProtocolAdapter {
    constructor() {
        super();
        const defaultPort = '8000';
        this.httpSSEUrl = `http://${window.location.hostname}:${defaultPort}`;
        this.sseConnection = null;
        this.sseReconnectTimer = null;
        this.manuallyDisconnected = false;
        this.activeSseSessionId = null; // 追蹤當前 SSE 連接對應的 session ID
    }
    
    async connect() {
        this.isConnected = true;
        if (this.onConnected) {
            this.onConnected('HTTP SSE');
        }
        return Promise.resolve();
    }
    
    async disconnect() {
        this.closeSSEConnection();
        this.isConnected = false;
    }
    
    async sendEvent(eventType, payload) {
        try {
            // HTTP SSE 特殊處理：session/create 事件透過建立 SSE 連接自動創建
            if (eventType === 'session/create') {
                const sessionId = payload.session_id;
                console.log(`[HTTP SSE] 自動創建 session: ${sessionId}`);
                
                // 建立 SSE 連接時會自動創建 session
                await this.createSSEConnection(sessionId);
                
                // 模擬成功回應
                return {
                    status: 'success',
                    action: 'create_session',
                    session_id: sessionId,
                    timestamp: new Date().toISOString()
                };
            }
            
            // HTTP SSE 特殊處理：session/destroy 事件關閉 SSE 連接
            if (eventType === 'session/destroy') {
                console.log(`[HTTP SSE] 銷毀 session: ${payload.session_id}`);
                this.closeSSEConnection();
                
                // 模擬成功回應
                return {
                    status: 'success',
                    action: 'destroy_session',
                    session_id: payload.session_id,
                    timestamp: new Date().toISOString()
                };
            }
            
            // 將事件類型轉換為端點路徑
            const endpoint = this.eventTypeToEndpoint(eventType);
            const sessionId = payload.session_id;
            
            // 為需要 session_id 的端點構建 URL
            const url = endpoint.includes('{session_id}') 
                ? `${this.httpSSEUrl}${endpoint.replace('{session_id}', sessionId)}`
                : `${this.httpSSEUrl}${endpoint}`;
            
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                throw new Error(`事件發送失敗: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            if (this.onError) {
                this.onError(`HTTP 事件發送失敗: ${error.message}`);
            }
            throw error;
        }
    }
    
    eventTypeToEndpoint(eventType) {
        // 將事件類型轉換為對應的 HTTP 端點（使用實際的後端路由）
        const endpointMap = {
            'session/start': '/session/start-listening/{session_id}',
            'recording/start': '/recording/start/{session_id}',
            'recording/end': '/recording/end/{session_id}',
            'chunk/upload/start': '/upload/chunk-start/{session_id}',
            'chunk/upload/done': '/upload/chunk-done/{session_id}',
            'file/upload': '/upload/file/{session_id}',
            'file/upload/done': '/upload/file-done/{session_id}',
            'transcription/begin': '/transcription/begin/{session_id}'
        };
        
        return endpointMap[eventType] || '/control';
    }
    
    async sendAudioChunk(sessionId, chunk, chunkId) {
        // HTTP SSE 模式不使用塊發送，而是通過檔案上傳
        // 這個方法在 HTTP 模式下不應該被調用
        throw new Error('HTTP SSE 模式不支援音訊塊發送');
    }
    
    async sendAudioData(sessionId, audioSource, isFileUpload, progressCallback, config = {}) {
        // HTTP SSE 協議：檔案上傳模式
        try {
            console.log(`[HTTP SSE] 開始音訊檔案上傳，Session ID: ${sessionId}`);
            
            // 不再在這裡自動建立 SSE 連接
            // SSE 連接應該在 session 創建時建立，並在整個 session 生命週期中保持
            
            // 準備上傳
            if (progressCallback) {
                progressCallback(10); // 初始化完成
            }
            
            // 上傳音訊
            const formData = new FormData();
            
            if (isFileUpload) {
                formData.append('audio', audioSource, audioSource.name);
            } else {
                formData.append('audio', audioSource, 'recording.webm');
            }
            
            formData.append('session_id', sessionId);
            
            if (progressCallback) {
                progressCallback(30); // 準備上傳
            }
            
            // 上傳音訊到 audio endpoint
            const uploadResponse = await fetch(`${this.httpSSEUrl}/audio/${sessionId}`, {
                method: 'POST',
                body: formData
            });
            
            if (!uploadResponse.ok) {
                throw new Error(`音訊上傳失敗: ${uploadResponse.status}`);
            }
            
            if (progressCallback) {
                progressCallback(100); // 上傳完成
            }
            
            const result = await uploadResponse.json();
            console.log(`[HTTP SSE] 音訊上傳完成:`, result);
            
            return result;
            
        } catch (error) {
            console.error(`[HTTP SSE] 音訊上傳失敗: ${error.message}`);
            throw error;
        }
    }
    
    // 已重構：統一使用 sendAudioData() 方法
    // uploadAudioFile() 方法已移除以避免重複邏輯
    
    async createSSEConnection(sessionId) {
        // 檢查是否已經有相同 session 的連接
        if (this.sseConnection && this.sseConnection.readyState !== EventSource.CLOSED) {
            if (this.activeSseSessionId === sessionId) {
                console.log(`[HTTP SSE] SSE 連接已存在且 session 相同 (${sessionId})，重用現有連接`);
                return Promise.resolve();
            } else {
                // 不同的 session，需要關閉舊連接
                console.log(`[HTTP SSE] 切換 session: ${this.activeSseSessionId} -> ${sessionId}，關閉舊連接`);
                this.closeSSEConnection();
            }
        }
        
        return new Promise((resolve, reject) => {
            try {
                const sseUrl = `${this.httpSSEUrl}/events/${sessionId}`;
                console.log(`建立 SSE 連接到: ${sseUrl}`);
                
                this.sseConnection = new EventSource(sseUrl);
                this.activeSseSessionId = sessionId; // 記錄當前活動的 session ID
                
                // 連接成功事件
                this.sseConnection.onopen = (event) => {
                    console.log('✅ SSE 連接已建立');
                    resolve();
                };
                
                // 設定事件處理器 - 監聽新的獨立事件類型
                const eventTypes = [
                    'session/create', 'session/start', 'session/stop', 'session/destroy',
                    'recording/start', 'recording/end',
                    'chunk/upload/start', 'chunk/upload/done', 'chunk/data',
                    'file/upload', 'file/upload/done',
                    'transcript', 'status', 'error'
                ];
                
                eventTypes.forEach(eventType => {
                    this.sseConnection.addEventListener(eventType, (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            if (this.onMessage) {
                                this.onMessage({
                                    type: eventType,
                                    payload: data
                                });
                            }
                        } catch (e) {
                            if (this.onError) {
                                this.onError(`解析 ${eventType} 事件失敗: ${e.message}`);
                            }
                        }
                    });
                });
                
                // 監聽辨識完成事件
                this.sseConnection.addEventListener('transcript', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (this.onMessage) {
                            this.onMessage({
                                type: 'transcript',
                                payload: data
                            });
                        }
                    } catch (e) {
                        if (this.onError) {
                            this.onError(`解析 transcript 事件失敗: ${e.message}`);
                        }
                    }
                });
                
                // 監聽狀態變化事件
                this.sseConnection.addEventListener('status', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (this.onMessage) {
                            this.onMessage({
                                type: 'status',
                                payload: data
                            });
                        }
                    } catch (e) {
                        if (this.onError) {
                            this.onError(`解析 status 事件失敗: ${e.message}`);
                        }
                    }
                });
                
                // 心跳事件
                this.sseConnection.addEventListener('heartbeat', (event) => {
                    console.log('💓 SSE 心跳');
                });
                
                // 連線狀態事件
                this.sseConnection.addEventListener('connected', (event) => {
                    console.log('SSE 連線狀態：已連接');
                });
                
                this.sseConnection.addEventListener('disconnected', (event) => {
                    console.log('SSE 連線狀態：已斷開');
                });
                
                // 錯誤處理
                this.sseConnection.onerror = (event) => {
                    console.error('SSE Error Event:', event);
                    
                    // 檢查連接狀態
                    if (this.sseConnection.readyState === EventSource.CONNECTING) {
                        console.log('⏳ SSE 正在重新連接...');
                    } else if (this.sseConnection.readyState === EventSource.CLOSED) {
                        console.log('❌ SSE 連接已關閉');
                        
                        // 嘗試重連（如果不是手動關閉）
                        if (!this.manuallyDisconnected) {
                            this.scheduleSSEReconnect(sessionId);
                        }
                        reject(new Error('SSE 連接失敗'));
                    } else {
                        console.log(`❌ SSE 連接錯誤 (readyState: ${this.sseConnection.readyState})`);
                        reject(new Error('SSE 連接錯誤'));
                    }
                };
                
                // 設定超時
                setTimeout(() => {
                    if (this.sseConnection.readyState === EventSource.CONNECTING) {
                        console.log('⏰ SSE 連接超時');
                        this.sseConnection.close();
                        reject(new Error('SSE 連接超時'));
                    }
                }, 10000); // 10 秒超時
                
            } catch (error) {
                if (this.onError) {
                    this.onError(`SSE 連接創建失敗: ${error.message}`);
                }
                reject(error);
            }
        });
    }
    
    scheduleSSEReconnect(sessionId) {
        if (this.sseReconnectTimer) {
            clearTimeout(this.sseReconnectTimer);
        }
        
        const reconnectDelay = 3000; // 3 秒後重連
        console.log(`🔄 將在 ${reconnectDelay/1000} 秒後嘗試重連 SSE`);
        
        this.sseReconnectTimer = setTimeout(async () => {
            try {
                await this.createSSEConnection(sessionId);
                console.log('✅ SSE 重連成功');
            } catch (error) {
                console.log(`❌ SSE 重連失敗: ${error.message}`);
                // 如果重連失敗，再次安排重連
                this.scheduleSSEReconnect(sessionId);
            }
        }, reconnectDelay);
    }
    
    closeSSEConnection() {
        this.manuallyDisconnected = true;
        
        if (this.sseReconnectTimer) {
            clearTimeout(this.sseReconnectTimer);
            this.sseReconnectTimer = null;
        }
        
        if (this.sseConnection) {
            this.sseConnection.close();
            this.sseConnection = null;
            this.activeSseSessionId = null; // 清除活動的 session ID
            console.log('SSE 連接已手動關閉');
        }
    }
}

// 協議適配器工廠
class ProtocolAdapterFactory {
    static create(protocol) {
        switch (protocol) {
            case 'websocket':
                return new WebSocketAdapter();
            case 'socketio':
                return new SocketIOAdapter();
            case 'http_sse':
                return new HTTPSSEAdapter();
            default:
                throw new Error(`不支援的協議: ${protocol}`);
        }
    }
    
    static getSupportedProtocols() {
        return ['websocket', 'socketio', 'http_sse'];
    }
}

// 導出到全域
window.ProtocolAdapter = ProtocolAdapter;
window.WebSocketAdapter = WebSocketAdapter;
window.SocketIOAdapter = SocketIOAdapter;
window.HTTPSSEAdapter = HTTPSSEAdapter;
window.ProtocolAdapterFactory = ProtocolAdapterFactory;