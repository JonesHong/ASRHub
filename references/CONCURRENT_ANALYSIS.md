# ASR Hub 並發處理方案分析

## 問題背景
- 當前 WhisperProvider 使用全局鎖 `self._processing_lock`
- 所有請求共享單一 Provider 實例
- 導致小檔案必須等待大檔案處理完成

## 方案一：Provider 池化

### 實作概念
```python
class ProviderPool:
    def __init__(self, provider_class, pool_size=3):
        self.pool = [provider_class() for _ in range(pool_size)]
        self.available = asyncio.Queue()
        for provider in self.pool:
            self.available.put_nowait(provider)
    
    async def acquire(self):
        return await self.available.get()
    
    async def release(self, provider):
        await self.available.put(provider)
```

### 優點
1. **並發能力**：可同時處理 N 個請求（N = 池大小）
2. **資源控制**：限制最大並發數，避免資源耗盡
3. **向後兼容**：不需修改現有 Provider 程式碼
4. **彈性配置**：池大小可根據系統資源調整
5. **故障隔離**：單一實例問題不影響其他實例

### 缺點
1. **記憶體開銷**：每個實例都載入完整模型（Whisper base ~150MB）
2. **初始化時間**：啟動時需載入多個模型實例
3. **複雜度增加**：需要池管理邏輯（獲取、釋放、健康檢查）
4. **配置負擔**：需要為每個 Provider 設定合適的池大小

### 對擴充的影響
- **低影響**：新 Provider 只需在配置中指定池大小
- **統一介面**：所有 Provider 都可使用相同的池化機制
- **靈活性**：不同 Provider 可有不同的池配置

## 方案二：移除全局鎖

### 實作概念
```python
class WhisperProvider(ProviderBase):
    async def transcribe(self, audio_data: bytes, **kwargs):
        # 移除 async with self._processing_lock:
        # 直接處理，依賴模型本身的線程安全性
        result = await self._transcribe_internal(audio_data, **kwargs)
        return result
```

### 優點
1. **最簡單**：只需刪除幾行程式碼
2. **最高並發**：理論上無並發限制
3. **無額外開銷**：不增加記憶體或管理複雜度
4. **即時生效**：修改後立即獲得並發能力

### 缺點
1. **安全風險**：
   - Whisper 模型可能不是線程安全的
   - 可能導致預測結果錯亂
   - 可能造成記憶體損壞或崩潰
2. **資源失控**：
   - 無法限制並發數
   - 可能導致 OOM（記憶體不足）
   - GPU 記憶體可能爆滿
3. **不可預測**：行為依賴底層實作，可能隨版本變化

### 對擴充的影響
- **高風險**：每個新 Provider 都需要仔細評估線程安全性
- **不一致**：有些 Provider 可能安全，有些不安全
- **維護困難**：需要深入了解每個模型的內部實作

## 方案三：任務隊列

### 實作概念
```python
class PriorityTaskQueue:
    def __init__(self):
        self.queue = asyncio.PriorityQueue()
        self.worker_task = None
    
    async def submit(self, priority, task):
        await self.queue.put((priority, task))
    
    async def worker(self):
        while True:
            priority, task = await self.queue.get()
            await task.execute()
```

### 優點
1. **智慧排程**：
   - 小檔案可設高優先級
   - 支援複雜的排程策略
   - 可實作公平排隊
2. **資源優化**：仍然單一模型實例，記憶體效率高
3. **可觀測性**：容易監控隊列狀態、等待時間
4. **擴展性強**：可加入更多排程邏輯（如超時、取消）

### 缺點
1. **仍是序列處理**：本質上還是一個接一個處理
2. **延遲問題**：高優先級任務仍需等當前任務完成
3. **複雜度高**：
   - 需要設計優先級策略
   - 需要處理任務取消、超時
   - 需要防止飢餓問題
4. **不真正並發**：無法充分利用多核 CPU

### 對擴充的影響
- **中等影響**：需要為每個 Provider 定義優先級策略
- **統一框架**：可建立通用的任務隊列框架
- **複雜配置**：需要考慮不同 Provider 的特性

## 方案四：多進程並行

### 實作概念
```python
import multiprocessing as mp

class MultiProcessProvider:
    def __init__(self, num_processes=3):
        self.pool = mp.Pool(processes=num_processes)
        self.executor = ProcessPoolExecutor(max_workers=num_processes)
    
    async def transcribe(self, audio_data: bytes, **kwargs):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor, 
            self._transcribe_in_process, 
            audio_data, 
            kwargs
        )
        return result
```

### 優點
1. **真正並行**：充分利用多核 CPU
2. **完全隔離**：
   - 進程間完全獨立
   - 一個崩潰不影響其他
   - 無需擔心線程安全
3. **資源獨立**：每個進程有獨立的記憶體空間
4. **穩定可靠**：經過驗證的並行模式

### 缺點
1. **記憶體開銷巨大**：
   - 每個進程載入完整模型
   - Python 進程本身的開銷
   - 無法共享記憶體
2. **通信開銷**：
   - 進程間傳遞音訊資料需要序列化
   - 大檔案傳輸成本高
3. **啟動緩慢**：
   - 進程創建成本高
   - 模型需要在每個進程中載入
4. **複雜度最高**：
   - 需要處理進程生命週期
   - 錯誤處理更複雜
   - 調試困難

### 對擴充的影響
- **高影響**：
  - 不是所有 Provider 都適合多進程
  - 需要確保模型可以序列化
  - 可能需要修改 Provider 介面
- **效能考量**：不同 Provider 的序列化成本不同
- **平台限制**：Windows 上的多進程行為不同

## 綜合評估與建議

### 評分表（1-5分，5分最佳）

| 方案 | 實作難度 | 效能提升 | 資源效率 | 擴充性 | 風險程度 | 總分 |
|------|---------|---------|---------|--------|---------|------|
| Provider 池化 | 3 | 4 | 3 | 5 | 5 | 20 |
| 移除全局鎖 | 5 | 5 | 5 | 2 | 1 | 18 |
| 任務隊列 | 2 | 2 | 5 | 4 | 4 | 17 |
| 多進程並行 | 1 | 5 | 1 | 3 | 3 | 13 |

### 建議方案：Provider 池化

**理由：**
1. **平衡性最佳**：在效能、安全性、擴充性之間取得良好平衡
2. **風險可控**：不會破壞現有架構，風險最低
3. **擴充友好**：新 Provider 可以輕鬆整合
4. **配置彈性**：可根據實際需求調整池大小

### 實施建議

1. **第一階段**：實作基礎 Provider 池化
   - 預設池大小 = CPU 核心數 / 2
   - 支援配置檔設定池大小

2. **第二階段**：加入智慧特性
   - 根據檔案大小動態分配
   - 池大小自動伸縮
   - 健康檢查和故障恢復

3. **第三階段**：優化和監控
   - 加入池使用率監控
   - 實作預熱機制
   - 支援不同 Provider 的差異化配置

### 配置範例
```yaml
providers:
  whisper:
    pool:
      enabled: true
      min_size: 2
      max_size: 5
      timeout: 30
  funasr:
    pool:
      enabled: true
      min_size: 1
      max_size: 3
      timeout: 60
```

## 結論

Provider 池化是最適合 ASR Hub 的方案，因為它：
- 提供良好的並發能力
- 保持架構的清晰和可維護性
- 對未來擴充新 Provider 影響最小
- 風險可控且易於調試

其他方案在特定場景下可能更優，但考慮到 ASR Hub 的長期發展和穩定性，Provider 池化是最佳選擇。