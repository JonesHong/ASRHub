# PyStoreX 完整使用說明書

<div align="center">

```
╔═══════════════════════════════════════════════╗
║   PyStoreX - Python 響應式狀態管理架構              ║
╚═══════════════════════════════════════════════╝
```

*基於 NgRx/Redux 模式和 ReactiveX，為 Python 應用程式提供可預測的狀態管理*

</div>

## 📚 目錄

1. [簡介](#簡介)
2. [安裝](#安裝)
3. [快速開始](#快速開始)
4. [核心概念](#核心概念)
5. [基礎使用](#基礎使用)
6. [進階功能](#進階功能)
7. [中介軟體系統](#中介軟體系統)
8. [Effects 副作用管理](#effects-副作用管理)
9. [Selectors 狀態選擇器](#selectors-狀態選擇器)
10. [模組化架構](#模組化架構)
11. [生產環境最佳實踐](#生產環境最佳實踐)
12. [框架整合](#框架整合)
13. [API 參考](#api-參考)
14. [常見問題](#常見問題)
15. [遷移指南](#遷移指南)

---

## 🌟 簡介

PyStoreX 是一個功能完整的 Python 狀態管理庫，靈感來自 Angular 的 NgRx 和 React 的 Redux，並整合了 ReactiveX (RxPy) 的響應式程式設計能力。它提供了：

- 🎯 **可預測的狀態管理**：單向資料流，確保狀態變更可追蹤
- 🔄 **響應式資料流**：基於 ReactiveX，支援複雜的非同步操作
- 🧩 **模組化架構**：支援動態載入和卸載功能模組
- 🛡️  **型別安全**：使用 TypedDict 和泛型確保型別安全
- ⚡ **高效能**：使用 immutables.Map 實現高效的不可變狀態
- 🔌 **豐富的中介軟體**：內建多種中介軟體，支援自定義擴展

### 核心理念

1. **單一資料來源**：整個應用程式的狀態儲存在單一 Store 中
2. **狀態不可變**：狀態是唯讀的，只能通過 Actions 觸發變更
3. **純函數更新**：使用純函數 Reducers 來描述狀態如何變更
4. **副作用隔離**：副作用通過 Effects 統一管理

---

## 📦 安裝

### 基本安裝

```bash
pip install pystorex
```

### 開發環境安裝

```bash
# 包含開發依賴
pip install pystorex[dev]

# 從源碼安裝
git clone https://github.com/JonesHong/pystorex.git
cd pystorex
pip install -e .
```

### 系統需求

- Python 3.9+
- reactivex 4.0+
- immutables 0.19+
- typing_extensions 4.0+

---

## 🚀 快速開始

### 30 秒上手

```python
from pystorex import create_store, create_reducer, create_action, on

# 定義 Actions
increment = create_action("[Counter] Increment")
decrement = create_action("[Counter] Decrement")
reset = create_action("[Counter] Reset")

# 定義 Reducer
counter_reducer = create_reducer(
    0,  # 初始狀態
    on(increment, lambda state, action: state + 1),
    on(decrement, lambda state, action: state - 1),
    on(reset, lambda state, action: 0)
)

# 創建 Store
store = create_store()
store.register_root({"counter": counter_reducer})

# 使用 Store
print(store.state)  # {"counter": 0}
store.dispatch(increment())
print(store.state)  # {"counter": 1}

# 監聽狀態變化
store.select(lambda state: state["counter"]).subscribe(
    lambda value: print(f"計數器: {value[1]}")
)
```

### 一分鐘進階

```python
from typing import Optional
from typing_extensions import TypedDict
from pystorex import create_store, create_effect
from pystorex.middleware import LoggerMiddleware

# 定義狀態型別
class AppState(TypedDict):
    counter: int
    user: Optional[dict]
    loading: bool

# 應用中介軟體
store = create_store()
store.apply_middleware(LoggerMiddleware)

# 定義 Effects（處理副作用）
class CounterEffects:
    @create_effect
    def auto_save(self, action_stream):
        return action_stream.pipe(
            # 監聽特定 action
            # 執行副作用（如 API 請求）
            # 返回新的 action
        )

# 註冊 Effects
store.register_effects(CounterEffects)
```

---

## 🔧 核心概念

### State（狀態）

狀態是應用程式在特定時間點的資料快照。PyStoreX 使用不可變資料結構來儲存狀態。

```python
from typing_extensions import TypedDict
from immutables import Map

# 使用 TypedDict 定義狀態結構
class TodoState(TypedDict):
    todos: list
    filter: str
    loading: bool

# 初始狀態
initial_state = TodoState(
    todos=[],
    filter="all",
    loading=False
)
```

### Actions（動作）

Actions 是描述發生了什麼事的簡單物件。它們是改變狀態的唯一方式。

```python
from pystorex import create_action, action

# 簡單 Action（無 payload）
increment = create_action("[Counter] Increment")

# 帶 payload 的 Action
add_todo = create_action("[Todo] Add", lambda text: {"text": text})

# 使用裝飾器定義複雜 Action
@action("[Todo] Add with metadata")
def add_todo_with_metadata(text: str, priority: int = 1):
    import time
    return {
        "text": text,
        "priority": priority,
        "timestamp": time.time()
    }
```

### Reducers（歸約器）

Reducers 是純函數，接收當前狀態和 action，返回新狀態。

```python
from pystorex import create_reducer, on

# 定義 reducer
todo_reducer = create_reducer(
    initial_state,
    on(add_todo, lambda state, action: {
        **state,
        "todos": state["todos"] + [action.payload]
    }),
    on(clear_todos, lambda state, action: {
        **state,
        "todos": []
    })
)

# 使用函數處理器（更複雜的邏輯）
def todo_handler(state, action):
    if action.type == add_todo.type:
        new_todos = state["todos"].copy()
        new_todos.append(action.payload)
        return {**state, "todos": new_todos}
    return state

todo_reducer = create_reducer_from_function_handler(
    initial_state,
    todo_handler
)
```

### Store（存儲）

Store 是狀態的容器，提供了 dispatch actions 和訂閱狀態變化的方法。

```python
from pystorex import create_store

# 創建 Store
store = create_store()

# 註冊根 reducer
store.register_root({
    "todos": todo_reducer,
    "user": user_reducer
})

# Dispatch action
store.dispatch(add_todo("學習 PyStoreX"))

# 獲取當前狀態
current_state = store.state

# 訂閱狀態變化
subscription = store.state_stream.subscribe(
    lambda state: print(f"狀態更新: {state}")
)
```

---

## 🎯 基礎使用

### 創建完整的計數器應用

```python
from typing_extensions import TypedDict
from pystorex import (
    create_store, create_reducer, create_action,
    on, create_selector
)
from pystorex.middleware import LoggerMiddleware

# 1. 定義狀態
class CounterState(TypedDict):
    value: int
    step: int
    history: list

# 2. 定義 Actions
increment = create_action("[Counter] Increment")
decrement = create_action("[Counter] Decrement")
increment_by = create_action("[Counter] Increment By", lambda amount: amount)
set_step = create_action("[Counter] Set Step", lambda step: step)
reset = create_action("[Counter] Reset")

# 3. 定義 Reducer
initial_state = CounterState(value=0, step=1, history=[])

def counter_handler(state, action):
    import copy
    new_state = copy.deepcopy(state)

    if action.type == increment.type:
        new_state["value"] += new_state["step"]
        new_state["history"].append(new_state["value"])
    elif action.type == decrement.type:
        new_state["value"] -= new_state["step"]
        new_state["history"].append(new_state["value"])
    elif action.type == increment_by.type:
        new_state["value"] += action.payload
        new_state["history"].append(new_state["value"])
    elif action.type == set_step.type:
        new_state["step"] = action.payload
    elif action.type == reset.type:
        new_state["value"] = 0
        new_state["history"] = []

    return new_state

counter_reducer = create_reducer(
    initial_state,
    on(increment, counter_handler),
    on(decrement, counter_handler),
    on(increment_by, counter_handler),
    on(set_step, counter_handler),
    on(reset, counter_handler)
)

# 4. 創建 Store
store = create_store()
store.apply_middleware(LoggerMiddleware)
store.register_root({"counter": counter_reducer})

# 5. 創建 Selectors
get_counter = lambda state: state["counter"]
get_value = create_selector(
    get_counter,
    result_fn=lambda counter: counter["value"]
)
get_history = create_selector(
    get_counter,
    result_fn=lambda counter: counter["history"]
)

# 6. 訂閱狀態變化
store.select(get_value).subscribe(
    lambda value: print(f"當前值: {value[1]}")
)

# 7. 操作應用
store.dispatch(set_step(5))
store.dispatch(increment())  # value = 5
store.dispatch(increment())  # value = 10
store.dispatch(decrement())  # value = 5
store.dispatch(increment_by(15))  # value = 20
store.dispatch(reset())  # value = 0
```

### 處理非同步操作

```python
from reactivex import operators as ops
from pystorex import create_effect
import requests

# 定義非同步 Actions
fetch_user_request = create_action("[User] Fetch Request")
fetch_user_success = create_action("[User] Fetch Success", lambda user: user)
fetch_user_failure = create_action("[User] Fetch Failure", lambda error: error)

# 定義 Effects
class UserEffects:
    @create_effect
    def fetch_user(self, action_stream):
        return action_stream.pipe(
            ops.filter(lambda action: action.type == fetch_user_request.type),
            ops.switch_map(lambda action:
                self._fetch_user_api(action.payload)
            ),
            ops.map(lambda user: fetch_user_success(user)),
            ops.catch(lambda error: fetch_user_failure(str(error)))
        )

    def _fetch_user_api(self, user_id):
        # 模擬 API 請求
        response = requests.get(f"https://api.example.com/users/{user_id}")
        return response.json()

# 註冊 Effects
store.register_effects(UserEffects)
```

---

## 🔌 中介軟體系統

### 內建中介軟體

PyStoreX 提供多種內建中介軟體：

```python
from pystorex.middleware import (
    LoggerMiddleware,
    ThunkMiddleware,
    ErrorMiddleware,
    PersistMiddleware,
    DevToolsMiddleware,
    PerformanceMonitorMiddleware,
    DebounceMiddleware,
    BatchMiddleware,
    AnalyticsMiddleware
)

# 應用多個中介軟體
store = create_store()
store.apply_middleware(
    LoggerMiddleware,
    ErrorMiddleware,
    PerformanceMonitorMiddleware
)
```

### 日誌中介軟體

```python
# LoggerMiddleware - 記錄所有 actions 和狀態變化
store.apply_middleware(LoggerMiddleware)

# 自定義日誌格式
class CustomLoggerMiddleware(LoggerMiddleware):
    def __call__(self, store, next_middleware):
        def middleware(action):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Action: {action.type}")
            result = next_middleware(action)
            print(f"New State: {store.state}")
            return result
        return middleware
```

### Thunk 中介軟體

```python
# ThunkMiddleware - 支援 dispatch 函數而非只有 actions
store.apply_middleware(ThunkMiddleware)

# 使用 thunk
def async_increment(dispatch, get_state):
    print("當前狀態:", get_state())
    time.sleep(1)  # 模擬非同步操作
    dispatch(increment())
    print("更新後狀態:", get_state())

store.dispatch(async_increment)
```

### 持久化中介軟體

```python
# PersistMiddleware - 自動儲存和載入狀態
persist_config = {
    "storage": "localStorage",  # 或 "sessionStorage", "file"
    "key": "app_state",
    "whitelist": ["user", "settings"],  # 只持久化特定部分
    "blacklist": ["temp"],  # 排除特定部分
}

store.apply_middleware(
    PersistMiddleware(persist_config)
)
```

### 錯誤處理中介軟體

```python
# ErrorMiddleware - 捕獲和處理錯誤
class CustomErrorMiddleware(ErrorMiddleware):
    def handle_error(self, error, action, store):
        print(f"錯誤發生在 action {action.type}: {error}")
        # 可以 dispatch 錯誤 action
        store.dispatch(handle_error_action(error))

store.apply_middleware(CustomErrorMiddleware)
```

### 效能監控中介軟體

```python
# PerformanceMonitorMiddleware - 監控 action 處理時間
perf_middleware = PerformanceMonitorMiddleware(
    threshold=100,  # 毫秒
    callback=lambda action, duration:
        print(f"Action {action.type} 耗時 {duration}ms")
)

store.apply_middleware(perf_middleware)
```

### 自定義中介軟體

```python
from pystorex.middleware import BaseMiddleware

class AuthMiddleware(BaseMiddleware):
    """驗證特定 actions 的權限"""

    def __call__(self, store, next_middleware):
        def middleware(action):
            # 檢查需要認證的 actions
            if action.type.startswith("[Admin]"):
                if not self._is_authenticated(store.state):
                    print("未授權的操作")
                    return None

            return next_middleware(action)

        return middleware

    def _is_authenticated(self, state):
        return state.get("user", {}).get("authenticated", False)

# 使用自定義中介軟體
store.apply_middleware(AuthMiddleware)
```

---

## 🎭 Effects 副作用管理

### Effects 基礎

Effects 用於處理副作用，如 API 請求、定時器、WebSocket 連接等。

```python
from pystorex import create_effect
from reactivex import operators as ops

class TodoEffects:
    def __init__(self, api_service):
        self.api = api_service

    @create_effect
    def load_todos(self, action_stream):
        """載入待辦事項"""
        return action_stream.pipe(
            ops.filter(lambda a: a.type == load_todos_request.type),
            ops.switch_map(lambda _: self.api.get_todos()),
            ops.map(lambda todos: load_todos_success(todos)),
            ops.catch(lambda error: load_todos_failure(error))
        )

    @create_effect
    def save_todo(self, action_stream):
        """儲存待辦事項"""
        return action_stream.pipe(
            ops.filter(lambda a: a.type == save_todo_request.type),
            ops.debounce_time(0.3),  # 防抖
            ops.switch_map(lambda action:
                self.api.save_todo(action.payload)
            ),
            ops.map(lambda todo: save_todo_success(todo))
        )

    @create_effect(dispatch=False)  # 不 dispatch 新 action
    def log_errors(self, action_stream):
        """記錄錯誤（副作用但不產生新 action）"""
        return action_stream.pipe(
            ops.filter(lambda a: a.type.endswith("Failure")),
            ops.do_action(lambda action:
                print(f"錯誤: {action.payload}")
            )
        )
```

### 複雜的 Effects 模式

```python
class AdvancedEffects:
    @create_effect
    def polling(self, action_stream):
        """輪詢效果"""
        return action_stream.pipe(
            ops.filter(lambda a: a.type == start_polling.type),
            ops.switch_map(lambda _:
                reactivex.interval(5.0).pipe(  # 每 5 秒
                    ops.take_until(
                        action_stream.pipe(
                            ops.filter(lambda a: a.type == stop_polling.type)
                        )
                    )
                )
            ),
            ops.map(lambda _: fetch_data())
        )

    @create_effect
    def debounced_search(self, action_stream):
        """防抖搜尋"""
        return action_stream.pipe(
            ops.filter(lambda a: a.type == search.type),
            ops.debounce_time(0.5),  # 500ms 防抖
            ops.distinct_until_changed(lambda a: a.payload),  # 去重
            ops.switch_map(lambda action:
                self.api.search(action.payload)
            ),
            ops.map(lambda results: search_success(results))
        )

    @create_effect
    def retry_on_error(self, action_stream):
        """錯誤重試"""
        return action_stream.pipe(
            ops.filter(lambda a: a.type == fetch_important_data.type),
            ops.switch_map(lambda action:
                self.api.fetch_data().pipe(
                    ops.retry(3),  # 重試 3 次
                    ops.catch(lambda error:
                        reactivex.of(fetch_data_failure(error))
                    )
                )
            )
        )
```

### Effects 生命週期管理

```python
# 註冊 Effects
effects_instance = store.register_effects(TodoEffects, api_service)

# 動態註冊和註銷 Effects
store.effects_manager.register_effects(effects_instance)
store.effects_manager.unregister_effects(effects_instance)

# 清理所有 Effects
store.effects_manager.cleanup()
```

---

## 🔍 Selectors 狀態選擇器

### 基本 Selectors

```python
from pystorex import create_selector

# 簡單 selector
get_todos = lambda state: state["todos"]
get_filter = lambda state: state["filter"]

# 組合 selector
get_filtered_todos = create_selector(
    get_todos,
    get_filter,
    result_fn=lambda todos, filter_type: [
        todo for todo in todos
        if filter_type == "all" or todo["status"] == filter_type
    ]
)

# 使用 selector
filtered_todos = get_filtered_todos(store.state)
```

### Memoized Selectors

```python
# 創建記憶化的 selector（避免重複計算）
get_expensive_calculation = create_selector(
    get_large_dataset,
    result_fn=lambda data: perform_expensive_calculation(data),
    memoize=True,  # 啟用記憶化
    cache_size=10  # 快取大小
)

# 配置 TTL（Time To Live）
get_time_sensitive_data = create_selector(
    get_api_data,
    result_fn=lambda data: process_data(data),
    ttl=60  # 60 秒後過期
)
```

### 巢狀 Selectors

```python
# 建立 selector 樹
get_user_profile = create_selector(
    lambda state: state["user"]["profile"]
)

get_user_settings = create_selector(
    lambda state: state["user"]["settings"]
)

get_user_display_name = create_selector(
    get_user_profile,
    get_user_settings,
    result_fn=lambda profile, settings:
        settings.get("nickname") or profile.get("name") or "匿名用戶"
)

# 深度比較
get_deep_nested = create_selector(
    lambda state: state["deeply"]["nested"]["data"],
    deep_compare=True  # 啟用深度比較
)
```

### 動態 Selectors

```python
# 參數化 selector
def make_get_todo_by_id(todo_id):
    return create_selector(
        get_todos,
        result_fn=lambda todos: next(
            (todo for todo in todos if todo["id"] == todo_id),
            None
        )
    )

# 使用
get_todo_1 = make_get_todo_by_id(1)
todo = get_todo_1(store.state)
```

---

## ��️  模組化架構

### Feature Modules

```python
# todo_module.py
from pystorex import StoreModule

class TodoModule(StoreModule):
    def __init__(self):
        super().__init__("todos")

        # 定義 feature state
        self.initial_state = {
            "items": [],
            "loading": False,
            "error": None
        }

        # 定義 actions
        self.actions = {
            "add": create_action("[Todo] Add"),
            "remove": create_action("[Todo] Remove"),
            "toggle": create_action("[Todo] Toggle")
        }

        # 定義 reducer
        self.reducer = create_reducer(
            self.initial_state,
            on(self.actions["add"], self._add_todo),
            on(self.actions["remove"], self._remove_todo),
            on(self.actions["toggle"], self._toggle_todo)
        )

        # 定義 effects
        self.effects = TodoEffects()

    def _add_todo(self, state, action):
        # 實作加入邏輯
        pass

    def _remove_todo(self, state, action):
        # 實作移除邏輯
        pass

    def _toggle_todo(self, state, action):
        # 實作切換邏輯
        pass

# 使用 module
store = create_store()
todo_module = TodoModule()
store.register_feature(todo_module)
```

### 動態模組載入

```python
# 延遲載入模組
def lazy_load_admin_module():
    from admin_module import AdminModule
    return AdminModule()

# 條件載入
if user.is_admin:
    admin_module = lazy_load_admin_module()
    store.register_feature(admin_module)

# 動態註銷模組
store.unregister_feature("admin")
```

### 模組間通訊

```python
# shared_actions.py
user_logged_in = create_action("[Auth] User Logged In")
user_logged_out = create_action("[Auth] User Logged Out")

# todo_module.py
class TodoModule(StoreModule):
    def __init__(self):
        # 監聽共享 actions
        self.reducer = create_reducer(
            self.initial_state,
            on(user_logged_out, self._clear_todos)
        )

    def _clear_todos(self, state, action):
        return self.initial_state

# auth_module.py
class AuthModule(StoreModule):
    def login(self, credentials):
        # 登入邏輯
        if success:
            self.store.dispatch(user_logged_in(user_data))
```

---

## 🏭 生產環境最佳實踐

### 1. 狀態設計原則

```python
# ✅ 好的狀態設計
class AppState(TypedDict):
    # 正規化資料
    entities: dict  # {users: {}, posts: {}, comments: {}}
    # UI 狀態分離
    ui: dict  # {loading: {}, errors: {}, modals: {}}
    # 領域狀態
    domain: dict  # {currentUser: None, selectedPost: None}

# ❌ 避免的狀態設計
class BadState(TypedDict):
    # 巢狀過深
    user_posts_comments_replies: dict
    # 衍生資料
    filtered_sorted_posts: list  # 應該用 selector
    # 暫時資料
    form_input_value: str  # 應該在元件內管理
```

### 2. 效能優化

```python
# 使用 immutables.Map 提升效能
from immutables import Map
from pystorex.map_utils import batch_update

def optimized_reducer(state: Map, action) -> Map:
    if action.type == bulk_update.type:
        # 批次更新，避免多次複製
        return batch_update(state, {
            "field1": new_value1,
            "field2": new_value2,
            "field3": new_value3
        })
    return state

# 避免不必要的訂閱
# ✅ 好：精確訂閱
store.select(get_specific_field).subscribe(handler)

# ❌ 壞：訂閱整個狀態
store.state_stream.subscribe(handler)  # 每次變更都觸發
```

### 3. 錯誤處理策略

```python
from pystorex.errors import ErrorHandler, global_error_handler

# 全域錯誤處理
class AppErrorHandler(ErrorHandler):
    def handle_error(self, error, context):
        if isinstance(error, APIError):
            self.store.dispatch(show_error_toast(error.message))
        elif isinstance(error, ValidationError):
            self.store.dispatch(show_validation_errors(error.fields))
        else:
            # 記錄到監控服務
            sentry.capture_exception(error)
            self.store.dispatch(show_generic_error())

# 設定全域錯誤處理器
global_error_handler.set_handler(AppErrorHandler())

# Effect 層級錯誤處理
@create_effect
def safe_api_call(self, action_stream):
    return action_stream.pipe(
        ops.filter(lambda a: a.type == api_call.type),
        ops.switch_map(lambda action:
            self.api.call(action.payload).pipe(
                ops.catch(lambda error:
                    reactivex.of(api_error(error))
                )
            )
        )
    )
```

### 4. 測試策略

```python
import pytest
from pystorex import create_store, create_reducer, on

# 測試 Reducers
def test_counter_reducer():
    initial_state = 0
    reducer = create_reducer(
        initial_state,
        on(increment, lambda s, a: s + 1)
    )

    new_state = reducer(0, increment())
    assert new_state == 1

# 測試 Selectors
def test_filtered_todos_selector():
    state = {
        "todos": [
            {"id": 1, "done": True},
            {"id": 2, "done": False}
        ]
    }

    active_todos = get_active_todos(state)
    assert len(active_todos) == 1
    assert active_todos[0]["id"] == 2

# 測試 Effects
@pytest.mark.asyncio
async def test_load_data_effect():
    mock_api = Mock()
    mock_api.fetch_data.return_value = reactivex.of({"data": "test"})

    effects = DataEffects(mock_api)
    store = create_store()
    store.register_effects(effects)

    store.dispatch(load_data())
    await asyncio.sleep(0.1)  # 等待 effect 執行

    assert store.state["data"] == {"data": "test"}
```

### 5. 監控和除錯

```python
# 開發工具整合
if DEBUG:
    store.apply_middleware(
        DevToolsMiddleware,  # Redux DevTools 整合
        LoggerMiddleware,    # 詳細日誌
        PerformanceMonitorMiddleware  # 效能監控
    )

# 生產環境監控
class MonitoringMiddleware(BaseMiddleware):
    def __call__(self, store, next_middleware):
        def middleware(action):
            start_time = time.time()

            try:
                result = next_middleware(action)
                duration = time.time() - start_time

                # 發送指標
                metrics.record("action.duration", duration, {
                    "action_type": action.type
                })

                return result
            except Exception as e:
                # 發送錯誤
                metrics.record("action.error", 1, {
                    "action_type": action.type,
                    "error_type": type(e).__name__
                })
                raise

        return middleware
```

---

## 🔌 框架整合

### FastAPI 整合

```python
from fastapi import FastAPI, Depends
from pystorex import create_store

# 創建全域 store
app_store = create_store()
app_store.register_root(root_reducer)

# FastAPI 應用
app = FastAPI()

# 依賴注入
def get_store():
    return app_store

@app.post("/todos")
async def add_todo(text: str, store = Depends(get_store)):
    store.dispatch(add_todo_action(text))
    return {"status": "success", "state": store.state["todos"]}

@app.get("/todos")
async def get_todos(store = Depends(get_store)):
    return store.state["todos"]

# WebSocket 支援
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # 訂閱狀態變化
    def send_update(state):
        asyncio.create_task(
            websocket.send_json({"type": "state_update", "state": state})
        )

    subscription = app_store.state_stream.subscribe(send_update)

    try:
        while True:
            data = await websocket.receive_json()
            # 處理來自客戶端的 actions
            action = create_action(data["type"])(data.get("payload"))
            app_store.dispatch(action)
    finally:
        subscription.dispose()
```

### Django 整合

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'pystorex_django',
]

# store.py
from django.conf import settings
from pystorex import create_store

class DjangoStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = create_store()
            cls._instance.register_root(root_reducer)

            if settings.DEBUG:
                cls._instance.apply_middleware(LoggerMiddleware)

        return cls._instance

# views.py
from django.views import View
from .store import DjangoStore

class TodoView(View):
    def __init__(self):
        self.store = DjangoStore()

    def post(self, request):
        data = json.loads(request.body)
        self.store.dispatch(add_todo(data["text"]))
        return JsonResponse({"state": self.store.state["todos"]})
```

### Flask 整合

```python
from flask import Flask, request, jsonify
from pystorex import create_store

app = Flask(__name__)

# 初始化 store
store = create_store()
store.register_root(root_reducer)

@app.route('/dispatch', methods=['POST'])
def dispatch_action():
    data = request.json
    action_type = data.get('type')
    payload = data.get('payload')

    action = create_action(action_type)(payload)
    store.dispatch(action)

    return jsonify({"state": store.state})

@app.route('/state')
def get_state():
    return jsonify(store.state)

# Socket.IO 整合
from flask_socketio import SocketIO, emit

socketio = SocketIO(app)

# 訂閱狀態變化並廣播
store.state_stream.subscribe(
    lambda state: socketio.emit('state_update', state)
)
```

---

## 📖 API 參考

### 核心函數

#### `create_store(**kwargs)`
創建一個新的 Store 實例。

**參數：**
- `initial_state` (dict): 初始狀態
- `middleware` (list): 中介軟體列表
- `dev_tools` (bool): 是否啟用開發工具

**返回：** Store 實例

```python
store = create_store(
    initial_state={"counter": 0},
    middleware=[LoggerMiddleware],
    dev_tools=True
)
```

#### `create_action(type, payload_creator=None)`
創建 Action 創建器。

**參數：**
- `type` (str): Action 類型
- `payload_creator` (callable): Payload 創建函數

**返回：** Action 創建器函數

```python
increment = create_action("[Counter] Increment")
add_todo = create_action("[Todo] Add", lambda text: {"text": text})
```

#### `create_reducer(initial_state, *handlers)`
創建 Reducer。

**參數：**
- `initial_state`: 初始狀態
- `*handlers`: Action 處理器

**返回：** Reducer 函數

```python
reducer = create_reducer(
    0,
    on(increment, lambda state, action: state + 1),
    on(decrement, lambda state, action: state - 1)
)
```

#### `create_effect(dispatch=True)`
Effect 裝飾器。

**參數：**
- `dispatch` (bool): 是否 dispatch 返回的 actions

**返回：** 裝飾後的 effect 方法

```python
class Effects:
    @create_effect
    def load_data(self, action_stream):
        return action_stream.pipe(
            # RxPy 操作符
        )
```

#### `create_selector(*input_selectors, result_fn, **options)`
創建記憶化的 selector。

**參數：**
- `*input_selectors`: 輸入 selectors
- `result_fn`: 結果計算函數
- `**options`: 配置選項（memoize, ttl, deep_compare 等）

**返回：** Selector 函數

```python
get_filtered_todos = create_selector(
    get_todos,
    get_filter,
    result_fn=lambda todos, filter: filter_todos(todos, filter),
    memoize=True
)
```

### Store 類

#### 屬性
- `state`: 當前狀態
- `state_stream`: 狀態 Observable
- `action_stream`: Action Observable

#### 方法

##### `dispatch(action)`
分發 Action。

```python
store.dispatch(increment())
```

##### `select(selector)`
選擇狀態切片。

```python
counter_stream = store.select(lambda state: state["counter"])
```

##### `register_root(reducers)`
註冊根 reducers。

```python
store.register_root({
    "counter": counter_reducer,
    "todos": todo_reducer
})
```

##### `register_feature(module)`
註冊功能模組。

```python
store.register_feature(TodoModule())
```

##### `register_effects(effects_class, *args)`
註冊 Effects。

```python
store.register_effects(TodoEffects, api_service)
```

##### `apply_middleware(*middleware_classes)`
應用中介軟體。

```python
store.apply_middleware(
    LoggerMiddleware,
    ThunkMiddleware,
    ErrorMiddleware
)
```

### 中介軟體類

#### BaseMiddleware
所有中介軟體的基類。

```python
class CustomMiddleware(BaseMiddleware):
    def __call__(self, store, next_middleware):
        def middleware(action):
            # 前處理
            result = next_middleware(action)
            # 後處理
            return result
        return middleware
```

### 工具函數

#### `ofType(*types)`
RxPy 操作符，過濾特定類型的 actions。

```python
from pystorex import ofType

action_stream.pipe(
    ofType(increment.type, decrement.type),
    # 處理這些 actions
)
```

#### `batch_update(state, updates)`
批次更新不可變狀態。

```python
from pystorex.map_utils import batch_update

new_state = batch_update(state, {
    "field1": value1,
    "field2": value2
})
```

#### `to_immutable(obj)`
轉換為不可變物件。

```python
from pystorex.immutable_utils import to_immutable

immutable_state = to_immutable({"counter": 0})
```

---

## ❓ 常見問題

### Q1: PyStoreX 與 Redux 有什麼區別？

**A:** PyStoreX 採用了 Redux 的核心概念，但針對 Python 生態系統進行了優化：
- 使用 RxPy 而非 Redux-Observable
- 支援 Python 的型別提示
- 整合了 Python 特有的功能（如裝飾器）
- 提供了更 Pythonic 的 API

### Q2: 如何處理大型應用的狀態？

**A:** 使用模組化架構：
```python
# 按功能分割狀態
state = {
    "auth": AuthState,
    "todos": TodoState,
    "ui": UIState
}

# 使用功能模組
store.register_feature(AuthModule())
store.register_feature(TodoModule())

# 延遲載入
if needed:
    store.register_feature(AdminModule())
```

### Q3: 如何除錯狀態管理？

**A:** 使用內建的除錯工具：
```python
# 開發環境
if DEBUG:
    store.apply_middleware(
        LoggerMiddleware,      # 日誌
        DevToolsMiddleware,    # Redux DevTools
        PerformanceMonitorMiddleware  # 效能
    )

# 時間旅行除錯
store.enable_time_travel()
store.go_back()  # 回到上一個狀態
store.go_forward()  # 前進到下一個狀態
```

### Q4: 如何測試 PyStoreX 應用？

**A:** 分層測試策略：
```python
# 單元測試 Reducers（純函數）
def test_reducer():
    assert reducer(0, increment()) == 1

# 測試 Selectors
def test_selector():
    state = {"todos": [{"id": 1}]}
    assert get_todo_count(state) == 1

# 整合測試 Effects
async def test_effect():
    store = create_store()
    store.dispatch(load_data())
    await wait_for_effect()
    assert store.state["data"] is not None
```

### Q5: 效能優化建議？

**A:**
1. 使用 `immutables.Map` 而非字典
2. 實施 selector 記憶化
3. 避免深層巢狀狀態
4. 使用 `batch_update` 批次更新
5. 實施虛擬滾動處理大列表

### Q6: 如何處理表單狀態？

**A:** 建議本地狀態與全域狀態結合：
```python
# 本地狀態：臨時表單輸入
class FormComponent:
    def __init__(self):
        self.local_state = {"input": ""}

    def on_submit(self):
        # 提交時才更新全域狀態
        store.dispatch(submit_form(self.local_state))

# 全域狀態：已提交的資料
form_reducer = create_reducer(
    {"submitted_data": []},
    on(submit_form, lambda state, action: {
        **state,
        "submitted_data": state["submitted_data"] + [action.payload]
    })
)
```

---

### 最佳實踐建議

1. **逐步遷移**：先遷移新功能，再處理舊代碼
2. **保持相容**：使用適配器模式橋接新舊系統
3. **統一管理**：集中管理所有狀態定義
4. **完整測試**：確保遷移後功能正常

---

## 🎯 總結

PyStoreX 提供了一個強大且靈活的狀態管理解決方案，適用於各種規模的 Python 應用。

### 核心優勢

- ✅ **可預測性**：單向資料流確保狀態變更可追蹤
- ✅ **模組化**：支援功能模組的動態載入和卸載
- ✅ **響應式**：基於 RxPy 的強大非同步處理能力
- ✅ **型別安全**：完整的型別提示支援
- ✅ **可測試性**：純函數和依賴注入使測試變得簡單
- ✅ **生產就緒**：內建監控、錯誤處理和效能優化

### 適用場景

- 複雜的應用
- 微服務的狀態管理
- 即時資料處理系統
- 遊戲狀態管理
- IoT 設備狀態同步
- 任何需要可預測狀態管理的應用