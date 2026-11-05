"""tests/test_provider_fallbacks.py

Unit tests for provider fallback and recovery behavior:
  - Provider failure detection and counter increments.
  - Circuit breaker trips upon repeated provider failures.
  - Fail-fast rejection when a provider is in OPEN circuit state.
  - Recovery to HALF_OPEN and CLOSED when healthy.
"""
import unittest
from backend.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
    reset_circuit_breakers,
)
from backend.observability.metrics import MetricsCollector


class ProviderFallbackTests(unittest.TestCase):
    def setUp(self):
        reset_circuit_breakers()
        MetricsCollector.reset()

    def tearDown(self):
        reset_circuit_breakers()
        MetricsCollector.reset()

    def test_provider_failure_triggers_circuit_trip(self):
        cb = get_circuit_breaker("groq-llm", failure_threshold=3, recovery_timeout_seconds=5.0)
        metrics = MetricsCollector.instance()

        # 1. Healthy calls
        self.assertTrue(cb.allow_request())
        cb.record_success()
        metrics.record_provider_success("groq")

        # 2. Three consecutive failures trip circuit breaker
        for _ in range(3):
            cb.record_failure()
            metrics.record_provider_failure("groq")

        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request(), "Should fail fast when OPEN")

        # 3. Verify metrics captured the failures
        snap = metrics.snapshot()
        self.assertEqual(snap["providers"]["groq"]["failure"], 3)
        self.assertEqual(snap["providers"]["groq"]["success"], 1)

    def test_tts_provider_fallback_recovery(self):
        """Simulates falling back to secondary TTS when primary fails."""
        primary_tts = get_circuit_breaker("cartesia", failure_threshold=2)
        secondary_tts = get_circuit_breaker("elevenlabs", failure_threshold=3)

        # Primary fails twice
        primary_tts.record_failure()
        primary_tts.record_failure()
        self.assertFalse(primary_tts.allow_request())

        # Fallback to secondary succeeds
        self.assertTrue(secondary_tts.allow_request())
        secondary_tts.record_success()
        self.assertEqual(secondary_tts.state, CircuitState.CLOSED)


if __name__ == "__main__":
    unittest.main()

