import argparse
import sys
import time
import threading
from pathlib import Path
import cv2
import mediapipe as mp

from utils.logger import setup_logging
from core.serial_bridge import SerialBridge
from core.robot_brain import RobotBrain
from core.wireless_bridge import WirelessBridge
from modules.wireless_vision import AutoVisionModule
from modules.wireless_speech import WirelessSpeechModule
from core.event_bus import bus
from config.settings import WIRELESS, VISION

sys.path.insert(0, str(Path(__file__).parent))

def parse_args():
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Companion Robot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  register    Register a face into the robot's memory
  arduino     Run the robot using Arduino over USB   (hardware required)
  esp32       Run the robot using ESP32 over WiFi    (hardware required)

examples:
  python run.py register --name Alice
  python run.py arduino
  python run.py arduino --port COM3
  python run.py esp32
        """
    )

    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    # register
    reg = sub.add_parser("register", help="Register a face")
    reg.add_argument("--name", required=True, metavar="NAME", help="Name of the person to register")
    reg.add_argument("--photos", type=int, default=3, metavar="N", help="Number of photos to capture (default: 3)")
    reg.add_argument("--wireless", action="store_true", help="Use ESP32 camera instead of USB webcam")

    # arduino
    ard = sub.add_parser("arduino", help="Run with Arduino via USB (hardware required)")
    ard.add_argument("--port", default=None, metavar="PORT", help="Serial port, e.g. COM3 or /dev/ttyUSB0 (auto-detect if omitted)")

    # esp32
    esp = sub.add_parser("esp32", help="Run with ESP32 via WiFi (hardware required)")

    return parser.parse_args()

def cmd_register(name: str, photos: int, wireless: bool):
    name = name.strip().title()
    print(f"\n  Registering face for: {name}")
    print(f"  Photos to capture  : {photos}")
    print(f"  Camera source      : {'ESP32 WiFi' if wireless else 'USB webcam'}")
    print("-" * 42)
    print(" Controls in preview window:")
    print(" SPACE - capture photo now")
    print(" A - auto-capture in 3 seconds")
    print(" Q - quit")
    print("-" * 42 + "\n")

    # Open camera
    if wireless:
        get_frame = _open_esp32_camera()
    else:
        cap = _open_usb_camera(VISION["camera_index"])
        def get_frame():
            ok, frame = cap.read()
            return frame if ok else None

    # Face detector
    detect = _build_face_detector()

    # Capture loop
    captured = 0
    auto_at = None          # timestamp for auto-capture

    save_dir = Path(VISION["face_db_path"]) / name
    save_dir.mkdir(parents=True, exist_ok=True)

    while captured < photos:
        frame = get_frame()
        if frame is None:
            time.sleep(0.03)
            continue

        bbox = detect(frame)
        display = frame.copy()

        # Green box around face
        if bbox:
            x, y, w, h = bbox
            cv2.rectangle(display, (x, y), (x+w, y+h), (0, 210, 70), 2)

        # Status bar
        bar_text = f" {captured}/{photos} saved   SPACE=capture  A=auto  Q=quit"
        cv2.rectangle(display, (0, 0), (display.shape[1], 38), (20, 20, 20), -1)
        cv2.putText(display, bar_text, (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1)

        # Countdown overlay
        if auto_at is not None:
            left = auto_at - time.time()
            if left <= 0:
                auto_at = None
                if bbox:
                    _save_crop(frame, bbox, save_dir)
                    captured += 1
                    print(f"\tAuto-captured ({captured}/{photos})")
                else:
                    print("\tNo face — skipped")
            else:
                cv2.putText(display, f"  Capturing in {left:.1f}s", (12, display.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        cv2.imshow(f"Register: {name}", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            print("\n Cancelled.")
            break

        elif key == ord(" "):
            if bbox:
                _save_crop(frame, bbox, save_dir)
                captured += 1
                print(f"Captured ({captured}/{photos})")
                # Green flash
                _flash(display, name)
            else:
                print("No face detected — try again")

        elif key == ord("a") and auto_at is None:
            auto_at = time.time() + 3.0
            print("Auto-capturing in 3 seconds...")

    cv2.destroyAllWindows()
    if not wireless:
        cap.release()

    print()
    if captured == photos:
        print(f"Done — {captured} photo(s) saved for '{name}'")
        print(f"]Folder: {save_dir}\n")
    elif captured > 0:
        print(f"Partial — {captured}/{photos} photo(s) saved for '{name}'\n")
    else:
        print(f"Nothing saved for '{name}'\n")


def _open_usb_camera(index: int):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"ERROR: Cannot open USB camera (index {index})")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("[Camera] USB webcam ready")
    return cap


def _open_esp32_camera():
    print("[WiFi] Connecting to ESP32...")
    wb = WirelessBridge()
    wb.connect()

    deadline = time.time() + WIRELESS.get("connect_timeout", 15)
    while not wb.connected and time.time() < deadline:
        time.sleep(0.3)

    if not wb.connected:
        print("ERROR: ESP32 not reachable. Check IP in settings.py")
        sys.exit(1)

    print("[WiFi] ESP32 connected - streaming camera")

    def get_frame():
        for _ in range(30):
            f = wb.poll_frame()
            if f is not None:
                return f
            time.sleep(0.04)
        return None

    return get_frame


def _build_face_detector():
    try:
        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.7
        )
        def detect(frame):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = detector.process(rgb)
            if not res.detections:
                return None
            h, w = frame.shape[:2]
            b    = res.detections[0].location_data.relative_bounding_box
            return (max(0, int(b.xmin*w)), max(0, int(b.ymin*h)),
                    int(b.width*w),        int(b.height*h))
        return detect
    except ImportError:
        pass

    # Haar fallback
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    def detect(frame):
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if len(faces) == 0:
            return None
        return tuple(max(faces, key=lambda f: f[2]*f[3]))
    return detect


def _save_crop(frame, bbox, save_dir: Path):
    x, y, w, h = bbox
    fh, fw = frame.shape[:2]
    px, py = int(w * 0.2), int(h * 0.2)
    crop = frame[max(0,y-py):min(fh,y+h+py), max(0,x-px):min(fw,x+w+px)]
    cv2.imwrite(str(save_dir / f"{int(time.time()*1000)}.jpg"), crop)


def _flash(display, name: str):
    f = display.copy()
    cv2.rectangle(f, (0,0), (f.shape[1], f.shape[0]), (0,230,70), 10)
    cv2.imshow(f"Register: {name}", f)
    cv2.waitKey(220)

def cmd_arduino(port=None):
    setup_logging()

    # Auto-detect port if not given
    if port is None:
        ports = SerialBridge.list_ports()
        for p in ports:
            if any(k in p.lower() for k in ["ttyusb","ttyacm","ch340","cp210","com"]):
                port = p
                break

    if port is None:
        print("\n  ✗ ERROR: No Arduino found on any serial port.")
        print("  This mode requires the Arduino to be physically connected via USB.")
        print("  Plug it in, or specify the port manually:")
        print("    python run.py arduino --port COM3")
        print("    python run.py arduino --port /dev/ttyUSB0\n")
        sys.exit(1)

    print(f"\n  Mode  : Arduino (USB serial)")
    print(f"  Port  : {port}")
    print()

    brain = RobotBrain()
    brain.start(serial_port=port)

    if not brain.serial.connected:
        print(f"\n  ✗ ERROR: Could not establish a connection to the Arduino on '{port}'.")
        print("  Check that the board is plugged in, powered, and not held open")
        print("  by another program (e.g. the Arduino IDE Serial Monitor).\n")
        brain.stop()
        sys.exit(1)

    print("  ✓ Arduino connected!\n")

    _launch(brain, mode="serial")

def cmd_esp32():
    setup_logging()

    print(f"\n  Mode  : ESP32 (WiFi WebSocket)")
    print(f"  Server: ws://0.0.0.0:{WIRELESS['ws_port']}/robot")
    print()

    wb = WirelessBridge()
    wb.start_event_router()

    brain         = RobotBrain()
    brain.serial  = wb
    brain.vision  = AutoVisionModule(wireless_bridge=wb)
    brain.speech  = WirelessSpeechModule(wireless_bridge=wb)
    brain._wireless_bridge = wb

    brain.start(serial_port=None)

    # Wait for ESP32 — required, no software-only fallback
    timeout  = WIRELESS.get("connect_timeout", 15)
    deadline = time.time() + timeout
    print(f"  Waiting up to {timeout}s for ESP32 to connect...")
    while not wb.connected and time.time() < deadline:
        time.sleep(0.3)

    if not wb.connected:
        print(f"\n  ✗ ERROR: No ESP32 connected within {timeout}s.")
        print("  This mode requires the ESP32 hardware to be powered on and")
        print(f"  connected over WiFi to ws://<this-machine-ip>:{WIRELESS['ws_port']}/robot")
        print("  Check the ESP32's WiFi credentials/server address and try again.\n")
        brain.stop()
        sys.exit(1)

    print("  ✓ ESP32 connected!\n")

    _launch(brain, mode="esp32")

def _launch(brain, mode: str):
    _run_headless(brain, mode)


def _run_headless(brain, mode: str):

    print(f"  {'═'*50}")
    print(f"  {brain.persona.persona.name} — {mode.upper()} MODE")
    print(f"  Ctrl+C to stop")
    print(f"  {'═'*50}\n")

    def _print():
        while True:
            for e in bus.poll_all():
                t, p = e["type"], e["payload"]
                if   t == "speech_out":   print(f"🤖  {p.get('text','')}")
                elif t == "speech_in":    print(f"👤  {p.get('text','')}")
                elif t == "state_change": print(f"◌   {p.get('state','')}")
                elif t == "gesture":      print(f"✦   {p.get('name','')}")
                elif t == "tool_call":    print(f"⚙   {p.get('tool','')} → {str(p.get('result',''))[:80]}")
            time.sleep(0.1)

    threading.Thread(target=_print, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
    finally:
        brain.stop()

if __name__ == "__main__":
    args = parse_args()

    if args.command == "register":
        cmd_register(
            name     = args.name,
            photos   = args.photos,
            wireless = args.wireless,
        )

    elif args.command == "arduino":
        cmd_arduino(
            port = args.port,
        )

    elif args.command == "esp32":
        cmd_esp32()