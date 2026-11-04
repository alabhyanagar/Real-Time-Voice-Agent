# Phase 7 — Google Workspace read-only connectors

Phase 7 adds the first external productivity connector using Google REST APIs.
This phase intentionally stops at read-only operations; email sending, drafts,
calendar writes, and Drive mutations remain confirmation-gated future work.

## Tools

| Tool | Scope | Behavior |
|---|---|---|
| `google_gmail_search` | `gmail.readonly` | Bounded Gmail query with page token |
| `google_gmail_read` | `gmail.readonly` | Metadata by default; body only when requested |
| `google_calendar_list` | `calendar.readonly` | Ordered events in an ISO-8601 time range |
| `google_calendar_freebusy` | `calendar.freebusy` | Busy intervals for selected calendars |

## Security contract

- Requests require a configured OAuth access token and the exact read-only scope.
- Registry metadata also declares the required scope so the executor can deny a
  call when a user/session has not been granted it.
- IDs, timestamps, result counts, and response payloads are bounded and validated.
- Only HTTPS Google API base URLs are accepted by configuration.
- Tool definitions are low-risk, read-only, rate-limited, and audited by the
  existing executor.

The current adapter accepts an access token from configuration for local
development. Production OAuth authorization-code flow, encrypted token storage,
refresh-token rotation, and per-user scope injection belong to the gateway
connector layer before deployment.

## Verification

Mocked tests cover Gmail search, Calendar event reads, scope denial, and invalid
input handling without making external API calls.
