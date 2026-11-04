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
    MEMORY_REDIS_REQUIRED: bool = False
    MEMORY_MAX_TURNS: int = 15
    MEMORY_MAX_TOKENS: int = 4_000
    MEMORY_TTL_SECONDS: int = 86_400
    MEMORY_CANCEL_TTL_SECONDS: int = 300
    MEMORY_SUMMARY_MAX_CHARS: int = 2_000
    MEMORY_MAX_MESSAGE_CHARS: int = 32_000
    POSTGRES_DSN: str = "postgresql+asyncpg://voice_agent:voice_agent@localhost:5432/voice_agent"
    CHROMA_PATH: str = "data/chroma"
    RAG_MAX_DOCUMENT_BYTES: int = 10_000_000
    RAG_CHUNK_SIZE: int = 900
    RAG_CHUNK_OVERLAP: int = 120
    RAG_TOP_K: int = 5

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
    TOOLS_ENABLED: bool = False
    WORKSPACE_ROOTS: List[str] = Field(default_factory=list)
    WORKSPACE_MAX_LIST_RESULTS: int = 100
    WORKSPACE_MAX_SEARCH_FILE_BYTES: int = 1_000_000
    WORKSPACE_MAX_READ_BYTES: int = 256_000
    WORKSPACE_MAX_READ_LINES: int = 300
    WORKSPACE_MAX_WRITE_BYTES: int = 256_000
    WORKSPACE_TRASH_DIR: str = ".voice_agent_trash"
    WORKSPACE_GIT_TIMEOUT_SECONDS: float = 15.0
    WORKSPACE_ALLOWED_EXTENSIONS: List[str] = Field(default_factory=list)
    WORKSPACE_SECRET_FILE_PATTERNS: List[str] = Field(default_factory=lambda: [".env", "*.pem", "*.key", "*secret*", "*credential*", "id_rsa", "id_ed25519"])
    WEB_SEARCH_ENDPOINT: str = ""
    WEB_SEARCH_API_KEY: str = ""
    WEB_ALLOWED_DOMAINS: List[str] = Field(default_factory=list)
    WEB_MAX_RESULTS: int = 10
    WEB_MAX_RESPONSE_BYTES: int = 1_000_000
    WEB_FETCH_TIMEOUT_SECONDS: float = 15.0
    WEB_USER_AGENT: str = "RealTimeVoiceAgent/1.0"
    GOOGLE_ACCESS_TOKEN: str = ""
    GOOGLE_API_BASE_URL: str = "https://www.googleapis.com"
    GOOGLE_TIMEOUT_SECONDS: float = 15.0
    GOOGLE_MAX_RESULTS: int = 20
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/v1/oauth/google/callback"
    GOOGLE_OAUTH_AUTHORIZE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_OAUTH_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    GOOGLE_OAUTH_REVOKE_URL: str = "https://oauth2.googleapis.com/revoke"
    GOOGLE_OAUTH_ENCRYPTION_KEY: str = ""
    GOOGLE_TOKEN_DB_PATH: str = "data/google_tokens.sqlite3"
    GRAPH_ACCESS_TOKEN: str = ""
    GRAPH_API_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    GRAPH_TIMEOUT_SECONDS: float = 15.0
    MICROSOFT_OAUTH_CLIENT_ID: str = ""
    MICROSOFT_OAUTH_CLIENT_SECRET: str = ""
    MICROSOFT_OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/v1/oauth/microsoft/callback"
    MICROSOFT_OAUTH_AUTHORIZE_URL: str = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    MICROSOFT_OAUTH_TOKEN_URL: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    MICROSOFT_TOKEN_DB_PATH: str = "data/microsoft_tokens.sqlite3"
    INTEGRATION_TIMEOUT_SECONDS: float = 15.0
    ESP32_BASE_URL: str = ""
    ESP32_API_KEY: str = ""
    MERN_API_BASE_URL: str = ""
    MERN_API_KEY: str = ""
    TELEPHONY_TIMEOUT_SECONDS: float = 15.0
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_API_BASE_URL: str = "https://api.twilio.com/2010-04-01"
    TWILIO_VOICE_WEBHOOK_URL: str = ""
    TWILIO_STATUS_CALLBACK_URL: str = ""
    TWILIO_ALLOWED_DESTINATIONS: List[str] = Field(default_factory=list)
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

        if self.MEMORY_MAX_TURNS < 1 or self.MEMORY_MAX_TOKENS < 128 or self.MEMORY_TTL_SECONDS <= 0 or self.MEMORY_CANCEL_TTL_SECONDS <= 0 or self.MEMORY_SUMMARY_MAX_CHARS < 100 or self.MEMORY_MAX_MESSAGE_CHARS < 1:
            raise ValueError("Conversation memory limits are invalid")
        if self.RAG_MAX_DOCUMENT_BYTES <= 0 or self.RAG_CHUNK_SIZE <= 0 or self.RAG_CHUNK_OVERLAP < 0 or self.RAG_CHUNK_OVERLAP >= self.RAG_CHUNK_SIZE or self.RAG_TOP_K <= 0:
            raise ValueError("RAG limits are invalid")

        if self.WS_RATE_LIMIT_PER_MINUTE <= 0 or self.WS_MAX_CONNECTIONS_PER_USER <= 0:
            raise ValueError("WebSocket rate and connection limits must be positive")

        if self.TOOL_EXECUTION_TIMEOUT_SECONDS <= 0 or self.MAX_TOOL_CALLS_PER_TURN <= 0:
            raise ValueError("Tool execution limits must be positive")

        if self.WORKSPACE_MAX_LIST_RESULTS <= 0:
            raise ValueError("WORKSPACE_MAX_LIST_RESULTS must be positive")

        if self.WORKSPACE_MAX_SEARCH_FILE_BYTES <= 0 or self.WORKSPACE_MAX_READ_BYTES <= 0 or self.WORKSPACE_MAX_READ_LINES <= 0:
            raise ValueError("Workspace file and line limits must be positive")

        if self.WORKSPACE_MAX_WRITE_BYTES <= 0:
            raise ValueError("WORKSPACE_MAX_WRITE_BYTES must be positive")
        trash_path = Path(self.WORKSPACE_TRASH_DIR)
        if trash_path.is_absolute() or ".." in trash_path.parts or not self.WORKSPACE_TRASH_DIR.strip():
            raise ValueError("WORKSPACE_TRASH_DIR must be a relative path inside each workspace root")
        if self.WORKSPACE_GIT_TIMEOUT_SECONDS <= 0:
            raise ValueError("WORKSPACE_GIT_TIMEOUT_SECONDS must be positive")

        if self.WEB_MAX_RESULTS <= 0 or self.WEB_MAX_RESPONSE_BYTES <= 0 or self.WEB_FETCH_TIMEOUT_SECONDS <= 0:
            raise ValueError("Web search and fetch limits must be positive")
        if not self.WEB_USER_AGENT.strip():
            raise ValueError("WEB_USER_AGENT cannot be empty")
        if self.GOOGLE_TIMEOUT_SECONDS <= 0 or self.GOOGLE_MAX_RESULTS <= 0:
            raise ValueError("Google Workspace limits must be positive")
        if self.GRAPH_TIMEOUT_SECONDS <= 0 or not self.GRAPH_API_BASE_URL.startswith("https://"):
            raise ValueError("Microsoft Graph configuration is invalid")
        if not self.MICROSOFT_OAUTH_AUTHORIZE_URL.startswith("https://") or not self.MICROSOFT_OAUTH_TOKEN_URL.startswith("https://"):
            raise ValueError("Microsoft OAuth endpoints must use HTTPS")
        if self.INTEGRATION_TIMEOUT_SECONDS <= 0:
            raise ValueError("INTEGRATION_TIMEOUT_SECONDS must be positive")
        if self.TELEPHONY_TIMEOUT_SECONDS <= 0 or not self.TWILIO_API_BASE_URL.startswith("https://"):
            raise ValueError("Telephony configuration is invalid")
        if not self.GOOGLE_API_BASE_URL.startswith("https://"):
            raise ValueError("GOOGLE_API_BASE_URL must use HTTPS")
        if not self.GOOGLE_OAUTH_AUTHORIZE_URL.startswith("https://") or not self.GOOGLE_OAUTH_TOKEN_URL.startswith("https://") or not self.GOOGLE_OAUTH_REVOKE_URL.startswith("https://"):
            raise ValueError("Google OAuth endpoints must use HTTPS")

        if self.JWT_EXPIRE_SECONDS <= 0:
            raise ValueError("JWT_EXPIRE_SECONDS must be positive")

        if self.ENVIRONMENT == "production":
            if not self.JWT_SECRET:
                raise ValueError("JWT_SECRET is required in production")
            if not self.GOOGLE_OAUTH_ENCRYPTION_KEY:
                raise ValueError("GOOGLE_OAUTH_ENCRYPTION_KEY is required in production")
            if not self.MEMORY_REDIS_REQUIRED:
                raise ValueError("MEMORY_REDIS_REQUIRED must be true in production")
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
