#!/bin/bash

# ASR Hub 啟動腳本

echo "🚀 ASR Hub 啟動腳本"
echo "===================="

# 檢查 Python 版本
python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
echo "✓ Python 版本：$python_version"

# 檢查虛擬環境
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  建議使用虛擬環境執行"
    echo "   執行以下命令建立虛擬環境："
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo ""
fi

# 檢查依賴是否安裝
echo "📦 檢查依賴套件..."
missing_deps=false

# 檢查關鍵套件
for package in "fastapi" "loguru" "pyyaml"; do
    if ! python3 -c "import $package" 2>/dev/null; then
        echo "   ❌ 缺少套件：$package"
        missing_deps=true
    else
        echo "   ✓ $package"
    fi
done

if [ "$missing_deps" = true ]; then
    echo ""
    echo "⚠️  缺少必要的依賴套件"
    echo "   請執行：pip install -r requirements.txt"
    exit 1
fi

# 建立必要的目錄
echo ""
echo "📁 建立必要目錄..."
mkdir -p logs
mkdir -p models
mkdir -p data/uploads
echo "   ✓ 目錄建立完成"

# 啟動服務
echo ""
echo "🚀 啟動 ASR Hub..."
echo "   伺服器將在 http://localhost:8000 運行"
echo "   按 Ctrl+C 停止服務"
echo ""

# 設定 Python 路徑並啟動
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python3 main.py "$@"