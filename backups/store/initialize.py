"""
ASRHub Store 初始化模組
簡化版初始化流程，移除過度封裝
"""

import asyncio
from typing import Optional, Dict, Callable

from src.config.manager import ConfigManager
from src.store.store_config import (
    StoreConfig,
    get_hub_store,
    configure_global_store
)
from src.core.audio_queue_manager import AudioQueueManager
from src.utils.logger import logger

config_manager = ConfigManager()
def create_operator_factories() -> Dict[str, Callable]:
    """
    創建 Operator 工廠函數字典
    
    Returns:
        工廠函數字典
    """
    factories = {}
    
    # OpenWakeWord
    def create_wakeword():
        from src.operators.wakeword.openwakeword import OpenWakeWordOperator
        return OpenWakeWordOperator()
    
    # Silero VAD
    def create_vad():
        from src.operators.vad.silero_vad import SileroVADOperator
        return SileroVADOperator()
    
    # Recording
    def create_recording():
        from src.operators.recording.recording_operator import RecordingOperator
        return RecordingOperator()
    
    # 注意: 格式轉換已經移到 AudioConverter，不再使用 Operator 模式
    # 如果需要格式轉換，請直接使用 src.audio.converter.AudioConverter
    
    factories['wakeword'] = create_wakeword
    factories['vad'] = create_vad
    factories['recording'] = create_recording
    # factories['format_conversion'] = create_format_conversion  # 已移除
    
    return factories


def create_provider_factories() -> Dict[str, Callable]:
    """
    創建 Provider 工廠函數字典
    
    Returns:
        工廠函數字典
    """
    factories = {}
    
    # Whisper (已完成模組級變數重構)
    def create_whisper():
        from src.providers.whisper.provider import WhisperProvider
        return WhisperProvider()  # 已移除依賴注入
    
    factories['whisper'] = create_whisper
    
    # 未來可添加其他 providers
    # factories['funasr'] = create_funasr
    
    return factories


async def initialize_asr_hub_store(
    provider_manager=None,
    metrics_client=None,
    max_sessions: int = 1000
):
    """
    初始化 ASRHub Store
    
    簡化版初始化流程：
    1. 創建 AudioQueueManager
    2. 創建工廠函數
    3. 配置並獲取 Store
    
    Args:
        provider_manager: Provider 管理器（可選）
        metrics_client: 指標客戶端（可選）
        max_sessions: 最大 session 數量
    
    Returns:
        配置好的 Store 實例
    """
    logger.info("初始化 ASRHub Store")
    
    # 1. 創建 AudioQueueManager
    logger.info("[1/3] 創建 AudioQueueManager...")
    audio_queue_manager = AudioQueueManager()
    
    # 2. 創建工廠函數
    logger.info("[2/3] 創建工廠函數...")
    operator_factories = create_operator_factories()
    provider_factories = create_provider_factories()
    
    # 3. 配置並獲取 Store
    logger.info("[3/3] 初始化 Store...")
    config = StoreConfig(
        audio_queue_manager=audio_queue_manager,
        provider_manager=provider_manager,
        metrics_client=metrics_client,
        operator_factories=operator_factories,
        provider_factories=provider_factories
    )
    
    # 使用新的 configure_global_store（會自動設置工廠函數）
    store = configure_global_store(
        metrics_client=metrics_client,
        provider_manager=provider_manager,
        audio_queue_manager=audio_queue_manager
    )
    
    # 設置工廠函數到 hub store
    hub_store = get_hub_store()
    hub_store.config.operator_factories = operator_factories
    hub_store.config.provider_factories = provider_factories
    
    # 如果 Store 已初始化，更新 Effects
    if hub_store._session_effects:
        hub_store._session_effects.operator_factories = operator_factories
        hub_store._session_effects.provider_factories = provider_factories
    
    logger.block("ASRHub Store 初始化完成",[
        f"  - {len(operator_factories)} Operator factories",
        f"  - {len(provider_factories)} Provider factories",
        f"  - Max sessions: {max_sessions}"
    ])
    
    return store



async def preload_models():
    """
    預載入 AI 模型到類別層級（可選）
    
    這個函數可以在系統啟動時調用，預先載入所有需要的 AI 模型，
    避免首次使用時的延遲。
    """
    logger.info("預載入 AI 模型...")
    
    try:
        # 動態導入以避免循環依賴
        from src.operators.vad.silero_vad import SileroVADOperator
        from src.operators.wakeword.openwakeword import OpenWakeWordOperator
        
        # 並行載入所有模型
        await asyncio.gather(
            SileroVADOperator.preload_model() if hasattr(SileroVADOperator, 'preload_model') else asyncio.sleep(0),
            OpenWakeWordOperator.preload_model() if hasattr(OpenWakeWordOperator, 'preload_model') else asyncio.sleep(0),
            # 可以添加其他模型的預載入
        )
        
        logger.info("✓ 所有 AI 模型已預載入")
        
    except Exception as e:
        logger.warning(f"模型預載入失敗（非致命錯誤）: {e}")


def get_store_status() -> dict:
    """
    獲取 Store 狀態資訊
    
    Returns:
        包含 Store 狀態的字典
    """
    from src.store.store_config import get_global_store
    
    try:
        store = get_global_store()
        state = store.state
        
        return {
            "initialized": True,
            "sessions_count": len(state.get("sessions", {}).get("sessions", {})),
            "active_sessions": [
                sid for sid, session in state.get("sessions", {}).get("sessions", {}).items()
                if session.get("state") != "IDLE"
            ],
            "stats": state.get("stats", {}),
            "effects_registered": len(store._effects_manager._effects) if hasattr(store, '_effects_manager') and hasattr(store._effects_manager, '_effects') else 0
        }
    except Exception as e:
        return {
            "initialized": False,
            "error": str(e)
        }


# 使用範例
if __name__ == "__main__":
    async def main():
        # 初始化 Store
        store = await initialize_asr_hub_store()
        
        # 可選：預載入模型
        await preload_models()
        
        # 檢查狀態
        status = get_store_status()
        logger.info(f"Store 狀態: {status}")
    
    asyncio.run(main())