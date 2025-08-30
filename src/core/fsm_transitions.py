# from transitions.extensions import HierarchicalMachine as Machine
"""
使用 transitions 定義多種 Session 狀態機 (FSM)
並生成 Mermaid 語法的狀態圖

python -m src.core.fsm_transitions
"""


from transitions.extensions.diagrams import HierarchicalGraphMachine as Machine


from src.config.manager import ConfigManager
from src.interface.action import Action
from src.interface.state import State
from src.interface.strategy import Strategy, StrategyPlugin, make_transition

config_manager = ConfigManager()

# Batch Plugin
BatchPlugin = StrategyPlugin(
    name=Strategy.BATCH,
    states=[State.UPLOADING, State.TRANSCRIBING],
    transitions=[
        make_transition(Action.UPLOAD_STARTED, State.IDLE, State.UPLOADING),
        make_transition(Action.UPLOAD_COMPLETED, State.UPLOADING, State.PROCESSING),
        make_transition(Action.TRANSCRIBE_STARTED, State.PROCESSING, State.TRANSCRIBING),
        make_transition(Action.TRANSCRIBE_DONE, State.TRANSCRIBING, State.IDLE),
    ],
)

# Non-streaming Plugin
NonStreamingPlugin = StrategyPlugin(
    name=Strategy.NON_STREAMING,
    states=[State.ACTIVATED, State.RECORDING, State.TRANSCRIBING, State.BUSY],
    transitions=[
        make_transition(Action.START_LISTENING, State.IDLE, State.PROCESSING),
        # 階層狀態需要使用完整路徑格式: parent_child
        make_transition(Action.WAKE_ACTIVATED, State.PROCESSING, f"{State.PROCESSING}_{State.ACTIVATED}"),
        make_transition(Action.RECORD_STARTED, f"{State.PROCESSING}_{State.ACTIVATED}", f"{State.PROCESSING}_{State.RECORDING}"),
        make_transition(Action.RECORD_STOPPED, f"{State.PROCESSING}_{State.RECORDING}", f"{State.PROCESSING}_{State.TRANSCRIBING}"),
        make_transition(Action.TRANSCRIBE_DONE, f"{State.PROCESSING}_{State.TRANSCRIBING}", f"{State.PROCESSING}_{State.ACTIVATED}"),
    ],
)

# Streaming Plugin
StreamingPlugin = StrategyPlugin(
    name=Strategy.STREAMING,
    states=[State.ACTIVATED, State.TRANSCRIBING, State.BUSY],
    transitions=[
        make_transition(Action.START_LISTENING, State.IDLE, State.PROCESSING),
        # 階層狀態需要使用完整路徑格式: parent_child
        make_transition(Action.WAKE_ACTIVATED, State.PROCESSING, f"{State.PROCESSING}_{State.ACTIVATED}"),
        make_transition(Action.ASR_STREAM_STARTED, f"{State.PROCESSING}_{State.ACTIVATED}", f"{State.PROCESSING}_{State.TRANSCRIBING}"),
        make_transition(Action.ASR_STREAM_STOPPED, f"{State.PROCESSING}_{State.TRANSCRIBING}", f"{State.PROCESSING}_{State.ACTIVATED}"),
    ],
)

