from enum import Enum, auto
from typing import Optional
import logging

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

        log.info("[Robot Brain] Running")

    def stop(self):
        self._running = False
        self.vision.stop()
        self.speech.stop()
        
        log.info("[Robot Brain Stopped]")