/**
 * Audio Stream Manager
 * 管理持續性音訊串流，包括麥克風捕獲、音訊處理和傳輸
 */

class AudioStreamManager {
    constructor() {
        this.mediaStream = null;
        this.audioContext = null;
        this.mediaRecorder = null;
        this.scriptProcessor = null;
        this.analyser = null;
        
        // 狀態管理
        this.isStreaming = false;
        this.isInitialized = false;
        
        // 音訊參數
        this.sampleRate = 16000;
        this.channels = 1;
        this.bufferSize = 4096;
        
        // 資料緩衝
        this.audioBuffer = [];
        this.chunkSize = 1024; // 每次傳送的樣本數
        
        // 回調函數
        this.onAudioData = null;          // 音訊資料回調
        this.onVolumeLevel = null;        // 音量等級回調
        this.onStreamStart = null;        // 串流開始回調
        this.onStreamStop = null;         // 串流停止回調
        this.onError = null;              // 錯誤回調
        
        // 音量分析
        this.volumeData = new Uint8Array(256);
        this.lastVolumeUpdate = 0;
        this.volumeUpdateInterval = 50; // 50ms 更新一次音量
        
        // 視覺化資料
        this.frequencyData = new Uint8Array(256);
    }
    
    /**
     * 初始化音訊串流管理器
     */
    async initialize() {
        try {
            console.log('AudioStreamManager: 初始化音訊串流管理器...');
            
            // 請求麥克風權限
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: this.sampleRate,
                    channelCount: this.channels,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            
            // 創建 AudioContext
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate
            });
            
            // 創建音訊處理節點
            const source = this.audioContext.createMediaStreamSource(this.mediaStream);
            
            // 創建分析器節點（用於視覺化和音量檢測）
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 512;
            this.analyser.smoothingTimeConstant = 0.8;
            
            // 創建 ScriptProcessor 節點（用於音訊資料處理）
            this.scriptProcessor = this.audioContext.createScriptProcessor(this.bufferSize, this.channels, this.channels);
            
            // 連接音訊處理管道
            source.connect(this.analyser);
            source.connect(this.scriptProcessor);
            this.scriptProcessor.connect(this.audioContext.destination);
            
            // 設置音訊處理回調
            this.scriptProcessor.onaudioprocess = (audioProcessingEvent) => {
                this.processAudioData(audioProcessingEvent);
            };
            
