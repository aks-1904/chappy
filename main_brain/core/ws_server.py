import logging
import queue

from config.settings import WIRELESS

log = logging.getLogger(__name__)

class WebSocketServer:
    def __init__(self):
        self._host = "0.0.0.0"
        self._port = WIRELESS.get("ws_port", 8765)
        self._path = WIRELESS.get("ws_path", "/robot")
        self._connected: bool = False

        self.event_queue: queue.Queue = queue.Queue(maxsize=64)

    @property
    def connected(self) -> bool:
        return self._connected
