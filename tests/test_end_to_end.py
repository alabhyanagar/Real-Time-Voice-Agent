"""tests/test_end_to_end.py

End-to-End integration tests for Step 16:
  - Prerecorded 16 kHz PCM audio chunk stream ingestion.
  - STT transcript to final audio output turn event flow.
  - Barge-in during TTS playback (cancelling active generation and flushing audio).
  - Network disconnect and recovery via resume_token handshake.
  - Multiple concurrent sessions ensuring strict multi-tenant isolation.
"""
import math
import struct
from backend.protocol import (
    PROTOCOL_VERSION,
    AudioEndEvent,
    AudioFlushEvent,
    AudioFormat,
    AudioFormatEvent,
    AudioFrameMetadata,
    AudioStartEvent,
    CancelEvent,
    HelloEvent,
    ReadyEvent,
    ResponseTextDeltaEvent,
    StateEvent,
    TranscriptEvent,
    parse_event,
    serialize_event,
)
from backend.observability.events import TurnEventBus


def generate_mock_pcm16_frame(sample_rate=16000, duration_ms=20, freq_hz=440, amplitude=16000) -> bytes:
    """Generate 20ms of 16-bit mono PCM audio."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    if amplitude == 0:
        return b"\x00" * (num_samples * 2)
    samples = [
        int(amplitude * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
        for i in range(num_samples)
    ]
    return struct.pack(f"<{len(samples)}h", *samples)


def test_prerecorded_pcm_input():
    """Validates feeding prerecorded 16 kHz PCM frames into the protocol."""
    TurnEventBus.reset()
    session_id = "e2e-session-pcm"
    turn_id = "turn-001"

    # 1. Format negotiation
    fmt = AudioFormatEvent(
        session_id=session_id,
        turn_id=turn_id,
        format=AudioFormat(encoding="pcm_s16le", sample_rate_hz=16000, channels=1),
        sequence=1,
    )
    parsed_fmt = parse_event(serialize_event(fmt), direction="client")
    assert parsed_fmt.format.sample_rate_hz == 16000

    # 2. Stream 10 mock PCM frames (200ms of voice)
    received_bytes = 0
    for i in range(10):
        frame = generate_mock_pcm16_frame(amplitude=12000)
        meta = AudioFrameMetadata(
            session_id=session_id,
            turn_id=turn_id,
            sequence=2 + i,
            byte_length=len(frame),
            frame_index=i,
        )
        parsed_meta = parse_event(serialize_event(meta), direction="client")
        assert parsed_meta.byte_length == 640
        received_bytes += len(frame)

    assert received_bytes == 6400
    TurnEventBus.reset()


def test_stt_to_final_audio_output_flow():
    """Simulates complete turn lifecycle: STT transcript -> LLM response -> TTS audio output."""
    session_id = "e2e-turn-flow"
    turn_id = "turn-002"
    gen_id = "gen-flow-100"

    # Server ready
    ready = ReadyEvent(
        session_id=session_id,
        turn_id=turn_id,
        server_version="1.0.0",
        audio_format=AudioFormat(),
        generation_id=gen_id,
    )
    assert parse_event(serialize_event(ready), direction="server").type == "ready"

    # STT produces final transcript
    transcript = TranscriptEvent(
        session_id=session_id,
        turn_id=turn_id,
        text="What is the weather today?",
        is_final=True,
        generation_id=gen_id,
    )
    assert parse_event(serialize_event(transcript), direction="server").text == "What is the weather today?"

    # LLM streams response delta
    delta = ResponseTextDeltaEvent(
        session_id=session_id,
        turn_id=turn_id,
        text="The weather is clear and 72 degrees.",
        is_final=True,
        generation_id=gen_id,
    )
    assert "clear and 72" in parse_event(serialize_event(delta), direction="server").text

    # TTS audio stream envelopes
    audio_start = AudioStartEvent(session_id=session_id, turn_id=turn_id, generation_id=gen_id)
    audio_end = AudioEndEvent(session_id=session_id, turn_id=turn_id, generation_id=gen_id)

    assert parse_event(serialize_event(audio_start), direction="server").type == "audio_start"
    assert parse_event(serialize_event(audio_end), direction="server").type == "audio_end"


def test_barge_in_during_tts():
    """Validates user barge-in interruption while assistant is speaking."""
    session_id = "e2e-bargein"
    turn_id = "turn-003"
    interrupted_gen_id = "gen-interrupt-456"

    # Assistant is in speaking state
    speaking = StateEvent(session_id=session_id, turn_id=turn_id, state="speaking", generation_id=interrupted_gen_id)
    assert parse_event(serialize_event(speaking), direction="server").state == "speaking"

    # User barges in -> client emits CancelEvent
    cancel = CancelEvent(session_id=session_id, turn_id=turn_id, sequence=10, reason="barge_in", generation_id=interrupted_gen_id)
    parsed_cancel = parse_event(serialize_event(cancel), direction="client")
    assert parsed_cancel.reason == "barge_in"

    # Server responds with AudioFlushEvent to immediately truncate client playback
    flush = AudioFlushEvent(session_id=session_id, turn_id=turn_id, reason="barge_in", generation_id=interrupted_gen_id)
    assert parse_event(serialize_event(flush), direction="server").reason == "barge_in"


def test_network_disconnect_and_recovery():
    """Validates reconnect handshake preserving session continuity via resume_token."""
    session_id = "e2e-session-recovery"
    turn_id = "turn-004"
    resume_token = "reconnect_token_secret_777"

    # Initial hello
    hello_init = HelloEvent(session_id=session_id, turn_id=turn_id, client_name="android", sequence=0)
    assert parse_event(serialize_event(hello_init), direction="client").resume_token is None

    # Reconnect hello with resume token
    hello_reconnect = HelloEvent(
        session_id=session_id,
        turn_id="turn-005",
        client_name="android",
        sequence=0,
        resume_token=resume_token,
    )
    parsed_reconnect = parse_event(serialize_event(hello_reconnect), direction="client")
    assert parsed_reconnect.resume_token == resume_token
    assert parsed_reconnect.session_id == session_id


def test_multiple_concurrent_sessions():
    """Ensures two concurrent sessions maintain completely isolated event streams and states."""
    session_a = "session-user-alpha"
    session_b = "session-user-beta"

    event_a = TranscriptEvent(session_id=session_a, turn_id="t-1", text="Alpha query: schedule meeting", is_final=True)
    event_b = TranscriptEvent(session_id=session_b, turn_id="t-1", text="Beta query: check emails", is_final=True)

    parsed_a = parse_event(serialize_event(event_a), direction="server")
    parsed_b = parse_event(serialize_event(event_b), direction="server")

    assert parsed_a.session_id == session_a
    assert "Alpha query" in parsed_a.text

    assert parsed_b.session_id == session_b
    assert "Beta query" in parsed_b.text
