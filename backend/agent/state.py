"""Structured state carried through the Step 8 conversational graph."""
from typing import Any, TypedDict


class AgentMessage(TypedDict):
    role: str
    content: str


class AgentState(TypedDict, total=False):
    messages: list[AgentMessage]
    session_id: str
    user_id: str
    turn_id: str
    generation_id: str
    retrieved_context: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    approval_state: dict[str, Any]
    errors: list[dict[str, Any]]
    usage_metadata: dict[str, Any]
    response_text: str
    model_response: Any


def make_initial_state(
    messages: list[AgentMessage],
    *,
    session_id: str = "local-session",
    user_id: str = "anonymous",
    turn_id: str = "local-turn",
    generation_id: str = "local-generation",
    retrieved_context: list[dict[str, Any]] | None = None,
) -> AgentState:
    return {
        "messages": list(messages),
        "session_id": session_id,
        "user_id": user_id,
        "turn_id": turn_id,
        "generation_id": generation_id,
        "retrieved_context": list(retrieved_context or []),
        "tool_calls": [],
        "tool_results": [],
        "approval_state": {"status": "not_required"},
        "errors": [],
        "usage_metadata": {},
        "response_text": "",
    }
