#!/bin/bash
# 啟動 ASR Hub 服務腳本

echo "🚀 正在啟動 ASR Hub..."

# 檢查是否已在運行
if ps aux | grep -E "python.*main\.py" | grep -v grep > /dev/null; then
    echo "⚠️  ASR Hub 似乎已在運行"
    echo "如需重新啟動，請先執行 ./stop_asr_hub.sh"
    exit 1
fi

# 檢查連接埠
for PORT in 8000 8003; do
    if lsof -i :$PORT >/dev/null 2>&1; then
        echo "⚠️  連接埠 $PORT 被占用"
        echo "請先執行 ./stop_asr_hub.sh 清理連接埠"
        exit 1
    fi
done

# 啟動服務
echo "啟動主服務..."
nohup python main.py > logs/asr_hub_nohup.log 2>&1 &
PID=$!

echo "ASR Hub 已在背景啟動 (PID: $PID)"
echo "日誌檔案: logs/asr_hub_nohup.log"
echo ""
echo "使用以下命令查看日誌："
echo "  tail -f logs/asr_hub_nohup.log"
echo ""
echo "使用以下命令停止服務："
echo "  ./stop_asr_hub.sh"