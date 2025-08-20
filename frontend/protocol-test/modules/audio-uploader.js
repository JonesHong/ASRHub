// 音訊上傳與分析模組 - 處理檔案選擇、分析和metadata管理
class AudioUploader {
    constructor() {
        this.audioFile = null;
        this.audioMetadata = null;
        
        // 事件監聽器
        this.onFileSelected = null;
        this.onFileAnalyzed = null;
        this.onAnalysisError = null;
    }
    
    /**
     * 處理檔案選擇
     */
    async handleFileSelect(file) {
        if (!file) return null;
        
        this.audioFile = file;
        
        if (this.onFileSelected) {
            this.onFileSelected(file);
        }
        
        // 立即分析音訊檔案規格
        try {
            const audioMetadata = await this.analyzeAudioFile(file);
            this.audioMetadata = audioMetadata;
            
            if (this.onFileAnalyzed) {
                this.onFileAnalyzed(audioMetadata);
            }
            
            return audioMetadata;
            
        } catch (error) {
            if (this.onAnalysisError) {
                this.onAnalysisError(`音訊分析失敗: ${error.message}`);
            }
            throw error;
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
                    console.warn(`Web Audio API 解碼失敗，返回基本資訊: ${error.message}`);
                    
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
     * 獲取檔案副檔名
     */
    getFileExtension(filename) {
        const lastDot = filename.lastIndexOf('.');
        return lastDot !== -1 ? filename.substring(lastDot + 1).toLowerCase() : '';
    }
    
    /**
     * 獲取選中的檔案
     */
    getSelectedFile() {
        return this.audioFile;
    }
    
    /**
     * 獲取檔案 metadata
     */
    getAudioMetadata() {
        return this.audioMetadata;
    }
    
    /**
     * 清除檔案數據
     */
    clearFile() {
        this.audioFile = null;
        this.audioMetadata = null;
    }
    
    /**
     * 生成顯示用的檔案資訊
     */
    getDisplayInfo() {
        if (!this.audioMetadata) return '';
        
        const metadata = this.audioMetadata;
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
        
        return infoText;
    }
}

// 導出到全域
window.AudioUploader = AudioUploader;