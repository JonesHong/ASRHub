// ASR Hub Frontend Application - 重構後的事件驅動架構
// 清晰的關注點分離: 錄音、上傳、UI管理、協議通訊

class ASRHubClient {
    constructor() {
        // 核心模組
        this.audioRecorder = new AudioRecorder();
        this.audioUploader = new AudioUploader();
        this.uiManager = new UIManager();
        this.protocolAdapter = null;
        
        // 應用配置 - 統一的策略設定
        this.config = {
            strategy: 'batch',  // 統一的批次策略，所有協議都使用相同策略
            chunkSize: 4096,    // 統一的分塊大小（在協議適配器中使用）
            progressInterval: 10, // 進度報告間隔（每10塊報告一次）
            auto_transcribe: false  // 錄音結束後不自動開始辨識，等待用戶操作
        };
        
        // 應用狀態
        this.currentProtocol = 'websocket';
        this.sessionId = null;
        this.currentAudioSource = null; // 當前的音訊來源 (錄音或檔案)
        this.isFileUpload = false;
        this.audioMetadata = null; // 儲存音訊 metadata，在開始辨識時發送
        this.debugMode = false; // 除錯模式，控制詳細日誌顯示
        this.totalChunks = 0; // 總音訊塊數，用於進度顯示
        
        // 事件驅動架構 - 動作類型定義（對應後端 PyStoreX actions）
        // 保持舊的 action 名稱以維持相容性，但在發送時會轉換為新的獨立事件格式
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
        
        this.initialize();
    }
    
    /**
     * 初始化應用
     */
    initialize() {
        this.setupEventListeners();
        this.setupModuleEventHandlers();
        this.initializeProtocolAdapter();
        
        // 初始化 UI 狀態 - 設置自動辨識開關
        this.initializeAutoTranscribeUI();
        
        this.uiManager.addLog('ASR Hub 客戶端初始化完成', 'success');
        this.uiManager.addLog('已更新為新的獨立事件架構（移除 action 事件）', 'info');
        
        // 記錄初始辨識模式
        const mode = this.config.auto_transcribe ? '自動辨識' : '手動辨識';
        this.uiManager.addLog(`初始辨識模式: ${mode}`, 'info');
    }
    
    /**
     * 設定 UI 事件監聽器
     */
    setupEventListeners() {
        this.uiManager.setEventListeners({
            onProtocolChange: (protocol) => this.handleProtocolChange(protocol),
            onAutoTranscribeChange: (enabled) => this.handleAutoTranscribeChange(enabled),
            onStartRecording: () => this.handleStartRecording(),
            onStopRecording: () => this.handleStopRecording(),
            onStartRecognition: () => this.handleStartRecognition(),
            onFileSelect: (file) => this.handleFileSelect(file)
        });
    }
    
