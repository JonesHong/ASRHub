# Audio Enhancer Service (音訊增強服務)

## 概述
音訊增強服務提供完整的音訊處理功能，從基礎清理到進階動態處理。採用單例模式，為整個系統提供統一的音訊增強能力。

## 核心功能

### 基礎工具
- **DC Offset 移除** - 消除直流偏移，確保音訊中心對齊
- **高通濾波** - 移除低頻噪音（如風聲、震動）
- **增益調整** - 智慧音量控制
- **硬限幅器** - 防止削波失真

### 進階工具
- **動態範圍壓縮** - 平衡音量動態
- **軟限幅器** - 使用 tanh 避免硬削波失真
- **噪音門** - 自動衰減靜音段落
- **簡易均衡器** - 頻率響應調整（規劃中）

### 智慧處理系統
- **auto_enhance()** - 自動分析音訊特徵並決定最佳處理流程
- **音訊分析** - RMS、峰值、SNR、動態範圍分析
- **預設配方** - VAD、ASR、WakeWord、Recording 專用優化

## 使用方式

### 快速開始（新手模式）
```python
from src.service.audio_enhancer import audio_enhancer

# 自動智慧增強
processed_audio, report = audio_enhancer.auto_enhance(
    audio_bytes,  # 16kHz, mono, int16
    purpose="asr"  # 用途: asr, vad, wakeword, recording, general
)

# 分析報告包含：
# - analysis: 音訊特徵分析（RMS、峰值、SNR 等）
# - decisions: 處理決策（是否需要增益、壓縮等）
# - applied_steps: 實際應用的處理步驟
print(f"音訊分析: {report['analysis']}")
print(f"處理步驟: {report['applied_steps']}")
```

### 預設配方使用
```python
# VAD 專用 - 最小處理，保持原始特徵
vad_audio = audio_enhancer.enhance_for_vad(audio_bytes)

# ASR 專用 - 積極增強，提高辨識率
asr_audio = audio_enhancer.enhance_for_asr(audio_bytes)

# WakeWord 專用 - 與 VAD 相同策略
wake_audio = audio_enhancer.enhance_for_wakeword(audio_bytes)

# Recording 專用 - 保持原始品質，只做基礎清理
rec_audio = audio_enhancer.enhance_for_recording(audio_bytes)
```

### 專家模式（直接使用工具）
```python
import numpy as np

# 轉換為 float32 進行處理
audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

# 基礎清理
audio = audio_enhancer.remove_dc_offset(audio)
audio = audio_enhancer.apply_highpass_simple(audio, alpha=0.95)

# 音量調整
current_rms = audio_enhancer.calculate_rms(audio)
if current_rms < 0.05:  # 音量太小
    audio = audio_enhancer.normalize_rms(audio, target_rms=0.16)
    # 或使用增益
    audio = audio_enhancer.apply_gain(audio, gain_db=6.0)

# 動態處理
audio = audio_enhancer.apply_compression(
    audio,
    threshold=-20,    # 壓縮閾值 (dBFS)
    ratio=2.5,        # 壓縮比例
    attack_ms=5,      # 起音時間
    release_ms=50     # 釋放時間
)

# 防止削波
audio = audio_enhancer.apply_limiter(
    audio,
    ceiling=0.891,    # -1 dBFS
    lookahead_ms=5,   # 前瞻時間
    release_ms=50     # 釋放時間
)

# 噪音門（移除背景噪音）
audio = audio_enhancer.apply_gate(audio, threshold=-40)  # dBFS

# 轉回 int16
processed_bytes = (audio * 32768).astype(np.int16).tobytes()
```

## 配置說明

服務通過 `config.yaml` 配置，主要參數：
```yaml
services:
  audio_enhancer:
    enabled: true
    mvp:
      min_rms_threshold: 0.05    # 最小 RMS 閾值
      target_rms: 0.16           # 目標 RMS (-16 dBFS)
      max_gain: 10.0             # 最大增益
      highpass_alpha: 0.95       # 高通濾波係數
      limiter_threshold: 0.95    # 限幅閾值
    presets:
      vad:
        dc_remove: true
        highpass: true
        normalize: false
        limit: false
      asr:
        dc_remove: true
        highpass: true
        normalize: true
        limit: true
```

## 注意事項

1. **輸入格式**: 預設接收 16kHz, mono, int16 格式音訊
2. **單例模式**: 使用模組級變數 `audio_enhancer`，無需自行實例化
3. **配置載入**: 服務會自動從 ConfigManager 載入配置
4. **效能考量**: 
   - 基礎工具執行速度快，適合即時處理
   - 進階工具（壓縮、限幅）計算較重，建議用於非即時場景
   - auto_enhance 包含完整分析，適合批次處理

## 處理建議

### 不同用途的處理策略
- **VAD/WakeWord**: 最小處理，保留原始語音特徵
- **ASR**: 積極處理，提高辨識準確率
- **Recording**: 保持動態範圍，只做必要保護
- **General**: 平衡處理，適度改善

### 處理順序重要性
1. DC Offset 移除（基礎清理）
2. 高通濾波（移除低頻噪音）
3. 噪音門（移除背景噪音）
4. 增益/標準化（調整音量）
5. 壓縮（控制動態範圍）
6. 限幅（防止削波）

## 擴展性
服務設計為易於擴展，未來可加入：
- 多頻段均衡器
- 降噪演算法整合
- 迴響消除
- 立體聲處理