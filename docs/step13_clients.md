# Step 13 — Electron desktop and Kotlin Android clients

Step 13 starts the native-client layer without changing the FastAPI protocol.

## Electron desktop foundation

`desktop/` contains a secure Electron shell that loads the existing modular web
client from the backend. It provides:

- Tray icon and show/hide behavior.
- `Ctrl+Space`/`Cmd+Space` assistant toggle.
- Floating assistant window.
- Context isolation, sandboxing, and disabled Node integration.
- Microphone permission handling.
- `VOICE_AGENT_URL` configuration.
- Electron Builder targets for Windows, macOS, and Linux.

The existing web client remains the renderer until the planned React/TypeScript
desktop UI migration is completed.

## Android Kotlin foundation

`android/` is a native Kotlin/Jetpack Compose application with:

- Kotlin serialization protocol models.
- OkHttp WebSocket transport.
- Server-issued reconnect session persistence.
- `AudioRecord` 16 kHz mono PCM16 capture.
- `AudioTrack` PCM playback and immediate flush.
- Android Acoustic Echo Canceler and Noise Suppressor where available.
- Audio foreground service with microphone service type.
- Runtime microphone and notification permissions.
- Compose state, captions, tool progress, confirmation dialog, telemetry, and
  citation placeholders.

The default emulator endpoint is `ws://10.0.2.2:8000/api/v1/ws/audio`; release
builds must provide a TLS `wss://` endpoint through `BuildConfig`.

## Build validation

The repository does not currently include the Gradle wrapper and the execution
environment does not have Gradle installed, so Android compilation is pending a
developer Android Studio/Gradle environment. JavaScript syntax checks and the
existing backend suite remain required before client work continues.
