"""Streaming LLM service backed by LangChain and a LangGraph boundary."""
import logging
from typing import AsyncGenerator, Dict, List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from backend.core.config import settings
from backend.llm.graph import VoiceAgentGraph
from backend.providers.llm.factory import build_provider
from backend.tools.registry import ToolRegistry

logger = logging.getLogger("uvicorn.error")

class LLMService:
    """Expose one provider-neutral streaming interface to the pipeline."""
    def __init__(self, on_tool_event=None):
        self.model = build_provider(settings)
        self.tool_registry = ToolRegistry()
        self.graph = (
            VoiceAgentGraph(
                self.model,
                tools=self.tool_registry.tools,
                tool_definitions=self.tool_registry.definitions,
                max_tool_calls=settings.MAX_TOOL_CALLS_PER_TURN,
                on_tool_event=on_tool_event,
            )
            if self.model is not None
            else None
        )
        self.system_prompt = (
            "You are a helpful, friendly, and ultra-concise real-time voice assistant. "
            "Keep spoken responses short, usually one or two sentences. "
            "Do not use markdown, bullets, URLs, code blocks, or symbols that sound unnatural. "
            "Respond in the same language as the user."
        )

    def _messages(self, conversation_history: List[Dict[str, str]]):
        messages = [SystemMessage(content=self.system_prompt)]
        for item in conversation_history:
            if item.get("role") == "user":
                messages.append(HumanMessage(content=item.get("content", "")))
            elif item.get("role") == "assistant":
                messages.append(AIMessage(content=item.get("content", "")))
        return messages

    @staticmethod
    def _text_content(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
        return str(content or "")

    async def stream_response(self, conversation_history: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """Yield text chunks from the configured LangChain chat model."""
        if self.model is None:
            logger.error("Configured LLM provider is missing its API key or model endpoint.")
            yield "I'm sorry, my language model is not configured yet."
            return
        try:
            async for chunk in self.graph.astream(self._messages(conversation_history)):
                text = self._text_content(getattr(chunk, "content", chunk))
                if text:
                    yield text
        except Exception as exc:
            logger.error("Error streaming response from %s: %s", settings.LLM_PROVIDER, exc)
            yield "I encountered an error processing your request."
