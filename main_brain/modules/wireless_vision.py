import logging
import threading
import time

from modules.vision import VisionModule
from modules.vision import Perception
from config.settings import VISION

log = logging.getLogger(__name__)

# How long to wait for a wireless frame before flagging no-signal (seconds)
WIRELESS_TIMEOUT = 5.0

class WirelessVisionModule(VisionModule):

    def __init__(self, wireless_bridge=None):
        super().__init__()
        self._wireless = wireless_bridge
        self._last_frame_ts = 0.0
        self._no_signal = True

    def start(self) -> bool:
        if self._wireless is None:
            log.warning("[WirelessVision] No bridge — falling back to USB camera")
            return super().start()
        
        self._running = True
        self._thread = threading.Thread(
            target=self._wireless_capture_loop,
            name="WirelessVisionThread",
            daemon=True,
        )
        self._thread.start()
        log.info("[WirelessVision] Started (ESP32 camera mode)")
        return True
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        
        # Don't release cap - there is none
        log.info("[WirelessVision] Stopped")

    def _wireless_capture_loop(self):
        while self._running:
            if not self._wireless:
                time.sleep(0.1)

            frame = self._wireless.poll_frame()
            if frame is None:
                # No frame yet - check timeout
                if(
                    time.time() - self._last_frame_ts > WIRELESS_TIMEOUT
                    and self._last_frame_ts > 0
                ):
                    if not self._no_signal:
                        log.warning("[WirelessVision] No frames - ESP32 camera signal lost")
                        self._no_signal = True
                time.sleep(0.02)
                continue
            
            self._no_signal = False
            self._last_frame_ts = time.time()
            self._frame_count += 1

            # Store frame
            with self._lock:
                self.latest_frame = frame.copy()

            # Run analysis - identical to parent _capture_loop
            perception = Perception(timestamp=time.time())

            if self._frame_count % VISION["face_detection_every"] == 0:
                faces = self._detect_faces(frame)

                if self._frame_count % (VISION["face_detection_every"] * 2) == 0:
                    faces = self._recognize_faces(frame, faces)

                if(self._frame_count % VISION["emotion_detection_every"] == 0 and len(faces) > 0):
                    faces = self._detect_emotions(frame, faces)
                
                perception.faces = faces
                perception.face_count = len(faces)
                perception.known_names = [
                    f["name"] for f in faces if f["name"] != VISION["unknown_label"]
                ]
                emotions = [f.get("emotion", "neutral") for f in faces]
                if emotions:
                    perception.dominant_emotion = max(
                        set(emotions), key=emotions.count
                    )

            with self._lock:
                self.latest_perception = perception

    @property
    def has_signal(self) -> bool:
        return not self._no_signal

# Auto-Fallback if no frames after WIRELESS_TIMEOUT    
class AutoVisionModule(WirelessVisionModule):
    def _wireless_capture_loop(self):
        # Run wireless loop for a while
        super()._wireless_capture_loop()

    def start(self) -> bool:
        ok = super().start()

        # Spawn fallback watcher
        threading.Thread(
            target=self._fallback_watcher,
            daemon=True,
            name="VisionFallbackWatcher",
        ).start()
        return ok

    def _fallback_watcher(self):
        time.sleep(WIRELESS_TIMEOUT + 1)
        if self._no_signal or self._last_frame_ts == 0:
            log.info("[AutoVision] No wireless frames - opening USB camera as fallback")

            # Stop wireless thread
            self._running = False
            if self._thread:
                self._thread.join(timeout=2)

            # Start USB camera instead
            self._wireless = None
            VisionModule.start(self)