"""LangGraph boundary for the conversational response agent."""
from typing import Annotated, Awaitable, Callable, TypedDict, Sequence
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from langgraph.types import Command, interrupt
from backend.tools.executor import ToolExecutor
from backend.tools.registry import ToolDefinition, ToolRegistry
from backend.tools.schemas import ToolCallRequest, ToolContext

class VoiceAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_id: str
    turn_id: str
    generation_id: str
    granted_scopes: frozenset[str]

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
        self._last_confirmation_result = None
        self.bound_model = model.bind_tools(self.tools) if self.tools else model
        self.executor = ToolExecutor(
            ToolRegistry(tool_definitions or None),
            on_status=self._emit_tool_event,
        )
        builder = StateGraph(VoiceAgentState)
        builder.add_node("respond", self._respond)
        builder.add_edge(START, "respond")
        if self.tools:
            builder.add_node("tools", self._run_tools)
            builder.add_conditional_edges("respond", tools_condition, {"tools": "tools", END: END})
            builder.add_edge("tools", "respond")
        else:
            builder.add_edge("respond", END)
        # Approval pauses must be resumable by the authenticated WebSocket
        # client.  Step 10 replaces this process-local checkpointer with a
        # durable store, but the graph contract is already native LangGraph.
        self.graph = builder.compile(checkpointer=InMemorySaver())

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
            if definition is None:
                content = f"Tool '{name}' is not registered."
                await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "failed", "detail": content})
            elif self._tool_calls >= self.max_tool_calls:
                content = "The tool call limit for this turn has been reached."
                await self._emit_tool_event({"tool_name": name, "call_id": call_id, "status": "failed", "detail": content})
            else:
                arguments = dict(call.get("args", {}))
                idempotency_key = arguments.pop("idempotency_key", None)
                request = ToolCallRequest(tool_name=name, call_id=call_id, arguments=arguments, idempotency_key=idempotency_key)
                context = ToolContext(
                    session_id=state.get("session_id", "legacy-session"),
                    user_id=state.get("user_id", "legacy-user"),
                    turn_id=state.get("turn_id", "legacy-turn"),
                    generation_id=state.get("generation_id", "legacy-generation"),
                    granted_scopes=state.get("granted_scopes", frozenset()),
                )
                result = await self.executor.execute(request, context)
                if result.status == "success":
                    self._tool_calls += 1
                    content = str(result.output)
                elif result.status == "confirmation_required":
                    decision = interrupt({
                        "kind": "tool_confirmation",
                        "confirmation_id": result.confirmation_id,
                        "tool_name": name,
                        "call_id": call_id,
                        "prompt": result.error_message or "User confirmation is required before this tool can run.",
                    })
                    if not isinstance(decision, dict) or decision.get("confirmation_id") != result.confirmation_id:
                        resumed = await self.executor.reject_confirmation(result.confirmation_id or "", context)
                    elif decision.get("approved") is True:
                        resumed = await self.executor.execute_confirmation(result.confirmation_id or "", context)
                    else:
                        resumed = await self.executor.reject_confirmation(result.confirmation_id or "", context)
                    self._last_confirmation_result = resumed
                    if resumed.status == "success":
                        self._tool_calls += 1
                        content = str(resumed.output)
                    else:
                        content = resumed.error_message or "The requested tool action was not completed."
                else:
                    content = result.error_message or "Tool execution failed."
            tool_messages.append(ToolMessage(content=content, tool_call_id=call_id, name=name))
        return {"messages": tool_messages}

    async def _respond(self, state: VoiceAgentState) -> dict[str, list[BaseMessage]]:
        response = await self.bound_model.ainvoke(state["messages"])
        return {"messages": [response]}

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        *,
        session_id: str = "legacy-session",
        user_id: str = "legacy-user",
        turn_id: str = "legacy-turn",
        generation_id: str = "legacy-generation",
        granted_scopes: frozenset[str] = frozenset(),
    ) -> list[BaseMessage]:
        self._tool_calls = 0
        config = self._thread_config(session_id, turn_id, generation_id)
        result = await self.graph.ainvoke(
            {
                "messages": messages,
                "session_id": session_id,
                "user_id": user_id,
                "turn_id": turn_id,
                "generation_id": generation_id,
                "granted_scopes": granted_scopes,
            },
            config={**config, "recursion_limit": max(4, self.max_tool_calls * 2 + 2)},
        )
        return result["messages"]

    @staticmethod
    def _thread_config(session_id: str, turn_id: str, generation_id: str) -> dict:
        return {"configurable": {"thread_id": f"{session_id}:{turn_id}:{generation_id}"}}

    async def resume_confirmation(
        self,
        confirmation_id: str,
        approved: bool,
        *,
        session_id: str,
        turn_id: str,
        generation_id: str,
    ):
        """Resume the exact LangGraph interrupt associated with one tool approval."""
        self._last_confirmation_result = None
        config = self._thread_config(session_id, turn_id, generation_id)
        await self.graph.ainvoke(
            Command(resume={"confirmation_id": confirmation_id, "approved": approved}),
            config={**config, "recursion_limit": max(4, self.max_tool_calls * 2 + 2)},
        )
        return self._last_confirmation_result

    async def astream(self, messages: list[BaseMessage], **context):
        """Stream model chunks through the graph-owned model boundary."""
        if self.tools:
            result = await self.ainvoke(messages, **context)
            if result:
                yield result[-1]
            return
        async for chunk in self.bound_model.astream(messages):
            yield chunk
