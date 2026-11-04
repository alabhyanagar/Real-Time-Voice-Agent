"""Application resource lifecycle and readiness state."""

from dataclasses import dataclass, field

from backend.core.config import settings


@dataclass
class RuntimeResources:
    ready: bool = False
    redis: object | None = None
    postgres: object | None = None
    chroma: object | None = None
    dependencies: dict[str, str] = field(default_factory=dict)

    async def startup(self) -> None:
        self.dependencies = {"configuration": "ready", "telemetry": "configured"}
        if settings.MEMORY_REDIS_REQUIRED or settings.REQUIRE_EXTERNAL_SERVICES:
            try:
                import redis.asyncio as redis
                self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
                await self.redis.ping()
                self.dependencies["redis"] = "ready"

                if not settings.REQUIRE_EXTERNAL_SERVICES:
                    self.ready = True
                    return

                from sqlalchemy.ext.asyncio import create_async_engine
                self.postgres = create_async_engine(settings.POSTGRES_DSN, pool_pre_ping=True)
                async with self.postgres.connect() as connection:
                    await connection.execute(__import__("sqlalchemy").text("SELECT 1"))
                self.dependencies["postgres"] = "ready"

                import chromadb
                self.chroma = chromadb.PersistentClient(path=settings.CHROMA_PATH)
                self.chroma.heartbeat()
                self.dependencies["chroma"] = "ready"
            except Exception as exc:
                await self.shutdown()
                raise RuntimeError(f"External service startup failed: {exc}") from exc
        self.ready = True

    async def shutdown(self) -> None:
        for resource in (self.redis, self.postgres):
            if resource is None:
                continue
            if hasattr(resource, "dispose"):
                result = resource.dispose()
                if hasattr(result, "__await__"):
                    await result
                continue
            close = getattr(resource, "close", None)
            if close:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        self.redis = self.postgres = self.chroma = None
        self.ready = False


runtime_resources = RuntimeResources()
