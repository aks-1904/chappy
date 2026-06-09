from enum import Enum, auto
from typing import Optional
import logging
import threading
import time

from core.serial_bridge import SerialBridge
from modules.vision import VisionModule, Perception
from modules.speech import SpeechModule
from modules.memory import MemoryModule
from config.settings import PROXIMITY

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
        self.memory = MemoryModule()

        self._running: bool = False
        self._state: RobotState = RobotState.IDLE
        self._state_lock: threading.Lock = threading.Lock()

        self._last_sensor: dict = {}
        self._last_greeted: dict = {} # name -> timestamp
        self._active_user: str = "Guest"

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

    # Vision-Driven Greet + Recognition
    def _greet_by_proximity(self):
        time.sleep(0.5) # letting vision catch up
        perception = self.vision.get_perception()
        name = self._get_active_user_from_perception(perception)
        self._greet_user(name, perception.dominant_emotion)

    def _greet_user(self, name: str, emotion: str = "neutral"):
        now = time.time()
        last = self._last_greeted.get(name, 0)
        if now - last < 60: # Don't re-greet within 60 seconds
            return
        
        self._last_greeted[name] = now
        self._active_user = name

        # Update memory
        self.memory.upsert_user(name)

        # Check if known user
        user = self.memory.get_user(name)
        is_known = user and user.get("preferences", {})

        if name == "Guest":
            greeting = "Hello there! I notices someone nearby. Welcome!"
        else:
            greeting = f"Hello {name}! Great to see you. [GESTURE:wave]"

            if is_known:
                # Adding a personal touch from memory
                last_seen = user.get("last_seen", now)
                hours_ago = (now - last_seen) / 3600

                if hours_ago > 8:
                    greeting = f"Welcome back, {name}! I missed you. [GESTURE:wave]"
        
        self._set_state(RobotState.GREETING)
        self.serial.gesture("wave")
        self._speak(greeting, emotion)
        self._set_state(RobotState.IDLE)

    def _get_active_user_from_perception(self, perception: Perception) -> str:
        if perception.known_names:
            return perception.known_names[0]

        return "Guest"

    def _offer_handshake(self):
        pass

    def _greet_by_pir(self):
        pass

    def _do_handshake_response(self):
        pass

    def _handle_serial_events(self):
        while True:
            msg = self.serial.poll_event()
            if not msg:
                break

            event = msg.get("event", "")
            data = msg.get("data", {})

            if event == "sensors":
                self._last_sensor = data
                dist = data.get("dist_cm", 999)

                # Someone walked close enough to greet
                if(dict <= PROXIMITY["greet_distance"] and self.state == RobotState.IDLE):
                    threading.Thread(
                        target=self._greet_by_proximity,
                        daemon=True
                    ).start()

                # Very close - offer handshake
                if (
                    dist <= PROXIMITY["handshake_dist"]
                    and self.state in (RobotState.IDLE, RobotState.GREETING)
                ):
                    threading.Thread(
                        target=self._offer_handshake,
                        daemon=True
                    ).start()
            
            elif event == "presence_detected":
                log.info("[Brain] PIR: presence detected")
                if self.state == RobotState.IDLE:
                    threading.Thread(
                        target=self._greet_by_pir,
                        daemon=True
                    ).start()
            
            elif event == "touch_detected":
                log.info("[Brain] Touch sensor activated")
                if self.state in (RobotState.IDLE, RobotState.GREETING):
                    threading.Thread(
                        target=self._do_handshake_response,
                        daemon=True
                    ).start()

            elif event == "error":
                log.warning(f"[Brain] Arduino error: {data}")

    def _speak(self, text: str, emotion: str = "neutral"):
        log.info(f"[Robot Brain] Speaking ({emotion}): {text!r}")
        # Robot speaks about reminder (To be implemented later)
    
    def _check_reminders(self):
        reminders = self.memory.get_due_reminders()

        for r in reminders:
            log.info(f"[Robot Brain] Reminder due: {r['text']}")
            self.memory.mark_reminder_done(r['id'])
            user = r['user_name']
            msg = f"Reminder for {user}: {r['text']}"
            self._speak(msg, emotion="neutral")

    def get_transcription(self):
        pass

    def _conversation_turn(self):
        pass

    def _main_loop(self):
        self.speech.start_listening_thread() # Start listening thread - pushes to SpeechModule queue

        last_reminder_check = 0.0

        while self._running:
            self._handle_serial_events() # Handle incoming Arduino events

            if time.time() - last_reminder_check > 30:
                self._check_reminders()
                last_reminder_check = time.time()

            # Handle spoken input
            if self.state == RobotState.IDLE:
                text = self.speech.get_transcription()

                if text:
                    threading.Thread(
                        target=self._conversation_turn,
                        args=(text,),
                        daemon=True,
                    ).start()
            
            time.sleep(0.05)