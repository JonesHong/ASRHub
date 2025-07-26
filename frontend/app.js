// ASR Hub Frontend Application

class ASRClient {
    constructor() {
        this.protocol = 'websocket';
        this.connection = null;
        this.sessionId = null;
        this.audioChunks = [];
        this.mediaRecorder = null;
        this.audioBlob = null;
        this.audioFile = null; // 用於存儲上傳的檔案
        this.isFileUpload = false; // 標記是否為檔案上傳模式
        
        // WebSocket config
        this.wsUrl = 'ws://localhost:8765';
        
        // Socket.io config
        this.socketioUrl = 'http://localhost:8766';
        this.socketioNamespace = '/asr';
        
        // HTTP SSE config
        this.httpSSEUrl = 'http://localhost:8000';
        this.sseConnection = null;
        
        this.initializeElements();
        this.attachEventListeners();
    }
    
    initializeElements() {
        this.elements = {
            protocolSelect: document.getElementById('protocol'),
            startRecordBtn: document.getElementById('startRecord'),
            stopRecordBtn: document.getElementById('stopRecord'),
            startRecognitionBtn: document.getElementById('startRecognition'),
            status: document.getElementById('status'),
            connectionStatus: document.getElementById('connectionStatus'),
            audioPlayer: document.getElementById('audioPlayer'),
            audioInfo: document.getElementById('audioInfo'),
            results: document.getElementById('results'),
            logs: document.getElementById('logs'),
            audioFileInput: document.getElementById('audioFile'),
            fileInfo: document.getElementById('fileInfo')
        };
    }
    
    attachEventListeners() {
        this.elements.protocolSelect.addEventListener('change', (e) => {
            this.protocol = e.target.value;
            this.log(`切換協議為: ${this.protocol}`, 'info');
            this.disconnect();
        });
        
        this.elements.startRecordBtn.addEventListener('click', () => this.startRecording());
        this.elements.stopRecordBtn.addEventListener('click', () => this.stopRecording());
        this.elements.startRecognitionBtn.addEventListener('click', () => this.startRecognition());
        
        // 檔案上傳事件
        this.elements.audioFileInput.addEventListener('change', (e) => this.handleFileSelect(e));
    }
    
    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            // 清除檔案相關狀態
            this.audioFile = null;
            this.isFileUpload = false;
            this.elements.fileInfo.textContent = '';
            this.elements.fileInfo.classList.remove('has-file');
            this.elements.audioFileInput.value = '';
            
            this.audioChunks = [];
            this.mediaRecorder = new MediaRecorder(stream);
            
            this.mediaRecorder.addEventListener('dataavailable', (event) => {
                this.audioChunks.push(event.data);
            });
            
            this.mediaRecorder.addEventListener('stop', () => {
                this.audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.isFileUpload = false; // 標記為錄音模式
                this.audioFile = null; // 清除檔案
                this.displayAudioInfo();
            });
            
            this.mediaRecorder.start();
            
            this.updateStatus('錄音中...', 'recording');
            this.elements.startRecordBtn.disabled = true;
            this.elements.stopRecordBtn.disabled = false;
            this.elements.stopRecordBtn.classList.add('recording');
            this.elements.startRecognitionBtn.disabled = true;
            
