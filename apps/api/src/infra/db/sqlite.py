import os, sqlite3, threading
from contextlib import contextmanager

_DB_PATH = os.getenv("WERFAMILY_DB_PATH", os.path.abspath("./werfamily.db"))
_LOCK = threading.Lock()

SCHEMA = [
    '''
    CREATE TABLE IF NOT EXISTS individuals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fsid TEXT UNIQUE,
        given TEXT,
        surname TEXT,
        birth_date TEXT,
        birth_place TEXT,
        death_date TEXT,
        death_place TEXT,
        sex TEXT
    );
    ''',
    '''
    CREATE TABLE IF NOT EXISTS relations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        src_fsid TEXT,
        dst_fsid TEXT,
        rel_type TEXT,
        UNIQUE (src_fsid, dst_fsid, rel_type)
    );
    ''',
    '''
    CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        root_fsid TEXT,
        action TEXT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    );
    '''
]

def init_db():
    with _LOCK, sqlite3.connect(_DB_PATH) as con:
        for ddl in SCHEMA:
            con.execute(ddl)
        con.commit()

@contextmanager
def db() :
    with _LOCK, sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        yield con
