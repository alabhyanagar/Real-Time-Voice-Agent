"""Strict JSON schemas for the versioned WebSocket contract."""
from typing import Annotated, Literal, Union
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from .versioning import PROTOCOL_VERSION

class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class EventEnvelope(ProtocolModel):
    type: str
    protocol_version: str = PROTOCOL_VERSION
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    sequence: int = Field(default=0, ge=0)
    timestamp_ms: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000), ge=0)
    response_id: str | None = Field(default=None, min_length=1)
    generation_id: str | None = Field(default=None, min_length=1)

class HelloEvent(EventEnvelope):
    type: Literal["hello"] = "hello"
    client_name: str = "web"
    client_version: str | None = None
    resume_token: str | None = None

class AudioFormat(ProtocolModel):
    encoding: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: int = Field(default=16_000, ge=8_000, le=48_000)
    channels: int = Field(default=1, ge=1, le=2)
    sample_width_bytes: Literal[2] = 2

class AudioFormatEvent(EventEnvelope):
    type: Literal["audio_format"] = "audio_format"
    format: AudioFormat

class AudioFrameMetadata(EventEnvelope):
    type: Literal["audio_frame"] = "audio_frame"
    byte_length: int = Field(gt=0)
    frame_index: int = Field(ge=0)

class CancelEvent(EventEnvelope):
    type: Literal["cancel"] = "cancel"
    reason: Literal["barge_in", "user_cancel", "disconnect", "timeout"] = "user_cancel"

class FlushEvent(EventEnvelope):
    type: Literal["flush"] = "flush"
    reason: Literal["barge_in", "cancel", "new_turn"] = "barge_in"

class FlushAckEvent(EventEnvelope):
    type: Literal["flush_ack"] = "flush_ack"

class ResumeEvent(EventEnvelope):
    type: Literal["resume"] = "resume"
    resume_token: str = Field(min_length=1)

class PingEvent(EventEnvelope):
    type: Literal["ping"] = "ping"

class PongEvent(EventEnvelope):
    type: Literal["pong"] = "pong"

class ClientMetricsEvent(EventEnvelope):
    type: Literal["client_metrics"] = "client_metrics"
    metrics: dict[str, float | int | str] = Field(default_factory=dict)

class ToolConfirmationResponseEvent(EventEnvelope):
    type: Literal["tool_confirmation_response"] = "tool_confirmation_response"
    confirmation_id: str = Field(min_length=1)
    approved: bool

class ReadyEvent(EventEnvelope):
    type: Literal["ready"] = "ready"
    server_version: str
    audio_format: AudioFormat

class StateEvent(EventEnvelope):
    type: Literal["state"] = "state"
    state: Literal["idle", "listening", "processing", "speaking", "cancelling", "error"]

class TranscriptEvent(EventEnvelope):
    type: Literal["transcript"] = "transcript"
    text: str
    is_final: bool = False

class ResponseTextDeltaEvent(EventEnvelope):
    type: Literal["response_text_delta"] = "response_text_delta"
    text: str
    is_final: bool = False

class AudioStartEvent(EventEnvelope):
    type: Literal["audio_start"] = "audio_start"
    mime_type: str = "audio/pcm"

class AudioEndEvent(EventEnvelope):
    type: Literal["audio_end"] = "audio_end"

class AudioFlushEvent(EventEnvelope):
    type: Literal["audio_flush"] = "audio_flush"
    reason: str = "barge_in"

class ToolStatusEvent(EventEnvelope):
    type: Literal["tool_status"] = "tool_status"
    tool_name: str
    status: Literal["requested", "running", "completed", "failed"]
    detail: str | None = None

class ToolConfirmationEvent(EventEnvelope):
    type: Literal["tool_confirmation"] = "tool_confirmation"
    tool_name: str
    confirmation_id: str
    prompt: str

class UiCardEvent(EventEnvelope):
    type: Literal["ui_card"] = "ui_card"
    card_type: str
    payload: dict[str, object] = Field(default_factory=dict)

class ErrorEvent(EventEnvelope):
    type: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False

class TelemetryEvent(EventEnvelope):
    type: Literal["telemetry"] = "telemetry"
    measurements: dict[str, float | int] = Field(default_factory=dict)

_CLIENT = (HelloEvent, AudioFormatEvent, AudioFrameMetadata, CancelEvent, FlushEvent, FlushAckEvent, ResumeEvent, PingEvent, ClientMetricsEvent, ToolConfirmationResponseEvent)
_SERVER = (ReadyEvent, StateEvent, TranscriptEvent, ResponseTextDeltaEvent, AudioStartEvent, AudioEndEvent, AudioFlushEvent, ToolStatusEvent, ToolConfirmationEvent, UiCardEvent, ErrorEvent, TelemetryEvent, PongEvent)
ClientEvent = Annotated[Union[_CLIENT], Field(discriminator="type")]
ServerEvent = Annotated[Union[_SERVER], Field(discriminator="type")]
