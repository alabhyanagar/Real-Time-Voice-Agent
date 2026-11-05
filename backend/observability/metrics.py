"""backend/observability/metrics.py

Aggregated runtime metrics for the voice pipeline.

Tracks the following metric families:
  - Latency histograms (p50 / p95 / p99 / mean) for TTFA, STT, LLM, TTS,
    total turn, and cancel latency.
  - Provider success / failure / timeout counters.
  - Tool call success / failure / confirmation rates.
  - Session counters: total, active, reconnect.
  - Queue depth snapshots.
  - Dropped audio frame counts.

The MetricsCollector is a singleton that subscribes to TurnEventBus and
accumulates stats in memory.  For production deployments the same stats can
be exported to Prometheus, OpenTelemetry, or any other backend by implementing
an exporter (see the export() method).

Design constraints
------------------
- No raw API keys, JWTs, audio blobs, or transcript text are stored.
- All counters and histograms use thread-safe primitives.
- The collector is opt-in: it starts only when start() is called.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from typing import Any

from .events import TurnEvent, TurnEventBus, TurnEventType

logger = logging.getLogger(__name__)

_HISTOGRAM_WINDOW = 1000  # keep last N samples per histogram


class LatencyHistogram:
    """Fixed-size sliding window histogram for latency values in ms."""

    def __init__(self, maxlen: int = _HISTOGRAM_WINDOW) -> None:
        self._data: deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, value_ms: float) -> None:
        with self._lock:
            self._data.append(value_ms)

    def stats(self) -> dict[str, float | None]:
        with self._lock:
            data = list(self._data)
        if not data:
            return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None}
        sorted_data = sorted(data)
        n = len(sorted_data)

        def percentile(p: float) -> float:
            idx = int(p / 100.0 * (n - 1))
            return sorted_data[min(idx, n - 1)]

        return {
            "count": n,
            "mean": round(statistics.mean(data), 2),
            "p50": round(percentile(50), 2),
            "p95": round(percentile(95), 2),
            "p99": round(percentile(99), 2),
        }


class Counter:
    """Thread-safe integer counter."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> None:
        with self._lock:
            self._value += amount

    def decrement(self, amount: int = 1) -> None:
        with self._lock:
            self._value = max(0, self._value - amount)

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0


