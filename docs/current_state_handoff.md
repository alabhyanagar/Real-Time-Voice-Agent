# Voice Agent Continuation Handoff

This file is the durable context for continuing implementation if the model or
conversation quota changes. Read it before making the next code change.

## Project

- Repository: `D:/Alabhya/Real-Time-Voice-Agent`
- Product: FastAPI/WebSocket voice assistant with LangChain/LangGraph, Deepgram
  STT, ElevenLabs/Deepgram TTS, browser AudioWorklet capture, and PCM playback.
- Primary plan: `voice_agent_implementation_plan.md`
- Canonical tool roadmap: `docs/agreed_implementation_phases.md`

## Latest state

- Step 8 is complete: the active runtime uses the compiled, tool-free LangGraph
  conversational agent.
- Phase 1 of Step 9 is complete: the shared tool foundation is implemented in
  `backend/tools/`.
- The current concrete tools are `calculate`, `get_current_time`, the three
  bounded workspace read tools, `workspace_preview_patch`, and four
  confirmation-gated workspace mutation tools, plus `web_search` and
  `web_fetch`, Google Workspace, Microsoft Graph, ESP32, and MERN tools. All
  state-changing tools are confirmation-gated.
- Phase 2 is complete: the starter tools are integrated into an opt-in model
  tool-call graph through the Phase 1 executor.
- Phase 3 is complete: workspace list/search/read plus Git status/diff are
  bounded, read-only tools with explicit roots and traversal protection.
- Phase 4 is complete: workspace create/patch/rename/Git commit/delete tools
  support previews, confirmation, audit, and reversible behavior.
- Phase 5 is complete: web search/fetch/summarize/fact extraction are bounded,
  source-aware, and SSRF-safe.
- Phase 6 is complete: Google Calendar read/free-busy/draft/create/update/cancel
  tools are registered with OAuth scopes and confirmation policies.
- Phase 7 is complete: Gmail search/read/summarize/draft/send and Drive
  search/read/create/update/delete tools are registered with OAuth scopes.
- Phase 8 is complete: Microsoft Graph mail/calendar/files adapters are
  registered behind the same policy interfaces and use delegated, encrypted
  per-user Microsoft OAuth tokens.
- Phase 9 is complete: ESP32 sensor/status/command and MERN CRUD adapters are
  registered with physical/state-changing confirmation policies and JWT scope
  authorization.
- Steps 0â€“9 hardening is complete: tool approvals pause/resume through native
  LangGraph interrupts, rejected approvals are audited, and user scopes reach
  the session-bound tool context. `LLMService.stream_response` accepts the
  supplied scope context, so tool-enabled turns no longer fail at the boundary.
- Phase 10 is complete for outbound SMS and call lifecycle. The next work is a
  separate advanced communications phase for inbound calls, consented
  recording/transcription, and proactive workflows.
- The virtual environment has been repaired using Python 3.15.2. Runtime
  verification is active again; ChromaDB remains excluded because its
  `onnxruntime` dependency has no compatible Python 3.15 wheel.

## Completed plan work

- Steps 0–7 are implemented and audited in `docs/steps_0_7_completion_audit.md`.
- Step 0: baseline health/WebSocket/configuration tests, README, `.env.example`,
  and dependency snapshot.
- Step 1: typed settings, provider selection, production secret validation,
  audio/WebSocket/tool/telemetry controls.
- Step 2: versioned Pydantic WebSocket protocol, binary PCM validation, sequence,
  timestamp, turn, response, and generation metadata.
- Step 3: FastAPI lifespan, JWT admission, origin checks, heartbeat, connection
  and message limits, `/livez`, `/readyz`, and optional Redis/PostgreSQL/Chroma
  startup checks.
- Step 4: session state machine, generation cancellation, session manager, and
  serialized outbound queue. Barge-in cancels graph work, TTS, and STT turn state.
- Step 5: AudioWorklet capture, AEC/noise suppression/AGC requests, 16 kHz mono
  PCM conversion, bounded playback, cached Silero VAD, and debounced turn events.
