from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# For Logging
LOG = {
    "level": "INFO", # DEBUG | INFO | WARNING | ERROR
    "to_file": True,
    "log_dir": str(BASE_DIR / "logs")
}

SERIAL = {
    "port": "/dev/ttyUSB0", # Windows: "COM3", Linux/Mac: "/dev/ttyUSB0"
    "baud": 115200,
    "timeout": 2, # In Seconds
    "reconnect_delay": 3, # Time between reconnect attempts (Seconds)
}

VISION = {
    "camera_index": 0,
    "frame_width": 640,
    "frame_height": 480,
    "fps": 20,
    "face_detection_every": 3, # process every Nth frame (performance)
    "emotion_detection_every": 10,
    "face_db_path": str[BASE_DIR / "data" / "faces"],
    "unknown_label": "Stranger",
    "min_face_confidence": 0.70
}

AUDIO = {
    # Speech to text(whisper)
    "whisper_model": "base", # tiny | base | small | medium | large
    "tts_voice_index": 0, # 0 = first available voice
    "tts_rate": 165, # Words per minute
    "ts_volume": 0.95,
}

MEMORY = {
    "db_path": str(BASE_DIR / "data" / "memory.db"),
}

PROXIMITY = {
    "greet_distance":   80,    # Start greeting when person is within 80cm
    "handshake_dist":   40,    # Offer handshake when within 40cm
    "too_close":        15,    # Back-off warning
}