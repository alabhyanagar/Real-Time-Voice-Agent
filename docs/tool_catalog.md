# Voice Agent Tool Catalog

This is the developer reference for tools available to the voice assistant.
It separates tools that already exist in the repository from tools planned for
the Step 9 implementation and later integration phases.

## Status and execution rules

| Status | Meaning |
|---|---|
| Implemented | Code exists and has a typed schema. |
| Registered | Present in the legacy tool registry, but not currently bound by the Step 8 live graph. |
| Planned | Design approved for a future implementation. |
| Deferred | Intentionally postponed because it needs additional security, provider, or product decisions. |

Risk levels:

- `low`: read-only, local, deterministic, or reversible. May run automatically
  after authorization is established.
- `medium`: creates or changes user data. Show a preview and request confirmation.
- `high`: sends external communications, deletes data, changes permissions, or
  controls a phone call. Require explicit confirmation and an audit record.

Every implemented tool must have a typed input schema, a timeout, cancellation
support, an authorization policy, structured errors, and an audit decision. An
unknown tool name must never execute.

## Implemented starter tools

These tools are defined in `backend/tools/safe_tools.py` and exposed through
`backend/tools/registry.py`. They are deterministic examples for validating the
tool registry and policy pipeline.

| Tool | Purpose | Risk | Confirmation | Auth / OAuth | Audit |
|---|---|---:|---:|---|---:|
| `calculate` | Add, subtract, multiply, or divide two numbers | low | No | None | Optional diagnostic event |
| `get_current_time` | Return the current time in an IANA timezone such as `Asia/Kolkata` or `UTC` | low | No | None | Optional diagnostic event |

The Step 8 production path is intentionally tool-free. These starter tools are
kept for the Step 9 workshop and must be explicitly attached to the future tool
graph before they can be invoked by the model.

## Phase 3–4 workspace tools

These tools form the recommended first product surface for the personal
workspace assistant.

| Tool | Purpose | Risk | Confirmation | Auth / scope | Notes |
|---|---|---:|---:|---|---|
| `workspace_list_files` | List files in approved workspace roots | low | No | Local workspace authorization | Never expose paths outside allowlisted roots |
| `workspace_search` | Search filenames and text in approved roots | low | No | Local workspace authorization | Enforce size, extension, and secret-file filters |
| `workspace_read_file` | Read a file or selected range | low | No | Local workspace authorization | Redact secrets and cap output size |
| `workspace_create_file` | Create a new file from user-provided content | medium | Yes | Local workspace authorization | Show path and content preview |
| `workspace_apply_patch` | Apply a targeted edit to an existing file | medium | Yes | Local workspace authorization | Show a unified diff before execution |
| `workspace_rename_file` | Rename or move a file within an approved root | medium | Yes | Local workspace authorization | Prevent traversal and overwrite by default |
| `workspace_delete_file` | Delete a file or directory | high | Yes, with step-up confirmation | Local workspace authorization | Prefer recycle-bin/trash behavior and audit the target |
| `workspace_run_command` | Run an approved command in a sandbox | high | Yes | Local execution policy | Start with a strict command allowlist; never expose arbitrary shell |
| `workspace_git_status` | Show repository status and changed files | low | No | Local workspace authorization | Read-only |
| `workspace_git_diff` | Summarize or display pending changes | low | No | Local workspace authorization | Read-only |
| `workspace_git_commit` | Create a commit from selected changes | medium | Yes | Local workspace authorization | Require explicit files and commit message |

## Phase 5 web and research tools

| Tool | Purpose | Risk | Confirmation | Auth | Notes |
|---|---|---:|---:|---|---|
| `web_search` | Search the configured public web provider | low | No | Search provider credential | Return sources and timestamps |
| `web_fetch` | Fetch an explicitly selected public page | low | No | Optional domain/provider policy | Restrict protocols, SSRF, redirects, and response size |
| `web_summarize` | Summarize fetched pages or documents | low | No | Uses approved model | Preserve source links |
| `web_extract_facts` | Extract structured facts from a selected source | low | No | Uses approved model | Mark uncertain or conflicting values |

