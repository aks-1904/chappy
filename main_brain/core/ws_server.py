import logging
import queue
import threading
import websockets
from websockets.server import WebSocketServerProtocol
from typing import Optional, Callable
import asyncio
import base64
import json
import numpy as np
import cv2

def _put_nowait(q: queue.Queue, item):
    try:
        q.put_nowait(item)
    except queue.Full:
        q.get_nowait()   # drop oldest
        q.put_nowait(item)

from config.settings import WIRELESS

log = logging.getLogger(__name__)

class WebSocketServer:
    def __init__(self):
        self._host = "0.0.0.0"
        self._port = WIRELESS.get("ws_port", 8765)
        self._path = WIRELESS.get("ws_path", "/robot")

        # Thread-safe queues (brain ↔ server)
        self.sensor_queue: queue.Queue  = queue.Queue(maxsize=64)
        self.audio_queue:  queue.Queue  = queue.Queue(maxsize=32)
        self.frame_queue:  queue.Queue  = queue.Queue(maxsize=4)
        self.event_queue:  queue.Queue  = queue.Queue(maxsize=64)
        self.cmd_queue:    queue.Queue  = queue.Queue(maxsize=128)

        self._loop:      Optional[asyncio.AbstractEventLoop] = None
        self._thread:    Optional[threading.Thread]          = None
        self._ws_client: Optional[WebSocketServerProtocol]   = None
        self._connected: bool = False
        self._stop_event = threading.Event()

        # Callbacks
        self.on_connected:    Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"[WS] Server loop error: {e}")
        finally:
            self._loop.close()

    def start(self):
        self._thread = threading.Thread(
            target=self._run_loop,
            name="WSServerThread",
            daemon=True
        )
        self._thread.start()
        log.info(f"[WS] Server starting on ws://{self._host}:{self._port}{self._path}")

    def stop(self):
        self._stop_event.set()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        log.info("[WS] Server stopped")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"[WS] Server loop error: {e}")
        finally:
            self._loop.close()

    async def _serve(self):
        async with websockets.serve(
            self._handler,
            self._host,
            self._port,
            max_size=2 * 1024 * 1024,   # 2MB max message (JPEG + b64 overhead)
            ping_interval=20,
            ping_timeout=10,
        ):
            log.info(f"[WS] Listening on ws://0.0.0.0:{self._port}{self._path}")
            # Run until stop_event
            while not self._stop_event.is_set():
                # Drain command queue -> send to ESP32
                await self._flush_cmd_queue()
                await asyncio.sleep(0.02)

    async def _handler(self, ws: "WebSocketServerProtocol", path: str):
        self._ws_client = ws
        self._connected = True
        log.info(f"[WS] ESP32 connected from {ws.remote_address}")
        if self.on_connected:
            self.on_connected()

        try:
            async for raw in ws:
                await self._route(raw)
        except websockets.exceptions.ConnectionClosed as e:
            log.warning(f"[WS] ESP32 disconnected: {e}")
        finally:
            self._ws_client = None
            self._connected = False
            if self.on_disconnected:
                self.on_disconnected()

    async def _route(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.debug(f"[WS] Non-JSON: {raw[:60]}")
            return

        t = msg.get("type", "")

        if t == "sensors":
            _put_nowait(self.sensor_queue, msg)

        elif t == "audio":
            _put_nowait(self.audio_queue, msg)

        elif t == "frame":
            _put_nowait(self.frame_queue, msg)

        elif t == "event":
            _put_nowait(self.event_queue, msg)

        elif t == "ready":
            log.info("[WS] ESP32 says ready")
            _put_nowait(self.event_queue, msg)

        elif t == "pong":
            pass # heartbeat

        else:
            log.debug(f"[WS] Unknown message type: {t}")

    async def _flush_cmd_queue(self):
        """Send all pending commands to ESP32."""
        if not self._ws_client:
            return
        while True:
            try:
                cmd_str = self.cmd_queue.get_nowait()
                await self._ws_client.send(cmd_str)
            except queue.Empty:
                break
            except Exception as e:
                log.error(f"[WS] Send error: {e}")
                break

    def send_cmd(self, cmd: str, payload: Optional[dict] = None) -> bool:
        if not self._connected:
            log.debug(f"[WS] Not connected — cmd dropped: {cmd}")
            return False
        msg = {"cmd": cmd}
        if payload:
            msg.update(payload)
        json_str = json.dumps(msg)
        _put_nowait(self.cmd_queue, json_str)
        return True

    def send_audio_to_esp32(self, pcm_bytes: bytes, sample_rate: int = 16000):
        CHUNK = 8192 # bytes per chunk (~256ms at 16kHz mono int16)
        for i in range(0, len(pcm_bytes), CHUNK):
            chunk = pcm_bytes[i:i + CHUNK]
            b64   = base64.b64encode(chunk).decode("ascii")
            self.send_cmd("audio_play", {"data": b64, "sr": sample_rate})

    def poll_audio_pcm(self) -> Optional[np.ndarray]:
        try:
            msg = self.audio_queue.get_nowait()
        except queue.Empty:
            return None
        b64 = msg.get("data", "")
        if not b64:
            return None
        raw = base64.b64decode(b64)
        return np.frombuffer(raw, dtype=np.int16)
    
    def poll_frame_jpeg(self) -> Optional[np.ndarray]:
        try:
            msg = self.frame_queue.get_nowait()
        except queue.Empty:
            return None
        b64 = msg.get("data", "")
        if not b64:
            return None
        try:
            raw  = base64.b64decode(b64)
            arr  = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            log.debug(f"[WS] Frame decode error: {e}")
            return None

    @property
    def connected(self) -> bool:
        return self._connected
