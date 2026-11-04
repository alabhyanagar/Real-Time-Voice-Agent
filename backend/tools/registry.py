"""Tool registration and policy metadata."""

from dataclasses import dataclass
from typing import Sequence

from langchain_core.tools import BaseTool

from .safe_tools import calculate, get_current_time


@dataclass(frozen=True)
class ToolDefinition:
    """A LangChain tool plus execution policy used by the agent graph."""

    tool: BaseTool
    requires_confirmation: bool = False
    timeout_seconds: float = 15.0


class ToolRegistry:
    """Explicit allow-list of tools exposed to the model."""

    def __init__(self, definitions: Sequence[ToolDefinition] | None = None):
        self.definitions = tuple(definitions or (
            ToolDefinition(calculate),
            ToolDefinition(get_current_time),
        ))
        names = [definition.tool.name for definition in self.definitions]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")

    @property
    def tools(self) -> list[BaseTool]:
        return [definition.tool for definition in self.definitions]

    def get(self, name: str) -> ToolDefinition:
        for definition in self.definitions:
            if definition.tool.name == name:
                return definition
        raise KeyError(f"Tool is not registered: {name}")
