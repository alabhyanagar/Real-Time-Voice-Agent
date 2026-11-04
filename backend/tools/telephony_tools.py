"""Confirmation-aware Twilio SMS and outbound call tools."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx
from langchain_core.tools import tool

from backend.core.config import settings


class TelephonyToolError(ValueError):
    """Raised for invalid recipients or unavailable telephony operations."""


E164 = re.compile(r"^\+[1-9]\d{7,14}$")


class TwilioService:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    @staticmethod
    def _phone(value: str) -> str:
        if not E164.fullmatch(value.strip()):
            raise TelephonyToolError("Phone number must use E.164 format, for example +14155550123")
        allowed = settings.TWILIO_ALLOWED_DESTINATIONS
        if allowed and value not in allowed:
            raise TelephonyToolError("Destination is not in the configured allow-list")
        return value

    @staticmethod
    def _sid(value: str, prefix: str = "CA") -> str:
        if not value or len(value) > 64 or not value.startswith(prefix):
            raise TelephonyToolError(f"Invalid Twilio {prefix} identifier")
        return value

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            raise TelephonyToolError("Twilio credentials are not configured")
        client = self.client or httpx.Client(timeout=settings.TELEPHONY_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.request(method, f"{settings.TWILIO_API_BASE_URL.rstrip('/')}/Accounts/{settings.TWILIO_ACCOUNT_SID}{path}", auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), data=data or {})
            if response.status_code in {401, 403}:
                raise TelephonyToolError("Twilio authorization was rejected")
            response.raise_for_status()
            return response.json() if response.content else {}
        except TelephonyToolError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise TelephonyToolError("Twilio request failed") from exc
        finally:
            if close:
                client.close()

    def sms_draft(self, *, to: str, body: str) -> str:
        to = self._phone(to)
        if not body.strip() or len(body) > 1600:
            raise TelephonyToolError("SMS body must contain 1-1600 characters")
        return json.dumps({"draft": {"to": to, "from": settings.TWILIO_FROM_NUMBER, "body": body}, "requires_confirmation": True}, separators=(",", ":"))

    def sms_send(self, *, to: str, body: str) -> str:
        to = self._phone(to)
        if not settings.TWILIO_FROM_NUMBER:
            raise TelephonyToolError("TWILIO_FROM_NUMBER is not configured")
        if not body.strip() or len(body) > 1600:
            raise TelephonyToolError("SMS body must contain 1-1600 characters")
        payload = self._request("POST", "/Messages.json", {"To": to, "From": settings.TWILIO_FROM_NUMBER, "Body": body})
        return json.dumps({"message_sid": payload.get("sid"), "status": payload.get("status"), "to": to, "sent_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def call_draft(self, *, to: str, purpose: str, script: str = "") -> str:
        to = self._phone(to)
        if not purpose.strip() or len(purpose) > 500 or len(script) > 5000:
            raise TelephonyToolError("Call purpose/script exceeds configured limits")
        return json.dumps({"draft": {"to": to, "from": settings.TWILIO_FROM_NUMBER, "purpose": purpose, "script": script}, "requires_confirmation": True}, separators=(",", ":"))

    def call_place(self, *, to: str, purpose: str = "") -> str:
        to = self._phone(to)
        if not settings.TWILIO_FROM_NUMBER or not settings.TWILIO_VOICE_WEBHOOK_URL:
            raise TelephonyToolError("Twilio voice sender or webhook URL is not configured")
        payload = self._request("POST", "/Calls.json", {"To": to, "From": settings.TWILIO_FROM_NUMBER, "Url": settings.TWILIO_VOICE_WEBHOOK_URL, "StatusCallback": settings.TWILIO_STATUS_CALLBACK_URL})
        return json.dumps({"call_sid": payload.get("sid"), "status": payload.get("status"), "to": to, "purpose": purpose[:500], "placed_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def call_status(self, *, call_sid: str) -> str:
        call_sid = self._sid(call_sid)
        payload = self._request("GET", f"/Calls/{call_sid}.json")
        return json.dumps({"call_sid": call_sid, "status": payload.get("status"), "duration": payload.get("duration"), "to": payload.get("to"), "from": payload.get("from")}, separators=(",", ":"))

    def call_hangup(self, *, call_sid: str) -> str:
        call_sid = self._sid(call_sid)
        payload = self._request("POST", f"/Calls/{call_sid}.json", {"Status": "completed"})
        return json.dumps({"call_sid": call_sid, "status": payload.get("status", "completed"), "ended_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def call_transcript(self, *, call_sid: str) -> str:
        call_sid = self._sid(call_sid)
        payload = self._request("GET", f"/Calls/{call_sid}/Recordings.json")
        return json.dumps({"call_sid": call_sid, "recordings": payload.get("recordings", []), "transcript_available": False, "notice": "Transcript retrieval requires a configured recording/transcription pipeline."}, separators=(",", ":"))


@tool
def sms_draft(to: str, body: str) -> str:
    """Prepare an SMS draft without sending it."""
    return TwilioService().sms_draft(to=to, body=body)


@tool
def sms_send(to: str, body: str) -> str:
    """Send an SMS after executor confirmation."""
    return TwilioService().sms_send(to=to, body=body)


@tool
def call_draft(to: str, purpose: str, script: str = "") -> str:
    """Prepare an outbound call plan without placing a call."""
    return TwilioService().call_draft(to=to, purpose=purpose, script=script)


@tool
def call_place(to: str, purpose: str = "") -> str:
    """Place an outbound call after executor confirmation."""
    return TwilioService().call_place(to=to, purpose=purpose)


@tool
def call_status(call_sid: str) -> str:
    """Read the current status of an assistant-controlled call."""
    return TwilioService().call_status(call_sid=call_sid)


@tool
def call_hangup(call_sid: str) -> str:
    """End an assistant-controlled call after explicit confirmation."""
    return TwilioService().call_hangup(call_sid=call_sid)


@tool
def call_transcript(call_sid: str) -> str:
    """Retrieve permitted call recordings and transcript availability."""
    return TwilioService().call_transcript(call_sid=call_sid)
