import logging
import httpx
from typing import AsyncGenerator
from backend.core.config import settings

logger = logging.getLogger("uvicorn.error")

class TTSService:
    def __init__(self):
        self.elevenlabs_api_key = settings.ELEVENLABS_API_KEY
        self.deepgram_api_key = settings.DEEPGRAM_API_KEY
        # Using ElevenLabs Flash v2.5 model optimized for ultra-low latency speech generation
        self.model_id = "eleven_flash_v2_5"
        # Default verified premade voice ID (e.g. George "JBFqnCBsd6RMkjVDRZzb")
        self.voice_id = getattr(settings, "ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the current provider stream (used by barge-in)."""
        self._cancelled = True

    def reset(self) -> None:
        self._cancelled = False

    async def _stream_sentence(self, text: str) -> AsyncGenerator[bytes, None]:
        if self._cancelled or not text.strip():
            return
        if self.elevenlabs_api_key:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?output_format=pcm_16000"
            headers = {"xi-api-key": self.elevenlabs_api_key, "Content-Type": "application/json", "Accept": "audio/pcm"}
            payload = {"text": text, "model_id": self.model_id, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code == 200:
                            async for chunk in response.aiter_bytes(chunk_size=1024):
                                if self._cancelled:
                                    return
                                if chunk:
                                    yield chunk
                            return
                        logger.warning("ElevenLabs returned %s; trying Deepgram", response.status_code)
            except Exception as exc:
                logger.warning("ElevenLabs stream failed: %s", exc)
        if self.deepgram_api_key and not self._cancelled:
            url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=16000"
            headers = {"Authorization": f"Token {self.deepgram_api_key}", "Content-Type": "application/json"}
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("POST", url, headers=headers, json={"text": text}) as response:
                        if response.status_code == 200:
                            async for chunk in response.aiter_bytes(chunk_size=1024):
                                if self._cancelled:
                                    return
                                if chunk:
                                    yield chunk
            except Exception as exc:
                logger.error("Deepgram TTS stream failed: %s", exc)

    @staticmethod
    async def _sentences(text_iterator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        buffer = ""
        async for token in text_iterator:
            buffer += token
            while True:
                boundary = next((i for i, char in enumerate(buffer) if char in ".!?\n"), -1)
                if boundary < 0 and len(buffer) < 180:
                    break
                if boundary < 0:
                    boundary = 179
                sentence, buffer = buffer[:boundary + 1], buffer[boundary + 1:]
                if sentence.strip():
                    yield sentence.strip()
        if buffer.strip():
            yield buffer.strip()

    async def stream_audio_from_text(self, text_iterator: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        """
        Consumes text tokens from an LLM stream, sends them to ElevenLabs (with Deepgram Aura fallback),
        and yields streaming raw 16kHz PCM audio chunks.
        """
        self.reset()
        async for sentence in self._sentences(text_iterator):
            if self._cancelled:
                break
            async for chunk in self._stream_sentence(sentence):
                yield chunk
