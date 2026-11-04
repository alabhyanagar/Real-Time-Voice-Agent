import asyncio

from langchain_core.messages import AIMessage

from backend.agent.graph import VoiceAgentGraph
from backend.agent.state import make_initial_state


class FakeChatModel:
    async def astream(self, _messages):
        for text in ("Hello", " there."):
            yield AIMessage(content=text)

    async def ainvoke(self, _messages):
        return AIMessage(content="Hello there.")


def test_step8_graph_streams_and_preserves_identity():
    async def run():
        graph = VoiceAgentGraph(FakeChatModel())
        chunks = []
        async for chunk in graph.astream(
            [{"role": "user", "content": "Hi"}],
            session_id="session-1",
            user_id="user-1",
            turn_id="turn-1",
            generation_id="generation-1",
        ):
            chunks.append(chunk)
        assert "".join(chunks) == "Hello there."
        assert graph.last_state["session_id"] == "session-1"
        assert graph.last_state["generation_id"] == "generation-1"

    asyncio.run(run())


def test_step8_compiled_graph_finalizes_turn_without_tools():
    async def run():
        graph = VoiceAgentGraph(FakeChatModel())
        state = make_initial_state([{"role": "user", "content": "Hi"}])
        result = await graph.ainvoke(state)
        assert result["response_text"] == "Hello there."
        assert result["tool_calls"] == []
        assert result["tool_results"] == []

    asyncio.run(run())
