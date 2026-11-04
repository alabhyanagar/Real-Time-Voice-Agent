import logging
import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.core.config import settings
from backend.core.rate_limit import ConnectionRateLimiter
from backend.core.security import authenticate_websocket
from backend.protocol.audio_frames import validate_audio_frame
from backend.protocol import parse_event
from backend.protocol.messages import AudioFormat, AudioFormatEvent, AudioFrameMetadata, CancelEvent, FlushEvent, HelloEvent, PingEvent
from backend.services.pipeline_orchestrator import PipelineOrchestrator
from backend.sessions.session_manager import session_manager

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
rate_limiter = ConnectionRateLimiter(settings.WS_RATE_LIMIT_PER_MINUTE, settings.WS_MAX_CONNECTIONS_PER_USER)

def _origin_allowed(websocket: WebSocket) -> bool:
    """Allow non-browser clients while enforcing configured browser origins."""
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    return "*" in settings.ALLOWED_ORIGINS or origin in settings.ALLOWED_ORIGINS

def _next_sequence(websocket: WebSocket) -> int:
    sequence = int(websocket.scope.get("voice_sequence", 0))
    websocket.scope["voice_sequence"] = sequence + 1
    return sequence


def _event_metadata(session_id: str, *, sequence: int = 0, generation_id: str | None = None) -> dict:
    return {
        "protocol_version": "1.0",
        "session_id": session_id,
        "turn_id": "gateway",
        "sequence": sequence,
        "generation_id": generation_id,
        "timestamp_ms": __import__("time").time_ns() // 1_000_000,
    }


async def _send_error(websocket: WebSocket, session_id: str, code: str, message: str, *, retryable: bool = False):
    await websocket.send_json({
        "type": "error",
        **_event_metadata(session_id, sequence=_next_sequence(websocket)),
        "code": code,
        "message": message,
        "retryable": retryable,
    })


