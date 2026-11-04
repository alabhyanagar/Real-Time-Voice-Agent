"""Streaming LLM service backed by LangChain and a LangGraph boundary."""
import logging
from collections.abc import AsyncGenerator
from backend.core.config import settings
from backend.agent.graph import VoiceAgentGraph
from backend.agent.nodes import to_langchain_messages
from backend.agent.state import make_initial_state
from backend.llm.graph import VoiceAgentGraph as ToolVoiceAgentGraph
from backend.providers.llm.factory import build_provider
from backend.tools.registry import ToolRegistry
from backend.integrations.google_oauth import get_default_google_oauth_service
from backend.integrations.microsoft_oauth import get_default_microsoft_oauth_service
from backend.tools.schemas import ToolContext, ToolResult

logger = logging.getLogger("uvicorn.error")

class LLMService:
    """Expose one provider-neutral streaming interface to the pipeline."""
    def __init__(self, on_tool_event=None):
        self.model = build_provider(settings)
        self.on_tool_event = on_tool_event
        self.tool_registry = ToolRegistry()
        self.tools_enabled = False
        self.graph = VoiceAgentGraph(self.model)
        if settings.TOOLS_ENABLED and self.model is not None:
            try:
                self.graph = ToolVoiceAgentGraph(
                    self.model,
                    tools=self.tool_registry.tools,
                    tool_definitions=self.tool_registry.definitions,
                    max_tool_calls=settings.MAX_TOOL_CALLS_PER_TURN,
                    on_tool_event=on_tool_event,
                )
                self.tools_enabled = True
            except Exception as exc:
                logger.warning("Tool graph is unavailable; using tool-free graph: %s", exc)

    async def stream_response(
        self,
        conversation_history: list[dict[str, str]],
        *,
        session_id: str = "local-session",
        user_id: str = "anonymous",
        turn_id: str = "local-turn",
        generation_id: str = "local-generation",
        granted_scopes: frozenset[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks from the configured LangChain chat model."""
        try:
            if self.tools_enabled:
                state = make_initial_state(
                    conversation_history,
                    session_id=session_id,
                    user_id=user_id,
                    turn_id=turn_id,
                    generation_id=generation_id,
                )
                async for chunk in self.graph.astream(
                    to_langchain_messages(state),
                    session_id=session_id,
                    user_id=user_id,
                    turn_id=turn_id,
                    generation_id=generation_id,
                    granted_scopes=(
                        (granted_scopes or frozenset())
                        | get_default_google_oauth_service().scopes_for_user(user_id)
                        | get_default_microsoft_oauth_service().scopes_for_user(user_id)
                    ),
                ):
                    text = self._text_content(getattr(chunk, "content", chunk))
                    if text:
                        yield text
            else:
                async for text in self.graph.astream(
                    conversation_history,
                    session_id=session_id,
                    user_id=user_id,
                    turn_id=turn_id,
                    generation_id=generation_id,
                ):
                    yield text
        except Exception as exc:
            logger.error("Error streaming response from %s: %s", settings.LLM_PROVIDER, exc)
            yield "I encountered an error processing your request."

    async def resolve_tool_confirmation(self, confirmation_id: str, approved: bool, *, session_id: str, user_id: str, turn_id: str, generation_id: str) -> ToolResult | None:
        """Resume or reject a pending executor confirmation for this session."""
        if not self.tools_enabled:
            return None
        return await self.graph.resume_confirmation(
            confirmation_id,
            approved,
            session_id=session_id,
            turn_id=turn_id,
            generation_id=generation_id,
        )

    @staticmethod
    def _text_content(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
        return str(content or "")
