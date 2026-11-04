"""Typed application configuration for the voice agent.

The settings object intentionally keeps the existing provider-specific names
(`GROQ_MODEL`, `DEEPGRAM_API_KEY`, and so on) while adding provider-neutral
fields for the upcoming LangChain/LangGraph architecture.
"""

from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
ENV_FILES = (str(BACKEND_DIR / ".env"), str(PROJECT_ROOT / ".env"))


class Settings(BaseSettings):
    """Validated settings loaded from process environment and local env files."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime mode and model provider selection.
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"
    DEBUG: bool = False
    LLM_PROVIDER: Literal["groq", "gemini", "anthropic", "local"] = "groq"
    LLM_MODEL: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    STT_PROVIDER: Literal["deepgram"] = "deepgram"
    TTS_PROVIDER: Literal["elevenlabs", "deepgram"] = "elevenlabs"

    # Existing Groq configuration retained for backwards compatibility.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"

    # Future provider credentials. Empty values are valid in development when
    # that provider is not selected.
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LOCAL_LLM_API_KEY: str = "local-development-key"

    # Existing speech provider configuration.
    DEEPGRAM_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "JBFqnCBsd6RMkjVDRZzb"

    # Provider request controls.
    PROVIDER_CONNECT_TIMEOUT_SECONDS: float = 5.0
    PROVIDER_READ_TIMEOUT_SECONDS: float = 30.0
    PROVIDER_MAX_RETRIES: int = 2

    # WebSocket and audio limits. Enforcement will be added in later steps.
    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    WS_HEARTBEAT_SECONDS: int = 20
    WS_MAX_MESSAGE_BYTES: int = 64 * 1024
    AUDIO_SAMPLE_RATE: int = 16_000
    AUDIO_CHANNELS: int = 1
    AUDIO_SAMPLE_WIDTH_BYTES: int = 2

    # Storage configuration. Connections are initialized in the application
    # lifespan in a later step.
    REDIS_URL: str = "redis://localhost:6379/0"
    POSTGRES_DSN: str = "postgresql+asyncpg://voice_agent:voice_agent@localhost:5432/voice_agent"
    CHROMA_PATH: str = "data/chroma"

    # Authentication and policy configuration. Enforcement is intentionally
    # deferred to the gateway-hardening step.
    JWT_SECRET: Optional[str] = None
    JWT_ISSUER: Optional[str] = None
    JWT_AUDIENCE: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 3600
    REQUIRE_EXTERNAL_SERVICES: bool = False
    TOOL_EXECUTION_TIMEOUT_SECONDS: float = 15.0
    MAX_TOOL_CALLS_PER_TURN: int = 4
    WS_RATE_LIMIT_PER_MINUTE: int = 600
    WS_MAX_CONNECTIONS_PER_USER: int = 4
    VAD_SPEECH_ONSET_FRAMES: int = 2
    VAD_SILENCE_HANGOVER_FRAMES: int = 5

    # Observability configuration.
    TELEMETRY_ENABLED: bool = False
    LANGSMITH_TRACING: bool = False
    LANGSMITH_PROJECT: str = "real-time-voice-agent"

    @property
    def active_llm_model(self) -> str:
        """Return the configured model or a provider-specific default."""
        if self.LLM_MODEL:
            return self.LLM_MODEL
        defaults = {
            "groq": self.GROQ_MODEL,
            "gemini": "gemini-2.0-flash",
            "anthropic": "claude-3-5-haiku-latest",
            "local": "local-model",
        }
        return defaults[self.LLM_PROVIDER]

    @model_validator(mode="after")
    def validate_deployment_safety(self) -> "Settings":
        """Prevent unsafe production defaults without blocking local development."""

        if self.ENVIRONMENT == "production" and self.DEBUG:
            raise ValueError("DEBUG must be false when ENVIRONMENT=production")

        if self.ENVIRONMENT == "production" and "*" in self.ALLOWED_ORIGINS:
            raise ValueError("Wildcard origins are not allowed in production")

        if self.PROVIDER_MAX_RETRIES < 0:
            raise ValueError("PROVIDER_MAX_RETRIES cannot be negative")

        if self.WS_MAX_MESSAGE_BYTES <= 0:
            raise ValueError("WS_MAX_MESSAGE_BYTES must be positive")

        if self.WS_RATE_LIMIT_PER_MINUTE <= 0 or self.WS_MAX_CONNECTIONS_PER_USER <= 0:
            raise ValueError("WebSocket rate and connection limits must be positive")

        if self.TOOL_EXECUTION_TIMEOUT_SECONDS <= 0 or self.MAX_TOOL_CALLS_PER_TURN <= 0:
            raise ValueError("Tool execution limits must be positive")

        if self.JWT_EXPIRE_SECONDS <= 0:
            raise ValueError("JWT_EXPIRE_SECONDS must be positive")

        if self.ENVIRONMENT == "production":
            if not self.JWT_SECRET:
                raise ValueError("JWT_SECRET is required in production")
            selected_key = {
                "groq": self.GROQ_API_KEY,
                "gemini": self.GEMINI_API_KEY,
                "anthropic": self.ANTHROPIC_API_KEY,
            }.get(self.LLM_PROVIDER, "")
            if self.LLM_PROVIDER != "local" and not selected_key:
                raise ValueError(f"Credentials for LLM_PROVIDER={self.LLM_PROVIDER} are required in production")

        if self.AUDIO_SAMPLE_RATE not in (8_000, 16_000, 24_000, 48_000):
            raise ValueError("AUDIO_SAMPLE_RATE must be a supported PCM sample rate")

        return self


settings = Settings()
