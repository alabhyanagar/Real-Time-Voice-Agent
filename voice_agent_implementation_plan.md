# Voice Agent Upgrade Implementation Plan

This document defines the complete implementation plan for upgrading the current cascade voice assistant into an industry-level, LangChain/LangGraph-powered voice assistant.

Implementation will be incremental. Each step must be completed, tested, reviewed, and approved before the next step begins.

## Target technology architecture

- FastAPI/WebSockets for real-time audio transport.
- LangChain for model/provider abstraction, tools, structured output, and RAG.
- LangGraph for agent state, approval workflows, retries, checkpoints, and resumable execution.
- Redis for active session state and cancellation signals.
- PostgreSQL for durable data and LangGraph checkpoints.
- ChromaDB initially for local document retrieval.
- OpenTelemetry/LangSmith-compatible tracing for agent and latency monitoring.

LangGraph is used for stateful workflows, checkpointing, streaming, retries, and human approval interruptions. Raw PCM timing, VAD, playback, and barge-in remain outside the agent framework in deterministic asynchronous services.

## Target architecture

```text
Browser / Electron / React Native
│
├── AudioWorklet or native audio bridge
├── Echo cancellation and microphone controls
├── Local playback queue and immediate flush
└── Versioned WebSocket protocol
        │
        ▼
FastAPI Realtime Gateway
│
├── JWT authentication
├── Origin and frame validation
├── Connection/session manager
├── Per-session outbound queue
└── Turn ID and generation ID tracking
        │
        ▼
Realtime Session Controller
│
├── Silero VAD and turn detector
├── Deepgram/STT adapter
├── LangGraph agent runner
├── Sentence-level TTS queue
├── Barge-in cancellation
└── Telemetry events
        │
        ▼
LangGraph Voice Agent
│
├── classify_intent
├── retrieve_memory
├── retrieve_documents
├── call_model
├── validate_tool_call
├── require_confirmation
├── execute_tool
├── add_tool_result
├── generate_spoken_response
└── finalize_turn
        │
        ├── LangChain chat model
        │   ├── Groq
        │   ├── Gemini
        │   ├── Anthropic
        │   └── Local vLLM/Ollama
        │
        ├── Tool registry
        ├── Redis short-term memory
        ├── PostgreSQL durable state
        ├── ChromaDB/pgvector RAG
        └── LangSmith/OpenTelemetry tracing
```

## Revised project structure

```text
D:\Alabhya\Real-Time-Voice-Agent\
│
├── backend\
│   ├── main.py
│   ├── requirements.txt
│   │
│   ├── api\
│   │   ├── websocket_router.py
│   │   ├── health_router.py
│   │   └── auth_router.py
│   │
│   ├── core\
│   │   ├── config.py
│   │   ├── lifecycle.py
│   │   ├── security.py
│   │   └── logging.py
│   │
│   ├── protocol\
│   │   ├── messages.py
│   │   ├── audio_frames.py
│   │   ├── events.py
│   │   └── versioning.py
│   │
│   ├── sessions\
│   │   ├── session_manager.py
│   │   ├── session_controller.py
│   │   ├── session_state.py
│   │   ├── cancellation.py
│   │   └── outbound_queue.py
│   │
│   ├── audio\
│   │   ├── vad_service.py
│   │   ├── turn_detector.py
│   │   ├── audio_format.py
│   │   └── audio_metrics.py
│   │
│   ├── providers\
│   │   ├── llm\
│   │   │   ├── base.py
│   │   │   ├── factory.py
│   │   │   ├── groq_provider.py
│   │   │   ├── gemini_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   └── local_provider.py
│   │   │
│   │   ├── stt\
│   │   │   └── deepgram_provider.py
│   │   │
│   │   └── tts\
│   │       ├── elevenlabs_provider.py
│   │       ├── deepgram_provider.py
│   │       └── tts_stream.py
│   │
│   ├── agent\
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   ├── prompts.py
│   │   └── policies.py
│   │
│   ├── tools\
│   │   ├── registry.py
│   │   ├── schemas.py
│   │   ├── executor.py
│   │   ├── approval.py
│   │   ├── audit.py
│   │   └── policies.py
│   │
│   ├── memory\
│   │   ├── redis_window.py
│   │   ├── postgres_store.py
│   │   ├── summarizer.py
│   │   ├── memory_policy.py
│   │   └── rag\
│   │       ├── ingestion.py
│   │       ├── retriever.py
│   │       ├── query_rewriter.py
│   │       └── citations.py
│   │
│   ├── observability\
│   │   ├── tracing.py
│   │   ├── metrics.py
│   │   ├── events.py
│   │   └── cost_tracking.py
│   │
│   └── tests\
│       ├── unit\
│       ├── integration\
│       ├── contract\
│       ├── audio\
│       └── load\
│
├── frontend\
│   ├── index.html
│   ├── app.js
│   ├── audio-worklet.js
│   ├── protocol-client.js
│   ├── playback-queue.js
│   └── components\
│       ├── tool-card.js
│       ├── confirmation-dialog.js
│       └── metrics-panel.js
│
├── infra\
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── migrations\
│
├── docs\
│   ├── architecture.md
│   ├── websocket-protocol.md
│   ├── tools.md
│   ├── security.md
│   └── operations.md
│
├── .env.example
├── pyproject.toml
└── README.md
```

