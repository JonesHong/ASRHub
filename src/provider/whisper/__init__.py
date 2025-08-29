"""Whisper ASR Provider Module"""

# 優先導入 FasterWhisperProvider
try:
    from .faster_whisper_provider import FasterWhisperProvider, faster_whisper_provider
    __all__ = ['FasterWhisperProvider', 'faster_whisper_provider']
except ImportError:
    pass

# 嘗試導入原始 WhisperProvider（需要 openai-whisper）
try:
    from .whisper_provider import WhisperProvider, whisper_provider
    if '__all__' not in locals():
        __all__ = []
    __all__.extend(['WhisperProvider', 'whisper_provider'])
except ImportError:
    pass

# 如果都沒有成功導入，至少保持 __all__ 存在
if '__all__' not in locals():
    __all__ = []