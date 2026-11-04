"""Single-writer outbound queue to prevent interleaved WebSocket sends."""
import asyncio
from dataclasses import dataclass

@dataclass
class OutboundMessage:
    kind: str
    value: dict | bytes

class OutboundQueue:
    def __init__(self, websocket, maxsize: int = 128):
        self.websocket = websocket
        self.queue: asyncio.Queue[OutboundMessage | None] = asyncio.Queue(maxsize=maxsize)
        self.worker: asyncio.Task | None = None

    async def start(self):
        if self.worker is None:
            self.worker = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            message = await self.queue.get()
            if message is None:
                self.queue.task_done()
                return
            try:
                if message.kind == "json":
                    await self.websocket.send_json(message.value)
                else:
                    await self.websocket.send_bytes(message.value)
            except Exception:
                # The gateway owns connection teardown; a failed send must not
                # leave the worker task unobservably dead while producers block.
                pass
            finally:
                self.queue.task_done()

    async def put_json(self, value: dict):
        await self.queue.put(OutboundMessage("json", value))

    async def put_bytes(self, value: bytes):
        await self.queue.put(OutboundMessage("bytes", value))

    async def close(self):
        if self.worker and not self.worker.done():
            await self.queue.put(None)
            await self.worker
        self.worker = None
