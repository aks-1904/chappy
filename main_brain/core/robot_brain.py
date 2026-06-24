from enum import Enum, auto
from typing import Optional
import logging
import threading
import time
from datetime import datetime

from core.serial_bridge import SerialBridge
from modules.vision import VisionModule, Perception
from modules.speech import SpeechModule
from modules.memory import MemoryModule
from modules.llm_engine import LLMEngine
from modules.persona import PersonaModule
from modules.emotional_support import EmotionalSupportModule, DistressLevel
from modules.agent_runner import AgentRunner
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

class RobotBrain:
    def __init__(self):
        self.serial = SerialBridge()
        self.vision = VisionModule()
        self.speech = SpeechModule()
        self.memory = MemoryModule()
        self.llm = LLMEngine()
        self.persona = PersonaModule()
        self.support = EmotionalSupportModule()
        self.agent = AgentRunner(memory_ref=self.memory)

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
            old = self._state.name
            self._state = new_state
            log.debug(f"[Robot Brain] State: {old} -> {new_state.name}")

    @property
    def state(self) -> RobotState:
        with self._state_lock:
            return self._state

    def start(self, serial_port: Optional[str] = None):
        log.info("[Robot Brain] Initializing")

        # Hardware connecting (optional - robot works without arduino)
        connected = self.serial.connect(serial_port)

        if not connected:
            log.warning("[Robot Brain] Arduino not connected")

        self.vision.start()
        self.speech.start()

        self._running = True
        self._main_thread = threading.Thread(
            target=self._main_loop, 
            name="BrainLoop", 
            daemon=True
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
        self.support.record_emotion(name, emotion)

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

    def _offer_hug(self, person: str, distress: DistressLevel):
        nickname = self.persona.get_nickname(person)
        relation = self.persona.get_relation_label(person)

        # Choose hug type
        if distress == DistressLevel.CRISIS:
            self._speak(f"Come here, {nickname}. I've got you. [GESTURE:hug_reach]", emotion="sad")
            self.serial.hug_reach()

        elif distress == DistressLevel.HIGH:
            if relation in ("son", "daughter", "baby", "child"):
                self._speak(f"Let me give you a hug, {nickname}. [GESTURE:hug_leg]", emotion="sad")
                self.serial.hug_leg()
            else:
                self._speak(
                    f"I'm here for you, {nickname}. [GESTURE:hug_waist]",
                    emotion="sad"
                )
                self.serial.hug_waist()

        elif distress == DistressLevel.MODERATE:
            self._speak(
                f"Hey, I noticed you seem a little down. [GESTURE:comfort_pat]",
                emotion="neutral"
            )
            self.serial.comfort_pat()

        # Let gesture finish before speaking more
        time.sleep(0.5)

    def _run_support_turn(self, person: str, user_text: str, support_injection: str):
        self.support.increment_support_turns(person)
        nickname = self.persona.get_nickname(person)

        memory_ctx = self.memory.build_context_for_llm(person)
        system = self.persona.build_system_prompt(
            active_user=person,
            memory_context=memory_ctx,
            user_emotion=self.support.dominant_recent_emotion(person),
        )
        system += f"\n\n{support_injection}"

        history = self.memory.to_llm_messages(person)

        self._set_state(RobotState.THINKING)
        self.serial.thinking_start()

        clean, gestures = self.llm.generate_response(
            user_input=user_text or f"[Robot is initiating emotional support support for {nickname}]",
            memory_context="",
            emotion=self.support.dominant_recent_emotion(person),
            history=history,
        )

        self.serial.thinking_stop()
        self._set_state(RobotState.SUPPORT)

        for g in gestures:
            self._execute_gesture(g, person)

        # Speak
        self.serial.speaking_start()
        self._speak(clean, emotion="sad")
        self.serial.speaking_stop()

        # Persist data
        if user_text:
            self.memory.add_interaction(person, "user", user_text, "sad")
        self.memory.add_interaction(person, "robot", clean, "neutral")

    def _initiate_support(self, person: str, emotion: str):
        self.support.enter_support_mode(person)
        self._set_state(RobotState.SUPPORT)
        self.support.mark_checkin(person)

        distress = self.support.get_distress_level(person)
        nickname = self.persona.get_nickname(person)

        # Decide on physical comfort gesture immediately
        hug_threshold = PERSONA.get("hug_offer_distress_level", 2)
        if distress.value >= hug_threshold:
            self._offer_hug(person, distress)
        else:
            self.serial.comfort_pat()

        # Generate empathetic opening via LLM
        support_injection = self.support.get_support_prompt_injection(
            person=person,
            nickname=nickname,
            distress=distress,
            turn=0,
            relation=self.persona.get_relation_label(person)
        )
        self._run_support_turn(person, "", support_injection)

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
        self._greet_user(self._get_name(perception), perception.dominant_emotion)

    def _handle_touch(self):
        person = self._active_user
        distress = self.support.get_distress_level(person)

        self._set_state(RobotState.GESTURE_ONLY)
        if distress in (DistressLevel.MODERATE, DistressLevel.HIGH, DistressLevel.CRISIS):
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
                if(dist <= PROXIMITY["greet_distance"] and self.state == RobotState.IDLE):
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
        distress = self.support.get_distress_level(person)

        # Children / small people -> leg hug
        if relation in ("son", "daughter", "baby", "child", "cousin"):
            self.serial.hug_leg()

        # Seated or mid-height contact
        elif relation in ("grandfather", "grandmother", "elder"):
            # Elderly often seated -> waist hug
            self.serial.hug_waist()

        # Crisis / reaching up for tall person bending down
        elif distress in (DistressLevel.HIGH, DistressLevel.CRISIS):
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
        self.support.record_text(person, text)
        self.support.record_emotion(
            person,
            emotion,
            intensity=0.6
        )

        distress = self.support.get_distress_level(person)

        # Escalate to support mode
        if(distress.value >= DistressLevel.MODERATE.value and not self.support.is_in_support_mode(person)):
            log.info(f"[Robot Brain] Escalating to support mode for {person} (distress={distress.name})")
            self.support.enter_support_mode(person)

        if self.support.is_in_support_mode(person) and self.support.is_recovering(person):
            self.support.exit_support_mode(person)
            nickname = self.persona.get_nickname(person)
            self._speak(
                f"You seem like you're feeling a bit better, {nickname}. "
                f"I'm really glad. [GESTURE:nod]",
                emotion="happy")

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

        # Inject support prompt if in support mode
        if self.support.is_in_support_mode(person):
            distress = self.support.get_distress_level(person)
            turn = self.support.support_turns(person)
            injection = self.support.get_support_prompt_injection(
                person = person,
                nickname=self.persona.get_nickname(person),
                distress=distress,
                turn=turn,
                relation=self.persona.get_relation_label(person),
            )
            if injection:
                system += f"\n\n{injection}"

            self.support.increment_support_turns(person)

        # Thinking
        self._set_state(RobotState.THINKING)
        self.serial.thinking_start()

        # Agents tools
        if self.agent.needs_tools(user_text):
            clean, gestures = self.agent.run(
                user_input=user_text,
                system_prompt=system,
                history=history,
                emotion=emotion,
                active_user=person,
            )
        else:
            clean, gestures = self.llm.generate_response(
                user_input=user_text,
                memory_context="",
                emotion=emotion,
                history=history,
            )

            # Re-build with system (generate_response doesn't take system yet)
            if not clean:
                clean, gestures = self.agent.run(
                    user_input=user_text,
                    system_prompt=system,
                    history=history,
                    emotion=emotion,
                    active_user=person
                )

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
        speak_emotion = self.support.dominant_recent_emotion(person)
        self._speak(clean, emotion=speak_emotion)
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
        
        if self.support.should_checkin(person):
            self._last_proactive_check = time.time()
            log.info(f"[Robot Brain] Proactive check-in for {person}")
            threading.Thread(
                target=self._initiate_support,
                args=(person, self.support.dominant_recent_emotion(person)),
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
            self.support.record_emotion(person, perception.dominant_emotion, intensity=0.5)

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