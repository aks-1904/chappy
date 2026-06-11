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

# Emotion sequences that signal a genuine downturn
_CRISIS_KEYWORDS = [
    "can't go on", "give up", "no point", "hopeless", "worthless",
    "nobody cares", "want to die", "end it all", "hurt myself",
    "don't want to be here", "can't take it", "falling apart",
]

_SUPPORT_KEYWORDS = [
    "sad", "upset", "depressed", "lonely", "stressed", "anxious",
    "scared", "worried", "crying", "hurt", "broken", "lost",
    "miss", "tired of", "exhausted", "overwhelmed", "nobody understands",
    "feel alone", "feel like", "i hate", "i can't",
]

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
    CHECKIN_COOLDOWN = 120.0
    CHECKIN_AFTER = 45.0 # Minimum interval between unsolicited check-ins (seconds)

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

    def increment_support_turns(self, person: str):
        self._turn_counts[person] = self._turn_counts.get(person, 0) + 1

    def dominant_recent_emotion(self, person: str, window_sec: float = 60) -> str:
        samples  = list(self._history.get(person, []))
        now      = time.time()
        recent   = [s.emotion for s in samples if now - s.timestamp < window_sec]
        if not recent:
            return "neutral"
        return max(set(recent), key=recent.count)

    def record_text(self, person: str, text: str):
        low = text.lower()
        if any(k in low for k in _CRISIS_KEYWORDS):
            self.record_emotion(person, "fear", intensity=1.0)
            log.warning(f"[Emotion] CRISIS keywords from {person}")
        elif any(k in low for k in _SUPPORT_KEYWORDS):
            self.record_emotion(person, "sad", intensity=0.8)

    def is_in_support_mode(self, person: str) -> bool:
        return self._support_mode.get(person, False)

    def is_recovering(self, person: str) -> bool:
        samples = list(self._history.get(person, []))
        if len(samples) < 4:
            return False
        
        older = samples[:-2]
        recent = samples[-2:]
        old_score = sum(_DISTRESS_WEIGHTS.get(s.emotion, 0) for s in older) / len(older)
        new_score = sum(_DISTRESS_WEIGHTS.get(s.emotion, 0) for s in recent) / len(recent)

        return old_score > 0.4 and new_score < 0.15

    def exit_support_mode(self, person: str):
        self._support_mode[person] = False
        log.info(f"[Emotion] Support mode OFF for {person}")

    def support_turns(self, person: str) -> int:
        return self._turn_counts.get(person, 0)

    def should_checkin(self, person: str) -> bool:
        distress = self.get_distress_level(person)
        if distress == DistressLevel.NONE:
            return False
        if self._support_mode.get(person, False):
            return False # Already in support mode
        
        now = time.time()
        last = self._last_checkin.get(person, 0)
        if now - last < self.CHECKIN_COOLDOWN:
            return False
        
        # Check duration of sustained negative emotion
        samples = list(self._history.get(person, []))
        if not samples:
            return False
        
        neg = [s for s in samples if _DISTRESS_WEIGHTS.get(e.emotion, 0) > 0]
        if not neg:
            return False
        
        duration = now - neg[0].timestamp

        return duration >= self.CHECKIN_AFTER

    def get_support_prompt_injection(
            self,
            person: str,
            nickname: str,
            distress: DistressLevel,
            turn: int,
            relation: str = "friend",
    ) -> str:
        pass