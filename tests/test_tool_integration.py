import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from backend.llm.graph import VoiceAgentGraph
from backend.tools.registry import ToolRegistry
from backend.tools.registry import ToolDefinition


class FakeToolCallingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate",
                        "args": {"operation": "add", "left": 2, "right": 3},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="The answer is five.")


def test_model_selected_starter_tool_runs_through_executor():
    async def run():
        events = []

        async def on_event(payload):
            events.append(payload)

        registry = ToolRegistry()
        graph = VoiceAgentGraph(
            FakeToolCallingModel(),
            tools=registry.tools,
            tool_definitions=registry.definitions,
            on_tool_event=on_event,
        )
        result = await graph.ainvoke(
            [HumanMessage(content="What is 2 + 3?")],
            session_id="session-1",
            user_id="user-1",
            turn_id="turn-1",
            generation_id="generation-1",
        )
        assert result[-1].content == "The answer is five."
        assert [event["status"] for event in events] == ["requested", "running", "completed"]
        assert graph.executor.audit_log.records[-1].status == "success"

    asyncio.run(run())


def test_confirmation_uses_a_langgraph_interrupt_and_resumes_once():
    @tool
    def write_note(value: str) -> str:
        """Write one note after explicit approval."""
        return f"wrote:{value}"

    class ConfirmingModel:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content="", tool_calls=[{
                    "name": "write_note",
                    "args": {"value": "approved"},
                    "id": "write-1",
                    "type": "tool_call",
                }])
            return AIMessage(content="Your note was written.")

    async def run():
        events = []

        async def on_event(payload):
            events.append(payload)

        graph = VoiceAgentGraph(
            ConfirmingModel(),
            tools=[write_note],
            tool_definitions=[ToolDefinition(write_note, risk_level="medium", requires_confirmation=True)],
            on_tool_event=on_event,
        )
        await graph.ainvoke(
            [HumanMessage(content="Write a note")],
            session_id="session-approval",
            user_id="user-approval",
            turn_id="turn-approval",
            generation_id="generation-approval",
        )
        confirmation = next(event for event in events if event["status"] == "confirmation_required")
        result = await graph.resume_confirmation(
            confirmation["confirmation_id"],
            True,
            session_id="session-approval",
            turn_id="turn-approval",
            generation_id="generation-approval",
        )
        assert result.status == "success"
        assert result.output == "wrote:approved"
        assert graph.executor.audit_log.records[-1].status == "success"
        assert len([event for event in events if event["status"] == "confirmation_required"]) == 1

    asyncio.run(run())
