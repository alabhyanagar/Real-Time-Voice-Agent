"""tests/test_observability.py

Unit tests for backend/observability/:
  - TurnEventBus publish/subscribe isolation
  - TurnTracer stage recording and latency arithmetic
  - MetricsCollector histogram accumulation and snapshot
  - CostTracker per-session and global cost accumulation
"""
import asyncio
import time
import unittest

from backend.observability.events import TurnEvent, TurnEventBus, TurnEventType
from backend.observability.tracing import TurnTracer, get_tracer, register_tracer, unregister_tracer
from backend.observability.metrics import Counter, LatencyHistogram, MetricsCollector
from backend.observability.cost_tracking import CostTracker


class TurnEventBusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        TurnEventBus.reset()

    def _make_event(self, event_type=TurnEventType.VAD_SPEECH_START):
        return TurnEvent(
            event_type=event_type,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-1",
        )

    async def test_publish_delivers_to_subscriber(self):
        bus = TurnEventBus.instance()
        received: list[TurnEvent] = []

        async def handler(event: TurnEvent) -> None:
            received.append(event)

        unsub = bus.subscribe(handler)
        event = self._make_event()
        bus.publish(event)
        await asyncio.sleep(0.05)  # allow consumer task to run
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, TurnEventType.VAD_SPEECH_START)
        unsub()

    async def test_unsubscribe_stops_delivery(self):
        bus = TurnEventBus.instance()
        received: list[TurnEvent] = []

        async def handler(event: TurnEvent) -> None:
            received.append(event)

        unsub = bus.subscribe(handler)
        unsub()
        bus.publish(self._make_event())
        await asyncio.sleep(0.05)
        self.assertEqual(len(received), 0)

    async def test_multiple_subscribers_are_isolated(self):
        bus = TurnEventBus.instance()
        counts = [0, 0]

        async def h1(e): counts[0] += 1
        async def h2(e): counts[1] += 1

        u1 = bus.subscribe(h1)
        u2 = bus.subscribe(h2)
        for _ in range(3):
            bus.publish(self._make_event())
        await asyncio.sleep(0.1)
        self.assertEqual(counts[0], 3)
        self.assertEqual(counts[1], 3)
        u1()
        u2()


class TurnTracerTests(unittest.TestCase):
    def setUp(self):
        TurnEventBus.reset()

    def _tracer(self):
        return TurnTracer(session_id="s-1", turn_id="t-1", generation_id="g-1")

    def test_mark_records_stage(self):
        tracer = self._tracer()
        tracer.mark(TurnEventType.VAD_SPEECH_START, publish=False)
        record = tracer.get(TurnEventType.VAD_SPEECH_START)
        self.assertIsNotNone(record)
        self.assertEqual(record.event_type, TurnEventType.VAD_SPEECH_START)

    def test_mark_only_records_first_occurrence(self):
        tracer = self._tracer()
        tracer.mark(TurnEventType.STT_FINAL, publish=False)
        t1 = tracer.get(TurnEventType.STT_FINAL).monotonic_ns
        time.sleep(0.001)
        tracer.mark(TurnEventType.STT_FINAL, publish=False)
        t2 = tracer.get(TurnEventType.STT_FINAL).monotonic_ns
        self.assertEqual(t1, t2)

    def test_latency_ms_returns_none_when_stage_missing(self):
        tracer = self._tracer()
        tracer.mark(TurnEventType.VAD_SPEECH_END, publish=False)
        result = tracer.latency_ms(TurnEventType.VAD_SPEECH_END, TurnEventType.STT_FINAL)
        self.assertIsNone(result)

    def test_latency_ms_non_negative(self):
        tracer = self._tracer()
        tracer.mark(TurnEventType.VAD_SPEECH_END, publish=False)
        time.sleep(0.002)
        tracer.mark(TurnEventType.STT_FINAL, publish=False)
        latency = tracer.latency_ms(TurnEventType.VAD_SPEECH_END, TurnEventType.STT_FINAL)
        self.assertIsNotNone(latency)
        self.assertGreaterEqual(latency, 0)

    def test_ttfa_ms_returns_none_when_incomplete(self):
        tracer = self._tracer()
        tracer.mark(TurnEventType.VAD_SPEECH_END, publish=False)
        self.assertIsNone(tracer.ttfa_ms())

    def test_summary_has_required_keys(self):
        tracer = self._tracer()
        summary = tracer.summary()
        self.assertIn("trace_id", summary)
        self.assertIn("session_id", summary)
        self.assertIn("latencies_ms", summary)
        self.assertIn("ttfa", summary["latencies_ms"])

    def test_tracer_registry(self):
        tracer = self._tracer()
        register_tracer("s-1", tracer)
        retrieved = get_tracer("s-1")
        self.assertIs(retrieved, tracer)
        unregister_tracer("s-1")
        self.assertIsNone(get_tracer("s-1"))


