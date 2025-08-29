# Audio Converter Service (音訊轉換服務)

## 概述
音訊轉換服務提供高效的音訊格式轉換功能，支援多種轉換後端（FFmpeg、SciPy），可處理採樣率轉換、聲道轉換、格式轉換等。採用策略模式設計，可根據需求選擇最適合的轉換器。

## 核心功能

### 格式轉換
- **多格式支援** - WAV、MP3、FLAC、AAC、PCM 等
- **採樣率轉換** - 8kHz 到 192kHz 任意轉換
- **聲道轉換** - 單聲道/立體聲互轉
- **位元深度** - 8bit、16bit、24bit、32bit 轉換

### 轉換後端
- **FFmpeg** - 功能完整，支援所有格式
- **SciPy** - 純 Python，支援 GPU 加速
- **自動選擇** - 根據可用性自動選擇最佳後端

## 使用方式

### 快速開始
```python
from src.service.audio_converter import audio_converter

# 簡單轉換（自動檢測格式）
converted = audio_converter.convert(
    audio_bytes,
    target_sample_rate=16000,
    target_channels=1
)

# 指定輸出格式
converted = audio_converter.convert_format(
    audio_bytes,
    input_format="wav",
    output_format="mp3",
    sample_rate=44100
)
```

### 批次處理
```python
# 轉換音訊片段（串流處理）
chunk_converter = audio_converter.create_stream_converter(
    input_sample_rate=48000,
    output_sample_rate=16000,
    input_channels=2,
    output_channels=1
)

while streaming:
    input_chunk = get_audio_chunk()
    output_chunk = chunk_converter.process(input_chunk)
    process_converted_audio(output_chunk)
```

### 選擇特定轉換器
```python
from src.service.audio_converter.ffmpeg_converter import FFmpegConverter
from src.service.audio_converter.scipy_converter import ScipyConverter

# 使用 FFmpeg（功能最全）
ffmpeg = FFmpegConverter()
converted = ffmpeg.convert(
    audio_data,
    input_format="mp3",
    output_format="wav",
    sample_rate=16000
)

# 使用 SciPy（支援 GPU）
scipy = ScipyConverter(use_gpu=True)
converted = scipy.resample(
    audio_data,
    orig_sr=44100,
    target_sr=16000
)
```

### 進階轉換選項
```python
# 完整參數控制
converted = audio_converter.convert_advanced(
    audio_bytes,
    # 輸入參數
    input_format="wav",
    input_sample_rate=44100,
    input_channels=2,
    input_bit_depth=24,
    
    # 輸出參數
    output_format="mp3",
    output_sample_rate=16000,
    output_channels=1,
    output_bit_depth=16,
    
    # 品質參數
    quality="high",        # low, medium, high
    bitrate=128000,       # 僅用於壓縮格式
    
    # 處理選項
    normalize=True,        # 標準化音量
    remove_silence=True,   # 移除靜音段
    apply_filters=["highpass", "denoise"]
)
```

## 實際應用範例

### ASR 預處理器
```python
class ASRPreprocessor:
    """ASR 專用音訊預處理器"""
    
    def __init__(self):
        self.converter = audio_converter
        self.target_config = {
            'sample_rate': 16000,  # ASR 標準採樣率
            'channels': 1,         # 單聲道
            'format': 'pcm_s16le'  # 16-bit PCM
        }
    
    def prepare_for_asr(self, audio_file: str) -> bytes:
        """準備音訊供 ASR 使用"""
        # 讀取任意格式音訊
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
        
        # 檢測輸入格式
        input_format = self.detect_format(audio_file)
        
        # 轉換為 ASR 格式
        converted = self.converter.convert(
            audio_data,
            input_format=input_format,
            output_format='pcm',
            target_sample_rate=self.target_config['sample_rate'],
            target_channels=self.target_config['channels']
        )
        
        # 可選：音訊增強
        if need_enhancement(converted):
            from src.service.audio_enhancer import audio_enhancer
            converted = audio_enhancer.enhance_for_asr(converted)
        
        return converted
    
    def detect_format(self, file_path: str) -> str:
        """檢測音訊格式"""
        extension = file_path.split('.')[-1].lower()
        format_map = {
            'wav': 'wav',
            'mp3': 'mp3',
            'flac': 'flac',
            'aac': 'aac',
            'm4a': 'aac',
            'ogg': 'ogg'
        }
        return format_map.get(extension, 'wav')
```

