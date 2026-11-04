"""Security and retention rules for short-term conversation memory."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.core.config import settings

_SESSION_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True)
class MemoryPolicy:
    """Centralized limits; user identity always comes from authenticated claims."""

    max_turns: int = settings.MEMORY_MAX_TURNS
    max_tokens: int = settings.MEMORY_MAX_TOKENS
    ttl_seconds: int = settings.MEMORY_TTL_SECONDS
    summary_max_chars: int = settings.MEMORY_SUMMARY_MAX_CHARS

    def validate_identity(self, user_id: str, session_id: str) -> tuple[str, str]:
        if not user_id or len(user_id) > 256 or any(ord(char) < 32 or ord(char) == 127 for char in user_id):
            raise ValueError("Authenticated user identity is invalid")
        if not session_id or not _SESSION_IDENTIFIER.fullmatch(session_id):
            raise ValueError("Session identifier is invalid")
        return user_id, session_id

    def clamp_turns(self, value: int | None = None) -> int:
        return max(1, min(value or self.max_turns, self.max_turns))

    def clamp_tokens(self, value: int | None = None) -> int:
        return max(128, min(value or self.max_tokens, self.max_tokens))
