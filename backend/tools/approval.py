"""Short-lived in-memory confirmation requests for mutating tools."""
import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, Field


class ConfirmationRequest(BaseModel):
    confirmation_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    expires_at: float


@dataclass
class _PendingApproval:
    request: ConfirmationRequest
    arguments: dict
    user_id: str
    idempotency_key: str | None = None


class ApprovalStore:
    def __init__(self, ttl_seconds: float = 120.0):
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, _PendingApproval] = {}
        self._lock = asyncio.Lock()

    async def create(self, tool_name: str, call_id: str, arguments: dict, user_id: str, idempotency_key: str | None = None) -> ConfirmationRequest:
        # LangGraph re-enters an interrupted node when it resumes.  Reusing an
        # existing approval keeps that replay from producing a second prompt.
        async with self._lock:
            self._purge_expired_locked()
            for pending in self._pending.values():
                if (
                    pending.user_id == user_id
                    and pending.request.tool_name == tool_name
                    and pending.request.call_id == call_id
                ):
                    return pending.request
        confirmation_id = str(uuid4())
        request = ConfirmationRequest(
            confirmation_id=confirmation_id,
            tool_name=tool_name,
            call_id=call_id,
            prompt=f"Allow the assistant to run '{tool_name}'?",
            expires_at=time.time() + self.ttl_seconds,
        )
        async with self._lock:
            self._pending[confirmation_id] = _PendingApproval(request, dict(arguments), user_id, idempotency_key)
        return request

    def _purge_expired_locked(self) -> None:
        now = time.time()
        for confirmation_id, pending in tuple(self._pending.items()):
            if pending.request.expires_at < now:
                self._pending.pop(confirmation_id, None)

    async def find(self, tool_name: str, call_id: str, user_id: str) -> ConfirmationRequest | None:
        """Return the still-valid approval for one replayed graph node."""
        async with self._lock:
            self._purge_expired_locked()
            for pending in self._pending.values():
                if (
                    pending.user_id == user_id
                    and pending.request.tool_name == tool_name
                    and pending.request.call_id == call_id
                ):
                    return pending.request
        return None

    async def consume(self, confirmation_id: str, user_id: str) -> _PendingApproval | None:
        async with self._lock:
            self._purge_expired_locked()
            pending = self._pending.pop(confirmation_id, None)
        if pending is None or pending.user_id != user_id:
            return None
        return pending

    async def reject(self, confirmation_id: str, user_id: str) -> _PendingApproval | None:
        async with self._lock:
            self._purge_expired_locked()
            pending = self._pending.pop(confirmation_id, None)
        if pending is None or pending.user_id != user_id:
            return None
        return pending
