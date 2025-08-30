"""VAD Service Module - 條件式載入

只在服務啟用時才載入 SileroVAD。
"""

from src.service.service_loader import lazy_load_service

# 使用延遲載入 - 只在第一次使用時檢查配置並載入
silero_vad = lazy_load_service(
    service_path='src.service.vad.silero_vad',
    class_name='SileroVAD',
    instance_name='silero_vad',
    config_path='services.vad'
)

__all__ = ['silero_vad']