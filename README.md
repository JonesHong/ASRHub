# ASR Hub

<div align="center">

**一個統一的語音辨識中介系統**

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

</div>

## 📋 簡介

ASR Hub 是一個功能強大的語音辨識中介系統，整合多種 ASR（Automatic Speech Recognition）服務提供商，透過統一的 API 介面提供語音轉文字服務。

### 核心特性

- 🎯 **統一介面**：整合多種 ASR 提供商（Whisper、FunASR、Vosk 等）
- 🔌 **多協定支援**：HTTP SSE、WebSocket、Socket.io、gRPC、Redis
- 🎨 **Pipeline 架構**：RxJS 風格的串流處理，支援 VAD、降噪、格式轉換等
- 📊 **狀態管理**：有限狀態機（FSM）管理 Session 狀態
- 🔧 **靈活配置**：基於 YAML 的配置系統，支援環境變數和熱重載
- 📝 **美化日誌**：使用 pretty-loguru 提供視覺化日誌輸出

## 🚀 快速開始

### 系統需求

- Python 3.8+
- Linux/macOS/Windows
- 記憶體：建議 4GB 以上（視使用的 ASR 模型而定）

### 安裝與設置

詳細的安裝與設置步驟請參考

快速步驟：
```bash
# 克隆專案
git clone https://github.com/JonesHong/ASRHub.git
cd ASRHub

# 建立虛擬環境並安裝依賴
python -m venv venv
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt

# 設置配置
cp config/base.sample.yaml config/base.yaml
# 編輯 config/base.yaml 填入您的設定

# 生成配置類別（重要！）
yaml2py --config config/base.yaml --output ./src/config

# 執行
python -m src.core.asr_hub
```

## 📖 架構概覽

```
ASR Hub
├── API 層（多協定支援）
│   ├── HTTP SSE
│   ├── WebSocket
│   ├── Socket.io
│   ├── gRPC
│   └── Redis
├── Pipeline 處理層
│   ├── VAD（語音活動偵測）
│   ├── 降噪
│   ├── 取樣率調整
│   ├── 格式轉換
│   └── 喚醒詞偵測
├── Provider 抽象層
│   ├── Local Whisper
│   ├── FunASR
│   ├── Vosk
│   ├── Google STT
│   └── OpenAI API
└── 狀態管理（FSM）
```

## 🔧 API 使用

### HTTP SSE 範例

```python
import requests
import json

# 開始語音辨識
response = requests.post('http://localhost:8080/control', json={
    'command': 'start',
    'session_id': 'test-session',
    'config': {
        'provider': 'whisper',
        'language': 'zh',
        'pipeline': ['vad', 'sample_rate']
    }
})

# 串流傳送音訊資料
# ...

# 接收轉譯結果（透過 SSE）
# ...
```

## 🛠️ 開發

### 開發原則

本專案遵循以下核心原則：
- KISS（Keep It Simple, Stupid）
- YAGNI（You Aren't Gonna Need It）
- SOLID 原則
- DRY（Don't Repeat Yourself）

詳見 [PRINCIPLE.md](./references/spec/PRINCIPLE.md)

### 專案結構

詳見 [PROJECT_STRUCTURE.md](./references/spec/PROJECT_STRUCTURE.md)

### 貢獻指南

1. Fork 專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交變更 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 開啟 Pull Request

## 📚 文件

- [軟體需求規格說明書](./references/spec/SRS.md)
- [開發原則](./references/spec/PRINCIPLE.md)
- [專案架構](./references/spec/PROJECT_STRUCTURE.md)
- [第一階段工作清單](./references/todo_phase/TODO_PHASE1.md)
- [第二階段工作清單](./references/todo_phase/TODO_PHASE2.md)

## 📄 授權

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

## 🤝 致謝

感謝所有貢獻者和以下開源專案：
- [yaml2py](https://pypi.org/project/yaml2py/) - YAML 配置管理
- [pretty-loguru](https://pypi.org/project/pretty-loguru/) - 美化日誌輸出

---

<div align="center">
Made with ❤️ by ASR Hub Team
</div>