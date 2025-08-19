// ASR Hub Frontend Application - PyStoreX Event-Driven Version
// 符合新的純事件驅動架構

class EventDrivenASRClient {
    constructor() {
        this.protocol = 'websocket';
        this.connection = null;
        this.sessionId = null;
        this.audioChunks = [];
        this.mediaRecorder = null;
        this.audioBlob = null;
        this.audioFile = null;
        this.isFileUpload = false;
        this.audioContext = null;
        this.mediaStreamSource = null;
        
        // API endpoints - 動態檢測端口或使用默認值
        this.wsUrl = 'ws://localhost:8765';
        this.socketioUrl = 'http://localhost:8766';
        this.socketioNamespace = '/asr';
        // 默認 8000
        const defaultPort = '8000';
        this.httpSSEUrl = `http://${window.location.hostname}:${defaultPort}`;
        this.sseConnection = null;
        this.sseReconnectTimer = null;
        this.manuallyDisconnected = false;
        
        // 事件驅動架構 - 動作類型定義（對應後端 PyStoreX actions）
        this.ACTIONS = {
            CREATE_SESSION: '[Session] Create',
            DESTROY_SESSION: '[Session] Destroy',
            START_LISTENING: '[Session] Start Listening',
            UPLOAD_FILE: '[Session] Upload File',
            UPLOAD_FILE_DONE: '[Session] Upload File Done',
            CHUNK_UPLOAD_START: '[Session] Chunk Upload Start',
            CHUNK_UPLOAD_DONE: '[Session] Chunk Upload Done',
            START_RECORDING: '[Session] Start Recording', 
            END_RECORDING: '[Session] End Recording',
            AUDIO_CHUNK_RECEIVED: '[Session] Audio Chunk Received',
            BEGIN_TRANSCRIPTION: '[Session] Begin Transcription',
            TRANSCRIPTION_DONE: '[Session] Transcription Done',
            AUDIO_METADATA: '[Session] Audio Metadata',
            ERROR: '[Session] Error'
        };
        
        this.initializeElements();
        this.attachEventListeners();
        this.initializeStatusElements();
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
    
    initializeStatusElements() {
        if (this.elements.status) {
            this.elements.status.classList.add('status-dynamic');
            this.elements.status.dataset.status = 'ready';
        }
    }
    
    attachEventListeners() {
        this.elements.protocolSelect.addEventListener('change', (e) => {
            this.protocol = e.target.value;
            this.log(`切換通訊協定為: ${this.protocol}`, 'info');
            this.disconnect();
        });
        
        this.elements.startRecordBtn.addEventListener('click', () => this.startRecording());
        this.elements.stopRecordBtn.addEventListener('click', () => this.stopRecording());
        this.elements.startRecognitionBtn.addEventListener('click', () => this.startRecognition());
        this.elements.audioFileInput.addEventListener('change', (e) => this.handleFileSelect(e));
    }
    
    // ==================== 事件分發方法 ====================
    
    /**
     * 分發 action 到後端（統一的事件驅動介面）
     */
    async dispatchAction(actionType, payload = {}) {
        const action = {
            type: actionType,
            payload: payload,
            timestamp: new Date().toISOString()
        };
        
        this.log(`分發 Action: ${actionType}`, 'info');
        
        if (this.protocol === 'websocket') {
            return this.dispatchWebSocketAction(action);
        } else if (this.protocol === 'socketio') {
            return this.dispatchSocketIOAction(action);
        } else if (this.protocol === 'http_sse') {
            return this.dispatchHTTPAction(action);
        }
    }
    
    async dispatchWebSocketAction(action) {
        if (this.connection && this.connection.readyState === WebSocket.OPEN) {
            this.connection.send(JSON.stringify({
                type: 'action',
                action: action
            }));
        }
    }
    
    async dispatchSocketIOAction(action) {
        if (this.connection && this.connection.connected) {
            this.connection.emit('action', action);
        }
    }
    
    async dispatchHTTPAction(action) {
        // HTTP 模式通過 REST endpoint 分發 action
        const response = await fetch(`${this.httpSSEUrl}/action`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(action)
        });
        
        if (!response.ok) {
            throw new Error(`Action 分發失敗: ${response.status}`);
        }
        
        return await response.json();
    }
    
