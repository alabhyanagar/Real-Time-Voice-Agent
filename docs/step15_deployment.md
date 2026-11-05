# Step 15 — Deployment and Production Hardening

Step 15 introduces the complete containerised production deployment stack,
Nginx reverse proxy with TLS/WSS termination, PostgreSQL migrations, provider
circuit breakers, and automated backup/restore scripts.

---

## Infrastructure Overview

```
                               Internet / Clients
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │   Nginx (TLS & Rate Limiting) │
                       │   - Port 80 / 443             │
                       │   - WSS proxying (no buffer)  │
                       │   - Rate limit: 20 req/s      │
                       └───────────────┬───────────────┘
                                       │
                         Internal Docker Network
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
    ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
    │  voice-api       │     │  redis           │     │  postgres        │
    │  - Non-root      │     │  - Session memory│     │  - Users, Tokens │
    │  - Port 8000     │     │  - Port 6379     │     │  - Port 5432     │
    │  - CircuitBreak  │     │  - AOF enabled   │     │  - Migrations    │
    └─────────┬────────┘     └──────────────────┘     └──────────────────┘
              │
              ▼
    ┌──────────────────┐
    │  chromadb        │
    │  - Document RAG  │
    │  - Port 8001     │
    └──────────────────┘
```

---

## Components

### 1. Production Dockerfile (`infra/Dockerfile`)
- Multi-stage build (Python 3.11-slim builder and minimal runtime).
- Runs under unprivileged non-root user `appuser:appgroup` (UID 10001).
- Installs audio libraries (`libsndfile1`, `ffmpeg`).
- Built-in `HEALTHCHECK` probing `/livez`.

### 2. Multi-Service Docker Compose (`infra/docker-compose.yml`)
Four core services + Nginx reverse proxy:
- `voice-api`: Main application with CPU and memory resource constraints.
- `redis`: Redis 7.4 with Append-Only File (AOF) persistence and `volatile-lru` eviction.
- `postgres`: PostgreSQL 16 with auto-executing initialization migrations.
- `chromadb`: Vector DB running in persistent storage mode.
- `nginx`: Reverse proxy with WebSocket streaming timeouts (`3600s`).

### 3. Nginx Configuration (`infra/nginx.conf`)
- Unbuffered streaming for `/api/v1/ws/audio` (zero buffering latency).
- HTTP rate limiting: `20 req/s` with burst of 40 via `limit_req_zone`.
- Connection limiting: max 20 concurrent connections per client IP.
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`.

### 4. Database Migrations (`infra/migrations/001_initial_schema.sql`)
- `users`: User identity and JSONB preferences.
- `oauth_tokens`: Per-user encrypted tokens for Google and Microsoft.
- `sessions`: Session lifecycle and reconnect token indices.
- `conversations`: Persistent history and turn records.
- `tool_audit_logs`: Redacted tool execution and confirmation audit trails.

### 5. Provider Circuit Breakers (`backend/core/circuit_breaker.py`)
- Independent circuit breakers per provider (Groq, Deepgram, Gemini, Cartesia, ElevenLabs).
- `CLOSED` -> `OPEN` after 5 consecutive failures / timeouts.
- In `OPEN` state, calls fail-fast immediately without stalling the real-time audio pipeline.
- Transitions to `HALF_OPEN` after 30 seconds to probe provider recovery.

### 6. Backup & Restore Scripts
- `infra/backup.sh`: Dumps PostgreSQL, snapshots Redis (`BGSAVE`), archives ChromaDB vectors, and packages a timestamped archive.
- `infra/restore.sh`: Extracts backup archive and restores databases and vectors.

---

## One-Command Startup

To launch the full production stack:

```bash
docker compose -f infra/docker-compose.yml up -d
```

To view logs across all services:

```bash
docker compose -f infra/docker-compose.yml logs -f voice-api
```

To shut down cleanly while preserving persistent data:

```bash
docker compose -f infra/docker-compose.yml down
```

---

## Verification & Completion Criteria

- [x] Multi-stage, non-root `Dockerfile` created with `appuser` least privilege.
- [x] Docker Compose defines `voice-api`, `redis`, `postgres`, `chromadb`, and `nginx`.
- [x] Persistent volumes configured for Redis, PostgreSQL, and ChromaDB.
- [x] Nginx reverse proxy configured with WSS unbuffered pass-through and rate limiting.
- [x] PostgreSQL migration `001_initial_schema.sql` created.
- [x] Provider Circuit Breaker implemented in `backend/core/circuit_breaker.py` with 7 passing tests.
- [x] Executable backup and restore procedures created in `infra/backup.sh` and `infra/restore.sh`.

