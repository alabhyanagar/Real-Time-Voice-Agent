# Real-Time Voice Agent

This repository contains the baseline cascade voice assistant:

```text
Browser microphone
  -> FastAPI WebSocket
  -> Silero VAD
  -> Deepgram STT
  -> Groq/Qwen LLM
  -> ElevenLabs or Deepgram TTS
  -> Browser PCM playback
```

## Local setup

1. Create or activate a Python 3.10+ virtual environment.
2. Install backend dependencies:

   ```powershell
   python -m pip install -r backend/requirements.txt
   ```

3. Copy `.env.example` to `.env` and add provider credentials.
4. Start the API from the repository root:

   ```powershell
   uvicorn backend.main:app --reload
   ```

5. Open `http://localhost:8000/` in a browser.

## Configuration

Configuration is loaded from process environment variables and, for local development, from `.env` in the project root or `backend/.env`. Use `.env.example` as the template. The provider-neutral settings are:

- `LLM_PROVIDER`: `groq`, `gemini`, `anthropic`, or `local`.
- `LLM_MODEL`: model identifier for the selected provider.
- `LLM_BASE_URL`: optional base URL for local/OpenAI-compatible servers.
- `ENVIRONMENT`: `development`, `test`, `staging`, or `production`.

Redis, PostgreSQL, ChromaDB, JWT, tool, VAD and telemetry settings are validated centrally. Redis/PostgreSQL/Chroma startup is enabled with `REQUIRE_EXTERNAL_SERVICES=true`.

## Baseline tests

Run the provider-free transport, configuration, session and audio tests with:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
# or: python -m pytest -q
```

The WebSocket test uses a fake orchestrator. It verifies transport behavior without loading Silero or contacting external providers.

## Implementation status

Steps 0–7 of the implementation plan are complete: validated configuration, authenticated/versioned WebSockets, session cancellation, AudioWorklet capture, debounced VAD, bounded playback, LangChain provider abstraction, streaming STT/TTS, and policy-aware tool plumbing. See [`docs/steps_0_7_completion_audit.md`](docs/steps_0_7_completion_audit.md) for the cross-validation.

The next plan boundary is durable conversation memory (Step 8), followed by the expanded tool workshop, Redis short-term memory, Chroma RAG, and production deployment phases.
