"""In-process session registry used by the WebSocket gateway."""
from .session_controller import SessionController


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, SessionController] = {}

    def create(self, session_id: str, user_id: str, granted_scopes: frozenset[str] = frozenset(), tenant_id: str | None = None) -> SessionController:
        session = SessionController(session_id, user_id, granted_scopes, tenant_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> SessionController | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()


session_manager = SessionManager()
