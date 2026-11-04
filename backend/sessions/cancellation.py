"""Generation-based cancellation and stale-event protection."""
from uuid import uuid4

class GenerationController:
    def __init__(self):
        self.generation_id = str(uuid4())
        self.cancelled: set[str] = set()

    def is_current(self, generation_id: str | None) -> bool:
        return bool(generation_id) and generation_id == self.generation_id and generation_id not in self.cancelled

    def next_generation(self) -> str:
        self.cancelled.add(self.generation_id)
        self.generation_id = str(uuid4())
        return self.generation_id

    def cancel_current(self) -> None:
        self.cancelled.add(self.generation_id)
