"""
處理 RxPY 與 async 函數整合的工具模組
"""

import asyncio
from typing import Callable, Any
from reactivex import Observable, empty
from reactivex import operators as ops
import threading


class AsyncToObservable:
    """將 async 函數轉換為 Observable 的工具類"""
    
    @staticmethod
    def from_async(async_func: Callable, *args, **kwargs) -> Observable:
        """
        將 async 函數轉換為 Observable
        
        Args:
            async_func: async 函數
            *args: 位置參數
            **kwargs: 關鍵字參數
            
        Returns:
            Observable 物件
        """
        def create(observer, scheduler=None):
            """創建 Observable"""
            
            # 獲取或創建事件循環
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except RuntimeError:
                # 創建新的事件循環
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 在事件循環中執行 async 函數
            def run_async():
                try:
                    # 創建協程
                    coro = async_func(*args, **kwargs)
                    
                    # 如果事件循環正在運行，使用 ensure_future
                    if loop.is_running():
                        future = asyncio.ensure_future(coro, loop=loop)
                    else:
                        # 否則使用 run_until_complete
                        future = loop.create_task(coro)
                        loop.run_until_complete(future)
                    
                    # 獲取結果
                    result = future.result() if not loop.is_running() else None
                    
                    # 處理結果
                    if result is None or result == []:
                        # 不發射任何值，直接完成
                        observer.on_completed()
                    elif isinstance(result, list):
                        # 發射列表中的每個值
                        for item in result:
                            observer.on_next(item)
                        observer.on_completed()
                    else:
                        # 發射單個值
                        observer.on_next(result)
                        observer.on_completed()
                        
                except Exception as e:
                    observer.on_error(e)
            
            # 在獨立執行緒中執行，避免阻塞
            thread = threading.Thread(target=run_async)
            thread.daemon = True
            thread.start()
            
            # 返回 dispose 函數
            return lambda: None
        
        return Observable(create)
    
    @staticmethod
    def run_async_in_thread(async_func: Callable, *args, **kwargs) -> Any:
        """
        在新執行緒中運行 async 函數
        
        Args:
            async_func: async 函數
            *args: 位置參數
            **kwargs: 關鍵字參數
            
        Returns:
            執行結果
        """
        result = [None]
        exception = [None]
        
        def run():
            try:
                # 創建新的事件循環
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 執行 async 函數
                result[0] = loop.run_until_complete(async_func(*args, **kwargs))
                
                # 關閉事件循環
                loop.close()
            except Exception as e:
                exception[0] = e
        
        # 在新執行緒中執行
        thread = threading.Thread(target=run)
        thread.start()
        thread.join()  # 等待執行完成
        
        if exception[0]:
            raise exception[0]
        
        return result[0]


def async_flat_map(async_func: Callable) -> Callable:
    """
    裝飾器：將 async 函數包裝為可用於 flat_map 的函數
    
    使用方式：
        ops.flat_map(async_flat_map(self._handle_create_session))
    
    Args:
        async_func: async 函數
        
    Returns:
        返回一個函數，該函數接受參數並返回 Observable
    """
    def wrapper(*args, **kwargs):
        # 使用 AsyncToObservable 轉換 async 函數
        return AsyncToObservable.from_async(async_func, *args, **kwargs).pipe(
            ops.default_if_empty([]),  # 如果沒有值，返回空列表
            ops.flat_map(lambda x: [] if x == [] else [x])  # 確保返回正確的格式
        )
    
    return wrapper