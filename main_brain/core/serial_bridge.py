import serial
import serial.tools.list_ports
import time
import logging
from typing import Optional
import queue

from config.settings import SERIAL

log = logging.getLogger(__name__)

class SerialBridge:

    def __init__(self):
        self._port: Optional[serial.Serial] = None
        self._connected: bool = False
        self._event_queue: queue.Queue  = queue.Queue(maxsize=64)

    @staticmethod
    def list_ports() -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]
    
    def connect(self, port: Optional[str] = None) -> bool:
        port = port or SERIAL["port"]
        try:
            self._port = serial.Serial(
                port=port,
                baudrate=SERIAL["baud"],
                timeout=SERIAL["timeout"],
            )
            time.sleep(2) # Arduino resets on serial open
            self._connected = True
            log.info(f"[Serial] Connected on {port}")

            # Call function to start reading serial data (Implement later)

            return True
        except serial.SerialException as e:
            log.error(f"[Serial] Connect failed on {port}: {e}")
            self._connected = False
            
            return False
        
    def disconnect(self):
        if self._port and self._port.is_open:
            self._port.close()
        self._connected = False
        
        log.info("[Serial] Disconnected")

    def poll_event(self) -> Optional[dict]:
        try:
            return self._event_queue.get_nowait()
        except queue.Empty:
            return None