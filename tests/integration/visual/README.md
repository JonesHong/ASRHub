# 視覺化整合測試

這個目錄包含了 ASR Hub 各個組件的視覺化整合測試工具。

## 測試工具

### 1. VAD 視覺化測試 (test_vad_visual.py)
測試語音活動檢測 (Voice Activity Detection) 功能，顯示即時的音訊波形和 VAD 狀態。

```bash
# 從專案根目錄執行
python tests/integration/visual/test_vad_visual.py

# 或使用測試運行器
python tests/integration/visual/run_visual_tests.py
```

功能：
- 即時音訊波形顯示
- VAD 機率和閾值視覺化
- 語音段落統計

### 2. 喚醒詞視覺化測試 (test_wakeword_visual.py)
測試喚醒詞檢測功能，支持 "嗨，高醫" 和 "hi kmu" 等喚醒詞。

```bash
# 從專案根目錄執行
python tests/integration/visual/test_wakeword_visual.py
```

功能：
- 即時音訊波形顯示
- 喚醒詞檢測分數追蹤
- 檢測事件記錄

### 3. 錄音視覺化測試 (test_recording_visual.py)
測試錄音功能，顯示即時音量和波形。

```bash
# 從專案根目錄執行
python tests/integration/visual/test_recording_visual.py
```

功能：
- 即時音訊波形顯示
- 音量歷史圖表
- 錄音檔案儲存（儲存在 test_recordings/ 目錄）

## 執行要求

1. 需要有可用的麥克風設備
2. 需要安裝視覺化相關套件：
   ```bash
   pip install matplotlib pyaudio numpy
   ```
3. 對於喚醒詞測試，需要設定 HF_TOKEN 環境變數：
   ```bash
   export HF_TOKEN=your_huggingface_token
   ```

## 測試模式

### VAD 測試支持三種模式：
1. **即時音訊測試**：使用麥克風進行即時測試
2. **音訊檔案測試**：測試預錄製的音訊檔案
3. **合成音訊測試**：使用生成的測試音訊

### 錄音測試：
- 可自定義錄音時長（5-60秒）
- 錄音檔案自動儲存到 `test_recordings/` 目錄

## 注意事項

- 這些測試工具會顯示 matplotlib 視窗，需要在有圖形界面的環境中執行
- 測試過程中會使用系統預設麥克風
- 按 Ctrl+C 或關閉視窗可以優雅地結束測試
- 所有測試都使用專案的視覺化工具 `src/utils/visualization.py`

## 技術架構

這些測試工具使用專案中的統一視覺化模組 `src/utils/visualization.py`，該模組提供：
- `VADVisualization` - VAD 專用視覺化
- `WakeWordVisualization` - 喚醒詞檢測視覺化
- `RecordingVisualization` - 錄音狀態監控視覺化

每個測試檔案都實現了自己的音訊處理邏輯，並使用相應的視覺化類來顯示結果。