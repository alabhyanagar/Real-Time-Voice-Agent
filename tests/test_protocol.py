import json
import sys
import unittest
sys.path.insert(0, ".")
from backend.protocol import HelloEvent, ReadyEvent, parse_event, serialize_event
from backend.protocol.messages import AudioFormat

class ProtocolTests(unittest.TestCase):
    def test_client_event_round_trip(self):
        parsed = parse_event(serialize_event(HelloEvent(session_id="s-1", turn_id="t-1", client_name="browser")))
        self.assertEqual(parsed.type, "hello")
        self.assertEqual(parsed.protocol_version, "1.0")

    def test_server_event_round_trip(self):
        event = ReadyEvent(session_id="s-1", turn_id="t-1", server_version="0.1.0", audio_format=AudioFormat())
        parsed = parse_event(json.loads(serialize_event(event)), direction="server")
        self.assertEqual(parsed.type, "ready")

    def test_unknown_type_and_version_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_event({"type": "unknown", "protocol_version": "1.0", "session_id": "s", "turn_id": "t"})
        with self.assertRaises(ValueError):
            parse_event({"type": "hello", "protocol_version": "2.0", "session_id": "s", "turn_id": "t"})

    def test_extra_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_event({"type": "hello", "protocol_version": "1.0", "session_id": "s", "turn_id": "t", "unexpected": True})

if __name__ == "__main__":
    unittest.main()
