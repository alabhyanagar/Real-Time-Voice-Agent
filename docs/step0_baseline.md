# Step 0 Baseline and Safety Snapshot

Date: 2026-11-04

## Scope

This snapshot establishes a provider-free baseline before LangChain, LangGraph, tools, durable memory, RAG, authentication, or audio-pipeline refactoring is introduced.

## Current runtime

- Python: 3.10.0
- FastAPI: 0.159.1
- Starlette: 1.7.0
- HTTPX: 0.28.1
- Pydantic: 2.14.1

## Current request flow

```text
Browser microphone
  -> FastAPI WebSocket (/api/v1/ws/audio)
  -> Silero VAD
  -> Deepgram STT
  -> Groq/Qwen LLM
  -> ElevenLabs or Deepgram TTS
  -> Browser PCM playback
```

## Baseline artifacts added

- `.env.example` with placeholders only; no credentials were copied.
- `README.md` with current startup and test instructions.
- `tests/test_health.py` for the health contract.
- `tests/test_websocket_contract.py` for provider-free WebSocket transport behavior.
- `tests/test_configuration.py` for the currently declared settings.

## Verification

Command:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: 4 tests passed.

The WebSocket test uses a fake orchestrator. It does not load Silero, contact Deepgram, call Groq, or call ElevenLabs.

## Safety findings

- The project directory is not currently a Git worktree, so a Git diff or rollback is not available from this checkout.
- `.env` and `backend/.env` remain untouched.
- Runtime behavior was not changed by Step 0.
- The existing provider integration still requires real credentials and external network access for an end-to-end voice test.
- The existing `fastapi.testclient`/HTTPX combination emits a Starlette deprecation warning, so baseline tests use provider-free direct endpoint tests instead of the hanging test client.

## Next gate

Step 1 should consolidate dependency/configuration management and add typed settings for provider selection, storage, authentication, audio limits, and telemetry. No tool definitions should be added until the LangGraph agent foundation is complete.
