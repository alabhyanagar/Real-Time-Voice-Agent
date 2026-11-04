import asyncio
from urllib.parse import parse_qs, urlparse

import httpx

from backend.core import config
from backend.integrations.google_oauth import OAuthStateStore, TokenStore
from backend.integrations.microsoft_oauth import MicrosoftOAuthService
from backend.routers.websocket_router import _claim_scopes
from backend.tools.context import current_tool_context
from backend.tools.graph_tools import GRAPH_MAIL_READ, GraphService, graph_mail_search
from backend.tools.schemas import ToolContext


def test_microsoft_pkce_exchange_is_user_bound_and_scoped(monkeypatch):
    monkeypatch.setattr(config.settings, "MICROSOFT_OAUTH_CLIENT_ID", "client")
    monkeypatch.setattr(config.settings, "MICROSOFT_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setattr(config.settings, "MICROSOFT_OAUTH_REDIRECT_URI", "http://localhost/callback")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}))
    service = MicrosoftOAuthService(state_store=OAuthStateStore(), token_store=TokenStore(), client=httpx.Client(transport=transport))
    request = service.authorization_url("user-1", [GRAPH_MAIL_READ])
    params = parse_qs(urlparse(request["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert "offline_access" in params["scope"][0]
    result = service.exchange_code(user_id="user-1", state=request["state"], code="code")
    assert result["stored"] is True
    assert GRAPH_MAIL_READ in service.scopes_for_user("user-1")


def test_graph_tool_uses_context_bound_user_token(monkeypatch):
    class StoredTokens:
        def token_for_user(self, user_id):
            assert user_id == "user-1"
            return {"access_token": "user-token"}

    captured = {}

    class FakeService(GraphService):
        def __init__(self, *, access_token=None, granted_scopes=frozenset()):
            captured["token"] = access_token
            captured["scopes"] = granted_scopes

        def mail_search(self, *, query, max_results=10):
            return '{"items":[]}'

    import backend.tools.graph_tools as graph_tools
    monkeypatch.setattr(graph_tools, "GraphService", FakeService)
    monkeypatch.setattr(graph_tools, "get_default_microsoft_oauth_service", lambda: StoredTokens())
    token = current_tool_context.set(ToolContext(
        session_id="session-1", user_id="user-1", turn_id="turn-1", generation_id="generation-1", granted_scopes=frozenset({GRAPH_MAIL_READ})
    ))
    try:
        assert graph_mail_search.invoke({"query": "invoice"}) == '{"items":[]}'
    finally:
        current_tool_context.reset(token)
    assert captured == {"token": "user-token", "scopes": frozenset({GRAPH_MAIL_READ})}


def test_websocket_claim_scope_normalization_is_server_side():
    assert _claim_scopes({"scope": "mern.read esp32.read"}) == frozenset({"mern.read", "esp32.read"})
    assert _claim_scopes({"scopes": ["Mail.Read", "Calendars.Read"]}) == frozenset({"Mail.Read", "Calendars.Read"})
    assert _claim_scopes({"scope": 123}) == frozenset()