## Execution method for every step

Each implementation step follows this exact cycle:

1. Define the step's objective and scope.
2. Inspect only the relevant current files.
3. Create a small implementation plan for that step.
4. Modify only the required files.
5. Add or update tests.
6. Run formatting, static checks, and smoke tests.
7. Inspect the resulting diff.
8. Report files changed, behavior added, tests run, remaining risks, and the next-step recommendation.
9. Stop and wait for approval before proceeding.

We should implement directly in the project checkout one step at a time. A single large master prompt for another agent is not recommended because it can modify many modules before the first checkpoint, make assumptions about dependencies, and make failures difficult to isolate. If another coding agent is used, give it only a narrowly scoped step-specific task, then review and test the result here.

# The 16 implementation steps

## Step 0 — Baseline and safety snapshot

Before changing behavior:

- Record the current project tree.
- Create a minimal smoke test for FastAPI startup.
- Test `/health`.
- Test WebSocket connection.
- Test VAD initialization.
- Test STT/LLM/TTS configuration errors.
- Verify environment variables without exposing secrets.
- Consolidate current dependency information.
- Create `.env.example` without secrets.
- Document how to start the current version.
- Confirm existing frontend behavior is preserved.

Expected additions:

```text
backend/tests/
├── conftest.py
├── test_health.py
├── test_websocket_contract.py
└── test_configuration.py

.env.example
README.md
```

Completion criteria:

- The current prototype still starts.
- A baseline WebSocket test exists.
- Missing-provider-key behavior is documented.
- Future regressions can be compared with this baseline.

No tools are implemented in this step.

## Step 1 — Dependency and configuration foundation

Update:

```text
backend/core/config.py
backend/requirements.txt
requirements.txt
```

Add typed settings for:

- `LLM_PROVIDER` and `LLM_MODEL`.
- Groq, Gemini, Anthropic, and local model credentials.
- STT and TTS providers.
- Redis and PostgreSQL URLs.
- ChromaDB path or URL.
- JWT issuer, audience, and signing configuration.
- Allowed WebSocket origins.
- Maximum audio frame size.
- Audio sample rate and channels.
- Tool timeouts and rate limits.
- Telemetry settings.
- Development, staging, and production modes.

Add dependency groups for LangChain, LangGraph, provider integrations, Redis, PostgreSQL, ChromaDB, OpenTelemetry, testing, and linting.

Completion criteria:

- One authoritative dependency workflow exists.
- Missing production secrets fail clearly.
- Development defaults cannot accidentally be used in production.
- Provider selection works from configuration.

## Step 2 — Versioned WebSocket protocol

Create:

```text
backend/protocol/messages.py
backend/protocol/events.py
backend/protocol/audio_frames.py
backend/protocol/versioning.py
```

Define Pydantic models for client messages:

- `hello`
- `audio_format`
- `audio_frame`
- `cancel`
- `flush_ack`
- `resume`
- `ping`
- `client_metrics`

Define server messages:

- `ready`
- `state`
- `transcript`
- `response_text_delta`
- `audio_start`
- `audio_end`
- `audio_flush`
- `tool_status`
- `tool_confirmation`
- `ui_card`
- `error`
- `telemetry`

Every turn contains:

```text
session_id
turn_id
response_id
generation_id
sequence_number
timestamp
protocol_version
```

Binary audio remains binary PCM instead of base64. The audio format must be negotiated explicitly.

Completion criteria:

- Invalid messages are rejected.
- Oversized frames are rejected.
- Old or cancelled generation IDs are ignored.
- Frontend and backend complete a full test turn.

