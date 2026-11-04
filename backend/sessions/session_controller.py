"""Session owner for state, turns, generations, and active tasks."""
from uuid import uuid4
from .cancellation import GenerationController
from .session_state import ALLOWED_TRANSITIONS, SessionState

class SessionController:
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.state = SessionState.IDLE
        self.turn_id = str(uuid4())
        self.response_id: str | None = None
        self.generations = GenerationController()
        self.active_tasks: set[object] = set()

    @property
    def generation_id(self) -> str:
        return self.generations.generation_id

    def transition(self, state: SessionState | str) -> SessionState:
        target = SessionState(state)
        if target != self.state and target not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid session transition: {self.state} -> {target}")
        self.state = target
        return self.state

    def begin_turn(self) -> str:
        self.turn_id = str(uuid4())
        self.response_id = None
        return self.turn_id

    def interrupt(self) -> str:
        self.transition(SessionState.INTERRUPTING)
        return self.generations.next_generation()

    def close(self) -> None:
        self.generations.cancel_current()
        self.state = SessionState.CLOSED
