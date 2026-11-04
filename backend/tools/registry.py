"""Tool registration and policy metadata."""

from dataclasses import dataclass
from typing import Sequence

from langchain_core.tools import BaseTool

from .safe_tools import calculate, get_current_time
from .schemas import ToolRisk
from .web_tools import web_extract_facts, web_fetch, web_search, web_summarize
from .google_tools import (
    CALENDAR_FREEBUSY_SCOPE,
    CALENDAR_EVENTS_SCOPE,
    CALENDAR_READ_SCOPE,
    DRIVE_FILE_SCOPE,
    DRIVE_METADATA_SCOPE,
    DRIVE_READ_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    GMAIL_READ_SCOPE,
    GMAIL_SEND_SCOPE,
    google_calendar_cancel,
    google_calendar_create,
    google_calendar_draft,
    google_calendar_freebusy,
    google_calendar_list,
    google_calendar_update,
    google_drive_create,
    google_drive_delete,
    google_drive_read,
    google_drive_search,
    google_drive_update,
    google_gmail_draft,
    google_gmail_read,
    google_gmail_summarize,
    google_gmail_send,
    google_gmail_search,
)
from .graph_tools import (
    GRAPH_CALENDAR_READ, GRAPH_CALENDAR_WRITE, GRAPH_FILES_READ, GRAPH_FILES_WRITE,
    GRAPH_MAIL_READ, GRAPH_MAIL_SEND, GRAPH_MAIL_WRITE,
    graph_calendar_cancel, graph_calendar_create, graph_calendar_find_time,
    graph_calendar_list, graph_calendar_update, graph_files_read, graph_files_search,
    graph_files_update, graph_mail_draft, graph_mail_read, graph_mail_search,
    graph_mail_send,
)
from .workspace_tools import (
    workspace_apply_patch,
    workspace_create_file,
    workspace_delete_file,
    workspace_git_commit,
    workspace_git_diff,
    workspace_git_revert_commit,
    workspace_git_status,
    workspace_list_files,
    workspace_preview_patch,
    workspace_read_file,
    workspace_rename_file,
    workspace_search,
)
from .integration_tools import (
    ESP32_CONTROL_SCOPE, ESP32_READ_SCOPE, MERN_READ_SCOPE, MERN_WRITE_SCOPE,
    device_command_execute, device_command_preview, device_status, mern_create,
    mern_delete, mern_search, mern_update, sensor_history, sensor_read,
)
from .telephony_tools import call_draft, call_hangup, call_place, call_status, call_transcript, sms_draft, sms_send


@dataclass(frozen=True)
class ToolDefinition:
    """A LangChain tool plus execution policy used by the agent graph."""

    tool: BaseTool
    risk_level: ToolRisk = "low"
    requires_confirmation: bool = False
    timeout_seconds: float = 15.0
    required_scopes: tuple[str, ...] = ()
    allowed_clients: tuple[str, ...] = ()
    rate_limit: int | None = None
    audit_required: bool = True
    idempotent: bool = False

    def __post_init__(self):
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        if self.rate_limit is not None and self.rate_limit <= 0:
            raise ValueError("Tool rate limit must be positive")


