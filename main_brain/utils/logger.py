import logging
import sys
from pathlib import Path
import datetime

from config.settings import LOG

def setup_logging():
    level = getattr(logging, LOG["level".upper(), logging.INFO])
    
    handlers = [logging.StreamHandler(sys.stdout)]

    if(LOG.get("to_file")):
        log_dir = Path(LOG["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)
        
        fname = log_dir / f"robot_{datetime.date.today()}.log"
        handlers.append(logging.FileHandler(fname, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )

    # Ouiet noisy third-party loggers
    for noisy in ("urllib3", "httpx", "httpcode", "PIL", "numba"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("Logger initiated")
