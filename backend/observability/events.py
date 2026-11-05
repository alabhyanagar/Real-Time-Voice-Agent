"""backend/observability/events.py

Lightweight, in-process event bus for voice pipeline turn events.

Each turn in the voice pipeline emits a structured sequence of TurnEvents
that record exactly when each stage begins and completes.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any, Callable

logger = logging.getLogger(__name__)


@unique
class TurnEventType(str, Enum):
    # Audio ingestion
    CAPTURE_START = "capture_start"
    SERVER_AUDIO_RECEIVED = "server_audio_received"
    # Voice activity detection
    VAD_SPEECH_START = "vad_speech_start"
    VAD_SPEECH_END = "vad_speech_end"
    # Speech-to-text
    STT_FIRST_PARTIAL = "stt_first_partial"
    STT_FINAL = "stt_final"
    # Language model
    LLM_FIRST_TOKEN = "llm_first_token"
    # Tool execution
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    # Text-to-speech
    TTS_STARTED = "tts_started"
    TTS_FIRST_AUDIO = "tts_first_audio"
    # Audio delivery
    SERVER_AUDIO_SENT = "server_audio_sent"
    # Client-reported (from telemetry WebSocket message)
    CLIENT_PLAYBACK_STARTED = "client_playback_started"
    CLIENT_PLAYBACK_FLUSHED = "client_playback_flushed"
    # Turn lifecycle
    TURN_CANCELLED = "turn_cancelled"
    TURN_COMPLETED = "turn_completed"
    TURN_ERROR = "turn_error"


@dataclass(slots=True)
class TurnEvent:
    """An immutable record of a single pipeline stage milestone."""

    event_type: TurnEventType
    trace_id: str
    session_id: str
    turn_id: str
    generation_id: str | None = None
    timestamp: float = field(default_factory=time.time)
    monotonic_ns: int = field(default_factory=time.monotonic_ns)
    metadata: dict[str, Any] = field(default_factory=dict)


class TurnEventBus:
    """Singleton async event bus for the voice pipeline."""

    _singleton: TurnEventBus | None = None

    def __init__(self) -> None:
        self._subscribers: list[Callable[[TurnEvent], Any]] = []

    @classmethod
    def instance(cls) -> "TurnEventBus":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    @classmethod
    def reset(cls) -> None:
        """Reset singleton – for testing only."""
        if cls._singleton is not None:
            cls._singleton._subscribers.clear()
            cls._singleton = None

    def subscribe(self, handler: Callable[[TurnEvent], Any]) -> Callable[[], None]:
        """Register a handler (sync function or async coroutine function)."""
        if handler not in self._subscribers:
            self._subscribers.append(handler)

        def _unsubscribe() -> None:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

        return _unsubscribe

    def publish(self, event: TurnEvent) -> None:
        """Publish an event to all subscribers immediately and safely."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for handler in list(self._subscribers):
            try:
                if inspect.iscoroutinefunction(handler):
                    if loop and loop.is_running():
                        loop.create_task(self._invoke_async(handler, event))
                else:
                    handler(event)
            except Exception as exc:  # noqa: BLE001
                logger.exception("TurnEventBus subscriber failed: %s", exc)

    async def _invoke_async(self, handler: Callable[[TurnEvent], Any], event: TurnEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("TurnEventBus async subscriber failed: %s", exc)

    def publish_nowait(self, event: TurnEvent) -> None:
        self.publish(event)