@router.websocket("/ws/audio")
async def audio_websocket_endpoint(websocket: WebSocket):
    session_id = str(uuid4())
    expected_audio_bytes = None
    claims = authenticate_websocket(websocket)
    if claims is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    user_id = str(claims.get("sub"))
    if not rate_limiter.acquire(user_id):
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    if not hasattr(websocket, "scope"):
        websocket.scope = {}
    websocket.scope["voice_session_id"] = session_id
    websocket.scope["voice_user_id"] = user_id
    websocket.scope["voice_sequence"] = 0
    websocket.scope["voice_generation_id"] = str(uuid4())
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"Client connected for live voice pipeline: {client_ip}")

    server_audio_format = AudioFormat(
        sample_rate_hz=settings.AUDIO_SAMPLE_RATE,
        channels=settings.AUDIO_CHANNELS,
        sample_width_bytes=settings.AUDIO_SAMPLE_WIDTH_BYTES,
    )
    await websocket.send_json({
        "type": "ready",
        **_event_metadata(session_id, sequence=_next_sequence(websocket), generation_id=websocket.scope["voice_generation_id"]),
        "server_version": "1.0.0",
        "audio_format": server_audio_format.model_dump(),
    })

    # Safely initialize the pipeline orchestrator
    try:
        session = session_manager.create(session_id, user_id)
        try:
            orchestrator = PipelineOrchestrator(websocket, session=session)
        except TypeError as exc:
            # Preserve the transport seam for lightweight test/dummy adapters
            # that still implement the pre-session constructor.
            if "session" not in str(exc):
                raise
            orchestrator = PipelineOrchestrator(websocket)
        await orchestrator.start()
    except Exception as startup_err:
        logger.error(f"Failed to initialize pipeline orchestrator: {str(startup_err)}")
        try:
            await _send_error(
                websocket,
                session_id,
                "PIPELINE_STARTUP_FAILED",
                "Server pipeline setup failed",
                retryable=True,
            )
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
        session_manager.remove(session_id)
        return

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=max(1, settings.WS_HEARTBEAT_SECONDS)
                )
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "pong",
                    **_event_metadata(session_id, sequence=_next_sequence(websocket), generation_id=websocket.scope["voice_generation_id"]),
                })
                continue

            if message.get("type") == "websocket.disconnect":
                break

            if not rate_limiter.allow_message(user_id):
                await _send_error(websocket, session_id, "RATE_LIMITED", "WebSocket message rate exceeded", retryable=True)
                await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
                break
            
            if "bytes" in message:
                audio_chunk = message["bytes"]
                if not isinstance(audio_chunk, bytes):
                    await _send_error(websocket, session_id, "INVALID_AUDIO", "Binary audio frame is required")
                    await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                    break
                if not audio_chunk or len(audio_chunk) > settings.WS_MAX_MESSAGE_BYTES:
                    await _send_error(websocket, session_id, "AUDIO_FRAME_TOO_LARGE", "Audio frame exceeds the configured limit")
                    await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                    break
                if expected_audio_bytes is not None and len(audio_chunk) != expected_audio_bytes:
                    await _send_error(websocket, session_id, "AUDIO_LENGTH_MISMATCH", "Binary frame does not match its metadata")
                    await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                    break
                try:
                    validate_audio_frame(audio_chunk, AudioFrameMetadata(
                        session_id=session_id,
                        turn_id="gateway",
                        byte_length=len(audio_chunk),
                        frame_index=0,
                    ), server_audio_format)
                except ValueError as frame_error:
                    await _send_error(websocket, session_id, "INVALID_AUDIO_FRAME", str(frame_error))
                    await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                    break
                expected_audio_bytes = None
                await orchestrator.handle_audio_chunk(audio_chunk)
                
            elif "text" in message:
                text_data = message["text"]
                try:
                    if len(text_data.encode("utf-8")) > settings.WS_MAX_MESSAGE_BYTES:
                        await _send_error(websocket, session_id, "MESSAGE_TOO_LARGE", "Control message exceeds the configured limit")
                        await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                        break
                    event = parse_event(text_data, direction="client")
                    if event.generation_id and event.generation_id != websocket.scope["voice_generation_id"]:
                        await _send_error(websocket, session_id, "STALE_GENERATION", "Message belongs to a cancelled generation")
                        continue
                    if isinstance(event, HelloEvent):
                        if event.session_id != session_id:
                            await _send_error(
                                websocket,
                                session_id,
                                "SESSION_ID_MISMATCH",
                                "hello.session_id must match the session advertised by ready",
                            )
                            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                            break
                    elif isinstance(event, PingEvent):
                        await websocket.send_json({"type": "pong", **_event_metadata(session_id, sequence=_next_sequence(websocket), generation_id=websocket.scope["voice_generation_id"])})
                    elif isinstance(event, AudioFormatEvent):
                        expected = server_audio_format
                        if event.format != expected:
                            await _send_error(websocket, session_id, "UNSUPPORTED_AUDIO_FORMAT", "Audio format does not match the server contract")
                            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                            break
                    elif event.type == "audio_frame":
                        expected_audio_bytes = event.byte_length
                        if expected_audio_bytes > settings.WS_MAX_MESSAGE_BYTES:
                            await _send_error(websocket, session_id, "AUDIO_FRAME_TOO_LARGE", "Audio metadata exceeds the configured limit")
                            await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                            break
                    elif isinstance(event, (CancelEvent, FlushEvent)):
                        websocket.scope["voice_generation_id"] = str(uuid4())
                        await orchestrator.interrupt()
                        await websocket.send_json({
                            "type": "audio_flush",
                            **_event_metadata(session_id, sequence=_next_sequence(websocket), generation_id=websocket.scope["voice_generation_id"]),
                            "reason": event.reason,
                        })
                except (ValueError, json.JSONDecodeError) as protocol_error:
                    await _send_error(websocket, session_id, "INVALID_PROTOCOL_MESSAGE", str(protocol_error))
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    break

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_ip}")
    except Exception as e:
        logger.error(f"WebSocket error with {client_ip}: {str(e)}")
    finally:
        rate_limiter.release(user_id)
        await orchestrator.close()
        session_manager.remove(session_id)
