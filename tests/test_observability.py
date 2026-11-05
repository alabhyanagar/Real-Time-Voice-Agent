"""tests/test_observability.py

Unit tests for backend/observability/:
  - TurnEventBus publish/subscribe isolation
  - TurnTracer stage recording and latency arithmetic
  - MetricsCollector histogram accumulation and snapshot
  - CostTracker per-session and global cost accumulation
"""
import time
from backend.observability.events import TurnEvent, TurnEventBus, TurnEventType
from backend.observability.tracing import TurnTracer, get_tracer, register_tracer, unregister_tracer
from backend.observability.metrics import Counter, LatencyHistogram, MetricsCollector
from backend.observability.cost_tracking import CostTracker


def _make_event(event_type=TurnEventType.VAD_SPEECH_START):
    return TurnEvent(
        event_type=event_type,
        trace_id="trace-1",
        session_id="session-1",
        turn_id="turn-1",
    )


def test_turn_event_bus_publish_delivers_to_subscriber():
    TurnEventBus.reset()
    bus = TurnEventBus.instance()
    received = []

    def handler(event: TurnEvent) -> None:
        received.append(event)

    unsub = bus.subscribe(handler)
    bus.publish(_make_event())
    assert len(received) == 1
    assert received[0].event_type == TurnEventType.VAD_SPEECH_START
    unsub()
    TurnEventBus.reset()


def test_turn_event_bus_unsubscribe_stops_delivery():
    TurnEventBus.reset()
    bus = TurnEventBus.instance()
    received = []

    def handler(event: TurnEvent) -> None:
        received.append(event)

    unsub = bus.subscribe(handler)
    unsub()
    bus.publish(_make_event())
    assert len(received) == 0
    TurnEventBus.reset()


def test_turn_event_bus_multiple_subscribers():
    TurnEventBus.reset()
    bus = TurnEventBus.instance()
    counts = [0, 0]

    def h1(e):
        counts[0] += 1

    def h2(e):
        counts[1] += 1

    u1 = bus.subscribe(h1)
    u2 = bus.subscribe(h2)
    for _ in range(3):
        bus.publish(_make_event())
    assert counts[0] == 3
    assert counts[1] == 3
    u1()
    u2()
    TurnEventBus.reset()


def test_turn_tracer():
    TurnEventBus.reset()
    tracer = TurnTracer(session_id="s-1", turn_id="t-1", generation_id="g-1")
    tracer.mark(TurnEventType.VAD_SPEECH_START, publish=False)
    record = tracer.get(TurnEventType.VAD_SPEECH_START)
    assert record is not None
    assert record.event_type == TurnEventType.VAD_SPEECH_START

    # Idempotent mark
    t1 = record.monotonic_ns
    tracer.mark(TurnEventType.VAD_SPEECH_START, publish=False)
    assert tracer.get(TurnEventType.VAD_SPEECH_START).monotonic_ns == t1

    # Incomplete latencies return None
    assert tracer.ttfa_ms() is None
    assert tracer.latency_ms(TurnEventType.VAD_SPEECH_START, TurnEventType.STT_FINAL) is None

    # Completed stage
    time.sleep(0.001)
    tracer.mark(TurnEventType.STT_FINAL, publish=False)
    latency = tracer.latency_ms(TurnEventType.VAD_SPEECH_START, TurnEventType.STT_FINAL)
    assert latency is not None and latency >= 0

    # Summary keys
    s = tracer.summary()
    assert s["trace_id"] == tracer.trace_id
    assert "latencies_ms" in s

    # Registry
    register_tracer("s-1", tracer)
    assert get_tracer("s-1") is tracer
    unregister_tracer("s-1")
    assert get_tracer("s-1") is None


def test_latency_histogram():
    h = LatencyHistogram()
    assert h.stats()["count"] == 0
    assert h.stats()["p50"] is None

    for v in range(1, 101):
        h.record(float(v))
    st = h.stats()
    assert st["count"] == 100
    assert st["p50"] is not None
    assert st["p50"] <= st["p95"] <= st["p99"]


def test_counter():
    c = Counter()
    c.increment(5)
    assert c.value == 5
    c.decrement(2)
    assert c.value == 3
    c.decrement(10)
    assert c.value == 0
    c.increment(10)
    c.reset()
    assert c.value == 0


def test_metrics_collector():
    MetricsCollector.reset()
    m = MetricsCollector.instance()
    snap = m.snapshot()
    assert "latencies" in snap
    assert "providers" in snap
    assert "tools" in snap

    m.record_provider_success("groq")
    m.record_provider_failure("groq")
    m.record_provider_timeout("groq")
    m.record_tool_success("calendar_create")
    m.record_tool_confirmed("calendar_create")
    m.record_tool_rejected("send_email")
    m.record_session_start(reconnect=True)
    m.record_frames(received=50, dropped=1)
    m.record_session_end()

    snap = m.snapshot()
    assert snap["providers"]["groq"]["success"] == 1
    assert snap["tools"]["calendar_create"]["confirmed"] == 1
    assert snap["sessions"]["total"] == 1
    assert snap["sessions"]["reconnect"] == 1
    assert snap["audio"]["frames_received"] == 50
    assert snap["audio"]["frames_dropped"] == 1


def test_cost_tracker():
    CostTracker.reset()
    t = CostTracker.instance()
    c1 = t.record_llm_usage("s-1", "groq", "llama-3.3-70b-versatile", 1000, 500)
    assert c1 > 0
    c2 = t.record_stt_usage("s-1", "deepgram", 10.0)
    assert c2 > 0
    c3 = t.record_tts_usage("s-1", "cartesia", 500)
    assert c3 >= 0

    summary = t.session_summary("s-1")
    assert summary["llm_prompt_tokens"] == 1000
    assert summary["estimated_total_cost_usd"] > 0

    totals = t.global_totals()
    assert totals["llm_prompt_tokens"] == 1000
    assert totals["active_sessions"] == 1

    t.close_session("s-1")
    assert "error" in t.session_summary("s-1")