    /**
     * 設定模組間的事件處理器
     */
    setupModuleEventHandlers() {
        // 錄音模組事件處理
        this.audioRecorder.onRecordingStart = () => {
            this.uiManager.updateStatus('錄音中', 'recording');
            this.uiManager.setRecordingState(true);
            this.uiManager.showNotification('已開始錄音', 'success');
            this.uiManager.addLog('開始錄音', 'success');
            
            // 清除檔案相關狀態
            this.clearFileState();
        };
        
        this.audioRecorder.onRecordingStop = async (audioBlob, duration) => {
            this.currentAudioSource = audioBlob;
            this.isFileUpload = false;
            
            // 創建錄音的元資料
            this.audioMetadata = {
                fileName: `recording_${Date.now()}.webm`,
                fileSize: audioBlob.size,
                mimeType: audioBlob.type || 'audio/webm',
                fileExtension: 'webm',
                duration: duration,
                sampleRate: 16000,  // 錄音設定的採樣率
                channels: 1,         // 錄音設定的單聲道
                detectedFormat: 'WebM',
                estimatedCodec: 'Opus',
                source: 'recording',
                analyzed_at: new Date().toISOString(),
                conversionNeeded: {
                    needed: false,
                    reasons: []
                }
            };
            
            this.uiManager.setRecordingState(false);
            this.uiManager.displayAudioInfo(audioBlob, false);
            
            const durationText = duration ? ` (${duration.toFixed(1)}s)` : '';
            this.uiManager.addLog(`錄音結束${durationText}`, 'success');
            this.uiManager.addLog(`錄音元資料: 採樣率 ${this.audioMetadata.sampleRate}Hz, ${this.audioMetadata.channels} 聲道`, 'info');
            
            // 檢查是否啟用自動辨識
            if (this.config.strategy === 'batch' && this.config.auto_transcribe) {
                this.uiManager.updateStatus('自動上傳音訊...', 'uploading');
                this.uiManager.showNotification('批次模式：自動開始辨識', 'info');
                this.uiManager.addLog('批次模式：自動開始上傳和辨識', 'info');
                
                // 自動開始批次辨識流程
                try {
                    await this.handleStartRecognition();
                } catch (error) {
                    this.uiManager.addLog(`自動辨識失敗: ${error.message}`, 'error');
                    this.uiManager.updateStatus('自動辨識失敗', 'error');
                }
            } else {
                // 手動模式：等待用戶點擊開始辨識
                this.uiManager.updateStatus('準備就緒', 'ready');
                this.uiManager.showNotification('錄音完成，請點擊「開始辨識」', 'success');
                this.uiManager.addLog('錄音完成，等待手動開始辨識', 'info');
            }
        };
        
        this.audioRecorder.onRecordingError = (error) => {
            this.uiManager.updateStatus('錄音失敗', 'error');
            this.uiManager.setRecordingState(false);
            this.uiManager.addLog(error, 'error');
        };
        
        // 檔案上傳模組事件處理
        this.audioUploader.onFileSelected = (file) => {
            const displaySize = ASRHubCommon.formatFileSize(file.size);
            this.uiManager.displayFileInfo(`已選擇: ${file.name} (${displaySize})`, true);
            this.uiManager.updateStatus('分析音訊檔案規格...', 'analyzing');
            this.uiManager.addLog(`載入檔案: ${file.name} (${displaySize})`, 'success');
            
            // 清除錄音相關狀態
            this.clearRecordingState();
        };
        
        this.audioUploader.onFileAnalyzed = async (metadata) => {
            this.currentAudioSource = this.audioUploader.getSelectedFile();
            this.isFileUpload = true;
            
            // 更新 UI 顯示更詳細的資訊
            this.uiManager.displayFileInfo(this.audioUploader.getDisplayInfo(), true);
            this.uiManager.displayAudioInfo(this.currentAudioSource, true);
            this.uiManager.updateStatus('檔案已載入，準備就緒', 'ready');
            this.uiManager.clearResults();
            
            // 確保按鈕狀態正確 - 檔案載入後應該可以開始辨識
            this.uiManager.setProcessingState(false);  // 這會啟用「開始辨識」按鈕
            
            this.uiManager.addLog('音訊檔案分析完成', 'success');
            this.displayAudioMetadataLogs(metadata);
            
            // 儲存 metadata，但不自動發送給後端
            // metadata 將在用戶點擊「開始辨識」時才發送
            this.audioMetadata = metadata;
            this.uiManager.addLog('檔案已準備就緒，請點擊「開始辨識」', 'info');
            
            // 檢查是否啟用自動辨識（僅針對檔案上傳）
            if (this.config.auto_transcribe) {
                this.uiManager.showNotification('自動辨識模式：準備開始辨識', 'info');
                this.uiManager.addLog('自動辨識模式：準備開始辨識', 'info');
                
                // 自動開始辨識流程
                try {
                    await this.handleStartRecognition();
                } catch (error) {
                    this.uiManager.addLog(`自動辨識失敗: ${error.message}`, 'error');
                    this.uiManager.updateStatus('自動辨識失敗', 'error');
                }
            } else {
                // 手動模式：提示用戶點擊按鈕
                this.uiManager.showNotification('檔案已分析完成，請點擊「開始辨識」', 'success');
            }
        };
        
        this.audioUploader.onAnalysisError = (error) => {
            this.uiManager.addLog(error, 'error');
            this.uiManager.updateStatus('音訊分析失敗，但仍可進行辨識', 'warning');
        };
    }
    
