from enum import Enum, auto
from typing import Optional
import logging
import threading
import time
import datetime

from core.serial_bridge import SerialBridge
from modules.vision import VisionModule, Perception
from modules.speech import SpeechModule
from modules.memory import MemoryModule
from modules.llm_engine import LLMEngine
from modules.persona import PersonaModule
from config.settings import PROXIMITY, EMOTION_GESTURES, PERSONA

log = logging.getLogger(__name__)

def get_time_of_day() -> str:
    h = datetime.now().hour
    if 5  <= h < 12: return "morning"
    if 12 <= h < 17: return "afternoon"
    if 17 <= h < 21: return "evening"
    return "night"

class RobotState(Enum):
    IDLE = auto()
    GREETING = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    GESTURE_ONLY = auto()
    SUPPORT      = auto() # in emotional support conversation
    GESTURE_ONLY = auto()

class RobotBrain:
    def __init__(self):
        self.serial = SerialBridge()
        self.vision = VisionModule()
        self.speech = SpeechModule()
        self.memory = MemoryModule()
        self.llm = LLMEngine()
        self.persona = PersonaModule()

        self._running: bool = False
        self._state: RobotState = RobotState.IDLE
        self._state_lock: threading.Lock = threading.Lock()

        self._last_sensor: dict = {}
        self._last_greeted: dict = {} # name -> timestamp
        self._active_user: str = "Guest"

        self._last_proactive_check: float = 0.0

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

        cooldown = PERSONA.get("greet_cooldown", 600)
        if now - last < cooldown:
            return
        
        self._last_greeted[name] = now
        self._active_user = name

        # Update memory
        self.memory.upsert_user(name)

        # Record emotion
        emotion = "neutral" # Update with function call (Future Work)

        # Check if known user
        user = self.memory.get_user(name)
        last_ts = user.get("last_seen", now) if user else now
        hours_away = (now - last_ts) / 3600
        tod = get_time_of_day()

        greeting = self.persona.generate_greeting(
            person_name = name,
            emotion = emotion,
            hours_away = hours_away,
            time_of_day = tod
        )
        
        self._set_state(RobotState.GREETING)
        self.serial.gesture("wave")
        self._speak(greeting, emotion)

        if emotion in ("sad", "fear") and name != "Guest":
            time.sleep(0.5)
            self._initiate_support(name, emotion)
        else:
            self._set_state(RobotState.IDLE)

    def _initiate_support(name: str, emotion: str):
        pass

    def _get_active_user_from_perception(self, perception: Perception) -> str:
        if perception.known_names:
            return perception.known_names[0]

        return "Guest"

    def _offer_handshake(self):
        if self.state not in (RobotState.IDLE, RobotState.GREETING):
            return
        
        self._set_state(RobotState.GESTURE_ONLY)

        nickname = self.persona.get_nickname(self._active_user)
        self._speak(f"Want to shake hands, {nickname}", "neutral")
        self.serial.gesture("handshake")
        self._set_state(RobotState.IDLE)

    def _greet_by_pir(self):
        time.sleep(1.0)
        perception = self.vision.get_perception()
        name = self._get_active_user_from_perception(perception)
        self._greet_user(name, perception.dominant_emotion)

    def _handle_touch(self):
        person = self._active_user
        distress = "moderate"

        self._set_state(RobotState.GESTURE_ONLY)
        if distress in ("moderate", "high", "crisis"):
            self.serial.comfort_pat()
            nickname = self.persona.get_nickname(person)
            self._speak(f"I'm right here, {nickname}. You're not alone.", "sad")
        else:
            self.serial.gesture("handshake")
            nickname = self.persona.get_nickname(person)
            self._speak(f"Good to feel you here, {nickname}!", "happy")
        self._set_state(RobotState.IDLE)

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
                        target=self._handle_touch,
                        daemon=True
                    ).start()

            elif event == "error":
                log.warning(f"[Brain] Arduino error: {data}")

    def _speak(self, text: str, emotion: str = "neutral"):
        log.info(f"[Robot Brain] Speaking ({emotion}): {text!r}")
        self.speech.speak(text, emotion=emotion, blocking=True)
    
    def _check_reminders(self):
        reminders = self.memory.get_due_reminders()

        for r in reminders:
            log.info(f"[Robot Brain] Reminder due: {r['text']}")
            self.memory.mark_reminder_done(r['id'])
            user = r['user_name']
            nickname = self.persona.get_nickname(user)
            msg = f"Hey {nickname}, just a reminder: {r['text']}"
            msg = f"Reminder for {user}: {r['text']}"
            self._speak(msg, emotion="neutral")

    def _smart_hug(self, person: str):
        relation = self.persona.get_relation_label(person)
        distress = "high"

        # Children / small people -> leg hug
        if relation in ("son", "daughter", "baby", "child", "cousin"):
            self.serial.hug_leg()

        # Seated or mid-height contact
        elif relation in ("grandfather", "grandmother", "elder"):
            # Elderly often seated -> waist hug
            self.serial.hug_waist()

        # Crisis / reaching up for tall person bending down
        elif distress in ("high", "crisis"):
            self.serial.hug_reach()

        # Default: waist hug (most versatile)
        else:
            self.serial.hug_waist()

    def _execute_gesture(self, gesture_name: str, person: str = "Guest"):
        name = gesture_name.lower().strip()

        # Smart hug routing
        if name == "hug":
            self._smart_hug(person)
            return
        
        if name in ("hug_leg", "hug_waist", "hug_reach", "comfort_pat"):
            self.serial.gesture(name)
            return
        
        # Standard gestures
        VALID = {
            "wave", "handshake", "nod", "shake", "happy", "sad", "surprised", "point",
        }
        if name in VALID:
            self.serial.gesture(name)

    def _check_emotion_and_act(self, person: str, text: str, emotion: str):
        pass

    def _conversation_turn(self, user_text: str):
        if not user_text.strip():
            return
        
        person = self._active_user
        perception = self.vision.get_perception()
        emotion = perception.dominant_emotion

        # Persist
        self.memory.upsert_user(self._active_user)
        self.memory.add_interaction(self._active_user, "user", user_text, emotion)

        # Check for persona update intent
        update_response = self.persona.try_parse_persona_update(user_text, person)
        if update_response:
            clean, gestures = LLMEngine.extract_gestures_static(update_response)

            # Emit persona update events
            p_name = self.persona.persona.name
            for g in gestures:
                self._execute_gesture(g, person)

            self._speak(clean, emotion="happy")
            self.memory.add_interaction(person, "robot", clean, "neutral")

        # Emotion tracking
        self._check_emotion_and_act(person, user_text, emotion)

        # Build system prompt with persona + relationships
        memory_ctx = self.memory.build_context_for_llm(person)
        history = self.memory.to_llm_messages(person)
        system = self.persona.build_system_prompt(
            active_user=person,
            memory_context=memory_ctx,
            user_emotion="neutral",
            robot_emotion=self.persona.persona.base_emotion,
        )

        # Thinking
        self._set_state(RobotState.THINKING)
        self.serial.thinking_start()

        # Agents Tasks

        self.serial.thinking_stop()
        self._set_state(RobotState.SPEAKING)

        # Execute gestures
        for g in gestures:
            self._execute_gesture(g, person)

            # Fallback emotion gesture if none from LLM
        if not gestures and emotion != "neutral":
            mapped = EMOTION_GESTURES.get(emotion)
            if mapped:
                self._execute_gesture(mapped.replace("gesture_", ""), person)

        self.serial.speaking_start()
        self._speak(clean, emotion="neutral")
        self.serial.speaking_stop()

        self.memory.add_interaction(person, "robot", clean, "neutral")
        self._set_state(RobotState.IDLE)

    def _proactive_checkin(self):
        person = self._active_user
        if person == "Guest":
            return
        if self.state != RobotState.IDLE:
            return
        
        interval = PERSONA.get("proactive_checkin_interval", 300)
        if time.time() - self._last_proactive_check < interval:
            return
        
        self._last_proactive_check = time.time()
        log.info(f"[Robot Brain] Proactive check-in for {person}")
        threading.Thread(
            target=self._initiate_support,
            args=(person, "neutral"),
            daemon=True
        ).start()

    def _get_name(self, perception: Perception) -> str:
        return perception.known_names[0] if perception.known_names else "Guest"

    def _log_background_emotion(self):
        interval = PERSONA.get("mood_log_interval", 60)
        if time.time() - getattr(self, "_last_mood_log", 0) < interval:
            return
        
        self._last_mood_log = time.time()
        perception = self.vision.get_perception()
        person = self._get_name(perception)
        if person != "Guest":
            # Recording emotion
            pass

    def _main_loop(self):
        self.speech.start_listening_thread() # Start listening thread - pushes to SpeechModule queue

        last_reminder_check = 0.0

        while self._running:
            self._handle_serial_events() # Handle incoming Arduino events

            if time.time() - last_reminder_check > 30:
                self._check_reminders()
                last_reminder_check = time.time()

            # AUtonomous emotional chack-in
            self._proactive_checkin()

            # Handle spoken input
            if self.state == RobotState.IDLE:
                text = self.speech.get_transcription()

                if text:
                    threading.Thread(
                        target=self._conversation_turn,
                        args=(text,),
                        daemon=True,
                    ).start()

            self._log_background_emotion()
            
            time.sleep(0.05)