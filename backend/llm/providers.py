"""Provider-neutral LangChain chat model construction."""
from typing import Any
from backend.core.config import Settings, settings

def _common_kwargs(config: Settings) -> dict[str, Any]:
    return {"temperature": 0.7, "max_tokens": 150, "timeout": config.PROVIDER_READ_TIMEOUT_SECONDS, "max_retries": config.PROVIDER_MAX_RETRIES}

def build_chat_model(config: Settings = settings):
    """Build the configured LangChain chat model lazily."""
    provider = config.LLM_PROVIDER
    model = config.active_llm_model
    kwargs = _common_kwargs(config)
    if provider == "groq":
        from langchain_groq import ChatGroq
        if not config.GROQ_API_KEY:
            return None
        return ChatGroq(model=model, api_key=config.GROQ_API_KEY, **kwargs)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not config.GEMINI_API_KEY:
            return None
        return ChatGoogleGenerativeAI(model=model, google_api_key=config.GEMINI_API_KEY, max_output_tokens=kwargs.pop("max_tokens"), **kwargs)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if not config.ANTHROPIC_API_KEY:
            return None
        return ChatAnthropic(model=model, anthropic_api_key=config.ANTHROPIC_API_KEY, **kwargs)
    if provider == "local":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=config.LOCAL_LLM_API_KEY, base_url=config.LLM_BASE_URL or "http://localhost:11434/v1", **kwargs)
    raise ValueError(f"Unsupported LLM provider: {provider}")
