#!/bin/bash
# 視覺化測試執行腳本

echo "======================================"
echo "ASRHub 視覺化測試工具"
echo "======================================"
echo ""
echo "請選擇要執行的測試："
echo "1) 錄音服務 (Recording)"
echo "2) VAD 服務 (Silero VAD)"
echo "3) 喚醒詞服務 (OpenWakeWord)"
echo "0) 退出"
echo ""
echo "📌 提示：測試會持續運行直到您關閉視窗"
echo ""

read -p "請輸入選擇 (0-3): " choice

case $choice in
    1)
        echo "執行錄音服務視覺化測試..."
        echo "關閉視窗即可停止測試"
        python test_recording_visual.py
        ;;
    2)
        echo "執行 VAD 服務視覺化測試..."
        echo "關閉視窗即可停止測試"
        python test_vad_visual.py
        ;;
    3)
        echo "執行喚醒詞服務視覺化測試..."
        echo "關閉視窗即可停止測試"
        python test_wakeword_visual.py
        ;;
    0)
        echo "退出測試"
        exit 0
        ;;
    *)
        echo "無效的選擇"
        exit 1
        ;;
esac