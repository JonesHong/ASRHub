"""錄音服務

從 AudioQueueManager 取得音訊 chunks 並寫入本地檔案。
"""

from .recording import recording, Recording

__all__ = ['recording', 'Recording']