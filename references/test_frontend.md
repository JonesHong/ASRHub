# 前端測試指南

## 測試步驟

1. **啟動 ASR Hub 服務**
   ```bash
   source venv/bin/activate
   python main.py
   ```

2. **啟動前端服務器**
   ```bash
   python frontend_server.py
   ```

3. **訪問前端**
   - 打開瀏覽器訪問: http://localhost:8080

4. **測試流程**
   - 選擇 WebSocket 協議
   - 點擊「開始錄音」
   - 說話幾秒鐘
   - 點擊「結束錄音」
   - 點擊「開始辨識」

## 預期行為

1. **錄音階段**
   - 瀏覽器請求麥克風權限
   - 錄音按鈕顯示動畫
   - 錄音結束後顯示音訊預覽

2. **辨識階段**
   - 建立 WebSocket 連接
   - 發送開始命令
   - 分塊發送音訊資料
   - 顯示進度更新
   - 發送停止命令
   - 顯示辨識結果

## 檢查日誌

### 前端日誌（瀏覽器）
- 連接狀態
- 音訊發送進度
- 收到的訊息

### 後端日誌
```
New WebSocket connection: xxx
建立新 session: xxx
Created audio stream for session xxx
接收音訊片段 1, 2, 3...
Received end marker for session xxx
收集完成，共 X 個片段，總大小 Y bytes
轉譯完成: 這是辨識結果（收到 Y bytes 的音訊）
```

## 常見問題

1. **連接失敗**
   - 確認 ASR Hub 正在運行
   - 檢查端口 8765 是否可用

2. **沒有辨識結果**
   - 檢查是否有錄音內容
   - 查看後端日誌是否有錯誤

3. **音訊立即結束**
   - 已修正：現在會等待所有音訊處理完成