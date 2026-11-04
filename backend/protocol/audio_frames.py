"""Validation helpers for binary PCM WebSocket frames."""

from pydantic import ValidationError

from .messages import AudioFormat, AudioFrameMetadata


def validate_audio_frame(payload: bytes, metadata: AudioFrameMetadata, audio_format: AudioFormat) -> None:
    """Raise ``ValueError`` when a binary frame violates negotiated PCM rules."""
    if not payload:
        raise ValueError("Audio frame cannot be empty")
    if len(payload) != metadata.byte_length:
        raise ValueError("Audio frame length does not match metadata")
    if len(payload) % audio_format.sample_width_bytes:
        raise ValueError("Audio frame is not aligned to the negotiated sample width")
    if audio_format.channels != 1:
        raise ValueError("Only mono PCM is currently supported")


__all__ = ["validate_audio_frame", "AudioFormat", "AudioFrameMetadata", "ValidationError"]
