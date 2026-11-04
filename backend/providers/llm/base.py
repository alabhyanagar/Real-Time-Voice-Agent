"""Stable LLM provider boundary; LangChain models are implementation details."""
from typing import Any
from backend.core.config import Settings, settings
from backend.llm.providers import build_chat_model


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, provider: str = "unknown", retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


def build_provider(config: Settings = settings) -> Any:
    try:
        model = build_chat_model(config)
    except Exception as exc:
        raise ProviderError(str(exc), provider=config.LLM_PROVIDER, retryable=False) from exc
    return model
