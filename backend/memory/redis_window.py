"""Redis-backed bounded conversation memory with a deterministic test fallback."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from backend.core.config import settings
from backend.core.lifecycle import runtime_resources

from .memory_policy import MemoryPolicy
from .summarizer import ConversationSummarizer, estimate_tokens


@dataclass
class MemorySnapshot:
    messages: list[dict[str, object]] = field(default_factory=list)
    summary: str = ""
    state: str = "idle"
    generation_id: str | None = None
    cancelled_generation_id: str | None = None
    updated_at_ms: int | None = None


class _InMemoryRedis:
    """Small async Redis subset used only when optional infrastructure is off."""

    def __init__(self):
        self.values: dict[str, Any] = {}
        self.expiry: dict[str, float] = {}

    def _live(self, key: str) -> Any:
        if key in self.expiry and self.expiry[key] <= time.time():
            self.values.pop(key, None)
            self.expiry.pop(key, None)
        return self.values.get(key)

    async def rpush(self, key: str, value: str):
        self.values.setdefault(key, []).append(value)

    async def lrange(self, key: str, start: int, end: int):
        values = self._live(key) or []
        return values[start:] if end == -1 else values[start : end + 1]

    async def hset(self, key: str, mapping: dict[str, str]):
        self.values.setdefault(key, {}).update(mapping)

    async def hgetall(self, key: str):
        return dict(self._live(key) or {})

    async def set(self, key: str, value: str, ex: int | None = None):
        self.values[key] = value
        if ex:
            self.expiry[key] = time.time() + ex

    async def get(self, key: str):
        return self._live(key)

    async def sadd(self, key: str, value: str):
        self.values.setdefault(key, set()).add(value)

    async def smembers(self, key: str):
        return set(self._live(key) or set())

    async def srem(self, key: str, value: str):
        self.values.setdefault(key, set()).discard(value)

    async def expire(self, key: str, seconds: int):
        self.expiry[key] = time.time() + seconds

    async def delete(self, *keys: str):
        for key in keys:
            self.values.pop(key, None)
            self.expiry.pop(key, None)


_fallback = _InMemoryRedis()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RedisMemoryWindow:
    """Bounded memory keyed by authenticated user and session, with TTL."""

    def __init__(self, redis_client: Any | None = None, *, policy: MemoryPolicy | None = None, summarizer: ConversationSummarizer | None = None):
        self.redis = redis_client or runtime_resources.redis or _fallback
        self.policy = policy or MemoryPolicy()
        self.summarizer = summarizer or ConversationSummarizer(max_chars=self.policy.summary_max_chars)

    def _keys(self, user_id: str, session_id: str) -> tuple[str, str, str]:
        self.policy.validate_identity(user_id, session_id)
        user = _digest(user_id)
        session = _digest(session_id)
        prefix = f"voice:memory:{user}:{session}"
        return f"{prefix}:messages", f"{prefix}:meta", f"voice:memory:{user}:sessions"

    async def _touch(self, *keys: str) -> None:
        for key in keys:
            await self.redis.expire(key, self.policy.ttl_seconds)

    async def register_session(self, user_id: str, session_id: str) -> None:
        _, _, index = self._keys(user_id, session_id)
        await self.redis.sadd(index, session_id)
        await self.redis.expire(index, self.policy.ttl_seconds)

    async def load(self, user_id: str, session_id: str) -> MemorySnapshot:
        messages_key, meta_key, _ = self._keys(user_id, session_id)
        raw_messages = await self.redis.lrange(messages_key, 0, -1)
        meta = await self.redis.hgetall(meta_key)
        messages = []
        for raw in raw_messages:
            try:
                item = json.loads(raw)
                if isinstance(item, dict):
                    messages.append(item)
            except (TypeError, ValueError):
                continue
        return MemorySnapshot(
            messages=messages,
            summary=str(meta.get("summary", "")),
            state=str(meta.get("state", "idle")),
            generation_id=meta.get("generation_id") or None,
            cancelled_generation_id=meta.get("cancelled_generation_id") or None,
            updated_at_ms=int(meta["updated_at_ms"]) if meta.get("updated_at_ms") else None,
        )

    async def append_turn(self, user_id: str, session_id: str, *, role: str, content: str, turn_id: str, metadata: dict[str, object] | None = None) -> MemorySnapshot:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Unsupported conversation role")
        if not content or len(content) > settings.MEMORY_MAX_MESSAGE_CHARS:
            raise ValueError("Conversation message is empty or exceeds the configured limit")
        messages_key, meta_key, _ = self._keys(user_id, session_id)
        await self.register_session(user_id, session_id)
        item = {"role": role, "content": content, "turn_id": turn_id, "timestamp_ms": int(time.time() * 1000)}
        if metadata:
            item["metadata"] = {key: value for key, value in metadata.items() if key in {"response_id", "generation_id"}}
        await self.redis.rpush(messages_key, json.dumps(item, separators=(",", ":")))
        await self._trim(user_id, session_id)
        await self.redis.hset(meta_key, {"updated_at_ms": str(int(time.time() * 1000))})
        await self._touch(messages_key, meta_key)
        return await self.load(user_id, session_id)

    async def _trim(self, user_id: str, session_id: str) -> None:
        messages_key, meta_key, _ = self._keys(user_id, session_id)
        original = await self.load(user_id, session_id)
        messages = list(original.messages)
        total = sum(estimate_tokens(str(item.get("content", ""))) for item in messages)
        while messages and (len(messages) > self.policy.max_turns or total > self.policy.max_tokens):
            removed = messages.pop(0)
            total -= estimate_tokens(str(removed.get("content", "")))
        evicted = original.messages[: len(original.messages) - len(messages)]
        if evicted:
            summary = await self.summarizer.summarize(evicted, original.summary)
            await self.redis.delete(messages_key)
            for item in messages:
                await self.redis.rpush(messages_key, json.dumps(item, separators=(",", ":")))
            await self.redis.hset(meta_key, {"summary": summary})

    async def set_session_state(self, user_id: str, session_id: str, *, state: str, generation_id: str | None = None) -> None:
        _, meta_key, _ = self._keys(user_id, session_id)
        await self.register_session(user_id, session_id)
        values = {"state": state, "updated_at_ms": str(int(time.time() * 1000))}
        if generation_id:
            values["generation_id"] = generation_id
        await self.redis.hset(meta_key, values)
        await self._touch(meta_key)

    async def cancel_generation(self, user_id: str, session_id: str, generation_id: str) -> None:
        _, meta_key, _ = self._keys(user_id, session_id)
        cancel_key = meta_key + ":cancel"
        await self.redis.hset(meta_key, {"cancelled_generation_id": generation_id})
        await self.redis.set(cancel_key, generation_id, ex=settings.MEMORY_CANCEL_TTL_SECONDS)
        await self._touch(meta_key, cancel_key)

    async def is_cancelled(self, user_id: str, session_id: str, generation_id: str) -> bool:
        _, meta_key, _ = self._keys(user_id, session_id)
        return await self.redis.get(meta_key + ":cancel") == generation_id

    async def delete_session(self, user_id: str, session_id: str) -> None:
        messages_key, meta_key, index = self._keys(user_id, session_id)
        await self.redis.delete(messages_key, meta_key, meta_key + ":cancel")
        if hasattr(self.redis, "srem"):
            await self.redis.srem(index, session_id)

    async def export_session(self, user_id: str, session_id: str) -> dict[str, object]:
        snapshot = await self.load(user_id, session_id)
        return {"session_id": session_id, "summary": snapshot.summary, "messages": snapshot.messages, "state": snapshot.state, "generation_id": snapshot.generation_id}

    async def export_user(self, user_id: str) -> dict[str, object]:
        index = f"voice:memory:{_digest(user_id)}:sessions"
        sessions = sorted(await self.redis.smembers(index))
        return {"user_id": user_id, "sessions": [await self.export_session(user_id, session) for session in sessions]}


_default_memory: RedisMemoryWindow | None = None


def get_default_memory() -> RedisMemoryWindow:
    global _default_memory
    if _default_memory is None:
        _default_memory = RedisMemoryWindow()
    return _default_memory
