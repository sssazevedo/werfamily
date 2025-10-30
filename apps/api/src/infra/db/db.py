import os, sqlite3, pathlib, time
from typing import Optional, Iterable

DB_PATH = os.getenv("WER_DB_PATH", "apps/api/src/data/werfamily.db")
pathlib.Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE,
  name TEXT,
  created_at INTEGER
);
CREATE TABLE IF NOT EXISTS families (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE,
  title TEXT,
  created_at INTEGER
);
CREATE TABLE IF NOT EXISTS memberships (
  user_id INTEGER, family_id INTEGER, role TEXT,
  UNIQUE(user_id, family_id)
);
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  family_id INTEGER,
  email TEXT,
  token TEXT UNIQUE,
  expires_at INTEGER,
  created_at INTEGER
);
"""

def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)
        c.commit()

def create_invite(family_slug: str, email: str, token: str, ttl_days: int = 7):
    with get_conn() as c:
        fam = c.execute("SELECT id FROM families WHERE slug=?", (family_slug,)).fetchone()
        if not fam:
            c.execute("INSERT INTO families(slug, title, created_at) VALUES(?,?,?)", (family_slug, family_slug.title(), int(time.time())))
            fam_id = c.lastrowid
        else:
            fam_id = fam["id"]
        exp = int(time.time()) + ttl_days*86400
        c.execute(
            "INSERT INTO invites(family_id, email, token, expires_at, created_at) VALUES(?,?,?,?,?)",
            (fam_id, email, token, exp, int(time.time()))
        )
        c.commit()
