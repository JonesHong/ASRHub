# ASR Hub 技術改進 TodoList

> 基於架構分析的技術改進任務清單，按優先級排序，不包含安全相關任務（因部署於內網環境）

## 優先級說明

- **P0 - 關鍵問題**：影響系統穩定性，必須立即修復
- **P1 - 重要改進**：性能和用戶體驗問題，1-2週內完成
- **P2 - 優化項目**：架構和擴展性改進，1個月內完成
- **P3 - 長期規劃**：未來功能演進，3個月內完成

---

## P0: 關鍵問題（立即修復）

### T001: 修復 WebSocket 連接內存洩漏
**問題描述**：WebSocket 連接斷開時，connections 和 chunk_sequences 字典未正確清理  
**影響範圍**：長期運行導致內存持續增長，最終 OOM  
**解決方案**：
```python
# 在 WebSocketServer 中添加清理邏輯
async def _cleanup_connection(self, connection_id: str):
    async with self._connection_lock:
        if connection_id in self.connections:
            connection = self.connections.pop(connection_id)
            await connection.close()
        self.chunk_sequences.pop(connection_id, None)
        # 清理相關音頻緩衝
```
**涉及文件**：
- `src/api/websocket/server.py`
- `src/api/websocket/stream_manager.py`

**預估工時**：4 小時  
**驗收標準**：
- 連接斷開後相關資源完全釋放
- 內存洩漏檢測工具無異常
- 壓力測試 1000 次連接/斷開無內存增長

---

### T002: 解決音頻隊列並發競態條件
**問題描述**：多個協程同時為同一 session_id 創建隊列時存在競態條件  
**影響範圍**：可能導致音頻數據丟失或重複處理  
**解決方案**：
```python
# AudioQueueManager 添加鎖保護
class AudioQueueManager:
    def __init__(self):
        self._queue_lock = asyncio.Lock()
    
    async def create_queue(self, session_id: str, config):
        async with self._queue_lock:
            if session_id in self.queues:
                return self.queues[session_id]
            # 創建新隊列
```
**涉及文件**：
- `src/core/audio_queue_manager.py`

**預估工時**：3 小時  
**驗收標準**：
- 並發創建測試無重複隊列
- 無數據丟失或重複
- 性能影響 <5%

---

### T003: 修復 SessionEffects 重複轉譯問題
**問題描述**：_transcription_processing 集合在異常時未正確清理，導致 session 無法再次轉譯  
**影響範圍**：轉譯失敗後該 session 永久阻塞  
**解決方案**：
```python
# 使用 context manager 確保清理
from contextlib import asynccontextmanager

@asynccontextmanager
async def transcription_lock(self, session_id):
    self._transcription_processing.add(session_id)
    try:
        yield
    finally:
        self._transcription_processing.discard(session_id)
```
**涉及文件**：
- `src/store/sessions/sessions_effects.py`

**預估工時**：2 小時  
**驗收標準**：
- 異常情況下 session_id 正確移除
- 轉譯失敗後可重新嘗試
- 無死鎖情況

---

## P1: 重要改進（1-2週）

### T004: 前端音頻處理升級到 AudioWorklet
**問題描述**：ScriptProcessorNode 已棄用，延遲高且佔用主線程  
**影響範圍**：音頻處理延遲增加 50-100ms，影響實時性  
**解決方案**：
```javascript
// 創建 AudioWorklet 處理器
class AudioProcessor extends AudioWorkletProcessor {
    process(inputs, outputs, parameters) {
        // 在獨立線程處理音頻
        const input = inputs[0];
        this.port.postMessage({audioData: input});
        return true;
    }
}
```
**涉及文件**：
- `frontend/realtime-streaming/modules/audio-stream-manager.js`
- 新建 `frontend/realtime-streaming/worklets/audio-processor.js`

**預估工時**：8 小時  
**驗收標準**：
- 音頻處理延遲降低 30%
- CPU 使用率降低 20%
- 兼容 Chrome/Firefox/Safari

---

### T005: 統一前後端協議格式
**問題描述**：前端發送三種不同格式的消息，後端處理邏輯複雜  
**影響範圍**：增加維護成本，容易出錯  
**解決方案**：
```typescript
// 定義統一的消息格式
interface UnifiedMessage {
    version: string;
    type: 'action' | 'data' | 'control';
    payload: {
        action?: Action;
        data?: any;
        metadata?: Metadata;
    };
    timestamp: number;
}
```
**涉及文件**：
- `frontend/realtime-streaming/modules/protocol-adapters.js`
- `src/api/websocket/server.py`
- `src/api/streaming_protocol.py`

**預估工時**：12 小時  
**驗收標準**：
- 所有協議使用統一格式
- 向後兼容舊格式
- 協議文檔更新完整

---

