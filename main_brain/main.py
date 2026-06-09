import sys
import time
from pathlib import Path
import logging
import argparse

from utils.logger import setup_logging
from core.serial_bridge import SerialBridge
from core.robot_brain import RobotBrain

# Allow imports from main_brain/ directory
sys.path.insert(0, str(Path(__file__).parent))

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CHAPPY - Laptop Controller")

    p.add_argument( # Check for Arduino PORT e.g. COM3 (Windows), /dev/ttyUSB0 (Linux/Mac)
        "--port",
        default=None,
        help="Arduino serial port (e.g. COM3 or /dev/ttyUSB0). Auto detect if leaved",
    )
    p.add_argument( # Check for if Arduino is connected
        "--no-arduino",
        action="store_true",
        help="Run without Arduino (software-only mode)"
    )
    p.add_argument( # To register new faces
        "--register",
        metavar="NAME",
        default=None,
        help="Register a new face. The robot will camput from camera"
    )
    p.add_argument( # List all serial ports
        "--list-ports",
        action="store_true",
        help="List available serial ports and exit",
    )

    return p.parse_args()


def main():
    setup_logging()

    log = logging.getLogger("main")
    
    args = parse_args()

    # List ports
    if args.list_ports:
        ports = SerialBridge.list_ports()
        print("Available serial ports: ")
        
        for p in ports:
            print(f"\t{p}")
        sys.exit(0)

    robotBrain = RobotBrain()

    port = None if args.no_arduino else args.port
    robotBrain.start(serial_port=port) # Starting the robot brain

    if args.register:
        name = args.register.strip()
        log.info(f"Face registration mode for '{name}")
        log.info("Look at the camera. Press ENTER to campure.")
        input()

        frame = robotBrain.vision.get_frame()
        if frame is not None:
            res = robotBrain.vision.register_face(name, frame)
            if res:
                robotBrain.memory.upsert_user(name)
                print(f"Face registered for '{name}'")
            else:
                print(f"No face detected. Try again")
        
        else:
            print("Camera not available")
        
        robotBrain.stop()
        sys.exit(0)

    print("\n" + "-" * 50)
    print("Chappy Robot - Running")
    print("Press Ctrl + C to stop")
    print("\n" + "-" * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting Down...\n\n")
    finally:
        robotBrain.stop()
        print("Stopping the system...")

if __name__ == "__main__":
    main()