    /**
     * 初始化協議適配器
     */
    initializeProtocolAdapter() {
        this.protocolAdapter = ProtocolAdapterFactory.create(this.currentProtocol);
        this.setupProtocolEventHandlers();
    }
    
    /**
     * 設定協議適配器事件處理器
     */
    setupProtocolEventHandlers() {
        if (!this.protocolAdapter) return;
        
        this.protocolAdapter.onConnected = (protocolInfo) => {
            this.uiManager.updateConnectionStatus(true, protocolInfo);
            this.uiManager.addLog(`${protocolInfo} 連接成功`, 'success');
        };
        
        this.protocolAdapter.onDisconnected = () => {
            this.uiManager.updateConnectionStatus(false);
            this.uiManager.addLog('連接已斷開', 'warning');
        };
        
        this.protocolAdapter.onMessage = (message) => {
            this.handleProtocolMessage(message);
        };
        
        this.protocolAdapter.onError = (error) => {
            this.uiManager.addLog(error, 'error');
            this.uiManager.updateStatus('連接錯誤', 'error');
        };
    }
    
    // ==================== 事件處理方法 ====================
    
    /**
     * 處理自動辨識開關變化
     */
    handleAutoTranscribeChange(enabled) {
        this.config.auto_transcribe = enabled;
        const mode = enabled ? '自動辨識' : '手動辨識';
        this.uiManager.addLog(`辨識模式切換為: ${mode}`, 'info');
        
        if (enabled) {
            this.uiManager.addLog('提示：錄音結束後將自動開始辨識', 'info');
        } else {
            this.uiManager.addLog('提示：錄音結束後需手動點擊「開始辨識」', 'info');
        }
    }
    
    /**
     * 處理協議切換
     */
    async handleProtocolChange(protocol) {
        this.currentProtocol = protocol;
        this.uiManager.addLog(`切換通訊協定為: ${protocol}`, 'info');
        
        // 斷開現有連接
        if (this.protocolAdapter) {
            await this.protocolAdapter.disconnect();
        }
        
        // 創建新的協議適配器
        this.initializeProtocolAdapter();
    }
    
    /**
     * 檢查是否需要創建新 session
     */
    async checkIfNeedNewSession() {
        // 如果沒有 sessionId，需要創建新 session
        if (!this.sessionId) {
            this.uiManager.addLog('沒有現有 session，需要創建新的', 'info');
            return true;
        }
        
        // 對於不同協議的檢查邏輯
        switch (this.currentProtocol) {
            case 'http_sse':
                // HTTP SSE: 檢查 SSE 連接是否仍然有效
                const adapter = this.protocolAdapter;
                if (!adapter.sseConnection || 
                    adapter.sseConnection.readyState === EventSource.CLOSED ||
                    adapter.activeSseSessionId !== this.sessionId) {
                    this.uiManager.addLog('SSE 連接無效或 session 不匹配，需要新 session', 'info');
                    return true;
                }
                // SSE 連接有效且 session 匹配，可以重用
                return false;
                
            case 'websocket':
            case 'socketio':
                // WebSocket 和 Socket.IO: 檢查連接是否仍然有效
                if (!this.protocolAdapter || !this.protocolAdapter.isConnected) {
                    this.uiManager.addLog('連接已斷開，需要新 session', 'info');
                    return true;
                }
                // 連接有效，可以重用 session
                return false;
                
            default:
                // 默認：總是創建新 session
                return true;
        }
    }
    
    /**
     * 創建新的 session
     */
    async createNewSession() {
        try {
            // 確保已連接 (isConnected 是屬性，不是方法)
            if (!this.protocolAdapter || !this.protocolAdapter.isConnected) {
                await this.protocolAdapter.connect();
            }
            
            // 生成新的 session ID
            this.sessionId = this.protocolAdapter.generateSessionId();
            
            // 發送創建 session 事件給後端
            await this.dispatchEvent(this.ACTIONS.CREATE_SESSION, {
                session_id: this.sessionId,
                strategy: this.config.strategy
            });
            
            // 對於 HTTP SSE，創建 SSE 連接
            if (this.currentProtocol === 'http_sse') {
                await this.protocolAdapter.createSSEConnection(this.sessionId);
                this.uiManager.addLog(`SSE 連接已建立 (Session: ${this.sessionId})`, 'success');
            }
            
            this.uiManager.addLog(`Session 已創建: ${this.sessionId}`, 'info');
            return this.sessionId;
        } catch (error) {
            console.error('創建 session 失敗:', error);
            throw error;
        }
    }
    
