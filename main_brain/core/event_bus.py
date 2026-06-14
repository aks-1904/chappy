"""
EventBus — Thread-safe publish/subscribe bus between RobotBrain and any
observer (terminal output, logging, future tooling, etc.).

RobotBrain and its modules run in background threads and post events here
at any time. Whatever is watching — e.g. the headless runner in run.py —
polls these events and decides what to do with them: print to the
terminal, log to a file, forward over a socket, etc. The bus itself has
no opinion about the consumer.

Event types (all carry a dict payload):
  state_change      {"state": "THINKING", "prev": "LISTENING"}
  speech_out        {"text": "...", "emotion": "happy"}
  speech_in         {"text": "...", "person": "Alice"}
  gesture           {"name": "hug_waist", "person": "Alice"}
  tool_call         {"tool": "web_search", "args": {...}, "result": "..."}
  emotion_detected  {"person": "Alice", "emotion": "sad", "intensity": 0.7}
  face_detected     {"names": ["Alice"], "count": 1}
  sensor_update     {"dist_cm": 45, "pir": True, "touch": False}
  persona_update    {"field": "name", "value": "Nova"}
  reminder_fired    {"person": "Alice", "text": "Take medicine"}
  distress_update   {"person": "Alice", "level": "HIGH"}
  system_log        {"msg": "...", "level": "INFO"}
  arduino_status    {"connected": True}
"""
import queue
import threading
import time
from typing import Optional

_MAXSIZE = 512   # drop oldest events if queue fills up

class EventBus:
    """Singleton event bus. Brain posts; any consumer polls."""

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._queue = queue.Queue(maxsize=_MAXSIZE)
        return cls._instance

    # Posting (brain side, any thread) 
    def post(self, event_type: str, payload: dict = None):
        """Non-blocking post. Drops oldest if full."""
        event = {
            "type":      event_type,
            "payload":   payload or {},
            "timestamp": time.time(),
        }
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()   # drop oldest
            except queue.Empty:
                pass
            self._queue.put_nowait(event)

    # ── Polling (consumer side)
    def poll(self) -> Optional[dict]:
        """Non-blocking poll. Returns None if empty."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def poll_all(self, max_per_tick: int = 20) -> list[dict]:
        """Drain up to N events per tick."""
        events = []
        for _ in range(max_per_tick):
            e = self.poll()
            if e is None:
                break
            events.append(e)
        return events


# Module-level singleton
bus = EventBus()