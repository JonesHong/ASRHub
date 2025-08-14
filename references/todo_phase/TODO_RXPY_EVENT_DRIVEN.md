# ASR Hub RxPY 事件驅動架構 - 直接替換實施計畫

## 📋 總覽
**目標**: 直接將現有架構替換為基於 RxPY 的事件驅動架構  
**優勢**: 系統尚未發布，無需考慮向後相容，可實現最佳架構  
**預計時間**: 2-3 週  
**狀態**: ⏳ 待開始 | 🚧 進行中 | ✅ 完成 | ❌ 已取消  
**優先級**: 🔴 高 | 🟡 中 | 🟢 低  

---

## 🎯 核心原則
1. **直接修改**：不創建平行文件，直接改原文件
2. **簡潔命名**：fsm.py、base.py（無 reactive 後綴）
3. **全面替換**：不保留舊代碼，不需要相容層
4. **專注核心**：先改核心，再擴展到周邊

---

## 🚀 Week 1: 核心重構與基礎設施

### 1.1 FSM 重寫為事件驅動 🔴
- [ ] ⏳ **直接修改 `src/core/fsm.py`**
  - [ ] 安裝 RxPY：`pip install reactivex`
  - [ ] 引入 `BehaviorSubject` 管理狀態（可查詢當前值）
  - [ ] 引入 `Subject` 處理事件流
  - [ ] 重寫 `StateMachine` 類（保持原名或改為 `FSM`）
  - [ ] 實現純函數狀態轉換器 `state_reducer`
  - [ ] 定義完整的 `FCMState` 枚舉（10個狀態）
  - [ ] 定義完整的 `FCMEvent` 枚舉（所有事件類型）
  - [ ] 實現狀態 Hook 機制（enter/exit callbacks）

### 1.2 實現策略模式 🔴
- [ ] ⏳ **在 `src/core/fsm.py` 中加入策略類**
  - [ ] 創建 `FCMStrategy` 抽象基類
  - [ ] 實現 `BatchModeStrategy`（批次處理）
  - [ ] 實現 `NonStreamingStrategy`（非串流實時）
  - [ ] 實現 `StreamingStrategy`（串流實時）
  - [ ] 實現策略選擇邏輯

### 1.3 Operator 基類升級 🔴
- [ ] ⏳ **直接修改 `src/pipeline/operators/base.py`**
  - [ ] 在 `OperatorBase.__init__` 加入 `self.events$ = Subject()`
  - [ ] 實現 `emit_event` 方法
  - [ ] 定義 `OperatorEvent` 數據類
  - [ ] 所有子類自動獲得事件發射能力
  - [ ] 移除不必要的 kwargs 傳遞邏輯

### 1.4 Session 整合 EventBus 🔴
- [ ] ⏳ **創建 `src/core/event_bus.py`**（唯一新文件）
  - [ ] 實現 `SessionEventBus` 類
  - [ ] 使用 `BehaviorSubject` 管理 FCM 狀態流
  - [ ] 使用 `Subject` 管理操作符事件流
  - [ ] 實現事件流合併邏輯（`rx.merge`）
  - [ ] 添加事件過濾和轉換功能

- [ ] ⏳ **修改 `src/core/session_manager.py`**
  - [ ] Session 初始化時創建 EventBus
  - [ ] 整合 FSM 實例與 EventBus
  - [ ] 實現訂閱生命週期管理
  - [ ] 確保 Session 銷毀時清理訂閱

### 1.5 核心組件測試 🟡
- [ ] ⏳ **編寫基礎測試** `tests/unit/test_rxpy/`
  - [ ] FSM 事件驅動測試
  - [ ] EventBus 發布/訂閱測試
  - [ ] 策略模式切換測試
  - [ ] 訂閱清理測試

---

## 🔄 Week 2: Operator 改造與事件流整合

### 2.1 VAD Operator 事件化 🔴
- [ ] ⏳ **直接修改 `src/pipeline/operators/vad/silero_vad.py`**
  - [ ] 注入 EventBus 依賴
  - [ ] 發射 `silence_detected` 事件
  - [ ] 發射 `speech_start` 和 `speech_end` 事件
  - [ ] 移除直接的狀態操作
  - [ ] 實現事件節流（`throttle`）

### 2.2 WakeWord Operator 事件化 🔴
- [ ] ⏳ **直接修改 `src/pipeline/operators/wakeword/openwakeword.py`**
  - [ ] 注入 EventBus 依賴
  - [ ] 發射 `wake_triggered` 事件
  - [ ] 實現防抖動（`debounce`）
  - [ ] 支援多種喚醒源（語音/按鈕/視覺）
  - [ ] 與 FSM 事件系統整合

### 2.3 錄音 Operator 事件化 🟡
- [ ] ⏳ **修改 `src/pipeline/operators/recording/recording_operator.py`**
  - [ ] 訂閱 FSM 狀態變化
  - [ ] 根據狀態決定錄音行為
  - [ ] 發射 `recording_started` 和 `recording_stopped` 事件
  - [ ] 實現緩衝區管理

