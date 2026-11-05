"""backend/observability/cost_tracking.py

Per-session, per-provider cost tracking for the voice pipeline.

Tracks:
  - LLM token usage (prompt + completion) per provider per model.
  - STT audio-second usage per provider.
  - TTS character usage per provider.
  - Derived cost estimates using configurable per-unit pricing.
  - Per-session cost accumulation and totals.

Design constraints
------------------
- No raw API keys, JWTs, audio blobs, or transcript text are stored.
- All pricing tables are configurable via environment variables or the
  Settings object; defaults reflect approximate public list prices as of
  late 2026.
- Cost figures are ESTIMATES only, not billing-accurate.
- Thread-safe for the asyncio + audio-thread pipeline.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pricing tables (USD per unit)
# These are approximations; override via CostTracker.set_pricing().
# ---------------------------------------------------------------------------

_DEFAULT_LLM_PRICING: dict[str, dict[str, float]] = {
    # provider:model -> {prompt_per_1k, completion_per_1k}
    "groq:llama-3.3-70b-versatile": {"prompt_per_1k": 0.00059, "completion_per_1k": 0.00079},
    "groq:llama-3.1-8b-instant": {"prompt_per_1k": 0.00005, "completion_per_1k": 0.00008},
    "groq:whisper-large-v3": {"audio_per_minute": 0.00000},  # STT via Groq – free tier
    "gemini:gemini-2.0-flash": {"prompt_per_1k": 0.000075, "completion_per_1k": 0.0003},
    "anthropic:claude-sonnet-4-6": {"prompt_per_1k": 0.003, "completion_per_1k": 0.015},
    "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002},
}

_DEFAULT_STT_PRICING: dict[str, float] = {
    # provider -> USD per audio-second
    "deepgram": 0.0000083,  # ~$0.0083/min Nova-2
    "groq": 0.0,            # Whisper on Groq free tier
    "default": 0.0001,
}

_DEFAULT_TTS_PRICING: dict[str, float] = {
    # provider -> USD per 1000 characters
    "elevenlabs": 0.0003,
    "cartesia": 0.000065,
    "deepgram": 0.000015,
    "default": 0.0001,
}


@dataclass
class UsageSample:
    """A single recorded usage event."""

    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    audio_seconds: float = 0.0
    tts_characters: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class SessionCost:
    """Accumulated cost and usage for one WebSocket session."""

    session_id: str
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    stt_audio_seconds: float = 0.0
    tts_characters: int = 0
    total_cost_usd: float = 0.0
    samples: list[UsageSample] = field(default_factory=list)


class CostTracker:
    """
    Singleton cost and usage tracker.

    Usage::

        tracker = CostTracker.instance()
        tracker.record_llm_usage(
            session_id="s-1",
            provider="groq",
            model="llama-3.3-70b-versatile",
            prompt_tokens=350,
            completion_tokens=120,
        )
        tracker.record_stt_usage(session_id="s-1", provider="deepgram", audio_seconds=4.5)
        tracker.record_tts_usage(session_id="s-1", provider="cartesia", characters=280)

        summary = tracker.session_summary("s-1")
        totals = tracker.global_totals()
    """

    _singleton: CostTracker | None = None

    def __init__(self) -> None:
        self._sessions: dict[str, SessionCost] = {}
        self._lock = threading.Lock()
        self._llm_pricing = dict(_DEFAULT_LLM_PRICING)
        self._stt_pricing = dict(_DEFAULT_STT_PRICING)
        self._tts_pricing = dict(_DEFAULT_TTS_PRICING)

        # Global totals across all sessions
        self._global_llm_prompt_tokens = 0
        self._global_llm_completion_tokens = 0
        self._global_stt_audio_seconds = 0.0
        self._global_tts_characters = 0
        self._global_cost_usd = 0.0

    @classmethod
    def instance(cls) -> "CostTracker":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    @classmethod
    def reset(cls) -> None:
        """Reset singleton – for testing only."""
        cls._singleton = None

    # ------------------------------------------------------------------
    # Pricing configuration
    # ------------------------------------------------------------------

    def set_llm_pricing(self, provider_model_key: str, prompt_per_1k: float, completion_per_1k: float) -> None:
        """Override LLM pricing. Key format: 'provider:model'."""
        with self._lock:
            self._llm_pricing[provider_model_key] = {
                "prompt_per_1k": prompt_per_1k,
                "completion_per_1k": completion_per_1k,
            }

    def set_stt_pricing(self, provider: str, usd_per_audio_second: float) -> None:
        with self._lock:
            self._stt_pricing[provider] = usd_per_audio_second

    def set_tts_pricing(self, provider: str, usd_per_1k_chars: float) -> None:
        with self._lock:
            self._tts_pricing[provider] = usd_per_1k_chars

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _get_or_create_session(self, session_id: str) -> SessionCost:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionCost(session_id=session_id)
        return self._sessions[session_id]

    def close_session(self, session_id: str) -> None:
        """Remove session cost record (call when WebSocket session ends)."""
        with self._lock:
            self._sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Recording usage
    # ------------------------------------------------------------------

    def record_llm_usage(
        self,
        session_id: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """
        Record LLM token usage and return the estimated cost in USD.

        Never pass raw transcripts, keys, or JWT payloads as model names.
        """
        key = f"{provider}:{model}"
        pricing = self._llm_pricing.get(key) or self._llm_pricing.get("default", {})
        prompt_rate = pricing.get("prompt_per_1k", 0.001)
        completion_rate = pricing.get("completion_per_1k", 0.002)
        cost = (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate

        sample = UsageSample(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=cost,
        )

        with self._lock:
            sc = self._get_or_create_session(session_id)
            sc.llm_prompt_tokens += prompt_tokens
            sc.llm_completion_tokens += completion_tokens
            sc.total_cost_usd += cost
            sc.samples.append(sample)

            self._global_llm_prompt_tokens += prompt_tokens
            self._global_llm_completion_tokens += completion_tokens
            self._global_cost_usd += cost

        logger.debug(
            "LLM usage: session=%s provider=%s model=%s prompt=%d completion=%d cost=$%.6f",
            session_id, provider, model, prompt_tokens, completion_tokens, cost,
        )
        return cost

    def record_stt_usage(
        self,
        session_id: str,
        provider: str,
        audio_seconds: float,
    ) -> float:
        """Record STT audio duration and return estimated cost in USD."""
        rate = self._stt_pricing.get(provider, self._stt_pricing.get("default", 0.0001))
        cost = audio_seconds * rate

        sample = UsageSample(
            provider=provider,
            model="stt",
            audio_seconds=audio_seconds,
            estimated_cost_usd=cost,
        )

        with self._lock:
            sc = self._get_or_create_session(session_id)
            sc.stt_audio_seconds += audio_seconds
            sc.total_cost_usd += cost
            sc.samples.append(sample)

            self._global_stt_audio_seconds += audio_seconds
            self._global_cost_usd += cost

        return cost

    def record_tts_usage(
        self,
        session_id: str,
        provider: str,
        characters: int,
    ) -> float:
        """Record TTS character count and return estimated cost in USD."""
        rate = self._tts_pricing.get(provider, self._tts_pricing.get("default", 0.0001))
        cost = (characters / 1000) * rate

        sample = UsageSample(
            provider=provider,
            model="tts",
            tts_characters=characters,
            estimated_cost_usd=cost,
        )

        with self._lock:
            sc = self._get_or_create_session(session_id)
            sc.tts_characters += characters
            sc.total_cost_usd += cost
            sc.samples.append(sample)

            self._global_tts_characters += characters
            self._global_cost_usd += cost

        return cost

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def session_summary(self, session_id: str) -> dict[str, Any]:
        """Return a privacy-safe cost summary for one session."""
        with self._lock:
            sc = self._sessions.get(session_id)
        if sc is None:
            return {"session_id": session_id, "error": "not_found"}
        return {
            "session_id": sc.session_id,
            "llm_prompt_tokens": sc.llm_prompt_tokens,
            "llm_completion_tokens": sc.llm_completion_tokens,
            "stt_audio_seconds": round(sc.stt_audio_seconds, 3),
            "tts_characters": sc.tts_characters,
            "estimated_total_cost_usd": round(sc.total_cost_usd, 6),
        }

    def global_totals(self) -> dict[str, Any]:
        """Return aggregate stats across all sessions since startup."""
        with self._lock:
            return {
                "llm_prompt_tokens": self._global_llm_prompt_tokens,
                "llm_completion_tokens": self._global_llm_completion_tokens,
                "stt_audio_seconds": round(self._global_stt_audio_seconds, 3),
                "tts_characters": self._global_tts_characters,
                "estimated_total_cost_usd": round(self._global_cost_usd, 6),
                "active_sessions": len(self._sessions),
            }


def get_cost_tracker() -> CostTracker:
    return CostTracker.instance()

