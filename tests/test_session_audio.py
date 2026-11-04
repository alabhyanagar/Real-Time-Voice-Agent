from backend.audio.audio_format import AudioFormatConfig
from backend.audio.turn_detector import TurnDetector
from backend.sessions.session_controller import SessionController
from backend.sessions.session_state import SessionState


def test_turn_detector_debounces_onset_and_hangover():
    detector = TurnDetector(threshold=0.5, onset_frames=2, hangover_frames=2)
    assert detector.process(0.8).type == "speech"
    assert detector.process(0.8).type == "speech_start"
    assert detector.process(0.1).type == "speech"
    assert detector.process(0.1).type == "speech_end"


def test_audio_format_rejects_misaligned_frames():
    audio = AudioFormatConfig()
    audio.validate_frame(b"\x00\x00")
    try:
        audio.validate_frame(b"\x00")
    except ValueError:
        pass
    else:
        raise AssertionError("misaligned PCM must be rejected")


def test_session_interrupt_rotates_generation():
    session = SessionController("session", "user")
    session.transition(SessionState.CONNECTING)
    session.transition(SessionState.LISTENING)
    old_generation = session.generation_id
    new_generation = session.interrupt()
    assert new_generation != old_generation
    assert session.state == SessionState.INTERRUPTING
