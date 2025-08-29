# AudioQueueManager (音訊佇列管理器)

## 概述
AudioQueueManager 是 ASRHub 核心模組之一，提供執行緒安全的音訊佇列管理功能。每個 session 都有獨立的佇列來存放音訊片段，支援多個 session 同時處理音訊資料。採用單例模式確保全系統只有一個管理器實例。

## 核心功能

### 佇列管理
- **Session 隔離** - 每個 session 擁有獨立的音訊佇列
- **自動建立** - 首次推入資料時自動建立佇列
- **執行緒安全** - 所有操作都是執行緒安全的
- **大小限制** - 可配置最大佇列大小，自動移除最舊資料

### 操作模式
- **推拉模式** - 標準的 push/pull 操作
- **阻塞模式** - pop_blocking 支援等待資料
- **批量操作** - 支援批量拉取多個片段
- **統計查詢** - 即時查詢佇列狀態

## 使用方式

### 基本操作
```python
from src.core.audio_queue_manager import audio_queue
from src.interface.audio import AudioChunk

# 推入音訊片段
session_id = "user_123"
chunk = AudioChunk(data=audio_bytes, sample_rate=16000)
success = audio_queue.push(session_id, chunk)

# 拉取音訊片段
chunks = audio_queue.pull(session_id, count=5)  # 取 5 個片段

# 阻塞式取出（等待資料）
chunk = audio_queue.pop_blocking(session_id, timeout=2.0)  # 最多等待 2 秒

# 查詢佇列大小
size = audio_queue.size(session_id)
print(f"佇列中有 {size} 個片段")

# 清空佇列
audio_queue.clear(session_id)

# 移除整個 session 佇列
audio_queue.remove(session_id)
```

### 進階使用
```python
# 檢查佇列是否存在
if audio_queue.exists(session_id):
    print(f"Session {session_id} 佇列存在")

# 取得統計資訊
stats = audio_queue.get_stats()
print(f"總佇列數: {stats['total_queues']}")
print(f"總片段數: {stats['total_chunks']}")
for sid, size in stats['queue_sizes'].items():
    print(f"  {sid}: {size} chunks")
```

## 實際應用範例

### 音訊串流處理
```python
def process_audio_stream(session_id: str):
    """處理即時音訊流"""
    while streaming:
        # 從網路接收音訊
        audio_data = receive_audio_from_network()
        
        # 包裝成 AudioChunk
        chunk = AudioChunk(
            data=audio_data,
            sample_rate=16000,
            timestamp=time.time()
        )
        
        # 推入佇列
        audio_queue.push(session_id, chunk)
        
        # 處理緩衝的資料
        if audio_queue.size(session_id) >= 10:
            chunks = audio_queue.pull(session_id, count=10)
            process_audio_batch(chunks)
```

### 多 Session 管理
```python
class SessionManager:
    def __init__(self):
        self.active_sessions = set()
    
    def create_session(self, session_id: str):
        """建立新 session"""
        self.active_sessions.add(session_id)
        # 佇列會在首次 push 時自動建立
        logger.info(f"Session {session_id} created")
    
    def cleanup_session(self, session_id: str):
        """清理 session"""
        if session_id in self.active_sessions:
            # 移除佇列
            audio_queue.remove(session_id)
            self.active_sessions.discard(session_id)
            logger.info(f"Session {session_id} cleaned up")
    
    def cleanup_all(self):
        """清理所有 session"""
        for session_id in list(self.active_sessions):
            self.cleanup_session(session_id)
```

### 阻塞式消費者
```python
def audio_consumer(session_id: str):
    """阻塞式音訊消費者"""
    while running:
        # 阻塞等待音訊，最多等 5 秒
        chunk = audio_queue.pop_blocking(session_id, timeout=5.0)
        
        if chunk is None:
            # 超時，可能沒有新資料
            logger.debug("No audio data available")
            continue
        
        # 處理音訊
        process_audio(chunk)
```

## 配置說明

通過 `config.yaml` 配置：
```yaml
services:
  audio_queue:
    max_queue_size: 1000           # 每個佇列最大片段數
    ttl_seconds: 3600              # 佇列存活時間（秒）
    queue_cleanup_interval: 300    # 清理間隔（秒）
    blocking_timeout: 5.0          # 阻塞操作預設超時（秒）
    blocking_sleep_interval: 0.01  # 阻塞等待間隔（秒）
```

## 執行緒安全設計

### 雙層鎖機制
```python
# Registry lock - 保護佇列註冊表
self._registry_lock = threading.Lock()

# Per-queue locks - 保護個別佇列操作
self._locks[session_id] = threading.Lock()
```

### 操作順序
1. **建立佇列**: 取得 registry lock → 建立佇列和鎖
2. **推拉操作**: 取得 queue lock → 操作佇列
3. **移除佇列**: 取得 registry lock → 取得 queue lock → 刪除

## 效能考量

- **記憶體使用**: 每個片段約 1KB，1000 片段約 1MB
- **執行緒開銷**: 每個佇列一個鎖，避免全域鎖競爭
- **自動清理**: 配置 TTL 和清理間隔避免記憶體洩漏
- **阻塞操作**: 使用 sleep 避免 busy waiting

## 錯誤處理

所有方法都包含完整的異常處理：
- **push**: 返回 bool 表示成功與否
- **pull**: 失敗時返回空列表
- **clear**: 返回 bool 表示成功與否
- **pop_blocking**: 超時或錯誤返回 None

## 注意事項

1. **自動建立**: 佇列在首次 push 時自動建立，無需預先建立
2. **佇列大小**: 配置 max_queue_size 防止記憶體無限增長
3. **阻塞超時**: pop_blocking 應設置合理的超時避免永久等待
4. **Session 清理**: 記得在 session 結束時呼叫 remove() 釋放資源
5. **統計查詢**: get_stats() 會鎖定註冊表，頻繁呼叫可能影響效能

## 設計理念

- **KISS 原則**: 簡單直接的 API 設計
- **無狀態操作**: 每個操作獨立，不依賴狀態
- **防禦性編程**: 完整的參數驗證和錯誤處理
- **效能優先**: 最小化鎖競爭，支援並行操作