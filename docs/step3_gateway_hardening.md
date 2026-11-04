# Step 3: WebSocket gateway hardening

The live `/api/v1/ws/audio` endpoint now applies the Step 2 contract at the connection boundary.

- Validates the browser `Origin` against `ALLOWED_ORIGINS`; non-browser clients without an Origin header remain supported.
- Sends a versioned `ready` event and periodic `pong` heartbeats.
- Parses client JSON events and rejects malformed, unknown, wrong-direction, or unsupported-version messages.
- Enforces maximum control-message and binary-audio sizes, PCM sample-width alignment, and audio metadata length matching.
- Handles `ping`, `hello`, `audio_format`, `audio_frame`, `cancel`, and `flush` events.
- Uses close codes for policy violations, unsupported data, and oversized frames, with structured protocol errors before closing.
- Configures FastAPI CORS from `settings.ALLOWED_ORIGINS` instead of a wildcard.

The existing orchestrator remains responsible for VAD/STT/LLM/TTS processing. Tool execution, persistent sessions, authentication, and barge-in teardown remain later steps.
