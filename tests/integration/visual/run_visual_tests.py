#!/usr/bin/env python3
"""
ASRHub 視覺化測試啟動器

執行各種服務的視覺化測試，無需輸入時長，
測試會持續運行直到使用者關閉視窗。
"""

import sys
import subprocess
import os

def print_menu():
    """顯示選單"""
    print("=" * 50)
    print("       ASRHub 視覺化測試工具")
    print("=" * 50)
    print()
    print("請選擇要執行的測試：")
    print()
    print("  1) 🎙️  錄音服務測試 (Recording)")
    print("  2) 🎤  VAD 服務測試 (Voice Activity Detection)")
    print("  3) 🎯  喚醒詞服務測試 (OpenWakeWord)")
    print("  0) 退出")
    print()
    print("📌 提示：測試會持續運行直到您關閉視窗")
    print()

def run_test(script_name, description):
    """執行測試腳本"""
    print()
    print(f"正在啟動{description}...")
    print("關閉視窗即可停止測試")
    print("-" * 50)
    
    try:
        # 取得當前腳本所在目錄
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, script_name)
        
        # 執行測試腳本
        result = subprocess.run([sys.executable, script_path])
        
        if result.returncode == 0:
            print()
            print(f"✅ {description}完成")
        else:
            print()
            print(f"❌ {description}失敗 (錯誤碼: {result.returncode})")
    except FileNotFoundError:
        print(f"❌ 找不到測試腳本: {script_name}")
    except KeyboardInterrupt:
        print()
        print("⚠️  測試被使用者中斷")
    except Exception as e:
        print(f"❌ 執行錯誤: {e}")

def main():
    """主函數"""
    while True:
        print_menu()
        
        try:
            choice = input("請輸入選項 [0-3]: ").strip()
            
            if choice == "1":
                run_test("test_recording_visual.py", "錄音服務視覺化測試")
            elif choice == "2":
                run_test("test_vad_visual.py", "VAD 服務視覺化測試")
            elif choice == "3":
                run_test("test_wakeword_visual.py", "喚醒詞服務視覺化測試")
            elif choice == "0":
                print()
                print("退出測試工具")
                break
            else:
                print()
                print("❌ 無效的選項，請重新選擇")
                input("按 Enter 繼續...")
                
        except KeyboardInterrupt:
            print()
            print()
            print("⚠️  程式被使用者中斷")
            break
        except Exception as e:
            print()
            print(f"❌ 發生錯誤: {e}")
            input("按 Enter 繼續...")

if __name__ == "__main__":
    main()