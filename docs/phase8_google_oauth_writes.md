# Phase 8 — Google OAuth lifecycle and confirmed writes

Phase 8 extends the Google connector with PKCE authorization primitives,
encrypted process-local token storage, refresh-token exchange, and explicit
confirmation-gated write tools.

## OAuth lifecycle

- `OAuthStateStore` creates short-lived, user-bound state and PKCE verifiers.
- `GoogleOAuthService.authorization_url` builds a Google authorization URL with
  S256 PKCE, offline access, and explicit scopes.
- Authorization-code exchange and refresh-token requests validate responses and
  store tokens encrypted with Fernet.
- Durable production storage should replace the process-local `TokenStore` with
  a KMS-backed database before multi-instance deployment.

## Confirmed write tools

| Tool | Scope | Risk |
|---|---|---:|
| `google_gmail_draft` | `gmail.compose` | medium |
| `google_gmail_send` | `gmail.send` | high |
| `google_calendar_create` | `calendar.events` | medium |
| `google_calendar_update` | `calendar.events` | medium |
| `google_calendar_cancel` | `calendar.events` | high |

All are registered with the existing executor's required-scope policy and
confirmation flow. The tool implementations validate recipient addresses,
content size, event timestamps, IDs, and API responses. No write runs from the
model without an executor confirmation decision.

## Remaining production work

The gateway still needs authenticated per-user OAuth callback routes, durable
encrypted token persistence, token revocation, and refresh-on-expiry injection
into `ToolContext`. These are deliberately separate from tool execution so
credentials never enter model messages or audit payloads.
