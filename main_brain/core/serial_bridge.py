import serial
import time
import logging
from typing import Optional
import queue
from typing import Callable
import json
import threading
import serial.tools.list_ports

from config.settings import SERIAL

log = logging.getLogger(__name__)

class SerialBridge:

    def __init__(self):
        self._port: Optional[serial.Serial] = None
        self._connected: bool = False
        self._event_queue: queue.Queue  = queue.Queue(maxsize=64)
        self._gesture_callbacks: dict[str, Callable] = {}
        self._lock: threading.Lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connected

    @staticmethod
    def list_ports() -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]
    
    def _start_reader(self):
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="SerialReader",
            daemon=True
        )
        self._reader_thread.start()
    
    def _dispatch(self, msg: dict):
        event = msg.get("event", "")
        data = msg.get("data", {})

        # Put on queue for main-thread consumers
        try:
            self._event_queue.put_nowait(msg)
        except queue.Full:
            self._event_queue.get_nowait() # drop oldest
            self._event_queue.put_nowait(msg)

        # Gesture-done callbacks
        if event == "gesture_done":
            gesture = data.get("gesture", "")
            cb = self._gesture_callbacks.pop(gesture, None)
            if cb:
                cb()

    def _reader_loop(self):
        while not self._stop_event.is_set():
            if not self._port or not self._port.is_open:
                break
            try:
                raw = self._port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._dispatch(msg)
                except json.JSONDecodeError:
                    log.debug(f"[Serial] Non-JSON line: {line}")
            except serial.SerialException as e:
                log.warning(f"[Serial] Read error: {e}")
                self._connected = False
                threading.Thread(
                    target=self._reconnect_loop,
                    daemon=True
                ).start()
                break

    def _reconnect_loop(self):
        delay = SERIAL["reconnect_delay"]
        log.info(f"[Serial] Reconnecting in {delay}s...")
        while not self._stop_event.is_set() and not self._connected:
            time.sleep(delay)
            log.info("[Serial] Attempting reconnect...")
            self.connect()

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
        self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2)
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

    def hug_leg(self, on_done: Optional[Callable] = None):
        self.gesture("hug_leg", on_done)

    def hug_waist(self, on_done: Optional[Callable] = None):
        self.gesture("hug_waist", on_done)

    def hug_reach(self, on_done: Optional[Callable] = None):
        self.gesture("hug_reach", on_done)

    def comfort_pat(self, on_done: Optional[Callable] = None): 
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