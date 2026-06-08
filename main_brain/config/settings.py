from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# For Logging
LOG = {
    "level": "INFO", # DEBUG | INFO | WARNING | ERROR
    "to_file": True,
    "log_dir": str(BASE_DIR / "logs")
}
