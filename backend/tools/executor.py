"""Policy-aware, bounded, idempotent tool execution."""
import asyncio
import time
from collections.abc import Awaitable, Callable
from collections import deque
from typing import Any
from uuid import uuid4

from .approval import ApprovalStore
from .audit import AuditRecord, InMemoryAuditLog, redact_arguments
from .context import current_tool_context
from .policies import decide
from .registry import ToolRegistry
from .schemas import ToolCallRequest, ToolContext, ToolResult


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        approvals: ApprovalStore | None = None,
        audit_log: InMemoryAuditLog | None = None,
        on_status: Callable[[dict], Awaitable[None]] | None = None,
    ):
        self.registry = registry
        self.approvals = approvals or ApprovalStore()
        self.audit_log = audit_log or InMemoryAuditLog()
        self.on_status = on_status
        self._idempotent_results: dict[str, ToolResult] = {}
        self._rate_windows: dict[tuple[str, str], deque[float]] = {}
        self._rate_lock = asyncio.Lock()

    async def _within_rate_limit(self, user_id: str, tool_name: str, limit: int | None) -> bool:
        if limit is None:
            return True
        now = time.monotonic()
        key = (user_id, tool_name)
        async with self._rate_lock:
            window = self._rate_windows.setdefault(key, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    async def _emit(self, payload: dict) -> None:
        if self.on_status:
            await self.on_status(payload)

    async def _audit(self, request: ToolCallRequest, context: ToolContext, status: str, **kwargs) -> AuditRecord:
        record = AuditRecord(
            tool_name=request.tool_name,
            call_id=request.call_id,
            user_id=context.user_id,
            session_id=context.session_id,
            status=status,
            arguments=redact_arguments(request.arguments),
            **kwargs,
        )
        await self.audit_log.append(record)
        return record

    async def execute(self, request: ToolCallRequest, context: ToolContext, *, confirmed: bool = False) -> ToolResult:
        try:
            definition = self.registry.get(request.tool_name)
        except KeyError:
            audit = await self._audit(request, context, "failed", detail="Unknown tool")
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="failed", error_code="UNKNOWN_TOOL", error_message="Tool is not registered", audit_id=audit.audit_id)

        decision = decide(
            risk_level=definition.risk_level,
            requires_confirmation=definition.requires_confirmation,
            required_scopes=definition.required_scopes,
            allowed_clients=definition.allowed_clients,
            context=context,
            confirmed=confirmed,
        )
        await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "requested"})
        if not await self._within_rate_limit(context.user_id, request.tool_name, definition.rate_limit):
            audit = await self._audit(request, context, "denied", detail="Tool rate limit exceeded")
            await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "failed", "detail": "Tool rate limit exceeded"})
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="denied", error_code="RATE_LIMITED", error_message="Tool rate limit exceeded", retryable=True, audit_id=audit.audit_id)
        if decision.action == "deny":
            audit = await self._audit(request, context, "denied", detail=decision.reason)
            await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "failed", "detail": decision.reason})
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="denied", error_code="POLICY_DENIED", error_message=decision.reason, audit_id=audit.audit_id)
        if decision.action == "confirm":
            confirmation = await self.approvals.find(request.tool_name, request.call_id, context.user_id)
            if confirmation is not None:
                # A LangGraph node is replayed on resume. Reuse its original
                # approval silently instead of prompting or auditing twice.
                return ToolResult(
                    tool_name=request.tool_name,
                    call_id=request.call_id,
                    status="confirmation_required",
                    confirmation_id=confirmation.confirmation_id,
                    error_message=confirmation.prompt,
                )
            confirmation = await self.approvals.create(request.tool_name, request.call_id, request.arguments, context.user_id, request.idempotency_key)
            audit = await self._audit(request, context, "confirmation_required", detail=confirmation.prompt)
            await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "confirmation_required", "prompt": confirmation.prompt, "confirmation_id": confirmation.confirmation_id})
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="confirmation_required", confirmation_id=confirmation.confirmation_id, error_message=confirmation.prompt, audit_id=audit.audit_id)

        if request.idempotency_key and request.idempotency_key in self._idempotent_results:
            return self._idempotent_results[request.idempotency_key]
        try:
            validated = definition.tool.args_schema.model_validate(request.arguments) if definition.tool.args_schema else request.arguments
            arguments = validated.model_dump() if hasattr(validated, "model_dump") else validated
        except Exception as exc:
            audit = await self._audit(request, context, "failed", detail="Invalid arguments")
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="failed", error_code="INVALID_ARGUMENTS", error_message=str(exc), audit_id=audit.audit_id)

        await self._audit(request, context, "started")
        await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "running"})
        started = time.monotonic()
        context_token = current_tool_context.set(context)
        try:
            output = await asyncio.wait_for(definition.tool.ainvoke(arguments), timeout=definition.timeout_seconds)
        except asyncio.CancelledError:
            await self._audit(request, context, "cancelled", duration_ms=int((time.monotonic() - started) * 1000))
            raise
        except TimeoutError:
            audit = await self._audit(request, context, "failed", detail="Tool timed out", duration_ms=int((time.monotonic() - started) * 1000))
            await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "failed", "detail": "Tool timed out"})
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="failed", error_code="TOOL_TIMEOUT", error_message="Tool timed out", retryable=True, audit_id=audit.audit_id)
        except Exception as exc:
            audit = await self._audit(request, context, "failed", detail=str(exc), duration_ms=int((time.monotonic() - started) * 1000))
            await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "failed", "detail": str(exc)})
            return ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="failed", error_code="TOOL_FAILED", error_message=str(exc), retryable=True, audit_id=audit.audit_id)
        finally:
            current_tool_context.reset(context_token)

        audit = await self._audit(request, context, "success", duration_ms=int((time.monotonic() - started) * 1000))
        result = ToolResult(tool_name=request.tool_name, call_id=request.call_id, status="success", output=output, audit_id=audit.audit_id)
        if request.idempotency_key:
            self._idempotent_results[request.idempotency_key] = result
        await self._emit({"tool_name": request.tool_name, "call_id": request.call_id, "status": "completed"})
        return result

    async def execute_confirmation(self, confirmation_id: str, context: ToolContext) -> ToolResult:
        pending = await self.approvals.consume(confirmation_id, context.user_id)
        if pending is None:
            return ToolResult(tool_name="unknown", call_id=confirmation_id, status="failed", error_code="INVALID_CONFIRMATION", error_message="Confirmation is missing, expired, or belongs to another user")
        request = ToolCallRequest(tool_name=pending.request.tool_name, arguments=pending.arguments, call_id=pending.request.call_id, idempotency_key=pending.idempotency_key)
        return await self.execute(request, context, confirmed=True)

    async def reject_confirmation(self, confirmation_id: str, context: ToolContext) -> ToolResult:
        """Cancel an approval without executing the requested action."""
        pending = await self.approvals.reject(confirmation_id, context.user_id)
        if pending is None:
            return ToolResult(
                tool_name="unknown",
                call_id=confirmation_id,
                status="failed",
                error_code="INVALID_CONFIRMATION",
                error_message="Confirmation is missing, expired, or belongs to another user",
            )
        request = ToolCallRequest(
            tool_name=pending.request.tool_name,
            arguments=pending.arguments,
            call_id=pending.request.call_id,
            idempotency_key=pending.idempotency_key,
        )
        audit = await self._audit(request, context, "cancelled", detail="User declined tool confirmation")
        await self._emit({
            "tool_name": request.tool_name,
            "call_id": request.call_id,
            "status": "failed",
            "detail": "User declined tool confirmation",
        })
        return ToolResult(
            tool_name=request.tool_name,
            call_id=request.call_id,
            status="cancelled",
            error_code="CONFIRMATION_DECLINED",
            error_message="Tool confirmation was declined",
            audit_id=audit.audit_id,
        )
