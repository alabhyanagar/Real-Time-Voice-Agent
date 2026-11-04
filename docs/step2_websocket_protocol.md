# Step 2: Versioned WebSocket protocol

Implemented a provider-neutral contract for browser, desktop, mobile, and the FastAPI gateway.

- JSON events use `protocol_version: "1.0"`, session/turn IDs, sequence, and optional response/timestamp metadata.
- Client events cover hello/resume, audio format and binary-frame metadata, cancellation/flush, ping, and client metrics.
- Server events cover readiness, state, transcripts, streamed response text, audio lifecycle/flush, tool status/confirmation placeholders, UI cards, errors, and telemetry.
- Binary PCM remains binary; `AudioFrameMetadata` describes its length/index without base64 overhead.
- Models forbid unknown fields and parsing rejects unsupported major versions, unknown types, and wrong direction.

The live router remains legacy-compatible until Step 3 wires validation, heartbeat, origin checks, and close-code behavior into connections.

## Verification

The new protocol modules pass Python syntax compilation. The normal unittest command could not run in this checkout because `venv\\Scripts\\python.exe` references a Python 3.10 installation that is no longer present; the system interpreter also does not have the project's FastAPI/Pydantic dependencies installed. Restore/recreate the virtual environment before running the full suite.