- Step 6: provider boundary for Groq, Gemini, Anthropic, and local models through
  LangChain, plus STT/TTS adapter packages.
- Step 7: asyncio-safe STT callbacks, reset support, sentence-level TTS streaming,
  provider fallback, and cancellation.

## Current important files

- Gateway: `backend/routers/websocket_router.py`
- Runtime lifecycle: `backend/core/lifecycle.py`
- Settings: `backend/core/config.py`
- Protocol: `backend/protocol/`
- Sessions: `backend/sessions/`
- Current service boundary: `backend/services/llm_service.py`
- Tool graph and executor: `backend/llm/graph.py`, `backend/tools/`
- Browser client: `frontend/app.js`, `frontend/audio-worklet.js`,
  `frontend/playback-queue.js`
- Phase 5 design: `docs/phase5_workspace_mutations.md`
- Phase 6 design: `docs/phase6_web_tools.md`
- Phase 7 design: `docs/phase7_google_workspace_read.md`
- Phase 8 design: `docs/phase8_google_oauth_writes.md`
- Phase 9 design: `docs/phase9_oauth_gateway_scope_context.md`
- Strategy reconciliation: `docs/strategy_alignment_audit.md`
- Canonical roadmap: `docs/agreed_implementation_phases.md`
- Steps 0–9 hardening: `docs/steps0_9_hardening.md`

## Verification baseline

- Python virtual environment: `D:/Alabhya/Real-Time-Voice-Agent/venv`
- `python -m pytest -q`: 13 tests passed at the end of Step 7.
- `python -m pip check`: no broken requirements.
- Compile check: `python -m compileall -q backend` passed.
- The shell may inject a `DEBUG` environment variable. For import checks use
  `$env:DEBUG='True'`; for configuration tests remove it with
  `Remove-Item Env:DEBUG -ErrorAction SilentlyContinue`.

## Phase 5 checkpoint

- Registry now exposes a read-only patch preview plus four workspace mutation
  operations. Mutation
  definitions carry medium/high risk metadata and require executor confirmation.
- Workspace writes enforce configured byte limits, UTF-8 text, root containment,
  symlink rejection, and atomic replacement. Delete is a reversible move into
  `.voice_agent_trash`.
- Configuration adds `WORKSPACE_MAX_WRITE_BYTES` and `WORKSPACE_TRASH_DIR`.

## Completed checkpoint: Step 8

Implement the tool-free LangGraph conversational agent from the plan:

```text
START → load_context → call_model → stream_response → finalize_turn → END
```

Create:

- `backend/agent/graph.py`
- `backend/agent/state.py`
- `backend/agent/nodes.py`
- `backend/agent/routing.py`
- `backend/agent/prompts.py`
- `backend/agent/policies.py`

The state must retain raw structured conversation messages, session/user/turn/
generation IDs, retrieved context, tool-call/result placeholders, approval state,
errors, and usage metadata. Step 8 must not bind or execute tools; concrete tool
work belongs to Step 9 after this checkpoint.

## Continuation rules

1. Read this file and the Step 8 section in `voice_agent_implementation_plan.md`.
2. Inspect the existing provider and session interfaces before editing.
3. Keep the graph provider-neutral and cancellation-aware.
4. Preserve protocol generation IDs so late output cannot reach the client.
5. Every code, configuration, documentation, or product change must update this
   handoff file before the work is reported complete.
6. Add the changed files, behavior, verification result, and next starting point
   to the latest dated change-log entry.
7. Keep this file's Latest state section synchronized with the change log.
8. Do not begin the next tool phase until the current phase is documented and
   verified.

## Change log

### 2026-11-04

- Created this handoff record before beginning Step 8.
- Confirmed Steps 0–7 implementation and verification baseline above.
- Implemented the tool-free `backend/agent/` LangGraph package with structured
  state, context loading, provider streaming, finalization, policies, routing,
  and cancellation handling.
