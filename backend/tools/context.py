"""Context-local identity available to connector tools during execution."""

from contextvars import ContextVar

from .schemas import ToolContext

current_tool_context: ContextVar[ToolContext | None] = ContextVar("current_tool_context", default=None)
