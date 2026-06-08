from enum import Enum, auto
from typing import Optional
import logging

from core.serial_bridge import SerialBridge

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

        self._running: bool = False
        self._state: RobotState = RobotState.IDLE

    def start(self, serial_port: Optional[str] = None):
        log.info("Robot Brain Initializing")

        # Hardware connecting (optional - robot works without arduino)
        if serial_port:
            connected = self.serial.connect(serial_port)
        else:
            ports = SerialBridge.list_ports()
            connected = self.serial.connect(ports[0]) if ports else False

        if not connected:
            log.warning("[Brain] Arduino not connected")

        self._running = True

        log.info("Robot Brain Running")

    def stop(self):
        self._running = False
        self.serial.disconnect()
        log.info("Robot Brain Stopped")