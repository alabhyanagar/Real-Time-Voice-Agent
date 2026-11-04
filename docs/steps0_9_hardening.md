# Steps 0–9 hardening checkpoint

This checkpoint closes the remaining plan-level gaps identified before Step 10.

## Completed hardening work

- Workspace reads now reject configured secret-file patterns and enforce an
  optional extension allow-list.
- Workspace mutations expose idempotency-key inputs; the graph transfers an
  idempotency key into `ToolCallRequest`, and confirmations preserve it through
  approval/resume.
- `workspace_git_revert_commit` provides explicit, confirmation-gated rollback
  for a selected commit.
- `ToolExecutor` now enforces configured per-user, per-tool rolling one-minute
  rate limits rather than treating `rate_limit` as metadata only.
- The protocol now supports a client `tool_confirmation_response` event. The
  gateway routes approval/rejection to a session-bound native LangGraph
  `interrupt()` checkpoint. The resumed graph executes or rejects the pending
  action exactly once and emits status/result events.
- WebSocket, confirmation, rate-limit, secret-filter, and extension-filter
  coverage has been added to the regression suite.
- Approval rejection is a first-class, redacted audit event and never executes
  the requested tool.
- Microsoft Graph now has authenticated PKCE start/callback/revoke routes,
  encrypted per-user SQLite token storage, refresh-on-expiry, and context-bound
  token injection. It no longer needs a deployment-wide token for a delegated
  user action.
- JWT `scope`/`scopes` claims are normalized server-side and placed in the
  session tool context. ESP32 and MERN tools require explicit read/control or
  read/write scopes before a configured service connector can be used.

## Confirmation behavior

The executor is the policy and audit boundary; LangGraph is the approval
checkpoint. A mutating call creates one user-bound, short-lived approval record
then interrupts the graph. An authenticated WebSocket decision resumes that
exact checkpoint. Graph replay reuses the existing approval rather than sending
a duplicate prompt. The connection receives `tool_confirmation`, followed by
`tool_status` and a final result event.

## Resolved after the original checkpoint

- The original Microsoft Graph OAuth deferral is now resolved by the delegated
  OAuth implementation above.
- ESP32/MERN endpoints still need deployment configuration, but access is no
  longer globally available: server-validated JWT scopes gate every tool.

## Deferred boundaries

- Microsoft Graph remains a configured adapter; adding delegated Microsoft OAuth
  token lifecycle is a connector-expansion task, not a Step 0–9 blocker.
- ESP32 and MERN adapters require deployment-specific endpoint/API-key setup.
- Full telephony transcription, consent retention, inbound calls, and proactive
  workflows remain intentionally outside the agreed Phase 1–10 scope.
