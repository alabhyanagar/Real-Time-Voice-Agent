# Step 10 — Redis conversation memory

Step 10 adds a bounded, user-isolated conversation memory layer without
persisting preferences automatically.

## Runtime behavior

- `backend/memory/redis_window.py` stores messages, summaries, state, generation
  IDs, and short-lived cancellation signals in Redis.
- Keys use SHA-256 digests of the authenticated user and session identifiers, so
  raw identity values are not used as Redis key material.
- Each session is TTL-bound. A per-user session index supports authenticated
  export of retained sessions.
- The default window is 15 messages and 4,000 estimated tokens. Old messages
  are summarized before they are evicted.
- `backend/memory/summarizer.py` provides a deterministic bounded fallback and
  accepts an async model callback for a production summarizer.
- `backend/memory/memory_policy.py` validates identities and centralizes limits.
- If optional Redis is disabled, tests and local development use a process-local
  Redis-compatible fallback. Set `MEMORY_REDIS_REQUIRED=true` to make startup
  verify Redis independently; production configuration enforces this setting.

## Reconnect and controls

The WebSocket endpoint accepts an optional `session_id` query parameter as a
reconnect handle. The browser stores only the server-issued handle and sends it
on the next connection. The authenticated JWT remains the only source of
`user_id`. On connection startup, the previous bounded context and summary are
restored.

Authenticated memory controls are available under `/api/v1/memory`:

- `GET /api/v1/memory` — export all retained sessions for the authenticated user.
- `GET /api/v1/memory/{session_id}` — export one session.
- `DELETE /api/v1/memory/{session_id}` — delete one session.
- `POST /api/v1/memory/{session_id}/forget` — explicit forget alias.

No endpoint or memory adapter automatically saves user preferences. Full
long-term semantic retrieval remains Step 11 RAG work.

## Verification

`tests/test_memory.py` covers reconnect recovery, bounded windows,
summarization, user isolation, state/cancellation signals, export, deletion,
and unsafe identity rejection.
