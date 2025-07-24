# ASR_Hub 專案設置指南

## 快速開始

### 1. 克隆專案
```bash
git clone https://github.com/JonesHong/ASRHub.git
cd ASRHub
```

### 2. 建立虛擬環境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 3. 安裝相依套件
```bash
pip install -r requirements.txt
```

### 4. 設置配置檔案
```bash
# 複製範例配置檔
cp config/base.sample.yaml config/base.yaml

# 編輯 config/base.yaml，填入你的 API keys 和其他設定
# 注意：base.yaml 已加入 .gitignore，不會被提交到版本控制
```

### 5. 生成配置類別（重要！）
```bash
# 使用 yaml2py 生成型別安全的配置類別
yaml2py --config config/base.yaml --output ./src/config

# 這會生成：
# - src/config/schema.py
# - src/config/manager.py
# 這些檔案包含敏感資料，已加入 .gitignore
```

### 6. 驗證安裝
```bash
# 執行簡單測試
python -c "from src.config.manager import ConfigManager; print('配置載入成功')"
python -c "from src.utils.logger import get_logger; logger = get_logger('test'); logger.info('日誌系統正常')"
```

## 注意事項

1. **yaml2py 生成的檔案**
   - `src/config/schema.py` 和 `src/config/manager.py` 是由 yaml2py 根據你的配置檔生成的
   - 這些檔案包含你的配置值（可能包含 API keys），因此不應提交到版本控制
   - 每位開發者都需要在本地執行 yaml2py 來生成這些檔案

2. **敏感資料處理**
   - 所有敏感資料（API keys、密碼等）都應該放在 `config/base.yaml` 中
   - 可以使用環境變數，例如：`api_key: ${OPENAI_API_KEY}`
   - 絕對不要將 `config/base.yaml` 提交到版本控制

3. **開發環境配置**
   - 如需不同環境的配置，可建立 `config/base.dev.yaml`、`config/base.prod.yaml` 等
   - 這些檔案也已加入 .gitignore

## 常見問題

### Q: 為什麼要每次都執行 yaml2py？
A: yaml2py 會根據你的配置檔生成包含實際配置值的 Python 類別。由於這些值可能包含敏感資料，我們不將生成的檔案加入版本控制，確保每位開發者使用自己的配置。

### Q: 如何更新配置？
A: 
1. 編輯 `config/base.yaml`
2. 重新執行 `yaml2py --config config/base.yaml --output ./src/config`
3. 重啟應用程式

### Q: 如何使用環境變數？
A: 在 YAML 配置中使用 `${VARIABLE_NAME:default_value}` 格式，例如：
```yaml
openai:
  api_key: ${OPENAI_API_KEY:your-default-key}
```

## 開發指南

詳細的開發指南請參考：
- [PRINCIPLE.md](PRINCIPLE.md) - 開發原則
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - 專案結構
- [TODO_PHASE1.md](TODO_PHASE1.md) - 第一階段任務
- [TODO_PHASE2.md](TODO_PHASE2.md) - 第二階段任務