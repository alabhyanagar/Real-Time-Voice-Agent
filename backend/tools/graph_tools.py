"""Provider-neutral Microsoft Graph tools behind the same tool policy layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from backend.core.config import settings
from backend.integrations.microsoft_oauth import get_default_microsoft_oauth_service
from backend.tools.context import current_tool_context

GRAPH_MAIL_READ = "Mail.Read"
GRAPH_MAIL_WRITE = "Mail.ReadWrite"
GRAPH_MAIL_SEND = "Mail.Send"
GRAPH_CALENDAR_READ = "Calendars.Read"
GRAPH_CALENDAR_WRITE = "Calendars.ReadWrite"
GRAPH_FILES_READ = "Files.Read"
GRAPH_FILES_WRITE = "Files.ReadWrite"


class GraphToolError(ValueError):
    """Raised for unavailable or invalid Graph operations."""


class GraphService:
    def __init__(self, client: httpx.Client | None = None, *, access_token: str | None = None, granted_scopes: set[str] | frozenset[str] = frozenset()):
        self.client = client
        self.access_token = access_token if access_token is not None else settings.GRAPH_ACCESS_TOKEN
        self.granted_scopes = frozenset(granted_scopes)

    def _request(self, method: str, path: str, *, scope: str, params: dict | None = None, body: dict | None = None) -> dict:
        if not self.access_token:
            raise GraphToolError("Microsoft Graph access token is not configured")
        if scope not in self.granted_scopes:
            raise GraphToolError(f"Microsoft Graph scope is not granted: {scope}")
        client = self.client or httpx.Client(timeout=settings.GRAPH_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.request(method, f"{settings.GRAPH_API_BASE_URL.rstrip('/')}{path}", headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}, params=params, json=body)
            if response.status_code in {401, 403}:
                raise GraphToolError("Microsoft Graph authorization was rejected")
            response.raise_for_status()
            return response.json() if response.content else {}
        except GraphToolError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise GraphToolError("Microsoft Graph request failed") from exc
        finally:
            if close:
                client.close()

    def mail_search(self, *, query: str, max_results: int = 10) -> str:
        payload = self._request("GET", "/me/messages", scope=GRAPH_MAIL_READ, params={"$search": f'"{query[:200]}"', "$top": max_results, "$select": "id,subject,from,receivedDateTime"})
        return json.dumps({"items": payload.get("value", [])[:max_results], "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def mail_read(self, *, message_id: str) -> str:
        if not message_id or "/" in message_id:
            raise GraphToolError("Invalid Graph message ID")
        payload = self._request("GET", f"/me/messages/{quote(message_id, safe='')}", scope=GRAPH_MAIL_READ)
        return json.dumps({"message": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def mail_draft(self, *, to: str, subject: str, body: str) -> str:
        payload = self._request("POST", "/me/messages", scope=GRAPH_MAIL_WRITE, body={"subject": subject[:300], "body": {"contentType": "Text", "content": body[:100000]}, "toRecipients": [{"emailAddress": {"address": to}}]})
        return json.dumps({"draft": payload}, separators=(",", ":"))

    def mail_send(self, *, to: str, subject: str, body: str) -> str:
        self._request("POST", "/me/sendMail", scope=GRAPH_MAIL_SEND, body={"message": {"subject": subject[:300], "body": {"contentType": "Text", "content": body[:100000]}, "toRecipients": [{"emailAddress": {"address": to}}]}})
        return json.dumps({"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_list(self, *, start: str, end: str, max_results: int = 10) -> str:
        payload = self._request("GET", "/me/calendarView", scope=GRAPH_CALENDAR_READ, params={"startDateTime": start, "endDateTime": end, "$top": max_results})
        return json.dumps({"items": payload.get("value", [])[:max_results], "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_find_time(self, *, attendees: list[str], duration_minutes: int = 30) -> str:
        payload = self._request("POST", "/me/findMeetingTimes", scope=GRAPH_CALENDAR_READ, body={"attendees": [{"emailAddress": {"address": item}, "type": "required"} for item in attendees[:20]], "meetingDuration": f"PT{duration_minutes}M"})
        return json.dumps({"suggestions": payload.get("meetingTimeSuggestions", []), "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_create(self, *, subject: str, start: str, end: str, attendees: list[str] | None = None) -> str:
        payload = self._request("POST", "/me/events", scope=GRAPH_CALENDAR_WRITE, body={"subject": subject[:300], "start": {"dateTime": start, "timeZone": "UTC"}, "end": {"dateTime": end, "timeZone": "UTC"}, "attendees": [{"emailAddress": {"address": item}, "type": "required"} for item in (attendees or [])[:20]]})
        return json.dumps({"event": payload}, separators=(",", ":"))

    def calendar_update(self, *, event_id: str, subject: str | None = None, start: str | None = None, end: str | None = None) -> str:
        if not event_id or "/" in event_id:
            raise GraphToolError("Invalid Graph event ID")
        body = {key: value for key, value in {"subject": subject, "start": {"dateTime": start, "timeZone": "UTC"} if start else None, "end": {"dateTime": end, "timeZone": "UTC"} if end else None}.items() if value is not None}
        if not body:
            raise GraphToolError("At least one event field is required")
        return json.dumps({"event": self._request("PATCH", f"/me/events/{quote(event_id, safe='')}", scope=GRAPH_CALENDAR_WRITE, body=body)}, separators=(",", ":"))

    def calendar_cancel(self, *, event_id: str) -> str:
        self._request("DELETE", f"/me/events/{quote(event_id, safe='')}", scope=GRAPH_CALENDAR_WRITE)
        return json.dumps({"event_id": event_id, "cancelled": True}, separators=(",", ":"))

    def files_search(self, *, query: str, max_results: int = 10) -> str:
        payload = self._request("GET", "/me/drive/root/search(q='" + quote(query[:100]) + "')", scope=GRAPH_FILES_READ, params={"$top": max_results})
        return json.dumps({"items": payload.get("value", [])[:max_results]}, separators=(",", ":"))

    def files_read(self, *, file_id: str) -> str:
        return json.dumps({"file": self._request("GET", f"/me/drive/items/{quote(file_id, safe='')}", scope=GRAPH_FILES_READ)}, separators=(",", ":"))

    def files_update(self, *, file_id: str, name: str | None = None, description: str | None = None) -> str:
        body = {key: value for key, value in {"name": name, "description": description}.items() if value is not None}
        if not body:
            raise GraphToolError("At least one file field is required")
        return json.dumps({"file": self._request("PATCH", f"/me/drive/items/{quote(file_id, safe='')}", scope=GRAPH_FILES_WRITE, body=body)}, separators=(",", ":"))


def _tool_service(scope: str) -> GraphService:
    context = current_tool_context.get()
    if context is None:
        return GraphService(granted_scopes={scope})
    stored = get_default_microsoft_oauth_service().token_for_user(context.user_id)
    return GraphService(
        access_token=(stored or {}).get("access_token"),
        granted_scopes=context.granted_scopes,
    )


@tool
def graph_mail_search(query: str, max_results: int = 10) -> str:
    """Search Outlook mail."""
    return _tool_service(GRAPH_MAIL_READ).mail_search(query=query, max_results=max_results)
@tool
def graph_mail_read(message_id: str) -> str:
    """Read an Outlook message."""
    return _tool_service(GRAPH_MAIL_READ).mail_read(message_id=message_id)
@tool
def graph_mail_draft(to: str, subject: str, body: str) -> str:
    """Create an Outlook draft after confirmation."""
    return _tool_service(GRAPH_MAIL_WRITE).mail_draft(to=to, subject=subject, body=body)
@tool
def graph_mail_send(to: str, subject: str, body: str) -> str:
    """Send an Outlook message after confirmation."""
    return _tool_service(GRAPH_MAIL_SEND).mail_send(to=to, subject=subject, body=body)
@tool
def graph_calendar_list(start: str, end: str, max_results: int = 10) -> str:
    """List Outlook calendar events."""
    return _tool_service(GRAPH_CALENDAR_READ).calendar_list(start=start, end=end, max_results=max_results)
@tool
def graph_calendar_find_time(attendees: list[str], duration_minutes: int = 30) -> str:
    """Find Outlook meeting-time suggestions."""
    return _tool_service(GRAPH_CALENDAR_READ).calendar_find_time(attendees=attendees, duration_minutes=duration_minutes)
@tool
def graph_calendar_create(subject: str, start: str, end: str, attendees: list[str] | None = None) -> str:
    """Create an Outlook meeting after confirmation."""
    return _tool_service(GRAPH_CALENDAR_WRITE).calendar_create(subject=subject, start=start, end=end, attendees=attendees)
@tool
def graph_calendar_update(event_id: str, subject: str | None = None, start: str | None = None, end: str | None = None) -> str:
    """Update an Outlook meeting after confirmation."""
    return _tool_service(GRAPH_CALENDAR_WRITE).calendar_update(event_id=event_id, subject=subject, start=start, end=end)
@tool
def graph_calendar_cancel(event_id: str) -> str:
    """Cancel an Outlook meeting after confirmation."""
    return _tool_service(GRAPH_CALENDAR_WRITE).calendar_cancel(event_id=event_id)
@tool
def graph_files_search(query: str, max_results: int = 10) -> str:
    """Search OneDrive files."""
    return _tool_service(GRAPH_FILES_READ).files_search(query=query, max_results=max_results)
@tool
def graph_files_read(file_id: str) -> str:
    """Read OneDrive file metadata."""
    return _tool_service(GRAPH_FILES_READ).files_read(file_id=file_id)
@tool
def graph_files_update(file_id: str, name: str | None = None, description: str | None = None) -> str:
    """Update OneDrive metadata after confirmation."""
    return _tool_service(GRAPH_FILES_WRITE).files_update(file_id=file_id, name=name, description=description)