            this.isInitialized = true;
            console.log('✓ AudioStreamManager: 音訊串流管理器初始化完成');
            
        } catch (error) {
            console.error('AudioStreamManager: 初始化失敗', error);
            if (this.onError) {
                this.onError('麥克風初始化失敗: ' + error.message);
            }
            throw error;
        }
    }
    
    /**
     * 開始音訊串流
     */
    async startStreaming() {
        try {
            if (!this.isInitialized) {
                await this.initialize();
            }
            
            if (this.isStreaming) {
                console.log('AudioStreamManager: 音訊串流已在進行中');
                return;
            }
            
            // 恢復 AudioContext（如果被暫停）
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            this.isStreaming = true;
            this.audioBuffer = [];
            
            // 準備音訊格式資訊，發送給後端
            const audioFormat = {
                sample_rate: this.sampleRate,
                channels: this.channels,
                encoding: 'pcm_f32le',  // Float32 PCM
                bits_per_sample: 32,
                format: 'raw',
                buffer_size: this.bufferSize
            };
            
            console.log('✓ AudioStreamManager: 音訊串流已開始，音訊格式:', audioFormat);
            
            if (this.onStreamStart) {
                this.onStreamStart(audioFormat);
            }
            
            // 開始音量監控
            this.startVolumeMonitoring();
            
        } catch (error) {
            console.error('AudioStreamManager: 開始串流失敗', error);
            if (this.onError) {
                this.onError('開始音訊串流失敗: ' + error.message);
            }
            throw error;
        }
    }
    
    /**
     * 停止音訊串流
     */
    stopStreaming() {
        try {
            if (!this.isStreaming) {
                console.log('AudioStreamManager: 音訊串流未啟動');
                return;
            }
            
            this.isStreaming = false;
            
            // 停止音量監控
            this.stopVolumeMonitoring();
            
            console.log('✓ AudioStreamManager: 音訊串流已停止');
            
            if (this.onStreamStop) {
                this.onStreamStop();
            }
            
        } catch (error) {
            console.error('AudioStreamManager: 停止串流失敗', error);
            if (this.onError) {
                this.onError('停止音訊串流失敗: ' + error.message);
            }
        }
    }
    
    /**
     * 清理資源
     */
    cleanup() {
        try {
            this.stopStreaming();
            
            // 停止媒體串流
            if (this.mediaStream) {
                this.mediaStream.getTracks().forEach(track => track.stop());
                this.mediaStream = null;
            }
            
            // 清理音訊節點
            if (this.scriptProcessor) {
                this.scriptProcessor.disconnect();
                this.scriptProcessor = null;
            }
            
            if (this.analyser) {
                this.analyser.disconnect();
                this.analyser = null;
            }
            
            // 關閉 AudioContext
            if (this.audioContext && this.audioContext.state !== 'closed') {
                this.audioContext.close();
                this.audioContext = null;
            }
            
            this.isInitialized = false;
            console.log('✓ AudioStreamManager: 資源清理完成');
            
        } catch (error) {
            console.error('AudioStreamManager: 清理資源失敗', error);
        }
    }
    
    /**
     * 處理音訊資料
     */
    processAudioData(audioProcessingEvent) {
        if (!this.isStreaming) return;
        
        const inputBuffer = audioProcessingEvent.inputBuffer;
        const inputData = inputBuffer.getChannelData(0); // 取得單聲道資料
        
        // 轉換為 16-bit PCM
        const pcmData = this.float32ToInt16(inputData);
        
        // 添加到緩衝區
        this.audioBuffer.push(...pcmData);
        
        // 檢查是否有足夠的資料發送
        while (this.audioBuffer.length >= this.chunkSize) {
            const chunk = this.audioBuffer.splice(0, this.chunkSize);
            const audioBytes = new Int16Array(chunk).buffer;
            
            // 發送音訊資料
            if (this.onAudioData) {
                this.onAudioData(audioBytes);
            }
        }
    }
    
    /**
     * 開始音量監控
     */
    startVolumeMonitoring() {
        const updateVolume = () => {
            if (!this.isStreaming || !this.analyser) return;
            
            const now = Date.now();
            if (now - this.lastVolumeUpdate < this.volumeUpdateInterval) {
                requestAnimationFrame(updateVolume);
                return;
            }
            this.lastVolumeUpdate = now;
            
            // 獲取頻率資料（用於視覺化）
            this.analyser.getByteFrequencyData(this.frequencyData);
            
            // 獲取時域資料（用於音量計算）
            this.analyser.getByteTimeDomainData(this.volumeData);
            
            // 計算音量等級
            const volumeLevel = this.calculateVolumeLevel(this.volumeData);
            
            // 發送音量資料
            if (this.onVolumeLevel) {
                this.onVolumeLevel({
                    level: volumeLevel,
                    frequencyData: this.frequencyData.slice(), // 複製陣列
                    timestamp: now
                });
            }
            
            requestAnimationFrame(updateVolume);
        };
        
        requestAnimationFrame(updateVolume);
    }
    
    /**
     * 停止音量監控
     */
    stopVolumeMonitoring() {
        // 音量監控會在下次 updateVolume 檢查 isStreaming 時自動停止
    }
    
    /**
     * 計算音量等級
     */
    calculateVolumeLevel(timeDomainData) {
        let sum = 0;
        for (let i = 0; i < timeDomainData.length; i++) {
            const value = (timeDomainData[i] - 128) / 128; // 正規化到 [-1, 1]
            sum += value * value;
        }
        
        const rms = Math.sqrt(sum / timeDomainData.length);
        
        // 轉換為分貝 (dB)
        const db = 20 * Math.log10(rms + 1e-6); // 避免 log(0)
        
        // 正規化到 [0, 1] 範圍
        const normalized = Math.max(0, Math.min(1, (db + 60) / 60)); // -60dB 到 0dB
        
        return normalized;
    }
    
    /**
     * 將 Float32 轉換為 Int16
     */
    float32ToInt16(float32Array) {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            const sample = Math.max(-1, Math.min(1, float32Array[i]));
            int16Array[i] = sample * 0x7FFF; // 轉換為 16-bit
        }
        return int16Array;
    }
    
    /**
     * 獲取音訊資訊
     */
    getAudioInfo() {
        return {
            isInitialized: this.isInitialized,
            isStreaming: this.isStreaming,
            sampleRate: this.sampleRate,
            channels: this.channels,
            bufferSize: this.bufferSize,
            contextState: this.audioContext ? this.audioContext.state : 'unknown'
        };
    }
    
    /**
     * 設置回調函數
     */
    setCallbacks({
        onAudioData = null,
        onVolumeLevel = null,
        onStreamStart = null,
        onStreamStop = null,
        onError = null
    } = {}) {
        this.onAudioData = onAudioData;
        this.onVolumeLevel = onVolumeLevel;
        this.onStreamStart = onStreamStart;
        this.onStreamStop = onStreamStop;
        this.onError = onError;
    }
    
    /**
     * 更新音訊參數
     */
    updateConfig({
        chunkSize = null,
        volumeUpdateInterval = null
    } = {}) {
        if (chunkSize !== null) {
            this.chunkSize = chunkSize;
            console.log(`AudioStreamManager: 更新 chunkSize 為 ${chunkSize}`);
        }
        
        if (volumeUpdateInterval !== null) {
            this.volumeUpdateInterval = volumeUpdateInterval;
            console.log(`AudioStreamManager: 更新 volumeUpdateInterval 為 ${volumeUpdateInterval}ms`);
        }
    }
}

// 導出到全域
window.AudioStreamManager = AudioStreamManager;