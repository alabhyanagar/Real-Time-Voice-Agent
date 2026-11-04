"""Safety and size policies for the tool-free conversational graph."""

MAX_MESSAGES = 30
MAX_MESSAGE_CHARS = 8_000


def validate_state_messages(messages: list[dict]) -> list[dict]:
    """Return a bounded copy so provider calls cannot grow without limit."""
    bounded = messages[-MAX_MESSAGES:]
    return [
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))[:MAX_MESSAGE_CHARS]}
        for item in bounded
    ]
