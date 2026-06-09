import logging
from pathlib import Path
from contextlib import contextmanager
import sqlite3

from config.settings import MEMORY

log = logging.getLogger(__name__)

# Postgres Database Schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    first_seen  REAL    NOT NULL,
    last_seen   REAL    NOT NULL,
    preferences TEXT    DEFAULT '{}',   -- JSON blob
    notes       TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name   TEXT    NOT NULL,
    role        TEXT    NOT NULL,       -- 'user' or 'robot'
    message     TEXT    NOT NULL,
    emotion     TEXT    DEFAULT 'neutral',
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name   TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    due_time    REAL    NOT NULL,
    done        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_interactions_user
    ON interactions(user_name, timestamp);

CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders(due_time, done);
"""

class MemoryModule:
    def __init__(self):
        db_path = Path(MEMORY["db_path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._init_db()

    def _init_db(self):
        with self._conn() as con:
            con.executescript(SCHEMA)
        log.info(f"[Memory] DB ready at {self._db_path}")

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(
            self._db_path,
            check_same_thread=False
            )
        con.row_factory = sqlite3.Row

        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