### T006: 實現智能錯誤恢復機制
**問題描述**：錯誤處理分散，缺乏統一的恢復策略  
**影響範圍**：用戶體驗差，錯誤時需要手動重連  
**解決方案**：
```python
class ErrorRecoveryManager:
    strategies = {
        ConnectionError: exponential_backoff_retry,
        AudioProcessingError: skip_and_continue,
        ProviderError: fallback_provider,
        ResourceError: resource_cleanup_retry
    }
    
    async def handle_error(self, error, context):
        strategy = self.strategies.get(type(error))
        return await strategy(error, context)
```
**涉及文件**：
- 新建 `src/core/error_recovery.py`
- `src/api/websocket/server.py`
- `src/providers/manager.py`

**預估工時**：10 小時  
**驗收標準**：
- 90% 的錯誤可自動恢復
- 恢復時間 <5 秒
- 用戶無感知恢復

---

### T007: 優化 Provider 池化管理
**問題描述**：Provider 實例創建銷毀頻繁，資源利用率低  
**影響範圍**：每次請求延遲增加 100-200ms  
**解決方案**：
```python
class ProviderPool:
    def __init__(self, provider_class, min_size=2, max_size=10):
        self.pool = asyncio.Queue(maxsize=max_size)
        self.semaphore = asyncio.Semaphore(max_size)
        # 預創建最小實例數
        
    async def acquire(self) -> Provider:
        # 從池中獲取或創建新實例
        
    async def release(self, provider: Provider):
        # 歸還到池中或銷毀
```
**涉及文件**：
- `src/providers/provider_pool.py`
- `src/providers/manager.py`

**預估工時**：6 小時  
**驗收標準**：
- Provider 重用率 >80%
- 請求延遲降低 50%
- 資源使用穩定

---

## P2: 優化項目（1個月）

### T008: 實現分佈式 Session 管理
**問題描述**：Session 存儲在內存中，無法水平擴展  
**影響範圍**：單機瓶頸，無法實現高可用  
**解決方案**：
```python
# 使用 Redis 存儲 Session
class RedisSessionStore:
    async def get(self, session_id: str) -> Session:
        data = await self.redis.get(f"session:{session_id}")
        return Session.from_json(data) if data else None
    
    async def set(self, session_id: str, session: Session):
        await self.redis.setex(
            f"session:{session_id}",
            3600,  # TTL
            session.to_json()
        )
```
**涉及文件**：
- 新建 `src/store/distributed_store.py`
- `src/store/sessions/sessions_reducer.py`

**預估工時**：20 小時  
**驗收標準**：
- 支援多實例部署
- Session 同步延遲 <10ms
- 故障切換時間 <3秒

---

### T009: 音頻處理 Pipeline 並行化
**問題描述**：音頻處理步驟串行執行，無法充分利用多核  
**影響範圍**：處理延遲高，CPU 利用率低  
**解決方案**：
```python
class ParallelPipeline:
    async def process(self, audio_data):
        # 並行執行獨立的處理步驟
        tasks = [
            self.vad_operator.process(audio_data),
            self.denoise_operator.process(audio_data),
            self.format_checker.check(audio_data)
        ]
        results = await asyncio.gather(*tasks)
        return self.merge_results(results)
```
**涉及文件**：
- 新建 `src/operators/pipeline.py`
- `src/operators/base.py`

**預估工時**：16 小時  
**驗收標準**：
- 處理延遲降低 40%
- CPU 利用率提升 60%
- 結果一致性保證

---

### T010: 集成 Prometheus 監控
**問題描述**：缺乏性能監控，無法及時發現問題  
**影響範圍**：故障定位困難，優化缺乏數據支撐  
**解決方案**：
```python
from prometheus_client import Counter, Histogram, Gauge

# 定義監控指標
websocket_connections = Gauge('websocket_connections', 'Active connections')
audio_processing_time = Histogram('audio_processing_seconds', 'Processing time')
transcription_errors = Counter('transcription_errors_total', 'Total errors')

# 在關鍵路徑添加監控
@audio_processing_time.time()
async def process_audio(self, data):
    # 處理邏輯
```
**涉及文件**：
- 新建 `src/monitoring/metrics.py`
- 所有核心模塊添加監控點

**預估工時**：12 小時  
**驗收標準**：
- 覆蓋所有關鍵指標
- Grafana 儀表板配置完成
- 告警規則設置合理

---

### T011: 優化批次/串流模式切換
**問題描述**：批次和串流模式切換不流暢，代碼重複  
**影響範圍**：維護成本高，容易出現不一致  
**解決方案**：
```python
class UnifiedAudioProcessor:
    def __init__(self, mode: ProcessingMode):
        self.strategy = self._get_strategy(mode)
    
    async def process(self, audio_input):
        return await self.strategy.process(audio_input)
    
    def _get_strategy(self, mode):
        return {
            ProcessingMode.STREAM: StreamStrategy(),
            ProcessingMode.BATCH: BatchStrategy(),
            ProcessingMode.HYBRID: HybridStrategy()
        }[mode]
```
**涉及文件**：
- `src/audio/processor.py`
- `src/stream/stream_controller.py`

**預估工時**：8 小時  
**驗收標準**：
- 模式切換無縫
- 代碼重複率降低 50%
- 性能無損失

---