- Switched `backend/services/llm_service.py` to the new Step 8 graph. Existing
  tool modules remain reserved for the Step 9 checkpoint.
- Added `docs/step8_langgraph_agent.md` and provider-free Step 8 graph tests.
- Added `docs/tool_catalog.md`, which records the implemented starter tools and
  the planned workspace, web, productivity, communication, and IoT tools.
- Implemented Phase 1 tool infrastructure: schemas, policy decisions, approval
  storage, redacted audit records, bounded executor, idempotency, and tests.
- Implemented Phase 2 starter-tool integration with the `TOOLS_ENABLED` feature
  flag, model-selected tool calls, executor status events, and audit completion.
- Added `docs/phase2_starter_tools.md` and provider-free integration coverage.
- The legacy tool graph now delegates registered tool execution to
  `backend/tools/executor.py`; the Step 8 graph remains deliberately tool-free.
- Phase 1 verification: `python -m pytest -q` reports 20 passing tests and
  `python -m compileall -q backend` passes.
- Phase 2 verification: `python -m pytest -q` reports 21 passing tests and
  `python -m compileall -q backend` passes.
- Implemented Phase 3 `workspace_list_files` with explicit configured roots,
  relative-path output, hidden-file filtering, symlink escape protection, and
  bounded results.
- Added `docs/phase3_workspace_list_files.md` and workspace security tests.
- Phase 3 verification: `python -m pytest -q` reports 24 passing tests and
  `python -m compileall -q backend` passes.
- Implemented Phase 4 `workspace_search` and `workspace_read_file` with bounded
  text search, extension filtering, binary/size checks, numbered excerpts, and
  relative-path-only results.
- Added `docs/phase4_workspace_search_read.md` and workspace search/read tests.
- Phase 4 verification: `python -m pytest -q` reports 27 passing tests and
  `python -m compileall -q backend` passes.
- Next implementation point is Phase 5: workspace mutation with diff previews
  and confirmation.
- Verified compiled graph streaming and cancellation-aware execution.
- Final Step 8 verification: `python -m pytest -q` reports 15 passing tests;
  `python -m compileall -q backend` passes.
- Clarified the Latest state section and made handoff updates mandatory for
  every future code, configuration, documentation, or product change.
- Implemented Phase 5 workspace mutations in `backend/tools/workspace_tools.py`:
  preview/apply patch, create, rename, and reversible trash-backed delete.
- Added confirmation/risk metadata for all mutation tools in
  `backend/tools/registry.py`, plus write-size and trash-directory settings in
  `backend/core/config.py` and `.env.example`.
- Added `docs/phase5_workspace_mutations.md`, `tests/test_workspace_mutations.py`,
  and updated `docs/tool_catalog.md` with the Phase 5 boundary.
- Phase 5 static verification: backend and test AST parsing passed. Runtime
  pytest verification is recorded below. Next point: Phase 6 web search/fetch.
- Repaired `venv` by preserving the broken environment as `venv_broken_20261104`
  and recreating it with the available Python 3.15.2 interpreter. Installed the
  compatible dependency set in `backend/requirements-python315.txt`; ChromaDB
  is intentionally deferred until a Python version with an `onnxruntime` wheel
  is available.
- Environment verification: `venv\\Scripts\\python.exe -m pytest -q` reports
  33 passing tests and `pip check` reports no broken requirements. Compileall
  cannot write into the repository's protected `__pycache__` directories, while
  AST parsing remains clean.
- Implemented Phase 6 in `backend/tools/web_tools.py` with provider-neutral
  `web_search`, SSRF-safe `web_fetch`, response limits, source timestamps, and
  HTML text extraction. Registered both tools with read-only rate limits.
- Added `backend/requirements-python315.txt` as the Python 3.15-compatible
  dependency manifest and `tests/test_web_tools.py`; verification now reports
  33 passing tests and no broken pip requirements. ChromaDB remains deferred
  because `onnxruntime` has no Python 3.15 wheel.
