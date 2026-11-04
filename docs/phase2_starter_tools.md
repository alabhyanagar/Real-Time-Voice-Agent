# Phase 2 — Starter Tool Integration

Phase 2 connects the existing `calculate` and `get_current_time` tools to the
policy-aware executor and model tool-call loop.

## Runtime switch

The `TOOLS_ENABLED` setting controls the live service:

- `false` keeps the Step 8 tool-free graph active.
- `true` selects the legacy-compatible tool graph with the Phase 1 executor.

The default is `false` so a deployment can enable tools deliberately after
provider tool-calling support and credentials have been checked.

## Flow

```text
model response with tool call
  → registered tool lookup
  → typed argument validation
  → risk and permission policy
  → executor timeout/cancellation boundary
  → tool result message
  → model final response
```

The graph emits `requested`, `running`, and `completed` or `failed` status
callbacks. These callbacks are already connected to the orchestrator's tool
status events and filler-audio path. Every successful execution is recorded in
the Phase 1 audit log.

## Starter-tool policy

Both starter tools are local, deterministic, read-only, and low risk. They do
not require OAuth or user confirmation. The executor still validates their
typed arguments, applies its timeout, records an audit result, and rejects
unknown tools.

## Verification

`tests/test_tool_integration.py` uses a provider-free fake tool-calling model to
verify model selection, executor invocation, status events, final response
generation, and audit completion.
