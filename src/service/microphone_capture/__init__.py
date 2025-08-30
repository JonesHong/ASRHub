"""Microphone Capture Service Module - 條件式載入

只在服務啟用時才載入 MicrophoneCapture。
"""

from src.service.service_loader import lazy_load_service

# 使用延遲載入 - 只在第一次使用時檢查配置並載入
microphone_capture = lazy_load_service(
    service_path='src.service.microphone_capture.microphone_capture',
    class_name='MicrophoneCapture',
    instance_name='microphone_capture',
    config_path='services.microphone'
)

__all__ = ['microphone_capture']