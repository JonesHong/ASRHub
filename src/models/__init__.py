"""
ASR Hub 資料模型
"""

# 轉譯相關模型
from .transcript import (
    TranscriptResult,
    TranscriptSegment,
    TranscriptAlternative,
    TranscriptStatus,
    Word
)

__all__ = [
    # 轉譯模型
    "TranscriptResult",
    "TranscriptSegment", 
    "TranscriptAlternative",
    "TranscriptStatus",
    "Word"
]