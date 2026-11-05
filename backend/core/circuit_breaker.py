"""backend/core/circuit_breaker.py

Provider Circuit Breaker for external speech and language model APIs.

Prevents cascading latency and timeouts when an upstream provider
(Groq, Deepgram, Gemini, Cartesia, ElevenLabs) experiences degradation or outages.

States:
  CLOSED    -> Provider is healthy; calls proceed normally.
  OPEN      -> Threshold exceeded; calls fail-fast immediately.
  HALF_OPEN -> Recovery timeout elapsed; 1 probe call allowed to test health.
"""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum, unique
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@unique
class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when an operation is attempted while the circuit is open."""


class CircuitBreaker:
    """
    Circuit breaker for an individual external service provider.

    Parameters
    ----------
    name:
        Provider identifier (e.g. "groq", "deepgram", "cartesia").
    failure_threshold:
        Consecutive failures before opening the circuit (default: 5).
    recovery_timeout_seconds:
        Seconds to wait in OPEN state before trying a probe call (default: 30.0).
    half_open_success_threshold:
        Successful probe calls needed to reset from HALF_OPEN to CLOSED (default: 2).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._half_open_successes = 0
        self._last_state_change = time.monotonic()
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_state_change
                if elapsed >= self.recovery_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_successes = 0
                    self._last_state_change = time.monotonic()
                    logger.info("CircuitBreaker[%s]: OPEN -> HALF_OPEN (probing)", self.name)
            return self._state

    def allow_request(self) -> bool:
        """Check whether a request is allowed through the circuit."""
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful provider call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_success_threshold:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._half_open_successes = 0
                    self._last_state_change = time.monotonic()
                    logger.info("CircuitBreaker[%s]: HALF_OPEN -> CLOSED (recovered)", self.name)
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed or timed-out provider call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._last_state_change = time.monotonic()
                logger.warning("CircuitBreaker[%s]: HALF_OPEN probe failed -> OPEN", self.name)
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_state_change = time.monotonic()
                    logger.error(
                        "CircuitBreaker[%s]: %d consecutive failures -> OPEN (failing fast for %.1fs)",
                        self.name,
                        self._consecutive_failures,
                        self.recovery_timeout_seconds,
                    )

    def reset(self) -> None:
        """Manually reset circuit to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_successes = 0
            self._last_state_change = time.monotonic()


# Global registry of circuit breakers by provider name
_circuit_registry: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(provider_name: str, **kwargs: Any) -> CircuitBreaker:
    """Retrieve or create a singleton CircuitBreaker for a provider."""
    with _registry_lock:
        if provider_name not in _circuit_registry:
            _circuit_registry[provider_name] = CircuitBreaker(name=provider_name, **kwargs)
        return _circuit_registry[provider_name]


def reset_circuit_breakers() -> None:
    """Reset all circuit breakers (for testing)."""
    with _registry_lock:
        for cb in _circuit_registry.values():
            cb.reset()
        _circuit_registry.clear()

