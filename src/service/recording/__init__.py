"""Recording Service Module - 條件式載入

只在服務啟用時才載入 Recording。
"""

from src.service.service_loader import lazy_load_service

# 使用延遲載入 - 只在第一次使用時檢查配置並載入
recording = lazy_load_service(
    service_path='src.service.recording.recording',
    class_name='Recording',
    instance_name='recording',
    config_path='services.recording'
)

__all__ = ['recording']