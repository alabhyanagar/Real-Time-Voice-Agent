# Step 14 — Observability and Telemetry

Step 14 adds the full observability stack to the voice pipeline. Every turn
now carries a unique trace ID, records precise stage timestamps, and
contributes to aggregated runtime metrics and cost estimates.

---

## Package layout

```
backend/observability/
├── __init__.py          # Public re-exports
├── events.py            # TurnEventBus + TurnEvent + TurnEventType
├── tracing.py           # TurnTracer + session-keyed registry
├── metrics.py           # MetricsCollector (latency histograms, counters)
└── cost_tracking.py     # CostTracker (per-session and global cost estimates)

backend/routers/
└── metrics_router.py    # GET /api/v1/metrics, /metrics/costs, /metrics/session/{id}/cost
```

---

## Events (`events.py`)

`TurnEventBus` is an in-process async publish/subscribe bus. Pipeline stages
call `bus.publish(TurnEvent(...))` without blocking. Each subscriber runs in
its own isolated `asyncio.Queue` consumer task so a slow subscriber cannot
cause backpressure on the pipeline.

### Tracked event types

| Event | Trigger |
|---|---|
| `capture_start` | First PCM frame written from client |
| `server_audio_received` | First validated WebSocket audio frame |
| `vad_speech_start` | VAD detects onset of speech |
| `vad_speech_end` | VAD detects end of utterance |
| `stt_first_partial` | First STT partial transcript returned |
| `stt_final` | STT final transcript confirmed |
| `llm_first_token` | First token streamed from LLM |
| `tool_started` | Tool executor begins a call |
| `tool_completed` | Tool executor finishes a call |
| `tts_started` | TTS synthesis starts for a sentence |
| `tts_first_audio` | First TTS audio chunk queued for send |
| `server_audio_sent` | First audio binary frame sent over WebSocket |
| `client_playback_started` | Client telemetry: playback_started |
| `client_playback_flushed` | Client telemetry: playback_flushed |
| `turn_cancelled` | Turn cancelled (barge-in or user cancel) |
| `turn_completed` | Turn completed successfully |
| `turn_error` | Turn ended with error |

---

## Tracing (`tracing.py`)

`TurnTracer` is instantiated once per turn by `PipelineOrchestrator`. It:

- Assigns a unique `trace_id` (UUID4) per turn.
- Records the first monotonic timestamp for each stage (later calls to `mark()`
  for the same stage are silently ignored — idempotent).
- Publishes every mark to `TurnEventBus` for downstream subscribers.
- Exposes latency helpers:

| Method | Measures |
|---|---|
| `ttfa_ms()` | VAD speech end → server audio sent |
| `stt_latency_ms()` | VAD speech end → STT final |
| `llm_latency_ms()` | STT final → LLM first token |
| `tts_latency_ms()` | LLM first token → TTS first audio |
| `total_turn_latency_ms()` | Server audio received → server audio sent |

A module-level `register_tracer / get_tracer / unregister_tracer` registry
(keyed by `session_id`) lets any pipeline layer fetch the active tracer
without threading it through every function signature.

---

## Metrics (`metrics.py`)

`MetricsCollector` subscribes to `TurnEventBus` on `start()`. It maintains:

- **Latency histograms** (sliding window, last 1 000 samples):
  - TTFA, STT, LLM first-token, TTS first-audio, total turn, cancel latency.
  - Exposes p50 / p95 / p99 / mean per histogram.
- **Provider counters** per provider name: success / failure / timeout.
- **Tool counters** per tool name: success / failure / confirmed / rejected.
- **Session counters**: total / active / reconnect.
- **Audio counters**: frames received / dropped.
- **Turn counters**: completed / cancelled / error.

Call `get_metrics().snapshot()` to get a full JSON-serialisable snapshot for
dashboards or alerting.

---

## Cost tracking (`cost_tracking.py`)

`CostTracker` accumulates estimated USD costs per session:

- **LLM**: prompt + completion tokens × configurable per-1 000-token rate.
- **STT**: audio seconds × configurable per-second rate.
- **TTS**: characters × configurable per-1 000-character rate.

Pricing defaults reflect approximate public list prices (late 2026). Override
at startup with `set_llm_pricing / set_stt_pricing / set_tts_pricing`.

> [!NOTE]
> Cost figures are **estimates only** and are not billing-accurate. They are
> intended for budget awareness and anomaly detection, not invoicing.

---

## REST endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/metrics` | Full pipeline metrics snapshot |
| `GET` | `/api/v1/metrics/costs` | Global cumulative cost and usage totals |
| `GET` | `/api/v1/metrics/session/{session_id}/cost` | Per-session cost summary |

---

## Privacy constraints

- No raw API keys, JWTs, audio blobs, or unredacted transcript text are
  stored or logged anywhere in the observability stack.
- `TurnEvent.metadata` accepts only caller-supplied dicts; pipeline call
  sites must sanitise values before passing them.
- Latency and counter data contain no personally identifiable information.

---

## Completion criteria (all met)

- [x] Every turn has a unique `trace_id`.
- [x] TTFA is computed from monotonic timestamps (VAD end → first audio sent).
- [x] Provider and tool failures are individually countable.
- [x] p50 / p95 / p99 latency histograms are available from `/api/v1/metrics`.
- [x] Per-session cost estimates are available from the REST API.
- [x] Logs are privacy-safe (no keys, JWTs, raw audio, or full transcripts).
- [x] `MetricsCollector.start()` is wired into the FastAPI lifespan.
- [x] 20 unit tests pass covering event bus, tracer, histograms, counters, and cost tracker.

---

## Next step

**Step 15 — Deployment and production hardening**:
Docker + Compose stack (`voice-api`, `redis`, `postgres`, `chromadb`),
Nginx TLS termination, database migrations, non-root containers, locked
dependencies, and health-check-aware restart policies.

