# yaml2py 完整使用說明書

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/yaml2py.svg)](https://badge.fury.io/py/yaml2py)

yaml2py 是一個強大的命令列工具，能夠從 YAML 配置檔案自動生成具有型別提示的 Python 類別。它支援巢狀結構、熱重載、環境變數、敏感資料保護等進階功能，讓您的配置管理變得更加安全、便捷和型別安全。

## 目錄

1. [核心特性](#核心特性)
2. [安裝指南](#安裝指南)
3. [快速開始](#快速開始)
4. [進階功能](#進階功能)
5. [命令列介面](#命令列介面)
6. [API 參考](#api-參考)
7. [最佳實踐](#最佳實踐)
8. [範例集合](#範例集合)
9. [故障排除](#故障排除)
10. [開發指南](#開發指南)

## 核心特性

### 🔧 自動化程式碼生成
- 從 YAML 檔案自動生成 Python 類別
- 完整的型別提示支援，提供優秀的 IDE 體驗
- 自動處理巢狀結構和複雜資料型態

### 🏗️ 智慧型別推斷
- 自動識別並正確推斷 Python 型別：
  - 基本型別：`int`、`float`、`bool`、`str`
  - 容器型別：`List[T]`、`Dict[str, Any]`
  - 可選型別：`Optional[T]`
  - 聯合型別：`Union[T1, T2, ...]`

### 🔄 熱重載機制
- 自動監控配置檔案變更
- 即時重新載入，無需重啟應用程式
- 在 CI 環境中自動停用以避免問題

### 🛡️ 安全功能
- 敏感資料自動遮罩（密碼、API 金鑰等）
- 使用 `yaml.safe_load()` 防止程式碼注入
- 支援環境變數以保護敏感資訊

### 🎯 智慧路徑偵測
- 自動在常見位置尋找配置檔案
- 支援多種檔案命名慣例
- 向上搜尋目錄樹以找到配置

### 💡 開發者友善
- 單例模式確保配置唯一性
- 完整的程式碼自動完成支援
- 清晰的錯誤訊息和除錯資訊

## 安裝指南

### 使用 pip 安裝

```bash
pip install yaml2py
```

### 從原始碼安裝

```bash
git clone https://github.com/yourusername/yaml2py.git
cd yaml2py
pip install -e .
```

### 開發環境安裝

```bash
# 安裝開發相依套件
pip install -e .[dev]

# 或使用 make
make install-dev
```

## 快速開始

### 步驟 1：建立 YAML 配置檔案

建立一個 `config.yaml` 檔案：

```yaml
# 應用程式配置
app:
  name: MyAwesomeApp
  version: 1.0.0
  debug: true
  
# 伺服器設定
server:
  host: 0.0.0.0
  port: 8080
  workers: 4
  timeout: 30.5
  
# 資料庫配置
database:
  engine: postgresql
  host: localhost
  port: 5432
  name: myapp_db
  user: admin
  password: secret123
  
  # 連接池設定
  pool:
    size: 20
    max_overflow: 10
    timeout: 30
    
# 功能開關
features:
  - name: authentication
    enabled: true
    config:
      session_timeout: 3600
      max_attempts: 3
  - name: caching
    enabled: false
    config:
      backend: redis
      ttl: 300
```

### 步驟 2：生成 Python 配置類別

使用命令列工具生成程式碼：

```bash
# 指定輸入和輸出路徑
yaml2py --config config.yaml --output ./src/config

# 或使用簡短選項
yaml2py -c config.yaml -o ./src/config

# 互動式模式（自動偵測配置檔案）
yaml2py
```

### 步驟 3：在程式碼中使用

```python
from src.config import ConfigManager

# 獲取單例實例
config = ConfigManager()

# 使用型別安全的屬性存取
print(f"應用程式：{config.app.name} v{config.app.version}")
print(f"偵錯模式：{config.app.debug}")  # bool 型別
print(f"伺服器埠號：{config.server.port}")  # int 型別
print(f"逾時設定：{config.server.timeout}")  # float 型別

# 存取巢狀結構
print(f"資料庫：{config.database.engine}")
print(f"連接池大小：{config.database.pool.size}")

# 處理列表資料
for feature in config.features:
    if feature.enabled:
        print(f"已啟用功能：{feature.name}")
        print(f"  Session 逾時：{feature.config.session_timeout}")

# 安全地顯示配置（自動遮罩敏感資料）
config.database.print_all()
# 輸出：
# DatabaseSchema:
# ----------------------------------------
#   engine: postgresql
#   host: localhost
#   port: 5432
#   name: myapp_db
#   user: admin
#   password: se*****23  # 自動遮罩！
# ----------------------------------------
```

## 進階功能

### 環境變數支援

yaml2py 支援在 YAML 檔案中使用環境變數，提供兩種語法：

#### 基本語法

```yaml
database:
  host: ${DB_HOST}  # 必須設定的環境變數
  port: ${DB_PORT:5432}  # 帶預設值的環境變數
  name: ${DB_NAME:myapp}
  user: ${DB_USER:postgres}
  password: ${DB_PASSWORD}  # 敏感資料不應提供預設值
```

#### 設定環境變數

```bash
# 設定環境變數
export DB_HOST=prod-db.example.com
export DB_PASSWORD=super_secret

# 執行應用程式
python app.py
```

#### 嚴格模式

預設情況下，未設定的環境變數會被替換為空字串。您可以啟用嚴格模式：

```bash
# 啟用嚴格模式
export YAML2PY_STRICT_ENV=true

# 現在缺少必要的環境變數會拋出錯誤
yaml2py -c config.yaml -o ./output
```

### 熱重載功能

配置檔案會自動監控變更並重新載入：

```python
# 初始配置
config = ConfigManager()
print(config.app.debug)  # False

# 編輯 config.yaml，將 debug 改為 true
# 不需要重啟程式！

time.sleep(2)  # 等待檔案系統事件
print(config.app.debug)  # True - 自動更新！
```

#### 停用熱重載

在某些環境中（如 CI/CD），您可能想要停用熱重載：

```python
# 方法 1：設定環境變數
os.environ['CI'] = 'true'

# 方法 2：修改程式碼（需要自訂）
# ConfigManager 會自動偵測 CI 環境
```

### 巢狀結構處理

yaml2py 優雅地處理深層巢狀結構：

```yaml
services:
  api:
    endpoints:
      users:
        base_path: /api/v1/users
        methods:
          get:
            rate_limit: 1000
            cache_ttl: 300
          post:
            rate_limit: 100
            requires_auth: true
```

存取巢狀資料：

```python
# 完整的型別提示和自動完成
rate_limit = config.services.api.endpoints.users.methods.get.rate_limit
```

### 列表和物件陣列

自動為物件陣列生成型別化類別：

```yaml
servers:
  - name: web-1
    host: 10.0.0.1
    port: 80
    region: us-east
  - name: web-2
    host: 10.0.0.2
    port: 80
    region: us-west
```

使用生成的類別：

```python
for server in config.servers:  # List[ServerSchema]
    print(f"{server.name}: {server.host}:{server.port}")
    print(f"區域：{server.region}")
```

### 敏感資料保護

#### 自動偵測敏感欄位

以下關鍵字會被自動識別為敏感資料：
- `password`
- `secret`
- `token`
- `key`
- `api_key`
- `private`

#### 使用範例

```python
# 直接存取會返回真實值
real_password = config.database.password  # "secret123"

# 使用 print_all() 會自動遮罩
config.database.print_all()
# password: se*****23

# 控制遮罩行為
config.database.print_all(mask_sensitive=False)  # 顯示真實值（謹慎使用！）

# 獲取屬性字典
props = config.database.return_properties(
    return_type="dict",
    mask_sensitive=True
)
# {'password': 'se*****23', ...}
```

## 命令列介面

### 基本用法

```bash
yaml2py [OPTIONS]
```

### 選項

| 選項 | 簡寫 | 說明 | 預設值 |
|------|------|------|--------|
| `--config` | `-c` | YAML 配置檔案路徑 | 自動偵測 |
| `--output` | `-o` | 輸出目錄路徑 | 自動偵測 |
| `--help` | | 顯示說明訊息 | - |

### 自動偵測邏輯

當未指定 `--config` 時，yaml2py 會按以下順序搜尋：

1. 當前目錄
2. `./config/` 目錄
3. `./conf/` 目錄
4. 向上搜尋最多 5 層目錄

支援的檔案名稱：
- `config.yaml` / `config.yml`
- `settings.yaml` / `settings.yml`
- `app.yaml` / `app.yml`

### 輸出結構

生成的檔案結構：

```
output_dir/
├── __init__.py      # 套件初始化
├── schema.py        # 配置類別定義
└── manager.py       # 配置管理器（單例模式）
```

## API 參考

### ConfigManager 類別

```python
class ConfigManager:
    """配置管理器，使用單例模式"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        參數：
            config_path: 配置檔案路徑（可選，預設自動偵測）
        """
    
    def reload_config(self):
        """手動重新載入配置"""
    
    def get_raw_data(self) -> Dict[str, Any]:
        """獲取原始 YAML 資料"""
```

### ConfigSchema 基礎類別

所有生成的配置類別都繼承自 `ConfigSchema`：

```python
class ConfigSchema:
    def return_properties(self, 
                         return_type="list", 
                         mask_sensitive=True):
        """
        返回所有屬性
        
        參數：
            return_type: "list" 或 "dict"
            mask_sensitive: 是否遮罩敏感資料
        """
    
    def print_all(self, mask_sensitive=True):
        """格式化列印所有屬性"""
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
```

## 最佳實踐

### 1. 配置檔案組織

```yaml
# 使用清晰的分組
app:
  # 應用程式基本資訊
  name: MyApp
  version: 1.0.0

# 環境相關配置
environment:
  name: production
  debug: false

# 外部服務配置
services:
  database:
    # 主要配置
  cache:
    # 快取配置
```

### 2. 環境變數使用

```yaml
# ❌ 避免硬編碼敏感資訊
database:
  password: admin123

# ✅ 使用環境變數
database:
  password: ${DB_PASSWORD}
  
# ✅ 非敏感資料可提供預設值
server:
  port: ${SERVER_PORT:8080}
```

### 3. 型別一致性

```yaml
# ❌ 避免混合型別
ports:
  - 8080
  - "9090"  # 字串
  - 3000

# ✅ 保持型別一致
ports:
  - 8080
  - 9090
  - 3000
```

### 4. 命名慣例

```yaml
# ✅ 使用 snake_case
database_config:
  connection_timeout: 30
  max_retry_attempts: 3

# 生成的類別會自動轉換為 CamelCase
# DatabaseConfigSchema
```

## 範例集合

### 基礎配置範例

```yaml
# 簡單的 Web 應用程式配置
app:
  name: SimpleWebApp
  version: 1.0.0
  debug: true

server:
  host: 0.0.0.0
  port: 8000
  
database:
  url: sqlite:///app.db
```

### 微服務配置範例

```yaml
# 微服務架構配置
service:
  name: user-service
  version: 2.1.0
  
# 服務發現
discovery:
  consul:
    host: consul.service.consul
    port: 8500
    
# 訊息佇列
messaging:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASS}
    
# API 閘道
gateway:
  timeout: 30
  retry_count: 3
  circuit_breaker:
    threshold: 5
    timeout: 60
```

### 多環境配置範例

```yaml
# 使用環境變數切換配置
environment: ${ENV:development}

# 開發環境預設值
database:
  host: ${DB_HOST:localhost}
  port: ${DB_PORT:5432}
  
# 根據環境調整
features:
  debug_toolbar: ${ENABLE_DEBUG:true}
  profiling: ${ENABLE_PROFILING:false}
  
# 日誌配置
logging:
  level: ${LOG_LEVEL:DEBUG}
  format: ${LOG_FORMAT:detailed}
```

## 故障排除

### 常見問題

#### 1. 找不到配置檔案

**錯誤訊息：**
```
FileNotFoundError: Could not find config.yaml or config.yml
```

**解決方案：**
```bash
# 明確指定路徑
yaml2py --config /path/to/config.yaml --output ./output

# 或將配置放在標準位置
mkdir config
mv myconfig.yaml config/config.yaml
```

#### 2. 環境變數未設定

**錯誤訊息：**
```
EnvironmentVariableError: 環境變數 'DB_PASSWORD' 未設定
```

**解決方案：**
```bash
# 設定環境變數
export DB_PASSWORD=your_password

# 或使用預設值
# 在 YAML 中：password: ${DB_PASSWORD:default_pass}

# 或關閉嚴格模式
export YAML2PY_STRICT_ENV=false
```

#### 3. 熱重載不工作

**可能原因：**
- 在 CI 環境中執行（自動停用）
- 檔案系統不支援監控
- 權限問題

**解決方案：**
```python
# 手動重新載入
config = ConfigManager()
config.reload_config()
```

#### 4. 型別推斷錯誤

**問題：** 數字被識別為字串

**解決方案：**
```yaml
# ❌ 錯誤
port: "8080"

# ✅ 正確
port: 8080
```

### 除錯技巧

#### 1. 查看生成的程式碼

```bash
# 生成後檢查 schema.py
cat ./output/schema.py
```

#### 2. 驗證 YAML 語法

```bash
# 使用 Python 驗證
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

#### 3. 環境變數除錯

```bash
# 列出所有環境變數
env | grep -E "(DB_|APP_|CONFIG_)"

# 測試環境變數替換
YAML2PY_STRICT_ENV=false yaml2py -c config.yaml -o ./test_output
```

## 開發指南

### 專案結構

```
yaml2py/
├── yaml2py/
│   ├── __init__.py
│   ├── cli.py              # CLI 主程式
│   ├── env_loader.py       # 環境變數處理
│   └── templates/          # 程式碼模板
│       ├── schema.py.tpl
│       └── manager.py.tpl
├── tests/                  # 測試套件
├── examples/               # 範例配置
├── docs/                   # 文件
└── Makefile               # 開發工具
```

### 開發環境設定

```bash
# 克隆專案
git clone https://github.com/yourusername/yaml2py.git
cd yaml2py

# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安裝開發相依套件
make install-dev
```

### 執行測試

```bash
# 執行所有測試
make test

# 執行特定測試
python -m pytest tests/test_cli.py

# 測試覆蓋率
make test-coverage
```

### 程式碼品質

```bash
# 執行 linting
make lint

# 自動格式化
make format

# 安全檢查
make security-check

# 完整 CI 流程
make ci
```

### 貢獻指南

1. Fork 專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交變更 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 開啟 Pull Request

### 發布流程

```bash
# 準備發布
make prepare-release

# 建立發布套件
make build

# 上傳到 TestPyPI
make upload-test

# 上傳到 PyPI
make upload
```

## 未來發展

### 計劃中的功能

- [ ] 支援自訂型別驗證器
- [ ] YAML 錨點和引用支援
- [ ] 多配置檔案合併
- [ ] 配置繼承機制
- [ ] JSON Schema 驗證
- [ ] 配置檔案加密
- [ ] GraphQL 架構生成
- [ ] 配置版本管理

### 效能優化

- [ ] 延遲載入大型配置
- [ ] 配置快取機制
- [ ] 增量式重新載入

## 授權

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案。

## 致謝

感謝所有貢獻者和使用者的支援，讓 yaml2py 變得更好！

---

📚 **更多資源：**
- [GitHub Repository](https://github.com/yourusername/yaml2py)
- [Issue Tracker](https://github.com/yourusername/yaml2py/issues)
- [PyPI Package](https://pypi.org/project/yaml2py/)