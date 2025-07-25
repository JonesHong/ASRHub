# ASR_Hub 第三階段工作清單

## 📋 階段目標
在現有基礎架構上新增 WebSocket 和 Socket.io API 協定層，實現多協定支援。本階段專注於建立 API 協定介面，暫不實作完整的端對端功能。

## ✅ 工作項目清單

### 1. WebSocket API 協定實作（src/api/websocket/）

#### 1.1 WebSocket 基礎架構
- [ ] 1.1.1 建立 WebSocketServer 類別（繼承 APIBase）
  - 使用 aiohttp 或 websockets 套件實作
  - 實作 WebSocket 連線管理（connection pool）
  - 實作心跳機制（ping/pong）
  - 處理連線生命週期（connect、disconnect、error）
- [ ] 1.1.2 定義 WebSocket 訊息格式
  - 設計統一的訊息結構（type、data、session_id、timestamp）
  - 支援二進位（音訊）和文字（控制指令）訊息
  - 實作訊息序列化/反序列化
- [ ] 1.1.3 實作認證機制
  - 支援 token-based 認證
  - 連線時驗證
  - Session 綁定

#### 1.2 控制指令實作
- [ ] 1.2.1 實作控制指令處理器
  - 解析 start、stop、status、busy_start、busy_end 指令
  - 與 SessionManager 整合
  - 狀態同步機制
- [ ] 1.2.2 實作指令回應機制
  - 同步回應（ack/nack）
  - 錯誤訊息格式
  - 指令執行狀態追蹤

#### 1.3 音訊串流處理
- [ ] 1.3.1 實作音訊接收處理
  - 二進位訊息解析
  - 音訊格式驗證
  - 串流緩衝管理
- [ ] 1.3.2 實作轉譯結果推送
  - 即時推送轉譯結果
  - 支援部分結果（interim）和最終結果（final）
  - 錯誤推送機制

#### 1.4 連線管理
- [ ] 1.4.1 實作連線池管理
  - 最大連線數限制
  - 連線健康檢查
  - 自動重連機制（客戶端指導）
- [ ] 1.4.2 實作廣播機制
  - 系統訊息廣播
  - 特定 session 訊息推送
  - 群組訊息支援（預留）

### 2. Socket.io API 協定實作（src/api/socketio/）

#### 2.1 Socket.io 基礎架構
- [ ] 2.1.1 建立 SocketIOServer 類別（繼承 APIBase）
  - 使用 python-socketio 套件實作
  - 整合 ASGI/WSGI 伺服器（如 uvicorn）
  - 實作 namespace 管理
  - 支援 Socket.io 協定版本（v4/v5）
- [ ] 2.1.2 定義事件架構
  - 設計事件命名規範（asr:start、asr:stop、asr:transcript 等）
  - 實作事件處理器註冊機制
  - 支援自定義事件
- [ ] 2.1.3 實作房間（room）機制
  - Session-based 房間管理
  - 自動加入/離開房間
  - 房間內廣播支援

#### 2.2 控制事件實作
- [ ] 2.2.1 實作控制事件處理器
  - 'control:start'、'control:stop' 等事件
  - 'status:query'、'status:update' 事件
  - 'busy:start'、'busy:end' 事件
- [ ] 2.2.2 實作事件確認機制
  - 使用 Socket.io 的 acknowledgment 功能
  - 逾時處理
  - 重試機制

#### 2.3 音訊串流處理
- [ ] 2.3.1 實作音訊事件處理
  - 'audio:chunk' 事件接收音訊資料
  - 支援 base64 編碼的音訊資料
  - 支援分塊傳輸
- [ ] 2.3.2 實作轉譯結果事件
  - 'transcript:partial' 部分結果
  - 'transcript:final' 最終結果
  - 'transcript:error' 錯誤訊息

#### 2.4 進階功能
- [ ] 2.4.1 實作中介軟體（middleware）
  - 認證中介軟體
  - 日誌中介軟體
  - 錯誤處理中介軟體
- [ ] 2.4.2 實作客戶端狀態同步
  - 連線狀態變更通知
  - Session 狀態同步
  - 系統狀態廣播

### 3. 協定共用元件（src/api/common/）

#### 3.1 訊息格式標準化
- [ ] 3.1.1 建立統一的訊息模型
  - BaseMessage 類別（適用所有協定）
  - 控制訊息模型（ControlMessage）
  - 音訊訊息模型（AudioMessage）
  - 轉譯結果模型（TranscriptMessage）
