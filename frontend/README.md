# Frontend 目錄

本目錄包含 ASRHub 的前端相關專案與測試。

## Submodules

### wake-word-transcriber
前端喚醒詞偵測與語音轉譯應用程式。

**Repository**: https://github.com/JonesHong/frontend_only_wake_word_transcriber

**功能特點**：
- 瀏覽器端喚醒詞偵測
- 即時語音轉譯
- 支援多種語言
- 無需後端伺服器

**初始化與更新**：
```bash
# 初始化 submodule
git submodule init

# 更新 submodule 到最新版本
git submodule update

# 或一次完成初始化與更新
git submodule update --init --recursive
```

**拉取最新更改**：
```bash
cd wake-word-transcriber
git pull origin main
cd ../..
git add frontend/wake-word-transcriber
git commit -m "Update wake-word-transcriber submodule"
```

## 其他專案

- **batch-test**: 批次測試工具
- **fsm-test**: 有限狀態機測試
- **protocol-test**: 協議測試
- **realtime-streaming**: 即時串流測試
- **realtime-test**: 即時功能測試
- **vad-test**: 語音活動偵測測試
- **wakeword-test**: 喚醒詞測試

## 開發說明

每個子目錄都是獨立的前端專案，可以單獨執行和測試。請參考各自目錄內的 README 文件了解詳細使用方法。