            this.log('開始錄音', 'success');
            
        } catch (error) {
            this.log(`錄音失敗: ${error.message}`, 'error');
            this.updateStatus('錄音失敗', 'error');
        }
    }
    
    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            
            this.updateStatus('錄音完成', 'ready');
            this.elements.startRecordBtn.disabled = false;
            this.elements.stopRecordBtn.disabled = true;
            this.elements.stopRecordBtn.classList.remove('recording');
            this.elements.startRecognitionBtn.disabled = false;
            
            this.log('錄音結束', 'success');
        }
    }
    
    displayAudioInfo() {
        if (this.audioBlob || this.audioFile) {
            const audioSource = this.audioFile || this.audioBlob;
            const audioUrl = URL.createObjectURL(audioSource);
            this.elements.audioPlayer.src = audioUrl;
            this.elements.audioPlayer.style.display = 'block';
            
            const sizeInKB = (audioSource.size / 1024).toFixed(2);
            const sourceType = this.isFileUpload ? '檔案' : '錄音';
            this.elements.audioInfo.textContent = `音訊${sourceType}大小: ${sizeInKB} KB`;
        }
    }
    
    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        // 重置錄音相關狀態
        this.audioBlob = null;
        this.audioChunks = [];
        this.isFileUpload = true;
        this.audioFile = file;
        
        // 顯示檔案資訊
        const sizeInKB = (file.size / 1024).toFixed(2);
        const sizeMB = (file.size / 1024 / 1024).toFixed(2);
        const displaySize = sizeMB > 1 ? `${sizeMB} MB` : `${sizeInKB} KB`;
        
        this.elements.fileInfo.textContent = `已選擇: ${file.name} (${displaySize})`;
        this.elements.fileInfo.classList.add('has-file');
        
        // 顯示音訊預覽
        this.displayAudioInfo();
        
        // 啟用辨識按鈕
        this.elements.startRecognitionBtn.disabled = false;
        
        // 清空結果
        this.elements.results.textContent = '';
        this.elements.results.classList.remove('has-content');
        
        this.updateStatus('檔案已載入，可以開始辨識', 'ready');
        this.log(`載入檔案: ${file.name} (${displaySize})`, 'success');
    }
    
    async startRecognition() {
        if (!this.audioBlob && !this.audioFile) {
            this.log('沒有音訊資料', 'error');
            return;
        }
        
        this.updateStatus('連接中...', 'connecting');
        this.elements.results.textContent = '';
        this.elements.results.classList.remove('has-content');
        
        try {
            await this.connect();
            await this.sendAudioForRecognition();
        } catch (error) {
            this.log(`辨識失敗: ${error.message}`, 'error');
            this.updateStatus('辨識失敗', 'error');
        }
    }
    
    async connect() {
        return new Promise((resolve, reject) => {
            if (this.protocol === 'websocket') {
                this.connectWebSocket(resolve, reject);
            } else if (this.protocol === 'socketio') {
                this.connectSocketIO(resolve, reject);
            } else if (this.protocol === 'http_sse') {
                this.connectHTTPSSE(resolve, reject);
            }
        });
    }
    
    connectWebSocket(resolve, reject) {
        this.connection = new WebSocket(this.wsUrl);
        
        this.connection.onopen = () => {
            this.log('WebSocket 連接成功', 'success');
            this.updateConnectionStatus(true);
            resolve();
        };
        
        this.connection.onerror = (error) => {
            this.log('WebSocket 連接錯誤', 'error');
            this.updateConnectionStatus(false);
            reject(error);
        };
        
        this.connection.onmessage = (event) => {
            this.handleWebSocketMessage(event.data);
        };
        
        this.connection.onclose = () => {
            this.log('WebSocket 連接關閉', 'warning');
            this.updateConnectionStatus(false);
        };
    }
    
    connectSocketIO(resolve, reject) {
        this.connection = io(this.socketioUrl, {
            path: '/socket.io/',
            transports: ['websocket']
        });
        
        const namespace = this.connection.io.socket(this.socketioNamespace);
        this.connection = namespace;
        
        this.connection.on('connect', () => {
            this.log(`Socket.io 連接成功, SID: ${this.connection.id}`, 'success');
            this.updateConnectionStatus(true);
            resolve();
        });
        
        this.connection.on('connect_error', (error) => {
            this.log(`Socket.io 連接錯誤: ${error.message}`, 'error');
            this.updateConnectionStatus(false);
            reject(error);
        });
        
        this.connection.on('welcome', (data) => {
            this.log(`收到歡迎訊息: ${JSON.stringify(data)}`, 'info');
        });
        
        this.connection.on('control_response', (data) => {
            this.handleSocketIOControlResponse(data);
        });
        
        this.connection.on('audio_received', (data) => {
            this.log(`音訊已接收: ${data.size} bytes`, 'info');
        });
        
        this.connection.on('partial_result', (data) => {
            this.handlePartialResult(data);
        });
        
        this.connection.on('final_result', (data) => {
            this.handleFinalResult(data);
        });
        
        this.connection.on('error', (data) => {
            this.log(`錯誤: ${data.error}`, 'error');
        });
        
        this.connection.on('disconnect', () => {
            this.log('Socket.io 連接斷開', 'warning');
            this.updateConnectionStatus(false);
        });
    }
    
    connectHTTPSSE(resolve, reject) {
        // HTTP SSE 可以選擇使用串流模式或一次性模式
        this.connection = { protocol: 'http_sse' };
        this.updateConnectionStatus(true);
        this.log('HTTP API 模式已啟用', 'success');
        
        // 詢問使用者選擇模式
        this.useStreamMode = false; // 預設使用一次性模式
        resolve();
    }
    
    async sendAudioForRecognition() {
        if (this.protocol !== 'http_sse') {
            this.sessionId = this.generateSessionId();
        }
        
        if (this.protocol === 'websocket') {
            await this.sendWebSocketAudio();
        } else if (this.protocol === 'socketio') {
            await this.sendSocketIOAudio();
        } else if (this.protocol === 'http_sse') {
            await this.sendHTTPSSEAudio();
        }
    }
    
    async sendWebSocketAudio() {
        // 發送開始命令
        const startCommand = {
            type: 'control',
            command: 'start',
            session_id: this.sessionId
        };
        this.connection.send(JSON.stringify(startCommand));
        this.log('發送開始命令', 'info');
        
        // 等待一下讓 session 初始化
        await this.sleep(100);
        
        // 將音訊轉換為 ArrayBuffer
        const audioSource = this.audioFile || this.audioBlob;
        const arrayBuffer = await audioSource.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        
        // 分塊發送音訊
        const chunkSize = 4096;
        for (let i = 0; i < uint8Array.length; i += chunkSize) {
            const chunk = uint8Array.slice(i, i + chunkSize);
            
            const audioMessage = {
                type: 'audio',
                session_id: this.sessionId,
                audio: this.arrayBufferToBase64(chunk),
                chunk_id: Math.floor(i / chunkSize)
            };
            
            this.connection.send(JSON.stringify(audioMessage));
            await this.sleep(10); // 避免發送太快
        }
        
        this.log(`音訊發送完成，共 ${uint8Array.length} bytes`, 'success');
        
        // 發送停止命令
        setTimeout(() => {
            const stopCommand = {
                type: 'control',
                command: 'stop',
                session_id: this.sessionId
            };
            this.connection.send(JSON.stringify(stopCommand));
            this.log('發送停止命令', 'info');
        }, 500);
    }
    
    async sendSocketIOAudio() {
        // 發送開始命令
        this.connection.emit('control', {
            command: 'start',
            params: {}
        });
        this.log('發送開始命令', 'info');
        
        // 等待 control_response
        await this.sleep(100);
        
        // 將音訊轉換為 ArrayBuffer
        const audioSource = this.audioFile || this.audioBlob;
        const arrayBuffer = await audioSource.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        
        // 分塊發送音訊
        const chunkSize = 4096;
        for (let i = 0; i < uint8Array.length; i += chunkSize) {
            const chunk = uint8Array.slice(i, i + chunkSize);
            
            this.connection.emit('audio_chunk', {
                audio: this.arrayBufferToBase64(chunk),
                format: 'base64',
                chunk_id: Math.floor(i / chunkSize),
                audio_params: {
                    sample_rate: 16000,
                    channels: 1,
                    encoding: 'webm'
                }
            });
            
            await this.sleep(10); // 避免發送太快
        }
        
        this.log(`音訊發送完成，共 ${uint8Array.length} bytes`, 'success');
        
        // 發送停止命令
        setTimeout(() => {
            this.connection.emit('control', {
                command: 'stop',
                params: {}
            });
            this.log('發送停止命令', 'info');
        }, 500);
    }
    
    async sendHTTPSSEAudio() {
        try {
            const audioSource = this.audioFile || this.audioBlob;
            // 根據音訊大小決定使用哪種模式
            const audioSizeKB = audioSource.size / 1024;
            const useStreamMode = audioSizeKB > 100; // 超過 100KB 使用串流模式
            
            if (useStreamMode) {
                // 使用串流模式（SSE + 音訊上傳）
                await this.sendHTTPSSEStreamMode();
            } else {
                // 使用一次性模式（適合小檔案）
                await this.sendHTTPSSEOneShot();
            }
            
        } catch (error) {
            this.log(`HTTP 轉譯錯誤: ${error.message}`, 'error');
            this.updateStatus('轉譯失敗', 'error');
        }
    }
    
    async sendHTTPSSEOneShot() {
        // 使用 v1/transcribe 端點進行一次性轉譯
        this.updateStatus('上傳音訊中...', 'uploading');
        
        // 建立 FormData
        const formData = new FormData();
        
        if (this.isFileUpload) {
            // 上傳檔案
            formData.append('audio', this.audioFile, this.audioFile.name);
        } else {
            // 上傳錄音
            formData.append('audio', this.audioBlob, 'recording.webm');
        }
        
        formData.append('provider', 'whisper');
        formData.append('language', 'auto');
        
        // 發送到 v1/transcribe 端點
        const response = await fetch(`${this.httpSSEUrl}/v1/transcribe`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`上傳失敗: ${response.status} - ${errorText}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'success') {
            this.log('轉譯成功', 'success');
            this.updateStatus('轉譯完成', 'complete');
            
            // 顯示轉譯結果
            this.handleFinalResult({
                text: result.transcript.text,
                confidence: result.transcript.confidence,
                language: result.transcript.language,
                is_final: true
            });
            
            // 如果有分段資訊，顯示在日誌中
            if (result.transcript.segments && result.transcript.segments.length > 0) {
                this.log(`共 ${result.transcript.segments.length} 個片段`, 'info');
            }
            
            // 顯示處理時間
            if (result.metadata && result.metadata.processing_time) {
                this.log(`處理時間: ${result.metadata.processing_time.toFixed(2)} 秒`, 'info');
            }
        } else {
            throw new Error(result.error || '轉譯失敗');
        }
    }
    
    async sendHTTPSSEStreamMode() {
        // 使用串流模式
        this.updateStatus('建立 SSE 連接...', 'connecting');
        
        // 建立 session
        const sessionResponse = await fetch(`${this.httpSSEUrl}/session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                metadata: { client: 'frontend' },
                provider_config: {
                    provider: 'whisper',
                    language: 'auto'
                }
            })
        });
        
        if (!sessionResponse.ok) {
            throw new Error(`建立 session 失敗: ${sessionResponse.status}`);
        }
        
        const sessionData = await sessionResponse.json();
        this.sessionId = sessionData.session_id;
        this.log(`Session 建立成功: ${this.sessionId}`, 'success');
        
        // 建立 SSE 連接
        this.sseConnection = new EventSource(`${this.httpSSEUrl}/transcribe/${this.sessionId}`);
        
        // 設定事件處理器
        this.sseConnection.addEventListener('connected', (event) => {
            this.log('SSE 連接成功', 'success');
            this.updateStatus('上傳音訊中...', 'uploading');
        });
        
        this.sseConnection.addEventListener('transcript', (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.is_final) {
                    this.handleFinalResult(data);
                    // 移除這裡的狀態更新，因為 handleFinalResult 已經會更新狀態
                } else {
                    this.handlePartialResult(data);
                }
            } catch (e) {
                this.log(`解析 transcript 事件失敗: ${e.message}`, 'error');
            }
        });
        
        this.sseConnection.addEventListener('error', (event) => {
            if (event.data) {
                try {
                    const data = JSON.parse(event.data);
                    this.log(`錯誤: ${data.message}`, 'error');
                } catch (e) {
                    this.log(`SSE 錯誤: ${event.data}`, 'error');
                }
            }
        });
        
        this.sseConnection.onerror = () => {
            this.log('SSE 連接錯誤', 'error');
            this.updateConnectionStatus(false);
        };
        
        // 等待連接建立
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // 發送開始命令
        const startResponse = await fetch(`${this.httpSSEUrl}/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                command: 'start',
                session_id: this.sessionId,
                params: {}
            })
        });
        
        if (!startResponse.ok) {
            throw new Error(`開始命令失敗: ${startResponse.status}`);
        }
        
        // 上傳音訊資料
        const audioSource = this.audioFile || this.audioBlob;
        const arrayBuffer = await audioSource.arrayBuffer();
        
        // 根據來源設定 Content-Type
        let contentType = 'audio/webm';
        let format = 'webm';
        
        if (this.isFileUpload && this.audioFile) {
            contentType = this.audioFile.type || 'application/octet-stream';
            // 從檔案類型推斷格式
            if (this.audioFile.name.endsWith('.mp3')) format = 'mp3';
            else if (this.audioFile.name.endsWith('.wav')) format = 'wav';
            else if (this.audioFile.name.endsWith('.m4a')) format = 'm4a';
            else if (this.audioFile.name.endsWith('.mp4')) format = 'mp4';
            else if (this.audioFile.name.endsWith('.ogg')) format = 'ogg';
        }
        
        const uploadResponse = await fetch(`${this.httpSSEUrl}/audio/${this.sessionId}`, {
            method: 'POST',
            body: arrayBuffer,
            headers: {
                'Content-Type': contentType,
                'X-Audio-Sample-Rate': '16000',
                'X-Audio-Channels': '1',
                'X-Audio-Format': format
            }
        });
        
        if (!uploadResponse.ok) {
            throw new Error(`音訊上傳失敗: ${uploadResponse.status}`);
        }
        
        const uploadResult = await uploadResponse.json();
        this.log(`音訊上傳成功: ${uploadResult.bytes_received} bytes`, 'success');
        
        // 發送停止命令
        setTimeout(async () => {
            await fetch(`${this.httpSSEUrl}/control`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command: 'stop',
                    session_id: this.sessionId,
                    params: {}
                })
            });
            this.log('發送停止命令', 'info');
            
            // 稍後關閉 SSE 連接
            setTimeout(() => {
                if (this.sseConnection) {
                    this.sseConnection.close();
                    this.sseConnection = null;
                }
            }, 2000);
        }, 500);
    }
    
    handleWebSocketMessage(data) {
        try {
            const message = JSON.parse(data);
            this.log(`收到訊息: ${message.type}`, 'info');
            
            switch (message.type) {
                case 'welcome':
                    this.sessionId = message.session_id;
                    break;
                case 'status':
                    this.updateStatus(`狀態: ${message.status}`, 'info');
                    break;
                case 'transcript':
                case 'transcript_partial':
                    this.handlePartialResult(message);
                    break;
                case 'transcript_final':
                case 'final_result':
                    this.handleFinalResult(message);
                    break;
                case 'control_response':
                    this.handleControlResponse(message);
                    break;
                case 'error':
                    this.log(`錯誤: ${message.error}`, 'error');
                    break;
                case 'progress':
                    this.log(`進度: ${message.message}`, 'info');
                    break;
                case 'audio_received':
                    this.log(`音訊已接收: ${message.size} bytes`, 'success');
                    break;
            }
        } catch (error) {
            this.log(`解析訊息失敗: ${error.message}`, 'error');
        }
    }
    
    handleSocketIOControlResponse(data) {
        this.log(`控制回應: ${data.command} - ${data.status}`, 'info');
        if (data.data && data.data.session_id) {
            this.sessionId = data.data.session_id;
        }
    }
    
    handleControlResponse(data) {
        this.log(`控制回應: ${data.command || data.status}`, 'info');
        if (data.data && data.data.session_id) {
            this.sessionId = data.data.session_id;
        }
    }
    
    handlePartialResult(data) {
        this.updateStatus('辨識中...', 'processing');
        if (data.text) {
            this.elements.results.textContent = data.text;
            this.elements.results.classList.add('has-content');
        }
    }
    
    handleFinalResult(data) {
        this.updateStatus('辨識完成', 'complete');
        if (data.text) {
            this.elements.results.textContent = data.text;
            this.elements.results.classList.add('has-content');
            this.log('辨識完成', 'success');
        }
    }
    
    disconnect() {
        if (this.connection) {
            if (this.protocol === 'websocket') {
                this.connection.close();
            } else if (this.protocol === 'socketio') {
                this.connection.disconnect();
            } else if (this.protocol === 'http_sse' && this.sseConnection) {
                this.sseConnection.close();
                this.sseConnection = null;
            }
            this.connection = null;
            this.updateConnectionStatus(false);
        }
    }
    
    updateStatus(text, type) {
        this.elements.status.textContent = text;
        this.elements.status.className = `status-text ${type}`;
    }
    
    updateConnectionStatus(connected) {
        this.elements.connectionStatus.textContent = connected ? '已連接' : '未連接';
        this.elements.connectionStatus.className = `connection-status ${connected ? 'connected' : 'disconnected'}`;
    }
    
    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        logEntry.textContent = `[${timestamp}] ${message}`;
        
        this.elements.logs.appendChild(logEntry);
        this.elements.logs.scrollTop = this.elements.logs.scrollHeight;
        
        // 保持日誌數量在合理範圍
        if (this.elements.logs.children.length > 100) {
            this.elements.logs.removeChild(this.elements.logs.firstChild);
        }
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
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    const client = new ASRClient();
    console.log('ASR Client 初始化完成');
});