### T012: 前端離線處理能力
**問題描述**：網絡斷開時無法繼續錄音，用戶體驗差  
**影響範圍**：網絡不穩定環境可用性低  
**解決方案**：
```javascript
class OfflineAudioBuffer {
    constructor(maxSize = 100 * 1024 * 1024) {  // 100MB
        this.buffer = [];
        this.maxSize = maxSize;
    }
    
    async store(audioData) {
        // 存儲到 IndexedDB
        await this.db.audioChunks.add({
            timestamp: Date.now(),
            data: audioData
        });
    }
    
    async sync() {
        // 網絡恢復後同步
        const chunks = await this.db.audioChunks.toArray();
        for (const chunk of chunks) {
            await this.upload(chunk);
        }
    }
}
```
**涉及文件**：
- `frontend/realtime-streaming/modules/audio-stream-manager.js`
- 新建 `frontend/realtime-streaming/modules/offline-manager.js`

**預估工時**：14 小時  
**驗收標準**：
- 離線可錄音 5 分鐘
- 網絡恢復自動同步
- 數據不丟失

---

## P3: 長期規劃（3個月）

### T013: 實現智能 Provider 路由
**問題描述**：Provider 選擇靜態配置，無法根據實際情況優化  
**影響範圍**：成本高，性能不optimal  
**解決方案**：
```python
class IntelligentRouter:
    async def select_provider(self, context):
        # 基於多維度評分
        scores = {}
        for provider in self.providers:
            scores[provider] = self.calculate_score(
                provider,
                context.audio_length,
                context.language,
                context.quality_requirement,
                provider.current_load,
                provider.average_latency,
                provider.cost_per_minute
            )
        return max(scores, key=scores.get)
```
**涉及文件**：
- 新建 `src/providers/intelligent_router.py`
- `src/providers/manager.py`

**預估工時**：40 小時  
**驗收標準**：
- 成本降低 30%
- 平均延遲降低 25%
- 成功率提升到 99.5%

---

### T014: WebRTC 點對點音頻傳輸
**問題描述**：所有音頻都經過服務器，延遲高且佔用帶寬  
**影響範圍**：規模化受限，成本高  
**解決方案**：實現 WebRTC DataChannel 直接傳輸音頻到邊緣節點  
**涉及文件**：
- 新建 `src/api/webrtc/`
- `frontend/realtime-streaming/modules/webrtc-adapter.js`

**預估工時**：60 小時  
**驗收標準**：
- P2P 連接成功率 >95%
- 延遲降低 50%
- 帶寬節省 70%

---

### T015: AI 驅動的音頻增強
**問題描述**：音頻質量影響識別準確率  
**影響範圍**：嘈雜環境識別率低  
**解決方案**：集成深度學習音頻增強模型  
**涉及文件**：
- 新建 `src/operators/ai_enhancement/`
- `src/operators/base.py`

**預估工時**：80 小時  
**驗收標準**：
- 噪音環境識別率提升 30%
- 處理延遲 <50ms
- 支援實時處理

---

### T016: 多語言混合識別
**問題描述**：不支援多語言混合場景  
**影響範圍**：國際化場景無法使用  
**解決方案**：實現語言檢測和動態 Provider 切換  
**涉及文件**：
- 新建 `src/providers/language_detector.py`
- `src/providers/manager.py`

**預估工時**：50 小時  
**驗收標準**：
- 支援 5 種語言混合
- 語言切換延遲 <100ms
- 準確率 >95%

---

## 實施建議

### 執行順序
1. **第一週**：完成所有 P0 任務，確保系統穩定
2. **第二週**：開始 P1 任務，重點改善性能
3. **第三週**：繼續 P1，開始規劃 P2
4. **第四週**：完成 P1，啟動 P2 任務
5. **第二個月**：專注 P2 任務，建立監控體系
6. **第三個月**：評估 P3 任務優先級，選擇性實施

### 資源需求
- **開發人員**：2-3 名全棧工程師
- **測試環境**：獨立的性能測試環境
- **監控設施**：Prometheus + Grafana
- **負載測試**：K6 或 Locust

### 風險管理
1. **回滾計劃**：每個改動都要有回滾方案
2. **灰度發布**：重大改動採用灰度發布
3. **性能基準**：改動前後進行性能對比
4. **代碼審查**：所有 P0/P1 任務需要代碼審查

### 成功指標
- **穩定性**：錯誤率 <0.1%
- **性能**：端到端延遲 <300ms
- **可擴展性**：支援 1000+ 並發連接
- **可維護性**：代碼覆蓋率 >80%

---

## 技術債務清單

### 需要重構的模塊
1. `WebSocketServer` - 拆分職責
2. `SessionEffects` - 簡化異步邏輯
3. `AudioQueueManager` - 改進並發設計

### 需要補充的文檔
1. API 文檔
2. 部署指南
3. 性能調優指南
4. 故障排查手冊

### 需要添加的測試
1. 並發測試
2. 壓力測試
3. 異常場景測試
4. 端到端測試

---

## 結語

本 TodoList 基於架構分析結果制定，聚焦於實際的技術問題解決。建議按優先級順序執行，確保系統穩定性的同時持續改進性能和架構。每個任務都有明確的驗收標準，便於追蹤進度和驗證效果。