    /**
     * 處理開始錄音
     */
    async handleStartRecording() {
        try {
            // 純前端錄音，不創建 session，不發送事件給後端
            // Session 只在開始辨識時創建
            this.uiManager.addLog('前端開始錄音（不通知後端）', 'info');
            await this.audioRecorder.startRecording();
        } catch (error) {
            this.uiManager.addLog(`錄音失敗: ${error.message}`, 'error');
            this.uiManager.updateStatus('錄音失敗', 'error');
        }
    }
    
    /**
     * 處理停止錄音
     */
    async handleStopRecording() {
        // 純前端停止錄音，不發送事件給後端
        this.uiManager.addLog('前端停止錄音（不通知後端）', 'info');
        if (this.audioRecorder.stopRecording()) {
            // 錄音停止成功，元資料會在 onRecordingStop 回調中生成
        }
    }
    
    /**
     * 處理檔案選擇
     */
    async handleFileSelect(file) {
        try {
            await this.audioUploader.handleFileSelect(file);
        } catch (error) {
            this.uiManager.addLog(`檔案處理失敗: ${error.message}`, 'error');
        }
    }
    
    /**
     * 處理開始辨識
     */
    async handleStartRecognition() {
        if (!this.currentAudioSource) {
            this.uiManager.addLog('沒有音訊資料', 'error');
            return;
        }
        
        try {
            this.uiManager.updateStatus('連接中', 'connecting');
            this.uiManager.clearResults();
            this.uiManager.setProcessingState(true);
            
            // 檢查是否需要創建新 session
            // 對於 HTTP SSE，如果已有 session 且 SSE 連接仍然有效，則重用
            const needNewSession = await this.checkIfNeedNewSession();
            
            if (needNewSession) {
                // 創建新 session
                await this.createNewSession();
                await this.sleep(100); // 等待 session 創建完成
                this.uiManager.addLog(`新 Session 已創建: ${this.sessionId}`, 'success');
            } else {
                // 重用現有 session
                this.uiManager.addLog(`重用現有 Session: ${this.sessionId}`, 'info');
                
                // 對於 HTTP SSE，確保 SSE 連接仍然有效
                if (this.currentProtocol === 'http_sse') {
                    const adapter = this.protocolAdapter;
                    if (!adapter.sseConnection || adapter.sseConnection.readyState === EventSource.CLOSED) {
                        // SSE 連接已關閉，需要重新建立
                        this.uiManager.addLog('SSE 連接已關閉，重新建立連接', 'warning');
                        await adapter.createSSEConnection(this.sessionId);
                    }
                }
            }
            
            // WebSocket 和 Socket.IO 需要單獨發送 metadata
            // HTTP SSE 不需要，因為已經在上傳時包含
            if (this.currentProtocol !== 'http_sse') {
                if (this.audioMetadata) {
                    try {
                        await this.sendAudioMetadata(this.audioMetadata);
                        this.uiManager.addLog(`音訊 metadata 已發送 (來源: ${this.audioMetadata.source || 'unknown'})`, 'success');
                    } catch (error) {
                        this.uiManager.addLog(`發送 metadata 失敗: ${error.message}`, 'error');
                    }
                } else {
                    this.uiManager.addLog('⚠️ 警告：沒有音訊元資料，後端可能無法正確處理', 'warning');
                }
            }
            
            // 發送音訊進行辨識
            await this.sendAudioForRecognition();
            
        } catch (error) {
            this.uiManager.addLog(`辨識失敗: ${error.message}`, 'error');
            this.uiManager.updateStatus('辨識失敗', 'error');
            this.uiManager.setProcessingState(false);
        }
    }
    
    // ==================== 協議通訊方法 ====================
    
