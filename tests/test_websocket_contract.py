import unittest
import asyncio
from types import SimpleNamespace

from backend.routers import websocket_router


class FakeOrchestrator:
    """Provider-free orchestrator used to test WebSocket transport only."""

    def __init__(self, websocket):
        self.websocket = websocket

    async def start(self):
        await self.websocket.send_json({"type": "state", "state": "LISTENING"})

    async def handle_audio_chunk(self, audio_chunk: bytes):
        self.received_audio = audio_chunk

    async def close(self):
        return None


class FakeWebSocket:
    def __init__(self):
        self.client = SimpleNamespace(host="baseline-test")
        self.headers = {}
        self.messages = [
            {"bytes": b"\x00\x00" * 4},
            {"text": '{"type":"ping","protocol_version":"1.0","session_id":"s-1","turn_id":"t-1"}'},
            {"type": "websocket.disconnect"},
        ]
        self.sent_json = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive(self):
        return self.messages.pop(0)

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def close(self, code=None):
        return None


class WebSocketContractTests(unittest.TestCase):
    def test_audio_endpoint_accepts_binary_audio_and_initializes_session(self):
        original_orchestrator = websocket_router.PipelineOrchestrator
        websocket_router.PipelineOrchestrator = FakeOrchestrator
        socket = FakeWebSocket()

        try:
            asyncio.run(websocket_router.audio_websocket_endpoint(socket))
        finally:
            websocket_router.PipelineOrchestrator = original_orchestrator

        self.assertTrue(socket.accepted)
        self.assertEqual(socket.sent_json[0]["type"], "ready")
        self.assertEqual(socket.sent_json[1], {"type": "state", "state": "LISTENING"})
        self.assertEqual(socket.sent_json[2]["type"], "pong")


if __name__ == "__main__":
    unittest.main()
