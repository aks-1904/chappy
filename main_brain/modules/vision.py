import logging
from typing import Optional
import cv2
import threading

from config.settings import VISION

log = logging.getLogger(__name__)

class VisionModule:
    def __init__(self):
        self._cap: Optional[cv2.VideoCampute] = None
        self._running: bool = False
        self._thread:  Optional[threading.Thread] = None

    def start(self) -> bool:
        idx = VISION["camera_index"]
        self._cap = cv2.VideoCapture(idx)

        if not self._cap.isOpened():
            log.error(f"[Vision] Cannot open camera {idx}")
            return False
        
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, VISION["frame_width"])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VISION["frame_height"])
        self._cap.set(cv2.CAP_PROP_FPS, VISION["fps"])
        
        log.info(f"[Vision] Camera {idx} started")
        
        return True
    
    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()

        log.info("[Vision] camera stopped")
