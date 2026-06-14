import logging
import threading
import queue
import time
from typing import Callable

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
        self._gesture_callbacks: dict[str, Callable] = {}
        self._server = WebSocketServer()        

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