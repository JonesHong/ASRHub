# Denoise Service (降噪服務)

## 概述
降噪服務使用深度學習模型（DeepFilterNet）提供高品質的音訊降噪功能。能有效去除背景噪音、環境聲、風聲等干擾，同時保持語音的自然度和清晰度。

## 核心功能

### 降噪能力
- **深度降噪** - 使用 DeepFilterNet 深度學習模型
- **即時處理** - 低延遲即時降噪
- **智慧識別** - 自動識別並保留語音
- **多種噪音** - 處理各類背景噪音

### 噪音類型
- **環境噪音** - 交通聲、人群聲、機械聲
- **白噪音** - 風扇、空調、電子噪音
- **脈衝噪音** - 鍵盤聲、敲擊聲
- **風噪** - 麥克風風聲

## 使用方式

### 基本降噪
```python
from src.service.denoise import denoise_service

# 初始化服務（自動載入模型）
denoise_service.initialize()

# 簡單降噪
clean_audio = denoise_service.process(noisy_audio_bytes)

# 調整降噪強度
clean_audio = denoise_service.process(
    noisy_audio_bytes,
    noise_reduction_level=0.8  # 0.0-1.0，越高降噪越強
)
```

### 串流降噪
```python
# 建立串流降噪器
stream_denoiser = denoise_service.create_stream_processor(
    session_id="user_123",
    sample_rate=16000,
    chunk_size=512
)

# 處理音訊流
while streaming:
    noisy_chunk = get_audio_chunk()
    clean_chunk = stream_denoiser.process_chunk(noisy_chunk)
    send_clean_audio(clean_chunk)

# 結束時刷新緩衝
final_chunk = stream_denoiser.flush()
```

### 進階配置
```python
from src.service.denoise import DenoiseConfig

config = DenoiseConfig(
    model="deepfilternet",           # 模型選擇
    noise_reduction_level=0.7,       # 降噪強度
    preserve_voice_level=0.9,        # 語音保留程度
    min_noise_duration=0.1,          # 最小噪音持續時間
    adaptive_mode=True,              # 自適應模式
    gpu_acceleration=True             # GPU 加速
)

denoise_service.configure(config)
```

## 實際應用範例

### 會議降噪系統
```python
class MeetingDenoiser:
    """會議音訊降噪系統"""
    
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id
        self.denoisers = {}  # 每個參與者的降噪器
        
    def add_participant(self, participant_id: str):
        """為參與者建立降噪器"""
        self.denoisers[participant_id] = denoise_service.create_stream_processor(
            session_id=f"{self.meeting_id}_{participant_id}",
            sample_rate=16000,
            # 會議場景：平衡降噪和語音品質
            noise_reduction_level=0.6,
            preserve_voice_level=0.95
        )
    
    def process_audio(self, participant_id: str, audio_chunk: bytes) -> bytes:
        """處理參與者音訊"""
        if participant_id not in self.denoisers:
            self.add_participant(participant_id)
        
        # 降噪處理
        clean_audio = self.denoisers[participant_id].process_chunk(audio_chunk)
        
        # 可選：檢測靜音避免不必要的傳輸
        if self.is_silence(clean_audio):
            return None
        
        return clean_audio
    
    def is_silence(self, audio: bytes, threshold: float = 0.01) -> bool:
        """檢測靜音"""
        import numpy as np
        audio_array = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(audio_array ** 2))
        return rms < threshold
    
    def end_meeting(self):
        """結束會議，清理資源"""
        for denoiser in self.denoisers.values():
            denoiser.cleanup()
        self.denoisers.clear()
```

