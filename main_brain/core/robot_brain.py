from enum import Enum, auto
from typing import Optional
import logging
import threading
import time

from core.serial_bridge import SerialBridge
from modules.vision import VisionModule
from modules.speech import SpeechModule
from modules.memory import MemoryModule
from config.settings import PROXIMITY

log = logging.getLogger(__name__)

class RobotState(Enum):
    IDLE = auto()
    GREETING = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    GESTURE_ONLY = auto()

class RobotBrain:
    def __init__(self):
        self.serial = SerialBridge()
        self.vision = VisionModule()
        self.speech = SpeechModule()
        self.memory = MemoryModule()

        self._running: bool = False
        self._state: RobotState = RobotState.IDLE
        self._state_lock: threading.Lock = threading.Lock()

        self._last_sensor: dict = {}

    # State helpers
    def _set_state(self, new_state: RobotState):
        with self._state_lock:
            old = self._state
            self._state = new_state
            log.debug(f"[Robot Brain] State: {old.name} -> {new_state.name}")

    @property
    def state(self) -> RobotState:
        with self._state_lock:
            return self._state

    def start(self, serial_port: Optional[str] = None):
        log.info("[Robot Brain] Initializing")

        # Hardware connecting (optional - robot works without arduino)
        if serial_port:
            connected = self.serial.connect(serial_port)
        else:
            ports = SerialBridge.list_ports()
            connected = self.serial.connect(ports[0]) if ports else False

        if not connected:
            log.warning("[Robot Brain] Arduino not connected")

        self.vision.start()
        self.speech.start()

        self._running = True
        self._main_thread = threading.Thread(
            target=self._main_loop, name="BrainLoop", daemon=True
        )
        self._main_thread.start()

        log.info("[Robot Brain] Running")

    def stop(self):
        self._running = False
        self.vision.stop()
        self.speech.stop()
        self.serial.disconnect()
        
        log.info("[Robot Brain Stopped]")

    def _greet_by_proximity(self):
        pass

    def _offer_handshake(self):
        pass

    def _greet_by_pir(self):
        pass

    def _do_handshake_response(self):
        pass

    def _handle_serial_events(self):
        while True:
            msg = self.serial.poll_event()
            if not msg:
                break

            event = msg.get("event", "")
            data = msg.get("data", {})

            if event == "sensors":
                self._last_sensor = data
                dist = data.get("dist_cm", 999)

                # Someone walked close enough to greet
                if(dict <= PROXIMITY["greet_distance"] and self.state == RobotState.IDLE):
                    threading.Thread(
                        target=self._greet_by_proximity,
                        daemon=True
                    ).start()

                # Very close - offer handshake
                if (
                    dist <= PROXIMITY["handshake_dist"]
                    and self.state in (RobotState.IDLE, RobotState.GREETING)
                ):
                    threading.Thread(
                        target=self._offer_handshake,
                        daemon=True
                    ).start()
            
            elif event == "presence_detected":
                log.info("[Brain] PIR: presence detected")
                if self.state == RobotState.IDLE:
                    threading.Thread(
                        target=self._greet_by_pir,
                        daemon=True
                    ).start()
            
            elif event == "touch_detected":
                log.info("[Brain] Touch sensor activated")
                if self.state in (RobotState.IDLE, RobotState.GREETING):
                    threading.Thread(
                        target=self._do_handshake_response,
                        daemon=True
                    ).start()

            elif event == "error":
                log.warning(f"[Brain] Arduino error: {data}")
    
    def _check_reminders(self):
        pass

    def get_transcription(self):
        pass

    def _conversation_turn(self):
        pass

    def _main_loop(self):
        self.speech.start_listening_thread() # Start listening thread - pushes to SpeechModule queue

        last_reminder_check = 0.0

        while self._running:
            self._handle_serial_events() # Handle incoming Arduino events

            if time.time() - last_reminder_check > 30:
                self._check_reminders()
                last_reminder_check = time.time()

            # Handle spoken input
            if self.state == RobotState.IDLE:
                text = self.speech.get_transcription()

                if text:
                    threading.Thread(
                        target=self._conversation_turn,
                        args=(text,),
                        daemon=True,
                    ).start()
            
            time.sleep(0.05)