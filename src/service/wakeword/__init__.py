"""Wakeword detection service module

Module-level singleton instance for OpenWakeWord service.
"""

# 匯出 OpenWakeword 服務
from .openwakeword import OpenWakeword, openwakeword

__all__ = ['OpenWakeword', 'openwakeword']