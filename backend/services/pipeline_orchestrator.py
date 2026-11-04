"""Coordinates VAD, STT, LLM, and TTS while emitting protocol events."""

import asyncio
import contextlib
import logging
import time
from typing import Dict, List, Optional
from uuid import uuid4

from backend.protocol.messages import (
    AudioEndEvent,
    AudioFlushEvent,
    AudioStartEvent,
    ErrorEvent,
    ResponseTextDeltaEvent,
    StateEvent,
    ToolConfirmationEvent,
    ToolStatusEvent,
    ToolConfirmationResponseEvent,
    TranscriptEvent,
    TelemetryEvent,
    UiCardEvent,
)
from backend.services.llm_service import LLMService
from backend.integrations.google_oauth import get_default_google_oauth_service
from backend.integrations.microsoft_oauth import get_default_microsoft_oauth_service
from backend.services.stt_service import STTService
from backend.services.tts_service import TTSService
from backend.services.vad_service import VADService
from backend.memory import get_default_memory
from backend.memory.rag import get_default_retriever
from backend.sessions.session_controller import SessionController
from backend.sessions.session_state import SessionState
from backend.sessions.outbound_queue import OutboundQueue

logger = logging.getLogger("uvicorn.error")


class PipelineOrchestrator:
    """Run the voice pipeline and publish versioned server events."""

    def __init__(self, websocket, session=None):
        self.websocket = websocket
        self.vad = VADService(sampling_rate=16000, threshold=0.5)
        self.llm = LLMService(on_tool_event=self.handle_tool_event)
        self.tts = TTSService()
        self.state = "LISTENING"
        scope = getattr(websocket, "scope", {})
        self.session = session or SessionController(
            str(scope.get("voice_session_id", "local-session")),
            str(scope.get("voice_user_id", "anonymous")),
        )
        if isinstance(scope, dict):
            scope["voice_generation_id"] = self.session.generation_id
        self.outbound = OutboundQueue(websocket)
        self.memory = get_default_memory()
        self.rag = get_default_retriever()
        self.conversation_history: List[Dict[str, str]] = []
        self.current_task: Optional[asyncio.Task] = None
        self.stt = STTService(on_transcript_callback=self.handle_transcript)
        self.accumulated_transcript = ""
        self.turn_id = str(uuid4())
        self.response_id: Optional[str] = None
        self._sequence = 0
        self._filler_task: Optional[asyncio.Task] = None

    async def _safe_send_json(self, data: dict):
        try:
            await self.outbound.put_json(data)
        except Exception:
            pass

    async def _safe_send_bytes(self, data: bytes):
        try:
            await self.outbound.put_bytes(data)
        except Exception:
            pass

    def _session_id(self) -> str:
        scope = getattr(self.websocket, "scope", {})
        if isinstance(scope, dict):
            return str(scope.get("voice_session_id", self.session.session_id))
        return self.session.session_id

    def _next_sequence(self) -> int:
        scope = getattr(self.websocket, "scope", {})
        if isinstance(scope, dict) and "voice_sequence" in scope:
            sequence = int(scope["voice_sequence"])
            scope["voice_sequence"] = sequence + 1
            return sequence
        sequence = self._sequence
        self._sequence += 1
        return sequence

    async def _send_event(self, event):
        """Send a validated protocol event using the connection sequence."""
        payload = event.model_copy(update={
            "sequence": self._next_sequence(),
            "generation_id": self.session.generation_id,
        }).model_dump(exclude_none=True)
        await self._safe_send_json(payload)

    async def _set_state(self, state: str):
        self.state = state.upper()
        target = {
            "LISTENING": SessionState.LISTENING,
            "PROCESSING": SessionState.PROCESSING,
            "SPEAKING": SessionState.SPEAKING,
            "INTERRUPTING": SessionState.INTERRUPTING,
            "ERROR": SessionState.ERROR,
        }.get(self.state)
        if target:
            try:
                self.session.transition(target)
            except ValueError:
                # A protocol event should never be lost because a provider returned
                # late; force the authoritative state for recovery paths.
                self.session.state = target
        try:
            await self.memory.set_session_state(
                self.session.user_id,
                self._session_id(),
                state=self.state.lower(),
                generation_id=self.session.generation_id,
            )
        except Exception as exc:
            logger.warning("Conversation memory state update failed: %s", exc)

    async def _send_state(self, state: str):
        await self._send_event(StateEvent(
            session_id=self._session_id(),
            turn_id=self.turn_id,
            state=state,
        ))

    async def _stream_tool_filler(self):
        async def filler_text():
            yield "Let me check that."

        async for audio_chunk in self.tts.stream_audio_from_text(filler_text()):
            await self._safe_send_bytes(audio_chunk)

    async def _stop_tool_filler(self):
        if self._filler_task and not self._filler_task.done():
            self._filler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._filler_task
        self._filler_task = None

    async def handle_tool_event(self, payload: dict):
        """Publish tool status and start or cancel low-latency filler audio."""
        name = payload.get("tool_name", "unknown")
        status = payload.get("status")
        call_id = payload.get("call_id", name)
        if status == "confirmation_required":
            await self._stop_tool_filler()
            await self._send_event(ToolConfirmationEvent(
                session_id=self._session_id(),
                turn_id=self.turn_id,
                confirmation_id=payload.get("confirmation_id", call_id),
                tool_name=name,
                prompt=payload.get("prompt", "Confirmation required."),
            ))
            return
        await self._send_event(ToolStatusEvent(
            session_id=self._session_id(),
            turn_id=self.turn_id,
            tool_name=name,
            status=status if status in {"requested", "running", "completed", "failed"} else "failed",
            detail=payload.get("detail"),
        ))
        if status == "requested":
            await self._stop_tool_filler()
            self._filler_task = asyncio.create_task(self._stream_tool_filler())
        elif status in {"completed", "failed"}:
            await self._stop_tool_filler()

    async def handle_tool_confirmation(self, confirmation_id: str, approved: bool):
        """Execute or reject a user-bound pending tool confirmation."""
        result = await self.llm.resolve_tool_confirmation(
            confirmation_id,
            approved,
            session_id=self._session_id(),
            user_id=self.session.user_id,
            turn_id=self.turn_id,
            generation_id=self.session.generation_id,
        )
        if result is None:
            await self._send_event(ErrorEvent(session_id=self._session_id(), turn_id=self.turn_id, code="TOOLS_DISABLED", message="Tool execution is disabled."))
            return
        status = "completed" if result.status == "success" else "failed"
        await self._send_event(ToolStatusEvent(session_id=self._session_id(), turn_id=self.turn_id, tool_name=result.tool_name, status=status, detail=result.error_message))
        message = "The requested action is complete." if result.status == "success" else (result.error_message or "The requested action was not completed.")
        await self._send_event(ResponseTextDeltaEvent(session_id=self._session_id(), turn_id=self.turn_id, response_id=self.response_id or str(uuid4()), text=message, is_final=True))

    async def start(self):
        await self.outbound.start()
        try:
            self.session.transition(SessionState.CONNECTING)
        except ValueError:
            pass
        await self.stt.connect()
        self.vad.reset()
        try:
            snapshot = await self.memory.load(self.session.user_id, self._session_id())
            self.conversation_history = [
                {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
                for item in snapshot.messages
                if item.get("role") in {"user", "assistant", "system"} and str(item.get("content", "")).strip()
            ]
            if snapshot.summary:
                self.conversation_history.insert(0, {
                    "role": "system",
                    "content": "Conversation summary for continuity: " + snapshot.summary,
                })
            logger.info("Recovered %d conversation messages for session %s", len(self.conversation_history), self._session_id())
        except Exception as exc:
            logger.warning("Conversation memory recovery failed: %s", exc)
        await self._set_state("LISTENING")
        await self._send_state("listening")
        logger.info("Pipeline Orchestrator started.")

    async def handle_audio_chunk(self, audio_chunk: bytes):
        try:
            speech_prob = self.vad.process_chunk(audio_chunk)
            self.vad.turn_detector.process(speech_prob)
            is_speech = self.vad.turn_detector.speaking
        except Exception as exc:
            logger.error("VAD processing error: %s", exc)
            return

        if self.state in ("SPEAKING", "PROCESSING") and is_speech:
            logger.info("Barge-in detected; interrupting agent speech.")
            await self.interrupt()

        if self.state == "LISTENING" and self.stt.is_connected:
            await self.stt.send_audio(audio_chunk)

    async def handle_transcript(self, text: str, is_final: bool):
        self.accumulated_transcript = text
        await self._send_event(TranscriptEvent(
            session_id=self._session_id(),
            turn_id=self.turn_id,
            text=text,
            is_final=is_final,
        ))

        if is_final and text.strip() and self.state == "LISTENING":
            self.turn_id = self.session.begin_turn()
            await self._set_state("PROCESSING")
            await self._send_state("processing")
            self.conversation_history.append({"role": "user", "content": text})
            try:
                await self.memory.append_turn(
                    self.session.user_id,
                    self._session_id(),
                    role="user",
                    content=text,
                    turn_id=self.turn_id,
                    metadata={"generation_id": self.session.generation_id},
                )
            except Exception as exc:
                logger.warning("User turn could not be persisted to conversation memory: %s", exc)
            self.current_task = asyncio.create_task(self.generate_and_stream_response())

    async def generate_and_stream_response(self):
        try:
            generation_id = self.session.generation_id
            await self._set_state("SPEAKING")
            self.response_id = str(uuid4())
            await self._send_state("speaking")
            await self._send_event(AudioStartEvent(
                session_id=self._session_id(),
                turn_id=self.turn_id,
                response_id=self.response_id,
            ))

            retrieved_context = []
            try:
                retrieval_started = time.perf_counter()
                query = self.accumulated_transcript or self.conversation_history[-1].get("content", "")
                rag_result = await self.rag.retrieve(
                    query,
                    user_id=self.session.user_id,
                    tenant_id=self.session.tenant_id,
                    conversation=self.conversation_history,
                )
                retrieved_context = list(rag_result.get("context", []))
                await self._send_event(TelemetryEvent(
                    session_id=self._session_id(),
                    turn_id=self.turn_id,
                    measurements={
                        "rag_retrieval_ms": round((time.perf_counter() - retrieval_started) * 1000, 2),
                        "rag_result_count": len(rag_result.get("results", [])),
                    },
                ))
                if rag_result.get("citations"):
                    await self._send_event(UiCardEvent(
                        session_id=self._session_id(),
                        turn_id=self.turn_id,
                        card_type="citations",
                        payload={
                            "citations": rag_result["citations"],
                            "rewritten_query": rag_result.get("rewritten_query", query),
                        },
                    ))
            except Exception as exc:
                logger.warning("RAG retrieval failed; continuing without documents: %s", exc)

            llm_stream = self.llm.stream_response(
                self.conversation_history,
                session_id=self._session_id(),
                user_id=self.session.user_id,
                turn_id=self.turn_id,
                generation_id=generation_id,
                granted_scopes=(
                    self.session.granted_scopes
                    | get_default_google_oauth_service().scopes_for_user(self.session.user_id)
                    | get_default_microsoft_oauth_service().scopes_for_user(self.session.user_id)
                ),
                retrieved_context=retrieved_context,
            )
            full_assistant_response = ""

            async def token_collector():
                nonlocal full_assistant_response
                async for token in llm_stream:
                    if await self.memory.is_cancelled(self.session.user_id, self._session_id(), generation_id):
                        raise asyncio.CancelledError
                    full_assistant_response += token
                    await self._send_event(ResponseTextDeltaEvent(
                        session_id=self._session_id(),
                        turn_id=self.turn_id,
                        response_id=self.response_id,
                        text=token,
                        is_final=False,
                    ))
                    yield token

            audio_stream = self.tts.stream_audio_from_text(token_collector())
            async for audio_chunk in audio_stream:
                if self.state != "SPEAKING":
                    break
                await self._safe_send_bytes(audio_chunk)

            if self.state == "SPEAKING":
                await self._send_event(AudioEndEvent(
                    session_id=self._session_id(),
                    turn_id=self.turn_id,
                    response_id=self.response_id,
                ))
                if full_assistant_response.strip():
                    self.conversation_history.append({"role": "assistant", "content": full_assistant_response})
                    try:
                        await self.memory.append_turn(
                            self.session.user_id,
                            self._session_id(),
                            role="assistant",
                            content=full_assistant_response,
                            turn_id=self.turn_id,
                            metadata={"response_id": self.response_id, "generation_id": self.session.generation_id},
                        )
                    except Exception as exc:
                        logger.warning("Assistant turn could not be persisted to conversation memory: %s", exc)
                    await self._send_event(ResponseTextDeltaEvent(
                        session_id=self._session_id(),
                        turn_id=self.turn_id,
                        response_id=self.response_id,
                        text=full_assistant_response,
                        is_final=True,
                    ))
                await self._set_state("LISTENING")
                await self._send_state("listening")
                self.accumulated_transcript = ""

        except asyncio.CancelledError:
            logger.info("Response generation task cancelled cleanly.")
        except Exception as exc:
            logger.error("Error in response generation pipeline: %s", exc)
            await self._set_state("ERROR")
            await self._send_event(ErrorEvent(
                session_id=self._session_id(),
                turn_id=self.turn_id,
                response_id=self.response_id,
                code="PIPELINE_FAILURE",
                message="Pipeline processing failed.",
                retryable=True,
            ))
            await self._set_state("LISTENING")
            await self._send_state("listening")

    async def interrupt(self):
        await self._set_state("INTERRUPTING")
        cancelled_generation = self.session.generation_id
        self.session.interrupt()
        try:
            await self.memory.cancel_generation(self.session.user_id, self._session_id(), cancelled_generation)
        except Exception as exc:
            logger.warning("Cancellation signal could not be persisted: %s", exc)
        scope = getattr(self.websocket, "scope", {})
        if isinstance(scope, dict):
            scope["voice_generation_id"] = self.session.generation_id
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.tts.cancel()
        try:
            await self.memory.set_session_state(self.session.user_id, self._session_id(), state="closed", generation_id=self.session.generation_id)
        except Exception as exc:
            logger.warning("Conversation memory close state update failed: %s", exc)
        await self._set_state("LISTENING")
        self.accumulated_transcript = ""
        self.vad.reset()
        self.stt.reset_turn()
        await self._stop_tool_filler()
        await self._send_event(AudioFlushEvent(
            session_id=self._session_id(),
            turn_id=self.turn_id,
            response_id=self.response_id,
            reason="barge_in",
        ))
        await self._send_state("listening")

    async def close(self):
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        await self._stop_tool_filler()
        await self.stt.close()
        self.tts.cancel()
        self.session.close()
        await self.outbound.close()
        logger.info("Pipeline Orchestrator closed.")
