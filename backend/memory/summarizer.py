"""Bounded conversation summarization without persisting personal preferences."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence


def estimate_tokens(text: str) -> int:
    """Conservatively estimate tokens without adding a tokenizer dependency."""
    return max(1, (len(text) + 3) // 4)


class ConversationSummarizer:
    """Summarize evicted turns; an optional model callback can provide richer text."""

    def __init__(self, model: Callable[[str], Awaitable[str]] | None = None, max_chars: int = 2_000):
        self.model = model
        self.max_chars = max_chars

    async def summarize(self, messages: Sequence[dict[str, object]], existing: str = "") -> str:
        if not messages:
            return existing[: self.max_chars]
        transcript = " ".join(
            f"{str(message.get('role', 'unknown'))}: {str(message.get('content', ''))}"
            for message in messages
        )
        prompt = (
            "Summarize the conversation facts needed for continuity. Do not infer or "
            "store passwords, credentials, or personal preferences unless explicitly "
            "required for this turn. Existing summary: " + existing + " New turns: " + transcript
        )
        if self.model is not None:
            result = await self.model(prompt)
            return result.strip()[: self.max_chars]
        compact = " ".join(part.strip() for part in (existing, transcript) if part.strip())
        return compact[: self.max_chars]
