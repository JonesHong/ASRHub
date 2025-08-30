"""Denoise Service Module - 條件式載入

只在服務啟用時才載入 DeepFilterNet。
"""

from src.service.service_loader import lazy_load_service

# 使用延遲載入 - 只在第一次使用時檢查配置並載入
denoiser = lazy_load_service(
    service_path='src.service.denoise.deepfilternet_denoiser',
    class_name='DeepFilterNetDenoiser',
    instance_name='denoiser',
    config_path='services.denoise'
)

__all__ = ['denoiser']