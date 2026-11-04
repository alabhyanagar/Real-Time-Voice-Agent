# Phase 6 — Web search and fetch

Phase 6 adds read-only public web tools to the opt-in LangChain tool graph.

## Safety and source contract

- `web_search` calls only the configured `WEB_SEARCH_ENDPOINT`, caps query size
  and result count, and returns each result's title, URL, hostname, snippet, and
  UTC retrieval timestamp.
- `web_fetch` accepts only HTTP(S), rejects embedded credentials, non-standard
  ports, localhost/private/link-local/reserved addresses, and domains outside
  `WEB_ALLOWED_DOMAINS` when an allow-list is configured.
- Redirect destinations are validated again before the request is followed.
- Response bytes, request timeout, and tool rate limits are bounded. HTML is
  reduced to readable text with scripts and styles removed.
- Tools are read-only and low risk. They never receive workspace content unless
  a future tool explicitly combines the two data boundaries.

## Configuration

Set `WEB_SEARCH_ENDPOINT` and optionally `WEB_SEARCH_API_KEY`. The endpoint is
provider-neutral so a deployment can use a managed provider (Brave, Tavily, or
an internal gateway) without changing the tool schema. Configure
`WEB_ALLOWED_DOMAINS` for a strict fetch allow-list.

## Verification

Mocked tests cover result normalization, source timestamps, HTML extraction,
private-host rejection, and response-size limits.
