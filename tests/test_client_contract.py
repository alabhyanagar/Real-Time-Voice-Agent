import json
import unittest
from backend.protocol import parse_event, serialize_event
from backend.protocol.messages import (
    PROTOCOL_VERSION,
    AudioFormat,
    AudioFormatEvent,
    AudioFrameMetadata,
    AudioFlushEvent,
    CancelEvent,
    FlushEvent,
    HelloEvent,
    PingEvent,
    ReadyEvent,
    ResponseTextDeltaEvent,
    StateEvent,
    TelemetryEvent,
    ToolConfirmationEvent,
    ToolConfirmationResponseEvent,
    ToolStatusEvent,
    TranscriptEvent,
    UiCardEvent,
)

class ClientContractTests(unittest.TestCase):
    def setUp(self):
        self.session_id = "test-session-android-desktop"
        self.turn_id = "turn-001"
        self.generation_id = "gen-abc-123"

    def test_android_hello_payload_conforms_to_backend_schema(self):
        """Validates that payload sent by Android ClientHelloEvent parses into HelloEvent."""
        android_hello_payload = {
            "type": "hello",
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": 0,
            "timestamp_ms": 1700000000000,
            "client_name": "android",
            "client_version": "0.1.0",
            "resume_token": "reconnect_token_456",
            "generation_id": self.generation_id,
        }
        event = parse_event(android_hello_payload, direction="client")
        self.assertIsInstance(event, HelloEvent)
        self.assertEqual(event.client_name, "android")
        self.assertEqual(event.resume_token, "reconnect_token_456")

    def test_android_audio_format_conforms_to_backend_schema(self):
        """Validates that Android audio format negotiation is accepted."""
        android_format_payload = {
            "type": "audio_format",
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": 1,
            "timestamp_ms": 1700000000100,
            "format": {
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16000,
                "channels": 1,
                "sample_width_bytes": 2,
            },
            "generation_id": self.generation_id,
        }
        event = parse_event(android_format_payload, direction="client")
        self.assertIsInstance(event, AudioFormatEvent)
        self.assertEqual(event.format.sample_rate_hz, 16000)
        self.assertEqual(event.format.channels, 1)

    def test_audio_frame_metadata_conforms_to_backend_schema(self):
        """Validates audio frame metadata packet sent before binary PCM."""
        frame_payload = {
            "type": "audio_frame",
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": 2,
            "timestamp_ms": 1700000000200,
            "byte_length": 640,
            "frame_index": 0,
            "generation_id": self.generation_id,
        }
        event = parse_event(frame_payload, direction="client")
        self.assertIsInstance(event, AudioFrameMetadata)
        self.assertEqual(event.byte_length, 640)

    def test_tool_confirmation_response_contract(self):
        """Validates that tool confirmation accept/reject responses match backend schema."""
        for approved in (True, False):
            payload = {
                "type": "tool_confirmation_response",
                "protocol_version": PROTOCOL_VERSION,
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "sequence": 3,
                "timestamp_ms": 1700000000300,
                "confirmation_id": "conf_xyz_789",
                "approved": approved,
                "generation_id": self.generation_id,
            }
            event = parse_event(payload, direction="client")
            self.assertIsInstance(event, ToolConfirmationResponseEvent)
            self.assertEqual(event.confirmation_id, "conf_xyz_789")
            self.assertEqual(event.approved, approved)

    def test_barge_in_and_cancel_contract(self):
        """Validates cancel and flush events from native clients."""
        cancel_payload = {
            "type": "cancel",
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": 4,
            "timestamp_ms": 1700000000400,
            "reason": "user_cancel",
            "generation_id": self.generation_id,
        }
        event = parse_event(cancel_payload, direction="client")
        self.assertIsInstance(event, CancelEvent)

        flush_payload = {
            "type": "flush",
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": 5,
            "timestamp_ms": 1700000000500,
            "reason": "barge_in",
            "generation_id": self.generation_id,
        }
        flush_event = parse_event(flush_payload, direction="client")
        self.assertIsInstance(flush_event, FlushEvent)

    def test_server_events_serializable_for_clients(self):
        """Validates that all server events serialize into valid JSON conforming to client models."""
        server_events = [
            ReadyEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                server_version="0.1.0",
                audio_format=AudioFormat(),
                generation_id=self.generation_id,
            ),
            StateEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                state="speaking",
                generation_id=self.generation_id,
            ),
            TranscriptEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                text="Schedule meeting with Alice tomorrow at 10 AM",
                is_final=True,
                generation_id=self.generation_id,
            ),
            ResponseTextDeltaEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                text="I have prepared the calendar invitation.",
                is_final=False,
                generation_id=self.generation_id,
            ),
            AudioFlushEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                reason="barge_in",
                generation_id=self.generation_id,
            ),
            ToolStatusEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                tool_name="google_calendar_create_event",
                status="running",
                generation_id=self.generation_id,
            ),
            ToolConfirmationEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                tool_name="google_calendar_create_event",
                confirmation_id="conf-1234",
                prompt="Do you want to create 'Team Sync' on your Google Calendar?",
                generation_id=self.generation_id,
            ),
            UiCardEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                card_type="citations",
                payload={"citations": ["doc_1", "doc_2"]},
                generation_id=self.generation_id,
            ),
            TelemetryEvent(
                session_id=self.session_id,
                turn_id=self.turn_id,
                measurements={"ttft_ms": 320, "vad_latency_ms": 25},
                generation_id=self.generation_id,
            ),
        ]

        for se in server_events:
            raw = serialize_event(se)
            decoded = json.loads(raw)
            self.assertEqual(decoded["protocol_version"], PROTOCOL_VERSION)
            self.assertEqual(decoded["type"], se.type)
            self.assertEqual(decoded["session_id"], self.session_id)

if __name__ == "__main__":
    unittest.main()

