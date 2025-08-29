# Timer Service (計時器服務)

## 概述
計時器服務為每個 session 提供獨立的倒數計時功能，支援回調觸發、重置和停止等操作。採用單例模式和執行緒安全設計，確保多 session 並行處理的穩定性。

## 核心功能

### 倒數計時管理
- **Session 隔離** - 每個 session 擁有獨立的計時器
- **Callback 機制** - 倒數歸零時自動觸發回調函數
- **執行緒安全** - 使用 threading.Lock 確保並發安全
- **動態控制** - 支援重置、停止、清除等操作

### 狀態追蹤
- **即時剩餘時間** - 動態計算當前剩餘秒數
- **計時器資訊** - 提供完整的狀態資訊（TimerInfo）
- **多狀態支援** - RUNNING、PAUSED、COMPLETED 等狀態

## 使用方式

### 基本倒數計時
```python
from src.service.timer import timer

# 定義倒數完成的回調函數
def on_timer_complete(session_id: str):
    print(f"⏰ Session {session_id} 倒數結束！")
    # 執行相關動作，如：停止錄音、觸發轉譯等

# 開始 60 秒倒數（使用預設時間）
session_id = "user_123"
timer.start_countdown(session_id, on_timer_complete)

# 開始 30 秒倒數（指定時間）
timer.start_countdown(session_id, on_timer_complete, duration=30)
```

### 重置計時器
```python
# 重置為原本的時間
timer.reset_countdown(session_id)

# 重置為新的時間（45 秒）
timer.reset_countdown(session_id, duration=45)
```

### 停止與清除
```python
# 停止倒數（保留狀態，可查詢剩餘時間）
if timer.stop_countdown(session_id):
    print("成功停止倒數")
else:
    print("沒有計時器在執行")

# 清除計時器（完全移除）
timer.clear_countdown(session_id)
```

### 查詢狀態
```python
# 取得剩餘時間
remaining = timer.get_remaining_time(session_id)
if remaining is not None:
    print(f"剩餘 {remaining:.1f} 秒")

# 取得詳細資訊
info = timer.get_timer_info(session_id)
if info:
    print(f"計時器 ID: {info.timer_id}")
    print(f"狀態: {info.status}")
    print(f"剩餘: {info.remaining:.1f}/{info.duration:.1f} 秒")
    print(f"建立時間: {info.created_at}")

# 檢查是否正在倒數
if timer.is_counting_down(session_id):
    print("計時器執行中")
```

### 批次操作
```python
# 清除所有計時器
count = timer.clear_all()
print(f"清除了 {count} 個計時器")
```

## 實際應用範例

### 錄音超時控制
```python
from src.service.timer import timer
from src.service.recording import recording_service

def stop_recording_on_timeout(session_id: str):
    """錄音超時自動停止"""
    logger.info(f"錄音超時，自動停止 session: {session_id}")
    recording_service.stop_recording(session_id)
    # 可以發送通知給客戶端
    send_timeout_notification(session_id)

# 開始錄音時設定 5 分鐘超時
def start_recording_with_timeout(session_id: str):
    recording_service.start_recording(session_id)
    timer.start_countdown(
        session_id,
        callback=stop_recording_on_timeout,
        duration=300  # 5 分鐘
    )

# 使用者主動停止時
def user_stop_recording(session_id: str):
    recording_service.stop_recording(session_id)
    timer.stop_countdown(session_id)  # 同時停止計時器
```

### VAD 靜音超時
```python
def on_silence_timeout(session_id: str):
    """VAD 檢測到長時間靜音"""
    logger.info(f"檢測到長時間靜音: {session_id}")
    # 觸發語音結束事件
    trigger_speech_end_event(session_id)

# VAD 檢測到語音時重置計時器
def on_speech_detected(session_id: str):
    # 重置 10 秒靜音計時器
    timer.reset_countdown(session_id, duration=10)

# VAD 開始監聽時
def start_vad_monitoring(session_id: str):
    timer.start_countdown(
        session_id,
        callback=on_silence_timeout,
        duration=10  # 10 秒靜音超時
    )
```

### Session 過期管理
```python
def cleanup_expired_session(session_id: str):
    """清理過期的 session"""
    logger.info(f"Session 過期: {session_id}")
    # 清理資源
    cleanup_session_resources(session_id)
    # 從 store 中移除
    remove_session_from_store(session_id)

# 建立 session 時設定過期時間
def create_session_with_expiry(session_id: str):
    # 建立 session
    create_session(session_id)
    # 設定 1 小時過期
    timer.start_countdown(
        session_id,
        callback=cleanup_expired_session,
        duration=3600  # 1 小時
    )
```

## 配置說明

通過 `config.yaml` 配置預設倒數時間：
```yaml
services:
  timer:
    default_duration: 60  # 預設倒數時間（秒）
```

## 注意事項

1. **執行緒安全**: 所有操作都是執行緒安全的，可在多執行緒環境使用
2. **Session 唯一性**: 每個 session 只能有一個計時器，重複呼叫 start_countdown 會忽略
3. **Callback 執行**: Callback 在獨立執行緒中執行，避免在其中執行耗時操作
4. **錯誤處理**: Callback 執行錯誤不會影響計時器服務，但會記錄錯誤日誌
5. **資源管理**: 使用 daemon thread，主程式結束時會自動清理
6. **時間精度**: 使用 threading.Timer，精度約為毫秒級

## 錯誤處理

服務使用自定義異常類型：
- `TimerSessionError` - Session 相關錯誤（如 ID 無效）
- `TimerConfigError` - 配置錯誤（如倒數時間無效）
- `TimerNotFoundError` - 計時器不存在

```python
from src.interface.exceptions import TimerNotFoundError

try:
    timer.reset_countdown("non_existent_session")
except TimerNotFoundError as e:
    logger.error(f"計時器不存在: {e}")
```

## 效能考量

- **記憶體使用**: 每個活躍計時器約佔用 1KB 記憶體
- **執行緒限制**: 每個計時器使用一個執行緒，大量計時器時需注意系統限制
- **最大倒數時間**: 限制為 24 小時（86400 秒）
- **建議容量**: 同時運行 < 1000 個計時器

## 未來擴展

- 支援暫停/恢復功能
- 週期性計時器（循環觸發）
- 計時器群組管理
- 持久化存儲（重啟後恢復）
- 更精確的計時機制