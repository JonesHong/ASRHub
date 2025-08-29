from pystorex import EffectsModule, LoggerMiddleware, StoreModule, create_store
from src.config.manager import ConfigManager
from src.store.sessions.sessions_reducer import sessions_reducer
# StoreConfig import removed - not needed
from src.core.audio_queue_manager import AudioQueueManager
from src.utils.logger import logger
import os

config_manager = ConfigManager()
audio_queue_manager = AudioQueueManager()

# 創建Store
store = create_store()

# store.apply_middleware(LoggerMiddleware)
# 註冊Reducer
store = StoreModule.register_root({"sessions": sessions_reducer}, store)

# 註冊Effects - 使用統一的 SessionEffects
logger.info("🎯 Using unified SessionEffects with timestamp support")
from src.store.sessions.sessions_effect import SessionEffects
effects = SessionEffects(store=store)

# 註冊所有 effects
store = EffectsModule.register_root([
    SessionEffects(store=store)
], store)

# 匯出 store 作為 main_store
main_store = store