    /**
     * 分發事件到後端
     */
    async dispatchEvent(eventType, payload = {}) {
        // 轉換為新的事件類型格式
        const newEventType = this.convertToNewEventType(eventType);
        
        this.uiManager.addLog(`分發事件: ${newEventType}`, 'info');
        
        try {
            await this.protocolAdapter.sendEvent(newEventType, payload);
        } catch (error) {
            this.uiManager.addLog(`事件分發失敗: ${error.message}`, 'error');
            throw error;
        }
    }
    
    /**
     * 將舊的 action 類型轉換為新的事件類型
     */
    convertToNewEventType(actionType) {
        const actionMap = {
            '[Session] Create': 'session/create',
            '[Session] Destroy': 'session/destroy',
            '[Session] Start Listening': 'session/start',
            '[Session] Upload File': 'file/upload',
            '[Session] Upload File Done': 'file/upload/done',
            '[Session] Chunk Upload Start': 'chunk/upload/start',
            '[Session] Chunk Upload Done': 'chunk/upload/done',
            '[Session] Start Recording': 'recording/start',
            '[Session] End Recording': 'recording/end',
            '[Session] Audio Chunk Received': 'chunk/received',
            '[Session] Begin Transcription': 'transcription/start',
            '[Session] Transcription Done': 'transcription/done',
            '[Session] Audio Metadata': 'audio/metadata',
            '[Session] Error': 'error'
        };
        
        return actionMap[actionType] || actionType;
    }
    
    /**
     * 發送音訊進行辨識 - 統一的音訊處理流程
     * 實現 100% 共享的音訊準備邏輯，僅網路傳輸層有協議差異
     */
    async sendAudioForRecognition() {
        try {
            this.uiManager.addLog(`準備發送音訊，Session ID: ${this.sessionId}`, 'info');
            
            // ===== 統一的前置處理 =====
            // 所有協議都執行相同的 chunk upload 開始流程
            await this.dispatchEvent(this.ACTIONS.CHUNK_UPLOAD_START, {
                session_id: this.sessionId
            });
            
            this.uiManager.addLog(`已開始 chunk upload 流程`, 'info');
            await this.sleep(50);
            
            // ===== 協議特定的傳輸層 =====
            // 統一接口：所有協議適配器實現相同的 sendAudioData 方法
            // WebSocket/Socket.IO: 使用 sendAudioDataInChunks() 進行分塊發送
            // HTTP SSE: 使用 FormData 進行檔案上傳
            await this.protocolAdapter.sendAudioData(
                this.sessionId,              // 會話 ID
                this.currentAudioSource,     // 音訊來源 (Blob)
                this.isFileUpload,           // 是否為檔案上傳
                (progress) => {              // 統一的進度回調
                    this.uiManager.updateStatus(`上傳中: ${progress}%`, 'uploading');
                },
                this.config                  // 統一的配置物件
            );
            
            await this.sleep(100);
            
            // ===== 統一的後置處理 =====
            // 所有協議都執行相同的 chunk upload 完成流程
            await this.dispatchEvent(this.ACTIONS.CHUNK_UPLOAD_DONE, {
                session_id: this.sessionId
            });
            
            this.uiManager.addLog(`已完成 chunk upload，等待辨識`, 'info');
            this.uiManager.updateStatus('處理中', 'processing');
            
        } catch (error) {
            this.uiManager.addLog(`發送音訊時發生錯誤: ${error.message}`, 'error');
            this.uiManager.updateStatus('發送失敗', 'error');
            throw error;
        }
    }
    