### ASR 前處理降噪
```python
from src.service.vad import vad_service

class ASRPreprocessor:
    """ASR 前處理器with 智慧降噪"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.denoiser = None
        self.noise_profile = None
        
    def analyze_noise_profile(self, audio_sample: bytes):
        """分析噪音特徵（使用開頭靜音段）"""
        # 假設前 0.5 秒是環境噪音
        sample_rate = 16000
        noise_samples = int(0.5 * sample_rate * 2)  # 2 bytes per sample
        noise_chunk = audio_sample[:noise_samples]
        
        # 分析噪音特徵
        self.noise_profile = denoise_service.analyze_noise(noise_chunk)
        
        # 根據噪音特徵調整降噪參數
        if self.noise_profile['noise_level'] > 0.7:
            # 高噪音環境
            config = DenoiseConfig(
                noise_reduction_level=0.9,
                preserve_voice_level=0.8,
                adaptive_mode=True
            )
        else:
            # 低噪音環境
            config = DenoiseConfig(
                noise_reduction_level=0.5,
                preserve_voice_level=0.95,
                adaptive_mode=False
            )
        
        self.denoiser = denoise_service.create_processor(self.session_id, config)
    
    def process_for_asr(self, audio: bytes) -> bytes:
        """為 ASR 準備音訊"""
        # 降噪
        clean_audio = self.denoiser.process(audio)
        
        # VAD 檢測
        has_speech = vad_service.quick_check(clean_audio)
        
        if not has_speech:
            return None  # 無語音，跳過 ASR
        
        # 音訊增強（可選）
        from src.service.audio_enhancer import audio_enhancer
        enhanced = audio_enhancer.enhance_for_asr(clean_audio)
        
        return enhanced
```

### 錄音降噪後處理
```python
class RecordingPostProcessor:
    """錄音後處理降噪"""
    
    def __init__(self):
        self.batch_denoiser = denoise_service.create_batch_processor()
        
    def process_recording(self, 
                         recording_path: str, 
                         output_path: str,
                         auto_detect: bool = True):
        """處理整個錄音檔案"""
        import wave
        import numpy as np
        
        # 讀取錄音
        with wave.open(recording_path, 'rb') as wav:
            params = wav.getparams()
            audio_data = wav.readframes(params.nframes)
        
        if auto_detect:
            # 自動檢測最佳降噪參數
            best_config = self.auto_tune_denoise(audio_data)
            denoise_service.configure(best_config)
        
        # 批次降噪
        clean_audio = self.batch_denoiser.process_file(
            audio_data,
            sample_rate=params.framerate,
            channels=params.nchannels
        )
        
        # 儲存降噪後的音訊
        with wave.open(output_path, 'wb') as wav:
            wav.setparams(params)
            wav.writeframes(clean_audio)
        
        # 生成降噪報告
        report = self.generate_report(audio_data, clean_audio)
        return report
    
    def auto_tune_denoise(self, audio_data: bytes) -> DenoiseConfig:
        """自動調整降噪參數"""
        # 嘗試不同的降噪強度
        test_levels = [0.3, 0.5, 0.7, 0.9]
        best_config = None
        best_score = 0
        
        for level in test_levels:
            config = DenoiseConfig(noise_reduction_level=level)
            denoised = denoise_service.quick_process(audio_data, config)
            
            # 評估降噪效果（SNR、語音品質等）
            score = self.evaluate_quality(audio_data, denoised)
            
            if score > best_score:
                best_score = score
                best_config = config
        
        return best_config
    
    def evaluate_quality(self, original: bytes, denoised: bytes) -> float:
        """評估降噪品質"""
        # 計算 SNR 改善
        original_snr = calculate_snr(original)
        denoised_snr = calculate_snr(denoised)
        snr_improvement = denoised_snr - original_snr
        
        # 計算語音失真度
        distortion = calculate_distortion(original, denoised)
        
        # 綜合評分
        score = snr_improvement * 0.7 - distortion * 0.3
        return score
    
    def generate_report(self, original: bytes, denoised: bytes) -> dict:
        """生成降噪報告"""
        return {
            'original_size': len(original),
            'denoised_size': len(denoised),
            'snr_improvement': calculate_snr(denoised) - calculate_snr(original),
            'processing_time': self.batch_denoiser.last_processing_time,
            'model_used': 'deepfilternet',
            'timestamp': datetime.now().isoformat()
        }
```

