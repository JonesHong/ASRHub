# Buffer 策略測試指南

針對「測試一二三，今天天氣如何」辨識效果不佳的問題分析與解決方案。

## 問題分析

從測試結果看出，問題主要出在：

1. **固定時間分割問題**: 原測試腳本使用固定 2 秒分割，可能切斷語音中間
2. **噪音門過於激進**: 音頻增強器的噪音門 (-45dBFS) 將大部分語音當作噪音過濾掉 
3. **音量分析不當**: 只有第一個 chunk 成功識別，其餘都被門控掉了

## 解決方案測試腳本

已創建三個測試腳本來分別驗證問題：

### 1. `test_wav_no_enhancement.py` - 無增強處理測試

```bash
# 直接測試，不使用音頻增強
python test_wav_no_enhancement.py test_record.wav

# 使用較大的 chunk 避免切斷語音
python test_wav_no_enhancement.py test_record.wav 8.0
```

**用途**: 
- 測試是否為音頻增強導致的問題
- 使用較大的 chunk (5秒) 避免切斷語音
- 顯示詳細的音頻特徵分析

### 2. `test_wav_with_vad.py` - VAD 智能分割測試

```bash
# 使用 VAD 智能分割語音段
python test_wav_with_vad.py test_record.wav

# 啟用音頻增強
python test_wav_with_vad.py test_record.wav --enhance

# 調整語音段參數
python test_wav_with_vad.py test_record.wav --min-duration 1.0 --max-duration 10.0
```

**用途**:
- 使用 Silero VAD 檢測語音邊界，避免切斷語音
- 可選擇是否啟用音頻增強進行對比
- 智能語音段分割，更符合實際語音特徵

### 3. `adjust_audio_enhancement.py` - 臨時調整音頻增強設置

```bash
# 禁用噪音門並執行測試
python adjust_audio_enhancement.py test_wav_simple.py test_record.wav

# 或配合其他測試腳本
python adjust_audio_enhancement.py test_wav_with_vad.py test_record.wav --enhance
```

**用途**:
- 臨時禁用噪音門功能
- 更保守的增益和壓縮設置
- 測試完後自動恢復原始設置

## 建議測試順序

1. **無增強測試** (確認基礎功能):
   ```bash
   python test_wav_no_enhancement.py test_record.wav
   ```

2. **VAD 智能分割測試** (驗證切分策略):
   ```bash
   python test_wav_with_vad.py test_record.wav
   ```

3. **修改增強設置測試** (驗證噪音門影響):
   ```bash
   python adjust_audio_enhancement.py test_wav_simple.py test_record.wav
   ```

4. **對比測試** (VAD + 修改過的增強):
   ```bash
   python adjust_audio_enhancement.py test_wav_with_vad.py test_record.wav --enhance
   ```

## 預期結果

- **原始問題**: 只有第一個 chunk 有結果「測試約30」
- **預期改善**: 完整識別「測試一二三，今天天氣如何」

## 輸出文件說明

測試會產生不同的結果文件：

- `test_record_raw.txt` - 無增強處理的結果
- `test_record_vad.txt` - VAD 分割不增強的結果  
- `test_record_vad_enhanced.txt` - VAD 分割 + 增強的結果

## 進一步優化建議

如果測試結果仍不理想，可以考慮：

1. **調整 VAD 參數**:
   ```bash
   python test_wav_with_vad.py test_record.wav --min-duration 0.3 --max-duration 5.0
   ```

2. **使用不同的 chunk 大小**:
   ```bash
   python test_wav_no_enhancement.py test_record.wav 10.0  # 10秒 chunk
   ```

3. **檢查配置文件**:
   - 確認 `config/config.yaml` 中的音頻增強設置
   - 必要時可以完全禁用: `services.audio_enhancer.enabled: false`

## 問題診斷

如果問題依然存在：

1. **檢查音頻品質**: 確認原始音頻清晰度
2. **模型問題**: 嘗試不同的 Whisper 模型大小
3. **語言設置**: 確認是否正確設置中文識別
4. **硬體效能**: 檢查 CPU/記憶體是否足夠

## 配置優化

長期解決方案是調整 `src/service/audio_enhancer.py` 中的設置：

1. 提高噪音門閾值 (從 -45dBFS 改為 -50dBFS)
2. 降低 SNR 觸發降噪的閾值 (從 10dB 改為 5dB)  
3. 使用更保守的增益設置

這樣可以避免正常語音被誤判為噪音。