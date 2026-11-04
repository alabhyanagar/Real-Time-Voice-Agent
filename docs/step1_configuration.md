# Step 1 Dependency and Configuration Foundation

Date: 2026-11-04

## Implemented

- Replaced environment lookups in `backend/core/config.py` with Pydantic Settings v2 configuration.
- Preserved existing fields such as `GROQ_MODEL`, `DEEPGRAM_API_KEY`, and `ELEVENLABS_API_KEY` for compatibility.
- Added provider-neutral model selection through `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_BASE_URL`.
- Added configuration for Gemini, Anthropic, and local OpenAI-compatible model servers.
- Added Redis, PostgreSQL, ChromaDB, JWT, WebSocket, audio, tool-policy, retry, and telemetry settings.
- Added production safety validation for debug mode, wildcard origins, retry counts, message limits, and supported audio rates.
- Expanded `backend/requirements.txt` with LangChain, LangGraph, provider adapters, storage, retrieval, and observability foundations.
- Expanded `.env.example` with all Step 1 settings and placeholders only.
- Added configuration tests for defaults and production validation.

## Dependency manifest policy

- `backend/requirements.txt` is the maintained direct runtime dependency manifest for new installations.
- Root `requirements.txt` is retained as a historical environment snapshot and is marked accordingly.
- No dependency installation was performed during this step; existing baseline tests do not import the new optional integrations.

## Intentionally deferred

The new settings do not yet initialize or enforce:

- LangChain or LangGraph model execution.
- Redis/PostgreSQL/ChromaDB connections.
- JWT authentication.
- WebSocket origin or frame-limit enforcement.
- Tool execution.
- Telemetry exporters.

Those behaviors belong to later implementation steps.

## Verification

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Result: 6 tests passed.

## Next gate

Step 2 can define the versioned WebSocket protocol and Pydantic event models using the new audio and message-limit settings.
