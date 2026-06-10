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
    "whisper_language": "en",
    "mic_device_index": None, # None -> SYstem default
    "vad_threshold": 0.5, # Voice activity Detection energy threshold
    "silence_timeout": 1.5, # seconds of silence before stopping recording
    "max_record_seconds": 15,

    # Text-to-Speech
    "tts_engine": "pyttsx3", # 'pyttsx3' | 'coqui
    "tts_voice_index": 0, # 0 = first available voice
    "tts_rate": 165, # Words per minute
    "ts_volume": 0.95,
    "coqui_model": "tts_models/en/ljspeech/tacotron2-DDC",

    # Speaker
    "output_device": None,
}

MEMORY = {
    "db_path": str(BASE_DIR / "data" / "memory.db"),
    "summary_after": 20, # summarize older interactions after N turns
    "max_history": 200 # max interactions stored per user
}

PROXIMITY = {
    "greet_distance":   80,    # Start greeting when person is within 80cm
    "handshake_dist":   40,    # Offer handshake when within 40cm
    "too_close":        15,    # Back-off warning
}

LLM = {
    "backend": "ollama", # "ollama" | "openai"
    "ollama_host": "http://localhost:11434",
    "model": "phi4-mini", # phi4-mini | llama3.2:3b
    "system_prompt": (
        "You are a friendly home companion robot. "
        "You are warm, helpful, and concise. "
        "You remember people and their preferences. "
        "You adapt your tone based on the user's emotional state. "
        "Keep responses under 3 sentences unless detail is needed. "
        "When you want the robot to perform a gesture, include a tag like "
        "[GESTURE:wave], [GESTURE:happy], [GESTURE:sad], [GESTURE:nod], "
        "[GESTURE:shake], [GESTURE:handshake], [GESTURE:surprised], [GESTURE:point]. "
        "Current context will be provided before each message."
    ),
    "context_messages": 10, # How many past turns to include
    "temperature":       0.75,
    "max_tokens":        512,
    "timeout_seconds":   30,
}

EMOTION_GESTURES = {
    "happy":     "gesture_happy",
    "sad":       "gesture_sad",
    "angry":     "gesture_shake",
    "fear":      "gesture_surprised",
    "surprise":  "gesture_surprised",
    "neutral":   None,
    "disgust":   None,
}