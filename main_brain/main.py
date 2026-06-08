import sys
import time;
from pathlib import Path
import logging

from utils.logger import setup_logging

# Allow imports from main_brain/ directory
sys.path.insert(0, str(Path(__file__).parent))

def main():
    setup_logging()

    log = logging.getLogger("main")

    log.info("Logs check")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting Down...\n\n")
    

if __name__ == "__main__":
    main()
