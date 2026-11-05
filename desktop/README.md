# Voice Agent Desktop

This Electron shell loads the authenticated web client served by the FastAPI
backend. It adds a tray icon, `Ctrl+Space`/`Cmd+Space` toggle, a floating window,
context isolation, disabled Node integration, and microphone permission control.

Run from this directory after installing dependencies:

```text
npm install
npm start
```

Set `VOICE_AGENT_URL` when the backend is not at `http://localhost:8000`.
