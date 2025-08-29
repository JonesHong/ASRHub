"""視覺化基礎類別

定義所有視覺化面板的基礎介面。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Tuple
import numpy as np
import gradio as gr


class VisualizationPanel(ABC):
    """視覺化面板基礎類別。
    
    所有面板都必須實現這個介面，確保可以被主視覺化器組合使用。
    """
    
    def __init__(self, title: str = "Panel"):
        """初始化面板。
        
        Args:
            title: 面板標題
        """
        self.title = title
        self._data_buffer = []
        self._max_buffer_size = 1000
        
    @abstractmethod
    def create_component(self) -> gr.components.Component:
        """創建 Gradio 組件。
        
        Returns:
            Gradio 組件實例
        """
        pass
    
    @abstractmethod
    def update(self, data: Any) -> Any:
        """更新面板顯示。
        
        Args:
            data: 要顯示的資料
            
        Returns:
            更新後的顯示內容
        """
        pass
    
    @abstractmethod
    def clear(self):
        """清空面板資料。"""
        pass
    
    def add_data(self, data: Any):
        """添加資料到緩衝區。
        
        Args:
            data: 要添加的資料
        """
        self._data_buffer.append(data)
        
        # 限制緩衝區大小
        if len(self._data_buffer) > self._max_buffer_size:
            self._data_buffer = self._data_buffer[-self._max_buffer_size:]
    
    def get_buffer(self) -> List[Any]:
        """取得資料緩衝區。
        
        Returns:
            資料緩衝區列表
        """
        return self._data_buffer
    
    def set_buffer_size(self, size: int):
        """設定緩衝區大小。
        
        Args:
            size: 最大緩衝區大小
        """
        self._max_buffer_size = size
        
        # 調整現有緩衝區
        if len(self._data_buffer) > size:
            self._data_buffer = self._data_buffer[-size:]