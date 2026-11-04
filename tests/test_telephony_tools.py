import json

import httpx
import pytest

from backend.core import config
from backend.tools.telephony_tools import TelephonyToolError, TwilioService


def test_sms_and_call_drafts_validate_and_never_contact_provider(monkeypatch):
    monkeypatch.setattr(config.settings, "TWILIO_FROM_NUMBER", "+14155550100")
    service = TwilioService()
    sms = json.loads(service.sms_draft(to="+14155550123", body="Hello"))
    call = json.loads(service.call_draft(to="+14155550123", purpose="Appointment", script="Hi"))
    assert sms["requires_confirmation"] is True
    assert call["requires_confirmation"] is True
    with pytest.raises(TelephonyToolError, match="E.164"):
        service.sms_draft(to="4155550123", body="Hello")


def test_twilio_send_and_call_lifecycle_are_structured(monkeypatch):
    monkeypatch.setattr(config.settings, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(config.settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(config.settings, "TWILIO_FROM_NUMBER", "+14155550100")
    monkeypatch.setattr(config.settings, "TWILIO_VOICE_WEBHOOK_URL", "https://example.com/voice")
    monkeypatch.setattr(config.settings, "TWILIO_STATUS_CALLBACK_URL", "https://example.com/status")

    def handler(request):
        if request.url.path.endswith("Messages.json"):
            return httpx.Response(201, json={"sid": "SM123", "status": "queued"})
        if request.url.path.endswith("Recordings.json"):
            return httpx.Response(200, json={"recordings": []})
        if request.method == "GET":
            return httpx.Response(200, json={"sid": "CA123", "status": "in-progress", "duration": "4"})
        return httpx.Response(200, json={"sid": "CA123", "status": "completed"})

    service = TwilioService(httpx.Client(transport=httpx.MockTransport(handler)))
    assert json.loads(service.sms_send(to="+14155550123", body="Hello"))["message_sid"] == "SM123"
    assert json.loads(service.call_place(to="+14155550123"))["call_sid"] == "CA123"
    assert json.loads(service.call_status(call_sid="CA123"))["status"] == "in-progress"
    assert json.loads(service.call_hangup(call_sid="CA123"))["status"] == "completed"
    assert json.loads(service.call_transcript(call_sid="CA123"))["transcript_available"] is False
