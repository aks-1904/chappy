import logging
from dataclasses import dataclass, field
import time
from enum import Enum, auto
from collections import deque

log = logging.getLogger(__name__)

_DISTRESS_WEIGHTS = {
    "sad":      0.7,
    "fear":     0.8,
    "angry":    0.6,
    "disgust":  0.5,
    "surprise": 0.2,   # could be positive
    "neutral":  0.0,
    "happy":    0.0,
}

@dataclass
class EmotionSample:
    emotion: str
    intensity: float
    person: str = "Guest"
    timestamp: float = field(default_factory=time.time)

class DistressLevel(Enum):
    NONE = auto() # All fine
    MILD = auto() # Slight sadness, tiredness
    MODERATE = auto() # Prolonged sadness, visible upset
    HIGH = auto() # Crying, fear, anger
    CRISIS = auto() # extreme distress

class EmotionalSupportModule:
    WINDOW_SIZE = 20 # Rolling window

    def __init__(self):
        self._history = dict[str, deque] = {}
        self._last_checkin: dict[str, float] = {}
        self._support_mode: dict[str, bool]  = {} # in active support conversation
        self._turn_counts: dict[str, int] = {} # turns of support given

    def record_emotion(self, person: str, emotion: str, intensity: float = 0.6):
        if person not in self._history:
            self._history[person] = deque(maxlen=self.WINDOW_SIZE)
            
        self._history[person].append(
            EmotionSample(emotion=emotion, intensity=intensity, person=person)
        )

    def get_distress_level(self, person: str) -> DistressLevel:
        samples = list(self._history.get(person, []))
        if not samples:
            return DistressLevel.NONE
        
        now = time.time()
        # Only consider samples from the last 3 minutes
        recent = [s for s in samples if now - s.timestamp < 180]
        if not recent:
            return DistressLevel.NONE
        
        # CHeck for crisis keywords already recorded as max-intensity fear
        crisis_count = sum(1 for s in recent if s.emotion == "fear" and s.intensity >= 1.0)
        if crisis_count >= 1:
            return DistressLevel.CRISIS
        
        # Weighted distress score
        score = sum(_DISTRESS_WEIGHTS.get(s.emotion, 0) * s.intensity for s in recent) / len(recent)

        # Duration
        neg_samples = [s for s in recent if _DISTRESS_WEIGHTS.get(s.emotion, 0) > 0]
        if neg_samples:
            duration = now - neg_samples[0].timestamp
        else:
            duration = 0

        if score >= 0.7 or duration > 90:
            return DistressLevel.HIGH
        if score >= 0.45 or duration > 45:
            return DistressLevel.MODERATE
        if score >= 0.2:
            return DistressLevel.MILD
        return DistressLevel.NONE

    def enter_support_mode(self, person: str):
        self._support_mode[person] = True
        self._turn_counts[person] = 0

        log.info(f"[Emotion] Support mode ON for {person}")

    def mark_checkin(self, person: str):
        self._last_checkin[person] = time.time()

    def get_support_prompt_injection(
            self,
            person: str,
            nickname: str,
            distress: DistressLevel,
            turn: int,
            relation: str = "friend",
    ) -> str:
        pass