# Step 12 — Frontend product experience

Step 12 replaces the single browser event loop with a modular, recoverable
voice-assistant interface.

## Modules

- `frontend/protocol.js` owns versioned event envelopes, sequence numbers,
  generation filtering, and stale-event rejection.
- `frontend/session-state.js` owns authenticated-session reconnect handles and
  UI connection state. It never stores or accepts a user ID.
- `frontend/audio-client.js` owns microphone permissions, requested browser AEC,
  noise suppression, AGC, AudioWorklet capture, PCM framing, mute state, device
  selection, playback, and immediate flush.
- `frontend/telemetry.js` renders live latency measurements.
- `frontend/app_modular.js` coordinates UI state, WebSocket transport, captions,
  tools, confirmations, citations, reconnects, and accessibility announcements.

`frontend/index.html` now exposes:

- Listening, processing, speaking, cancelling, interrupted, and error states.
- Streaming user captions and assistant text.
- Tool status and citation cards.
- Confirmation prompts for mutating tools.
- Microphone device selection and mute control.
- A microphone privacy indicator.
- Reconnect/error banners and a latency telemetry panel.
- An assertive live region for screen-reader state announcements.

## Recovery behavior

The server-issued session ID is stored as a reconnect handle. Network closure
preserves that handle, stops the local microphone safely, and retries with
bounded exponential backoff. The next connection resumes the authenticated
user's Step 10 memory window. Intentional disconnects do not retry.

Generation IDs reject stale server events. `audio_flush` immediately stops all
queued PCM sources, preventing interrupted speech from continuing to play.

## Validation

The browser modules pass `node --check`. The backend protocol, WebSocket, audio,
memory, tools, OAuth, and RAG regression suite remains green after the UI
change.