## Step 3 — FastAPI gateway hardening

Refactor:

```text
backend/routers/websocket_router.py
backend/main.py
```

Add:

- JWT validation during WebSocket admission.
- WebSocket origin validation.
- Session identity from authenticated claims.
- Heartbeats and connection timeouts.
- Per-user and per-session rate limits.
- Maximum binary-frame size.
- Backpressure handling.
- Structured error responses.
- One outbound queue per connection.
- `/livez` and `/readyz` endpoints.
- Application lifespan startup and shutdown.

At startup:

- Load the VAD model once.
- Initialize provider clients.
- Initialize Redis.
- Initialize PostgreSQL.
- Initialize ChromaDB.
- Register telemetry.
- Report readiness only when required dependencies are available.

Completion criteria:

- Unauthenticated connections are rejected.
- WebSocket sends cannot interleave unpredictably.
- Disconnect cleanup is graceful.
- Health checks distinguish alive from ready.

## Step 4 — Session controller and state machine

Replace the current orchestration logic in:

```text
backend/services/pipeline_orchestrator.py
```

with:

```text
backend/sessions/session_controller.py
backend/sessions/session_state.py
backend/sessions/session_manager.py
backend/sessions/cancellation.py
backend/sessions/outbound_queue.py
```

Use these states:

```text
IDLE
CONNECTING
LISTENING
USER_SPEAKING
PROCESSING
TOOL_PENDING
TOOL_RUNNING
SPEAKING
INTERRUPTING
ERROR
CLOSED
```

The session controller owns state transitions, current turn, response generation, active tasks, STT, LLM, TTS, outbound ordering, cancellation, and cleanup.

Interruption sequence:

1. Increment the generation ID.
2. Flush client playback.
3. Cancel graph execution.
4. Cancel TTS.
5. Stop obsolete audio output.
6. Reset the current STT turn.
7. Continue accepting new audio.
8. Ignore late events from the cancelled generation.

Completion criteria:

- Every state transition is deterministic.
- Cancelled responses cannot send stale audio.
- Disconnect cleanup is idempotent.
- Cancellation tests pass repeatedly.

## Step 5 — Audio capture, playback, and VAD

Create:

```text
frontend/audio-worklet.js
frontend/playback-queue.js
backend/audio/audio_format.py
backend/audio/turn_detector.py
```

Frontend changes:

- Replace `ScriptProcessorNode` with `AudioWorklet`.
- Request echo cancellation.
- Request noise suppression.
- Request automatic gain control where appropriate.
- Confirm the actual capture sample rate.
- Resample explicitly to 16 kHz when required.
- Use mono PCM.
- Add WebSocket backpressure.
- Maintain a bounded playback queue.
- Add immediate local playback flush.
- Reject stale response IDs.
- Add microphone and device diagnostics.

Backend changes:

- Preload Silero once.
- Keep VAD state per session.
- Add speech onset debounce.
- Add silence hangover.
- Add minimum interruption duration.
- Emit VAD events instead of only probabilities.
- Keep VAD and conversation state separate.

Completion criteria:

- Audio format is negotiated rather than assumed.
- Barge-in does not trigger from one noisy frame.
- Local playback stops immediately when interrupted.
- Audio does not feed back through the speaker route.
- VAD tests pass with prerecorded PCM samples.

## Step 6 — Provider abstraction with LangChain

Create:

```text
backend/providers/llm/base.py
backend/providers/llm/factory.py
backend/providers/llm/groq_provider.py
backend/providers/llm/gemini_provider.py
backend/providers/llm/anthropic_provider.py
backend/providers/llm/local_provider.py
```

Use LangChain chat-model interfaces so the agent graph does not depend directly on Groq, Gemini, Anthropic, or local-model response formats.

Normalize:

- Text streaming.
- Tool-call streaming.
- Structured output.
- Token usage.
- Provider errors.
- Timeouts.
- Cancellation.
- Retryable failures.

Provider examples:

```env
LLM_PROVIDER=groq
LLM_MODEL=qwen/qwen3.8-27b
```

```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6
```

```env
LLM_PROVIDER=local
LLM_MODEL=Qwen/Qwen3-14B
```

Completion criteria:

- At least two providers work through the same interface.
- Streaming text is normalized.
- Provider-specific exceptions become application errors.
- Switching models does not require changing the graph.

## Step 7 — Streaming STT and TTS

Refactor:

