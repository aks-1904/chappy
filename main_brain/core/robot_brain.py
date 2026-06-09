from enum import Enum, auto
from typing import Optional
import logging
import threading

from core.serial_bridge import SerialBridge
from modules.vision import VisionModule
from modules.speech import SpeechModule

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

        self._running: bool = False
        self._state: RobotState = RobotState.IDLE
        self._state_lock: threading.Lock = threading.Lock()

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

    def _main_loop(self):
        pass # To be implemented later