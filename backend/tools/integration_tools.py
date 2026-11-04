"""Bounded ESP32 and MERN application adapters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from backend.core.config import settings


ESP32_READ_SCOPE = "esp32.read"
ESP32_CONTROL_SCOPE = "esp32.control"
MERN_READ_SCOPE = "mern.read"
MERN_WRITE_SCOPE = "mern.write"


class IntegrationToolError(ValueError):
    """Raised when an IoT or application connector is unavailable."""


class IntegrationService:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def _request(self, base: str, token: str, method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
        if not base:
            raise IntegrationToolError("Connector endpoint is not configured")
        client = self.client or httpx.Client(timeout=settings.INTEGRATION_TIMEOUT_SECONDS)
        close = self.client is None
        try:
            response = client.request(method, f"{base.rstrip('/')}/{path.lstrip('/')}", headers={"Authorization": f"Bearer {token}"} if token else {}, json=body, params=params)
            response.raise_for_status()
            payload = response.json() if response.content else {}
            return payload if isinstance(payload, dict) else {"data": payload}
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationToolError("Connector request failed") from exc
        finally:
            if close:
                client.close()

    def sensor_read(self, sensor_id: str) -> str:
        payload = self._request(settings.ESP32_BASE_URL, settings.ESP32_API_KEY, "GET", f"sensors/{quote(sensor_id, safe='_-')}")
        return json.dumps({"sensor_id": sensor_id, "reading": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def sensor_history(self, sensor_id: str, limit: int = 20) -> str:
        if limit <= 0 or limit > 100:
            raise IntegrationToolError("limit must be between 1 and 100")
        payload = self._request(settings.ESP32_BASE_URL, settings.ESP32_API_KEY, "GET", f"sensors/{quote(sensor_id, safe='_-')}/history", params={"limit": limit})
        return json.dumps({"sensor_id": sensor_id, "history": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def device_status(self, device_id: str) -> str:
        payload = self._request(settings.ESP32_BASE_URL, settings.ESP32_API_KEY, "GET", f"devices/{quote(device_id, safe='_-')}/status")
        return json.dumps({"device_id": device_id, "status": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def command_preview(self, device_id: str, command: str, parameters: dict | None = None) -> str:
        if not device_id or not command or len(command) > 100:
            raise IntegrationToolError("Device and command are required")
        return json.dumps({"device_id": device_id, "command": command, "parameters": parameters or {}, "requires_confirmation": True}, separators=(",", ":"))

    def command_execute(self, device_id: str, command: str, parameters: dict | None = None) -> str:
        payload = self._request(settings.ESP32_BASE_URL, settings.ESP32_API_KEY, "POST", f"devices/{quote(device_id, safe='_-')}/commands", {"command": command, "parameters": parameters or {}})
        return json.dumps({"device_id": device_id, "result": payload, "executed_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def mern_search(self, collection: str, query: str, limit: int = 20) -> str:
        self._validate_collection(collection)
        payload = self._request(settings.MERN_API_BASE_URL, settings.MERN_API_KEY, "GET", f"{collection}", params={"q": query[:500], "limit": limit})
        return json.dumps({"collection": collection, "items": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":"))

    def mern_create(self, collection: str, record: dict) -> str:
        self._validate_collection(collection)
        payload = self._request(settings.MERN_API_BASE_URL, settings.MERN_API_KEY, "POST", collection, record)
        return json.dumps({"collection": collection, "record": payload}, separators=(",", ":"))

    def mern_update(self, collection: str, record_id: str, record: dict) -> str:
        self._validate_collection(collection)
        payload = self._request(settings.MERN_API_BASE_URL, settings.MERN_API_KEY, "PATCH", f"{collection}/{quote(record_id, safe='_-')}", record)
        return json.dumps({"collection": collection, "record": payload}, separators=(",", ":"))

    def mern_delete(self, collection: str, record_id: str) -> str:
        self._validate_collection(collection)
        self._request(settings.MERN_API_BASE_URL, settings.MERN_API_KEY, "DELETE", f"{collection}/{quote(record_id, safe='_-')}")
        return json.dumps({"collection": collection, "record_id": record_id, "deleted": True}, separators=(",", ":"))

    @staticmethod
    def _validate_collection(collection: str) -> None:
        if not collection or len(collection) > 80 or not collection.replace("_", "").replace("-", "").isalnum():
            raise IntegrationToolError("Collection must be an alphanumeric identifier")


@tool
def sensor_read(sensor_id: str) -> str:
    """Read an ESP32 sensor."""
    return IntegrationService().sensor_read(sensor_id)
@tool
def sensor_history(sensor_id: str, limit: int = 20) -> str:
    """Read bounded ESP32 sensor history."""
    return IntegrationService().sensor_history(sensor_id, limit)
@tool
def device_status(device_id: str) -> str:
    """Read ESP32 device status."""
    return IntegrationService().device_status(device_id)
@tool
def device_command_preview(device_id: str, command: str, parameters: dict | None = None) -> str:
    """Preview an ESP32 command."""
    return IntegrationService().command_preview(device_id, command, parameters)
@tool
def device_command_execute(device_id: str, command: str, parameters: dict | None = None) -> str:
    """Execute an ESP32 command after confirmation."""
    return IntegrationService().command_execute(device_id, command, parameters)
@tool
def mern_search(collection: str, query: str, limit: int = 20) -> str:
    """Search an approved MERN collection."""
    return IntegrationService().mern_search(collection, query, limit)
@tool
def mern_create(collection: str, record: dict) -> str:
    """Create a MERN record after confirmation."""
    return IntegrationService().mern_create(collection, record)
@tool
def mern_update(collection: str, record_id: str, record: dict) -> str:
    """Update a MERN record after confirmation."""
    return IntegrationService().mern_update(collection, record_id, record)
@tool
def mern_delete(collection: str, record_id: str) -> str:
    """Delete a MERN record after confirmation."""
    return IntegrationService().mern_delete(collection, record_id)