class LatencyHistogramTests(unittest.TestCase):
    def test_empty_histogram_returns_none_stats(self):
        h = LatencyHistogram()
        stats = h.stats()
        self.assertEqual(stats["count"], 0)
        self.assertIsNone(stats["p50"])

    def test_records_and_computes_percentiles(self):
        h = LatencyHistogram()
        for v in range(1, 101):
            h.record(float(v))
        stats = h.stats()
        self.assertEqual(stats["count"], 100)
        self.assertAlmostEqual(stats["mean"], 50.5, delta=1.0)
        self.assertIsNotNone(stats["p50"])
        self.assertIsNotNone(stats["p95"])
        self.assertIsNotNone(stats["p99"])
        self.assertLessEqual(stats["p50"], stats["p95"])
        self.assertLessEqual(stats["p95"], stats["p99"])


class CounterTests(unittest.TestCase):
    def test_increment_and_decrement(self):
        c = Counter()
        c.increment(5)
        self.assertEqual(c.value, 5)
        c.decrement(2)
        self.assertEqual(c.value, 3)
        c.decrement(100)  # floors at 0
        self.assertEqual(c.value, 0)

    def test_reset(self):
        c = Counter()
        c.increment(10)
        c.reset()
        self.assertEqual(c.value, 0)


class MetricsCollectorTests(unittest.TestCase):
    def setUp(self):
        MetricsCollector.reset()
        TurnEventBus.reset()

    def test_snapshot_has_all_required_keys(self):
        m = MetricsCollector.instance()
        snap = m.snapshot()
        self.assertIn("latencies", snap)
        self.assertIn("sessions", snap)
        self.assertIn("turns", snap)
        self.assertIn("audio", snap)
        self.assertIn("providers", snap)
        self.assertIn("tools", snap)

    def test_provider_counters_accumulate(self):
        m = MetricsCollector.instance()
        m.record_provider_success("groq")
        m.record_provider_failure("groq")
        m.record_provider_timeout("groq")
        snap = m.snapshot()
        self.assertEqual(snap["providers"]["groq"]["success"], 1)
        self.assertEqual(snap["providers"]["groq"]["failure"], 1)
        self.assertEqual(snap["providers"]["groq"]["timeout"], 1)

    def test_tool_counters_accumulate(self):
        m = MetricsCollector.instance()
        m.record_tool_success("calendar_create")
        m.record_tool_confirmed("calendar_create")
        m.record_tool_rejected("send_email")
        snap = m.snapshot()
        self.assertEqual(snap["tools"]["calendar_create"]["success"], 1)
        self.assertEqual(snap["tools"]["calendar_create"]["confirmed"], 1)
        self.assertEqual(snap["tools"]["send_email"]["rejected"], 1)

    def test_session_tracking(self):
        m = MetricsCollector.instance()
        m.record_session_start()
        m.record_session_start(reconnect=True)
        m.record_session_end()
        snap = m.snapshot()
        self.assertEqual(snap["sessions"]["total"], 2)
        self.assertEqual(snap["sessions"]["active"], 1)
        self.assertEqual(snap["sessions"]["reconnect"], 1)

    def test_audio_frame_tracking(self):
        m = MetricsCollector.instance()
        m.record_frames(received=100, dropped=2)
        snap = m.snapshot()
        self.assertEqual(snap["audio"]["frames_received"], 100)
        self.assertEqual(snap["audio"]["frames_dropped"], 2)


class CostTrackerTests(unittest.TestCase):
    def setUp(self):
        CostTracker.reset()

    def test_llm_usage_accumulates(self):
        t = CostTracker.instance()
        cost = t.record_llm_usage(
            session_id="s-1",
            provider="groq",
            model="llama-3.3-70b-versatile",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        self.assertGreater(cost, 0)
        summary = t.session_summary("s-1")
        self.assertEqual(summary["llm_prompt_tokens"], 1000)
        self.assertEqual(summary["llm_completion_tokens"], 500)
        self.assertGreater(summary["estimated_total_cost_usd"], 0)

    def test_stt_usage_accumulates(self):
        t = CostTracker.instance()
        cost = t.record_stt_usage(session_id="s-1", provider="deepgram", audio_seconds=10.0)
        self.assertGreater(cost, 0)
        summary = t.session_summary("s-1")
        self.assertAlmostEqual(summary["stt_audio_seconds"], 10.0, places=2)

    def test_tts_usage_accumulates(self):
        t = CostTracker.instance()
        cost = t.record_tts_usage(session_id="s-1", provider="cartesia", characters=500)
        self.assertGreaterEqual(cost, 0)
        summary = t.session_summary("s-1")
        self.assertEqual(summary["tts_characters"], 500)

    def test_global_totals_aggregate_across_sessions(self):
        t = CostTracker.instance()
        t.record_llm_usage("s-1", "groq", "llama-3.3-70b-versatile", 200, 100)
        t.record_llm_usage("s-2", "gemini", "gemini-2.0-flash", 300, 150)
        totals = t.global_totals()
        self.assertEqual(totals["llm_prompt_tokens"], 500)
        self.assertEqual(totals["llm_completion_tokens"], 250)
        self.assertGreater(totals["estimated_total_cost_usd"], 0)

    def test_session_summary_not_found(self):
        t = CostTracker.instance()
        result = t.session_summary("nonexistent-session")
        self.assertIn("error", result)

    def test_close_session_removes_record(self):
        t = CostTracker.instance()
        t.record_llm_usage("s-close", "groq", "llama-3.1-8b-instant", 100, 50)
        t.close_session("s-close")
        result = t.session_summary("s-close")
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()