    /**
     * 處理協議訊息
     */
    handleProtocolMessage(message) {
        const eventType = message.type || 'unknown';
        this.uiManager.addLog(`收到事件: ${eventType}`, 'info');
        
        // 轉換為舊的 action 類型以保持相容性
        const actionType = this.convertFromNewEventType(eventType);
        
        switch (actionType) {
            case this.ACTIONS.BEGIN_TRANSCRIPTION:
                this.uiManager.updateStatus('開始辨識', 'processing');
                break;
                
            case this.ACTIONS.TRANSCRIPTION_DONE:
                this.handleTranscriptionDone(message.payload);
                break;
                
            case this.ACTIONS.UPLOAD_FILE_DONE:
                this.uiManager.addLog('檔案處理完成，等待辨識', 'info');
                this.uiManager.updateStatus('辨識中', 'processing');
                break;
                
            case this.ACTIONS.CHUNK_UPLOAD_START:
                this.uiManager.addLog('開始接收音訊塊', 'info');
                this.uiManager.updateStatus('準備處理音訊', 'processing');
                break;
                
            case this.ACTIONS.CHUNK_UPLOAD_DONE:
                this.uiManager.addLog('音訊塊處理完成，開始辨識', 'info');
                this.uiManager.updateStatus('辨識中', 'processing');
                break;
                
            case this.ACTIONS.ERROR:
                this.handleError(message.payload);
                break;
                
            // 直接處理新的事件類型
            case 'transcript':
                // WebSocket 的 transcript 訊息沒有 payload 欄位，整個 message 就是資料
                // Socket.IO 的 transcript 訊息會有 payload 欄位
                this.handleTranscriptEvent(message.payload || message);
                break;
                
            case 'status':
                // WebSocket 的 status 訊息可能沒有 payload 欄位
                this.handleStatusEvent(message.payload || message);
                break;
                
            case 'error':
                // WebSocket 的 error 訊息沒有 payload 欄位，error 在 message.error
                this.handleError(message.payload || message);
                break;
            
            // 音訊相關事件
            case 'audio/received':
                this.handleAudioReceived(message);
                break;
            
            case 'audio_metadata_ack':
                this.handleAudioMetadataAck(message);
                break;
                
            // 向後兼容
            case 'final_result':
                this.handleLegacyFinalResult(message.payload);
                break;
                
            default:
                // 只對真正未處理的事件顯示警告
                if (!this.isKnownButIgnoredEvent(eventType)) {
                    this.uiManager.addLog(`未處理的事件: ${eventType}`, 'warning');
                }
        }
    }
    
    /**
     * 將新的事件類型轉換為舊的 action 類型
     */
    convertFromNewEventType(eventType) {
        const eventMap = {
            'session/create': this.ACTIONS.CREATE_SESSION,
            'session/destroy': this.ACTIONS.DESTROY_SESSION,
            'session/start': this.ACTIONS.START_LISTENING,
            'session/stop': this.ACTIONS.START_LISTENING, // 停止監聽
            'file/upload': this.ACTIONS.UPLOAD_FILE,
            'file/upload/done': this.ACTIONS.UPLOAD_FILE_DONE,
            'chunk/upload/start': this.ACTIONS.CHUNK_UPLOAD_START,
            'chunk/upload/done': this.ACTIONS.CHUNK_UPLOAD_DONE,
            'recording/start': this.ACTIONS.START_RECORDING,
            'recording/end': this.ACTIONS.END_RECORDING,
            'chunk/received': this.ACTIONS.AUDIO_CHUNK_RECEIVED,
            'transcription/start': this.ACTIONS.BEGIN_TRANSCRIPTION,
            'transcription/done': this.ACTIONS.TRANSCRIPTION_DONE,
            'audio/metadata': this.ACTIONS.AUDIO_METADATA,
            'error': this.ACTIONS.ERROR
        };
        
        return eventMap[eventType] || eventType;
    }
    
    /**
     * 處理辨識完成
     */
    handleTranscriptionDone(payload) {
        this.uiManager.updateStatus('辨識完成', 'complete');
        this.uiManager.setProcessingState(false);
        
        if (payload && payload.result) {
            const result = payload.result;
            let text = '';
            
            if (typeof result === 'string') {
                text = result;
            } else if (result.text) {
                text = result.text;
            }
            
            if (text) {
                this.uiManager.displayResults(text);
                this.uiManager.addLog(`辨識完成: ${text}`, 'success');
                
                // 顯示其他資訊
                if (result.language) {
                    this.uiManager.addLog(`語言: ${result.language}`, 'info');
                }
                if (result.confidence) {
                    this.uiManager.addLog(`信心度: ${(result.confidence * 100).toFixed(1)}%`, 'info');
                }
                
                this.uiManager.showNotification('語音辨識完成！', 'success');
            }
        } else {
            this.uiManager.addLog('收到空的辨識完成事件', 'warning');
        }
    }
    
