# src/api/redis/server.py
from redis_toolkit import RedisToolkit, RedisConnectionConfig

from src.api.redis import channels
from src.interface.action import InputAction
from src.config.manager import ConfigManager

config_manager = ConfigManager()
redis_config = config_manager.api.redis

redis_client: RedisToolkit = None
redis_subscriber: RedisToolkit = None
redis_client.publisher
def message_handler(message):
    """處理從 Redis 訂閱收到的消息"""
    from src.utils.logger import logger
    import json
    
    try:
        # 解析消息
        data = json.loads(message['data']) if isinstance(message['data'], str) else message['data']
        channel = message['channel']
        
        logger.debug(f"Received message on channel {channel}: {data}")
        
        # 根據頻道處理不同的消息
        if 'audio_chunk' in channel or 'emit:audio' in channel:
            # 音訊塊必須包含元資料
            if 'metadata' not in data:
                logger.error("Audio chunk missing metadata! Client must provide: sample_rate, channels, format")
                logger.error(f"Received data keys: {data.keys()}")
                return
            
            metadata = data['metadata']
            logger.info(f"Audio metadata from Redis client: {metadata.get('sample_rate')}Hz, "
                       f"{metadata.get('channels')}ch, {metadata.get('format')}")
            
            # 將消息轉發到 store
            from src.store.main_store import store
            from src.store.sessions.sessions_action import receive_audio_chunk
            
            store.dispatch(receive_audio_chunk({
                'session_id': data.get('session_id'),
                'audio_data': data.get('audio_data'),
                'metadata': metadata  # 傳遞音訊元資料
            }))
        
        elif 'create:session' in channel:
            # 處理創建會話請求
            from src.store.main_store import store
            from src.store.sessions.sessions_action import create_session
            
            store.dispatch(create_session({
                'strategy': data.get('strategy', 'realtime'),
                'request_id': data.get('request_id')
            }))
            
    except Exception as e:
        logger.error(f"Error handling Redis message: {e}")

def initialize():
    """初始化 Redis 客戶端和訂閱者"""
    global redis_client, redis_subscriber
    config = None

    config = RedisConnectionConfig(
        host=redis_config.host,
        port=redis_config.port,
        db=redis_config.db,
        password=redis_config.password,
    )
    redis_client = RedisToolkit(config=config, is_logger_info=False)

    redis_subscriber = RedisToolkit(
        channels=channels,
        message_handler=message_handler,
        config=config,
        is_logger_info=False,
    )


if redis_config.enabled:
    initialize()


if __name__ == "__main__":
    initialize()
