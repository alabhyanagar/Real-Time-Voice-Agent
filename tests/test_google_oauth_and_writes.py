import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.core import config
from backend.integrations.google_oauth import GoogleOAuthService, OAuthError, OAuthStateStore, TokenStore
from backend.tools.google_tools import CALENDAR_EVENTS_SCOPE, GMAIL_SEND_SCOPE, GoogleToolError, GoogleWorkspaceService


def test_pkce_state_is_user_bound_and_token_store_is_encrypted(monkeypatch):
    monkeypatch.setattr(config.settings, "GOOGLE_OAUTH_CLIENT_ID", "client")
    monkeypatch.setattr(config.settings, "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/callback")
    store = TokenStore()
    service = GoogleOAuthService(state_store=OAuthStateStore(), token_store=store)
    request = service.authorization_url("user-1", [GMAIL_SEND_SCOPE])
    params = parse_qs(urlparse(request["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == [request["state"]]
    service.tokens.put("user-1", {"access_token": "secret", "refresh_token": "refresh"})
    assert service.tokens.get("user-1")["access_token"] == "secret"
    with pytest.raises(OAuthError):
        service.states.consume(request["state"], "other-user")


def test_code_exchange_stores_scoped_token(monkeypatch):
    monkeypatch.setattr(config.settings, "GOOGLE_OAUTH_CLIENT_ID", "client")
    monkeypatch.setattr(config.settings, "GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setattr(config.settings, "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/callback")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}))
    service = GoogleOAuthService(client=httpx.Client(transport=transport))
    request = service.authorization_url("user-1", [GMAIL_SEND_SCOPE])
    result = service.exchange_code(user_id="user-1", state=request["state"], code="code")
    assert result["stored"] is True
    assert service.tokens.get("user-1")["refresh_token"] == "refresh"


def test_write_calls_are_structured_and_scope_checked():
    def handler(request):
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "created"})

    service = GoogleWorkspaceService(httpx.Client(transport=httpx.MockTransport(handler)), access_token="token", granted_scopes={GMAIL_SEND_SCOPE, CALENDAR_EVENTS_SCOPE})
    sent = json.loads(service.gmail_send(to="person@example.com", subject="Hello", body="Message"))
    assert sent["message"]["id"] == "created"
    created = json.loads(service.calendar_create(summary="Demo", start="2026-11-04T10:00:00Z", end="2026-11-04T11:00:00Z"))
    assert created["event"]["id"] == "created"
    cancelled = json.loads(service.calendar_cancel(event_id="event-1"))
    assert cancelled["cancelled"] is True
    with pytest.raises(GoogleToolError, match="email"):
        service.gmail_send(to="not-an-email", subject="Hello", body="Message")
