# Pretty-Loguru 完整使用說明書

<div align="center">

```
╔═══════════════════════════════════════════════╗
║   Pretty-Loguru - 美化你的 Python 日誌輸出    ║
╚═══════════════════════════════════════════════╝
```

*一個基於 Loguru 和 Rich 的增強型日誌庫，讓你的日誌既美觀又實用*

[![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

## 📚 目錄

1. [簡介](#簡介)
2. [安裝](#安裝)
3. [快速開始](#快速開始)
4. [基礎使用](#基礎使用)
5. [進階功能](#進階功能)
6. [視覺化特性](#視覺化特性)
7. [配置管理](#配置管理)
8. [框架整合](#框架整合)
9. [生產環境最佳實踐](#生產環境最佳實踐)
10. [API 參考](#api-參考)
11. [常見問題](#常見問題)
12. [遷移指南](#遷移指南)

---

## 🌟 簡介

Pretty-Loguru 是一個功能豐富的 Python 日誌庫，建立在著名的 Loguru 之上，並整合了 Rich 的視覺化能力。它提供了：

- 🎨 **視覺化日誌**：彩色區塊、ASCII 藝術標題、表格和樹狀結構
- 🎯 **目標導向輸出**：分離控制台和檔案輸出，各自優化
- 🔧 **靈活配置**：預設模板、動態更新、多 logger 管理
- 🚀 **框架整合**：與 FastAPI、Uvicorn 等無縫整合
- 📊 **生產就緒**：日誌輪替、壓縮、自動清理、性能監控

### 核心理念

1. **簡單優先**：一行代碼即可開始使用
2. **視覺清晰**：讓重要資訊一目了然
3. **性能考量**：生產環境下的高效能
4. **靈活擴展**：滿足各種客製化需求

---

## 📦 安裝

### 基本安裝

```bash
pip install pretty-loguru
```

---

## 🚀 快速開始

### 30 秒上手

```python
from pretty_loguru import create_logger

# 創建 logger
logger = create_logger("my_app")

# 基本日誌
logger.info("應用程式啟動成功")
logger.success("資料庫連接正常")
logger.warning("記憶體使用率偏高")
logger.error("無法連接到外部 API")

# 視覺化日誌
logger.block("系統狀態", "一切運行正常", border_style="green")
logger.ascii_header("WELCOME", font="slant")
```

### 一分鐘進階

```python
from pretty_loguru import LoggerConfig, ConfigTemplates

# 使用配置模板
config = ConfigTemplates.production()
logger = config.apply_to("app")

# 多 logger 管理
config = LoggerConfig(level="INFO", log_path="logs")
auth_logger, db_logger, api_logger = config.apply_to("auth", "database", "api")

# 動態更新所有 logger
config.update(level="DEBUG")  # 所有 logger 自動切換到 DEBUG 模式
```

---

## 🔧 基礎使用

### 創建 Logger

#### 方法一：簡單創建

```python
from pretty_loguru import create_logger

# 基本創建
logger = create_logger("my_app")

# 自定義參數
logger = create_logger(
    name="my_app",
    level="DEBUG",
    log_path="./logs",
    rotation="daily",
    retention="7 days",
    compression="zip"
)
```

#### 方法二：配置物件創建

```python
from pretty_loguru import LoggerConfig, create_logger

# 創建配置
config = LoggerConfig(
    level="INFO",
    log_path="./logs",
    rotation="100 MB",
    retention="30 days",
    format_string="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}"
)

# 應用配置
logger = create_logger("my_app", config=config)
```

### 日誌級別

Pretty-Loguru 支援標準的日誌級別：

```python
logger.trace("最詳細的追蹤資訊")
logger.debug("調試資訊")
logger.info("一般資訊")
logger.success("成功訊息")  # Loguru 特有
logger.warning("警告訊息")
logger.error("錯誤訊息")
logger.critical("嚴重錯誤")
```

### 格式化輸出

#### 基本格式化

```python
# 變數插值
user = "張三"
logger.info(f"用戶 {user} 登入成功")

# 結構化資料
data = {"user_id": 123, "action": "login", "ip": "192.168.1.1"}
logger.info("用戶活動", **data)

# 多行訊息
logger.info("""
系統啟動報告：
- 資料庫：已連接
- 快取：已就緒
- 消息隊列：運行中
""")
```

#### 上下文資訊

```python
# 添加上下文
logger = logger.bind(request_id="abc123", user_id=456)
logger.info("處理用戶請求")

# 臨時上下文
with logger.contextualize(task="data_import"):
    logger.info("開始導入資料")
    # ... 導入邏輯
    logger.success("資料導入完成")
```

### 異常處理

```python
# 自動捕獲異常堆疊
@logger.catch
def risky_function():
    return 1 / 0  # 這會被自動記錄

# 手動記錄異常
try:
    risky_operation()
except Exception as e:
    logger.exception("操作失敗")  # 自動包含堆疊追蹤
```

### 多 Logger 管理

```python
from pretty_loguru import get_logger, list_loggers, unregister_logger

# 獲取現有 logger
auth_logger = get_logger("auth")

# 列出所有 logger
all_loggers = list_loggers()
print(f"目前有 {len(all_loggers)} 個 logger")

# 註銷 logger
unregister_logger("temporary_logger")
```

---

## 🎨 視覺化特性

### Rich 區塊

```python
# 基本區塊
logger.block("部署狀態", "所有服務運行正常")

# 自定義樣式
logger.block(
    title="錯誤報告",
    content=[
        "錯誤類型：連接超時",
        "發生時間：2024-01-15 10:30:45",
        "影響範圍：API 服務"
    ],
    border_style="red",
    title_style="bold red"
)

# 嵌套內容
logger.block("系統資訊", {
    "CPU": "Intel i7-9700K",
    "記憶體": "32GB DDR4",
    "磁碟": {
        "系統": "256GB SSD",
        "資料": "2TB HDD"
    }
})
```

### ASCII 藝術標題

```python
# 基本 ASCII 標題
logger.ascii_header("STARTUP")

# 自定義字體
logger.ascii_header("WELCOME", font="slant")

# 不同字體樣式
logger.ascii_header("ERROR", font="doom")

# 組合使用
logger.ascii_block(
    title="系統初始化",
    content="正在載入配置...",
    ascii_header="INIT",
    font="standard"
)
```

### Rich 表格

```python
# 創建表格資料
users = [
    {"id": 1, "name": "張三", "role": "管理員"},
    {"id": 2, "name": "李四", "role": "用戶"},
    {"id": 3, "name": "王五", "role": "訪客"}
]

# 顯示表格
logger.table(
    data=users,
    title="用戶列表",
    caption="總計 3 位用戶"
)
```

### 樹狀結構

```python
# 顯示目錄結構
project_structure = {
    "my_project": {
        "src": ["main.py", "utils.py", "models.py"],
        "tests": ["test_main.py", "test_utils.py"],
        "docs": ["README.md", "API.md"]
    }
}

logger.tree(
    data=project_structure,
    title="專案結構"
)
```

### 進度條

```python
# 顯示進度
for i in logger.progress(range(100), description="處理資料"):
    # 處理邏輯
    time.sleep(0.1)
```

---

## ⚙️ 配置管理

### 配置模板

Pretty-Loguru 提供多種預設配置模板：

```python
from pretty_loguru import ConfigTemplates

# 開發環境
dev_config = ConfigTemplates.development()
# - DEBUG 級別
# - 控制台輸出彩色
# - 7 天日誌保留

# 生產環境
prod_config = ConfigTemplates.production()
# - INFO 級別
# - 啟用壓縮
# - 30 天保留
# - 自動清理

# 測試環境
test_config = ConfigTemplates.testing()
# - WARNING 級別
# - 最小化輸出
# - 3 天保留

# 性能模式
perf_config = ConfigTemplates.performance()
# - ERROR 級別
# - 代理模式
# - 大檔案輪替
```

### 輪替預設

```python
from pretty_loguru import RotationPresets

# 按時間輪替
daily = RotationPresets.daily()      # 每日輪替
hourly = RotationPresets.hourly()    # 每小時輪替
weekly = RotationPresets.weekly()    # 每週輪替
monthly = RotationPresets.monthly()  # 每月輪替

# 按大小輪替
small = RotationPresets.size_based(max_size="10 MB")
large = RotationPresets.size_based(max_size="1 GB")

# 自定義輪替
custom = RotationPresets.custom(
    when="daily",
    at_time="02:00",
    retention="90 days",
    compression="zip"
)
```

### 動態配置更新

```python
# 創建初始配置
config = LoggerConfig(level="INFO")
loggers = config.apply_to("app", "api", "db")

# 調整日誌級別（所有 logger 同步更新）
config.update(level="DEBUG")

# 更改多個設定
config.update(
    level="WARNING",
    rotation="100 MB",
    retention="60 days"
)

# 克隆配置（避免影響原配置）
new_config = config.clone()
new_config.update(level="ERROR")
```

### 環境感知配置

```python
import os
from pretty_loguru import LoggerConfig, ConfigTemplates

# 根據環境變數選擇配置
env = os.getenv("APP_ENV", "development")

config_map = {
    "development": ConfigTemplates.development(),
    "staging": ConfigTemplates.testing(),
    "production": ConfigTemplates.production()
}

config = config_map.get(env, ConfigTemplates.development())
logger = config.apply_to("app")
```

---

## 🔌 框架整合

### FastAPI 整合

```python
from fastapi import FastAPI
from pretty_loguru import create_logger
from pretty_loguru.integrations.fastapi import setup_fastapi_logging

# 創建應用和 logger
app = FastAPI()
logger = create_logger("api", log_path="./logs")

# 設置 FastAPI 日誌
setup_fastapi_logging(
    app,
    logger=logger,
    log_requests=True,
    log_responses=True,
    log_errors=True
)

# 使用範例
@app.get("/")
async def root():
    logger.info("處理根路徑請求")
    return {"message": "Hello World"}

# 中間件自動記錄
# [2024-01-15 10:30:45] INFO | api | Request: GET / from 127.0.0.1
# [2024-01-15 10:30:45] INFO | api | Response: 200 OK in 15ms
```

### Uvicorn 整合

```python
from pretty_loguru import create_logger
from pretty_loguru.integrations.uvicorn import setup_uvicorn_logging
import uvicorn

# 創建 logger
logger = create_logger("server", log_path="./logs")

# 設置 Uvicorn 日誌
setup_uvicorn_logging(logger, level="INFO")

# 啟動服務器
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        log_config=None  # 使用 pretty-loguru 的配置
    )
```


---

## 🏭 生產環境最佳實踐

### 1. 日誌策略

```python
from pretty_loguru import ConfigTemplates, LoggerConfig

# 生產環境配置
production_config = LoggerConfig(
    level="INFO",                    # 適當的日誌級別
    log_path="/var/log/myapp",       # 專用日誌目錄
    rotation="500 MB",               # 檔案大小限制
    retention="30 days",             # 保留期限
    compression="zip",               # 壓縮舊日誌
    enqueue=True,                    # 異步寫入
    backtrace=True,                  # 完整錯誤追蹤
    diagnose=False                   # 生產環境關閉診斷
)

# 創建不同用途的 logger
app_logger = production_config.apply_to("app")
audit_logger = production_config.clone().update(
    retention="1 year"  # 審計日誌保留更久
).apply_to("audit")
```

### 2. 性能優化

```python
# 使用目標導向方法減少開銷
logger.console_info("用戶可見訊息")      # 僅控制台
logger.file_error("詳細錯誤資訊")        # 僅檔案

# 條件日誌
if logger.isEnabledFor("DEBUG"):
    expensive_debug_info = calculate_debug_data()
    logger.debug(expensive_debug_info)

# 批量操作
with logger.contextualize(batch_id="12345"):
    for item in large_dataset:
        # 上下文會自動附加到所有日誌
        process_item(item)
```

---

## 📖 API 參考

### 核心函數

#### `create_logger(name, **kwargs)`
創建一個新的 logger 實例。

**參數：**
- `name` (str): Logger 名稱
- `level` (str): 日誌級別，預設 "INFO"
- `log_path` (str): 日誌檔案路徑
- `rotation` (str/int/time): 輪替策略
- `retention` (str/int/timedelta): 保留策略
- `compression` (str): 壓縮格式
- `config` (LoggerConfig): 配置物件

**返回：** Logger 實例

#### `get_logger(name)`
獲取已存在的 logger。

**參數：**
- `name` (str): Logger 名稱

**返回：** Logger 實例或 None

### LoggerConfig 類

#### 屬性
- `level`: 日誌級別
- `log_path`: 檔案路徑
- `rotation`: 輪替策略
- `retention`: 保留策略
- `compression`: 壓縮設定
- `format_string`: 格式字串
- `enqueue`: 是否異步
- `serialize`: 是否序列化

#### 方法

##### `apply_to(*names)`
應用配置到一個或多個 logger。

```python
loggers = config.apply_to("app", "api", "db")
```

##### `update(**kwargs)`
更新配置並自動應用到所有關聯的 logger。

```python
config.update(level="DEBUG", rotation="1 hour")
```

##### `clone()`
創建配置的副本。

```python
new_config = config.clone()
```

### 視覺化方法

#### `logger.block(title, content, **kwargs)`
顯示 Rich 面板區塊。

**參數：**
- `title` (str): 標題
- `content` (str/list/dict): 內容
- `border_style` (str): 邊框樣式
- `title_style` (str): 標題樣式
- `padding` (int): 內邊距

#### `logger.ascii_header(text, **kwargs)`
顯示 ASCII 藝術標題。

**參數：**
- `text` (str): 要顯示的文字
- `font` (str): 字體名稱
- `width` (int): 寬度
- `border` (bool): 是否顯示邊框
- `border_style` (str): 邊框樣式

#### `logger.table(data, **kwargs)`
顯示表格。

**參數：**
- `data` (list[dict]): 表格資料
- `title` (str): 表格標題
- `caption` (str): 表格說明
- `show_header` (bool): 是否顯示標題列
- `show_lines` (bool): 是否顯示網格線

---

## ❓ 常見問題

### Q1: 如何在生產環境中避免性能問題？

**A:** 使用以下策略：
1. 適當的日誌級別（生產環境建議 INFO 或更高）
2. 啟用異步寫入（`enqueue=True`）
3. 使用目標導向方法避免不必要的格式化
4. 定期清理舊日誌檔案

### Q2: 如何處理多進程/多線程環境？

**A:** Pretty-Loguru 基於 Loguru，天生支援多線程。對於多進程：
```python
# 使用進程安全的檔案寫入
logger = create_logger(
    "app",
    enqueue=True,  # 異步隊列
    multiprocess=True  # 多進程安全
)
```

### Q3: 如何與現有的 logging 模組整合？

**A:** 可以攔截標準 logging：
```python
import logging
from pretty_loguru import create_logger

# 創建 pretty-loguru logger
logger = create_logger("app")

# 攔截標準 logging
logging.basicConfig(handlers=[InterceptHandler()], level=0)
```

### Q4: 如何自定義日誌格式？

**A:** 使用 format_string 參數：
```python
custom_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

logger = create_logger("app", format_string=custom_format)
```

### Q5: 視覺化功能會影響性能嗎？

**A:** 視覺化功能主要影響控制台輸出。建議：
- 生產環境謹慎使用 ASCII 藝術
- 使用 `console_*` 方法確保檔案日誌不包含格式化
- 對於高頻日誌避免使用複雜視覺化

---

## 🔄 遷移指南

### 從標準 logging 遷移

```python
# 之前（標準 logging）
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler("app.log")
logger.addHandler(handler)
logger.info("Hello")

# 之後（pretty-loguru）
from pretty_loguru import create_logger
logger = create_logger(__name__, level="INFO", log_path="app.log")
logger.info("Hello")
```

### 從純 Loguru 遷移

```python
# 之前（純 Loguru）
from loguru import logger
logger.add("app.log", rotation="1 day")
logger.info("Hello")

# 之後（pretty-loguru）
from pretty_loguru import create_logger
logger = create_logger("app", rotation="daily")
logger.info("Hello")
# 額外獲得視覺化功能
logger.block("歡迎", "系統已啟動")
```

### 最佳實踐建議

1. **逐步遷移**：先遷移新模組，再處理舊代碼
2. **保留兼容性**：使用適配器模式包裝現有日誌
3. **統一管理**：使用 LoggerConfig 統一配置
4. **測試覆蓋**：確保日誌輸出符合預期

---

## 🎯 總結

Pretty-Loguru 提供了一個功能完整、易於使用的日誌解決方案。無論是快速原型開發還是大規模生產部署，它都能滿足你的需求。

### 核心優勢

- ✅ **零配置啟動**：一行代碼開始使用
- ✅ **視覺化輸出**：讓日誌更易讀
- ✅ **生產就緒**：完整的輪替、壓縮、清理機制
- ✅ **靈活擴展**：豐富的自定義選項
- ✅ **框架友好**：與主流框架無縫整合


---

<div align="center">

**Happy Logging! 🎉**

[GitHub](https://github.com/your-repo/pretty-loguru) | [文檔](https://pretty-loguru.readthedocs.io) | [問題回報](https://github.com/your-repo/pretty-loguru/issues)

</div>