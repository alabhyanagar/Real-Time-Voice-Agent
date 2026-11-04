import asyncio

from langchain_core.tools import tool

from backend.tools.audit import InMemoryAuditLog
from backend.tools.executor import ToolExecutor
from backend.tools.registry import ToolDefinition, ToolRegistry
from backend.tools.schemas import ToolCallRequest, ToolContext
from backend.tools.safe_tools import calculate


def context(**overrides):
    values = {
        "session_id": "session-1",
        "user_id": "user-1",
        "turn_id": "turn-1",
        "generation_id": "generation-1",
    }
    values.update(overrides)
    return ToolContext(**values)


def test_safe_tool_execution_validates_arguments_and_audits():
    async def run():
        audit = InMemoryAuditLog()
        executor = ToolExecutor(ToolRegistry(), audit_log=audit)
        result = await executor.execute(
            ToolCallRequest(tool_name="calculate", call_id="call-1", arguments={"operation": "add", "left": 2, "right": 3}),
            context(),
        )
        assert result.status == "success"
        assert result.output == "5"
        assert [record.status for record in audit.records] == ["started", "success"]

    asyncio.run(run())


def test_unknown_tool_and_invalid_arguments_are_rejected():
    async def run():
        executor = ToolExecutor(ToolRegistry())
        unknown = await executor.execute(ToolCallRequest(tool_name="shell", call_id="call-1"), context())
        invalid = await executor.execute(
            ToolCallRequest(tool_name="calculate", call_id="call-2", arguments={"operation": "add", "left": "bad", "right": 1}),
            context(),
        )
        assert unknown.error_code == "UNKNOWN_TOOL"
        assert invalid.error_code == "INVALID_ARGUMENTS"

    asyncio.run(run())


def test_mutating_tool_requires_confirmation_then_can_be_consumed():
    @tool
    def change_value(value: str) -> str:
        """Change a value."""
        return value

    async def run():
        registry = ToolRegistry((ToolDefinition(change_value, risk_level="medium"),))
        executor = ToolExecutor(registry)
        request = ToolCallRequest(tool_name="change_value", call_id="call-1", arguments={"value": "new"})
        pending = await executor.execute(request, context())
        assert pending.status == "confirmation_required"
        completed = await executor.execute_confirmation(pending.confirmation_id, context())
        assert completed.status == "success"
        assert completed.output == "new"

    asyncio.run(run())


def test_idempotency_returns_the_original_result():
    async def run():
        executor = ToolExecutor(ToolRegistry())
        request = ToolCallRequest(
            tool_name="calculate",
            call_id="call-1",
            idempotency_key="same-operation",
            arguments={"operation": "multiply", "left": 4, "right": 5},
        )
        first = await executor.execute(request, context())
        second = await executor.execute(request.model_copy(update={"call_id": "call-2"}), context())
        assert first.output == second.output == "20"
        assert first.audit_id == second.audit_id

    asyncio.run(run())


def test_timeout_returns_retryable_failure():
    @tool
    async def slow_tool(delay: float) -> str:
        """Sleep for a requested duration."""
        await asyncio.sleep(delay)
        return "done"

    async def run():
        registry = ToolRegistry((ToolDefinition(slow_tool, timeout_seconds=0.01),))
        executor = ToolExecutor(registry)
        result = await executor.execute(
            ToolCallRequest(tool_name="slow_tool", call_id="call-1", arguments={"delay": 0.1}),
            context(),
        )
        assert result.status == "failed"
        assert result.error_code == "TOOL_TIMEOUT"
        assert result.retryable is True

    asyncio.run(run())


def test_rate_limit_is_enforced_per_user_and_tool():
    @tool
    def limited_tool() -> str:
        """Return a bounded value."""
        return "ok"

    async def run():
        executor = ToolExecutor(ToolRegistry((ToolDefinition(limited_tool, rate_limit=1),)))
        first = await executor.execute(ToolCallRequest(tool_name="limited_tool", call_id="one"), context())
        second = await executor.execute(ToolCallRequest(tool_name="limited_tool", call_id="two"), context())
        assert first.status == "success"
        assert second.status == "denied"
        assert second.error_code == "RATE_LIMITED"

    asyncio.run(run())


def test_declined_confirmation_is_audited_and_never_executes_tool():
    calls = []

    @tool
    def irreversible_change(value: str) -> str:
        """A change that must never run after rejection."""
        calls.append(value)
        return value

    async def run():
        audit = InMemoryAuditLog()
        executor = ToolExecutor(ToolRegistry((ToolDefinition(irreversible_change, risk_level="high"),)), audit_log=audit)
        pending = await executor.execute(
            ToolCallRequest(tool_name="irreversible_change", call_id="declined-1", arguments={"value": "no"}),
            context(),
        )
        result = await executor.reject_confirmation(pending.confirmation_id, context())
        assert result.status == "cancelled"
        assert result.error_code == "CONFIRMATION_DECLINED"
        assert calls == []
        assert audit.records[-1].status == "cancelled"

    asyncio.run(run())
