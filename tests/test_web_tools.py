import json
import socket

import httpx
import pytest

from backend.core import config
from backend.tools.web_tools import WebService, WebToolError


def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])


def test_search_returns_source_metadata_and_normalizes_results(monkeypatch):
    public_dns(monkeypatch)
    monkeypatch.setattr(config.settings, "WEB_SEARCH_ENDPOINT", "https://search.example.test/api")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": [{"title": "Example", "link": "https://example.com/page", "description": "A result"}]}))
    result = json.loads(WebService(httpx.Client(transport=transport)).search(query="voice agents", max_results=1))
    assert result["items"][0]["title"] == "Example"
    assert result["items"][0]["source"] == "example.com"
    assert result["retrieved_at"]


def test_fetch_extracts_text_and_rejects_private_hosts(monkeypatch):
    public_dns(monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<html><title>News</title><script>bad()</script><p>Hello <b>world</b></p></html>"))
    result = json.loads(WebService(httpx.Client(transport=transport)).fetch(url="https://example.com/news"))
    assert result["title"] == "News"
    assert "bad()" not in result["text"]
    assert "Hello world" in result["text"]
    with pytest.raises(WebToolError):
        WebService().fetch(url="http://127.0.0.1/admin")


def test_fetch_enforces_response_limit(monkeypatch):
    public_dns(monkeypatch)
    monkeypatch.setattr(config.settings, "WEB_MAX_RESPONSE_BYTES", 5)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="0123456789"))
    with pytest.raises(WebToolError, match="size limit"):
        WebService(httpx.Client(transport=transport)).fetch(url="https://example.com")
