"""Tool-free LangGraph runner with token streaming and cancellation support."""
import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.config import get_stream_writer

from .nodes import finalize_turn, load_context, model_result_update, to_langchain_messages
from .state import AgentState, make_initial_state


class VoiceAgentGraph:
    """Initial conversational graph; tools are deliberately not bound in Step 8."""

    def __init__(self, model):
        self.model = model
        self._last_state: AgentState | None = None
        builder = StateGraph(AgentState)
        builder.add_node("load_context", load_context)
        builder.add_node("call_model", self._call_model)
        builder.add_node("stream_response", self._stream_marker)
        builder.add_node("finalize_turn", finalize_turn)
        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "call_model")
        builder.add_edge("call_model", "stream_response")
        builder.add_edge("stream_response", "finalize_turn")
        builder.add_edge("finalize_turn", END)
        self.graph = builder.compile()

    async def _call_model(self, state: AgentState) -> dict[str, Any]:
        writer = get_stream_writer()
        if self.model is None:
            text = "I'm sorry, my language model is not configured yet."
            writer({"type": "text_delta", "text": text})
            return model_result_update(text)
        chunks = []
        async for chunk in self.model.astream(to_langchain_messages(state)):
            chunks.append(chunk)
            text = self._chunk_text(chunk)
            if text:
                writer({"type": "text_delta", "text": text})
        response_text = "".join(self._chunk_text(chunk) for chunk in chunks)
        return {"model_response": chunks[-1] if chunks else None, "response_text": response_text}

    async def _stream_marker(self, state: AgentState) -> dict[str, Any]:
        return {"response_text": state.get("response_text", "")}

    @staticmethod
    def _chunk_text(chunk: Any) -> str:
        content = getattr(chunk, "content", chunk)
        if isinstance(content, list):
            return "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
        return str(content or "")

    async def astream(
        self,
        messages: list[dict[str, str]],
        *,
        session_id: str = "local-session",
        user_id: str = "anonymous",
        turn_id: str = "local-turn",
        generation_id: str = "local-generation",
        retrieved_context: list[dict[str, Any]] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[str, None]:
        """Run graph stages while preserving provider token timing."""
        state = make_initial_state(
            messages,
            session_id=session_id,
            user_id=user_id,
            turn_id=turn_id,
            generation_id=generation_id,
            retrieved_context=retrieved_context,
        )
        response_text = ""
        final_state: AgentState | None = None
        try:
            streamed = False
            async for mode, payload in self.graph.astream(state, stream_mode=["custom", "updates"]):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError
                if mode == "custom" and isinstance(payload, dict) and payload.get("type") == "text_delta":
                    text = str(payload.get("text", ""))
                    if text:
                        streamed = True
                        response_text += text
                        yield text
                elif mode == "updates" and isinstance(payload, dict):
                    for node_output in payload.values():
                        if isinstance(node_output, dict):
                            state.update(node_output)
                    if "finalize_turn" in payload:
                        final_state = dict(state)
            if final_state is None:
                final_state = dict(state)
                final_state["response_text"] = response_text
                final_state.update(finalize_turn(final_state))
            if not streamed and final_state.get("response_text"):
                yield final_state["response_text"]
            self._last_state = final_state
        except asyncio.CancelledError:
            state["errors"] = [{"code": "CANCELLED", "message": "Graph generation cancelled"}]
            self._last_state = state
            raise

    async def ainvoke(self, state: AgentState) -> AgentState:
        """Execute the compiled graph for non-streaming callers and tests."""
        result = await self.graph.ainvoke(state)
        self._last_state = result
        return result

    @property
    def last_state(self) -> AgentState | None:
        return self._last_state
