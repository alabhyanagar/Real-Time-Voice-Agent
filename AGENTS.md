# Engineering Standards & Guardrails: Real-Time Voice Agent

## 1. Architecture & Design Principles
- **Modularity:** Maintain strict separation of concerns. Services (VAD, STT, LLM, TTS) must be isolated in independent modules within `/backend/services/`.
- **Asynchronous Execution:** Use Python `asyncio` across the entire pipeline to handle non-blocking concurrent streaming of audio chunks and token streams.

## 2. Tech Stack Constraints
- **Backend:** Python 3.10+, FastAPI, Uvicorn, WebSockets, Pydantic v2.
- **Frontend:** HTML5, Tailwind CSS (via CDN), Vanilla JavaScript, Web Audio API (`AudioWorklet` / `AudioContext`).
- **State Management:** Clean state machines for managing agent states (Listening, Processing, Speaking, Interrupted/Barge-in).

## 3. Security & Compliance
- **Environment Isolation:** Never hardcode API keys. All credentials (Groq, Deepgram, ElevenLabs/Cartesia) must be loaded securely from environment variables using `python-dotenv`.
- **Input Validation:** Validate all incoming WebSocket payloads using Pydantic schemas. Reject malformed or oversized binary frames immediately.
- **CORS & Origin Security:** Configure strict CORS headers and validate WebSocket connection origins in production.

## 4. Performance & Execution
- **Low Latency Optimization:** Prioritize stream-based processing over batch processing for STT and TTS to minimize perceived latency.
- **Incremental Streaming:** Implement "early return" patterns for streaming responses (e.g., streaming TTS audio as it becomes available).

## 5. Development Workflow
- **Build Incrementally:** Implement one module at a time.
- **Testing:** Write unit tests for service logic and integration tests for the pipeline.
- **Review:** Present artifacts/diffs for review before advancing to the next module.

## 6. Prompt Engineering & LLM Interaction
- **Context Management:** Maintain a sliding window of conversation history (User Utterances + AI Responses) to provide context to the LLM.
- **Prompt Structure:** Use a strict system prompt defining the Agent's persona, operational rules (e.g., "Respond to the user immediately"), and task objective (e.g., "Summarize the conversation.").
- **Streaming Logic:** Ensure the LLM integration layer supports streaming JSON output to enable token-by-token processing and reduce perceived latency.

## 7. Audio Processing & VAD
- **Chunk-Based Processing:** Audio data must be processed in fixed-size chunks (e.g., 20ms or 40ms) to maintain real-time performance.
- **Voice Activity Detection (VAD):** Use Silero VAD to reliably detect speech boundaries, minimizing false positives during pauses or background noise.

## 8. State Management & Control Flow
- **State Machine:** Implement a robust state machine (e.g., `IDLE` -> `LISTENING` -> `PROCESSING` -> `SPEAKING`) to handle the lifecycle of the conversation.
- **Barge-In Support:** Implement logic to interrupt the AI's speech if new user audio is detected (requires continuous monitoring via VAD during the `SPEAKING` state).

## 9. Testing & Validation
- **Unit Testing:** Write unit tests for individual services (VAD, STT, LLM, TTS) to ensure they meet performance and accuracy requirements.
- **Integration Testing:** Implement integration tests to validate the entire pipeline from audio input to text output and back.

## 10. Documentation & Code Quality
- **Inline Documentation:** Add comprehensive docstrings and type hints to all functions and classes.
- **Readability:** Maintain clean, modular, and well-structured code that adheres to Python's PEP 8 style guide.

