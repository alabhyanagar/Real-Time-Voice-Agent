"""Fast reference-aware query rewriting for conversational retrieval."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence


_REFERENCE = re.compile(r"\b(it|that|this|they|them|the previous (?:document|file|message)|above|earlier)\b", re.IGNORECASE)


class QueryRewriter:
    def __init__(self, model: Callable[[str], Awaitable[str]] | None = None):
        self.model = model

    def needs_rewrite(self, query: str) -> bool:
        return bool(_REFERENCE.search(query))

    async def rewrite(self, query: str, conversation: Sequence[dict[str, str]] | None = None) -> str:
        query = query.strip()
        if not query or not self.needs_rewrite(query):
            return query
        recent = [str(item.get("content", "")).strip() for item in (conversation or []) if str(item.get("content", "")).strip()]
        context = recent[-3:]
        prompt = "Rewrite this retrieval query as a standalone query. Query: " + query + " Context: " + " | ".join(context)
        if self.model is not None:
            result = (await self.model(prompt)).strip()
            if result:
                return result[:1_000]
        # Deterministic fallback is bounded and avoids an extra model round trip.
        if context:
            return f"{query} (conversation context: {context[-1][:500]})"
        return query
