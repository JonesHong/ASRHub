#!/usr/bin/env python3
"""
簡易 HTTP 服務器提供前端檔案
"""

import http.server
import socketserver
import os
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

def main():
    # 確保在正確的目錄
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        print(f"=== 前端服務器啟動 ===")
        print(f"訪問 http://localhost:{PORT} 開始使用")
        print(f"提供目錄: {DIRECTORY}")
        print("按 Ctrl+C 停止服務器")
        print("=" * 30)
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服務器已停止")

if __name__ == "__main__":
    main()