### 即時採樣率轉換
```python
class RealtimeResampler:
    """即時採樣率轉換器"""
    
    def __init__(self, input_sr: int, output_sr: int):
        self.input_sr = input_sr
        self.output_sr = output_sr
        self.converter = audio_converter.create_stream_converter(
            input_sample_rate=input_sr,
            output_sample_rate=output_sr,
            buffer_size=1024
        )
        self.residue = np.array([])  # 殘餘樣本
    
    def process_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """處理音訊塊"""
        # 合併殘餘樣本
        if len(self.residue) > 0:
            chunk = np.concatenate([self.residue, chunk])
        
        # 計算可處理的樣本數
        input_samples = len(chunk)
        output_samples = int(input_samples * self.output_sr / self.input_sr)
        
        # 計算實際需要的輸入樣本數
        needed_samples = int(output_samples * self.input_sr / self.output_sr)
        
        # 分離可處理和殘餘部分
        to_process = chunk[:needed_samples]
        self.residue = chunk[needed_samples:]
        
        # 執行重採樣
        resampled = self.converter.process(to_process)
        
        return resampled
    
    def flush(self) -> np.ndarray:
        """處理剩餘樣本"""
        if len(self.residue) > 0:
            resampled = self.converter.process(self.residue)
            self.residue = np.array([])
            return resampled
        return np.array([])
```

### 多格式錄音轉換器
```python
from pathlib import Path

class MultiFormatRecorder:
    """支援多格式輸出的錄音器"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.raw_audio = []  # 原始音訊資料
        
    def add_audio(self, chunk: bytes):
        """添加音訊資料"""
        self.raw_audio.append(chunk)
    
    def save_all_formats(self, base_name: str, formats: list = None):
        """儲存為多種格式"""
        if formats is None:
            formats = ['wav', 'mp3', 'flac']
        
        # 合併所有音訊
        full_audio = b''.join(self.raw_audio)
        
        saved_files = {}
        for format in formats:
            # 轉換格式
            converted = audio_converter.convert_format(
                full_audio,
                input_format='pcm',
                output_format=format,
                sample_rate=16000,
                channels=1
            )
            
            # 儲存檔案
            file_path = f"{base_name}.{format}"
            with open(file_path, 'wb') as f:
                f.write(converted)
            
            saved_files[format] = {
                'path': file_path,
                'size': len(converted),
                'compression_ratio': len(full_audio) / len(converted)
            }
            
            logger.info(f"已儲存 {format}: {file_path}")
        
        return saved_files
```

