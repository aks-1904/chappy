import serial
import serial.tools.list_ports
import time
import logging
from typing import Optional
import queue
from typing import Callable
import json
import threading

from config.settings import SERIAL

log = logging.getLogger(__name__)

class SerialBridge:

    def __init__(self):
        self._port: Optional[serial.Serial] = None
        self._connected: bool = False
        self._event_queue: queue.Queue  = queue.Queue(maxsize=64)
        self._gesture_callbacks: dict[str, Callable] = {}
        self._lock: threading.Lock = threading.Lock()

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

            self._start_reader()

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

    def thinking_start(self):
        self.send("thinking_start")

    def thinking_stop(self):
        self.send("thinking_stop")

    def speaking_start(self):
        self.send("speaking_start")
    
    def speaking_stop(self):
        self.send("speaking_stop")
    
    def neutral(self):
        self.send("neutral")

    def comfort_pat(self,  on_done: Optional[Callable] = None): 
        self.gesture("comfort_pat", on_done)
    
    def send(self, cmd: str, payload: Optional[dict] = None) -> bool:
        if not self._connected:
            log.warning("[Serial] Not connected - command dropped")
            return False
        
        msg = {"cmd": cmd}
        if payload:
            msg.update(payload)

        line = json.dumps(msg) + "\n"
        with self._lock:
            try:
                self._port.write(line.encode("utf-8"))
                return True
            except serial.SerialException as e:
                log.error(f"[Serial] Write failed: {e}")
                self._connected = False
                return False
            

    def gesture(self, name: str, on_done: Optional[Callable] = None):
        cmd = f"gesture_{name}"
        if on_done:
            self._gesture_callbacks[name] = on_done
        self.send(cmd)

    def poll_event(self) -> Optional[dict]:
        try:
            return self._event_queue.get_nowait()
        except queue.Empty:
            return None