Web tools should not silently send private workspace content to an external
site. Any request that combines private documents with web search must make the
data boundary visible to the user.

## Phase 6–7 Google Workspace tools

Google Workspace is the recommended first external connector because it matches
the product direction. Use OAuth with the narrowest scopes required for each
tool. Google documents separate scopes for read-only and write access, and
public applications may require OAuth verification.

| Tool | Purpose | Risk | Confirmation | Suggested scope family |
|---|---|---:|---:|---|
| `google_gmail_search` | Search messages by sender, subject, date, or label | low | No | Gmail read-only |
| `google_gmail_read` | Read a selected email or thread | low | No | Gmail read-only |
| `google_gmail_summarize` | Summarize a selected thread | low | No | Gmail read-only |
| `google_gmail_draft` | Create an email draft | medium | Yes before saving if content is sensitive | Gmail compose |
| `google_gmail_send` | Send an email or reply | high | Always | Gmail send/compose |
| `google_calendar_list` | List events in a time range | low | No | Calendar read-only |
| `google_calendar_freebusy` | Find availability | low | No | Calendar free/busy |
| `google_calendar_create` | Create a calendar event | medium | Always | Calendar events write |
| `google_calendar_update` | Change an event or attendees | medium | Always | Calendar events write |
| `google_calendar_cancel` | Cancel an event and notify attendees | high | Always | Calendar events write |
| `google_drive_search` | Search files and folders | low | No | Drive metadata/read-only |
| `google_drive_read` | Read a selected Drive file | low | No | Drive read-only |
| `google_drive_create` | Create a document or upload a file | medium | Yes | Drive file write |
| `google_drive_update` | Update file content or metadata | medium | Yes with diff/preview | Drive file write |
| `google_drive_delete` | Delete or move a Drive file to trash | high | Always | Drive file write |

Phases 6–7 implement the Calendar, Gmail, and Drive rows with confirmation and
OAuth scope enforcement. OAuth callback routing and durable encrypted token
persistence are implemented in `backend/integrations/google_oauth.py`.

## Phase 8 Microsoft Graph tools

These mirror the Google tools for Outlook, Microsoft 365 files, and calendars.
Delegated Microsoft OAuth is implemented through authenticated PKCE
start/callback/revoke routes and encrypted user-token storage. The active
user's Graph token and granted scopes are resolved only inside the executor's
context; application permissions should be reserved for explicitly administered
organizational workflows.

| Tool | Purpose | Risk | Confirmation |
|---|---|---:|---:|
| `graph_mail_search` | Search Outlook mail | low | No |
| `graph_mail_read` | Read a selected message or thread | low | No |
| `graph_mail_draft` | Create a draft message | medium | Yes |
| `graph_mail_send` | Send or reply to a message | high | Always |
| `graph_calendar_list` | List events and calendar views | low | No |
| `graph_calendar_find_time` | Find workable meeting times | low | No |
| `graph_calendar_create` | Create a meeting | medium | Always |
| `graph_calendar_update` | Update attendees, time, or details | medium | Always |
| `graph_calendar_cancel` | Cancel a meeting | high | Always |
| `graph_files_search` | Search OneDrive or SharePoint files | low | No |
| `graph_files_read` | Read a selected file | low | No |
| `graph_files_update` | Update a file after preview | medium | Yes |

## Phase 10 SMS and phone tools

Communication tools are a later phase because they create immediate external
side effects and can incur provider charges.

