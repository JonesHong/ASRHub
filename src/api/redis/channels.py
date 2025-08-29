from pydantic import BaseModel
from src.interface.action import InputAction, OutputAction


def action2channel(action: str) -> str:
    """
    將 Action 名稱轉換為 Redis 頻道名稱
    例如: create_session -> create:session
    Args:
        action (str): Action 名稱
    Returns:
        str: Redis 頻道名稱
    """
    return action.replace("_", ":").lower()


def session2channel(channel: str, session_id: str) -> str:
    """
    將 Session ID 與頻道名稱結合
    例如: create:session:12345
    Args:
        channel (str): 頻道名稱
        session_id (str): Session ID
    Returns:
        str: 完整的 Redis 頻道名稱
    """
    return f"{channel}:{session_id}"


class RedisChannels:
    """Redis 全頻道定義"""

    # Subscribe Channels
    REQUEST_CREATE_SESSION = "request:" + action2channel(InputAction.CREATE_SESSION) 
    REQUEST_LISTEN_REQUESTED = "request:" + action2channel(InputAction.START_LISTENING)
    REQUEST_EMIT_AUDIO_CHUNK = "request:" + action2channel(InputAction.EMIT_AUDIO_CHUNK)
    
    # Publish Channels
    RESPONSE_CREATE_SESSION = "response:" + action2channel(OutputAction.CREATE_SESSION)
    RESPONSE_EMIT_AUDIO_CHUNK = "response:" + action2channel(OutputAction.EMIT_AUDIO_CHUNK)
    RESPONSE_TRANSCRIBE_DONE = "response:" + action2channel(OutputAction.TRANSCRIBE_DONE)
    RESPONSE_DELETE_SESSION = "response:" + action2channel(OutputAction.DELETE_SESSION)


channels = [
    "request:" + action2channel(InputAction.CREATE_SESSION),
    "request:" + action2channel(InputAction.EMIT_AUDIO_CHUNK),
]


class CreateSessionInput(BaseModel):
    strategy: str
    request_id: str


class CreateSessionOutput(BaseModel):
    session_id: str
