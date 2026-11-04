"""Typed request, context, and result models shared by every tool."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ToolRisk = Literal["low", "medium", "high"]
ToolStatus = Literal["success", "failed", "denied", "confirmation_required", "cancelled"]


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = Field(min_length=1, max_length=256)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)


class ToolContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    client_type: str = "web"
    granted_scopes: frozenset[str] = frozenset()


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    call_id: str
    status: ToolStatus
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    confirmation_id: str | None = None
    audit_id: str | None = None


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["allow", "confirm", "deny"]
    reason: str | None = None
    required_scopes: tuple[str, ...] = ()