    /**
     * 處理錯誤
     */
    handleError(payload) {
        this.uiManager.updateStatus('發生錯誤', 'error');
        this.uiManager.setProcessingState(false);
        // 支援不同的錯誤訊息格式
        const errorMessage = payload.error || payload.message || payload || '未知錯誤';
        this.uiManager.addLog(`錯誤: ${errorMessage}`, 'error');
    }
    
    /**
     * 處理舊版 final_result 事件
     */
    handleLegacyFinalResult(data) {
        this.uiManager.addLog('收到辨識結果 (final_result)', 'info');
        if (data.text) {
            this.uiManager.displayResults(data.text);
            this.uiManager.updateStatus('辨識完成', 'complete');
            this.uiManager.setProcessingState(false);
            this.uiManager.addLog('辨識完成', 'success');
        }
    }
    
    /**
     * 處理 transcript 事件
     */
    handleTranscriptEvent(data) {
        // WebSocket 協議的 transcript 訊息包含 result 物件
        const result = data.result || data;
        const text = result.text || '';
        
        if (text) {
            this.uiManager.addLog(`收到辨識結果: ${text}`, 'success');
            this.uiManager.displayResults(text);
            
            // 顯示其他資訊
            if (result.confidence !== undefined) {
                this.uiManager.addLog(`信心度: ${(result.confidence * 100).toFixed(1)}%`, 'info');
            }
            if (result.language) {
                this.uiManager.addLog(`語言: ${result.language}`, 'info');
            }
        } else {
            this.uiManager.addLog('收到空的辨識結果', 'warning');
            this.uiManager.displayResults('（無辨識結果）');
        }
        
        this.uiManager.updateStatus('辨識完成', 'complete');
        this.uiManager.setProcessingState(false);
    }
    
    /**
     * 處理狀態事件
     */
    handleStatusEvent(data) {
        this.uiManager.addLog(`狀態更新: ${data.state}`, 'info');
        const statusText = this.uiManager.getStatusText(data.state);
        
        // 檢查是否為未翻譯的英文狀態值（只對英文狀態發出警告）
        if (statusText === data.state && !this.uiManager.isChineseText(data.state)) {
            this.uiManager.addLog(`⚠️ 未翻譯的狀態值: "${data.state}"`, 'warning');
            console.warn(`Untranslated status value: "${data.state}"`);
        }
        
        this.uiManager.updateStatus(statusText, 'processing');
    }
    
    /**
     * 處理音訊接收確認事件
     */
    handleAudioReceived(message) {
        // audio/received 訊息包含 size 和 chunk_id
        const size = message.size || 0;
        const chunkId = message.chunk_id;
        
        // 只在 debug 模式下顯示，避免刷屏
        if (this.debugMode) {
            this.uiManager.addLog(`音訊塊 #${chunkId} 已接收 (${size} bytes)`, 'debug');
        }
        
        // 更新進度（如果有進度條的話）
        if (this.totalChunks && chunkId !== undefined) {
            const progress = ((chunkId + 1) / this.totalChunks) * 100;
            this.uiManager.updateProgress(progress);
        }
    }
    
    /**
     * 處理音訊元資料確認事件
     */
    handleAudioMetadataAck(message) {
        if (message.status === 'success') {
            this.uiManager.addLog('音訊元資料已成功處理', 'success');
        } else {
            this.uiManager.addLog('音訊元資料處理失敗', 'error');
        }
    }
    
    /**
     * 檢查是否為已知但可忽略的事件
     */
    isKnownButIgnoredEvent(eventType) {
        const ignoredEvents = [
            'welcome',           // 歡迎訊息
            'session/create',    // 會話創建確認
            'session/destroy',   // 會話銷毀確認
            'chunk/upload/start', // 分塊上傳開始確認
            'chunk/upload/done', // 分塊上傳完成確認
            'audio_config_ack'   // 音訊配置確認
        ];
        
        return ignoredEvents.includes(eventType);
    }
    
    // ==================== 輔助方法 ====================
    
