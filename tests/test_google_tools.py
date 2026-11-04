import json

import httpx
import pytest

from backend.tools.google_tools import (
    CALENDAR_READ_SCOPE,
    GMAIL_READ_SCOPE,
    GoogleToolError,
    GoogleWorkspaceService,
)


def test_gmail_search_is_bounded_and_source_scoped():
    def handler(request):
        assert request.headers["authorization"] == "Bearer token"
        assert request.url.path.endswith("/gmail/v1/users/me/messages")
        return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}], "nextPageToken": "next"})

    service = GoogleWorkspaceService(httpx.Client(transport=httpx.MockTransport(handler)), access_token="token", granted_scopes={GMAIL_READ_SCOPE})
    result = json.loads(service.gmail_search(query="from:alerts", max_results=1))
    assert result["items"] == [{"id": "m1", "thread_id": "t1"}]
    assert result["next_page_token"] == "next"


def test_calendar_list_and_freebusy_use_read_only_scope():
    def handler(request):
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json={"items": [{"id": "event-1"}]})
        return httpx.Response(200, json={"calendars": {"primary": {"busy": []}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = GoogleWorkspaceService(client, access_token="token", granted_scopes={CALENDAR_READ_SCOPE})
    result = json.loads(service.calendar_list(time_min="2026-11-04T00:00:00Z", max_results=1))
    assert result["items"][0]["id"] == "event-1"
    with pytest.raises(GoogleToolError, match="scope"):
        service.calendar_freebusy(time_min="2026-11-04T00:00:00Z", time_max="2026-11-05T00:00:00Z", calendar_ids=["primary"])


def test_google_tools_reject_invalid_inputs():
    service = GoogleWorkspaceService(access_token="token", granted_scopes={GMAIL_READ_SCOPE})
    with pytest.raises(GoogleToolError, match="ISO-8601"):
        service.calendar_list(time_min="tomorrow")
    with pytest.raises(GoogleToolError, match="message ID"):
        service.gmail_read(message_id="bad/id")
