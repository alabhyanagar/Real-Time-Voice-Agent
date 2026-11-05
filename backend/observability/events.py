"""backend/observability/events.py

Lightweight, in-process event bus for voice pipeline turn events.

Each turn in the voice pipeline emits a structured sequence of TurnEvents
that record exactly when each stage begins and completes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

_MAX_QUEUE = 512  # max buffered events per subscriber before oldest is dropped


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


AsyncSubscriber = Callable[[TurnEvent], Coroutine[Any, Any, None]]


class TurnEventBus:
    """Singleton async event bus for the voice pipeline."""

    _singleton: TurnEventBus | None = None

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[TurnEvent]] = []
        self._tasks: set[asyncio.Task[None]] = set()

    @classmethod
    def instance(cls) -> "TurnEventBus":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    @classmethod
    def reset(cls) -> None:
        """Reset singleton – cancels background consumer tasks."""
        if cls._singleton is not None:
            for task in list(cls._singleton._tasks):
                task.cancel()
            cls._singleton._tasks.clear()
            cls._singleton._subscribers.clear()
            cls._singleton = None

    def _get_loop(self) -> asyncio.AbstractEventLoop | None:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def subscribe(self, handler: AsyncSubscriber) -> Callable[[], None]:
        """Register an async handler coroutine. Returns an unsubscribe callable."""
        loop = self._get_loop()
        if loop is None:
            logger.warning("TurnEventBus.subscribe called outside of running event loop; subscriber ignored.")
            return lambda: None

        q: asyncio.Queue[TurnEvent] = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._subscribers.append(q)

        async def _consumer() -> None:
            try:
                while True:
                    try:
                        event = await q.get()
                    except asyncio.CancelledError:
                        break
                    try:
                        await handler(event)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("TurnEventBus subscriber raised: %s", exc)
                    finally:
                        q.task_done()
            except asyncio.CancelledError:
                pass

        task = loop.create_task(_consumer())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        def _unsubscribe() -> None:
            if q in self._subscribers:
                self._subscribers.remove(q)
            task.cancel()

        return _unsubscribe

    def publish(self, event: TurnEvent) -> None:
        """Publish an event to all subscribers."""
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()
                    q.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def publish_nowait(self, event: TurnEvent) -> None:
        self.publish(event)
