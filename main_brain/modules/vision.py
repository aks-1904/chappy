import logging
from typing import Optional
import cv2
import threading
import time
import numpy as np
from dataclasses import dataclass, field

from config.settings import VISION

log = logging.getLogger(__name__)

@dataclass
class Perception:
    """Snapshot of the latest vision analysis."""
    faces: list[dict] = field(default_factory=list)
    # Each face: {"name": str, "emotion": str, "bbox": (x,y,w,h), "confidence": float}
    face_count: int = 0
    known_names: list[str] = field(default_factory=list)
    dominant_emotion: str = "neutral"
    timestamp: float = 0.0
# 

class VisionModule:
    def __init__(self):
        self._cap: Optional[cv2.VideoCampute] = None
        self._running: bool = False
        self._thread:  Optional[threading.Thread] = None
        self._frame_count: int = 0
        self._lock: threading.Lock = threading.Lock()
        self.latest_frame:      Optional[np.ndarray] = None
        self.latest_perception: Perception = Perception()

    def start(self) -> bool:
        idx = VISION["camera_index"]
        self._cap = cv2.VideoCapture(idx)

        if not self._cap.isOpened():
            log.error(f"[Vision] Cannot open camera {idx}")
            return False
        
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, VISION["frame_width"])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VISION["frame_height"])
        self._cap.set(cv2.CAP_PROP_FPS, VISION["fps"])
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="Vision Thread",
            daemon=True
        )
        self._thread.start()
        
        log.info(f"[Vision] Camera {idx} started")
        
        return True
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()

        log.info("[Vision] camera stopped")

    def _capture_loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                log.warning("[Vision] Frame grab failed")
                time.sleep(0.1)
                continue

            self._frame_count += 1

            # Store raw frame
            with self._lock:
                self.latest_frame = frame.copy()

            # Run face detection every N frames
            perception = Perception(timestamp=time.time())

            if self._frame_count % VISION["face_detection_every"] == 0:
                pass # Detect face every (To be implement later)

            with self._lock:
                self.latest_perception = perception
