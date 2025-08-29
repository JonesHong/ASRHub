"""
SSE Event Stream using PyStoreX Selectors
使用 PyStoreX Selector 模式實現響應式事件流
"""

import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, Any, Tuple
from datetime import datetime
from queue import Queue
from threading import Thread

from src.utils.logger import logger
from src.store.sessions.sessions_selectors import (
    get_session,
    get_session_fsm_state,
    get_session_transcription,
    get_session_error
)


class SelectorBasedEventStream:
    """
    基於 PyStoreX Selector 的 SSE 事件流
    
    取代輪詢機制，使用響應式訂閱
    """
    def __init__(self, store, session_id: str):
        """
        初始化事件流
        
        Args:
            store: PyStoreX store 實例
            session_id: Session ID
        """
        self.store = store
        self.session_id = session_id
        self.event_queue = asyncio.Queue()
        self.subscriptions = []
        self.running = False
        
        # 創建 session-specific selectors
        self.session_selector = get_session(session_id)
        self.fsm_state_selector = get_session_fsm_state(session_id)
        self.transcription_selector = get_session_transcription(session_id)
        self.error_selector = get_session_error(session_id)
        
        logger.info(f"📡 Initialized selector-based event stream for session: {session_id[:8]}...")
    
    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        格式化 SSE 事件
        
        Args:
            event_type: 事件類型
            data: 事件數據
            
        Returns:
            格式化的 SSE 事件字符串
        """
        # Convert any Map objects to regular dicts
        def convert_to_serializable(obj):
            if hasattr(obj, 'to_dict'):
                return obj.to_dict()
            elif hasattr(obj, '_asdict'):
                return obj._asdict()
            elif hasattr(obj, '__dict__'):
                return obj.__dict__
            else:
                return obj
        
        # Recursively convert the data
        if isinstance(data, dict):
            serializable_data = {k: convert_to_serializable(v) for k, v in data.items()}
        else:
            serializable_data = convert_to_serializable(data)
            
        event = f"event: {event_type}\n"
        event += f"data: {json.dumps(serializable_data, ensure_ascii=False, default=str)}\n\n"
        return event
    
    def _handle_state_change(self, change_type: str):
        """
        創建狀態變化處理器
        
        Args:
            change_type: 變化類型
        """
        def handler(change: Tuple[Any, Any]):
            """處理狀態變化"""
            old_value, new_value = change
            
            # 跳過初始訂閱
            if old_value is None:
                return
            
            # 創建事件
            event_data = {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "old_value": old_value,
                "new_value": new_value
            }
            
            # 根據變化類型決定事件名稱
            if change_type == "fsm_state":
                event_name = "fsm_state_changed"
                event_data = {
                    "session_id": self.session_id,
                    "from": str(old_value) if old_value else None,
                    "to": str(new_value) if new_value else None,
                    "timestamp": datetime.now().isoformat()
                }
            elif change_type == "transcription":
                event_name = "transcription"
                event_data = new_value if new_value else {}
            elif change_type == "error":
                event_name = "error"
                event_data = new_value if new_value else {}
            elif change_type == "session":
                # 檢測 session 整體變化
                event_name = "session_updated"
                # Convert Map objects to dict for JSON serialization
                try:
                    if hasattr(new_value, 'to_dict'):
                        event_data = new_value.to_dict()
                    elif hasattr(new_value, '_asdict'):
                        event_data = new_value._asdict()
                    else:
                        event_data = dict(new_value) if new_value else {}
                except:
                    event_data = {"session_id": self.session_id}
                    
                # 分析具體變化
                if isinstance(old_value, dict) and isinstance(new_value, dict):
                    changes = []
                    for key in new_value:
                        if old_value.get(key) != new_value.get(key):
                            changes.append(key)
                    event_data["changed_fields"] = changes
            else:
                event_name = f"{change_type}_changed"
            
            # 將事件放入佇列（同步）
            try:
                # 使用 thread-safe queue 橋接同步和異步
                asyncio.run_coroutine_threadsafe(
                    self.event_queue.put((event_name, event_data)),
                    asyncio.get_event_loop()
                )
            except Exception as e:
                logger.error(f"Failed to queue event: {e}")
        
        return handler
    
    def start_subscriptions(self):
        """啟動所有訂閱"""
        if self.running:
            return
        
        self.running = True
        
        # 訂閱 session 整體變化
        session_sub = self.store.select(self.session_selector).subscribe(
            self._handle_state_change("session")
        )
        self.subscriptions.append(session_sub)
        
        # 訂閱 FSM 狀態變化
        fsm_sub = self.store.select(self.fsm_state_selector).subscribe(
            self._handle_state_change("fsm_state")
        )
        self.subscriptions.append(fsm_sub)
        
        # 訂閱轉譯結果變化
        trans_sub = self.store.select(self.transcription_selector).subscribe(
            self._handle_state_change("transcription")
        )
        self.subscriptions.append(trans_sub)
        
        # 訂閱錯誤變化
        error_sub = self.store.select(self.error_selector).subscribe(
            self._handle_state_change("error")
        )
        self.subscriptions.append(error_sub)
        
        logger.info(f"✅ Started {len(self.subscriptions)} subscriptions for session: {self.session_id[:8]}...")
    
    def stop_subscriptions(self):
        """停止所有訂閱"""
        if not self.running:
            return
        
        self.running = False
        
        # 取消所有訂閱
        for subscription in self.subscriptions:
            try:
                subscription.dispose()
            except Exception as e:
                logger.error(f"Failed to dispose subscription: {e}")
        
        self.subscriptions.clear()
        logger.info(f"🛑 Stopped all subscriptions for session: {self.session_id[:8]}...")
    
    async def create_event_stream(self) -> AsyncGenerator[str, None]:
        """
        創建 SSE 事件流
        
        Yields:
            格式化的 SSE 事件
        """
        try:
            # 啟動訂閱
            self.start_subscriptions()
            
            # 發送連接成功事件
            yield self._format_sse_event("connected", {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "method": "selector-based"
            })
            
            # 心跳任務
            async def heartbeat():
                while self.running:
                    await asyncio.sleep(30)  # 每30秒發送心跳
                    if self.running:
                        await self.event_queue.put(("heartbeat", {
                            "timestamp": datetime.now().isoformat()
                        }))
            
            heartbeat_task = asyncio.create_task(heartbeat())
            
            # 事件循環
            while self.running:
                try:
                    # 等待事件（帶超時）
                    event_type, event_data = await asyncio.wait_for(
                        self.event_queue.get(),
                        timeout=1.0
                    )
                    
                    # 發送事件
                    yield self._format_sse_event(event_type, event_data)
                    
                    # 檢查是否是終止事件
                    if event_type == "session_destroyed":
                        break
                    
                except asyncio.TimeoutError:
                    # 超時正常，繼續循環
                    continue
                except Exception as e:
                    logger.error(f"Error in event stream: {e}")
                    yield self._format_sse_event("error", {
                        "message": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    break
            
            # 取消心跳任務
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            
        finally:
            # 停止訂閱
            self.stop_subscriptions()
            
            # 發送斷開事件
            yield self._format_sse_event("disconnected", {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"📡 Event stream closed for session: {self.session_id[:8]}...")


def create_selector_event_stream(store, session_id: str) -> AsyncGenerator[str, None]:
    """
    工廠函數：創建基於 selector 的事件流
    
    Args:
        store: PyStoreX store 實例
        session_id: Session ID
        
    Returns:
        SSE 事件流生成器
    """
    stream = SelectorBasedEventStream(store, session_id)
    return stream.create_event_stream()