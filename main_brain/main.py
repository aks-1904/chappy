import argparse
import sys
import time
from pathlib import Path
import logging

from utils.logger import setup_logging
from core.serial_bridge import SerialBridge
from core.robot_brain import RobotBrain
from core.wireless_bridge import WirelessBridge
from modules.wireless_vision import AutoVisionModule
from modules.wireless_speech import WirelessSpeechModule
from config.settings import WIRELESS

log = logging.getLogger("main")

sys.path.insert(0, str(Path(__file__).parent))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Companion Robot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  register -> Register a face into the robot's memory
  arduino -> Run the robot using Arduino over USB   (hardware required)
  esp32 -> Run the robot using ESP32 over WiFi    (hardware required)

examples:
  python main.py --register Alice
  python main.py --port /dev/ttyUSB0
  python main.py --wireless
        """
    )

    parser.add_argument("--register", metavar="NAME", default=None, help="Register a face for NAME and exit")
    parser.add_argument("--port", default=None, help="Force serial Arduino port (COM3, /dev/ttyUSB0)")
    parser.add_argument("--wireless", action="store_true", help="Force wireless ESP32 mode")
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit")

    return parser.parse_args()

def detect_mode(args) -> tuple[str, str | None]:
    if args.wireless or WIRELESS.get("enabled", False):
        return "wireless", None
    if args.port:
        return "serial", args.port
    
    # Auto-scan for Arduino
    ports = SerialBridge.list_ports()
    for p in ports:
        low = p.lower()
        if any(k in low for k in ["ttyusb", "ttyacm", "ch340", "cp210", "arduino"]):
            log.info(f"Arduino found on {p}")
            return "serial", p
        
    # Default to wireless if enabled in settings
    if WIRELESS.get("enabled", True):
        return "wireless", None

    print("Specify to run with arduino or ESP32 or connect arduino for auto-detection")

    sys.exit(1)

    return "nothing", None

def build_brain(mode: str, port: str | None) -> tuple[RobotBrain | None, str]:
    brain = RobotBrain()

    if mode == "wireless":
        wb = WirelessBridge()
        wb.start_event_router()

        # Replace default modules with wireless versions
        brain.serial = wb
        brain.vision = AutoVisionModule(wireless_bridge=wb)
        brain.speech = WirelessSpeechModule(wireless_bridge=wb)
        brain._wireless_bridge = wb

        log.info(f"[Main] Wireless mode - starting WS server on port {WIRELESS['ws_port']}")
        brain.start(serial_port=None) # serial_port ignored in wireless mode

        # Wait for ESP32 to connect
        timeout = WIRELESS.get("connect_timeout", 15)
        deadline = time.time() + timeout
        log.info(f"[Main] Waiting up to {timeout}s for ESP32 to connect...")

        while not wb.connected and time.time() < deadline:
            time.sleep(0.3)

        if wb.connected:
            log.info("[Main] ESP32 connected!")
            return brain, "wireless"
        else:
            log.warning("[Main] ESP32 not connected — will connect when available")
            return brain, "wireless_waiting"
        
    elif mode == "serial":
        brain.start(serial_port=port)
        if brain.serial.connected:
            return brain, "serial"
        log.warning("[Main] Arduino serial failed — switching to simulation")

        return brain, "simulation"
    else:
        sys.exit(1)
        return None, ""

def _register_face(brain: RobotBrain, name: str):
    print(f"\nLook at camera for '{name}'. Press ENTER to capture...")
    input()
    frame = brain.vision.get_frame()
    
    if frame is not None:
        ok = brain.vision.register_face(name, frame)
        print(f"{'Registered' if ok else 'No face detected'} for {'{name'}'")    
    else:
        print("Camera not available")

if __name__ == "__main__":
    setup_logging()
    args = parse_args()

    if args.list_ports:
        ports = SerialBridge.list_ports()
        print("Available serial ports: ")
        
        for p in (ports or ["(none found)"]):
            print(f"\t{p}")
        sys.exit(0)

    mode, port = detect_mode(args)
    log.info(f"[Main] Detected mode: {mode}")

    brain, actual_mode = build_brain(mode, port)

    if args.register:
        _register_face(brain, args.register)
        brain.stop()
        sys.exit(0)

    