# Step 4: Protocol-aligned pipeline and client

The pipeline and browser client now use the versioned server and client events defined in Step 2.

## Backend

- `PipelineOrchestrator` emits validated `state`, `transcript`, `audio_start`, `audio_end`, `response_text_delta`, `audio_flush`, and `error` events.
- Every orchestrator event carries the negotiated session ID, turn ID, response ID when applicable, and a connection sequence number.
- LLM tokens are forwarded as response deltas while TTS audio continues over binary WebSocket frames.
- Barge-in emits `audio_flush`, cancels the active generation task, and returns the state to `listening`.

## Browser client

- Waits for `ready`, then sends `hello` and the negotiated `audio_format` event.
- Sends `audio_frame` metadata before each binary PCM frame.
- Handles lowercase protocol states, streamed response deltas, audio lifecycle, flush, and structured errors.
- Maintains a smooth queued PCM playback path and clears queued audio on interruption.

The protocol boundary now has one event shape end to end. Tool execution, persistent memory, and provider abstraction remain later milestones.