- Next point: Phase 7 Google Workspace OAuth read-only connectors.
- Implemented Phase 7 in `backend/tools/google_tools.py`: Gmail search/read,
  Calendar event listing, and Calendar free/busy. Added Google API settings,
  scope metadata in the registry, and mocked connector tests.
- Phase 7 verification: `pytest` reports 36 passing tests and `pip check`
  reports no broken requirements. Next point: OAuth lifecycle and confirmed
  Google write operations.
- Implemented Phase 8 with `backend/integrations/google_oauth.py` and expanded
  `backend/tools/google_tools.py` for Gmail draft/send and Calendar
  create/update/cancel. Added PKCE state binding, Fernet token encryption,
  refresh support, write scopes, confirmation metadata, and mocked tests.
- Phase 8 verification: `pytest` reports 39 passing tests, AST parsing passes,
  and `pip check` reports no broken requirements. Next point: authenticated
  OAuth callback routes and durable per-user token storage.
- Implemented Phase 9 with `/api/v1/oauth/google/start`, `/callback`, and
  `/revoke`, user-bound PKCE state, encrypted `SQLiteTokenStore`, token
  revocation, Google scope injection into the tool graph context, and a
  context-local connector identity that resolves the user's stored access token
  without exposing it to model messages or audit arguments.
- Phase 9 verification: `pytest` reports 39 passing tests, AST parsing passes,
  and `pip check` reports no broken requirements. Next point: shared durable
  token infrastructure and refresh-on-expiry connector injection.
- Reconciled the implementation against the agreed Phases 1–9 strategy in
  `docs/strategy_alignment_audit.md`. Added missing workspace Git tools, web
  summarization/fact extraction, Calendar drafts, Gmail summarization, Drive
  tools, Microsoft Graph adapters, ESP32 integrations, and MERN CRUD tools.
- Added `tests/test_remaining_strategy_tools.py`; full verification now reports
  42 passing tests, AST parsing passes, and `pip check` reports no broken
  requirements. The project is aligned through Phase 9; Phase 10 is next.
- Implemented Phase 10 outbound SMS and phone tools in
  `backend/tools/telephony_tools.py`: SMS/call drafts, send/place, status,
  hangup, and recording/transcript availability. Added Twilio configuration,
  confirmation/rate/idempotency metadata, tests, and
  `docs/phase10_sms_phone.md`. Inbound answering, recording consent, and
  proactive calling remain deferred.
- Phase 10 verification: `pytest` reports 44 passing tests, AST parsing passes,
  and `pip check` reports no broken requirements.
- Added `docs/agreed_implementation_phases.md` as the canonical Phase 1–10
  roadmap to prevent future phase-numbering drift.
- Closed the remaining Steps 0–9 hardening gaps: workspace secret/extension
  protections, mutation idempotency propagation, Git rollback, enforced tool
  rate limits, and client confirmation accept/reject protocol routing. Added
  `docs/steps0_9_hardening.md` and regression coverage.
- Hardening verification: `pytest` reports 48 passing tests; `pip check` and
  AST parsing pass. Step 10 Redis conversation memory is now ready to begin.
- Completed the final pre-Step-10 hardening: native LangGraph approval
  interrupts/resume, non-executing audited rejection, user JWT scope propagation,
  Microsoft delegated OAuth routes with encrypted per-user persistence and
  refresh, plus ESP32/MERN scope requirements. Fixed the `granted_scopes`
  argument mismatch between the pipeline and `LLMService.stream_response`, and
  corrected the Google OAuth redirect default to the mounted `/api/v1` route.
- Added `tests/test_microsoft_oauth.py` and expanded executor/graph tests.
  Full verification: `python -m pytest -q` reports 53 passing tests; `pip check`
  reports no broken requirements. The pytest cache warning is harmless and is
  caused by an existing path conflict in `.pytest_cache`.
- Next starting point: Step 10, Redis conversation memory. Keep the current
  in-memory LangGraph checkpointer only as a pre-Step-10 approval checkpoint;
  move it to the durable Step 10/12 persistence design before production use.
