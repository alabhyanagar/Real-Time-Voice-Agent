# Phase 9 — Authenticated OAuth gateway and user scope context

Phase 9 completes the connector lifecycle boundary around the Phase 8 Google
tools.

## Routes

Mounted under `/api/v1/oauth/google`:

- `GET /start?scopes=...` requires the authenticated HTTP user and returns a
  short-lived PKCE authorization URL.
- `GET /callback?state=...&code=...` validates the user-bound state and stores
  the exchanged token.
- `POST /revoke` requires the authenticated user, revokes the provider token,
  and deletes the local encrypted record.

The callback never accepts a user ID from the browser; the user identity comes
from the server-side OAuth state record.

## Persistence and scope propagation

- `SQLiteTokenStore` persists encrypted token blobs keyed by user ID.
- Fernet encryption requires `GOOGLE_OAUTH_ENCRYPTION_KEY` in production.
- `GoogleOAuthService.scopes_for_user` reads only scope names, never token
  values, and `LLMService` passes them into the tool graph's `ToolContext`.
- The executor's existing `required_scopes` policy denies a tool when the
  authenticated user has not granted that exact scope.

The current SQLite store is a durable single-instance baseline. Production
deployment should move it to a KMS-backed shared database and inject the
user's refreshed access token into connector clients without exposing it to
model messages or audit records.

## Verification

Tests cover PKCE state binding, encrypted persistence, code exchange,
revocation primitives, write-tool behavior, and the full existing suite.
