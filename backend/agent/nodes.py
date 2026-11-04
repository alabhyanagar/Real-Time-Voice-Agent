"""Node functions for the Step 8 LangGraph conversational workflow."""
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .policies import validate_state_messages
from .prompts import build_system_prompt
from .state import AgentState


def load_context(state: AgentState) -> dict[str, Any]:
    """Normalize conversation and retrieved document context for the graph."""
    return {
        "messages": validate_state_messages(state.get("messages", [])),
        "retrieved_context": list(state.get("retrieved_context", [])),
    }


def to_langchain_messages(state: AgentState):
    messages = [SystemMessage(content=build_system_prompt(state.get("retrieved_context")))]
    for item in state.get("messages", []):
        if item.get("role") == "assistant":
            messages.append(AIMessage(content=item.get("content", "")))
        else:
            messages.append(HumanMessage(content=item.get("content", "")))
    return messages


def model_result_update(response: Any) -> dict[str, Any]:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
    usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None) or {}
    return {"model_response": response, "response_text": str(content or ""), "usage_metadata": dict(usage)}


def finalize_turn(state: AgentState) -> dict[str, Any]:
    response_text = state.get("response_text", "").strip()
    messages = list(state.get("messages", []))
    if response_text:
        messages.append({"role": "assistant", "content": response_text})
    return {"messages": messages, "response_text": response_text}
