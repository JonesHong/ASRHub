#!/usr/bin/env python3
"""
視覺化測試運行器
提供統一的介面來運行各種視覺化測試
"""

import os
import sys
import subprocess
from pathlib import Path

# 確保能找到專案根目錄
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))


def main():
    """主函數"""
    # 檢查是否在正確的位置執行
    project_root = Path(__file__).parent.parent.parent.parent
    if not (project_root / 'src').exists():
        print("⚠️  請從專案根目錄執行此腳本")
        print(f"例如: python {Path(__file__).relative_to(project_root)}")
        sys.exit(1)
    
    print("=" * 60)
    print("🎯 ASR Hub 視覺化測試運行器")
    print("=" * 60)
    print("\n請選擇要運行的測試：")
    print("1. VAD (語音活動檢測) 視覺化測試")
    print("2. Wake Word (喚醒詞) 視覺化測試")
    print("3. Recording (錄音) 視覺化測試 - 包含聲譜圖")
    print("4. 退出")
    
    choice = input("\n請輸入選擇 (1-4): ").strip()
    
    # 測試檔案路徑
    test_dir = Path(__file__).parent
    
    # 切換到專案根目錄
    os.chdir(project_root)
    
    if choice == "1":
        print("\n啟動 VAD 視覺化測試...")
        print("請對著麥克風說話，觀察語音檢測效果")
        subprocess.run([sys.executable, str(test_dir / "test_vad_visual.py")])
    elif choice == "2":
        print("\n啟動喚醒詞視覺化測試...")
        # 檢查 HF_TOKEN
        if not os.environ.get("HF_TOKEN"):
            print("⚠️  警告: 未設定 HF_TOKEN 環境變數")
            print("如果需要下載 HuggingFace 模型，請設定此變數")
            print("export HF_TOKEN=your_token_here\n")
        print("請說 '嗨，高醫' 或 'hi kmu' 來觸發喚醒詞")
        subprocess.run([sys.executable, str(test_dir / "test_wakeword_visual.py")])
    elif choice == "3":
        print("\n啟動錄音視覺化測試...")
        print("包含即時聲譜圖顯示")
        print("開始錄音，關閉視窗結束")
        subprocess.run([sys.executable, str(test_dir / "test_recording_visual.py")])
    elif choice == "4":
        print("\n再見！")
        sys.exit(0)
    else:
        print("\n無效的選擇，請重新執行")
        sys.exit(1)


if __name__ == "__main__":
    main()