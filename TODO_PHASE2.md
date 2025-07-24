# ASR_Hub 第二階段工作清單

## 📋 階段目標
實作所有基礎類別，建立核心功能框架，優先實作 HTTP SSE API、sample_rate operator 和 local whisper provider。

## ✅ 工作項目清單

### 1. 實作所有基礎類別（Base Classes）

#### 1.1 API 基礎類別（src/api/base.py）
- [ ] 1.1.1 定義 APIBase 抽象類別
  - 定義統一的控制指令介面（start、stop、status、busy_start、busy_end）
  - 定義 transcribe 和 transcribe_stream 抽象方法
  - 實作共用的錯誤處理機制
  - 實作共用的 session 管理介面
- [ ] 1.1.2 定義 APIResponse 資料模型
  - 統一的回應格式（status、data、error、session_id）
  - 支援串流回應的資料結構
- [ ] 1.1.3 實作基礎的請求驗證和參數處理
  - 音訊格式驗證（sample_rate、channels、format）
  - Pipeline 配置驗證

#### 1.2 Pipeline 基礎類別（src/pipeline/base.py）
- [ ] 1.2.1 定義 PipelineBase 抽象類別
  - 實作 RxJS 風格的串流處理介面
  - 定義 process 和 process_stream 方法
  - 實作 operator chain 管理
- [ ] 1.2.2 實作 Pipeline 生命週期管理
  - initialize、start、stop、cleanup 方法
  - 資源管理和釋放機制
- [ ] 1.2.3 建立 Pipeline 配置介面
  - operators 列表管理
  - 動態載入和配置 operators

#### 1.3 Operator 基礎類別（src/pipeline/operators/base.py）
- [ ] 1.3.1 定義 OperatorBase 抽象類別
  - 定義 process 和 process_stream 介面
  - 輸入/輸出格式定義（AudioChunk 資料模型）
  - 實作串流處理的基礎邏輯
- [ ] 1.3.2 實作 Operator 配置管理
  - 參數驗證機制
  - 預設值處理
  - 型別檢查
- [ ] 1.3.3 建立 Operator 鏈接機制
  - next() 和 subscribe() 方法
  - 錯誤傳播機制

#### 1.4 Provider 基礎類別（src/providers/base.py）
- [ ] 1.4.1 定義 ProviderBase 抽象類別
  - 定義 transcribe 和 transcribe_stream 介面
  - 統一的輸入/輸出格式（TranscriptResult 資料模型）
  - 語言和模型配置介面
- [ ] 1.4.2 實作 Provider 生命週期管理
  - 模型載入和初始化
  - 資源管理（GPU/記憶體）
  - 清理和釋放機制
- [ ] 1.4.3 建立 Provider 錯誤處理
  - 統一的異常類型
  - 重試機制
  - Fallback 處理

### 2. 實作資料模型（src/models/）

#### 2.1 音訊資料模型（src/models/audio.py）
- [ ] 2.1.1 定義 AudioChunk 類別
  - 音訊資料（bytes）
  - 取樣率、通道數、格式
  - 時間戳記資訊
- [ ] 2.1.2 定義 AudioFormat 列舉
  - 支援的音訊格式（PCM、WAV、MP3 等）
  - 格式轉換介面

#### 2.2 轉譯結果模型（src/models/transcript.py）
- [ ] 2.2.1 定義 TranscriptResult 類別
  - 轉譯文字（text）
  - 時間戳記（start_time、end_time）
  - 信心分數（confidence）
  - 語言資訊
- [ ] 2.2.2 定義 TranscriptSegment 類別
  - 用於串流結果的片段
  - is_final 標記
  - 替代結果列表

#### 2.3 Session 模型（src/models/session.py）
- [ ] 2.3.1 定義 Session 類別
  - session_id（UUID）
  - 狀態（IDLE、LISTENING、BUSY）
  - 建立時間、最後活動時間
  - Pipeline 配置
  - Provider 配置

### 3. 實作 HTTP SSE Server（優先）

#### 3.1 HTTP SSE 基礎架構（src/api/http_sse/）
- [ ] 3.1.1 建立 SSEServer 類別（繼承 APIBase）
  - 使用 FastAPI 或 aiohttp 實作
  - 實作 SSE 連線管理
  - 實作心跳機制（keep-alive）
