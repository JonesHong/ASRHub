# ASR_Hub 第三階段工作清單

## 📋 階段目標
在第二階段完成的基礎上，專注於實作 WebSocket 和 Socket.io 通訊協定，擴展系統的即時通訊能力，完善 API 層的多協定支援。

## ✅ 工作項目清單

### 1. WebSocket API 實作（src/api/websocket/）

#### 1.1 WebSocket Server 基礎架構
- [x] 1.1.1 建立 WebSocketServer 類別（繼承 APIBase）
  - 使用 websockets 或 aiohttp 實作 WebSocket 服務器
  - 實作連線管理（connection pool）
  - 實作心跳機制（ping/pong）
  - 支援自動重連機制
- [x] 1.1.2 實作 WebSocket 訊息格式
  - 定義訊息類型（control、audio、transcript、error、status）
  - 實作二進位（音訊）和文字（控制/結果）訊息處理
  - 支援 JSON 格式的控制訊息
- [x] 1.1.3 連線生命週期管理
  - on_connect：建立新 session
  - on_message：處理訊息路由
  - on_disconnect：清理資源
  - on_error：錯誤處理

#### 1.2 WebSocket 控制指令處理
- [x] 1.2.1 實作控制指令處理器
  - 解析 JSON 格式控制訊息
  - 處理 start、stop、status、busy_start、busy_end 指令
  - 實作指令回應機制
- [x] 1.2.2 實作雙向通訊機制
  - 客戶端發送音訊資料（二進位）
  - 客戶端發送控制指令（JSON）
  - 服務端推送轉譯結果（JSON）
  - 服務端推送狀態更新（JSON）

#### 1.3 WebSocket 音訊串流處理
- [x] 1.3.1 實作即時音訊串流
  - 接收二進位音訊 chunks
  - 實作音訊緩衝管理
  - 支援不同音訊格式（PCM、WAV）
- [x] 1.3.2 實作串流轉譯整合
  - 與 Pipeline 和 Provider 整合
  - 即時推送部分轉譯結果
  - 實作背壓（backpressure）控制
- [x] 1.3.3 實作連線復用
  - 支援單一連線多個 session
  - 實作 session 切換機制
  - 並發 session 管理

### 2. Socket.io API 實作（src/api/socketio/）

#### 2.1 Socket.io Server 基礎架構
- [x] 2.1.1 建立 SocketIOServer 類別（繼承 APIBase）
  - 使用 python-socketio 實作服務器
  - 整合 aiohttp 或 FastAPI
  - 實作命名空間（namespace）管理
  - 支援房間（room）功能
- [x] 2.1.2 實作 Socket.io 事件系統
  - 定義事件類型（control、audio_chunk、transcript、error、status_update）
  - 實作事件處理器註冊機制
  - 支援自定義事件
- [x] 2.1.3 Socket.io 特有功能
  - 實作廣播機制
  - 支援 acknowledgment 回調
  - 實作中介軟體（middleware）

#### 2.2 Socket.io 控制指令處理
- [x] 2.2.1 實作事件處理器
  - on('control')：處理控制指令
  - on('audio_chunk')：處理音訊資料
  - on('subscribe')：訂閱特定 session
  - on('unsubscribe')：取消訂閱
- [x] 2.2.2 實作房間管理
  - 每個 session 一個房間
  - 支援多客戶端訂閱同一 session
  - 實作房間級廣播

#### 2.3 Socket.io 音訊串流處理
- [x] 2.3.1 實作分塊音訊傳輸
  - 支援 Base64 編碼音訊
  - 支援二進位音訊傳輸
  - 實作 chunk 序號管理
- [x] 2.3.2 實作進度追蹤
  - emit('progress')：推送處理進度
  - emit('partial_result')：推送部分結果
  - emit('final_result')：推送最終結果
- [x] 2.3.3 實作客戶端狀態同步
  - 自動同步 session 狀態變更
  - 推送錯誤和警告訊息
  - 實作斷線重連狀態恢復

### 3. API 共用功能增強

#### 3.1 統一的連線管理器（src/api/connection_manager.py）
- [x] 3.1.1 建立 ConnectionManager 類別
  - 管理所有協定的連線
  - 實作連線池和資源限制
  - 監控連線健康狀態
- [x] 3.1.2 實作跨協定 session 共享
  - 允許不同協定存取同一 session
  - 實作 session 鎖定機制
  - 支援 session 遷移

#### 3.2 統一的訊息路由器（src/api/message_router.py）
- [x] 3.2.1 建立 MessageRouter 類別
  - 統一處理不同協定的訊息
  - 實作訊息類型識別
  - 路由到對應處理器
- [x] 3.2.2 實作訊息轉換
  - HTTP SSE ↔ WebSocket 訊息轉換
  - WebSocket ↔ Socket.io 訊息轉換
  - 統一的內部訊息格式

### 4. 整合測試和驗證

