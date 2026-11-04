"""PKCE OAuth and encrypted token lifecycle for delegated Microsoft Graph access."""

from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import urlencode

import httpx

from backend.core.config import settings
from backend.integrations.google_oauth import OAuthError, OAuthStateStore, SQLiteTokenStore, TokenStore


class MicrosoftOAuthService:
    """Keep Graph tokens per user; never expose them to prompts or audit data."""

    def __init__(self, state_store: OAuthStateStore | None = None, token_store: TokenStore | None = None, client: httpx.Client | None = None):
        self.states = state_store or OAuthStateStore()
        self.tokens = token_store or TokenStore()
        self.client = client

    def authorization_url(self, user_id: str, scopes: list[str]) -> dict:
        if not settings.MICROSOFT_OAUTH_CLIENT_ID or not settings.MICROSOFT_OAUTH_REDIRECT_URI:
            raise OAuthError("Microsoft OAuth client configuration is incomplete")
        requested = list(dict.fromkeys([*scopes, "offline_access"]))
        item = self.states.create(user_id, requested)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(item.code_verifier.encode()).digest()).rstrip(b"=").decode()
        params = {
            "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
            "redirect_uri": settings.MICROSOFT_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "response_mode": "query",
            "scope": " ".join(item.scopes),
            "state": item.state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return {"authorization_url": f"{settings.MICROSOFT_OAUTH_AUTHORIZE_URL}?{urlencode(params)}", "state": item.state, "expires_at": item.expires_at}

    def exchange_code(self, *, user_id: str, state: str, code: str) -> dict:
        item = self.states.consume(state, user_id)
        if not code or not settings.MICROSOFT_OAUTH_CLIENT_ID or not settings.MICROSOFT_OAUTH_CLIENT_SECRET:
            raise OAuthError("Microsoft OAuth client credentials or authorization code are incomplete")
        token = self._token_request({
            "code": code,
            "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
            "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
            "redirect_uri": settings.MICROSOFT_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
            "code_verifier": item.code_verifier,
        })
        token["scopes"] = list(item.scopes)
        token["issued_at"] = int(time.time())
        self.tokens.put(user_id, token)
        return {"scopes": token["scopes"], "expires_in": token.get("expires_in"), "stored": True}

    def refresh(self, user_id: str) -> dict:
        stored = self.tokens.get(user_id)
        if not stored or not stored.get("refresh_token"):
            raise OAuthError("No Microsoft refresh token is stored for this user")
        token = self._token_request({
            "refresh_token": stored["refresh_token"],
            "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
            "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
        token["refresh_token"] = token.get("refresh_token") or stored["refresh_token"]
        token["scopes"] = stored.get("scopes", [])
        token["issued_at"] = int(time.time())
        self.tokens.put(user_id, token)
        return token

    def token_for_user(self, user_id: str) -> dict | None:
        token = self.tokens.get(user_id)
        if token and token.get("expires_in") and token.get("issued_at"):
            if int(token["issued_at"]) + int(token["expires_in"]) - 60 <= time.time():
                token = self.refresh(user_id)
        return token

    def scopes_for_user(self, user_id: str) -> frozenset[str]:
        return self.tokens.scopes(user_id)

    def revoke(self, user_id: str) -> dict:
        # Microsoft does not expose a user-token revocation endpoint for this
        # delegated flow. Deleting the encrypted local token disconnects it.
        had_token = self.tokens.get(user_id) is not None
        self.tokens.delete(user_id)
        return {"revoked": had_token, "provider": "microsoft"}

    def _token_request(self, payload: dict) -> dict:
        client = self.client or httpx.Client(timeout=settings.GRAPH_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.post(settings.MICROSOFT_OAUTH_TOKEN_URL, data=payload, headers={"Accept": "application/json"})
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict) or not value.get("access_token"):
                raise OAuthError("Microsoft token response is invalid")
            return value
        except OAuthError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthError("Microsoft token exchange failed") from exc
        finally:
            if close:
                client.close()


_default_service: MicrosoftOAuthService | None = None


def get_default_microsoft_oauth_service() -> MicrosoftOAuthService:
    global _default_service
    if _default_service is None:
        _default_service = MicrosoftOAuthService(
            token_store=SQLiteTokenStore(
                settings.MICROSOFT_TOKEN_DB_PATH,
                settings.GOOGLE_OAUTH_ENCRYPTION_KEY or None,
                table_name="microsoft_tokens",
            )
        )
    return _default_service