### GPU 加速批次轉換
```python
class GPUBatchConverter:
    """GPU 加速批次音訊轉換"""
    
    def __init__(self):
        # 使用 SciPy converter 並啟用 GPU
        from src.service.audio_converter.scipy_converter import ScipyConverter
        self.converter = ScipyConverter(use_gpu=True)
        
    def batch_convert(self, 
                      file_list: list,
                      target_sr: int = 16000,
                      target_channels: int = 1,
                      output_dir: str = "converted/"):
        """批次轉換音訊檔案"""
        Path(output_dir).mkdir(exist_ok=True)
        
        results = []
        for file_path in file_list:
            try:
                # 讀取音訊
                audio_data, sr = self.converter.load_audio(file_path)
                
                # GPU 加速重採樣
                if sr != target_sr:
                    audio_data = self.converter.resample_gpu(
                        audio_data,
                        orig_sr=sr,
                        target_sr=target_sr
                    )
                
                # 聲道轉換
                if audio_data.shape[-1] != target_channels:
                    audio_data = self.converter.convert_channels(
                        audio_data,
                        target_channels
                    )
                
                # 儲存結果
                output_file = Path(output_dir) / Path(file_path).name
                self.converter.save_audio(output_file, audio_data, target_sr)
                
                results.append({
                    'input': file_path,
                    'output': str(output_file),
                    'success': True
                })
                
            except Exception as e:
                logger.error(f"轉換失敗 {file_path}: {e}")
                results.append({
                    'input': file_path,
                    'error': str(e),
                    'success': False
                })
        
        return results
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  audio_converter:
    enabled: true
    default_backend: "auto"      # auto, ffmpeg, scipy
    
    ffmpeg:
      path: "ffmpeg"             # FFmpeg 執行檔路徑
      threads: 4                 # 使用執行緒數
      
    scipy:
      use_gpu: false             # 是否使用 GPU
      gpu_device: 0              # GPU 裝置 ID
      
    quality_presets:
      low:
        bitrate: 64000
        sample_rate: 8000
      medium:
        bitrate: 128000
        sample_rate: 16000
      high:
        bitrate: 256000
        sample_rate: 44100
        
    cache:
      enabled: true              # 啟用轉換快取
      max_size_mb: 100          # 快取大小限制
```

## 支援的格式

### 音訊格式
| 格式 | 讀取 | 寫入 | 壓縮 | 說明 |
|------|------|------|------|------|
| WAV | ✅ | ✅ | ❌ | 無損，通用性佳 |
| MP3 | ✅ | ✅ | ✅ | 有損，檔案小 |
| FLAC | ✅ | ✅ | ✅ | 無損壓縮 |
| AAC | ✅ | ✅ | ✅ | 高效壓縮 |
| OGG | ✅ | ✅ | ✅ | 開源格式 |
| PCM | ✅ | ✅ | ❌ | 原始音訊 |
| MP4 | ✅ | ❌ | ✅ | 音訊軌道 |

### 採樣率
- 8000 Hz (電話品質)
- 16000 Hz (語音標準)
- 22050 Hz (FM 廣播)
- 44100 Hz (CD 品質)
- 48000 Hz (專業音訊)
- 96000 Hz (高解析音訊)
- 192000 Hz (超高解析)

## 效能考量

### 轉換器選擇
- **FFmpeg**: 功能最全，適合各種格式
- **SciPy**: 支援 GPU，適合大批量處理
- **品質優先**: 使用 FLAC 或 WAV
- **速度優先**: 使用 PCM 直接處理

### 最佳化建議
1. **批次處理**: 一次轉換多個檔案
2. **串流處理**: 大檔案使用串流避免記憶體溢出
3. **GPU 加速**: 大量重採樣時使用 GPU
4. **快取結果**: 重複轉換使用快取

## 注意事項

1. **FFmpeg 依賴**: 完整功能需要安裝 FFmpeg
2. **GPU 支援**: 需要 CUDA 或 OpenCL
3. **記憶體使用**: 大檔案建議串流處理
4. **品質損失**: 多次壓縮轉換會累積損失
5. **執行緒安全**: 轉換器實例可並行使用

## 錯誤處理

```python
from src.interface.exceptions import (
    AudioFormatError,
    ConversionError
)

try:
    converted = audio_converter.convert(audio_data)
except AudioFormatError as e:
    logger.error(f"不支援的格式: {e}")
    # 嘗試其他轉換器
    use_fallback_converter()
except ConversionError as e:
    logger.error(f"轉換失敗: {e}")
```

## 未來擴展

- WebAssembly 後端支援
- 即時編碼器整合
- 雲端轉換服務
- AI 音質增強
- 批次並行處理優化