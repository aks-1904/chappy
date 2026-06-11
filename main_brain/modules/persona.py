import logging
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, field
from contextlib import contextmanager
import time
import sqlite3

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