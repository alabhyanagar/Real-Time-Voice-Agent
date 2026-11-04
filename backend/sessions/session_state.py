"""Deterministic session state model."""
from enum import StrEnum

class SessionState(StrEnum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    LISTENING = "LISTENING"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING = "PROCESSING"
    TOOL_PENDING = "TOOL_PENDING"
    TOOL_RUNNING = "TOOL_RUNNING"
    SPEAKING = "SPEAKING"
    INTERRUPTING = "INTERRUPTING"
    ERROR = "ERROR"
    CLOSED = "CLOSED"

ALLOWED_TRANSITIONS = {
    SessionState.IDLE: {SessionState.CONNECTING, SessionState.CLOSED},
    SessionState.CONNECTING: {SessionState.LISTENING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.LISTENING: {SessionState.USER_SPEAKING, SessionState.PROCESSING, SessionState.INTERRUPTING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.USER_SPEAKING: {SessionState.LISTENING, SessionState.PROCESSING, SessionState.INTERRUPTING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.PROCESSING: {SessionState.TOOL_PENDING, SessionState.SPEAKING, SessionState.INTERRUPTING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.TOOL_PENDING: {SessionState.TOOL_RUNNING, SessionState.INTERRUPTING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.TOOL_RUNNING: {SessionState.PROCESSING, SessionState.SPEAKING, SessionState.INTERRUPTING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.SPEAKING: {SessionState.LISTENING, SessionState.INTERRUPTING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.INTERRUPTING: {SessionState.LISTENING, SessionState.ERROR, SessionState.CLOSED},
    SessionState.ERROR: {SessionState.LISTENING, SessionState.CLOSED},
    SessionState.CLOSED: set(),
}
