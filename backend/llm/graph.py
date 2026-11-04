"""LangGraph boundary for the conversational response agent."""
import asyncio
from typing import Annotated, Awaitable, Callable, TypedDict, Sequence
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from backend.tools.registry import ToolDefinition

class VoiceAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

class VoiceAgentGraph:
    """Compiled graph and insertion point for tools and memory."""
    def __init__(
        self,
        model: BaseChatModel,
        tools: Sequence[BaseTool] = (),
        tool_definitions: Sequence[ToolDefinition] = (),
        max_tool_calls: int = 4,
        on_tool_event: Callable[[dict], Awaitable[None]] | None = None,
    ):
        self.model = model
        self.tools = list(tools)
        self.tool_definitions = {definition.tool.name: definition for definition in tool_definitions}
        self.max_tool_calls = max_tool_calls
        self.on_tool_event = on_tool_event
        self._tool_calls = 0
        self.bound_model = model.bind_tools(self.tools) if self.tools else model
        builder = StateGraph(VoiceAgentState)
        builder.add_node("respond", self._respond)
        builder.add_edge(START, "respond")
        if self.tools:
            builder.add_node("tools", self._run_tools)
            builder.add_conditional_edges("respond", tools_condition, {"tools": "tools", END: END})
            builder.add_edge("tools", "respond")
        else:
            builder.add_edge("respond", END)
        self.graph = builder.compile()

    async def _emit_tool_event(self, payload: dict):
        if self.on_tool_event is not None:
            await self.on_tool_event(payload)

    async def _run_tools(self, state: VoiceAgentState) -> dict[str, list[BaseMessage]]:
        """Execute model-selected tools with policy, timeout, and status hooks."""
        last_message = state["messages"][-1]
        tool_messages: list[BaseMessage] = []
        for call in getattr(last_message, "tool_calls", []):
            name = call.get("name", "unknown")
            call_id = call.get("id", name)
            definition = self.tool_definitions.get(name)
            await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "requested"})
            if definition is None:
                content = f"Tool '{name}' is not registered."
                await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "failed", "detail": content})
            elif self._tool_calls >= self.max_tool_calls:
                content = "The tool call limit for this turn has been reached."
                await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "failed", "detail": content})
            elif definition.requires_confirmation:
                content = "User confirmation is required before this tool can run."
                await self._emit_tool_event({
                    "tool_name": name,
                    "call_id": call_id,
                    "status": "confirmation_required",
                    "prompt": content,
                })
            else:
                self._tool_calls += 1
                await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "running"})
                try:
                    result = await asyncio.wait_for(
                        definition.tool.ainvoke(call.get("args", {})),
                        timeout=definition.timeout_seconds,
                    )
                    content = str(result)
                    await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "completed"})
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    content = f"Tool execution failed: {exc}"
                    await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "failed", "detail": str(exc)})
            tool_messages.append(ToolMessage(content=content, tool_call_id=call_id, name=name))
        return {"messages": tool_messages}

    async def _respond(self, state: VoiceAgentState) -> dict[str, list[BaseMessage]]:
        response = await self.bound_model.ainvoke(state["messages"])
        return {"messages": [response]}

    async def ainvoke(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        self._tool_calls = 0
        result = await self.graph.ainvoke(
            {"messages": messages},
            config={"recursion_limit": max(4, self.max_tool_calls * 2 + 2)},
        )
        return result["messages"]

    async def astream(self, messages: list[BaseMessage]):
        """Stream model chunks through the graph-owned model boundary."""
        if self.tools:
            result = await self.ainvoke(messages)
            if result:
                yield result[-1]
            return
        async for chunk in self.bound_model.astream(messages):
            yield chunk