- [ ] 3.1.2 實作 SSE 事件格式
  - 定義事件類型（control、transcript、error、status）
  - 實作事件序列化
  - 支援 JSON 格式資料

#### 3.2 控制指令處理（src/api/http_sse/handlers.py）
- [ ] 3.2.1 實作 /control endpoint
  - POST 方法接收控制指令
  - 處理 start、stop、status、busy_start、busy_end
  - 回傳指令執行結果
- [ ] 3.2.2 實作 session 管理
  - 建立新 session
  - 查詢 session 狀態
  - 清理過期 session

#### 3.3 音訊串流處理
- [ ] 3.3.1 實作 /transcribe endpoint（SSE）
  - 建立 SSE 連線
  - 接收音訊資料（透過另一個 endpoint 或 WebSocket）
  - 串流回傳轉譯結果
- [ ] 3.3.2 實作音訊上傳 endpoint
  - POST /audio/upload 接收音訊 chunks
  - 支援 multipart/form-data
  - 驗證音訊格式

### 4. 實作 Sample Rate Operator（優先）

#### 4.1 Sample Rate Adjustment Operator（src/pipeline/operators/sample_rate.py）
- [ ] 4.1.1 建立 SampleRateOperator 類別（繼承 OperatorBase）
  - 實作取樣率轉換演算法
  - 支援常見取樣率（8000、16000、44100、48000 Hz）
  - 使用 scipy 或 librosa 進行重新取樣
- [ ] 4.1.2 實作串流處理
  - 處理不完整的音訊 chunks
  - 維護內部緩衝區
  - 確保音訊連續性
- [ ] 4.1.3 效能優化
  - 實作快取機制（相同轉換參數）
  - 支援批次處理
  - 多執行緒/異步處理

### 5. 實作 Local Whisper Provider（優先）

#### 5.1 Whisper Provider 基礎（src/providers/whisper/provider.py）
- [ ] 5.1.1 建立 WhisperProvider 類別（繼承 ProviderBase）
  - 整合 OpenAI Whisper 或 faster-whisper
  - 實作模型載入（支援不同大小：tiny、base、small、medium、large）
  - 配置 GPU/CPU 執行
- [ ] 5.1.2 實作批次轉譯
  - transcribe 方法（完整音訊）
  - 語言偵測或指定語言
  - 回傳 TranscriptResult

#### 5.2 串流轉譯實作
- [ ] 5.2.1 實作 transcribe_stream 方法
  - 處理即時音訊串流
  - 實作滑動視窗機制
  - 管理內部音訊緩衝區
- [ ] 5.2.2 優化串流效能
  - VAD 整合（只處理有語音的部分）
  - 動態調整視窗大小
  - 實作部分結果快取

#### 5.3 Whisper 特定功能
- [ ] 5.3.1 實作進階功能
  - 時間戳記對齊
  - 字詞級別時間戳記（如果模型支援）
  - 語言機率輸出
- [ ] 5.3.2 錯誤處理和恢復
  - 記憶體不足處理
  - 模型載入失敗處理
  - 自動降級到較小模型

### 6. 核心模組整合（src/core/）

#### 6.1 ASRHub 主類別完善（src/core/asr_hub.py）
- [ ] 6.1.1 整合所有模組
  - 初始化 API servers
  - 初始化 Pipeline manager
  - 初始化 Provider manager
- [ ] 6.1.2 實作主要流程
  - 接收請求 → Pipeline 處理 → Provider 轉譯 → 回傳結果
  - 錯誤處理和日誌記錄
  - 效能監控

#### 6.2 Session Manager 實作（src/core/session_manager.py）
- [ ] 6.2.1 實作 SessionManager 類別
  - 建立、查詢、更新、刪除 session
  - Session 過期管理
  - 並發 session 限制
- [ ] 6.2.2 Session 狀態同步
  - 跨 API 協定的 session 共享
  - 狀態變更通知機制

