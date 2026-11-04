"""PKCE OAuth state and encrypted Google token lifecycle primitives."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings


class OAuthError(ValueError):
    """Raised when OAuth state, credentials, or token exchange is invalid."""


@dataclass(frozen=True)
class OAuthState:
    state: str
    user_id: str
    code_verifier: str
    scopes: tuple[str, ...]
    expires_at: float


class OAuthStateStore:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, OAuthState] = {}

    def create(self, user_id: str, scopes: list[str]) -> OAuthState:
        if not user_id or not scopes:
            raise OAuthError("OAuth user and scopes are required")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        item = OAuthState(state, user_id, verifier, tuple(dict.fromkeys(scopes)), time.time() + self.ttl_seconds)
        self._items[state] = item
        return item

    def consume(self, state: str, user_id: str) -> OAuthState:
        item = self._items.pop(state, None)
        if item is None or item.user_id != user_id or item.expires_at < time.time():
            raise OAuthError("OAuth state is missing, expired, or bound to another user")
        return item

    def peek(self, state: str) -> OAuthState | None:
        item = self._items.get(state)
        if item is None or item.expires_at < time.time():
            return None
        return item


class TokenStore:
    """Process-local encrypted token store; production should use durable KMS storage."""

    def __init__(self, encryption_key: str | None = None):
        key = encryption_key or settings.GOOGLE_OAUTH_ENCRYPTION_KEY or Fernet.generate_key().decode()
        try:
            self._fernet = Fernet(key.encode())
        except Exception as exc:
            raise OAuthError("GOOGLE_OAUTH_ENCRYPTION_KEY must be a valid Fernet key") from exc
        self._items: dict[str, bytes] = {}

    def put(self, user_id: str, token: dict) -> None:
        if not user_id or not isinstance(token, dict) or not token.get("access_token"):
            raise OAuthError("A user and access token are required")
        self._items[user_id] = self._fernet.encrypt(json.dumps(token, separators=(",", ":")).encode())

    def get(self, user_id: str) -> dict | None:
        encrypted = self._items.get(user_id)
        if encrypted is None:
            return None
        try:
            value = json.loads(self._fernet.decrypt(encrypted).decode())
        except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OAuthError("Stored Google token could not be decrypted") from exc
        return value if isinstance(value, dict) else None

    def delete(self, user_id: str) -> None:
        self._items.pop(user_id, None)

    def scopes(self, user_id: str) -> frozenset[str]:
        token = self.get(user_id) or {}
        return frozenset(token.get("scopes", []))


class SQLiteTokenStore(TokenStore):
    """Durable encrypted token store with one encrypted record per user."""

    def __init__(self, path: str, encryption_key: str | None = None, *, table_name: str = "google_tokens"):
        super().__init__(encryption_key)
        if table_name not in {"google_tokens", "microsoft_tokens"}:
            raise OAuthError("Token table name is not allowed")
        self.path = path
        self.table_name = table_name
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(f"CREATE TABLE IF NOT EXISTS {self.table_name} (user_id TEXT PRIMARY KEY, token BLOB NOT NULL)")

    def put(self, user_id: str, token: dict) -> None:
        super().put(user_id, token)
        encrypted = self._items[user_id]
        with sqlite3.connect(self.path) as connection:
            connection.execute(f"INSERT INTO {self.table_name}(user_id, token) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET token=excluded.token", (user_id, encrypted))

    def get(self, user_id: str) -> dict | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(f"SELECT token FROM {self.table_name} WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        encrypted = row[0]
        try:
            value = json.loads(self._fernet.decrypt(encrypted).decode())
        except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OAuthError("Stored Google token could not be decrypted") from exc
        return value if isinstance(value, dict) else None

    def delete(self, user_id: str) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(f"DELETE FROM {self.table_name} WHERE user_id = ?", (user_id,))

    def scopes(self, user_id: str) -> frozenset[str]:
        token = self.get(user_id) or {}
        return frozenset(token.get("scopes", []))


class GoogleOAuthService:
    def __init__(self, state_store: OAuthStateStore | None = None, token_store: TokenStore | None = None, client: httpx.Client | None = None):
        self.states = state_store or OAuthStateStore()
        self.tokens = token_store or TokenStore()
        self.client = client

    def authorization_url(self, user_id: str, scopes: list[str]) -> dict:
        if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
            raise OAuthError("Google OAuth client configuration is incomplete")
        item = self.states.create(user_id, scopes)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(item.code_verifier.encode()).digest()).rstrip(b"=").decode()
        params = {"client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI, "response_type": "code", "scope": " ".join(item.scopes), "access_type": "offline", "prompt": "consent", "state": item.state, "code_challenge": challenge, "code_challenge_method": "S256"}
        return {"authorization_url": f"{settings.GOOGLE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}", "state": item.state, "expires_at": item.expires_at}

    def exchange_code(self, *, user_id: str, state: str, code: str) -> dict:
        item = self.states.consume(state, user_id)
        if not code or not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
            raise OAuthError("Google OAuth client credentials or authorization code are incomplete")
        payload = {"code": code, "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET, "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI, "grant_type": "authorization_code", "code_verifier": item.code_verifier}
        result = self._token_request(payload)
        result["scopes"] = list(item.scopes)
        result["issued_at"] = int(time.time())
        self.tokens.put(user_id, result)
        return {"scopes": list(item.scopes), "expires_in": result.get("expires_in"), "stored": True}

    def refresh(self, user_id: str) -> dict:
        stored = self.tokens.get(user_id)
        if not stored or not stored.get("refresh_token"):
            raise OAuthError("No refresh token is stored for this user")
        result = self._token_request({"refresh_token": stored["refresh_token"], "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET, "grant_type": "refresh_token"})
        result["refresh_token"] = stored["refresh_token"]
        result["scopes"] = stored.get("scopes", [])
        result["issued_at"] = int(time.time())
        self.tokens.put(user_id, result)
        return {"scopes": result["scopes"], "expires_in": result.get("expires_in"), "refreshed": True}

    def scopes_for_user(self, user_id: str) -> frozenset[str]:
        return self.tokens.scopes(user_id)

    def revoke(self, user_id: str) -> dict:
        stored = self.tokens.get(user_id)
        if not stored:
            return {"revoked": False}
        token = stored.get("refresh_token") or stored.get("access_token")
        client = self.client or httpx.Client(timeout=settings.GOOGLE_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.post(settings.GOOGLE_OAUTH_REVOKE_URL, data={"token": token})
            if response.status_code not in {200, 204}:
                raise OAuthError("Google token revocation was rejected")
        except httpx.HTTPError as exc:
            raise OAuthError("Google token revocation failed") from exc
        finally:
            if close:
                client.close()
        self.tokens.delete(user_id)
        return {"revoked": True}

    def _token_request(self, payload: dict) -> dict:
        client = self.client or httpx.Client(timeout=settings.GOOGLE_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.post(settings.GOOGLE_OAUTH_TOKEN_URL, data=payload, headers={"Accept": "application/json"})
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict) or not value.get("access_token"):
                raise OAuthError("Google token response is invalid")
            return value
        except OAuthError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthError("Google token exchange failed") from exc
        finally:
            if close:
                client.close()


_default_service: GoogleOAuthService | None = None


def get_default_google_oauth_service() -> GoogleOAuthService:
    global _default_service
    if _default_service is None:
        _default_service = GoogleOAuthService(token_store=SQLiteTokenStore(settings.GOOGLE_TOKEN_DB_PATH, settings.GOOGLE_OAUTH_ENCRYPTION_KEY or None))
    return _default_service
