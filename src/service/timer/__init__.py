"""Timer Service Module - 條件式載入

只在服務啟用時才載入 TimerService。
"""

from src.service.service_loader import lazy_load_service

# 使用延遲載入 - 只在第一次使用時檢查配置並載入
timer_service = lazy_load_service(
    service_path='src.service.timer.timer_service',
    class_name='TimerService',
    instance_name='timer_service',
    config_path='services.timer'
)

__all__ = ['timer_service']