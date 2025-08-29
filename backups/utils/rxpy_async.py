"""
處理 RxPY 與 async 函數整合的工具模組

提供簡潔、安全的方式將 async 函數整合到 RxPY pipeline 中，
避免 threading 和 event loop 的複雜性問題。
"""

import asyncio
from typing import Callable, Any, Optional, Union, List, Tuple
import reactivex as rx
import reactivex.operators as ops


def async_flat_map(async_fn: Callable) -> Callable:
    """
    將 async 函數包裝成可用於 RxPY pipe 的 operator。
    
    這個 operator 能夠：
    1. 安全地在當前 event loop 執行 async 函數
    2. 智能處理不同類型的返回值
    3. 避免 threading 和 event loop 的複雜性
    4. 防範錯誤的 Action 對象使用
    
    Args:
        async_fn: async 函數，簽名為 (value) -> awaitable[T | Iterable[T] | None]
    
    Returns:
        可用於 pipe 的 operator 函數
    
    使用範例:
        >>> action_stream.pipe(
        ...     ops.filter(lambda a: a.type == create_session.type),
        ...     async_flat_map(self._handle_create_session),
        ...     ops.do_action(lambda x: print(f"Created: {x}"))
        ... )
    
    返回值處理:
        - None: 不發射任何值（用於 side effects only）
        - list/tuple: 展開為多個 on_next 事件
        - 其他: 作為單一 on_next 事件發射
    """
    def _operator(source):
        def create_future(value):
            """智能創建 Future，處理有無 event loop 的情況"""
            # 防範措施：確保 value 不會錯誤地調用 pipe 方法
            if hasattr(value, 'pipe') and not hasattr(value, 'payload'):
                # 這是一個 Observable，不是 Action - 可能是錯誤的使用方式
                import logging
                logging.warning(f"Potentially incorrect usage: received Observable instead of Action in async_flat_map: {type(value)}")
            elif hasattr(value, 'pipe') and hasattr(value, 'payload'):
                # 這可能是混合對象，需要記錄以便調試
                import logging 
                logging.debug(f"Mixed object type in async_flat_map: {type(value)}")
            
            # 正常處理邏輯
            try:
                # 嘗試獲取當前的 event loop
                loop = asyncio.get_running_loop()
                # 如果有 event loop，使用 create_task
                return asyncio.create_task(async_fn(value))
            except RuntimeError:
                # 沒有運行中的 event loop，創建新的或使用 asyncio.run
                try:
                    # 嘗試獲取現有的 loop（可能未運行）
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 不應該到這裡，但以防萬一
                        return asyncio.create_task(async_fn(value))
                    else:
                        # Loop 存在但未運行，使用 run_coroutine_threadsafe
                        import concurrent.futures
                        future = concurrent.futures.Future()
                        
                        async def wrapper():
                            try:
                                result = await async_fn(value)
                                future.set_result(result)
                            except Exception as e:
                                future.set_exception(e)
                        
                        # 在新的事件循環中運行
                        import threading
                        def run_in_new_loop():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                new_loop.run_until_complete(wrapper())
                            finally:
                                new_loop.close()
                        
                        thread = threading.Thread(target=run_in_new_loop, daemon=True)
                        thread.start()
                        return future
                except:
                    # 最後的備用方案：使用 asyncio.run
                    import concurrent.futures
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    return executor.submit(asyncio.run, async_fn(value))
        
        return source.pipe(
            # 將 async_fn(value) 轉換為 Observable
            # 智能處理 event loop 的情況
            ops.flat_map(lambda v: rx.from_future(create_future(v))),
            
            # 統一處理不同類型的返回值
            ops.flat_map(lambda res:
                rx.empty() if res is None else  # None -> 不發射
                rx.from_iterable(res) if isinstance(res, (list, tuple)) else  # list/tuple -> 展開
                rx.of(res)  # 其他 -> 單值
            )
        )
    return _operator


def async_map(async_fn: Callable) -> Callable:
    """
    類似 async_flat_map，但不展開 list/tuple。
    
    適用於當你希望保留 list/tuple 作為單一值的情況。
    
    Args:
        async_fn: async 函數
    
    Returns:
        可用於 pipe 的 operator 函數
    """
    def _operator(source):
        def create_future(value):
            """智能創建 Future，處理有無 event loop 的情況"""
            try:
                loop = asyncio.get_running_loop()
                return asyncio.create_task(async_fn(value))
            except RuntimeError:
                # 沒有運行中的 event loop，使用線程池執行
                import concurrent.futures
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                return executor.submit(asyncio.run, async_fn(value))
        
        return source.pipe(
            ops.flat_map(lambda v: rx.from_future(create_future(v))),
            ops.filter(lambda res: res is not None)  # 過濾 None
        )
    return _operator


def async_do_action(async_fn: Callable) -> Callable:
    """
    執行 async side effect，但不改變 stream 的值。
    
    類似於 ops.do_action，但支援 async 函數。
    
    Args:
        async_fn: async 函數（僅用於 side effects）
    
    Returns:
        可用於 pipe 的 operator 函數
    """
    def _operator(source):
        def _do_async(value):
            async def _wrapper():
                await async_fn(value)
                return value  # 保持原值不變
            
            # 智能處理 event loop
            try:
                loop = asyncio.get_running_loop()
                return rx.from_future(asyncio.create_task(_wrapper()))
            except RuntimeError:
                # 沒有運行中的 event loop，使用線程池執行
                import concurrent.futures
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                return rx.from_future(executor.submit(asyncio.run, _wrapper()))
        
        return source.pipe(
            ops.flat_map(_do_async)
        )
    return _operator


def with_async_error_handler(
    async_fn: Callable,
    error_handler: Optional[Callable[[Exception], Any]] = None
) -> Callable:
    """
    包裝 async 函數，添加錯誤處理。
    
    Args:
        async_fn: async 函數
        error_handler: 錯誤處理函數，接收 Exception 並返回替代值
    
    Returns:
        包裝後的 async 函數
    """
    async def _wrapper(*args, **kwargs):
        try:
            return await async_fn(*args, **kwargs)
        except Exception as e:
            if error_handler:
                return error_handler(e)
            else:
                # 預設：記錄錯誤並返回 None
                import logging
                logging.error(f"Error in async function: {e}", exc_info=True)
                return None
    
    return _wrapper



# 為了完全向後相容，保留舊的 async_flat_map 簽名
# （雖然新版本已經是正確的實現）
__all__ = [
    'async_flat_map',
    'async_map',
    'async_do_action',
    'with_async_error_handler',
]