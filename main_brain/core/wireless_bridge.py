import logging
import threading
import queue
import time
from typing import Callable, Optional
import numpy as np

from core.ws_server import WebSocketServer

log = logging.getLogger(__name__)

def _put_nowait(q: queue.Queue, item):
    try:
        q.put_nowait(item)
    except queue.Full:
        try: 
            q.get_nowait()
        except queue.Empty: 
            pass
        q.put_nowait(item)

class WirelessBridge:
    def __init__(self):
        self._server = WebSocketServer()
        self._event_queue: queue.Queue = queue.Queue(maxsize=128)
        self._gesture_callbacks: dict[str, Callable] = {}
        self._lock = threading.Lock()

        # Wire server callbacks
        self._server.on_connected    = self._on_esp32_connected
        self._server.on_disconnected = self._on_esp32_disconnected

    def connect(self, *args, **kwargs) -> bool:
        self._server.start()

        # Wait upto 10s for ESP32 to connect
        deadline = time.time() + 10
        while not self._server.connected and time.time() < deadline:
            time.sleep(0.2)
        if self._server.connected:
            log.info("[Wireless] ESP32 connected")
            return True
        
        log.info("[Wireless] ESP32 not yet connected — will connect when available")
        # Return True anyway - server is running and will accept connection
        return True

    
    def disconnect(self):
        self._server.stop()
        log.info("[Wireless] Server stopped")
        
    def _on_esp32_connected(self):
        log.info("[Wireless] ESP32 joined")
        bus.post("arduino_status", {"connected": True, "mode": "wireless"})
        # Drain queues left from previous session
        while not self._event_queue.empty():
            try: 
                self._event_queue.get_nowait()
            except queue.Empty: 
                break

    def _on_esp32_disconnected(self):
        log.warning("[Wireless] ESP32 dropped")

    def poll_event(self) -> Optional[dict]:
        # Check internal event queue first
        try:
            return self._event_queue.get_nowait()
        except queue.Empty:
            pass

        # Check sensor queue
        try:
            msg = self._server.sensor_queue.get_nowait()
            return {"event": "sensors", "data": {
                "dist_cm": msg.get("dist_cm", 999),
                "pir":     msg.get("pir",  False),
                "touch":   msg.get("touch", False),
            }}
        except queue.Empty:
            pass

        # Check ESP32 event queue
        try:
            msg = self._server.event_queue.get_nowait()
            evt = msg.get("event", msg.get("type", ""))
            return {"event": evt, "data": msg.get("data", {})}
        except queue.Empty:
            pass

        return None
    
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

    def gesture(self, name: str, on_done: Optional[Callable] = None):
        cmd = f"gesture_{name}"
        if on_done:
            self._gesture_callbacks[name] = on_done
        self.send(cmd)

    def hug_leg(self,     on_done: Optional[Callable] = None): 
        self.gesture("hug_leg",     on_done)
    def hug_waist(self,   on_done: Optional[Callable] = None): 
        self.gesture("hug_waist",   on_done)
    def hug_reach(self,   on_done: Optional[Callable] = None): 
        self.gesture("hug_reach",   on_done)
    def comfort_pat(self, on_done: Optional[Callable] = None): 
        self.gesture("comfort_pat", on_done)
    
    def poll_audio_pcm(self) -> Optional[np.ndarray]:
        """Get one audio chunk from ESP32 mic. Returns int16 numpy array."""
        return self._server.poll_audio_pcm()

    def send_tts_audio(self, pcm_bytes: bytes, sample_rate: int = 16000):
        if not self.connected:
            log.warning("[Wireless] Not connected - audio not sent to speaker")
            return
        self._server.send_audio_to_esp32(pcm_bytes, sample_rate)
        log.debug(f"[Wireless] Sent {len(pcm_bytes)} PCM bytes to ESP32 speaker")

    def poll_frame(self) -> Optional[np.ndarray]:
        return self._server.poll_frame_jpeg()

    def send(self, cmd: str, payload: Optional[dict] = None) -> bool:
        return self._server.send_cmd(cmd, payload)

    def _process_esp32_events(self):
        while True:
            try:
                msg = self._server.event_queue.get_nowait()
                event = msg.get("event", "")
                data = msg.get("data", {})

                if event == "gesture_done":
                    gesture_name = data.get("gesture", "")
                    cb = self._gesture_callbacks.pop(gesture_name, None)
                    if cb:
                        cb()

                # Forward all events to main event queue
                _put_nowait(self._event_queue, {"event": event, "data": data})
            
            except queue.Empty:
                time.sleep(0.02)
            except Exception as e:
                log.debug(f"[Wireless] Event routing error: {e}")
                time.sleep(0.05)

    def start_event_router(self):
        t = threading.Thread(
            target=self._process_esp32_events,
            name="WirelessEventRouter",
            daemon=True,
        )
        t.start()

    @property
    def connected(self) -> bool:
        return self._server.connected