"""Read-only Google Workspace REST tools with explicit OAuth scope checks."""

from __future__ import annotations

import json
import base64
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from backend.core.config import settings
from backend.tools.context import current_tool_context
from backend.integrations.google_oauth import get_default_google_oauth_service


class GoogleToolError(ValueError):
    """Raised when a Google Workspace request is unavailable or invalid."""


GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_READ_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
DRIVE_METADATA_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"
DRIVE_READ_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"


class GoogleWorkspaceService:
    def __init__(self, client: httpx.Client | None = None, *, access_token: str | None = None, granted_scopes: set[str] | frozenset[str] = frozenset()):
        self.client = client
        execution_context = current_tool_context.get()
        stored = None
        if access_token is None and execution_context is not None:
            stored = get_default_google_oauth_service().tokens.get(execution_context.user_id)
        self.access_token = access_token if access_token is not None else (stored or {}).get("access_token") or settings.GOOGLE_ACCESS_TOKEN
        self.granted_scopes = frozenset(granted_scopes or (stored or {}).get("scopes", []))

    def _require(self, scope: str) -> None:
        if not self.access_token:
            raise GoogleToolError("Google OAuth access token is not configured")
        if scope not in self.granted_scopes:
            raise GoogleToolError(f"OAuth scope is not granted: {scope}")

    def _request(self, method: str, path: str, *, scope: str, params: dict | None = None, json_body: dict | None = None) -> dict:
        self._require(scope)
        client = self.client or httpx.Client(timeout=settings.GOOGLE_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.request(method, f"{settings.GOOGLE_API_BASE_URL.rstrip('/')}{path}", headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}, params=params, json=json_body)
            if response.status_code in {401, 403}:
                raise GoogleToolError("Google OAuth authorization was rejected")
            response.raise_for_status()
            payload = response.json() if response.content else {}
            if not isinstance(payload, dict):
                raise GoogleToolError("Google returned an invalid response")
            return payload
        except GoogleToolError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise GoogleToolError("Google Workspace request failed") from exc
        finally:
            if close:
                client.close()

    def gmail_search(self, *, query: str, max_results: int = 10, page_token: str | None = None) -> str:
        query = query.strip()
        if not query or len(query) > 500:
            raise GoogleToolError("Gmail query must contain 1-500 characters")
        if max_results <= 0 or max_results > settings.GOOGLE_MAX_RESULTS:
            raise GoogleToolError(f"max_results must be between 1 and {settings.GOOGLE_MAX_RESULTS}")
        payload = self._request("GET", "/gmail/v1/users/me/messages", scope=GMAIL_READ_SCOPE, params={"q": query, "maxResults": max_results, **({"pageToken": page_token} if page_token else {})})
        items = [{"id": str(item.get("id")), "thread_id": str(item.get("threadId"))} for item in payload.get("messages", [])[:max_results] if item.get("id")]
        return json.dumps({"query": query, "items": items, "next_page_token": payload.get("nextPageToken"), "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def gmail_read(self, *, message_id: str, include_body: bool = False) -> str:
        if not message_id or len(message_id) > 200 or "/" in message_id:
            raise GoogleToolError("Invalid Gmail message ID")
        params = {"format": "full" if include_body else "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]}
        payload = self._request("GET", f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}", scope=GMAIL_READ_SCOPE, params=params)
        if not include_body:
            payload.pop("payload", None)
        return json.dumps({"message": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def gmail_summarize(self, *, message_id: str) -> str:
        result = json.loads(self.gmail_read(message_id=message_id, include_body=True))
        payload = result.get("message", {}).get("payload", {})
        headers = {item.get("name", "").lower(): item.get("value", "") for item in payload.get("headers", [])}
        return json.dumps({"message_id": message_id, "subject": headers.get("subject"), "from": headers.get("from"), "summary": "Thread summary requires a configured summarization model; metadata and body were retrieved.", "retrieved_at": result.get("retrieved_at")}, separators=(",", ":"))

    def calendar_list(self, *, time_min: str, time_max: str | None = None, calendar_id: str = "primary", max_results: int = 10, page_token: str | None = None) -> str:
        self._validate_time(time_min)
        if time_max:
            self._validate_time(time_max)
        if max_results <= 0 or max_results > settings.GOOGLE_MAX_RESULTS:
            raise GoogleToolError(f"max_results must be between 1 and {settings.GOOGLE_MAX_RESULTS}")
        calendar_id = quote(calendar_id, safe="@._-")
        params = {"timeMin": time_min, "singleEvents": "true", "orderBy": "startTime", "maxResults": max_results}
        if time_max:
            params["timeMax"] = time_max
        if page_token:
            params["pageToken"] = page_token
        payload = self._request("GET", f"/calendar/v3/calendars/{calendar_id}/events", scope=CALENDAR_READ_SCOPE, params=params)
        return json.dumps({"calendar_id": calendar_id, "items": payload.get("items", [])[:max_results], "next_page_token": payload.get("nextPageToken"), "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_freebusy(self, *, time_min: str, time_max: str, calendar_ids: list[str]) -> str:
        self._validate_time(time_min)
        self._validate_time(time_max)
        if not calendar_ids or len(calendar_ids) > 20 or any(not item or len(item) > 200 for item in calendar_ids):
            raise GoogleToolError("calendar_ids must contain 1-20 valid IDs")
        payload = self._request("POST", "/calendar/v3/freeBusy", scope=CALENDAR_FREEBUSY_SCOPE, json_body={"timeMin": time_min, "timeMax": time_max, "items": [{"id": item} for item in calendar_ids]})
        return json.dumps({"time_min": time_min, "time_max": time_max, "calendars": payload.get("calendars", {}), "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def gmail_draft(self, *, to: str, subject: str, body: str, cc: str | None = None, bcc: str | None = None) -> str:
        raw = self._mime_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
        payload = self._request("POST", "/gmail/v1/users/me/drafts", scope=GMAIL_COMPOSE_SCOPE, json_body={"message": {"raw": raw}})
        return json.dumps({"draft": payload, "created_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def gmail_send(self, *, to: str, subject: str, body: str, cc: str | None = None, bcc: str | None = None) -> str:
        raw = self._mime_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
        payload = self._request("POST", "/gmail/v1/users/me/messages/send", scope=GMAIL_SEND_SCOPE, json_body={"raw": raw})
        return json.dumps({"message": payload, "sent_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_create(self, *, summary: str, start: str, end: str, calendar_id: str = "primary", description: str | None = None, attendees: list[str] | None = None) -> str:
        self._validate_time(start)
        self._validate_time(end)
        body = {"summary": self._bounded(summary, 300), "start": {"dateTime": start}, "end": {"dateTime": end}}
        if description:
            body["description"] = self._bounded(description, 4000)
        body["attendees"] = [{"email": email} for email in self._emails(attendees or [])]
        payload = self._request("POST", f"/calendar/v3/calendars/{quote(calendar_id, safe='@._-')}/events", scope=CALENDAR_EVENTS_SCOPE, json_body=body)
        return json.dumps({"event": payload, "created_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_update(self, *, event_id: str, summary: str | None = None, start: str | None = None, end: str | None = None, calendar_id: str = "primary") -> str:
        if not event_id or "/" in event_id:
            raise GoogleToolError("Invalid Calendar event ID")
        body = {}
        if summary is not None:
            body["summary"] = self._bounded(summary, 300)
        if start:
            self._validate_time(start)
            body["start"] = {"dateTime": start}
        if end:
            self._validate_time(end)
            body["end"] = {"dateTime": end}
        if not body:
            raise GoogleToolError("At least one event field must be updated")
        payload = self._request("PATCH", f"/calendar/v3/calendars/{quote(calendar_id, safe='@._-')}/events/{quote(event_id, safe='')}", scope=CALENDAR_EVENTS_SCOPE, json_body=body)
        return json.dumps({"event": payload, "updated_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_cancel(self, *, event_id: str, calendar_id: str = "primary") -> str:
        if not event_id or "/" in event_id:
            raise GoogleToolError("Invalid Calendar event ID")
        self._request("DELETE", f"/calendar/v3/calendars/{quote(calendar_id, safe='@._-')}/events/{quote(event_id, safe='')}", scope=CALENDAR_EVENTS_SCOPE)
        return json.dumps({"event_id": event_id, "cancelled": True, "cancelled_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def calendar_draft(self, *, summary: str, start: str, end: str, calendar_id: str = "primary", description: str | None = None, attendees: list[str] | None = None) -> str:
        self._validate_time(start)
        self._validate_time(end)
        self._bounded(summary, 300)
        clean_attendees = self._emails(attendees or [])
        return json.dumps({"draft": {"calendar_id": calendar_id, "summary": summary, "start": start, "end": end, "description": description, "attendees": clean_attendees}, "requires_confirmation": True}, separators=(",", ":"))

    def drive_search(self, *, query: str, max_results: int = 10) -> str:
        if not query.strip() or len(query) > 500:
            raise GoogleToolError("Drive query must contain 1-500 characters")
        payload = self._request("GET", "/drive/v3/files", scope=DRIVE_METADATA_SCOPE, params={"q": query, "pageSize": max_results, "fields": "files(id,name,mimeType,modifiedTime,size),nextPageToken"})
        return json.dumps({"query": query, "items": payload.get("files", [])[:max_results], "next_page_token": payload.get("nextPageToken"), "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def drive_read(self, *, file_id: str) -> str:
        if not file_id or "/" in file_id:
            raise GoogleToolError("Invalid Drive file ID")
        payload = self._request("GET", f"/drive/v3/files/{quote(file_id, safe='')}", scope=DRIVE_READ_SCOPE, params={"alt": "media"})
        return json.dumps({"file_id": file_id, "file": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def drive_create(self, *, name: str, mime_type: str = "text/plain") -> str:
        self._bounded(name, 300)
        payload = self._request("POST", "/drive/v3/files", scope=DRIVE_FILE_SCOPE, json_body={"name": name, "mimeType": mime_type})
        return json.dumps({"file": payload, "created_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def drive_update(self, *, file_id: str, name: str | None = None, description: str | None = None) -> str:
        if not file_id or "/" in file_id or (name is None and description is None):
            raise GoogleToolError("Drive update requires a valid ID and field")
        body = {}
        if name is not None:
            body["name"] = self._bounded(name, 300)
        if description is not None:
            body["description"] = self._bounded(description, 1000)
        payload = self._request("PATCH", f"/drive/v3/files/{quote(file_id, safe='')}", scope=DRIVE_FILE_SCOPE, json_body=body)
        return json.dumps({"file": payload, "updated_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def drive_delete(self, *, file_id: str) -> str:
        if not file_id or "/" in file_id:
            raise GoogleToolError("Invalid Drive file ID")
        self._request("DELETE", f"/drive/v3/files/{quote(file_id, safe='')}", scope=DRIVE_FILE_SCOPE)
        return json.dumps({"file_id": file_id, "trashed": True, "deleted_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    @staticmethod
    def _bounded(value: str, limit: int) -> str:
        if not value or len(value) > limit:
            raise GoogleToolError(f"Text must contain 1-{limit} characters")
        return value

    @staticmethod
    def _emails(values: list[str]) -> list[str]:
        if len(values) > 50 or any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) for value in values):
            raise GoogleToolError("Attendees must contain valid email addresses")
        return values

    @classmethod
    def _mime_message(cls, *, to: str, subject: str, body: str, cc: str | None, bcc: str | None) -> str:
        cls._emails([to] + ([cc] if cc else []) + ([bcc] if bcc else []))
        cls._bounded(subject, 300)
        cls._bounded(body, 100_000)
        lines = [f"To: {to}", f"Subject: {subject}", "Content-Type: text/plain; charset=utf-8"]
        if cc:
            lines.insert(1, f"Cc: {cc}")
        if bcc:
            lines.insert(1, f"Bcc: {bcc}")
        return base64.urlsafe_b64encode(("\\r\\n".join(lines) + "\\r\\n\\r\\n" + body).encode()).decode().rstrip("=")

    @staticmethod
    def _validate_time(value: str) -> None:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GoogleToolError("Time values must be ISO-8601 timestamps") from exc


@tool
def google_gmail_search(query: str, max_results: int = 10, page_token: str | None = None) -> str:
    """Search Gmail messages with the user's read-only OAuth grant."""
    return GoogleWorkspaceService(granted_scopes={GMAIL_READ_SCOPE}).gmail_search(query=query, max_results=max_results, page_token=page_token)


@tool
def google_gmail_read(message_id: str, include_body: bool = False) -> str:
    """Read one Gmail message's metadata, optionally including its body."""
    return GoogleWorkspaceService(granted_scopes={GMAIL_READ_SCOPE}).gmail_read(message_id=message_id, include_body=include_body)


@tool
def google_gmail_summarize(message_id: str) -> str:
    """Retrieve a Gmail message and return source-linked summary metadata."""
    return GoogleWorkspaceService(granted_scopes={GMAIL_READ_SCOPE}).gmail_summarize(message_id=message_id)


@tool
def google_calendar_list(time_min: str, time_max: str | None = None, calendar_id: str = "primary", max_results: int = 10, page_token: str | None = None) -> str:
    """List Calendar events in a bounded time range."""
    return GoogleWorkspaceService(granted_scopes={CALENDAR_READ_SCOPE}).calendar_list(time_min=time_min, time_max=time_max, calendar_id=calendar_id, max_results=max_results, page_token=page_token)


@tool
def google_calendar_freebusy(time_min: str, time_max: str, calendar_ids: list[str]) -> str:
    """Read free/busy intervals for selected calendars."""
    return GoogleWorkspaceService(granted_scopes={CALENDAR_FREEBUSY_SCOPE}).calendar_freebusy(time_min=time_min, time_max=time_max, calendar_ids=calendar_ids)


@tool
def google_calendar_draft(summary: str, start: str, end: str, calendar_id: str = "primary", description: str | None = None, attendees: list[str] | None = None) -> str:
    """Prepare a Calendar event preview without contacting Google."""
    return GoogleWorkspaceService(granted_scopes={CALENDAR_EVENTS_SCOPE}).calendar_draft(summary=summary, start=start, end=end, calendar_id=calendar_id, description=description, attendees=attendees)


@tool
def google_gmail_draft(to: str, subject: str, body: str, cc: str | None = None, bcc: str | None = None) -> str:
    """Create a Gmail draft; the executor requires confirmation before execution."""
    return GoogleWorkspaceService(granted_scopes={GMAIL_COMPOSE_SCOPE}).gmail_draft(to=to, subject=subject, body=body, cc=cc, bcc=bcc)


@tool
def google_gmail_send(to: str, subject: str, body: str, cc: str | None = None, bcc: str | None = None) -> str:
    """Send a Gmail message; always confirmation-gated by the executor."""
    return GoogleWorkspaceService(granted_scopes={GMAIL_SEND_SCOPE}).gmail_send(to=to, subject=subject, body=body, cc=cc, bcc=bcc)


@tool
def google_calendar_create(summary: str, start: str, end: str, calendar_id: str = "primary", description: str | None = None, attendees: list[str] | None = None) -> str:
    """Create a Calendar event; always confirmation-gated by the executor."""
    return GoogleWorkspaceService(granted_scopes={CALENDAR_EVENTS_SCOPE}).calendar_create(summary=summary, start=start, end=end, calendar_id=calendar_id, description=description, attendees=attendees)


@tool
def google_calendar_update(event_id: str, summary: str | None = None, start: str | None = None, end: str | None = None, calendar_id: str = "primary") -> str:
    """Update a Calendar event; always confirmation-gated by the executor."""
    return GoogleWorkspaceService(granted_scopes={CALENDAR_EVENTS_SCOPE}).calendar_update(event_id=event_id, summary=summary, start=start, end=end, calendar_id=calendar_id)


@tool
def google_calendar_cancel(event_id: str, calendar_id: str = "primary") -> str:
    """Cancel a Calendar event; always confirmation-gated by the executor."""
    return GoogleWorkspaceService(granted_scopes={CALENDAR_EVENTS_SCOPE}).calendar_cancel(event_id=event_id, calendar_id=calendar_id)


@tool
def google_drive_search(query: str, max_results: int = 10) -> str:
    """Search Drive metadata with read-only OAuth."""
    return GoogleWorkspaceService(granted_scopes={DRIVE_METADATA_SCOPE}).drive_search(query=query, max_results=max_results)


@tool
def google_drive_read(file_id: str) -> str:
    """Read a selected Drive file through the read-only API."""
    return GoogleWorkspaceService(granted_scopes={DRIVE_READ_SCOPE}).drive_read(file_id=file_id)


@tool
def google_drive_create(name: str, mime_type: str = "text/plain") -> str:
    """Create Drive metadata after executor confirmation."""
    return GoogleWorkspaceService(granted_scopes={DRIVE_FILE_SCOPE}).drive_create(name=name, mime_type=mime_type)


@tool
def google_drive_update(file_id: str, name: str | None = None, description: str | None = None) -> str:
    """Update Drive metadata after executor confirmation."""
    return GoogleWorkspaceService(granted_scopes={DRIVE_FILE_SCOPE}).drive_update(file_id=file_id, name=name, description=description)


@tool
def google_drive_delete(file_id: str) -> str:
    """Move a Drive file to trash after executor confirmation."""
    return GoogleWorkspaceService(granted_scopes={DRIVE_FILE_SCOPE}).drive_delete(file_id=file_id)