```text
backend/services/stt_service.py
backend/services/tts_service.py
```

into:

```text
backend/providers/stt/deepgram_provider.py
backend/providers/tts/elevenlabs_provider.py
backend/providers/tts/deepgram_provider.py
backend/providers/tts/tts_stream.py
```

STT improvements:

- Safe async queue ownership.
- Avoid unsafe cross-thread connection access.
- Reconnect and keepalive behavior.
- Per-turn reset.
- Surfaced callback failures.
- Provider timeouts.

TTS pipeline:

```text
LLM text deltas
→ sentence chunker
→ TTS queue
→ TTS provider stream
→ audio output queue
```

Add language-aware voices, persistent clients, explicit cancellation, fallback rules, audio metadata, and response/generation IDs.

Completion criteria:

- First audio can be produced before the final LLM token.
- TTS cancellation stops obsolete output.
- Provider fallback is observable.
- Sentence chunking does not produce unnatural fragments.

## Step 8 — LangGraph conversational agent without tools

Create:

```text
backend/agent/graph.py
backend/agent/state.py
backend/agent/nodes.py
backend/agent/routing.py
backend/agent/prompts.py
backend/agent/policies.py
```

Initial graph:

```text
START
  ↓
load_context
  ↓
call_model
  ↓
stream_response
  ↓
finalize_turn
  ↓
END
```

Graph state contains raw structured data:

- Conversation messages.
- Session ID.
- User ID.
- Turn ID.
- Generation ID.
- Retrieved context.
- Tool calls.
- Tool results.
- Approval state.
- Errors.
- Usage metadata.

The graph streams text events to the session controller, which sends them to TTS.

Completion criteria:

- Normal conversations work through LangGraph.
- Graph cancellation works.
- Text streaming works.
- Voice behavior is equal to or better than the original pipeline.
- No tools are added yet.

## Step 9 — Tool architecture workshop and implementation

Pause before implementing concrete tools and decide:

- Which tools are read-only.
- Which tools modify state.
- Which tools require confirmation.
- Which tools require OAuth.
- Which tools require audit records.
- Which tools are safe for automatic execution.
- Which tools need rate limits.
- Which tools are restricted to desktop or mobile.

Then create:

```text
backend/tools/registry.py
backend/tools/schemas.py
backend/tools/executor.py
backend/tools/approval.py
backend/tools/audit.py
backend/tools/policies.py
```

LangChain tools expose typed Pydantic schemas. LangGraph controls:

```text
model decision
→ argument validation
→ authorization
→ confirmation if required
→ execution
→ tool result
→ final spoken response
```

Sensitive tools use `interrupt()` for approval and resume only after explicit confirmation.

Completion criteria:

- Tool arguments are validated.
- Unknown tools cannot execute.
- Destructive tools require approval.
- Tool failures are safely returned to the model.
- State-changing tools are audited.
- The user has reviewed the initial tool list.

## Step 10 — Redis conversation memory

Create:

```text
backend/memory/redis_window.py
backend/memory/summarizer.py
backend/memory/memory_policy.py
```

Redis stores:

- Recent 10–15 conversation turns.
- Token-aware message windows.
- Current session state.
- Reconnect information.
- Active generation ID.
- Short-lived cancellation signals.

Long conversations are summarized instead of growing without limit.

Memory rules:

- Key by authenticated user and session.
- Never trust client-provided user IDs.
- Add TTL.
- Support reconnect recovery.
- Do not automatically save personal preferences.
- Provide forget, export, and delete operations.

Completion criteria:

- Conversation context survives WebSocket reconnect.
- Context size is bounded.
- Old context is summarized.
- User boundaries are enforced.

## Step 11 — RAG and ChromaDB

Create:

```text
backend/memory/rag/ingestion.py
backend/memory/rag/retriever.py
backend/memory/rag/query_rewriter.py
backend/memory/rag/citations.py
```

Pipeline:

```text
document upload
→ text extraction
→ normalization
→ chunking
→ embeddings
→ ChromaDB
→ metadata and ACL filters
→ retrieval
→ reranking
→ cited answer
```

Run query rewriting only for references such as “it,” “that,” or “the previous document.”

Every document includes:

- User ID.
- Tenant ID.
- Source ID.
- Document type.
- Upload timestamp.
- Access policy.

Completion criteria:

- Documents upload and index successfully.
- Search is isolated by user and tenant.
- Responses include citations.
- Retrieved content is treated as untrusted data.
- Retrieval quality and latency are measured.

