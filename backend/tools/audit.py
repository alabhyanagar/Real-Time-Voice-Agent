"""Structured, redacted audit records for tool decisions and executions."""
import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    tool_name: str
    call_id: str
    user_id: str
    session_id: str
    status: Literal["requested", "allowed", "denied", "confirmation_required", "started", "success", "failed", "cancelled"]
    detail: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = None


_SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "authorization", "access_token", "refresh_token"}


def redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    return redact(arguments)


class InMemoryAuditLog:
    def __init__(self):
        self.records: list[AuditRecord] = []

    async def append(self, record: AuditRecord) -> AuditRecord:
        self.records.append(record)
        return record

    async def for_user(self, user_id: str) -> list[AuditRecord]:
        return [record for record in self.records if record.user_id == user_id]
