# ASR Hub Provider 池化整合計劃

## 📋 概述

本文檔詳細記錄了將 Provider 池化機制整合到 ASR Hub 系統的完整計劃。通過實施池化，我們將解決 WhisperProvider 的並發瓶頸問題，預期可將系統吞吐量提升 3-5 倍。

**關鍵目標**：
- 解決並發處理瓶頸
- 保持系統架構完整性
- 確保向後兼容
- 提供完善的監控和錯誤處理

## 🏗️ 系統架構

### 現有架構
```
ASR Hub API Layer
    ↓
SessionManager
    ↓
ProviderManager (單例模式)
    ↓
Provider 實例 (全局鎖)
```

### 目標架構
```
┌─────────────────────────────────────────────────────────┐
│                    ASR Hub API Layer                     │
├─────────────────────────────────────────────────────────┤
│                   SessionManager                         │
├─────────────────────────────────────────────────────────┤
│                  ProviderManager                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              ProviderPool (NEW)                  │   │
│  │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐           │   │
│  │  │ P1  │  │ P2  │  │ P3  │  │ ... │           │   │
│  │  └─────┘  └─────┘  └─────┘  └─────┘           │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## ✅ 實施檢查清單

### Phase 1: 基礎架構實現

#### 1. ProviderPool 類別開發

- [x] 創建 `src/providers/provider_pool.py` 檔案
- [x] 實現 ProviderPool 基礎類別結構
  ```python
  class ProviderPool:
      def __init__(self, provider_class, provider_type, min_size, max_size)
      async def initialize()
      async def acquire() -> ProviderBase
      async def release(provider: ProviderBase)
      async def health_check() -> Dict[str, Any]
      async def scale(new_size: int)
      async def cleanup()
  ```
- [x] 實現池的核心邏輯
  - [x] 使用 `asyncio.Queue` 管理可用實例
  - [x] 實現 acquire 超時處理
  - [x] 實現 release 時的狀態檢查
  - [x] 追蹤使用中的實例 (`self._in_use`)
- [x] 添加統計資訊收集
  - [x] 總請求數
  - [x] 平均等待時間
  - [x] 當前使用率
  - [x] 健康狀態

#### 2. ProviderManager 整合

- [x] 修改 `src/providers/manager.py`
- [x] 新增池化相關屬性
  ```python
  self.provider_pools: Dict[str, ProviderPool] = {}
  self.pool_enabled: Dict[str, bool] = {}
  ```
- [x] 修改 `_initialize_enabled_providers` 方法
  - [x] 讀取池化配置
  - [x] 根據配置創建池或單例
  - [x] 初始化池實例
- [x] 修改 `transcribe` 方法
  - [x] 判斷是否使用池化
  - [x] 實現 acquire/release 模式
  - [x] 保留原有單例邏輯作為 fallback
- [x] 修改 `transcribe_stream` 方法（相同邏輯）
- [x] 修改 `cleanup` 方法
  - [x] 清理所有池資源
  - [x] 等待所有進行中的請求完成

### Phase 2: 配置系統整合

#### 3. YAML 配置更新

- [x] 更新 `config/config.sample.yaml`
  ```yaml
  providers:
    whisper:
      enabled: true
      model_size: base
      # 新增池化配置
      pool:
        enabled: false  # 預設關閉，需要手動啟用
        min_size: 2
        max_size: 5
        idle_timeout: 300  # 秒
        acquire_timeout: 30  # 秒
        health_check_interval: 60  # 秒
    
    funasr:
      enabled: false
      pool:
        enabled: false
        min_size: 1
        max_size: 3
  ```
- [x] 在配置中添加詳細註解說明
- [x] 提供不同場景的配置範例

#### 4. ConfigManager 更新

- [x] 執行 yaml2py 重新生成配置類別
  ```bash
  yaml2py --config config/config.yaml --output ./src/config
  ```
- [x] 驗證生成的類別包含池化配置
- [x] 測試配置的型別安全性
- [x] 確保 IDE 自動完成正常工作

### Phase 3: 監控與健康檢查

#### 5. 監控系統實現

- [x] 整合 pretty-loguru 日誌
  - [x] 池狀態定期輸出
  - [x] 請求追蹤日誌
  - [x] 錯誤和警告日誌
- [x] 實現監控方法
  ```python
  def get_pool_status(self) -> Dict[str, Any]
  def log_pool_metrics(self)
  ```
- [x] 監控指標實現
  - [x] 池使用率 (used/total)
  - [x] 平均等待時間
  - [x] 請求成功/失敗率
  - [x] Provider 健康狀態
  - [x] 記憶體/GPU 使用率

#### 6. 健康檢查機制

- [x] 實現被動健康檢查
  - [x] 在 release 時檢查 Provider 狀態
  - [x] 標記異常的 Provider
- [x] 實現主動健康檢查
  - [x] 定期檢查空閒 Provider
  - [x] 使用簡單的測試音訊進行驗證
- [x] 故障處理邏輯
  - [x] 自動移除故障實例
  - [x] 創建替代實例
  - [x] 記錄故障資訊

### Phase 4: 測試與文檔

#### 7. 測試開發

- [ ] 單元測試 (`tests/unit/test_provider_pool.py`)
  - [ ] 測試池的基本操作
  - [ ] 測試並發獲取/釋放
  - [ ] 測試超時處理
  - [ ] 測試健康檢查
  - [ ] 測試故障恢復
- [ ] 整合測試 (`tests/integration/test_pool_integration.py`)
  - [ ] 端到端並發請求測試
  - [ ] 池耗盡情況測試
  - [ ] 配置切換測試（池化/非池化）
  - [ ] 長時間運行穩定性測試
- [ ] 性能測試
  - [ ] 基準測試（單例 vs 池化）
  - [ ] 壓力測試
  - [ ] 資源使用測試

#### 8. 文檔準備

- [ ] 使用指南 (`docs/guides/provider_pooling.md`)
  - [ ] 池化概念說明
  - [ ] 配置指南
  - [ ] 最佳實踐
  - [ ] 常見問題
- [ ] 運維文檔 (`docs/operations/pool_monitoring.md`)
  - [ ] 監控指標解讀
  - [ ] 調優建議
  - [ ] 故障排查流程
  - [ ] 應急處理步驟
- [ ] API 文檔更新
  - [ ] 更新配置說明
  - [ ] 添加池化相關 API

### Phase 5: 部署準備

#### 9. 部署策略

- [ ] 開發環境驗證
  - [ ] 功能測試通過
  - [ ] 性能測試達標
  - [ ] 資源使用合理
- [ ] 預生產環境測試
  - [ ] 部署到測試環境
  - [ ] 執行完整測試套件
  - [ ] 24小時穩定性測試
  - [ ] 故障恢復演練
- [ ] 生產環境部署計劃
  - [ ] 制定灰度發布策略
  - [ ] 準備監控告警
  - [ ] 確認回滾流程
  - [ ] 準備應急響應團隊

#### 10. 回滾準備

- [ ] 確保配置開關正常工作
  ```yaml
  pool:
    enabled: false  # 快速關閉池化
  ```
- [ ] 測試回滾流程
- [ ] 準備回滾腳本
- [ ] 記錄回滾檢查清單

## 🚀 實施時間表

### Week 1: 基礎開發
- ProviderPool 類別實現
- ProviderManager 整合
- 基本單元測試

### Week 2: 完善功能
- 配置系統整合
- 監控和健康檢查
- 完整測試套件

### Week 3: 部署準備
- 文檔編寫
- 性能測試
- 部署演練

### Week 4: 正式上線
- 灰度發布
- 監控和調優
- 問題修復

## 📊 成功指標

1. **性能指標**
   - 並發處理能力提升 3-5 倍
   - 平均響應時間降低 50%
   - 系統吞吐量提升 300%

2. **穩定性指標**
   - 錯誤率 < 0.1%
   - 可用性 > 99.9%
   - 故障恢復時間 < 1 分鐘

3. **資源指標**
   - 記憶體使用可控（< 設定上限）
   - GPU 使用率合理分配
   - 無資源洩漏

## ⚠️ 風險與緩解

### 技術風險
1. **池大小配置不當**
   - 緩解：提供配置建議和自動調整功能
   
2. **Provider 狀態不一致**
   - 緩解：嚴格的健康檢查和狀態管理

3. **並發問題**
   - 緩解：充分的測試和漸進式部署

### 運營風險
1. **監控不足**
   - 緩解：完善的監控系統和告警機制

2. **文檔不完整**
   - 緩解：詳細的文檔和培訓計劃

## 📝 備註

- 所有程式碼修改都需要通過 Code Review
- 每個階段完成後進行階段性評審
- 保持與現有系統的兼容性是首要原則
- 遇到問題及時溝通和記錄

---

最後更新時間：2024-01-26