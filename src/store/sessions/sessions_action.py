# src/store/sessions/sessions.action.py
from pystorex import create_action

from src.interface.action import Action
from src.interface.strategy import Strategy
from src.interface.wake import WakeActivateSource, WakeDeactivateSource
from src.utils.string_case import to_camel_case, add_title_prefix


# ================================
# Utils
# =================================
def add_session_title(action_type: str):
    """
    把 snake_case 的 Action 轉成 CamelCase，並加上 [Session] 前綴
    例: "create_session" -> "[Session] Create Session"
    """
    title = "[Session]"
    camel_case = to_camel_case(action_type)
    return add_title_prefix(title, camel_case)


# =================================
# Actions
# =================================

create_session = create_action(
    add_session_title(Action.CREATE_SESSION),
    lambda strategy=Strategy.NON_STREAMING, request_id=None, session_id=None: {
        'strategy': strategy,
        'request_id': request_id,
        'session_id': session_id
    }
)

delete_session = create_action(
    add_session_title(Action.DELETE_SESSION),
    lambda session_id: session_id,
)

session_expired = create_action(
    add_session_title(Action.SESSION_EXPIRED),
    lambda session_id: session_id,
)

reset_session = create_action(
    add_session_title(Action.RESET_SESSION),
    lambda session_id: session_id,
)

emit_audio_chunk = create_action(
    add_session_title(Action.EMIT_AUDIO_CHUNK),
    lambda session_id, audio_data: {"session_id": session_id, "audio_data": audio_data},
)

receive_audio_chunk = create_action(
    add_session_title(Action.RECEIVE_AUDIO_CHUNK),
    lambda session_id, audio_data: {"session_id": session_id, "audio_data": audio_data},
)

clear_audio_buffer = create_action(
    add_session_title(Action.CLEAR_AUDIO_BUFFER),
    lambda session_id: session_id,
)

upload_started = create_action(
    add_session_title(Action.UPLOAD_STARTED),
    lambda session_id, file_name, sample_rate, channels, format: {
        "session_id": session_id,
        "file_name": file_name,
        "sample_rate": sample_rate,
        "channels": channels,
        "format": format,
    },
)

upload_completed = create_action(
    add_session_title(Action.UPLOAD_COMPLETED),
    lambda session_id, file_name: {"session_id": session_id, "file_name": file_name},
)

start_listening = create_action(
    add_session_title(Action.START_LISTENING),
    lambda session_id, sample_rate, channels, format: {
        "session_id": session_id,
        "sample_rate": sample_rate,
        "channels": channels,
        "format": format,
    },
)

wake_activated = create_action(
    add_session_title(Action.WAKE_ACTIVATED),
    lambda session_id, source: {"session_id": session_id, "source": source}, # WakeActivateSource
)

wake_deactivated = create_action(
    add_session_title(Action.WAKE_DEACTIVATED),
    lambda session_id, source: {"session_id": session_id, "source": source}, # WakeDeactivateSource
)

vad_speech_detected = create_action(
    add_session_title(Action.VAD_SPEECH_DETECTED),
    lambda session_id: session_id,
)

vad_silence_detected = create_action(
    add_session_title(Action.VAD_SILENCE_DETECTED),
    lambda session_id: session_id,
)

silence_timeout = create_action(
    add_session_title(Action.SILENCE_TIMEOUT),
    lambda session_id: session_id,
)

record_started = create_action(
    add_session_title(Action.RECORD_STARTED),
    lambda session_id: session_id,
)

record_stopped = create_action(
    add_session_title(Action.RECORD_STOPPED),
    lambda session_id: session_id,
)

play_asr_feedback = create_action(
    add_session_title(Action.PLAY_ASR_FEEDBACK),
    lambda session_id, command: {"session_id": session_id, "command": command},
)

transcribe_started = create_action(
    add_session_title(Action.TRANSCRIBE_STARTED),
    lambda session_id, file_path=None: {"session_id": session_id, "file_path": file_path},
)

transcribe_done = create_action(
    add_session_title(Action.TRANSCRIBE_DONE),
    lambda session_id,result: {"session_id": session_id, "result": result},
)

asr_stream_started = create_action(
    add_session_title(Action.ASR_STREAM_STARTED),
    lambda session_id: session_id,
)

asr_stream_stopped = create_action(
    add_session_title(Action.ASR_STREAM_STOPPED),
    lambda session_id: session_id,
)

llm_reply_started = create_action(
    add_session_title(Action.LLM_REPLY_STARTED),
    lambda session_id: session_id,
)

llm_replying = create_action(
    add_session_title(Action.LLM_REPLYING),
    lambda session_id: session_id,
)

llm_reply_completed = create_action(
    add_session_title(Action.LLM_REPLY_COMPLETED),
    lambda session_id: session_id,
)

llm_reply_timeout = create_action(
    add_session_title(Action.LLM_REPLY_TIMEOUT),
    lambda session_id: session_id,
)

tts_playback_started = create_action(
    add_session_title(Action.TTS_PLAYBACK_STARTED),
    lambda session_id: session_id,
)

tts_playing = create_action(
    add_session_title(Action.TTS_PLAYING),
    lambda session_id: session_id,
)

tts_playback_completed = create_action(
    add_session_title(Action.TTS_PLAYBACK_COMPLETED),
    lambda session_id: session_id,
)

tts_playback_timeout = create_action(
    add_session_title(Action.TTS_PLAYBACK_TIMEOUT),
    lambda session_id: session_id,
)

reply_interrupted = create_action(
    add_session_title(Action.REPLY_INTERRUPTED),
    lambda session_id: session_id,
)

error_occurred = create_action(
    add_session_title(Action.ERROR_OCCURRED),
    lambda session_id: session_id,
)

error_raised = create_action(
    add_session_title(Action.ERROR_RAISED),
    lambda session_id, error: {"session_id": session_id, "error": error},
)

error_reported = create_action(
    add_session_title(Action.ERROR_REPORTED),
    lambda session_id: session_id,
)