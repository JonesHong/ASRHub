# WebASRCore 文檔概覽

## 文檔結構

本文檔按照邏輯內容組織，分為以下幾個主要部分：

### 1. 概覽 (Overview)
- 專案介紹
- 核心理念
- 特性列表
- 快速開始

### 2. 架構 (Architecture)  
- 系統架構設計
- 技術架構
- 狀態機設計
- 事件流架構

### 3. 核心組件 (Core Components)
- FSM 狀態機
- AudioQueue 音訊隊列
- BufferManager 緩衝管理
- 事件系統

### 4. Provider 系統 (Providers)
- ASR Provider 介面
- Web Speech Provider
- Whisper Provider
- Provider 管理

### 5. 服務層 (Services)
- 執行模式管理
- VAD 服務
- Wake Word 服務
- 音訊處理服務

### 6. 部署配置 (Deployment)
- COOP/COEP 配置
- CSP 政策
- CDN 策略
- 瀏覽器兼容性

### 7. 故障排除 (Troubleshooting)
- 診斷 API
- 常見問題
- 效能優化
- 調試指南

### 8. API 參考 (API Reference)
- 配置選項
- 公開 API
- 事件列表
- 型別定義

## 文檔維護原則

1. **避免重複**：相同內容只在一處定義，其他地方引用
2. **邏輯分組**：按功能而非章節號組織內容
3. **漸進式詳細**：從概念到實作逐層深入
4. **實用優先**：包含實際可用的程式碼範例

## 內容映射表

| 原章節 | 新位置 | 說明 |
|--------|--------|------|
| 執行摘要 | 01-overview | 專案總覽 |
| 1. 架構總覽 | 02-architecture | 系統設計 |
| 2. 技術架構 | 02-architecture | 合併到架構章節 |
| 3. 核心組件設計 | 03-core-components | FSM、Queue、Buffer |
| 4. 服務層架構 | 05-services | 各種服務實作 |
| 5. 配置系統 | 08-api-reference | 配置 API |
| 6. 使用範例 | 01-overview | 快速開始指南 |
| 7. 模型管理（重複） | 05-services | 合併為模型服務 |
| 8. 性能優化 | 07-troubleshooting | 效能調優 |
| 9. 測試策略 | 07-troubleshooting | 測試指南 |
| 10. 部署（重複） | 06-deployment | 合併部署內容 |
| 11. Worker 整合 | 05-services | Worker 服務 |
| 12. 系統架構圖 | 02-architecture | 架構圖表 |
| 13. COOP/COEP | 06-deployment | 部署配置 |
| 14. CSP 配置 | 06-deployment | 安全配置 |
| 15. 瀏覽器兼容 | 06-deployment | 兼容性矩陣 |
| 16. IndexedDB | 05-services | 儲存服務 |
| 17. 診斷 API | 07-troubleshooting | 診斷工具 |
| 18. 效能預期 | 07-troubleshooting | 效能基準 |
| 19. CDN 策略 | 06-deployment | CDN 配置 |
| 20. 安全聲明 | 06-deployment | 安全性 |
| 21. VAD 參數 | 08-api-reference | 參數配置 |