#### 6.3 有限狀態機實作（src/core/fsm.py）
- [ ] 6.3.1 實作 FSM 類別
  - 定義狀態（IDLE、LISTENING、BUSY）
  - 定義狀態轉換規則
  - 實作狀態轉換方法
- [ ] 6.3.2 狀態管理
  - 狀態持久化
  - 狀態變更回調
  - 並發狀態管理

### 7. 串流處理模組（src/stream/）

#### 7.1 音訊串流處理（src/stream/audio_stream.py）
- [ ] 7.1.1 實作 AudioStream 類別
  - 接收音訊資料
  - 管理串流生命週期
  - 實作背壓（backpressure）處理
- [ ] 7.1.2 串流分發
  - 分發到多個 operators
  - 支援多個訂閱者

#### 7.2 Buffer 管理（src/stream/buffer_manager.py）
- [ ] 7.2.1 實作 BufferManager 類別
  - 環形緩衝區實作
  - 溢出處理策略
  - 記憶體使用監控
- [ ] 7.2.2 緩衝區操作
  - 寫入、讀取、清空
  - 並發安全操作
  - 效能優化

### 8. Manager 類別實作

#### 8.1 Pipeline Manager（src/pipeline/manager.py）
- [ ] 8.1.1 實作 PipelineManager 類別
  - Pipeline 實例管理
  - 動態創建和配置 pipeline
  - Pipeline 驗證
- [ ] 8.1.2 Operator 註冊機制
  - 註冊可用的 operators
  - 動態載入 operator

#### 8.2 Provider Manager（src/providers/manager.py）
- [ ] 8.2.1 實作 ProviderManager 類別
  - Provider 實例管理
  - 負載平衡（如果有多個 provider）
  - Provider 健康檢查
- [ ] 8.2.2 Provider 路由
  - 根據語言選擇 provider
  - Fallback 機制
  - 優先級管理

### 9. 工具函式實作（src/utils/）

#### 9.1 音訊處理工具（src/utils/audio_utils.py）
- [ ] 9.1.1 實作音訊格式轉換
  - PCM ↔ WAV 轉換
  - 採樣率轉換函式
  - 通道數轉換
- [ ] 9.1.2 音訊分析工具
  - 計算音量（RMS）
  - 靜音偵測
  - 音訊長度計算

#### 9.2 驗證工具（src/utils/validators.py）
- [ ] 9.2.1 實作配置驗證
  - Pipeline 配置驗證
  - Provider 配置驗證
  - API 參數驗證
- [ ] 9.2.2 音訊格式驗證
  - 支援格式檢查
  - 參數範圍檢查

### 10. 例外處理完善（src/core/exceptions.py）
- [ ] 10.1 定義自定義例外類別
  - ASRHubException（基礎類別）
  - ConfigurationError
  - PipelineError
  - ProviderError
  - StreamError
  - SessionError
- [ ] 10.2 例外處理機制
  - 統一的錯誤訊息格式
  - 錯誤碼定義
  - 錯誤追蹤和日誌

## 🔍 驗收標準
1. ✅ 所有基礎類別都已實作且遵循 SOLID 原則
2. ✅ HTTP SSE server 可以接收控制指令並回應
3. ✅ Sample rate operator 可以正確轉換音訊取樣率
4. ✅ Local Whisper provider 可以進行基本的語音轉文字
5. ✅ 整體系統可以完成：接收音訊 → Pipeline 處理 → Whisper 轉譯 → 回傳結果的完整流程
6. ✅ 所有模組都有適當的錯誤處理和日誌記錄

## 📝 注意事項
1. 專注於核心功能，避免過度設計
2. 使用 pretty-loguru 記錄所有重要操作
3. 確保所有類別都有完整的 docstring
4. 遵循 Python 型別提示（typing）
5. 保持程式碼簡潔，遵循 KISS 原則
6. 不實作測試、文件和部署相關內容

## 🚀 下一階段預告
第三階段將專注於：
- 實作其他通訊協定（WebSocket、Socket.io 等）
- 實作其他 Pipeline Operators（VAD、降噪等）
- 整合其他 ASR Providers（FunASR、Vosk 等）
- 效能優化和穩定性提升

---
建立時間：2025-07-24
最後更新：2025-07-24
負責人：ASR Hub Team