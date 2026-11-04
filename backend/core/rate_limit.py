"""Small in-process connection and message limiter for the gateway."""

import time
from collections import defaultdict, deque


class ConnectionRateLimiter:
    def __init__(self, messages_per_minute: int, max_connections: int):
        self.messages_per_minute = messages_per_minute
        self.max_connections = max_connections
        self._messages: dict[str, deque[float]] = defaultdict(deque)
        self._connections: dict[str, int] = defaultdict(int)

    def acquire(self, identity: str) -> bool:
        if self._connections[identity] >= self.max_connections:
            return False
        self._connections[identity] += 1
        return True

    def release(self, identity: str) -> None:
        self._connections[identity] = max(0, self._connections[identity] - 1)

    def allow_message(self, identity: str) -> bool:
        now = time.monotonic()
        window = self._messages[identity]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self.messages_per_minute:
            return False
        window.append(now)
        return True