### 即時通話降噪
```python
class CallDenoiser:
    """即時通話降噪"""
    
    def __init__(self, call_id: str):
        self.call_id = call_id
        # 雙向降噪器
        self.inbound_denoiser = denoise_service.create_stream_processor(
            f"{call_id}_in",
            noise_reduction_level=0.7
        )
        self.outbound_denoiser = denoise_service.create_stream_processor(
            f"{call_id}_out",
            noise_reduction_level=0.7
        )
        
    def process_inbound(self, audio: bytes) -> bytes:
        """處理來電音訊"""
        return self.inbound_denoiser.process_chunk(audio)
    
    def process_outbound(self, audio: bytes) -> bytes:
        """處理去電音訊"""
        return self.outbound_denoiser.process_chunk(audio)
    
    def enable_echo_cancellation(self):
        """啟用回音消除（配合降噪）"""
        self.inbound_denoiser.enable_aec()
        self.outbound_denoiser.enable_aec()
    
    def adjust_noise_reduction(self, level: float):
        """動態調整降噪強度"""
        self.inbound_denoiser.set_reduction_level(level)
        self.outbound_denoiser.set_reduction_level(level)
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  denoise:
    enabled: true
    model: "deepfilternet"              # 降噪模型
    model_path: "models/deepfilternet"  # 模型路徑
    
    default_config:
      noise_reduction_level: 0.7        # 預設降噪強度
      preserve_voice_level: 0.9         # 語音保留程度
      adaptive_mode: true               # 自適應模式
      
    performance:
      use_gpu: false                    # GPU 加速
      batch_size: 32                    # 批次大小
      num_threads: 4                    # CPU 執行緒數
      
    quality:
      min_snr_improvement: 3.0          # 最小 SNR 改善 (dB)
      max_distortion: 0.1               # 最大失真度
```

## 效能優化

### 處理模式選擇
- **即時模式**: 低延遲，適合通話、直播
- **批次模式**: 高品質，適合後處理
- **自適應模式**: 自動調整參數

### 降噪強度建議
| 場景 | 強度 | 語音保留 | 說明 |
|------|------|----------|------|
| 安靜環境 | 0.3-0.4 | 0.95 | 輕度降噪 |
| 一般環境 | 0.5-0.7 | 0.90 | 平衡設定 |
| 吵雜環境 | 0.8-0.9 | 0.85 | 強力降噪 |
| 極端噪音 | 0.9-1.0 | 0.80 | 最大降噪 |

### 資源使用
- **CPU**: 單核 15-25% @ 16kHz
- **記憶體**: 模型 ~50MB，每 session ~5MB
- **GPU**: 可降低 CPU 使用至 5%
- **延遲**: < 20ms (即時模式)

## 注意事項

1. **模型載入**: 首次使用會下載模型（~50MB）
2. **音訊格式**: 最佳效果需 16kHz 單聲道
3. **過度降噪**: 太強可能損害語音品質
4. **GPU 支援**: 需要 CUDA 11+ 或 ROCm
5. **記憶體管理**: 長時間運行注意釋放資源

## 錯誤處理

```python
from src.interface.exceptions import (
    DenoiseError,
    ModelLoadError,
    ProcessingError
)

try:
    denoise_service.initialize()
except ModelLoadError as e:
    logger.error(f"模型載入失敗: {e}")
    # 降級到基礎降噪
    use_basic_denoise()

try:
    clean = denoise_service.process(noisy)
except ProcessingError as e:
    logger.error(f"降噪處理失敗: {e}")
    # 返回原始音訊
    return noisy
```

## 降噪效果評估

```python
def evaluate_denoise_quality(original: bytes, denoised: bytes):
    """評估降噪品質"""
    metrics = {
        'snr_improvement': calculate_snr_improvement(original, denoised),
        'speech_quality': calculate_pesq(original, denoised),  # PESQ 分數
        'noise_suppression': calculate_noise_suppression(original, denoised),
        'speech_distortion': calculate_distortion(original, denoised)
    }
    
    # 綜合評分（0-100）
    score = (
        metrics['snr_improvement'] * 0.3 +
        metrics['speech_quality'] * 0.4 +
        metrics['noise_suppression'] * 0.2 -
        metrics['speech_distortion'] * 0.1
    ) * 10
    
    return score, metrics
```

## 未來擴展

- 多模型支援（RNNoise、NSNET等）
- 場景識別自動調整
- 個性化降噪訓練
- 空間音訊降噪
- 音樂保護模式
- 即時降噪品質監控