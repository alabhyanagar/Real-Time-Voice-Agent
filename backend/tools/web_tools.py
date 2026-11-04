"""Bounded, source-aware public web search and fetch tools."""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from langchain_core.tools import tool

from backend.core.config import settings


class WebToolError(ValueError):
    """Raised when a web request is unsafe or cannot be represented safely."""


class WebService:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    @staticmethod
    def _validate_url(url: str, *, allowed_domains: list[str] | None = None) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise WebToolError("Only public http(s) URLs are supported")
        if parsed.username or parsed.password:
            raise WebToolError("URLs with embedded credentials are not allowed")
        if parsed.port not in {None, 80, 443}:
            raise WebToolError("Non-standard URL ports are not allowed")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
            raise WebToolError("Local network hostnames are not allowed")
        try:
            address = ipaddress.ip_address(hostname)
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
                raise WebToolError("Private or special-use network addresses are not allowed")
        except ValueError:
            try:
                resolved = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            except OSError as exc:
                raise WebToolError("Unable to resolve public hostname") from exc
            for item in resolved:
                address = ipaddress.ip_address(item[4][0])
                if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
                    raise WebToolError("Hostname resolves to a private or special-use address")
        allowed = [domain.lower().lstrip(".") for domain in (allowed_domains or []) if domain.strip()]
        if allowed and not any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed):
            raise WebToolError("Domain is not in the configured web allow-list")
        return parsed.geturl()

    @staticmethod
    def _response_bytes(response: httpx.Response) -> bytes:
        raw = response.content
        if len(raw) > settings.WEB_MAX_RESPONSE_BYTES:
            raise WebToolError("Web response exceeds the configured size limit")
        return raw

    @staticmethod
    def _normalise_results(payload: object, query: str, max_results: int) -> list[dict]:
        if isinstance(payload, dict):
            candidates = payload.get("results") or payload.get("organic_results") or payload.get("web", {}).get("results", [])
            if not candidates and payload.get("RelatedTopics"):
                candidates = payload["RelatedTopics"]
        else:
            candidates = []
        output: list[dict] = []
        queue = list(candidates)
        while queue:
            item = queue.pop(0)
            if not isinstance(item, dict):
                continue
            nested = item.get("Topics")
            if nested:
                queue.extend(nested)
                continue
            url = item.get("url") or item.get("link")
            if not url:
                continue
            output.append({
                "title": str(item.get("title") or item.get("name") or url)[:300],
                "url": str(url),
                "snippet": str(item.get("snippet") or item.get("description") or item.get("text") or "")[:1000],
                "source": urlparse(str(url)).hostname,
            })
            if len(output) >= max_results:
                break
        return output

    def search(self, *, query: str, max_results: int = 5, domains: list[str] | None = None) -> str:
        query = query.strip()
        if not query or len(query) > 500:
            raise WebToolError("Search query must contain 1-500 characters")
        if max_results <= 0 or max_results > settings.WEB_MAX_RESULTS:
            raise WebToolError(f"max_results must be between 1 and {settings.WEB_MAX_RESULTS}")
        endpoint = settings.WEB_SEARCH_ENDPOINT.strip()
        if not endpoint:
            raise WebToolError("Web search is not configured")
        endpoint = self._validate_url(endpoint, allowed_domains=settings.WEB_ALLOWED_DOMAINS)
        params = {"q": query, "count": max_results, "format": "json"}
        headers = {"User-Agent": settings.WEB_USER_AGENT, "Accept": "application/json"}
        if settings.WEB_SEARCH_API_KEY:
            headers["Authorization"] = f"Bearer {settings.WEB_SEARCH_API_KEY}"
        client = self.client or httpx.Client(timeout=settings.WEB_FETCH_TIMEOUT_SECONDS, follow_redirects=False)
        close = self.client is None
        try:
            response = client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = json.loads(self._response_bytes(response))
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise WebToolError("Web search provider request failed") from exc
        finally:
            if close:
                client.close()
        results = self._normalise_results(payload, query, max_results)
        if domains:
            allowed_domains = [domain.lower().lstrip(".") for domain in domains]
            results = [item for item in results if item["source"] and any(item["source"] == domain or item["source"].endswith(f".{domain}") for domain in allowed_domains)]
        return json.dumps({"query": query, "retrieved_at": datetime.now(timezone.utc).isoformat(), "items": results}, separators=(",", ":"))

    def fetch(self, *, url: str, extract_text: bool = True) -> str:
        current = self._validate_url(url, allowed_domains=settings.WEB_ALLOWED_DOMAINS)
        client = self.client or httpx.Client(timeout=settings.WEB_FETCH_TIMEOUT_SECONDS, follow_redirects=False)
        close = self.client is None
        try:
            response = client.get(current, headers={"User-Agent": settings.WEB_USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise WebToolError("Redirect did not include a destination")
                current = self._validate_url(urljoin(current, location), allowed_domains=settings.WEB_ALLOWED_DOMAINS)
                response = client.get(current, headers={"User-Agent": settings.WEB_USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"})
            response.raise_for_status()
            raw = self._response_bytes(response)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            text = raw.decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise WebToolError("Web page request failed") from exc
        finally:
            if close:
                client.close()
        title = self._title(text)
        if extract_text and ("html" in content_type or not content_type):
            text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = html.unescape(re.sub(r"\s+", " ", text)).strip()
        return json.dumps({"url": current, "retrieved_at": datetime.now(timezone.utc).isoformat(), "content_type": content_type, "title": title, "text": text[: settings.WEB_MAX_RESPONSE_BYTES]}, separators=(",", ":"))

    @staticmethod
    def summarize(*, source: str, max_sentences: int = 5) -> str:
        if not source.strip() or len(source) > settings.WEB_MAX_RESPONSE_BYTES:
            raise WebToolError("Source text is empty or exceeds the configured size limit")
        if max_sentences <= 0 or max_sentences > 10:
            raise WebToolError("max_sentences must be between 1 and 10")
        try:
            payload = json.loads(source)
        except json.JSONDecodeError:
            payload = {"text": source}
        text = str(payload.get("text", ""))
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        return json.dumps({"summary": " ".join(sentences[:max_sentences]), "source_url": payload.get("url"), "retrieved_at": payload.get("retrieved_at")}, separators=(",", ":"))

    @staticmethod
    def extract_facts(*, source: str, max_facts: int = 20) -> str:
        if not source.strip() or len(source) > settings.WEB_MAX_RESPONSE_BYTES:
            raise WebToolError("Source text is empty or exceeds the configured size limit")
        if max_facts <= 0 or max_facts > 50:
            raise WebToolError("max_facts must be between 1 and 50")
        try:
            payload = json.loads(source)
        except json.JSONDecodeError:
            payload = {"text": source}
        text = str(payload.get("text", ""))
        facts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip() and (re.search(r"\b\d+(?:\.\d+)?\b", part) or re.search(r"\b(is|are|was|were|has|have|will|can)\b", part, re.I))]
        return json.dumps({"facts": facts[:max_facts], "source_url": payload.get("url"), "retrieved_at": payload.get("retrieved_at")}, separators=(",", ":"))

    @staticmethod
    def _title(text: str) -> str | None:
        match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
        return html.unescape(match.group(1).strip())[:300] if match else None


@tool
def web_search(query: str, max_results: int = 5, domains: list[str] | None = None) -> str:
    """Search configured public web sources and return timestamped results."""
    return WebService().search(query=query, max_results=max_results, domains=domains)


@tool
def web_fetch(url: str, extract_text: bool = True) -> str:
    """Fetch one public web page with SSRF and response-size protections."""
    return WebService().fetch(url=url, extract_text=extract_text)


@tool
def web_summarize(source: str, max_sentences: int = 5) -> str:
    """Summarize bounded fetched source text while preserving its source URL."""
    return WebService.summarize(source=source, max_sentences=max_sentences)


@tool
def web_extract_facts(source: str, max_facts: int = 20) -> str:
    """Extract bounded, source-linked factual sentences from fetched text."""
    return WebService.extract_facts(source=source, max_facts=max_facts)
