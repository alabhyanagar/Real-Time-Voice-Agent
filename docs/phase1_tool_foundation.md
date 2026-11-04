# Phase 1 — Tool Execution Foundation

Phase 1 establishes the shared safety and execution boundary for every future
assistant tool. It does not add external integrations or workspace mutation.

## Components

- `backend/tools/schemas.py` defines typed requests, identity context, policy
  decisions, and structured results.
- `backend/tools/policies.py` applies risk, client, confirmation, and scope rules.
- `backend/tools/approval.py` stores short-lived, user-bound confirmations.
- `backend/tools/audit.py` records decisions and executions with sensitive values
  redacted.
- `backend/tools/executor.py` validates arguments, enforces policy, applies
  timeouts, handles cancellation, supports idempotency, emits status callbacks,
  and returns safe errors.
- `backend/tools/registry.py` now records risk, scopes, client restrictions,
  rate-limit metadata, audit requirements, and idempotency behavior.

## Execution flow

```text
model tool request
  → registry allow-list
  → typed argument validation
  → client and scope authorization
  → confirmation when risk requires it
  → idempotency lookup
  → timeout and cancellation boundary
  → execution
  → redacted audit record
  → structured result and status event
```

Unknown tools cannot execute. Medium and high risk tools require confirmation by
policy even if a definition does not explicitly set `requires_confirmation`.
Confirmation requests are short-lived and bound to the requesting user.

The legacy tool graph now delegates execution to `ToolExecutor`. The active Step
8 graph remains tool-free until the Step 9 tool graph is explicitly introduced.

## Verification

The provider-free tests cover successful execution, unknown tools, invalid
arguments, confirmation and resume, idempotency, and timeout failures.
