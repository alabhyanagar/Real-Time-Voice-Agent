"""Serialization and parsing helpers for protocol events."""
import json
from typing import Any
from pydantic import ValidationError
from .messages import ClientEvent, ServerEvent, _CLIENT, _SERVER
from .versioning import is_supported_version

_EVENT_TYPES = {event.model_fields["type"].default: event for event in (*_CLIENT, *_SERVER)}
_CLIENT_TYPES = {event.model_fields["type"].default for event in _CLIENT}

def parse_event(payload: str | bytes | dict[str, Any], *, direction: str = "client") -> ClientEvent | ServerEvent:
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("WebSocket event must be a JSON object")
    if not is_supported_version(payload.get("protocol_version", "")):
        raise ValueError(f"Unsupported protocol version: {payload.get('protocol_version')!r}")
    event_type = payload.get("type")
    event_cls = _EVENT_TYPES.get(event_type)
    if event_cls is None:
        raise ValueError(f"Unknown protocol event type: {event_type!r}")
    if direction == "client" and event_type not in _CLIENT_TYPES:
        raise ValueError(f"Event type {event_type!r} is not valid from a client")
    if direction == "server" and event_type in _CLIENT_TYPES:
        raise ValueError(f"Event type {event_type!r} is not valid from the server")
    try:
        return event_cls.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid {event_type!r} event: {exc}") from exc

def serialize_event(event: ClientEvent | ServerEvent) -> str:
    return event.model_dump_json(exclude_none=True)
