from pystorex import EffectsModule, LoggerMiddleware, StoreModule, create_store
from src.config.manager import ConfigManager
from src.store.sessions import sessions_reducer
from src.store.sessions.sessions_effects import SessionEffects
from src.store.store_config import StoreConfig, get_hub_store, configure_global_store
from src.core.audio_queue_manager import AudioQueueManager
from src.utils.logger import logger

config_manager = ConfigManager()
audio_queue_manager = AudioQueueManager()


# 創建Store
store = create_store()


# store.apply_middleware(LoggerMiddleware)
# 註冊Reducer
store = StoreModule.register_root({"sessions": sessions_reducer}, store)

# 註冊Effects
store = EffectsModule.register_root(
    SessionEffects(
        store=store,
    ),
    store,
)
