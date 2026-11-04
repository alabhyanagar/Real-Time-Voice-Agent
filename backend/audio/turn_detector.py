"""Debounced speech onset/hangover state machine for VAD probabilities."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TurnEvent:
    type: Literal["speech_start", "speech_end", "speech", "silence"]
    probability: float


class TurnDetector:
    def __init__(self, threshold: float = 0.5, onset_frames: int = 2, hangover_frames: int = 8):
        self.threshold = threshold
        self.onset_frames = max(1, onset_frames)
        self.hangover_frames = max(1, hangover_frames)
        self.speaking = False
        self._onset = 0
        self._silence = 0

    def process(self, probability: float) -> TurnEvent:
        probability = max(0.0, min(1.0, float(probability)))
        if probability >= self.threshold:
            self._onset += 1
            self._silence = 0
            if not self.speaking and self._onset >= self.onset_frames:
                self.speaking = True
                return TurnEvent("speech_start", probability)
            return TurnEvent("speech", probability)
        self._onset = 0
        if self.speaking:
            self._silence += 1
            if self._silence >= self.hangover_frames:
                self.speaking = False
                self._silence = 0
                return TurnEvent("speech_end", probability)
            return TurnEvent("speech", probability)
        return TurnEvent("silence", probability)

    def reset(self) -> None:
        self.speaking = False
        self._onset = 0
        self._silence = 0
