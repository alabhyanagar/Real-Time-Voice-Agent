"""Negotiated PCM audio format and safe frame sizing."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormatConfig:
    sample_rate_hz: int = 16_000
    channels: int = 1
    sample_width_bytes: int = 2
    encoding: str = "pcm_s16le"

    @property
    def bytes_per_second(self) -> int:
        return self.sample_rate_hz * self.channels * self.sample_width_bytes

    def frame_bytes(self, duration_ms: int) -> int:
        if duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        samples = round(self.sample_rate_hz * duration_ms / 1000)
        return samples * self.channels * self.sample_width_bytes

    def validate_frame(self, payload: bytes, *, duration_ms: int | None = None) -> None:
        if not payload or len(payload) % (self.channels * self.sample_width_bytes):
            raise ValueError("PCM frame is empty or misaligned")
        if duration_ms is not None and len(payload) != self.frame_bytes(duration_ms):
            raise ValueError("PCM frame length does not match negotiated duration")