class MetricsCollector:
    """
    Aggregated runtime metrics collector.

    Subscribes to TurnEventBus.  Call start() after the asyncio event loop
    is running (e.g., in the FastAPI lifespan) and stop() on shutdown.

    Example::

        metrics = MetricsCollector.instance()
        await asyncio.get_event_loop().run_until_complete(metrics.start())
        snapshot = metrics.snapshot()
    """

    _singleton: MetricsCollector | None = None

    def __init__(self, bus: TurnEventBus | None = None) -> None:
        self._bus = bus or TurnEventBus.instance()
        self._unsubscribe: list[Any] = []

        # --- Latency histograms ---
        self.hist_ttfa = LatencyHistogram()
        self.hist_stt = LatencyHistogram()
        self.hist_llm_first_token = LatencyHistogram()
        self.hist_tts_first_audio = LatencyHistogram()
        self.hist_total_turn = LatencyHistogram()
        self.hist_cancel_latency = LatencyHistogram()

        # --- Per-turn timestamp tracking ---
        # Maps trace_id -> dict of stage -> monotonic_ns
        self._turn_stages: dict[str, dict[TurnEventType, int]] = defaultdict(dict)
        self._turn_lock = threading.Lock()

        # --- Provider counters ---
        # provider_name -> {success, failure, timeout}
        self._provider_counters: dict[str, dict[str, Counter]] = defaultdict(
            lambda: {"success": Counter(), "failure": Counter(), "timeout": Counter()}
        )

        # --- Tool counters ---
        # tool_name -> {success, failure, confirmed, rejected}
        self._tool_counters: dict[str, dict[str, Counter]] = defaultdict(
            lambda: {
                "success": Counter(),
                "failure": Counter(),
                "confirmed": Counter(),
                "rejected": Counter(),
            }
        )

        # --- Session counters ---
        self.sessions_total = Counter()
        self.sessions_active = Counter()
        self.sessions_reconnect = Counter()

        # --- Audio counters ---
        self.frames_received = Counter()
        self.frames_dropped = Counter()

        # --- Turn counters ---
        self.turns_completed = Counter()
        self.turns_cancelled = Counter()
        self.turns_error = Counter()

    @classmethod
    def instance(cls) -> "MetricsCollector":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    @classmethod
    def reset(cls) -> None:
        """Reset singleton – for testing only."""
        cls._singleton = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Subscribe to TurnEventBus. Must be called inside a running loop."""
        unsub = self._bus.subscribe(self._handle_event)
        self._unsubscribe.append(unsub)
        logger.info("MetricsCollector started.")

    def stop(self) -> None:
        """Unsubscribe from TurnEventBus."""
        for fn in self._unsubscribe:
            fn()
        self._unsubscribe.clear()
        logger.info("MetricsCollector stopped.")

    # ------------------------------------------------------------------
    # Event handler (called by TurnEventBus consumer task)
    # ------------------------------------------------------------------

    async def _handle_event(self, event: TurnEvent) -> None:
        with self._turn_lock:
            self._turn_stages[event.trace_id][event.event_type] = event.monotonic_ns

        et = event.event_type
        stages = self._turn_stages[event.trace_id]

        def _latency(a: TurnEventType, b: TurnEventType) -> float | None:
            ts_a = stages.get(a)
            ts_b = stages.get(b)
            if ts_a is None or ts_b is None:
                return None
            return (ts_b - ts_a) / 1_000_000

        if et == TurnEventType.SERVER_AUDIO_SENT:
            ttfa = _latency(TurnEventType.VAD_SPEECH_END, TurnEventType.SERVER_AUDIO_SENT)
            if ttfa is not None:
                self.hist_ttfa.record(ttfa)
            total = _latency(TurnEventType.SERVER_AUDIO_RECEIVED, TurnEventType.SERVER_AUDIO_SENT)
            if total is not None:
                self.hist_total_turn.record(total)

        elif et == TurnEventType.STT_FINAL:
            stt = _latency(TurnEventType.VAD_SPEECH_END, TurnEventType.STT_FINAL)
            if stt is not None:
                self.hist_stt.record(stt)

        elif et == TurnEventType.LLM_FIRST_TOKEN:
            llm = _latency(TurnEventType.STT_FINAL, TurnEventType.LLM_FIRST_TOKEN)
            if llm is not None:
                self.hist_llm_first_token.record(llm)

        elif et == TurnEventType.TTS_FIRST_AUDIO:
            tts = _latency(TurnEventType.LLM_FIRST_TOKEN, TurnEventType.TTS_FIRST_AUDIO)
            if tts is not None:
                self.hist_tts_first_audio.record(tts)

        elif et == TurnEventType.TURN_CANCELLED:
            self.turns_cancelled.increment()
            cancel = _latency(TurnEventType.SERVER_AUDIO_RECEIVED, TurnEventType.TURN_CANCELLED)
            if cancel is not None:
                self.hist_cancel_latency.record(cancel)
            # Clean up per-turn stage tracking
            with self._turn_lock:
                self._turn_stages.pop(event.trace_id, None)

        elif et == TurnEventType.TURN_COMPLETED:
            self.turns_completed.increment()
            with self._turn_lock:
                self._turn_stages.pop(event.trace_id, None)

        elif et == TurnEventType.TURN_ERROR:
            self.turns_error.increment()
            with self._turn_lock:
                self._turn_stages.pop(event.trace_id, None)

    # ------------------------------------------------------------------
    # Manual increment helpers (called directly by pipeline code)
    # ------------------------------------------------------------------

    def record_provider_success(self, provider: str) -> None:
        self._provider_counters[provider]["success"].increment()

    def record_provider_failure(self, provider: str) -> None:
        self._provider_counters[provider]["failure"].increment()

    def record_provider_timeout(self, provider: str) -> None:
        self._provider_counters[provider]["timeout"].increment()

    def record_tool_success(self, tool_name: str) -> None:
        self._tool_counters[tool_name]["success"].increment()

    def record_tool_failure(self, tool_name: str) -> None:
        self._tool_counters[tool_name]["failure"].increment()

    def record_tool_confirmed(self, tool_name: str) -> None:
        self._tool_counters[tool_name]["confirmed"].increment()

    def record_tool_rejected(self, tool_name: str) -> None:
        self._tool_counters[tool_name]["rejected"].increment()

    def record_session_start(self, *, reconnect: bool = False) -> None:
        self.sessions_total.increment()
        self.sessions_active.increment()
        if reconnect:
            self.sessions_reconnect.increment()

    def record_session_end(self) -> None:
        self.sessions_active.decrement()

    def record_frames(self, received: int = 1, dropped: int = 0) -> None:
        self.frames_received.increment(received)
        if dropped:
            self.frames_dropped.increment(dropped)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a serialisable metrics snapshot. No sensitive data included."""
        providers: dict[str, dict[str, int]] = {}
        for name, ctrs in self._provider_counters.items():
            providers[name] = {k: v.value for k, v in ctrs.items()}

        tools: dict[str, dict[str, int]] = {}
        for name, ctrs in self._tool_counters.items():
            tools[name] = {k: v.value for k, v in ctrs.items()}

        return {
            "latencies": {
                "ttfa_ms": self.hist_ttfa.stats(),
                "stt_ms": self.hist_stt.stats(),
                "llm_first_token_ms": self.hist_llm_first_token.stats(),
                "tts_first_audio_ms": self.hist_tts_first_audio.stats(),
                "total_turn_ms": self.hist_total_turn.stats(),
                "cancel_latency_ms": self.hist_cancel_latency.stats(),
            },
            "sessions": {
                "total": self.sessions_total.value,
                "active": self.sessions_active.value,
                "reconnect": self.sessions_reconnect.value,
            },
            "turns": {
                "completed": self.turns_completed.value,
                "cancelled": self.turns_cancelled.value,
                "error": self.turns_error.value,
            },
            "audio": {
                "frames_received": self.frames_received.value,
                "frames_dropped": self.frames_dropped.value,
            },
            "providers": providers,
            "tools": tools,
        }


# Module-level accessor
def get_metrics() -> MetricsCollector:
    return MetricsCollector.instance()

