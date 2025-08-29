# ASRHub 視覺化測試

本目錄包含 ASRHub 各服務的視覺化測試工具，使用 matplotlib 繪製即時圖表。

## 測試項目

### 1. 錄音服務測試 (test_recording_visual.py)
- **上半部**：即時麥克風輸入波形
- **下半部**：錄音歷史波形（隨時間延長）
- **功能**：測試錄音服務是否正常工作，觀察音訊緩衝狀態

### 2. VAD 服務測試 (test_vad_visual.py)
- **上半部**：即時麥克風輸入波形
- **下半部**：VAD 檢測結果（語音活動區域標記）
  - 紅色區域：檢測到語音
  - 黃色虛線區域：正在進行的語音
  - 綠色線條：VAD 概率曲線
- **功能**：測試 Silero VAD 服務的語音檢測能力

### 3. 喚醒詞服務測試 (test_wakeword_visual.py)
- **上半部**：即時麥克風輸入波形
- **下半部**：喚醒詞檢測信心度圖
  - 紅色虛線：檢測閾值 (0.5)
  - 綠色矩形：檢測到喚醒詞的時刻
  - 綠色線條：信心度曲線
- **功能**：測試 OpenWakeWord 服務的喚醒詞檢測

## 使用方法

### 方法一：使用 Python 啟動器（推薦）
```bash
# 執行視覺化測試啟動器
python run_visual_tests.py
```

### 方法二：直接執行 Python 腳本
```bash
# 測試錄音服務
python test_recording_visual.py

# 測試 VAD 服務
python test_vad_visual.py

# 測試喚醒詞服務
python test_wakeword_visual.py
```

### 方法三：使用 Shell 腳本（Linux/macOS）
```bash
# 給予執行權限
chmod +x test_all_visual.sh

# 執行測試選單
./test_all_visual.sh
```

**重要提示**：
- 測試會持續運行，無需輸入時長
- 關閉 matplotlib 視窗即可停止測試
- 使用 Ctrl+C 可中斷測試程序

## 依賴套件

確保已安裝以下 Python 套件：
```bash
pip install matplotlib pyaudio numpy
```

對於 OpenWakeWord 測試，還需要：
```bash
pip install openwakeword
```

## 測試流程

1. **準備環境**
   - 確保麥克風已連接並正常工作
   - 確保已安裝所有依賴套件
   - 確保 config/config.yaml 已正確配置

2. **執行測試**
   - 運行測試腳本或啟動器
   - 測試會自動開始，無需輸入時長
   - 對著麥克風說話或發出聲音

3. **觀察結果**
   - 即時波形應該反映麥克風輸入
   - VAD 應該能檢測到語音段落
   - OpenWakeWord 應該能檢測到關鍵字（預設 "Hey Jarvis"）

4. **結束測試**
   - 等待測試時間結束
   - 或關閉 matplotlib 視窗
   - 查看控制台輸出的測試結果摘要

## 注意事項

1. **麥克風權限**：確保系統已授予程式麥克風訪問權限
2. **音訊格式**：預設使用 16kHz, 單聲道, int16 格式
3. **緩衝大小**：可以根據需要調整 chunk_size
4. **喚醒詞**：預設使用 "Hey Jarvis"，可在配置中修改

## 問題排查

### 問題：無法開啟麥克風
- 檢查麥克風是否正確連接
- 檢查系統音訊設定
- 確認 PyAudio 已正確安裝

### 問題：沒有檢測到語音/喚醒詞
- 調高說話音量
- 調整檢測閾值（在配置文件中）
- 確認服務已正確初始化

### 問題：圖表不更新
- 檢查 matplotlib backend 設定
- 嘗試使用不同的 backend：
  ```python
  import matplotlib
  matplotlib.use('TkAgg')  # 或 'Qt5Agg'
  ```

## 架構說明

這些測試工具展示了 ASRHub 的核心架構：

1. **Session-based 設計**：每個測試創建獨立的 session
2. **Audio Queue 管理**：音訊通過 AudioQueueManager 傳遞
3. **回調模式**：服務使用回調函數通知狀態變化
4. **單例模式**：服務使用 SingletonMixin 實現單例
5. **配置管理**：通過 ConfigManager 載入 yaml2py 生成的配置

## 更新歷史

- 2024-12-26：重寫所有視覺化測試以符合新的服務架構
  - 更新為 session-based 回調模式
  - 整合 BufferManager 和 AudioQueueManager
  - 使用新的介面定義（VADResult, WakewordDetection）
  - 修復 Silero VAD 的 LSTM 隱藏狀態管理
  - 添加黑底主題和中文字體支援