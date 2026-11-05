from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.routers import (
    websocket_router,
    google_oauth_router,
    microsoft_oauth_router,
    memory_router,
    rag_router,
    metrics_router,
)
from backend.core.config import settings
from backend.core.lifecycle import runtime_resources
from backend.observability.metrics import get_metrics


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await runtime_resources.startup()
    # Start observability metrics subscriber inside the running event loop
    get_metrics().start()
    try:
        yield
    finally:
        get_metrics().stop()
        await runtime_resources.shutdown()


app = FastAPI(
    title="Real-Time Voice Agent Backend",
    version="1.0.0",
    description="Enterprise-grade cascade voice agent backend with async WebSocket streaming.",
    lifespan=lifespan,
)

# Configure strict CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(websocket_router.router, prefix="/api/v1")
app.include_router(google_oauth_router.router, prefix="/api/v1")
app.include_router(microsoft_oauth_router.router, prefix="/api/v1")
app.include_router(memory_router.router, prefix="/api/v1")
app.include_router(rag_router.router, prefix="/api/v1")
app.include_router(metrics_router.router, prefix="/api/v1")

# Mount frontend files
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(frontend_dir / "index.html"))

    @app.get("/app.js")
    async def get_app_js():
        return FileResponse(str(frontend_dir / "app_modular.js"), media_type="text/javascript")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "voice-agent-backend"}


@app.get("/livez")
async def liveness_check():
    return {"status": "alive", "service": "voice-agent-backend"}


@app.get("/readyz")
async def readiness_check():
    if not runtime_resources.ready:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "dependencies": runtime_resources.dependencies},
        )
    return {"status": "ready", "dependencies": runtime_resources.dependencies}
