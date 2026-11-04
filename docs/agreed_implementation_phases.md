# Agreed implementation phases

This is the canonical implementation roadmap for the voice assistant. Phase
numbering and scope in this document take precedence over earlier exploratory
phase labels.

## Phase 1 — Tool execution foundation

Implement the infrastructure required by every future tool:

- Typed Pydantic input schemas
- Tool registry and allow-list
- Risk classification
- Permission policy
- Confirmation workflow
- Timeout and cancellation
- Idempotency keys
- Structured success and error results
- Audit records
- Tool status and confirmation WebSocket events

This phase must not add external integrations.

## Phase 2 — Existing safe tools

Reintegrate and verify:

- `calculate`
- `get_current_time`

These validate the complete tool execution path without OAuth, network access,
or destructive actions.

## Phase 3 — Local workspace read tools

Implement:

1. `workspace_list_files`
2. `workspace_search`
3. `workspace_read_file`
4. `workspace_git_status`
5. `workspace_git_diff`

Requirements:

- Configured workspace roots only
- Path traversal protection
- Secret-file filtering
- File-size limits
- Extension allow-lists
- Read-only behavior
- Audit logging

## Phase 4 — Local workspace mutation tools

Implement:

1. `workspace_create_file`
2. `workspace_apply_patch`
3. `workspace_rename_file`
4. `workspace_git_commit`
5. `workspace_delete_file`

Every mutation must show a preview or diff, require confirmation, use an
idempotency key, record an audit event, support rollback where possible, and
reject ambiguous paths or overwrite operations. `workspace_run_command` is
deferred because arbitrary command execution is higher risk.

## Phase 5 — Web research tools

Implement:

- `web_search`
- `web_fetch`
- `web_summarize`
- `web_extract_facts`

Responses must include source URLs where applicable. Private workspace content
must never be sent to public web providers silently.

## Phase 6 — Google Calendar

Implement in this order:

1. Read calendar events
2. Read free/busy availability
3. Prepare meeting drafts
4. Create meetings after confirmation
5. Update meetings after confirmation
6. Cancel meetings with strong confirmation

## Phase 7 — Gmail and Drive

Gmail:

1. Search emails
2. Read selected messages
3. Summarize threads
4. Create drafts
5. Send messages after confirmation

Drive:

1. Search files
2. Read files
3. Create files
4. Update files with preview
5. Move files to trash after confirmation

## Phase 8 — Microsoft Graph

Add Outlook, Microsoft Calendar, OneDrive, and SharePoint tools behind the same
interfaces used for Google Workspace. The agent should not require different
reasoning logic for Google and Microsoft providers.

## Phase 9 — IoT and application integrations

Implement:

- ESP32 sensor readings
- Device status
- MERN read operations
- Device command previews
- Confirmed device commands
- MERN create/update/delete operations

Physical device actions always require explicit confirmation.

## Phase 10 — SMS and phone tools

Implement only after approval, audit, and identity controls are reliable:

- SMS draft
- SMS send
- Call draft
- Outbound call
- Call status
- Call hangup
- Call transcript

Inbound call answering, recording, and proactive call handling are a separate
advanced phase requiring consent, retention, legal, and provider-policy review.

Implementation status: the outbound SMS and call lifecycle tools are now
implemented in `backend/tools/telephony_tools.py`. Inbound and proactive
capabilities remain deferred as specified above.

## Standard implementation cycle for every tool

1. Define a typed input schema.
2. Define risk and permission policy.
3. Implement the provider or local adapter.
4. Add timeout and cancellation handling.
5. Add structured errors.
6. Add confirmation when external state changes.
7. Add audit logging.
8. Connect it to the LangGraph tool node.
9. Add mocked unit and integration tests.
10. Verify WebSocket status, confirmation, and result events.
11. Update `docs/tool_catalog.md`.
12. Update `docs/current_state_handoff.md`.
