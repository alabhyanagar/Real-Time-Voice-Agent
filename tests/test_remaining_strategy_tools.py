import json

import httpx

from backend.core import config
from backend.tools.graph_tools import GRAPH_MAIL_READ, GraphService
from backend.tools.integration_tools import IntegrationService
from backend.tools.web_tools import WebService


def test_web_source_tools_preserve_source_metadata():
    result = json.loads(WebService.summarize(source=json.dumps({"url": "https://example.com", "retrieved_at": "now", "text": "One fact is 42. Another fact is stable."})))
    assert result["source_url"] == "https://example.com"
    facts = json.loads(WebService.extract_facts(source=json.dumps({"url": "https://example.com", "text": "One fact is 42."})))
    assert facts["facts"]


def test_graph_adapter_uses_scopes_and_normalizes_results(monkeypatch):
    monkeypatch.setattr(config.settings, "GRAPH_API_BASE_URL", "https://graph.example/v1.0")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"value": [{"id": "mail-1"}]}))
    service = GraphService(httpx.Client(transport=transport), access_token="token", granted_scopes={GRAPH_MAIL_READ})
    result = json.loads(service.mail_search(query="invoice", max_results=1))
    assert result["items"][0]["id"] == "mail-1"


def test_integration_adapter_is_bounded_and_structured(monkeypatch):
    monkeypatch.setattr(config.settings, "MERN_API_BASE_URL", "https://mern.example/api")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"items": [{"id": "1"}]}))
    result = json.loads(IntegrationService(httpx.Client(transport=transport)).mern_search("users", "alice", 1))
    assert result["items"]["items"][0]["id"] == "1"
