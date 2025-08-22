#!/usr/bin/env python3
"""
簡易 HTTP 服務器提供前端檔案
"""

import http.server
import socketserver
import os
import signal
import sys
from pathlib import Path

PORT = 8082
DIRECTORY = "frontend"

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """添加 CORS 支援的 HTTP 請求處理器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

# 使用 ThreadingTCPServer 替代 TCPServer，支援多線程處理
class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """支援多線程的 HTTP 服務器"""
    # 允許重用地址，避免 "Address already in use" 錯誤
    allow_reuse_address = True
    # 設置 daemon 線程，確保主程序退出時所有線程都會終止
    daemon_threads = True
    # 設置請求隊列大小
    request_queue_size = 100

def signal_handler(sig, frame):
    """處理 Ctrl+C 信號"""
    print('\n\n正在關閉服務器...')
    sys.exit(0)

def main():
    # 註冊信號處理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 確保在正確的目錄
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # 使用改進的線程化服務器
    with ThreadedHTTPServer(("", PORT), CORSRequestHandler) as httpd:
        # 設置套接字選項（額外保險）
        httpd.socket.settimeout(0.5)  # 設置超時，讓服務器定期檢查中斷信號
        
        print(f"=== 前端服務器啟動 ===")
        print(f"訪問 http://localhost:{PORT} 開始使用")
        print(f"提供目錄: {DIRECTORY}")
        print("按 Ctrl+C 停止服務器")
        print("=" * 30)
        
        try:
            # 使用 handle_request 循環替代 serve_forever，更容易中斷
            while True:
                httpd.handle_request()
        except KeyboardInterrupt:
            print("\n服務器正在停止...")
        except SystemExit:
            print("服務器已停止")
        finally:
            # 確保服務器正確關閉
            httpd.shutdown()
            httpd.server_close()
            print("服務器已完全關閉")

if __name__ == "__main__":
    main()