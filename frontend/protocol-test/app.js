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
        this.uiManager.addLog('符合 PyStoreX 純事件驅動架構', 'info');
        
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
            
            this.uiManager.setRecordingState(false);
            this.uiManager.displayAudioInfo(audioBlob, false);
            
            const durationText = duration ? ` (${duration.toFixed(1)}s)` : '';
            this.uiManager.addLog(`錄音結束${durationText}`, 'success');
            
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
     * 處理開始錄音
     */
    async handleStartRecording() {
        try {
            await this.audioRecorder.startRecording();
            
            // 分發 START_RECORDING action
            if (this.sessionId) {
                await this.dispatchAction(this.ACTIONS.START_RECORDING, {
                    session_id: this.sessionId,
                    strategy: this.config.strategy
                });
            }
        } catch (error) {
            this.uiManager.addLog(`錄音失敗: ${error.message}`, 'error');
            this.uiManager.updateStatus('錄音失敗', 'error');
        }
    }
    
    /**
     * 處理停止錄音
     */
    async handleStopRecording() {
        if (this.audioRecorder.stopRecording()) {
            // 分發 END_RECORDING action
            if (this.sessionId) {
                const duration = this.audioRecorder.getRecordingDuration();
                await this.dispatchAction(this.ACTIONS.END_RECORDING, {
                    session_id: this.sessionId,
                    trigger: 'manual',
                    duration: duration
                });
            }
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
            
            // 連接到後端
            await this.protocolAdapter.connect();
            
            // 總是創建新的 session 以確保狀態乾淨
            this.sessionId = this.protocolAdapter.generateSessionId();
            
            // 創建 session
            await this.dispatchAction(this.ACTIONS.CREATE_SESSION, {
                session_id: this.sessionId,
                strategy: this.config.strategy
            });
            
            await this.sleep(100); // 等待 session 創建完成
            
            this.uiManager.addLog(`Session 創建成功: ${this.sessionId}`, 'success');
            
            // 如果有 metadata（檔案上傳），先發送 metadata
            if (this.audioMetadata && this.isFileUpload) {
                try {
                    await this.sendAudioMetadata(this.audioMetadata);
                    this.uiManager.addLog('音訊 metadata 已發送', 'success');
                } catch (error) {
                    this.uiManager.addLog(`發送 metadata 失敗: ${error.message}`, 'error');
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
     * 分發 action 到後端
     */
    async dispatchAction(actionType, payload = {}) {
        const action = {
            type: actionType,
            payload: payload,
            timestamp: new Date().toISOString()
        };
        
        this.uiManager.addLog(`分發 Action: ${actionType}`, 'info');
        
        try {
            await this.protocolAdapter.sendAction(action);
        } catch (error) {
            this.uiManager.addLog(`Action 分發失敗: ${error.message}`, 'error');
            throw error;
        }
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
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_START, {
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
            await this.dispatchAction(this.ACTIONS.CHUNK_UPLOAD_DONE, {
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
        this.uiManager.addLog(`收到 Message: ${message.type || 'unknown'}`, 'info');
        
        switch (message.type) {
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
                
            // 向後兼容
            case 'final_result':
                this.handleLegacyFinalResult(message.payload);
                break;
                
            case 'transcript':
                this.handleTranscriptEvent(message.payload);
                break;
                
            case 'status':
                this.handleStatusEvent(message.payload);
                break;
                
            default:
                this.uiManager.addLog(`未處理的訊息: ${message.type}`, 'warning');
        }
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
        const errorMessage = payload.error || payload.message || '未知錯誤';
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
        this.uiManager.addLog(`收到辨識結果: ${data.text}`, 'success');
        this.uiManager.displayResults(data.text);
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
    
    // ==================== 輔助方法 ====================
    
    /**
     * 發送音訊 metadata 給後端
     */
    async sendAudioMetadata(metadata) {
        try {
            if (!this.sessionId) {
                throw new Error('Session ID 不存在，無法發送 metadata');
            }
            
            await this.dispatchAction(this.ACTIONS.AUDIO_METADATA, {
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
    console.log('- 統一的事件驅動架構');
});