- [ ] 3.1.2 實作訊息轉換器
  - HTTP SSE ↔ WebSocket ↔ Socket.io 格式轉換
  - 保證跨協定的一致性
  - 版本相容性處理

#### 3.2 Session 協定適配器
- [ ] 3.2.1 建立 ProtocolAdapter 介面
  - 統一的 session 管理介面
  - 協定特定的實作細節封裝
  - 狀態同步機制
- [ ] 3.2.2 實作跨協定 session 共享
  - Session 資料結構擴充（支援多協定）
  - 協定切換支援（同一 session）
  - Session 遷移機制

#### 3.3 錯誤處理標準化
- [ ] 3.3.1 定義統一錯誤碼
  - 協定無關的錯誤碼（1xxx）
  - 協定特定的錯誤碼（2xxx-4xxx）
  - 錯誤碼對應表
- [ ] 3.3.2 實作錯誤處理器
  - 統一的錯誤格式化
  - 錯誤日誌記錄
  - 客戶端友善的錯誤訊息

### 4. 協定管理器（src/api/manager.py）

#### 4.1 API Manager 實作
- [ ] 4.1.1 建立 APIManager 類別
  - 管理所有 API 協定實例
  - 協定註冊機制
  - 生命週期管理
- [ ] 4.1.2 實作協定路由
  - 根據請求類型路由到對應協定
  - 負載平衡（如果需要）
  - 健康檢查

#### 4.2 協定配置管理
- [ ] 4.2.1 擴充配置結構
  - 更新 config.yaml 支援 WebSocket 和 Socket.io 配置
  - 協定特定的配置項（port、path、cors 等）
  - 重新生成配置類別
- [ ] 4.2.2 實作動態配置
  - 協定啟用/停用
  - 運行時配置更新
  - 配置驗證

### 5. 整合與測試準備

#### 5.1 ASRHub 整合
- [ ] 5.1.1 更新 ASRHub 主類別
  - 整合 WebSocket 和 Socket.io server
  - 統一的啟動/停止流程
  - 協定狀態監控
- [ ] 5.1.2 實作協定協調
  - 跨協定的 session 管理
  - 統一的事件分發
  - 資源共享機制

#### 5.2 開發工具
- [ ] 5.2.1 建立簡單的測試客戶端
  - WebSocket 測試客戶端（Python）
  - Socket.io 測試客戶端（Python）
  - 基本功能驗證腳本
- [ ] 5.2.2 建立協定文件模板
  - WebSocket API 文件結構
  - Socket.io 事件文件結構
  - 使用範例

### 6. 日誌與監控

#### 6.1 協定層日誌
- [ ] 6.1.1 實作協定特定日誌
  - 連線建立/斷開日誌
  - 訊息收發日誌（可配置層級）
  - 效能指標日誌
- [ ] 6.1.2 整合 pretty-loguru
  - 統一的日誌格式
  - 協定識別標記
  - 美化輸出

#### 6.2 基礎監控
- [ ] 6.2.1 實作連線統計
  - 即時連線數
  - 協定使用分佈
  - 訊息吞吐量
- [ ] 6.2.2 建立健康檢查端點
  - 各協定的健康狀態
  - 系統資源使用情況
  - 簡單的 metrics 輸出

## 🔍 驗收標準
1. ✅ WebSocket 和 Socket.io server 可以正常啟動並接受連線
2. ✅ 兩種協定都能接收並解析控制指令
3. ✅ 基本的訊息收發機制運作正常
4. ✅ Session 管理可跨協定共享
5. ✅ 統一的錯誤處理和日誌輸出
6. ✅ 可透過配置檔啟用/停用特定協定

## 📝 注意事項
1. 本階段專注於協定層實作，暫不處理複雜的業務邏輯
2. 保持與現有 HTTP SSE 實作的一致性
3. 預留擴充空間（gRPC、Redis 等協定）
4. 使用 async/await 確保非阻塞操作
5. 遵循現有的程式碼風格和架構原則
6. 確保向下相容，不影響現有功能

## 🚀 後續規劃（第四階段預覽）
- 完整的端對端功能整合
- 進階 Pipeline operators（VAD、降噪等）
- 更多 ASR Provider 整合
- 效能優化和壓力測試
- 生產環境部署準備

---
建立時間：2025-07-25
最後更新：2025-07-25
負責人：ASR Hub Team