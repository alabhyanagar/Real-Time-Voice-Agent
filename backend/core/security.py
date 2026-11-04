"""WebSocket authentication helpers."""

from typing import Any

from fastapi import WebSocket

from backend.core.config import settings


def authenticate_websocket(websocket: WebSocket) -> dict[str, Any] | None:
    """Return JWT claims, or a development identity when auth is not configured."""
    token = None
    authorization = websocket.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = getattr(websocket, "query_params", {}).get("token")

    if not settings.JWT_SECRET:
        if settings.ENVIRONMENT == "production":
            return None
        client = getattr(websocket, "client", None)
        return {"sub": f"anonymous:{getattr(client, 'host', 'local')}"}
    if not token:
        return None

    try:
        import jwt

        options: dict[str, Any] = {"algorithms": [settings.JWT_ALGORITHM]}
        if settings.JWT_ISSUER:
            options["issuer"] = settings.JWT_ISSUER
        if settings.JWT_AUDIENCE:
            options["audience"] = settings.JWT_AUDIENCE
        claims = jwt.decode(token, settings.JWT_SECRET, **options)
        if not claims.get("sub"):
            return None
        return claims
    except Exception:
        return None
