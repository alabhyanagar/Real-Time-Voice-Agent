"""Authenticated Google OAuth lifecycle endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.core.config import settings
from backend.core.security import authenticate_http
from backend.integrations.google_oauth import OAuthError, get_default_google_oauth_service

router = APIRouter(prefix="/oauth/google", tags=["google-oauth"])
def _user_id(request: Request) -> str:
    claims = authenticate_http(request)
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(claims["sub"])


@router.get("/start")
async def google_oauth_start(request: Request, scopes: str):
    user_id = _user_id(request)
    oauth = get_default_google_oauth_service()
    requested = [scope.strip() for scope in scopes.split() if scope.strip()]
    try:
        return oauth.authorization_url(user_id, requested)
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/callback")
async def google_oauth_callback(request: Request, state: str, code: str):
    oauth = get_default_google_oauth_service()
    pending = oauth.states.peek(state)
    if pending is None:
        raise HTTPException(status_code=400, detail="OAuth state is missing or expired")
    try:
        result = oauth.exchange_code(user_id=pending.user_id, state=state, code=code)
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connected": True, **result}


@router.post("/revoke")
async def google_oauth_revoke(request: Request):
    user_id = _user_id(request)
    oauth = get_default_google_oauth_service()
    try:
        return oauth.revoke(user_id)
    except OAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
