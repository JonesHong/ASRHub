// 音訊錄音模組 - 處理所有錄音相關功能
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioBlob = null;
        this.audioContext = null;
        this.mediaStreamSource = null;
        this.isRecording = false;
        this.recordingStartTime = null;
        
        // 錄音模式設定 - 區分批次和串流模式
        this.mode = 'batch'; // 'batch' 或 'stream'
        
        // 事件監聽器
        this.onRecordingStart = null;
        this.onRecordingStop = null;
        this.onRecordingData = null; // 僅在 stream 模式時使用
        this.onRecordingError = null;
    }
    
    /**
     * 設置錄音模式
     * @param {string} mode - 'batch' 或 'stream'
     */
    setMode(mode) {
        if (mode !== 'batch' && mode !== 'stream') {
            throw new Error('錄音模式必須是 "batch" 或 "stream"');
        }
        this.mode = mode;
        console.log(`🎙️ 錄音模式設定為: ${mode}`);
    }
    
    /**
     * 獲取當前錄音模式
     */
    getMode() {
        return this.mode;
    }
    
    /**
     * 開始錄音
     */
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
            
            this.audioChunks = [];
            this.recordingStartTime = Date.now();
            
            // 創建 AudioContext
            try {
                const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                this.audioContext = new AudioContextClass({ sampleRate: 16000 });
                
                if (this.audioContext.sampleRate !== 16000) {
                    console.warn(`注意：瀏覽器使用 ${this.audioContext.sampleRate} Hz 採樣率`);
                }
                
                this.mediaStreamSource = this.audioContext.createMediaStreamSource(stream);
                
            } catch (e) {
                console.warn('無法創建 AudioContext，使用預設錄音設定');
            }
            
            const mimeType = this.getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};
            
            if (mimeType && mimeType.includes('webm')) {
                options.audioBitsPerSecond = 128000;
            }
            
            this.mediaRecorder = new MediaRecorder(stream, options);
            
            this.mediaRecorder.addEventListener('dataavailable', (event) => {
                this.audioChunks.push(event.data);
                
                // 只在串流模式時發送分片數據
                if (this.mode === 'stream' && this.onRecordingData) {
                    console.log(`🔄 串流模式: 發送音訊分片 (${event.data.size} bytes)`);
                    this.onRecordingData(event.data);
                } else if (this.mode === 'batch') {
                    console.log(`📦 批次模式: 暫存音訊分片 (${event.data.size} bytes), 總共 ${this.audioChunks.length} 個分片`);
                }
            });
            
            this.mediaRecorder.addEventListener('stop', () => {
                this.audioBlob = new Blob(this.audioChunks, { type: mimeType || 'audio/webm' });
                this.isRecording = false;
                
                // 根據模式顯示不同的日誌信息
                if (this.mode === 'batch') {
                    console.log(`📦 批次模式: 錄音完成，合併 ${this.audioChunks.length} 個分片為完整音訊檔案 (${this.audioBlob.size} bytes)`);
                    console.log(`📊 批次模式: audioBlob 包含完整的 WebM 容器頭部，適合後端 FFmpeg/pydub 處理`);
                } else if (this.mode === 'stream') {
                    console.log(`🔄 串流模式: 錄音結束，已發送 ${this.audioChunks.length} 個分片`);
                }
                
                // 驗證實際錄製的格式
                this.verifyActualAudioFormat();
                
                if (this.audioContext) {
                    this.audioContext.close();
                    this.audioContext = null;
                    this.mediaStreamSource = null;
                }
                
                if (this.onRecordingStop) {
                    const duration = this.recordingStartTime ? 
                        (Date.now() - this.recordingStartTime) / 1000 : 0;
                    this.onRecordingStop(this.audioBlob, duration);
                }
            });
            
            // 根據模式決定 MediaRecorder 的啟動方式
            if (this.mode === 'stream') {
                // 串流模式：啟用時間片段，定期觸發 dataavailable 事件
                this.mediaRecorder.start(1000); // 每1秒觸發一次 dataavailable
                console.log(`🔄 串流模式: MediaRecorder 啟動，每1秒發送音訊分片`);
            } else {
                // 批次模式：不設定時間片段，只在停止時觸發 dataavailable 事件
                this.mediaRecorder.start();
                console.log(`📦 批次模式: MediaRecorder 啟動，僅在錄音結束時產生完整音訊檔案`);
            }
            
            this.isRecording = true;
            
            if (this.onRecordingStart) {
                this.onRecordingStart();
            }
            
            return true;
            
        } catch (error) {
            if (this.onRecordingError) {
                this.onRecordingError(`錄音失敗: ${error.message}`);
            }
            throw error;
        }
    }
    
    /**
     * 停止錄音
     */
    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            return true;
        }
        return false;
    }
    
    /**
     * 獲取錄音結果
     */
    getRecordingBlob() {
        return this.audioBlob;
    }
    
    /**
     * 獲取錄音時長
     */
    getRecordingDuration() {
        return this.recordingStartTime ? 
            (Date.now() - this.recordingStartTime) / 1000 : 0;
    }
    
    /**
     * 清除錄音數據
     */
    clearRecording() {
        this.audioChunks = [];
        this.audioBlob = null;
        this.recordingStartTime = null;
    }
    
    /**
     * 檢測瀏覽器支援的音訊格式
     */
    getSupportedMimeType() {
        const types = [
            'audio/wav',
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4'
        ];
        
        console.log('🔍 檢測瀏覽器音訊格式支援:');
        
        for (const type of types) {
            const isSupported = MediaRecorder.isTypeSupported(type);
            console.log(`  ${type}: ${isSupported ? '✅ 支援' : '❌ 不支援'}`);
            
            if (isSupported) {
                console.log(`📋 選擇音訊格式: ${type}`);
                console.log(`⚠️ 注意: 瀏覽器可能聲稱支援但實際錄製不同格式`);
                return type;
            }
        }
        
        console.error('❌ 無支援的音訊格式，使用預設格式');
        return null;
    }
    
    /**
     * 驗證實際錄製的音訊格式
     */
    async verifyActualAudioFormat() {
        if (!this.audioBlob) return;
        
        try {
            console.log(`🔬 驗證實際錄製的音訊格式 (${this.mode} 模式)...`);
            
            // 讀取前16個字節檢查檔案頭
            const arrayBuffer = await this.audioBlob.slice(0, 16).arrayBuffer();
            const uint8Array = new Uint8Array(arrayBuffer);
            const header = Array.from(uint8Array)
                .map(b => b.toString(16).padStart(2, '0'))
                .join(' ');
            
            console.log(`📊 音訊檔案頭 (前16字節): ${header}`);
            console.log(`📋 聲明的MIME類型: ${this.audioBlob.type}`);
            console.log(`📏 音訊大小: ${this.audioBlob.size} bytes`);
            
            // 檢測實際格式
            const actualFormat = this.detectActualFormat(uint8Array);
            console.log(`🎯 檢測到的實際格式: ${actualFormat.format} (${actualFormat.codec})`);
            
            if (this.mode === 'batch') {
                console.log(`✅ 批次模式: audioBlob 包含完整的 ${actualFormat.format} 容器，可直接提交給後端處理`);
            }
            
            if (!actualFormat.matches_declared) {
                console.error(`⚠️ 格式不匹配! 聲明: ${this.audioBlob.type}, 實際: ${actualFormat.format}`);
                console.warn(`💡 建議: 後端應強制處理為 ${actualFormat.format} 格式`);
            }
            
            return {
                declared_type: this.audioBlob.type,
                actual_format: actualFormat.format,
                codec: actualFormat.codec,
                size: this.audioBlob.size,
                header: header,
                matches_declared: actualFormat.matches_declared
            };
            
        } catch (error) {
            console.error(`❌ 格式驗證失敗: ${error.message}`);
            return null;
        }
    }
    
    /**
     * 檢測實際音訊格式
     */
    detectActualFormat(uint8Array) {
        // WAV 格式檢測 (RIFF header)
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
        
        // WebM 格式檢測 (EBML header)
        if (uint8Array[0] === 0x1A && uint8Array[1] === 0x45 && 
            uint8Array[2] === 0xDF && uint8Array[3] === 0xA3) {
            return {
                format: 'WebM',
                codec: 'Opus or VP8/VP9',
                matches_declared: this.audioBlob.type.includes('webm')
            };
        }
        
        // Ogg 格式檢測
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

// 導出到全域
window.AudioRecorder = AudioRecorder;