    /**
     * 發送音訊 metadata 給後端
     */
    async sendAudioMetadata(metadata) {
        try {
            if (!this.sessionId) {
                throw new Error('Session ID 不存在，無法發送 metadata');
            }
            
            await this.dispatchEvent(this.ACTIONS.AUDIO_METADATA, {
                session_id: this.sessionId,
                audio_metadata: metadata
            });
            
            this.uiManager.addLog('音訊 metadata 已發送給後端', 'success');
            
            // 記錄重要的轉換建議
            if (metadata.conversionNeeded && metadata.conversionNeeded.needed) {
                this.uiManager.addLog('轉換建議:', 'warning');
                metadata.conversionNeeded.reasons.forEach(reason => {
                    this.uiManager.addLog(`  • ${reason}`, 'warning');
                });
            }
            
        } catch (error) {
            this.uiManager.addLog(`發送 metadata 失敗: ${error.message}`, 'error');
            throw error;
        }
    }
    
    /**
     * 顯示音訊 metadata 日誌
     */
    displayAudioMetadataLogs(metadata) {
        this.uiManager.addLog('音訊檔案分析結果:', 'info');
        this.uiManager.addLog(`  格式: ${metadata.detectedFormat} (${metadata.estimatedCodec})`, 'info');
        if (metadata.duration) this.uiManager.addLog(`  時長: ${Math.round(metadata.duration * 100) / 100} 秒`, 'info');
        if (metadata.sampleRate) this.uiManager.addLog(`  採樣率: ${metadata.sampleRate} Hz`, 'info');
        if (metadata.channels) this.uiManager.addLog(`  聲道數: ${metadata.channels}`, 'info');
        if (metadata.estimatedBitrate) this.uiManager.addLog(`  估算位元率: ${Math.round(metadata.estimatedBitrate / 1000)} kbps`, 'info');
        
        // 顯示音量分析結果
        if (metadata.rmsLevel !== undefined) {
            if (metadata.isSilent) {
                this.uiManager.addLog('  ⚠️ 音訊似乎是靜音的', 'warning');
            } else if (metadata.isLowVolume) {
                this.uiManager.addLog('  ⚠️ 音訊音量較低', 'warning');
            } else {
                this.uiManager.addLog('  🔊 音量正常', 'info');
            }
        }
        
        // 顯示格式匹配狀態
        if (metadata.formatMatches === false) {
            this.uiManager.addLog(`  ⚠️ 檔案副檔名與實際格式不匹配`, 'warning');
        }
        
        if (metadata.fallbackMode) {
            this.uiManager.addLog('  ℹ️ 使用備用分析模式', 'info');
        }
    }
    
    /**
     * 清除檔案狀態
     */
    clearFileState() {
        this.audioUploader.clearFile();
        this.uiManager.clearFileState();
        if (this.isFileUpload) {
            this.currentAudioSource = null;
            this.isFileUpload = false;
            this.audioMetadata = null;
        }
    }
    
    /**
     * 清除錄音狀態
     */
    clearRecordingState() {
        this.audioRecorder.clearRecording();
        if (!this.isFileUpload) {
            this.currentAudioSource = null;
            this.audioMetadata = null;
        }
    }
    
    /**
     * 初始化自動辨識UI控制
     */
    initializeAutoTranscribeUI() {
        const checkbox = document.getElementById('autoTranscribe');
        if (checkbox) {
            // 設置初始狀態
            checkbox.checked = this.config.auto_transcribe;
            
            // 設置事件監聽器
            checkbox.addEventListener('change', (e) => {
                this.handleAutoTranscribeChange(e.target.checked);
            });
            
            console.log('Auto transcribe UI initialized:', {
                enabled: this.config.auto_transcribe,
                checkbox: !!checkbox
            });
        } else {
            console.error('Auto transcribe checkbox not found');
        }
    }
    
    /**
     * 休眠函數
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    const client = new ASRHubClient();
    
    // 將客戶端實例暴露到全域以便調試
    window.asrClient = client;
    
    console.log('ASR Hub 客戶端初始化完成');
    console.log('架構特性：');
    console.log('- 清晰的關注點分離');
    console.log('- 音訊錄音模組 (AudioRecorder)');
    console.log('- 音訊上傳模組 (AudioUploader)');
    console.log('- UI 管理模組 (UIManager)');
    console.log('- 協議適配器模組 (ProtocolAdapters)');
    console.log('- 新的獨立事件架構：session/*, recording/*, chunk/*, file/*');
});