### 2.4 複雜事件流組合 🔴
- [ ] ⏳ **在 EventBus 中實現事件組合邏輯**
  - [ ] VAD + WakeWord 組合（`combineLatest`）
  - [ ] 實現事件流防抖（`debounce`）
  - [ ] 實現事件流節流（`throttle`）
  - [ ] 錯誤事件處理流
  - [ ] 使用 `share()` 避免重複訂閱

### 2.5 實時 Pipeline 編排器 🔴
- [ ] ⏳ **修改 `src/pipeline/manager.py`**
  - [ ] 整合 EventBus 到 Pipeline
  - [ ] 根據 FSM 狀態協調 Operator
  - [ ] 實現半雙工控制（BUSY 狀態暫停）
  - [ ] 支援並行處理分支

### 2.6 前端事件整合 🟡
- [ ] ⏳ **修改 `src/api/message_router.py`**
  - [ ] 訂閱 EventBus 事件
  - [ ] 定義 20+ 種精細事件類型
  - [ ] 實現事件到前端消息的映射
  - [ ] 支援 WebSocket/Socket.io/SSE 分發

---

## 🎯 Week 3: 測試、優化與交付

### 3.1 其他 Operator 改造 🟡
- [ ] ⏳ **改造剩餘的 Operators**
  - [ ] 音訊格式轉換 Operator
  - [ ] 降噪 Operator
  - [ ] 採樣率調整 Operator
  - [ ] 統一事件發射模式

### 3.2 全面測試重構 🔴
- [ ] ⏳ **重新設計所有測試**
  - [ ] 事件流單元測試
  - [ ] 狀態轉換測試
  - [ ] Operator 事件測試
  - [ ] 端到端整合測試
  - [ ] 多 Session 並發測試

### 3.3 性能優化 🟡
- [ ] ⏳ **優化事件流性能**
  - [ ] 使用 `share()` 優化訂閱
  - [ ] 實現懶加載策略
  - [ ] 背壓處理優化
  - [ ] 記憶體使用分析
  - [ ] 事件處理延遲測試（目標 < 10ms）

### 3.4 調試工具開發 🟢
- [ ] ⏳ **創建 `src/utils/event_debugger.py`**
  - [ ] 事件流記錄器
  - [ ] 事件重播功能
  - [ ] 簡單的 Marble Diagram 生成
  - [ ] 狀態轉換日誌
  - [ ] 性能監控儀表板

### 3.5 文檔與知識轉移 🟢
- [ ] ⏳ **更新技術文檔**
  - [ ] 編寫 RxPY 使用指南
  - [ ] 創建事件流架構圖
  - [ ] 更新 API 文檔
  - [ ] 提供代碼範例
  - [ ] 團隊培訓材料

---

## ✅ 驗收標準

### 功能驗收
- [ ] 所有原有功能正常運作
- [ ] 事件驅動架構完全取代舊架構
- [ ] 三種操作模式（批次/非串流/串流）正常切換
- [ ] 狀態管理正確無誤

### 性能指標
- [ ] 事件處理延遲 < 10ms
- [ ] 記憶體使用穩定（無洩漏）
- [ ] CPU 使用率合理
- [ ] 並發 Session 支援 > 100

### 代碼品質
- [ ] 測試覆蓋率 > 80%
- [ ] 代碼行數減少 20%
- [ ] 無循環依賴
- [ ] 清晰的模組邊界

---

## 🚨 風險管理

| 風險 | 影響 | 緩解措施 | 負責人 |
|------|------|----------|--------|
| RxPY 學習曲線 | 🟡 中 | 提前準備培訓材料、代碼範例 | - |
| 調試複雜度增加 | 🟢 低 | 開發專用調試工具 | - |
| 訂閱洩漏 | 🟢 低 | 嚴格的生命週期管理、自動清理 | - |
| 測試重寫工作量 | 🟡 中 | 分階段進行、優先核心功能 | - |

---

## 📝 備註

1. **依賴安裝**：
   ```bash
   pip install reactivex
   ```

2. **命名規範**：
   - 事件流變數使用 `$` 後綴（如 `events$`、`state$`）
   - 事件類型使用 PascalCase（如 `SilenceDetected`）
   - 保持原有文件名，不加 reactive 後綴

3. **關鍵決策**：
   - 使用 BehaviorSubject 管理狀態（需要查詢當前值）
   - 使用 Subject 處理純事件流
   - Session 級別的 EventBus（每個 Session 獨立）
   - 直接修改現有文件，不創建平行版本

4. **成功指標**：
   - 2-3 週內完成全部實施
   - 代碼更簡潔、架構更清晰
   - 團隊掌握 RxPY 基本概念
   - 系統穩定性和性能達標

---

**創建日期**: 2025-01-12  
**最後更新**: 2025-01-12  
**狀態**: ⏳ 待開始