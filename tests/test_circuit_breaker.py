"""tests/test_circuit_breaker.py

Unit tests for backend/core/circuit_breaker.py:
  - State transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
  - Failure threshold trips
  - Recovery timeout evaluation
  - Half-open probe success and failure
  - Registry management and resets
"""
import time
from backend.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
    reset_circuit_breakers,
)


def test_circuit_breaker_starts_closed_and_allows_requests():
    cb = CircuitBreaker("test-provider", failure_threshold=3)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_failures_below_threshold_remain_closed():
    cb = CircuitBreaker("test-provider", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_exceeding_threshold_trips_to_open_and_blocks():
    cb = CircuitBreaker("test-provider", failure_threshold=3, recovery_timeout_seconds=10.0)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_success_resets_consecutive_failures_in_closed_state():
    cb = CircuitBreaker("test-provider", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    # Now one failure should not trip it
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_half_open_recovery_transition():
    cb = CircuitBreaker(
        "test-provider",
        failure_threshold=2,
        recovery_timeout_seconds=0.05,
        half_open_success_threshold=1,
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.06)  # wait for recovery timeout
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True

    # Successful probe resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_probe_failure_returns_to_open():
    cb = CircuitBreaker(
        "test-provider",
        failure_threshold=2,
        recovery_timeout_seconds=0.05,
        half_open_success_threshold=2,
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN

    # Probe fails -> immediately back to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_registry():
    reset_circuit_breakers()
    cb1 = get_circuit_breaker("groq")
    cb2 = get_circuit_breaker("groq")
    cb3 = get_circuit_breaker("deepgram")

    assert cb1 is cb2
    assert cb1 is not cb3
    assert cb1.name == "groq"
    assert cb3.name == "deepgram"
    reset_circuit_breakers()

