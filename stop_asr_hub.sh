#!/bin/bash
# 停止 ASR Hub 服務腳本

echo "🛑 正在停止 ASR Hub..."

# 查找並終止所有 ASR Hub 相關程序
echo "尋找 ASR Hub 程序..."
PIDS=$(ps aux | grep -E "python.*main\.py|python.*asr_hub" | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "✅ 沒有找到運行中的 ASR Hub 程序"
else
    echo "找到以下 PID: $PIDS"
    for PID in $PIDS; do
        echo "終止程序 $PID..."
        kill -TERM $PID 2>/dev/null
        sleep 1
        # 如果還在運行，強制終止
        if kill -0 $PID 2>/dev/null; then
            echo "強制終止程序 $PID..."
            kill -9 $PID 2>/dev/null
        fi
    done
    echo "✅ 所有程序已終止"
fi

# 檢查連接埠狀態
echo ""
echo "檢查連接埠狀態..."
for PORT in 8000 8003; do
    if lsof -i :$PORT >/dev/null 2>&1; then
        echo "⚠️  連接埠 $PORT 仍被占用"
        PID=$(lsof -t -i :$PORT)
        echo "  嘗試終止占用程序 PID: $PID"
        kill -9 $PID 2>/dev/null
    else
        echo "✅ 連接埠 $PORT 已釋放"
    fi
done

echo ""
echo "🎉 ASR Hub 已停止"