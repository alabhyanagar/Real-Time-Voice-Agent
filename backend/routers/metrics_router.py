"""backend/routers/metrics_router.py

Exposes observability data via REST endpoints.

Endpoints
---------
GET /api/v1/metrics           – full pipeline metrics snapshot
GET /api/v1/metrics/costs     – global cost and usage totals
GET /api/v1/metrics/session/{session_id}/cost – per-session cost summary

Access is intentionally left unprotected here (it only exposes aggregate
data, never raw transcripts, keys, or audio).  In production, place these
behind your existing JWT middleware or an internal network boundary.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.observability.metrics import get_metrics
from backend.observability.cost_tracking import get_cost_tracker

router = APIRouter(tags=["observability"])


@router.get("/metrics")
async def metrics_snapshot() -> JSONResponse:
    """Return a full runtime metrics snapshot including latency histograms,
    session counters, provider stats, and tool stats."""
    return JSONResponse(content=get_metrics().snapshot())


@router.get("/metrics/costs")
async def cost_totals() -> JSONResponse:
    """Return global cumulative cost and usage totals (estimates only)."""
    return JSONResponse(content=get_cost_tracker().global_totals())


@router.get("/metrics/session/{session_id}/cost")
async def session_cost(session_id: str) -> JSONResponse:
    """Return estimated cost and usage breakdown for one active session."""
    summary = get_cost_tracker().session_summary(session_id)
    if "error" in summary:
        return JSONResponse(status_code=404, content=summary)
    return JSONResponse(content=summary)

