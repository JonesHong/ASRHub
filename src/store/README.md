# ASRHub Store 架構說明

## 📁 目錄結構

採用 **Feature-based (Domain-driven)** 組織方式，每個功能域包含完整的 Redux 元素。

```
src/store/
├── sessions/           # 會話管理域
│   ├── __init__.py
│   ├── sessions.state.py     # State 類型定義
│   ├── sessions.actions.py   # Actions 定義
│   ├── sessions.reducer.py   # Reducer 實現
│   ├── sessions.effects.py   # Effects（副作用）
│   ├── sessions.selectors.py # Selectors（查詢）
│   └── sessions.adapter.py   # 與舊系統的適配器
│
├── pipeline/          # 音訊處理管線域
│   ├── __init__.py
│   ├── pipeline.state.py
│   ├── pipeline.actions.py
│   ├── pipeline.reducer.py
│   ├── pipeline.effects.py
│   └── pipeline.selectors.py
│
├── providers/         # ASR 提供者管理域
│   ├── __init__.py
│   ├── providers.state.py
│   ├── providers.actions.py
│   ├── providers.reducer.py
│   ├── providers.effects.py
│   └── providers.selectors.py
│
├── audio/            # 音訊處理域
│   ├── __init__.py
│   ├── audio.state.py
│   ├── audio.actions.py
│   ├── audio.reducer.py
│   ├── audio.effects.py
│   └── audio.selectors.py
│
├── stats/            # 統計資訊域
│   ├── __init__.py
│   ├── stats.state.py
│   ├── stats.actions.py
│   ├── stats.reducer.py
│   └── stats.selectors.py
│
├── shared/           # 共享元素
│   ├── __init__.py
│   ├── types.py      # 共用類型定義
│   ├── utils.py      # 工具函數
│   └── middleware.py # 中介軟體
│
├── __init__.py
├── store.py          # Store 配置和初始化
└── root.reducer.py  # 根 Reducer 組合
```

## 🎯 設計原則

### 1. 單一職責原則
每個功能域負責管理自己的狀態切片：
- **sessions**: 會話生命週期、FSM 狀態
- **pipeline**: 音訊處理管線配置
- **providers**: ASR 提供者狀態
- **audio**: 音訊緩衝、串流管理
- **stats**: 統計和監控數據

### 2. 命名規範

#### Actions
```python
# 格式：[Domain] Action Description
create_session = create_action("[Session] Create")
wake_triggered = create_action("[Session] Wake Triggered")
audio_chunk_received = create_action("[Audio] Chunk Received")
```

#### State
```python
# 使用 TypedDict 定義狀態結構
class SessionState(TypedDict):
    id: str
    fsm_state: FSMStateEnum
    # ...
```

#### Selectors
```python
# get_ 前綴表示查詢
get_session = create_selector(...)
get_active_sessions = create_selector(...)
```

### 3. 跨域通訊

當需要跨域操作時，使用 Effects：

```python
# 在 audio.effects.py 中
@create_effect
def process_audio_chunk(self, action_stream):
    return action_stream.pipe(
        # 監聽 audio action
        ops.filter(lambda a: a.type == audio_chunk_received.type),
        # 可能觸發 session action
        ops.map(lambda a: wake_triggered(...))
    )
```

### 4. 模組導出

每個功能域的 `__init__.py` 應導出公共 API：

```python
# sessions/__init__.py
from .sessions.actions import *
from .sessions.selectors import *
from .sessions.reducer import sessions_reducer
from .sessions.effects import SessionEffects
from .sessions.state import SessionState
```

## 🚀 使用範例

```python
# 在 store.py 中組合所有 reducers
from src.store.sessions import sessions_reducer
from src.store.pipeline import pipeline_reducer
from src.store.stats import stats_reducer

root_reducer = {
    "sessions": sessions_reducer,
    "pipeline": pipeline_reducer,
    "stats": stats_reducer,
}

# 註冊 Effects
store.register_effects(SessionEffects)
store.register_effects(PipelineEffects)
store.register_effects(AudioEffects)
```

## 📝 開發指南

### 新增功能域

1. 創建新資料夾：`src/store/new_feature/`
2. 定義 State 結構：`new_feature.state.py`
3. 創建 Actions：`new_feature.actions.py`
4. 實現 Reducer：`new_feature.reducer.py`
5. 添加 Effects（如需要）：`new_feature.effects.py`
6. 編寫 Selectors：`new_feature.selectors.py`
7. 在 `store.py` 中註冊

### 測試策略

```
src/store/
└── __tests__/
    ├── sessions/
    │   ├── test_sessions_reducer.py
    │   ├── test_sessions_effects.py
    │   └── test_sessions_selectors.py
    └── integration/
        └── test_store_integration.py
```

## 🔄 遷移計劃

從 POC 到生產環境的遷移步驟：

1. **Phase 1**: 重構 POC 代碼到新結構
2. **Phase 2**: 整合現有 FSM 和 SessionManager
3. **Phase 3**: 連接 Pipeline 和 Operators
4. **Phase 4**: 整合 API 層（WebSocket, SSE）
5. **Phase 5**: 性能優化和監控

## 📚 參考資源

- [Redux Style Guide](https://redux.js.org/style-guide/)
- [NgRx Best Practices](https://ngrx.io/guide/store)
- [PyStoreX Documentation](https://github.com/JonesHong/pystorex)