def set_specific_transitions(strategy_name: str):
    transitions = []
    if (
            strategy_name == Strategy.NON_STREAMING
            or strategy_name == Strategy.STREAMING
        ):
            # 非串流與串流策略專屬轉換
            # 使用完整階層路徑
            transitions += [
                make_transition(Action.WAKE_DEACTIVATED, f"{State.PROCESSING}_{State.ACTIVATED}", State.IDLE),
            ]
            
            # TODO: LLM 功能尚未實作，暫時停用
            # 當加入 LLM 功能時，需要在 config.yaml 中加入相關配置
            llm_enabled = False  # config_manager.core.llm == True
            if llm_enabled:
                transitions += [
                    make_transition(Action.LLM_REPLY_STARTED, [f"{State.PROCESSING}_{State.ACTIVATED}", f"{State.PROCESSING}_{State.TRANSCRIBING}"], f"{State.PROCESSING}_{State.BUSY}"),
                    make_transition(Action.LLM_REPLY_COMPLETED, f"{State.PROCESSING}_{State.BUSY}", f"{State.PROCESSING}_{State.ACTIVATED}"),
                    make_transition(Action.LLM_REPLY_TIMEOUT, f"{State.PROCESSING}_{State.BUSY}", f"{State.PROCESSING}_{State.ACTIVATED}"),
                ]
            
            # TODO: TTS 功能尚未實作，暫時停用
            # 當加入 TTS 功能時，需要在 config.yaml 中加入相關配置
            tts_enabled = False  # config_manager.core.tts == True
            if tts_enabled:
                transitions += [
                    make_transition(Action.TTS_PLAYBACK_STARTED, [f"{State.PROCESSING}_{State.ACTIVATED}", f"{State.PROCESSING}_{State.TRANSCRIBING}"], f"{State.PROCESSING}_{State.BUSY}"),
                    make_transition(Action.TTS_PLAYBACK_COMPLETED, f"{State.PROCESSING}_{State.BUSY}", f"{State.PROCESSING}_{State.ACTIVATED}"),
                    make_transition(Action.TTS_PLAYBACK_TIMEOUT, f"{State.PROCESSING}_{State.BUSY}", f"{State.PROCESSING}_{State.ACTIVATED}"),
                ]
            # 當 LLM 或 TTS 啟用時的回覆中斷轉換
            if llm_enabled or tts_enabled:
                transitions += [
                    make_transition(Action.REPLY_INTERRUPTED, f"{State.PROCESSING}_{State.BUSY}", f"{State.PROCESSING}_{State.ACTIVATED}"),
                ]
    return transitions
    


# === 基底 FSM ===
class SessionFSM:
    def __init__(self, strategy_plugin: StrategyPlugin):
        self.strategy = strategy_plugin.name

        # 通用狀態
        states = [
            State.IDLE,
            State.ERROR,
            {"name": State.PROCESSING, "children": strategy_plugin.states},
        ]

        # 通用轉換
        transitions = [
            make_transition(Action.SESSION_EXPIRED, "*", State.IDLE),
            make_transition(Action.RESET_SESSION, "*", State.IDLE),
            make_transition(Action.ERROR_OCCURRED, "*", State.ERROR),
        ] + strategy_plugin.transitions  # 插入策略專屬轉換

        transitions += set_specific_transitions(strategy_plugin.name)

        # 初始化
        # transitions library 會將 trigger 等方法注入到 model (self) 上
        # 所以調用時應該用 fsm.trigger() 而不是 fsm.machine.trigger()
        self.machine = Machine(
            model=self,
            states=states,
            transitions=transitions,
            initial=State.IDLE,
            title=strategy_plugin.name,
            graph_engine="mermaid",
            show_conditions=True,
            auto_transitions=False,
        )

def _print_fsm_graph():
    """輸出 FSM 狀態圖 (Mermaid 語法)"""
    batch_fsm = SessionFSM(BatchPlugin)
    non_streaming_fsm = SessionFSM(NonStreamingPlugin)
    streaming_fsm = SessionFSM(StreamingPlugin)

    print(batch_fsm.machine.get_graph().draw(None))  # 直接輸出 Mermaid 語法
    print("\n", "= " * 30, "\n")
    print(non_streaming_fsm.machine.get_graph().draw(None))  # 直接輸出 Mermaid 語法
    print("\n", "= " * 30, "\n")
    print(streaming_fsm.machine.get_graph().draw(None))  # 直接輸出 Mermaid 語法

if __name__ == "__main__":
    _print_fsm_graph()