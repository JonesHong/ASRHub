# id_provider.py
import uuid

try:
    from uuid6 import uuid7 as _uuid7  # 有安裝就用 v7
except ImportError:
    _uuid7 = None

def new_id(id: str | None = None) -> str:
    """回傳現有 id；若沒有就產生一個（優先 UUIDv7，否則 v4）。"""
    if id:                     # 有傳入就沿用
        return id
    return str(_uuid7()) if _uuid7 else str(uuid.uuid4())