| Tool | Purpose | Risk | Confirmation | Provider |
|---|---|---:|---:|---|
| `sms_draft` | Prepare an SMS message | medium | Yes before saving | Twilio or equivalent |
| `sms_send` | Send an SMS or MMS | high | Always | Twilio or equivalent |
| `call_draft` | Prepare a call plan and recipient summary | medium | Yes | Twilio or equivalent |
| `call_place` | Place an outbound call | high | Always | Twilio Voice or equivalent |
| `call_hangup` | End an active assistant-controlled call | high | Explicit command | Twilio Voice or equivalent |
| `call_status` | Read the state of an assistant-controlled call | low | No | Twilio Voice or equivalent |
| `call_transcript` | Retrieve a permitted call transcript | high | Yes | Provider and recording policy |
| `call_answer` | Answer or route an incoming call | high | Explicit user policy plus confirmation | Telephony provider |

Inbound call answering, recording, and transcription require a separate consent
and retention design before implementation.

The outbound Phase 10 tools are implemented through the Twilio adapter with
E.164 validation, server-side credentials, confirmation policies, rate limits,
and executor audit/status events. Inbound/proactive capabilities remain
deferred.

## Phase 9 IoT and application tools

These tools support the project's ESP32 and MERN integration possibilities.
Their service connector credential stays on the server, while JWT scopes gate
the active user: `esp32.read`, `esp32.control`, `mern.read`, and `mern.write`.

| Tool | Purpose | Risk | Confirmation |
|---|---|---:|---:|
| `sensor_read` | Read an ESP32 sensor value | low | No |
| `sensor_history` | Retrieve recent sensor measurements | low | No |
| `device_status` | Report device connectivity and health | low | No |
| `device_command_preview` | Show a proposed device command | medium | Yes |
| `device_command_execute` | Execute an approved device command | high | Always for physical effects |
| `mern_search` | Read records from approved application APIs | low | No |
| `mern_create` | Create an application record | medium | Yes |
| `mern_update` | Update an application record | medium | Yes |
| `mern_delete` | Delete an application record | high | Always |

## Tool execution contract

Each registered tool should provide the following metadata:

```text
name
description
input_schema
risk_level
requires_confirmation
required_scopes
allowed_clients
timeout_seconds
rate_limit
idempotency_key_policy
audit_policy
rollback_policy
```

The execution path is:

```text
model decision
  → tool name allow-list check
  → typed argument validation
  → user and connector authorization
  → confirmation when required
  → timeout and cancellation boundary
  → execution
  → structured result or safe error
  → audit record
  → spoken and UI response
```

## Recommended implementation order

1. Tool foundation and safe calculator/clock verification.
2. Workspace reads, Git reads, then confirmed workspace mutations.
3. Web search, fetch, summarization, and fact extraction.
4. Google Calendar, Gmail, and Drive read/write flows.
5. Microsoft Graph adapters behind the same interfaces.
6. ESP32 sensor/device and MERN application integrations.
7. Defer SMS, telephony, arbitrary commands, inbound calls, and proactive
   workflows until the approval and audit system is proven.

## Current implementation boundary

At the time of this document:

- All Phase 1–9 tools listed in this catalog are concrete registry tools,
  including workspace Git, web research, Google Workspace, Microsoft Graph,
  ESP32, and MERN adapters.
- Phase 4 adds `workspace_preview_patch`, `workspace_apply_patch`,
  `workspace_create_file`, `workspace_rename_file`, and `workspace_delete_file`.
  Mutations are confirmation-gated by risk policy; deletes move files to a
  reversible per-root trash directory instead of permanently removing them.
- Phase 2 integrates both starter tools into the opt-in model tool-call graph;
  set `TOOLS_ENABLED=true` to select it at runtime.
- Phase 1 now provides typed schemas, policy decisions, confirmation storage,
  redacted audit records, timeout/cancellation handling, and idempotent execution
  in `backend/tools/`.
- `ToolRegistry` is an explicit allow-list and validates unique tool names.
- The legacy `backend/llm/graph.py` delegates execution to `ToolExecutor`.
- The active Step 8 `backend/agent/graph.py` is intentionally tool-free.
- SMS, telephony, inbound calls, arbitrary command execution, and proactive
  workflows remain intentionally outside the Phase 1–9 strategy scope.
