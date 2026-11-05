"""backend/observability/tracing.py

Per-turn distributed tracing for the voice pipeline.

Each WebSocket turn gets a unique trace_id (UUID4). The TurnTracer records
the monotonic timestamp of every pipeline stage and exposes the latency between
any two stages as well as the canonical "Time to First Audio" (TTFA) metric.

Design constraints
------------------
- No raw API keys, JWTs, full audio blobs, or unredacted transcript text.
- Trace data is kept in memory per-turn and published to TurnEventBus for
  async downstream subscribers (metrics, logging, LangSmith-compat export).
- The tracer is provider-neutral: it neither imports nor references any LLM,
  STT, or TTS library directly.
- Thread-safe for the pipeline's asyncio + threading audio worker pattern.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .events import TurnEvent, TurnEventBus, TurnEventType

logger = logging.getLogger(__name__)


@dataclass
class StageRecord:
    """Records the monotonic timestamp of a single pipeline stage."""

    event_type: TurnEventType
    monotonic_ns: int = field(default_factory=time.monotonic_ns)
    wall_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class TurnTracer:
    """
    Tracks timing milestones for a single voice turn.

    Instantiated once per turn (or per session reconnect) by the
    PipelineOrchestrator and passed down through pipeline stages.

    Example::

        tracer = TurnTracer(session_id="s-1", turn_id="t-1")
        tracer.mark(TurnEventType.SERVER_AUDIO_RECEIVED)
        tracer.mark(TurnEventType.VAD_SPEECH_START)
        tracer.mark(TurnEventType.STT_FINAL)
        ttfa = tracer.ttfa_ms()      # None until tts_first_audio + server_audio_sent
        summary = tracer.summary()
    """

    def __init__(
        self,
        session_id: str,
        turn_id: str,
        generation_id: str | None = None,
        trace_id: str | None = None,
        bus: TurnEventBus | None = None,
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        self.generation_id = generation_id
        self.trace_id: str = trace_id or str(uuid.uuid4())
        self._bus = bus or TurnEventBus.instance()
        self._stages: dict[TurnEventType, StageRecord] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def mark(
        self,
        event_type: TurnEventType,
        metadata: dict[str, Any] | None = None,
        *,
        publish: bool = True,
    ) -> StageRecord:
        """
        Record a pipeline stage milestone.

        Parameters
        ----------
        event_type:
            The stage being recorded.
        metadata:
            Optional privacy-safe key/value pairs (do NOT include raw tokens,
            audio frames, full transcripts, API keys, or JWT payloads).
        publish:
            If True (default) the event is published to TurnEventBus for
            async subscribers such as the metrics collector.
        """
        record = StageRecord(
            event_type=event_type,
            metadata=metadata or {},
        )
        with self._lock:
            # Only record the FIRST occurrence of each stage type per turn.
            if event_type not in self._stages:
                self._stages[event_type] = record

        if publish:
            self._bus.publish(
                TurnEvent(
                    event_type=event_type,
                    trace_id=self.trace_id,
                    session_id=self.session_id,
                    turn_id=self.turn_id,
                    generation_id=self.generation_id,
                    timestamp=record.wall_time,
                    monotonic_ns=record.monotonic_ns,
                    metadata=record.metadata,
                )
            )
        return record

    def get(self, event_type: TurnEventType) -> StageRecord | None:
        """Return the recorded stage or None if not yet reached."""
        with self._lock:
            return self._stages.get(event_type)

    # ------------------------------------------------------------------
    # Latency helpers
    # ------------------------------------------------------------------

    def latency_ms(
        self,
        from_stage: TurnEventType,
        to_stage: TurnEventType,
    ) -> float | None:
        """
        Return the latency in milliseconds between two recorded stages,
        or None if either stage has not been recorded yet.
        """
        with self._lock:
            start = self._stages.get(from_stage)
            end = self._stages.get(to_stage)
        if start is None or end is None:
            return None
        return (end.monotonic_ns - start.monotonic_ns) / 1_000_000

    def ttfa_ms(self) -> float | None:
        """
        Time to First Audio (TTFA): latency from vad_speech_end (end of
        user utterance) to server_audio_sent (first audio chunk on the wire).

        Returns None until both stages are recorded.
        """
        return self.latency_ms(TurnEventType.VAD_SPEECH_END, TurnEventType.SERVER_AUDIO_SENT)

    def stt_latency_ms(self) -> float | None:
        """Latency from VAD speech end to STT final transcript."""
        return self.latency_ms(TurnEventType.VAD_SPEECH_END, TurnEventType.STT_FINAL)

    def llm_latency_ms(self) -> float | None:
        """Latency from STT final to first LLM token."""
        return self.latency_ms(TurnEventType.STT_FINAL, TurnEventType.LLM_FIRST_TOKEN)

    def tts_latency_ms(self) -> float | None:
        """Latency from first LLM token to first TTS audio chunk queued."""
        return self.latency_ms(TurnEventType.LLM_FIRST_TOKEN, TurnEventType.TTS_FIRST_AUDIO)

    def total_turn_latency_ms(self) -> float | None:
        """
        Total end-to-end turn latency from first audio received to first
        audio byte sent back to the client.
        """
        return self.latency_ms(TurnEventType.SERVER_AUDIO_RECEIVED, TurnEventType.SERVER_AUDIO_SENT)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """
        Return a privacy-safe summary dict suitable for logging and
        telemetry. Never includes raw transcripts, JWT, or audio.
        """
        with self._lock:
            stages_recorded = [e.value for e in self._stages]

        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "generation_id": self.generation_id,
            "stages_recorded": stages_recorded,
            "latencies_ms": {
                "ttfa": self.ttfa_ms(),
                "stt": self.stt_latency_ms(),
                "llm_first_token": self.llm_latency_ms(),
                "tts_first_audio": self.tts_latency_ms(),
                "total_turn": self.total_turn_latency_ms(),
            },
        }


# ---------------------------------------------------------------------------
# Module-level accessor (used by pipeline code that cannot hold a reference
# to the per-turn tracer).  The registry is session-keyed so each session
# can retrieve its current tracer without passing it down the whole call tree.
# ---------------------------------------------------------------------------

_tracer_registry: dict[str, TurnTracer] = {}
_registry_lock = threading.Lock()


def register_tracer(session_id: str, tracer: TurnTracer) -> None:
    """Register the active tracer for a session."""
    with _registry_lock:
        _tracer_registry[session_id] = tracer


def get_tracer(session_id: str) -> TurnTracer | None:
    """
    Return the active TurnTracer for a session, or None if not registered.
    Safe to call from any thread.
    """
    with _registry_lock:
        return _tracer_registry.get(session_id)


def unregister_tracer(session_id: str) -> None:
    """Remove the tracer when a session ends."""
    with _registry_lock:
        _tracer_registry.pop(session_id, None)

