#!/usr/bin/env python3
"""
測試 HTTP SSE 轉譯功能
測試各種音訊格式的轉譯
"""

import requests
import json
import os
import time
from datetime import datetime

# API 設定
BASE_URL = "http://127.0.0.1:8000"

def test_transcribe_file(file_path: str, provider: str = "whisper", language: str = "zh"):
    """測試轉譯音訊檔案"""
    if not os.path.exists(file_path):
        print(f"❌ 檔案不存在: {file_path}")
        return
    
    # 準備表單資料
    with open(file_path, 'rb') as f:
        files = {'audio': (os.path.basename(file_path), f, 'audio/wav')}
        data = {
            'provider': provider,
            'language': language
        }
        
        print(f"\n📁 測試檔案: {file_path}")
        print(f"🔧 Provider: {provider}")
        print(f"🌐 語言: {language}")
        print("🚀 發送請求...")
        
        start_time = time.time()
        
        try:
            # 發送 POST 請求
            response = requests.post(
                f"{BASE_URL}/v1/transcribe",
                files=files,
                data=data,
                timeout=30
            )
            
            elapsed_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 轉譯成功！(耗時: {elapsed_time:.2f}秒)")
                print(f"📝 轉譯文字: {result['transcript']['text']}")
                print(f"🌍 偵測語言: {result['transcript']['language']}")
                print(f"🎯 信心分數: {result['transcript']['confidence']:.2f}")
                
                # 顯示片段資訊
                if 'segments' in result['transcript'] and result['transcript']['segments']:
                    print(f"\n📊 片段數量: {len(result['transcript']['segments'])}")
                    for i, seg in enumerate(result['transcript']['segments'][:3]):  # 只顯示前3個
                        print(f"  片段{i+1}: {seg['text']}")
                
            else:
                print(f"❌ 轉譯失敗！狀態碼: {response.status_code}")
                print(f"錯誤訊息: {response.text}")
                
        except requests.exceptions.Timeout:
            print("❌ 請求超時！")
        except requests.exceptions.ConnectionError:
            print("❌ 無法連接到伺服器！請確認 ASR Hub 是否正在運行。")
        except Exception as e:
            print(f"❌ 發生錯誤: {str(e)}")


def test_create_test_mp4():
    """創建測試用的 MP4 檔案"""
    print("\n🎬 創建測試 MP4 檔案...")
    
    # 使用 ffmpeg 將 WAV 轉換為 MP4
    if os.path.exists("test_audio/small.wav"):
        os.system("ffmpeg -i test_audio/small.wav -c:a aac test_audio/test.mp4 -y")
        if os.path.exists("test_audio/test.mp4"):
            print("✅ 成功創建 test.mp4")
            return "test_audio/test.mp4"
    
    print("❌ 無法創建測試 MP4 檔案")
    return None


def main():
    """主測試函數"""
    print("=" * 60)
    print("HTTP SSE /v1/transcribe 端點測試")
    print("=" * 60)
    
    # 檢查伺服器狀態
    print("\n🔍 檢查伺服器狀態...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            health = response.json()
            print(f"✅ 伺服器正常運行")
            print(f"   活躍 sessions: {health['active_sessions']}")
            print(f"   活躍連線: {health['active_connections']}")
        else:
            print(f"⚠️  伺服器回應異常: {response.status_code}")
    except:
        print("❌ 無法連接到伺服器！請先啟動 ASR Hub：")
        print("   python main.py")
        return
    
    # 測試不同格式的檔案
    test_files = []
    
    # WAV 檔案
    if os.path.exists("test_audio/small.wav"):
        test_files.append(("test_audio/small.wav", "wav"))
    
    # MP4 檔案
    mp4_file = test_create_test_mp4()
    if mp4_file:
        test_files.append((mp4_file, "mp4"))
    
    # PCM 檔案（如果有）
    if os.path.exists("test_audio/test.pcm"):
        test_files.append(("test_audio/test.pcm", "pcm"))
    
    # 測試每個檔案
    for file_path, format_type in test_files:
        print(f"\n{'='*60}")
        print(f"測試 {format_type.upper()} 格式")
        print(f"{'='*60}")
        test_transcribe_file(file_path)
        time.sleep(1)  # 避免請求過快
    
    print(f"\n{'='*60}")
    print("測試完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()