- Implemented Step 10 Redis conversation memory in `backend/memory/`: bounded
  15-message/4,000-token windows, summarization on eviction, TTLs, hashed
  user/session keys, reconnect recovery, session state, generation cancellation
  signals, export, forget, and delete controls. Integrated recovery and writes
  into `PipelineOrchestrator`; authenticated JWT identity remains authoritative.
  `MEMORY_REDIS_REQUIRED=true` enables an independent Redis startup check,
  without requiring ChromaDB/PostgreSQL during this step.
  Updated `frontend/app.js` to persist the server-issued reconnect handle and
  send it on the next WebSocket connection.
- Added `backend/routers/memory_router.py`, `/api/v1/memory` export/delete
  controls, reconnect session handles, memory settings in `config.py` and
  `.env.example`, and `docs/step10_redis_memory.md`.
- Added `tests/test_memory.py`. Full Step 10 verification: `pytest` reports 56
  passing tests, `pip check` is clean, and backend AST parsing passes.
- Step 11 is now the next starting point: ChromaDB RAG ingestion, retrieval,
  query rewriting, and citations.
- Implemented Step 11 in `backend/memory/rag/`: safe text/HTML/JSON/Markdown
  ingestion, optional PDF extraction, normalization, overlapping chunks,
  ChromaDB persistence with a Python 3.15-compatible JSON fallback, metadata,
  user/tenant ACL filtering, private versus tenant access policies, bounded
  reranked retrieval, reference-aware query rewriting, citations, and
  untrusted-context prompt boundaries.
- Added authenticated `/api/v1/rag/documents` upload/delete and `/api/v1/rag/query`
  routes. Integrated retrieval into the voice pipeline with citations UI cards,
  `rag_retrieval_ms` telemetry, and LangGraph context injection. Added RAG
  settings to `config.py` and `.env.example`, plus `docs/step11_rag.md`.
- Added `tests/test_rag.py`. Full Step 11 verification: `pytest` reports 59
  passing tests, `pip check` is clean, backend AST parsing and frontend syntax
  checks pass. The next starting point is Step 12, frontend product experience.
- Implemented Step 12 frontend product experience with `frontend/protocol.js`,
  `session-state.js`, `audio-client.js`, `telemetry.js`, and modular
  `app_modular.js`. Added live captions, streaming responses, tool progress and
  confirmation UI, citations, device selection, mute/AEC privacy controls,
  reconnect backoff, generation filtering, accessibility announcements,
  immediate playback flush, error recovery, and latency telemetry. Updated
  `frontend/index.html` and routed `/app.js` to the modular implementation.
- Added `docs/step12_frontend_product_experience.md`. Verification: all browser
  modules pass `node --check`; the full backend suite remains green with 59
  passing tests, `pip check` is clean, and backend AST parsing passes. Step 13
  (desktop and mobile clients) is now the next starting point.
- Updated `voice_agent_implementation_plan.md` Step 13: desktop is now Electron
  with React/TypeScript, Android is native Kotlin with Jetpack Compose,
  Coroutines/StateFlow, OkHttp WebSocket, AudioRecord/AudioTrack, AEC, audio
  focus, foreground-service, permission, reconnect, and shared protocol
  requirements. iOS, React Native, Flutter, and Tauri are outside the current
  implementation scope.
- Started Step 13 with `desktop/` Electron scaffolding (tray, global shortcut,
  secure preload, microphone permission handling, floating window, and builder
  targets) and `android/` Kotlin/Jetpack Compose scaffolding (OkHttp protocol,
  reconnect state, AudioRecord/AudioTrack, AEC/noise suppression, foreground
  microphone service, permissions, Compose state, tool confirmation, telemetry,
  and citations). Added `docs/step13_clients.md` and build-output ignore rules.
- JavaScript syntax validation passes. Android compilation is pending an
  Android Studio/Gradle environment because Gradle is not installed in the
  current workspace. The next task is to generate the Gradle wrapper and run a
  real emulator/device build, then harden protocol/audio tests.