    // ==================== 錄音相關方法 ====================
    
    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000,
                    channelCount: 1
                }
            });
            
            // 清除檔案相關狀態
            this.audioFile = null;
            this.isFileUpload = false;
            this.elements.fileInfo.textContent = '';
            this.elements.fileInfo.classList.remove('has-file');
            this.elements.audioFileInput.value = '';
            
            this.audioChunks = [];
            
            // 創建 AudioContext
            try {
                const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                this.audioContext = new AudioContextClass({ sampleRate: 16000 });
                
                if (this.audioContext.sampleRate !== 16000) {
                    this.log(`注意：瀏覽器使用 ${this.audioContext.sampleRate} Hz 採樣率`, 'warning');
                }
                
                this.mediaStreamSource = this.audioContext.createMediaStreamSource(stream);
                
            } catch (e) {
                this.log('無法創建 AudioContext，使用預設錄音設定', 'warning');
            }
            
            const mimeType = this.getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};
            
            if (mimeType && mimeType.includes('webm')) {
                options.audioBitsPerSecond = 128000;
            }
            
            this.mediaRecorder = new MediaRecorder(stream, options);
            
            this.mediaRecorder.addEventListener('dataavailable', (event) => {
                this.audioChunks.push(event.data);
            });
            
            this.mediaRecorder.addEventListener('stop', () => {
                this.audioBlob = new Blob(this.audioChunks, { type: mimeType || 'audio/webm' });
                this.isFileUpload = false;
                this.audioFile = null;
                
                // 验证实际录制的格式
                this.verifyActualAudioFormat();
                
                this.displayAudioInfo();
                
                if (this.audioContext) {
                    this.audioContext.close();
                    this.audioContext = null;
                    this.mediaStreamSource = null;
                }
            });
            
            this.mediaRecorder.start();
            
            // 分發 START_RECORDING action
            await this.dispatchAction(this.ACTIONS.START_RECORDING, {
                session_id: this.sessionId,
                strategy: 'batch'
            });
            
            this.updateStatus('錄音中', 'recording');
            ASRHubCommon.showNotification('已開始錄音', 'success');
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
    
    async stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            
            // 分發 END_RECORDING action
            await this.dispatchAction(this.ACTIONS.END_RECORDING, {
                session_id: this.sessionId,
                trigger: 'manual',
                duration: 0  // 實際應該計算錄音時長
            });
            
            this.updateStatus('準備就緒', 'ready');
            ASRHubCommon.showNotification('錄音完成，可以開始辨識', 'success');
            this.elements.startRecordBtn.disabled = false;
            this.elements.stopRecordBtn.disabled = true;
            this.elements.stopRecordBtn.classList.remove('recording');
            this.elements.startRecognitionBtn.disabled = false;
            
            if (this.audioContext) {
                this.log(`錄音結束 (採樣率: ${this.audioContext.sampleRate} Hz)`, 'success');
            } else {
                this.log('錄音結束', 'success');
            }
        }
    }
    
    displayAudioInfo() {
        if (this.audioBlob || this.audioFile) {
            const audioSource = this.audioFile || this.audioBlob;
            const audioUrl = URL.createObjectURL(audioSource);
            this.elements.audioPlayer.src = audioUrl;
            this.elements.audioPlayer.style.display = 'block';
            
            const sourceType = this.isFileUpload ? '檔案' : '錄音';
            const formattedSize = ASRHubCommon.formatFileSize(audioSource.size);
            this.elements.audioInfo.textContent = `音訊${sourceType}大小: ${formattedSize}`;
        }
    }

    /**
     * 分析音訊檔案的詳細規格
     */
    async analyzeAudioFile(file) {
        return new Promise((resolve, reject) => {
            // 基本檔案資訊
            const metadata = {
                fileName: file.name,
                fileSize: file.size,
                mimeType: file.type,
                fileExtension: this.getFileExtension(file.name),
                lastModified: file.lastModified,
                analyzed_at: new Date().toISOString()
            };

            // 使用 Web Audio API 分析音訊
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const fileReader = new FileReader();

            fileReader.onload = async (event) => {
                try {
                    const arrayBuffer = event.target.result;
                    
                    // 解碼音訊數據
                    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
                    
                    // 提取音訊規格
                    metadata.duration = audioBuffer.duration;
                    metadata.sampleRate = audioBuffer.sampleRate;
                    metadata.channels = audioBuffer.numberOfChannels;
                    metadata.length = audioBuffer.length;
                    
                    // 計算位元率 (估算)
                    if (metadata.duration > 0) {
                        metadata.estimatedBitrate = Math.round((file.size * 8) / metadata.duration);
                    }
                    
                    // 分析音訊格式特徵
                    await this.analyzeAudioFormat(arrayBuffer, metadata);
                    
                    // 分析音訊內容特徵 
                    this.analyzeAudioContent(audioBuffer, metadata);
                    
                    await audioContext.close();
                    resolve(metadata);
                    
                } catch (error) {
                    await audioContext.close();
                    // 如果 Web Audio API 失敗，仍然返回基本資訊
                    this.log(`Web Audio API 解碼失敗，返回基本資訊: ${error.message}`, 'warning');
                    
                    // 嘗試使用 HTML Audio 元素獲取基本資訊
                    this.fallbackAudioAnalysis(file, metadata)
                        .then(resolve)
                        .catch(reject);
                }
            };

            fileReader.onerror = () => {
                reject(new Error('讀取檔案失敗'));
            };

            fileReader.readAsArrayBuffer(file);
        });
    }

    /**
     * 分析音訊格式特徵 (檔案頭、編碼等)
     */
    async analyzeAudioFormat(arrayBuffer, metadata) {
        const uint8Array = new Uint8Array(arrayBuffer.slice(0, 32));
        const header = Array.from(uint8Array.slice(0, 16))
            .map(b => b.toString(16).padStart(2, '0'))
            .join(' ');
        
        metadata.fileHeader = header;
        
        // 檢測實際格式
        const formatInfo = this.detectAudioFormat(uint8Array);
        metadata.detectedFormat = formatInfo.format;
        metadata.estimatedCodec = formatInfo.codec;
        metadata.formatMatches = formatInfo.matches_declared;
        
        // 檢查是否為常見的轉換問題格式
        metadata.conversionNeeded = this.assessConversionNeeded(metadata);
        
        return metadata;
    }

    /**
     * 分析音訊內容特徵
     */
    analyzeAudioContent(audioBuffer, metadata) {
        // 計算音量統計 (取樣前 1000 個樣本)
        const sampleSize = Math.min(1000, audioBuffer.length);
        let maxAmplitude = 0;
        let rmsSum = 0;
        
        for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
            const channelData = audioBuffer.getChannelData(channel);
            
            for (let i = 0; i < sampleSize; i++) {
                const amplitude = Math.abs(channelData[i]);
                maxAmplitude = Math.max(maxAmplitude, amplitude);
                rmsSum += amplitude * amplitude;
            }
        }
        
        metadata.maxAmplitude = maxAmplitude;
        metadata.rmsLevel = Math.sqrt(rmsSum / (sampleSize * audioBuffer.numberOfChannels));
        metadata.estimatedLoudness = 20 * Math.log10(metadata.rmsLevel);
        
        // 檢測靜音或低音量
        metadata.isSilent = metadata.rmsLevel < 0.001;
        metadata.isLowVolume = metadata.rmsLevel < 0.01;
        
        return metadata;
    }

    /**
     * 備用分析方法 (使用 HTML Audio 元素)
     */
    async fallbackAudioAnalysis(file, metadata) {
        return new Promise((resolve, reject) => {
            const audio = new Audio();
            const url = URL.createObjectURL(file);
            
            audio.addEventListener('loadedmetadata', () => {
                metadata.duration = audio.duration;
                metadata.fallbackMode = true;
                
                // 估算位元率
                if (metadata.duration > 0) {
                    metadata.estimatedBitrate = Math.round((file.size * 8) / metadata.duration);
                }
                
                URL.revokeObjectURL(url);
                resolve(metadata);
            });
            
            audio.addEventListener('error', () => {
                URL.revokeObjectURL(url);
                reject(new Error('HTML Audio 元素分析失敗'));
            });
            
            audio.src = url;
        });
    }

    /**
     * 檢測音訊格式
     */
    detectAudioFormat(uint8Array) {
        // WAV 格式檢測 (RIFF header)
        if (uint8Array[0] === 0x52 && uint8Array[1] === 0x49 && 
            uint8Array[2] === 0x46 && uint8Array[3] === 0x46 &&
            uint8Array[8] === 0x57 && uint8Array[9] === 0x41 && 
            uint8Array[10] === 0x56 && uint8Array[11] === 0x45) {
            return {
                format: 'WAV',
                codec: 'PCM',
                matches_declared: this.audioFile?.type.includes('wav') || false
            };
        }
        
        // MP3 格式檢測
        if ((uint8Array[0] === 0xFF && (uint8Array[1] & 0xE0) === 0xE0) || // MPEG frame
            (uint8Array[0] === 0x49 && uint8Array[1] === 0x44 && uint8Array[2] === 0x33)) { // ID3
            return {
                format: 'MP3',
                codec: 'MPEG Layer III',
                matches_declared: this.audioFile?.type.includes('mp3') || false
            };
        }
        
        // WebM 格式檢測 (EBML header)
        if (uint8Array[0] === 0x1A && uint8Array[1] === 0x45 && 
            uint8Array[2] === 0xDF && uint8Array[3] === 0xA3) {
            return {
                format: 'WebM',
                codec: 'Opus/VP8',
                matches_declared: this.audioFile?.type.includes('webm') || false
            };
        }
        
        // OGG 格式檢測
        if (uint8Array[0] === 0x4F && uint8Array[1] === 0x67 && 
            uint8Array[2] === 0x67 && uint8Array[3] === 0x53) {
            return {
                format: 'OGG',
                codec: 'Opus/Vorbis',
                matches_declared: this.audioFile?.type.includes('ogg') || false
            };
        }
        
        // M4A/AAC 格式檢測 (ftyp header)
        if (uint8Array[4] === 0x66 && uint8Array[5] === 0x74 && 
            uint8Array[6] === 0x79 && uint8Array[7] === 0x70) {
            return {
                format: 'M4A/AAC',
                codec: 'AAC',
                matches_declared: this.audioFile?.type.includes('m4a') || this.audioFile?.type.includes('aac') || false
            };
        }
        
        return {
            format: 'Unknown',
            codec: 'Unknown',
            matches_declared: false
        };
    }

    /**
     * 評估是否需要轉換
     */
    assessConversionNeeded(metadata) {
        const conversionReasons = [];
        
        // 檢查採樣率 (推薦 16kHz 或 44.1kHz)
        if (metadata.sampleRate && metadata.sampleRate !== 16000 && metadata.sampleRate !== 44100) {
            conversionReasons.push(`採樣率 ${metadata.sampleRate} Hz 可能需要轉換為 16kHz`);
        }
        
        // 檢查聲道數 (推薦單聲道)
        if (metadata.channels && metadata.channels > 1) {
            conversionReasons.push(`${metadata.channels} 聲道，建議轉換為單聲道`);
        }
        
        // 檢查格式相容性
        if (metadata.detectedFormat && !['WAV', 'MP3', 'M4A/AAC'].includes(metadata.detectedFormat)) {
            conversionReasons.push(`格式 ${metadata.detectedFormat} 可能需要轉換`);
        }
        
        // 檢查檔案大小 (過大可能需要壓縮)
        if (metadata.fileSize > 10 * 1024 * 1024) { // 10MB
            conversionReasons.push(`檔案大小 ${ASRHubCommon.formatFileSize(metadata.fileSize)} 較大，可能需要壓縮`);
        }
        
        return {
            needed: conversionReasons.length > 0,
            reasons: conversionReasons
        };
    }

    /**
     * 發送音訊 metadata 給後端
     */
    async sendAudioMetadata(metadata) {
        try {
            // 創建一個臨時 session_id 用於 metadata (如果還沒有的話)
            const sessionId = this.sessionId || this.generateSessionId();
            
            // 分發 AUDIO_METADATA action 給後端
            await this.dispatchAction(this.ACTIONS.AUDIO_METADATA, {
                session_id: sessionId,
                audio_metadata: metadata
            });
            
            this.log('音訊 metadata 已發送給後端', 'success');
            
            // 記錄重要的轉換建議
            if (metadata.conversionNeeded && metadata.conversionNeeded.needed) {
                this.log('轉換建議:', 'warning');
                metadata.conversionNeeded.reasons.forEach(reason => {
                    this.log(`  • ${reason}`, 'warning');
                });
            }
            
        } catch (error) {
            this.log(`發送 metadata 失敗: ${error.message}`, 'error');
            throw error;
        }
    }

    /**
     * 顯示音訊 metadata 在 UI 上
     */
    displayAudioMetadata(metadata) {
        // 更新檔案資訊顯示
        let infoText = `${metadata.fileName} (${ASRHubCommon.formatFileSize(metadata.fileSize)})`;
        
        if (metadata.duration) {
            const duration = Math.round(metadata.duration * 100) / 100;
            infoText += ` • ${duration}s`;
        }
        
        if (metadata.sampleRate) {
            infoText += ` • ${metadata.sampleRate} Hz`;
        }
        
        if (metadata.channels) {
            const channelText = metadata.channels === 1 ? '單聲道' : `${metadata.channels} 聲道`;
            infoText += ` • ${channelText}`;
        }
        
        if (metadata.estimatedBitrate) {
            const bitrate = Math.round(metadata.estimatedBitrate / 1000);
            infoText += ` • ~${bitrate} kbps`;
        }
        
        this.elements.fileInfo.textContent = infoText;
        
        // 記錄詳細分析結果
        this.log('音訊檔案分析結果:', 'info');
        this.log(`  格式: ${metadata.detectedFormat} (${metadata.estimatedCodec})`, 'info');
        if (metadata.duration) this.log(`  時長: ${Math.round(metadata.duration * 100) / 100} 秒`, 'info');
        if (metadata.sampleRate) this.log(`  採樣率: ${metadata.sampleRate} Hz`, 'info');
        if (metadata.channels) this.log(`  聲道數: ${metadata.channels}`, 'info');
        if (metadata.estimatedBitrate) this.log(`  估算位元率: ${Math.round(metadata.estimatedBitrate / 1000)} kbps`, 'info');
        
        // 顯示音量分析結果
        if (metadata.rmsLevel !== undefined) {
            if (metadata.isSilent) {
                this.log('  ⚠️ 音訊似乎是靜音的', 'warning');
            } else if (metadata.isLowVolume) {
                this.log('  ⚠️ 音訊音量較低', 'warning');
            } else {
                this.log('  🔊 音量正常', 'info');
            }
        }
        
        // 顯示格式匹配狀態
        if (metadata.formatMatches === false) {
            this.log(`  ⚠️ 檔案副檔名與實際格式不匹配`, 'warning');
        }
        
        if (metadata.fallbackMode) {
            this.log('  ℹ️ 使用備用分析模式', 'info');
        }
    }

    /**
     * 獲取檔案副檔名
     */
    getFileExtension(filename) {
        const lastDot = filename.lastIndexOf('.');
        return lastDot !== -1 ? filename.substring(lastDot + 1).toLowerCase() : '';
    }
    
    async handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        this.audioBlob = null;
        this.audioChunks = [];
        this.isFileUpload = true;
        this.audioFile = file;
        
        const displaySize = ASRHubCommon.formatFileSize(file.size);
        
        this.elements.fileInfo.textContent = `已選擇: ${file.name} (${displaySize})`;
        this.elements.fileInfo.classList.add('has-file');
        
        // 立即分析音訊檔案規格
        this.updateStatus('分析音訊檔案規格...', 'analyzing');
        try {
            const audioMetadata = await this.analyzeAudioFile(file);
            this.log('音訊檔案分析完成', 'success');
            
            // 發送 metadata 給後端
            await this.sendAudioMetadata(audioMetadata);
            
            // 更新 UI 顯示更詳細的資訊
            this.displayAudioMetadata(audioMetadata);
            
        } catch (error) {
            this.log(`音訊分析失敗: ${error.message}`, 'error');
            this.updateStatus('音訊分析失敗，但仍可進行辨識', 'warning');
        }
        
        this.displayAudioInfo();
        this.elements.startRecognitionBtn.disabled = false;
        
        this.elements.results.textContent = '';
        this.elements.results.classList.remove('has-content');
        
        this.updateStatus('檔案已載入，準備就緒', 'ready');
        this.log(`載入檔案: ${file.name} (${displaySize})`, 'success');
    }
    
    // ==================== 辨識相關方法 ====================
    
    async startRecognition() {
        if (!this.audioBlob && !this.audioFile) {
            this.log('沒有音訊資料', 'error');
            return;
        }
        
        this.updateStatus('連接中', 'connecting');
        this.elements.results.textContent = '';
        this.elements.results.classList.remove('has-content');
        
        try {
            await this.connect();
            
            // 總是創建新的 session 以確保狀態乾淨
            this.sessionId = this.generateSessionId();
            
            // 根據音訊來源選擇正確的 strategy
            // const strategy = this.isFileUpload ? 'batch' : 'non_streaming';
            const strategy ='batch' ; // 目前只支援 batch 模式
            
            // 先創建 session，確保後端有 session 狀態
            await this.dispatchAction(this.ACTIONS.CREATE_SESSION, {
                session_id: this.sessionId,
                strategy: strategy
            });
            
            // 等待一小段時間確保 session 創建完成
            await this.sleep(100);
            
            this.log(`Session 創建成功: ${this.sessionId} (strategy: ${strategy})`, 'success');
            
            await this.sendAudioForRecognition();
        } catch (error) {
            this.log(`辨識失敗: ${error.message}`, 'error');
            this.updateStatus('辨識失敗', 'error');
        }
    }
    
    // ==================== 連線管理方法 ====================
    
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
        
        // 監聽事件驅動的 actions
        this.connection.on('action', (data) => {
            this.handleSocketIOAction(data);
        });
        
        this.connection.on('event', (data) => {
            this.handleSocketIOEvent(data);
        });
        
        // 向後兼容：監聽 final_result 事件
        this.connection.on('final_result', (data) => {
            this.log('收到辨識結果 (final_result)', 'info');
            if (data.text) {
                this.elements.results.textContent = data.text;
                this.elements.results.classList.add('has-content');
                this.updateStatus('辨識完成', 'complete');
                this.log('辨識完成', 'success');
            }
        });
        
        // 監聽其他事件
        this.connection.on('audio_received', (data) => {
            this.log(`音訊塊已接收: ${data.size} bytes`, 'debug');
        });
        
        this.connection.on('error', (data) => {
            this.log(`錯誤: ${data.error}`, 'error');
            this.updateStatus('發生錯誤', 'error');
        });
        
        this.connection.on('disconnect', () => {
            this.log('Socket.io 連接斷開', 'warning');
            this.updateConnectionStatus(false);
        });
    }
    
    connectHTTPSSE(resolve, reject) {
        this.connection = { protocol: 'http_sse' };
        this.updateConnectionStatus(true);
        this.log('HTTP API 模式已啟用', 'success');
        resolve();
    }
    
    // ==================== 音訊傳送方法（符合新架構） ====================
    
    async sendAudioForRecognition() {
        if (this.protocol === 'websocket') {
            await this.sendWebSocketAudio();
        } else if (this.protocol === 'socketio') {
            await this.sendSocketIOAudio();
        } else if (this.protocol === 'http_sse') {
            await this.sendHTTPSSEAudio();
        }
    }
    
    async sendWebSocketAudio() {
        try {
            // 確保有 session_id
            if (!this.sessionId) {
                throw new Error('Session ID 不存在，請先創建 session');
            }
            
            // 將音訊轉換為 ArrayBuffer
            const audioSource = this.audioFile || this.audioBlob;
            const arrayBuffer = await audioSource.arrayBuffer();
            
            this.log(`準備發送音訊，Session ID: ${this.sessionId}`, 'info');
            
            // 使用新的 Chunk Upload 流程：
            // 1. 分發 CHUNK_UPLOAD_START - 準備接收音訊塊
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_START, {
                session_id: this.sessionId
            });
            this.log(`已開始 chunk upload 流程 (session: ${this.sessionId})`, 'info');
            
            // 等待一下確保後端處理 CHUNK_UPLOAD_START
            await this.sleep(50);
            
            // 2. 將音訊數據以塊形式推送到後端的 AudioQueueManager
            await this.uploadAudioData(arrayBuffer);
            
            // 等待所有音訊塊上傳完成
            await this.sleep(100);
            
            // 3. 分發 CHUNK_UPLOAD_DONE - 觸發轉譯流程：
            // chunk_upload_done → transcription_done (與 upload_file_done 等價)
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_DONE, {
                session_id: this.sessionId
            });
            
            this.log(`已完成 chunk upload (session: ${this.sessionId})，等待辨識`, 'info');
            this.updateStatus('處理中', 'processing');
            
        } catch (error) {
            this.log(`發送音訊時發生錯誤: ${error.message}`, 'error');
            this.updateStatus('發送失敗', 'error');
        }
    }
    
    async sendSocketIOAudio() {
        try {
            // 將音訊轉換為 ArrayBuffer
            const audioSource = this.audioFile || this.audioBlob;
            const arrayBuffer = await audioSource.arrayBuffer();
            
            // 使用新的 Chunk Upload 流程：
            // 1. 分發 CHUNK_UPLOAD_START - 準備接收音訊塊
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_START, {
                session_id: this.sessionId
            });
            this.log('已開始 Socket.IO chunk upload 流程', 'info');
            
            // 2. 將音訊數據以塊形式推送到後端的 AudioQueueManager
            await this.uploadAudioData(arrayBuffer);
            
            // 3. 分發 CHUNK_UPLOAD_DONE - 觸發轉譯流程
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_DONE, {
                session_id: this.sessionId
            });
            
            this.log('已完成 Socket.IO chunk upload，等待辨識', 'info');
            this.updateStatus('處理中', 'processing');
            
        } catch (error) {
            this.log(`Socket.IO 音訊發送錯誤: ${error.message}`, 'error');
            this.updateStatus('發送失敗', 'error');
        }
    }
    
    async sendHTTPSSEAudio() {
        try {
            const audioSource = this.audioFile || this.audioBlob;
            
            // 使用新的事件驅動 API endpoint
            this.updateStatus('上傳音訊中', 'uploading');
            
            // 建立 SSE 連接監聽事件
            if (!this.sessionId) {
                this.sessionId = this.generateSessionId();
            }
            
            await this.createSSEConnection();
            
            // 上傳音訊並分發 action
            const formData = new FormData();
            
            if (this.isFileUpload) {
                formData.append('audio', this.audioFile, this.audioFile.name);
            } else {
                formData.append('audio', this.audioBlob, 'recording.webm');
            }
            
            formData.append('session_id', this.sessionId);
            
            // 上傳音訊到 audio endpoint
            const uploadResponse = await fetch(`${this.httpSSEUrl}/audio/${this.sessionId}`, {
                method: 'POST',
                body: formData
            });
            
            if (!uploadResponse.ok) {
                throw new Error(`音訊上傳失敗: ${uploadResponse.status}`);
            }
            
            // 使用新的 Chunk Upload 流程：
            // HTTP 模式先上傳檔案到 audio endpoint，然後觸發 chunk upload 流程
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_START, {
                session_id: this.sessionId
            });
            
            // HTTP 模式的音訊已經透過 FormData 上傳，現在觸發處理
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_DONE, {
                session_id: this.sessionId
            });
            
            this.log('已上傳音訊並完成 HTTP chunk upload 流程', 'success');
            
        } catch (error) {
            this.log(`HTTP 辨識錯誤: ${error.message}`, 'error');
            this.updateStatus('辨識失敗', 'error');
        }
    }
    
    /**
     * 上傳音訊數據到後端的 AudioQueueManager
     */
    async uploadAudioData(arrayBuffer) {
        const uint8Array = new Uint8Array(arrayBuffer);
        const chunkSize = 4096;
        let sentChunks = 0;
        
        this.log(`開始上傳音訊數據，總大小: ${uint8Array.length} bytes`, 'info');
        
        for (let i = 0; i < uint8Array.length; i += chunkSize) {
            const chunk = uint8Array.slice(i, i + chunkSize);
            const chunkId = Math.floor(i / chunkSize);
            
            if (this.protocol === 'websocket') {
                // WebSocket 模式：發送音訊塊
                const message = {
                    type: 'audio_chunk',
                    session_id: this.sessionId,
                    audio: this.arrayBufferToBase64(chunk),
                    chunk_id: chunkId
                };
                this.connection.send(JSON.stringify(message));
                
                // 每隔幾個塊記錄一次
                if (chunkId % 10 === 0) {
                    this.log(`發送音訊塊 ${chunkId} (session: ${this.sessionId})`, 'debug');
                }
            } else if (this.protocol === 'socketio') {
                // Socket.io 模式：emit 音訊塊
                this.connection.emit('audio_chunk', {
                    session_id: this.sessionId,
                    audio: this.arrayBufferToBase64(chunk),
                    chunk_id: chunkId
                });
            }
            
            sentChunks++;
            
            // 更新進度
            const progress = Math.round((i + chunk.length) / uint8Array.length * 100);
            this.updateStatus(`上傳中: ${progress}%`, 'uploading');
            
            // 控制發送速度，避免淹沒後端
            await this.sleep(5);
        }
        
        this.log(`音訊上傳完成，共 ${uint8Array.length} bytes，${sentChunks} 個分塊 (session: ${this.sessionId})`, 'success');
    }
    
    // ==================== 事件處理方法 ====================
    
    handleWebSocketMessage(data) {
        try {
            const message = JSON.parse(data);
            
            if (message.type === 'action' || message.type === 'event') {
                this.handleAction(message.action || message);
            } else {
                // 向後兼容舊的消息格式
                this.log(`收到訊息: ${message.type}`, 'info');
            }
        } catch (error) {
            this.log(`解析訊息失敗: ${error.message}`, 'error');
        }
    }
    
    handleSocketIOAction(action) {
        this.handleAction(action);
    }
    
    handleSocketIOEvent(event) {
        this.handleAction(event);
    }
    
    handleHTTPSSEAction(action) {
        this.handleAction(action);
    }
    
    /**
     * 統一的 action 處理器
     */
    handleAction(action) {
        this.log(`收到 Action: ${action.type}`, 'info');
        
        switch (action.type) {
            case this.ACTIONS.BEGIN_TRANSCRIPTION:
                this.updateStatus('開始辨識', 'processing');
                break;
                
            case this.ACTIONS.TRANSCRIPTION_DONE:
                this.handleTranscriptionDone(action.payload);
                break;
                
            case this.ACTIONS.UPLOAD_FILE_DONE:
                this.log('檔案處理完成，等待辨識', 'info');
                this.updateStatus('辨識中', 'processing');
                break;
                
            case this.ACTIONS.CHUNK_UPLOAD_START:
                this.log('開始接收音訊塊', 'info');
                this.updateStatus('準備處理音訊', 'processing');
                break;
                
            case this.ACTIONS.CHUNK_UPLOAD_DONE:
                this.log('音訊塊處理完成，開始辨識', 'info');
                this.updateStatus('辨識中', 'processing');
                break;
                
            case this.ACTIONS.AUDIO_METADATA:
                this.handleAudioMetadata(action.payload);
                break;
                
            case this.ACTIONS.ERROR:
                this.handleError(action.payload);
                break;
                
            default:
                this.log(`未處理的 Action: ${action.type}`, 'warning');
        }
    }
    
    handleTranscriptionResult(data) {
        this.updateStatus('辨識完成', 'complete');
        
        if (data && data.text) {
            this.elements.results.textContent = data.text;
            this.elements.results.classList.add('has-content');
            this.log(`辨識完成: ${data.text}`, 'success');
            
            // 顯示其他資訊
            if (data.language) {
                this.log(`語言: ${data.language}`, 'info');
            }
            if (data.confidence) {
                this.log(`信心度: ${(data.confidence * 100).toFixed(1)}%`, 'info');
            }
            
            // 重新啟用按鈕
            this.elements.startRecognitionBtn.disabled = false;
            this.elements.startRecordBtn.disabled = false;
            
            // 顯示成功通知
            ASRHubCommon.showNotification('語音辨識完成！', 'success');
        } else {
            this.log('收到空的辨識結果', 'warning');
        }
    }

    handleTranscriptionDone(payload) {
        this.updateStatus('辨識完成', 'complete');
        
        if (payload && payload.result) {
            // 處理辨識結果
            const result = payload.result;
            let text = '';
            
            if (typeof result === 'string') {
                text = result;
            } else if (result.text) {
                text = result.text;
            }
            
            if (text) {
                this.elements.results.textContent = text;
                this.elements.results.classList.add('has-content');
                this.log(`辨識完成: ${text}`, 'success');
                
                // 顯示其他資訊
                if (result.language) {
                    this.log(`語言: ${result.language}`, 'info');
                }
                if (result.confidence) {
                    this.log(`信心度: ${(result.confidence * 100).toFixed(1)}%`, 'info');
                }
                
                // 重新啟用按鈕
                this.elements.startRecognitionBtn.disabled = false;
                this.elements.startRecordBtn.disabled = false;
                
                // 顯示成功通知
                ASRHubCommon.showNotification('語音辨識完成！', 'success');
            }
        } else {
            this.log('收到空的辨識完成事件', 'warning');
        }
    }
    
    handleAudioMetadata(payload) {
        this.log('後端已接收音訊 metadata', 'info');
        
        // 如果後端返回了轉換建議或處理狀態，可以在這裡處理
        if (payload && payload.conversion_strategy) {
            this.log(`後端轉換策略: ${payload.conversion_strategy}`, 'info');
        }
        
        if (payload && payload.processing_optimizations) {
            this.log('後端處理優化:', 'info');
            payload.processing_optimizations.forEach(opt => {
                this.log(`  • ${opt}`, 'info');
            });
        }
        
        if (payload && payload.warnings) {
            payload.warnings.forEach(warning => {
                this.log(`⚠️ ${warning}`, 'warning');
            });
        }
    }
    
    handleError(payload) {
        this.updateStatus('發生錯誤', 'error');
        const errorMessage = payload.error || payload.message || '未知錯誤';
        this.log(`錯誤: ${errorMessage}`, 'error');
    }
    
    // ==================== SSE 連接管理方法 ====================
    
    async createSSEConnection() {
        // 創建和管理 SSE 連接，包含重連機制
        return new Promise((resolve, reject) => {
            try {
                const sseUrl = `${this.httpSSEUrl}/events/${this.sessionId}`;
                this.log(`建立 SSE 連接到: ${sseUrl}`, 'info');
                
                this.sseConnection = new EventSource(sseUrl);
                
                // 連接成功事件
                this.sseConnection.onopen = (event) => {
                    this.log('✅ SSE 連接已建立', 'success');
                    this.updateConnectionStatus(true);
                    resolve();
                };
                
                // 設定事件處理器
                this.sseConnection.addEventListener('action', (event) => {
                    try {
                        const action = JSON.parse(event.data);
                        this.handleHTTPSSEAction(action);
                    } catch (e) {
                        this.log(`解析 action 事件失敗: ${e.message}`, 'error');
                    }
                });
                
                // 監聽辨識完成事件
                this.sseConnection.addEventListener('transcript', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.log(`收到辨識結果: ${data.text}`, 'success');
                        this.handleTranscriptionResult(data);
                    } catch (e) {
                        this.log(`解析 transcript 事件失敗: ${e.message}`, 'error');
                    }
                });
                
                // 監聽狀態變化事件
                this.sseConnection.addEventListener('status', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.log(`狀態更新: ${data.state}`, 'info');
                        this.updateStatus(this.getStatusText(data.state), 'processing');
                    } catch (e) {
                        this.log(`解析 status 事件失敗: ${e.message}`, 'error');
                    }
                });
                
                // 心跳事件
                this.sseConnection.addEventListener('heartbeat', (event) => {
                    this.log('💓 SSE 心跳', 'debug');
                });
                
                // 連線狀態事件
                this.sseConnection.addEventListener('connected', (event) => {
                    this.log('SSE 連線狀態：已連接', 'success');
                });
                
                this.sseConnection.addEventListener('disconnected', (event) => {
                    this.log('SSE 連線狀態：已斷開', 'warning');
                });
                
                // 錯誤處理
                this.sseConnection.onerror = (event) => {
                    console.error('SSE Error Event:', event);
                    
                    // 檢查連接狀態
                    if (this.sseConnection.readyState === EventSource.CONNECTING) {
                        this.log('⏳ SSE 正在重新連接...', 'warning');
                    } else if (this.sseConnection.readyState === EventSource.CLOSED) {
                        this.log('❌ SSE 連接已關閉', 'error');
                        this.updateConnectionStatus(false);
                        
                        // 嘗試重連（如果不是手動關閉）
                        if (!this.manuallyDisconnected) {
                            this.scheduleSSEReconnect();
                        }
                        reject(new Error('SSE 連接失敗'));
                    } else {
                        this.log(`❌ SSE 連接錯誤 (readyState: ${this.sseConnection.readyState})`, 'error');
                        reject(new Error('SSE 連接錯誤'));
                    }
                };
                
                // 設定超時
                setTimeout(() => {
                    if (this.sseConnection.readyState === EventSource.CONNECTING) {
                        this.log('⏰ SSE 連接超時', 'error');
                        this.sseConnection.close();
                        reject(new Error('SSE 連接超時'));
                    }
                }, 10000); // 10 秒超時
                
            } catch (error) {
                this.log(`SSE 連接創建失敗: ${error.message}`, 'error');
                reject(error);
            }
        });
    }
    
    scheduleSSEReconnect() {
        // 安排 SSE 重連
        if (this.sseReconnectTimer) {
            clearTimeout(this.sseReconnectTimer);
        }
        
        const reconnectDelay = 3000; // 3 秒後重連
        this.log(`🔄 將在 ${reconnectDelay/1000} 秒後嘗試重連 SSE`, 'info');
        
        this.sseReconnectTimer = setTimeout(async () => {
            try {
                await this.createSSEConnection();
                this.log('✅ SSE 重連成功', 'success');
            } catch (error) {
                this.log(`❌ SSE 重連失敗: ${error.message}`, 'error');
                // 如果重連失敗，再次安排重連
                this.scheduleSSEReconnect();
            }
        }, reconnectDelay);
    }
    
    closeSSEConnection() {
        // 關閉 SSE 連接
        this.manuallyDisconnected = true;
        
        if (this.sseReconnectTimer) {
            clearTimeout(this.sseReconnectTimer);
            this.sseReconnectTimer = null;
        }
        
        if (this.sseConnection) {
            this.sseConnection.close();
            this.sseConnection = null;
            this.log('SSE 連接已手動關閉', 'info');
        }
    }
    
    // ==================== 輔助方法 ====================
    
    getStatusText(state) {
        const stateMapping = {
            'IDLE': '準備就緒',
            'LISTENING': '等待喚醒',
            'ACTIVATED': '已喚醒',
            'RECORDING': '錄音中',
            'TRANSCRIBING': '辨識中',
            'STREAMING': '串流中',
            'COMPLETED': '辨識完成',
            'ERROR': '發生錯誤',
            'ready': '準備就緒',
            'connecting': '連接中',
            'recording': '錄音中',
            'uploading': '上傳中',
            'processing': '處理中',
            'analyzing': '分析中',
            'complete': '辨識完成',
            'error': '發生錯誤'
        };
        
        return stateMapping[state] || state || '未知狀態';
    }
    
    disconnect() {
        if (this.connection) {
            if (this.protocol === 'websocket') {
                this.connection.close();
            } else if (this.protocol === 'socketio') {
                this.connection.disconnect();
            } else if (this.protocol === 'http_sse') {
                this.closeSSEConnection();
            }
            this.connection = null;
            this.updateConnectionStatus(false);
        }
    }
    
    updateStatus(text, type) {
        ASRHubCommon.updateStatusWithData(this.elements.status, text, type);
        this.log(text, type === 'error' ? 'error' : 'info');
    }
    
    updateConnectionStatus(connected) {
        if (connected) {
            this.elements.connectionStatus.innerHTML = '<i class="fas fa-circle text-green-500 mr-2"></i>已連接';
            this.elements.connectionStatus.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200';
        } else {
            this.elements.connectionStatus.innerHTML = '<i class="fas fa-circle text-red-500 mr-2"></i>未連接';
            this.elements.connectionStatus.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200';
        }
    }
    
    log(message, type = 'info') {
        ASRHubCommon.addLogEntry(this.elements.logs, message, type);
        
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
    
    getSupportedMimeType() {
        const types = [
            'audio/wav',
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4'
        ];
        
        this.log('🔍 检测浏览器音频格式支持:', 'info');
        
        for (const type of types) {
            const isSupported = MediaRecorder.isTypeSupported(type);
            this.log(`  ${type}: ${isSupported ? '✅ 支持' : '❌ 不支持'}`, 'debug');
            
            if (isSupported) {
                this.log(`📋 选择音頻格式: ${type}`, 'info');
                this.log(`⚠️ 注意: 浏览器可能声称支持但实际录制不同格式`, 'warning');
                return type;
            }
        }
        
        this.log('❌ 无支持的音频格式，使用預設格式', 'error');
        return null;
    }
    
    async verifyActualAudioFormat() {
        if (!this.audioBlob) return;
        
        try {
            this.log('🔬 验证实际录制的音频格式...', 'info');
            
            // 读取前16个字节检查文件头
            const arrayBuffer = await this.audioBlob.slice(0, 16).arrayBuffer();
            const uint8Array = new Uint8Array(arrayBuffer);
            const header = Array.from(uint8Array)
                .map(b => b.toString(16).padStart(2, '0'))
                .join(' ');
            
            this.log(`📊 音频文件头 (前16字节): ${header}`, 'info');
            this.log(`📋 声明的MIME类型: ${this.audioBlob.type}`, 'info');
            this.log(`📏 音频大小: ${this.audioBlob.size} bytes`, 'info');
            
            // 检测实际格式
            const actualFormat = this.detectActualFormat(uint8Array);
            this.log(`🎯 检测到的实际格式: ${actualFormat.format} (${actualFormat.codec})`, actualFormat.matches_declared ? 'success' : 'error');
            
            if (!actualFormat.matches_declared) {
                this.log(`⚠️ 格式不匹配! 声明: ${this.audioBlob.type}, 实际: ${actualFormat.format}`, 'error');
                this.log(`💡 建议: 后端应强制处理为 ${actualFormat.format} 格式`, 'warning');
            }
            
            // 发送格式信息到后端 (用于调试)
            this.actualAudioFormat = {
                declared_type: this.audioBlob.type,
                actual_format: actualFormat.format,
                codec: actualFormat.codec,
                size: this.audioBlob.size,
                header: header,
                matches_declared: actualFormat.matches_declared
            };
            
        } catch (error) {
            this.log(`❌ 格式验证失败: ${error.message}`, 'error');
        }
    }
    
    detectActualFormat(uint8Array) {
        // WAV 格式检测 (RIFF header)
        if (uint8Array[0] === 0x52 && uint8Array[1] === 0x49 && 
            uint8Array[2] === 0x46 && uint8Array[3] === 0x46 &&
            uint8Array[8] === 0x57 && uint8Array[9] === 0x41 && 
            uint8Array[10] === 0x56 && uint8Array[11] === 0x45) {
            return {
                format: 'WAV',
                codec: 'PCM or other',
                matches_declared: this.audioBlob.type.includes('wav')
            };
        }
        
        // WebM 格式检测 (EBML header)
        if (uint8Array[0] === 0x1A && uint8Array[1] === 0x45 && 
            uint8Array[2] === 0xDF && uint8Array[3] === 0xA3) {
            return {
                format: 'WebM',
                codec: 'Opus or VP8/VP9',
                matches_declared: this.audioBlob.type.includes('webm')
            };
        }
        
        // Ogg 格式检测
        if (uint8Array[0] === 0x4F && uint8Array[1] === 0x67 && 
            uint8Array[2] === 0x67 && uint8Array[3] === 0x53) {
            return {
                format: 'OGG',
                codec: 'Opus or Vorbis',
                matches_declared: this.audioBlob.type.includes('ogg')
            };
        }
        
        return {
            format: 'Unknown',
            codec: 'Unknown',
            matches_declared: false
        };
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    const client = new EventDrivenASRClient();
    console.log('ASR Event-Driven Client 初始化完成');
    console.log('符合 PyStoreX 純事件驅動架構');
    console.log('新事件流程: chunk_upload_start → [audio chunks] → chunk_upload_done → transcription_done');
    console.log('兼容舊流程: upload_file → upload_file_done → transcription_done');
});