#### 4.1 WebSocket 測試客戶端（test_websocket_client.py）
- [x] 4.1.1 建立 WebSocket 測試客戶端
  - 實作連線和斷線測試
  - 測試所有控制指令
  - 測試音訊串流
- [x] 4.1.2 壓力測試
  - 多連線並發測試
  - 長時間連線穩定性測試
  - 大量資料傳輸測試

#### 4.2 Socket.io 測試客戶端（test_socketio_client.py）
- [x] 4.2.1 建立 Socket.io 測試客戶端
  - 實作事件訂閱測試
  - 測試房間功能
  - 測試廣播機制
- [x] 4.2.2 功能測試
  - 測試斷線重連
  - 測試多客戶端同步
  - 測試錯誤處理

### 5. 前端整合和工具開發

#### 5.1 簡易前端測試介面（frontend/）
- [x] 5.1.1 建立統一的前端測試介面
  - 支援 WebSocket、Socket.io、HTTP SSE 三種協定切換
  - 實作錄音功能（使用 MediaRecorder API）
  - 實作音訊檔案上傳功能
  - 即時顯示辨識結果
- [x] 5.1.2 前端功能增強
  - 雙輸入模式：支援錄音和檔案上傳
  - 智慧模式選擇：根據檔案大小自動選擇串流或一次性模式
  - 連線狀態監控和日誌顯示
  - 音訊預覽播放器

#### 5.2 系統管理工具
- [x] 5.2.1 服務管理腳本（stop_main.py）
  - 實作優雅的服務停止機制
  - 清理所有相關進程
  - 支援根據端口號查找並終止進程
- [x] 5.2.2 測試工具集
  - HTTP SSE 實際轉譯測試（test_httpsse_real.py）
  - 音訊檔案產生工具（使用系統 TTS）
  - 效能測試腳本

### 6. 核心功能修正和改進

#### 6.1 WebSocket 和 Socket.io 修正
- [x] 6.1.1 修正 SessionState 枚舉值處理
  - 統一使用 SessionState 枚舉而非字串
  - 修正 session.state 類型混淆問題
  - 確保所有 API 一致處理狀態
- [x] 6.1.2 實作實際轉譯功能
  - 整合真實 ASR Provider（Whisper）
  - 移除模擬轉譯結果
  - 實作 WebM 到 PCM 音訊格式轉換
  - 完整的音訊緩衝區管理

#### 6.2 HTTP SSE 增強
- [x] 6.2.1 修正 pipeline_manager 屬性問題
  - 更新 SSEServer 初始化參數
  - 確保所有管理器正確傳遞
- [x] 6.2.2 實作完整音訊處理流程
  - _process_audio_chunk 方法：處理串流音訊
  - _process_all_audio 方法：處理完整音訊
  - 整合 Pipeline 和 Provider 處理

## 🔍 驗收標準
1. ✅ WebSocket API 可以建立穩定連線並處理即時音訊串流
2. ✅ Socket.io API 支援多客戶端連線和房間管理
3. ✅ 兩個新協定都能正確處理控制指令（start、stop、status、busy_start、busy_end）
4. ✅ 實作跨協定的 Session 共享機制
5. ✅ 所有 API 協定都能與現有的 Pipeline 和 Provider 整合
6. ✅ 完整的測試腳本驗證功能正常
7. ✅ 前端介面支援所有三種協定（WebSocket、Socket.io、HTTP SSE）
8. ✅ 實作錄音和檔案上傳雙輸入模式
9. ✅ 整合真實 ASR Provider 進行實際語音轉譯
10. ✅ 建立完整的系統管理和測試工具

## 📝 注意事項
1. 確保 WebSocket 和 Socket.io 實作遵循 APIBase 介面
2. 注意處理網路斷線和重連情況
3. 實作適當的背壓控制避免記憶體溢出
4. 使用 pretty-loguru 記錄所有重要事件
5. 確保執行緒/協程安全性
6. 效能測試確保能處理多個並發連線

## 🎯 第三階段完成總結

### 主要成就
1. **多協定支援**：成功實作 WebSocket、Socket.io、HTTP SSE 三種通訊協定
2. **前端整合**：建立統一的測試介面，支援所有協定的測試和驗證
3. **實際轉譯**：整合 Whisper ASR Provider，實現真實語音辨識功能
4. **雙輸入模式**：支援錄音和檔案上傳兩種音訊輸入方式
5. **智慧處理**：根據檔案大小自動選擇最佳處理模式

### 技術亮點
- WebM 到 PCM 格式自動轉換
- 完整的音訊緩衝區管理
- Session 狀態的統一處理
- 跨協定的一致性 API 設計

### 已知問題和改進空間
- 可進一步優化大檔案的串流處理
- 可增加更多音訊格式支援
- 可實作更完善的錯誤恢復機制

---
建立時間：2025-07-25
最後更新：2025-07-26
負責人：ASR Hub Team