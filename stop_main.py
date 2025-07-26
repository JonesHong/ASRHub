#!/usr/bin/env python3
"""
停止所有 ASR Hub 相關服務
使用 ConfigManager 讀取配置並終止使用這些端口的進程
"""

import os
import sys
import subprocess
import signal
from pathlib import Path
from typing import List, Set
from src.config.manager import ConfigManager
from src.utils.logger import get_logger

logger = get_logger("stop_main")


def extract_ports_from_config() -> Set[int]:
    """從 ConfigManager 中提取所有端口號"""
    ports = set()
    ports.add(8082)
    try:
        # 獲取 ConfigManager 單例
        config = ConfigManager()
        
        # HTTP SSE (總是啟用)
        port = config.api.http_sse.port
        if port:
            ports.add(port)
            logger.info(f"找到 HTTP SSE 端口: {port}")
        
        # WebSocket
        if config.api.websocket.enabled:
            port = config.api.websocket.port
            if port:
                ports.add(port)
                logger.info(f"找到 WebSocket 端口: {port}")
        
        # Socket.IO
        if config.api.socketio.enabled:
            port = config.api.socketio.port
            if port:
                ports.add(port)
                logger.info(f"找到 Socket.IO 端口: {port}")
        
        # gRPC
        if config.api.grpc.enabled:
            port = config.api.grpc.port
            if port:
                ports.add(port)
                logger.info(f"找到 gRPC 端口: {port}")
        
        # Redis
        if config.api.redis.enabled:
            port = config.api.redis.port
            if port:
                ports.add(port)
                logger.info(f"找到 Redis 端口: {port}")
                
    except Exception as e:
        logger.error(f"從 ConfigManager 提取端口失敗: {e}")
        # 使用預設端口
        logger.info("使用預設端口配置")
        ports.update({8000, 8765, 8766})
    
    return ports


def find_process_by_port(port: int) -> List[int]:
    """使用 lsof 查找使用指定端口的進程 PID"""
    pids = []
    try:
        # 使用 lsof 查找監聽指定端口的進程
        cmd = f"lsof -i :{port} -t"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            # lsof -t 直接返回 PID，可能有多個
            pids = [int(pid) for pid in result.stdout.strip().split('\n') if pid]
            logger.info(f"端口 {port} 被進程使用: PIDs = {pids}")
        else:
            logger.info(f"端口 {port} 未被使用")
            
    except Exception as e:
        logger.error(f"查找端口 {port} 的進程失敗: {e}")
    
    return pids


def kill_process(pid: int, force: bool = True) -> bool:
    """終止指定的進程"""
    try:
        if force:
            # 使用 SIGKILL (kill -9)
            os.kill(pid, signal.SIGKILL)
            logger.info(f"強制終止進程 {pid} (SIGKILL)")
        else:
            # 使用 SIGTERM (正常終止)
            os.kill(pid, signal.SIGTERM)
            logger.info(f"正常終止進程 {pid} (SIGTERM)")
        return True
    except ProcessLookupError:
        logger.warning(f"進程 {pid} 不存在")
        return False
    except PermissionError:
        logger.error(f"沒有權限終止進程 {pid}")
        return False
    except Exception as e:
        logger.error(f"終止進程 {pid} 失敗: {e}")
        return False


def kill_processes_by_name(process_names: List[str]):
    """根據進程名稱終止進程"""
    for name in process_names:
        try:
            # 使用 pkill 終止進程
            cmd = f"pkill -f '{name}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"終止了包含 '{name}' 的進程")
            elif result.returncode == 1:
                logger.info(f"沒有找到包含 '{name}' 的進程")
            else:
                logger.warning(f"pkill '{name}' 返回碼: {result.returncode}")
                
        except Exception as e:
            logger.error(f"終止進程 '{name}' 失敗: {e}")


def main():
    """主函數"""
    logger.info("=" * 50)
    logger.info("開始停止 ASR Hub 服務")
    logger.info("=" * 50)
    
    # 從 ConfigManager 提取端口
    ports = extract_ports_from_config()
    
    # 額外檢查的端口（前端服務器等）
    extra_ports = {8080, 8081, 8082}  # 前端服務器可能使用的端口
    ports.update(extra_ports)
    
    logger.info(f"將檢查以下端口: {sorted(ports)}")
    
    # 收集所有需要終止的 PID
    all_pids = set()
    for port in ports:
        pids = find_process_by_port(port)
        all_pids.update(pids)
    
    # 終止所有找到的進程
    if all_pids:
        logger.info(f"準備終止 {len(all_pids)} 個進程: {sorted(all_pids)}")
        killed_count = 0
        for pid in all_pids:
            if kill_process(pid, force=True):
                killed_count += 1
        
        logger.info(f"成功終止 {killed_count}/{len(all_pids)} 個進程")
    else:
        logger.info("沒有找到需要終止的進程")
    
    # 額外終止可能的相關進程
    logger.info("檢查其他相關進程...")
    related_processes = [
        "main.py",
        "asr_hub.py",
        "frontend_server.py",
        "src.core.asr_hub"
    ]
    kill_processes_by_name(related_processes)
    
    logger.info("=" * 50)
    logger.info("ASR Hub 服務停止完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()