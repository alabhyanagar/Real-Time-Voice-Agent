import asyncio
import logging
import threading
from typing import Awaitable, Callable, Optional, Any
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from backend.core.config import settings

logger = logging.getLogger("uvicorn.error")

def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to safely extract fields whether obj is a dictionary or a Pydantic/SDK model."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

class STTService:
    def __init__(self, on_transcript_callback: Callable[[str, bool], Awaitable[None]]):
        self.api_key = settings.DEEPGRAM_API_KEY.strip().strip("'").strip('"') if settings.DEEPGRAM_API_KEY else ""
        self.on_transcript_callback = on_transcript_callback
        
        self.client: Optional[DeepgramClient] = None
        self.connection: Optional[Any] = None
        self.is_connected: bool = False
        
        self._thread: Optional[threading.Thread] = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._current_transcript: str = ""

        if self.api_key:
            self.client = DeepgramClient(api_key=self.api_key)

    def _submit_callback(self, text: str, is_final: bool) -> None:
        """Bridge SDK worker-thread callbacks into asyncio without orphaned errors."""
        if not self.loop or not self.loop.is_running() or self.loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(
            self.on_transcript_callback(text, is_final), self.loop
        )
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

    def reset_turn(self) -> None:
        self._current_transcript = ""

    async def connect(self):
        """Establishes live streaming WebSocket connection to Deepgram Flux v2 with multilingual (English + Hindi) support."""
        if not self.api_key or not self.client:
            logger.error("DEEPGRAM_API_KEY is missing or empty. STT service cannot connect.")
            return

        self.loop = asyncio.get_running_loop()
        self._ready_event.clear()
        self._stop_event.clear()
        self.is_connected = False
        self._current_transcript = ""

        # Launch listener in dedicated worker thread
        self._thread = threading.Thread(target=self._run_listener, daemon=True)
        self._thread.start()

        # Await connection ready event without blocking asyncio event loop
        try:
            connected = await asyncio.to_thread(self._ready_event.wait, timeout=6.0)
            if not connected or not self.is_connected:
                logger.error("Timed out or failed while connecting to Deepgram Live STT.")
                self.is_connected = False
            else:
                logger.info("Connected to Deepgram Live STT (flux-general-multi) successfully.")
        except Exception as e:
            logger.error(f"Error during Deepgram connect: {str(e)}")
            self.is_connected = False

    def _run_listener(self):
        """Worker thread running Deepgram live WebSocket listener."""
        try:
            with self.client.listen.v2.connect(
                model="flux-general-multi",
                language_hint=["en", "hi"],
                eot_threshold=0.7,
                eot_timeout_ms=5000,
                encoding="linear16",
                sample_rate=16000,
            ) as connection:
                self.connection = connection

                def on_open(_):
                    self.is_connected = True
                    self._ready_event.set()

                def on_close(_):
                    self.is_connected = False
                    logger.info("Deepgram STT WebSocket closed.")

                def on_error(err):
                    logger.error(f"Deepgram STT WebSocket error: {err}")
                    self.is_connected = False
                    self._ready_event.set()

                def on_message(result):
                    try:
                        event = _get_attr(result, "event")
                        turn_index = _get_attr(result, "turn_index")
                        eot_confidence = _get_attr(result, "end_of_turn_confidence")
                        transcript = _get_attr(result, "transcript")

                        if event == "StartOfTurn":
                            logger.debug(f"--- StartOfTurn (Turn {turn_index}) ---")
                            self._current_transcript = ""

                        if transcript:
                            self._current_transcript = transcript
                            is_final = (event == "EndOfTurn")
                            logger.debug(f"STT Transcript [Final: {is_final}, Event: {event}]: {transcript}")
                            
                            if self.loop and self.loop.is_running() and not self.loop.is_closed():
                                self._submit_callback(transcript, is_final)

                        if event == "EndOfTurn":
                            logger.debug(f"--- EndOfTurn (Turn {turn_index}, Confidence: {eot_confidence}) ---")
                            # If transcript was not in this message but accumulated earlier
                            if not transcript and self._current_transcript:
                                if self.loop and self.loop.is_running() and not self.loop.is_closed():
                                    self._submit_callback(self._current_transcript, True)
                            self._current_transcript = ""

                    except Exception as ex:
                        logger.error(f"Error handling Deepgram message: {str(ex)}")

                connection.on(EventType.OPEN, on_open)
                connection.on(EventType.CLOSE, on_close)
                connection.on(EventType.ERROR, on_error)
                connection.on(EventType.MESSAGE, on_message)

                logger.info("Starting Deepgram live STT listening loop...")
                connection.start_listening()

        except Exception as e:
            logger.error(f"Failed to connect or maintain Deepgram STT stream: {str(e)}")
            self.is_connected = False
            self._ready_event.set()
        finally:
            self.is_connected = False
            self.connection = None

    async def send_audio(self, audio_chunk: bytes):
        """Streams raw binary PCM audio chunks to Deepgram."""
        if not self.is_connected or not self.connection:
            return
        try:
            self.connection.send_media(audio_chunk)
        except Exception as e:
            logger.error(f"Error sending audio chunk to Deepgram: {str(e)}")
            self.is_connected = False

    async def close(self):
        """Closes the Deepgram WebSocket connection cleanly."""
        self.is_connected = False
        if self.connection:
            try:
                self.connection.send_close_stream()
            except Exception:
                pass
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, timeout=1.5)
        self.connection = None
        logger.info("Deepgram STT service closed cleanly.")
