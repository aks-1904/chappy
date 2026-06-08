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