## Step 12 — Frontend product experience

Refactor:

```text
frontend/app.js
frontend/index.html
```

into modules for WebSocket protocol, audio capture, playback, session state, transcripts, tool cards, confirmation dialogs, connection recovery, and telemetry display.

Add:

- Streaming assistant text.
- Live captions.
- Tool progress.
- Confirmation prompts.
- Device selection.
- Mute control.
- Privacy indicator.
- Reconnect/resume state.
- Error recovery.
- Accessibility announcements.
- Latency dashboard.

Completion criteria:

- UI clearly shows listening, processing, tool execution, speaking, and interrupted states.
- Tool confirmations are understandable.
- Playback flushes immediately on interruption.
- The user can recover from provider or network errors.

## Step 13 — Desktop and mobile clients

Begin only after the protocol is stable.

### Desktop

Build Electron or Tauri support with:

- System tray.
- Global shortcut.
- Floating assistant window.
- Native microphone permissions.
- Device switching.
- Session reconnect.
- Tool confirmation UI.

### Mobile

Build React Native or Flutter support with:

- Native audio bridge.
- Foreground audio behavior.
- Native echo cancellation.
- Audio focus handling.
- Permission management.
- Native dialer and contact integrations.
- Background-service limitations handled per platform.

Completion criteria:

- Desktop and mobile use the same protocol.
- Audio formats are negotiated.
- Barge-in behavior is consistent across clients.
- Permissions and privacy status are visible.

## Step 14 — Observability and telemetry

Create:

```text
backend/observability/tracing.py
backend/observability/metrics.py
backend/observability/events.py
backend/observability/cost_tracking.py
```

Track:

```text
capture_start
server_audio_received
vad_speech_start
vad_speech_end
stt_first_partial
stt_final
llm_first_token
tool_started
tool_completed
tts_started
tts_first_audio
server_audio_sent
client_playback_started
client_playback_flushed
```

Metrics:

- Time to first audio.
- p50, p95, and p99 turn latency.
- Local playback flush latency.
- Server cancellation latency.
- STT finalization latency.
- Tool success rate.
- Tool confirmation rate.
- Provider failure rate.
- Reconnect rate.
- Queue depth.
- Dropped audio frames.
- Cost per session.

Do not log raw API keys, JWTs, full audio, or unnecessary transcripts.

Completion criteria:

- Every turn has a trace ID.
- TTFA includes actual client playback start.
- Provider and tool failures are measurable.
- Logs are privacy-safe.

## Step 15 — Deployment and production hardening

Create:

```text
infra/Dockerfile
infra/docker-compose.yml
infra/nginx.conf
infra/migrations/
```

Local Compose services:

```text
voice-api
redis
postgres
chromadb
```

Production requirements:

- Non-root containers.
- Locked dependencies.
- TLS/WSS.
- Platform-managed secrets.
- Persistent volumes.
- Readiness checks.
- Provider circuit breakers.
- Rate limiting.
- Database migrations.
- Backup and restore procedures.
- Error alerting.

Completion criteria:

- The complete stack starts with one documented command.
- Services recover cleanly after restart.
- Secrets are not baked into images.
- Health checks detect unavailable dependencies.

## Step 16 — Testing and evaluation

Testing is added throughout the project and completed here as the final validation stage.

### Unit tests

- VAD hysteresis.
- State transitions.
- Protocol validation.
- Tool schemas.
- Memory limits.
- Query rewriting.
- Audio framing.

### Integration tests

- WebSocket audio flow.
- LangGraph execution.
- Tool approval.
- Redis reconnect.
- Chroma retrieval.
- Provider fallback.
- TTS cancellation.

### End-to-end tests

- Prerecorded PCM input.
- STT to final audio output.
- Barge-in during TTS.
- Network disconnect and recovery.
- Multiple concurrent sessions.

### Load tests

- Concurrent WebSocket clients.
- Long sessions.
- Provider timeouts.
- Tool latency.
- Redis failures.
- Audio backpressure.

Completion criteria:

- Automated tests run in CI.
- Latency benchmarks are repeatable.
- Provider failures have documented recovery behavior.
- Resume claims use measured metrics only.

## Tool implementation checkpoint

Concrete assistant tools should not be implemented until Step 8 is complete. At Step 9, we will separately decide the tool catalogue, permissions, confirmation behavior, integrations, and audit requirements before adding any real-world actions.