class ToolRegistry:
    """Explicit allow-list of tools exposed to the model."""

    def __init__(self, definitions: Sequence[ToolDefinition] | None = None):
        self.definitions = tuple(definitions or (
            ToolDefinition(calculate),
            ToolDefinition(get_current_time),
            ToolDefinition(workspace_list_files, timeout_seconds=10.0),
            ToolDefinition(workspace_search, timeout_seconds=15.0),
            ToolDefinition(workspace_read_file, timeout_seconds=10.0),
            ToolDefinition(workspace_preview_patch, timeout_seconds=10.0),
            ToolDefinition(workspace_create_file, risk_level="medium", requires_confirmation=True, timeout_seconds=10.0),
            ToolDefinition(workspace_apply_patch, risk_level="medium", requires_confirmation=True, timeout_seconds=10.0),
            ToolDefinition(workspace_rename_file, risk_level="medium", requires_confirmation=True, timeout_seconds=10.0),
            ToolDefinition(workspace_delete_file, risk_level="high", requires_confirmation=True, timeout_seconds=10.0),
            ToolDefinition(workspace_git_status, timeout_seconds=10.0, rate_limit=30),
            ToolDefinition(workspace_git_diff, timeout_seconds=10.0, rate_limit=30),
            ToolDefinition(workspace_git_commit, risk_level="medium", requires_confirmation=True, timeout_seconds=20.0, rate_limit=5),
            ToolDefinition(workspace_git_revert_commit, risk_level="high", requires_confirmation=True, timeout_seconds=20.0, rate_limit=5),
            ToolDefinition(web_search, timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(web_fetch, timeout_seconds=15.0, rate_limit=60),
            ToolDefinition(web_summarize, timeout_seconds=10.0, rate_limit=30),
            ToolDefinition(web_extract_facts, timeout_seconds=10.0, rate_limit=30),
            ToolDefinition(google_gmail_search, required_scopes=(GMAIL_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(google_gmail_read, required_scopes=(GMAIL_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(google_gmail_summarize, required_scopes=(GMAIL_READ_SCOPE,), timeout_seconds=15.0, rate_limit=20),
            ToolDefinition(google_calendar_list, required_scopes=(CALENDAR_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(google_calendar_freebusy, required_scopes=(CALENDAR_FREEBUSY_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(google_calendar_draft, risk_level="medium", requires_confirmation=True, required_scopes=(CALENDAR_EVENTS_SCOPE,), timeout_seconds=10.0, rate_limit=20),
            ToolDefinition(google_gmail_draft, risk_level="medium", requires_confirmation=True, required_scopes=(GMAIL_COMPOSE_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(google_gmail_send, risk_level="high", requires_confirmation=True, required_scopes=(GMAIL_SEND_SCOPE,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(google_calendar_create, risk_level="medium", requires_confirmation=True, required_scopes=(CALENDAR_EVENTS_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(google_calendar_update, risk_level="medium", requires_confirmation=True, required_scopes=(CALENDAR_EVENTS_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(google_calendar_cancel, risk_level="high", requires_confirmation=True, required_scopes=(CALENDAR_EVENTS_SCOPE,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(google_drive_search, required_scopes=(DRIVE_METADATA_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(google_drive_read, required_scopes=(DRIVE_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(google_drive_create, risk_level="medium", requires_confirmation=True, required_scopes=(DRIVE_FILE_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(google_drive_update, risk_level="medium", requires_confirmation=True, required_scopes=(DRIVE_FILE_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(google_drive_delete, risk_level="high", requires_confirmation=True, required_scopes=(DRIVE_FILE_SCOPE,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(graph_mail_search, required_scopes=(GRAPH_MAIL_READ,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(graph_mail_read, required_scopes=(GRAPH_MAIL_READ,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(graph_mail_draft, risk_level="medium", requires_confirmation=True, required_scopes=(GRAPH_MAIL_WRITE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(graph_mail_send, risk_level="high", requires_confirmation=True, required_scopes=(GRAPH_MAIL_SEND,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(graph_calendar_list, required_scopes=(GRAPH_CALENDAR_READ,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(graph_calendar_find_time, required_scopes=(GRAPH_CALENDAR_READ,), timeout_seconds=15.0, rate_limit=20),
            ToolDefinition(graph_calendar_create, risk_level="medium", requires_confirmation=True, required_scopes=(GRAPH_CALENDAR_WRITE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(graph_calendar_update, risk_level="medium", requires_confirmation=True, required_scopes=(GRAPH_CALENDAR_WRITE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(graph_calendar_cancel, risk_level="high", requires_confirmation=True, required_scopes=(GRAPH_CALENDAR_WRITE,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(graph_files_search, required_scopes=(GRAPH_FILES_READ,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(graph_files_read, required_scopes=(GRAPH_FILES_READ,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(graph_files_update, risk_level="medium", requires_confirmation=True, required_scopes=(GRAPH_FILES_WRITE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(sensor_read, required_scopes=(ESP32_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(sensor_history, required_scopes=(ESP32_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(device_status, required_scopes=(ESP32_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(device_command_preview, risk_level="medium", requires_confirmation=True, required_scopes=(ESP32_CONTROL_SCOPE,), timeout_seconds=15.0, rate_limit=20),
            ToolDefinition(device_command_execute, risk_level="high", requires_confirmation=True, required_scopes=(ESP32_CONTROL_SCOPE,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(mern_search, required_scopes=(MERN_READ_SCOPE,), timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(mern_create, risk_level="medium", requires_confirmation=True, required_scopes=(MERN_WRITE_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(mern_update, risk_level="medium", requires_confirmation=True, required_scopes=(MERN_WRITE_SCOPE,), timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(mern_delete, risk_level="high", requires_confirmation=True, required_scopes=(MERN_WRITE_SCOPE,), timeout_seconds=15.0, rate_limit=5),
            ToolDefinition(sms_draft, risk_level="medium", requires_confirmation=True, timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(sms_send, risk_level="high", requires_confirmation=True, timeout_seconds=15.0, rate_limit=5, idempotent=True),
            ToolDefinition(call_draft, risk_level="medium", requires_confirmation=True, timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(call_place, risk_level="high", requires_confirmation=True, timeout_seconds=20.0, rate_limit=3, idempotent=True),
            ToolDefinition(call_status, timeout_seconds=15.0, rate_limit=30),
            ToolDefinition(call_hangup, risk_level="high", requires_confirmation=True, timeout_seconds=15.0, rate_limit=10),
            ToolDefinition(call_transcript, risk_level="high", requires_confirmation=True, timeout_seconds=15.0, rate_limit=10),
        ))
        names = [definition.tool.name for definition in self.definitions]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")

    @property
    def tools(self) -> list[BaseTool]:
        return [definition.tool for definition in self.definitions]

    def get(self, name: str) -> ToolDefinition:
        for definition in self.definitions:
            if definition.tool.name == name:
                return definition
        raise KeyError(f"Tool is not registered: {name}")
    DRIVE_FILE_SCOPE,
    DRIVE_METADATA_SCOPE,
    DRIVE_READ_SCOPE,
    google_drive_create,
    google_drive_delete,
    google_drive_read,
    google_drive_search,
    google_drive_update,
