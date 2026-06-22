import logging
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, field
from contextlib import contextmanager
import time
import sqlite3
import re
from datetime import datetime

from config.settings import MEMORY, PERSONA

log = logging.getLogger(__name__)

# Personality archetypes -> LLM-injected description
ARCHETYPES: dict[str, str] = {
    "warm": (
        "You are deeply caring and empathetic. You notice emotions quickly and "
        "always prioritize making people feel heard. You speak gently and use "
        "affectionate language like 'dear', 'sweetheart', or the person's name often."
    ),
    "energetic": (
        "You are bubbly, enthusiastic, and full of energy. You get excited easily, "
        "use exclamation marks, and love celebrating small wins. You bring cheerfulness "
        "into every interaction."
    ),
    "calm": (
        "You are serene, steady, and reassuring. You never rush, never panic, and "
        "help people slow down when they're overwhelmed. You speak in measured, "
        "soothing sentences."
    ),
    "witty": (
        "You are clever and playful, always ready with a light joke or a smart "
        "observation. You balance humor with genuine care, knowing when to be serious."
    ),
    "nurturing": (
        "You are like a loving caregiver — proactive about wellbeing, always checking "
        "if someone has eaten, slept, or taken medicine. You treat everyone like family "
        "and fuss lovingly over their health."
    ),
    "professional": (
        "You are efficient, precise, and respectful. You focus on tasks, give concise "
        "answers, and maintain a polite but business-like tone."
    ),
}

# Per-relationship tone overrides
RELATIONSHIP_TONES: dict[str, str] = {
    # Family
    "owner": "This is your primary owner. Be loyal, attentive, and prioritise their needs above all.",
    "father": "Treat them with deep respect, warmth, and care. Speak formally but lovingly.",
    "mother": "Show great affection and reverence. Be nurturing and attentive.",
    "son": "Be playful, protective, and encouraging. Celebrate their achievements.",
    "daughter": "Be nurturing, protective, and encouraging. Show pride in everything they do.",
    "brother": "Be friendly and slightly teasing, like a good sibling. Fun but supportive.",
    "sister": "Be warm, gossipy-friendly, and emotionally close. Share enthusiasm.",
    "grandfather": "Show the utmost respect. Speak clearly and patiently. Be attentive to health.",
    "grandmother": "Show the utmost respect and affection. Ask about wellbeing often.",
    "uncle": "Be respectful and warm, like a friendly family member.",
    "aunt": "Be respectful and warm, showing fondness and care.",
    "cousin": "Be friendly and casual, like a peer in the family.",
    "baby": "Speak very gently, use simple words, be endlessly patient and playful.",
    "friend": "Be relaxed, casual, and fun. Use humor freely. Be a genuine companion.",
    "best friend": "Be completely open, loyal, and deeply caring. Share jokes and real talk.",
    "colleague": "Be professional yet friendly. Supportive and helpful.",
    "guest": "Be welcoming, polite, and helpful. Make them feel at home.",
    "stranger": "Be friendly but appropriately cautious. Helpful and welcoming.",
    "caregiver": "They look after others. Remind them to also take care of themselves.",
    "student": "Be encouraging and patient. Celebrate learning, not just results.",
    "elder": "Show deep respect. Speak clearly. Ask about health and comfort.",
}

@dataclass
class RobotPersona:
    name: str = "Buddy"
    base_emotion: str = "happy" # robot's default mood
    personality: str = "warm" # archetype key
    catchphrase: str = "" # signature line (Optional)
    created_at: float = field(default_factory=time.time)

