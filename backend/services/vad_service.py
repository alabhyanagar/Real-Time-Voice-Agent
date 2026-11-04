import torch
import numpy as np
import logging
import threading
from backend.core.config import settings
from backend.audio.turn_detector import TurnDetector

logger = logging.getLogger("uvicorn.error")

class VADService:
    _model_cache = None
    _utils_cache = None
    _model_lock = threading.Lock()

    def __init__(self, sampling_rate: int = 16000, threshold: float = 0.5):
        self.sampling_rate = sampling_rate
        self.threshold = threshold
        self.model = None
        self.utils = None
        # Silero VAD requires exact window sizes: 512 for 16kHz, 256 for 8kHz
        self.window_size = 512 if sampling_rate == 16000 else 256
        self.bytes_per_window = self.window_size * 2  # 16-bit PCM = 2 bytes per sample
        self._buffer = bytearray()
        self._last_prob = 0.0
        self.turn_detector = TurnDetector(
            threshold=threshold,
            onset_frames=settings.VAD_SPEECH_ONSET_FRAMES,
            hangover_frames=settings.VAD_SILENCE_HANGOVER_FRAMES,
        )
        self._load_model()

    def _load_model(self):
        """Loads the pre-trained enterprise-grade Silero VAD model via torch.hub."""
        try:
            with self._model_lock:
                if self.__class__._model_cache is None:
                    torch.set_num_threads(1)
                    self.__class__._model_cache, self.__class__._utils_cache = torch.hub.load(
                        repo_or_dir="snakers4/silero-vad", model="silero_vad",
                        force_reload=False, trust_repo=True
                    )
                self.model, self.utils = self.__class__._model_cache, self.__class__._utils_cache
            logger.info("Silero VAD model loaded successfully.")
        except Exception as e:
            # A deployment can preload the model at startup; retain a safe energy
            # fallback so the gateway remains available while the model downloads.
            logger.error("Failed to load Silero VAD model: %s", e)
            self.model = None

    def process_chunk(self, audio_chunk: bytes) -> float:
        """
        Buffers raw PCM audio chunks (16-bit mono) and evaluates Silero VAD
        in exact 512-sample windows. Returns highest speech probability in chunk.
        """
        if not audio_chunk:
            return self._last_prob

        self._buffer.extend(audio_chunk)

        evaluated_probs = []
        while len(self._buffer) >= self.bytes_per_window:
            window_raw = bytes(self._buffer[:self.bytes_per_window])
            del self._buffer[:self.bytes_per_window]

            # Convert 16-bit PCM bytes to normalized float32 tensor
            audio_np = np.frombuffer(window_raw, dtype=np.int16).astype(np.float32) / 32768.0
            if self.model:
                audio_tensor = torch.from_numpy(audio_np)
                with torch.no_grad():
                    prob = self.model(audio_tensor, self.sampling_rate).item()
            else:
                # RMS-derived probability is deliberately conservative and only
                # used until Silero is available.
                prob = min(1.0, float(np.sqrt(np.mean(audio_np * audio_np)) * 8.0))
            evaluated_probs.append(prob)

        if evaluated_probs:
            self._last_prob = max(evaluated_probs)

        return self._last_prob

    def reset(self):
        """Resets the internal hidden states of the VAD model and buffer between utterances."""
        self._buffer.clear()
        self._last_prob = 0.0
        self.turn_detector.reset()
        if self.model and hasattr(self.model, "reset_states"):
            self.model.reset_states()
