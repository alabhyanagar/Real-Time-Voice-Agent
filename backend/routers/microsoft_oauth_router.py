"""Authenticated delegated Microsoft Graph OAuth endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.core.security import authenticate_http
from backend.integrations.google_oauth import OAuthError
from backend.integrations.microsoft_oauth import get_default_microsoft_oauth_service


router = APIRouter(prefix="/oauth/microsoft", tags=["microsoft-oauth"])


def _user_id(request: Request) -> str:
    claims = authenticate_http(request)
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(claims["sub"])


@router.get("/start")
async def microsoft_oauth_start(request: Request, scopes: str):
    requested = [scope.strip() for scope in scopes.split() if scope.strip()]
    try:
        return get_default_microsoft_oauth_service().authorization_url(_user_id(request), requested)
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/callback")
async def microsoft_oauth_callback(state: str, code: str):
    oauth = get_default_microsoft_oauth_service()
    pending = oauth.states.peek(state)
    if pending is None:
        raise HTTPException(status_code=400, detail="OAuth state is missing or expired")
    try:
        return {"connected": True, **oauth.exchange_code(user_id=pending.user_id, state=state, code=code)}
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/revoke")
async def microsoft_oauth_revoke(request: Request):
    return get_default_microsoft_oauth_service().revoke(_user_id(request))