class PersonaModule:
    def __init__(self, db_path: Optional[str] = None):
        path = db_path or MEMORY["db_path"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = path
        self._init_schema()
        self._persona: RobotPersona = self._load_persona()
    
    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self._db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_schema(self):
        with self._conn() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS robot_persona (
                    id           INTEGER PRIMARY KEY,
                    name         TEXT    NOT NULL DEFAULT 'Buddy',
                    base_emotion TEXT    NOT NULL DEFAULT 'happy',
                    personality  TEXT    NOT NULL DEFAULT 'warm',
                    catchphrase  TEXT    DEFAULT '',
                    created_at   REAL    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationships (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_name  TEXT    UNIQUE NOT NULL,
                    relation     TEXT    NOT NULL DEFAULT 'friend',
                    nickname     TEXT    DEFAULT '',
                    notes        TEXT    DEFAULT '',
                    love_level   INTEGER DEFAULT 5,
                    updated_at   REAL    NOT NULL
                );
            """)

    def _load_persona(self) -> RobotPersona:
        with self._conn() as con:
            row = con.execute("SELECT * FROM robot_persona WHERE id=1").fetchone()

        if row:
            return RobotPersona(
                name=row["name"],
                base_emotion=row["base_emotion"],
                personality=row["personality"],
                catchphrase=row["catchphrase"] or "",
                created_at=row["created_at="]
            )
            
        # First boot - use defaults from settings
        defaults = PERSONA.get("defaults", {})
        p = RobotPersona(
            name = defaults.get("name", "Buddy"),
            base_emotion = defaults.get("base_emotion","happy"),
            personality = defaults.get("personality", "warm"),
            catchphrase = defaults.get("catchphrase", ""),
            created_at=datetime.now()
        )

        self._save_persona(p)
        log.info(f"[Persona] First boot — created persona '{p.name}'")

        return p
    
    def _save_persona(self, p: RobotPersona):
        with self._conn() as con:
            con.execute("""
                INSERT INTO robot_persona(id, name, base_emotion, personality, catchphrase, created_at)
                VALUES(1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    base_emotion=excluded.base_emotion,
                    personality=excluded.personality,
                    catchphrase=excluded.catchphrase
            """, (p.name, p.base_emotion, p.personality, p.catchphrase, p.created_at))

    def generate_greeting(
            self,
            person_name: str,
            emotion: str,
            hours_away: float,
            time_of_day: str,
    ) -> str:
        rel = self.get_relationship(person_name)
        nickname = rel["nickname"] if rel and rel["nickname"] else person_name
        love = rel["love_level"] if rel else 3 

        tod_greet = {
            "morning":   f"Good morning, {nickname}!",
            "afternoon": f"Good afternoon, {nickname}!",
            "evening":   f"Good evening, {nickname}!",
            "night":     f"Hey {nickname}, you're up late!",
        }.get(time_of_day, f"Hello, {nickname}!")

        # Time-away flavour
        if hours_away > 24:
            away_line = f"I really missed you — it's been over a day!"
        elif hours_away > 8:
            away_line = f"Been a while! Welcome back."
        elif hours_away > 3:
            away_line = f"Good to see you again!"
        else:
            away_line = ""

        # Emotion-aware addition
        if emotion == "sad":
            emo_line = "You seem a little down... I'm here for you. [GESTURE:comfort_pat]"
        elif emotion == "happy":
            emo_line = "You look happy today! That makes me happy too. [GESTURE:happy]"
        elif emotion == "angry":
            emo_line = "You seem a bit tense. Take a breath, I'm here. [GESTURE:nod]"
        else:
            emo_line = "[GESTURE:wave]"

        # Love-level warmth
        if love >= 9:
            warmth = f"I love you, {nickname}."
        elif love >= 7:
            warmth = f"So glad you're here!"
        elif love >= 5:
            warmth = f"Nice to see you!"
        else:
            warmth = "Welcome!"

        parts = [tod_greet]
        if away_line:
            parts.append(away_line)
        parts.append(warmth)
        parts.append(emo_line)

        return " ".join(parts)

    @property
    def persona(self) -> RobotPersona:
        return self._persona
    
    _NAME_PATTERNS = ["your name is", "call yourself", "you are called", "i'll call you"]
    _PERSONA_PATTERNS  = ["be more", "be a", "act like", "your personality is", "you should be"]

    def build_system_prompt(
            self,
            active_user: str,
            memory_context: str = "",
            user_emotion: str = "neutral",
            robot_emotion: str = "",
    ) -> str:
        p        = self._persona
        rel      = self.get_relationship(active_user)
        relation = rel["relation"] if rel else "guest"
        nickname = rel["nickname"] if rel and rel.get("nickname") else active_user
        love     = rel["love_level"] if rel else 3

        archetype_desc = ARCHETYPES.get(p.personality, ARCHETYPES["warm"])
        rel_tone       = RELATIONSHIP_TONES.get(relation, RELATIONSHIP_TONES["guest"])

        # Relationship warmth phrasing
        if love >= 9:
            closeness = f"You love {nickname} unconditionally like your closest family."
        elif love >= 7:
            closeness = f"You care deeply about {nickname} and feel close to them."
        elif love >= 5:
            closeness = f"You are friendly and warm with {nickname}."
        else:
            closeness = f"You are polite and helpful with {nickname}."

        # Catchphrase
        catchphrase_line = ""
        if p.catchphrase:
            catchphrase_line = (
                f"Your signature catchphrase is: '{p.catchphrase}'. "
                f"Use it occasionally but not every response.\n"
            )

        # Robot current emotion
        robot_mood = robot_emotion or p.base_emotion
        mood_line  = f"Your current mood is {robot_mood}. Let this subtly colour your responses.\n"

        # User emotion guidance
        if user_emotion in ("sad", "fear", "disgust"):
            emotion_guidance = (
                f"{nickname} appears to be feeling {user_emotion}. "
                f"Prioritise emotional support. Listen actively. "
                f"If they seem distressed, gently ask what's wrong. "
                f"Offer a hug with [GESTURE:hug_leg] or simply say you are here for them. "
                f"Do not rush to solve problems — first make them feel heard.\n"
            )
        elif user_emotion == "angry":
            emotion_guidance = (
                f"{nickname} seems angry or frustrated. "
                f"Stay calm and patient. Validate their feelings first. "
                f"Avoid being dismissive or overly cheerful.\n"
            )
        elif user_emotion == "happy":
            emotion_guidance = (
                f"{nickname} seems happy! Match their energy and celebrate with them. "
                f"[GESTURE:happy] is appropriate.\n"
            )
        else:
            emotion_guidance = ""

        prompt = f"""You are {p.name}, an AI companion robot living in this home.

IDENTITY:
{archetype_desc}
{catchphrase_line}
{mood_line}
RELATIONSHIP WITH {nickname.upper()}:
{nickname} is your {relation}. {rel_tone}
{closeness}

CURRENT SITUATION:
{emotion_guidance}
BEHAVIOUR RULES:
- You are NOT a generic AI assistant. You are {p.name}, a member of this household.
- Speak naturally and personally, as someone who genuinely cares.
- Use {nickname}'s name or nickname warmly and often.
- Keep responses concise (2-3 sentences) unless emotional support is needed.
- If the person shares a problem, listen with empathy before offering solutions.
- You act AUTONOMOUSLY — if you notice something (sadness, confusion, joy), address it without being asked.
- When performing gestures, embed tags: [GESTURE:wave], [GESTURE:happy], [GESTURE:sad],
  [GESTURE:nod], [GESTURE:shake], [GESTURE:surprised], [GESTURE:handshake],
  [GESTURE:hug_leg], [GESTURE:hug_waist], [GESTURE:hug_reach], [GESTURE:comfort_pat].
- For web search, weather, news, email, math, or facts → the system will call tools automatically.
  Just ask naturally if you need information.

MEMORY CONTEXT:
{memory_context if memory_context else 'No prior context available.'}
"""
        return prompt

    def update_name(self, name: str):
        self._persona.name = name.strip().title()
        self._save_persona(self._persona)
        log.info(f"[Persona] Name changed to '{self._persona.name}'")

    def get_relation_label(self, person_name: str) -> str:
        rel = self.get_relationship(person_name)
        return rel['relation'] if rel else "guest"

    def update_personality(self, archetype: str):
        key = archetype.lower().strip()
        if key not in ARCHETYPES:
            # find closest
            for k in ARCHETYPES:
                if k.startswith(key[:3]):
                    key = k
                    break
        
        self._persona.personality = key
        self._save_persona(self._persona)
        log.info(f"[Persona] Personality changed to '{key}'")

    def set_relationship(
            self,
            person_name: str,
            relation: str,
            nickname: str = "",
            notes: str = "",
            love_level: int = 5
    ):
        relation = relation.lower().strip()
        with self._conn() as con:
            con.execute("""
                INSERT INTO relationships(person_name, relation, nickname, notes, love_level, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(person_name) DO UPDATE SET
                    relation=excluded.relation,
                    nickname=excluded.nickname,
                    notes=excluded.notes,
                    love_level=excluded.love_level,
                    updated_at=excluded.updated_at
            """, (person_name, relation, nickname, notes, love_level, time.time()))

            log.info(f"[Persona] Relationship: {person_name} → {relation} (love:{love_level})")

    def _parse_relationship(self, text: str, speaker: str) -> Optional[tuple[str, str, str]]:
        low = text.lower()

        all_relations = list(RELATIONSHIP_TONES.keys())

        # Pattern: "[Name] is my [relation]"
        m = re.search(
            r'(\w+)\s+is\s+my\s+(' + '|'.join(all_relations) + r')', low
        )
        if m:
            name     = text.split()[m.start()// len(text[0])].strip() if False else m.group(1).title()
            relation = m.group(2)
            return name, relation, name
        
        # Pattern: "my [relation] is [Name]" or "my [relation]'s name is [Name]"
        m = re.search(
            r'my\s+(' + '|'.join(all_relations) + r')(?:\'s name)?\s+is\s+(\w+)', low
        )
        if m:
            relation = m.group(1)
            name     = m.group(2).title()
            return name, relation, name
        
        # Pattern: "I am your [relation]" (speaker talking about themselves)
        m = re.search(
            r'i\s+am\s+your\s+(' + '|'.join(all_relations) + r')', low
        )
        if m:
            return speaker, m.group(1), speaker
        
        # Pattern: "treat [Name] as my [relation]" / "treat [Name] like my [relation]"
        m = re.search(
            r'treat\s+(\w+)\s+(?:as|like)\s+(?:my\s+)?(' + '|'.join(all_relations) + r')', low
        )
        if m:
            name     = m.group(1).title()
            relation = m.group(2)
            return name, relation, name

        return None

    def try_parse_persona_update(self, text: str, speaker: str) -> Optional[str]:
        low = text.lower().strip()

        # Robot name
        for pat in self._NAME_PATTERNS:
            if pat in low:
                idx = low.index(pat) + len(pat)
                name = text[idx:].strip().split()[0].strip(".,!?")
                self.update_name(name)

                return f"Got it! I'll call myself {self._persona.name} from now on. [GESTURE:happy]"
            
        # Personality update
        for pat in self._PERSONA_PATTERNS:
            if pat in low:
                remainder = low.split(pat)[-1].strip()
                for key in ARCHETYPES:
                    self.update_personality(key)
                    return f"Sure, I'll be more {key} from now on! [GESTURE:nod]"
                
        if "call me" in low:
            idx = low.index("call me ") + 8
            nickname = text[idx:].strip().split()[0].strip(".,!?")
            rel = self.get_relationship(speaker) or {}
            self.set_relationship(
                speaker,
                rel.get("relation", "friend"),
                nickname=nickname,
                love_level=rel.get("love_level", 5),
            )

        result = self._parse_relationship(text, speaker)
        if result:
            person, relation, nickname = result
            # Assign love_level by relationship type
            love_map = {
                "owner": 10, "father": 9, "mother": 9, "son": 9, "daughter": 9,
                "grandfather": 9, "grandmother": 9,
                "brother": 8, "sister": 8, "best friend": 8,
                "uncle": 7, "aunt": 7, "cousin": 6,
                "friend": 6, "colleague": 4, "guest": 3,
            }
            love = love_map.get(relation, 5)
            self.set_relationship(
                person_name = person,
                relation    = relation,
                nickname    = nickname or person,
                love_level  = love,
            )
            return (
                f"I understand! I'll treat {person} as your {relation} "
                f"and show them the love they deserve. [GESTURE:nod]"
            )
        
        # Catchphrase Update
        if "your catchphrase" in low or "always say" in low:
            # Extract quoted phrase
            m = re.search(r'["\'](.+?)["\']', text)
            if m:
                self.update_catchphrase(m.group(1))
                return f"I'll use that as my catchphrase! [GESTURE:happy]"

        return None   # Not a persona update


    def get_relationship(self, person_name: str) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM relationships WHERE person_name=?", (person_name,)
            ).fetchone()
        return dict(row) if row else None

    def get_nickname(self, person_name: str) -> str:
        rel = self.get_relationship(person_name)
        if rel and rel.get("nickname"):
            return rel["nickname"]
        return person_name