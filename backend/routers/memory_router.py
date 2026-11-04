"""Authenticated short-term conversation-memory controls."""

from fastapi import APIRouter, HTTPException, Request
import re

from backend.core.security import authenticate_http
from backend.memory import get_default_memory

router = APIRouter(prefix="/memory", tags=["conversation-memory"])


def _user_id(request: Request) -> str:
    claims = authenticate_http(request)
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(claims["sub"])


def _session_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
        raise HTTPException(status_code=400, detail="Invalid session identifier")
    return value


@router.get("")
async def export_memory(request: Request):
    """Export all retained short-term sessions for the authenticated user."""
    return await get_default_memory().export_user(_user_id(request))


@router.get("/{session_id}")
async def export_session_memory(request: Request, session_id: str):
    return await get_default_memory().export_session(_user_id(request), _session_id(session_id))


@router.delete("/{session_id}")
async def delete_session_memory(request: Request, session_id: str):
    session_id = _session_id(session_id)
    await get_default_memory().delete_session(_user_id(request), session_id)
    return {"deleted": True, "session_id": session_id}


@router.post("/{session_id}/forget")
async def forget_session_memory(request: Request, session_id: str):
    session_id = _session_id(session_id)
    await get_default_memory().delete_session(_user_id(request), session_id)
    return {"forgotten": True, "session_id": session_id}
