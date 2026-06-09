import logging
from typing import Optional
import cv2
import threading
import time
import numpy as np
from dataclasses import dataclass, field
import os
from deepface import DeepFace
import mediapipe

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

        self._load_known_faces()
        self._known_faces: dict[str, list] = {}

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

    # Face Recognition
    def _load_known_faces(self):
        db_path = VISION["face_db_path"]
        if not os.path.isdir(db_path):
            os.makedirs(db_path, exist_ok=True)
            return
        
        for name_dir in os.listdir(db_path):
            dir_path = os.path.join(db_path, name_dir)
            if not os.path.isdir(dir_path):
                continue

            embeddings = []
            for img_file in os.listdir(dir_path):
                if not img_file.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue

                img_path = os.path.join(dir_path, img_file)
                try:
                    emb = DeepFace.represent(
                        img_path=img_path,
                        model_name="Facenet",
                        enforce_detection=False,
                    )
                    embeddings.append(emb[0]["embedding"])
                except Exception as e:
                    log.debug(f"[Vision] Embedding failed for {img_path}: {e}")
            if embeddings:
                self._known_faces[name_dir] = embeddings
                log.info(f"[Vision] Loaded {len(embeddings)} faces for '{name_dir}'")

    def register_face(self, name: str, frame: np.ndarray) -> bool:
        perception = self.latest_perception
        if not perception.faces:
            log.warning("[Vision] No face detected to register")
            return False
        
        bbox = perception.faces[0]["bbox"]
        x, y, fw, fh = bbox
        crop = frame[y: y + fh, x: x + fw]
        save_dir = os.path.join(VISION["face_db_path"], name)
        os.makedirs(save_dir, exist_ok=True)

        fname = os.path.join(save_dir, f"{int(time.time())}.jpg")
        cv2.imwrite(fname, crop)
        log.info(f"[Vision] Registerd face for '{name}' -> '{fname}'")

        return True

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

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