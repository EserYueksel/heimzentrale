"""SQLite-Datenbank (/data/heimzentrale.db).

Eine Verbindung fuer alle Threads, geschuetzt durch eine Sperre. Beim Start werden fehlende
Tabellen und Spalten angelegt, damit eine Datenbank aus Version 1 einfach weiterlaeuft.
"""
import json
import sqlite3
import threading

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS latest (
  host TEXT PRIMARY KEY,
  received INTEGER NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
  host TEXT NOT NULL,
  ts INTEGER NOT NULL,
  height INTEGER,
  headers INTEGER,
  disk_avail INTEGER,
  disk_size INTEGER,
  temp REAL,
  peers_out INTEGER,
  peers_in INTEGER,
  mempool_tx INTEGER,
  mempool_bytes INTEGER,
  service_ok INTEGER,
  PRIMARY KEY (host, ts)
);
CREATE TABLE IF NOT EXISTS alerts (
  key TEXT PRIMARY KEY,
  level INTEGER NOT NULL,
  first_seen INTEGER NOT NULL,
  notified_level INTEGER NOT NULL DEFAULT 0,
  title TEXT,
  text TEXT
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  host TEXT NOT NULL,
  kind TEXT NOT NULL,
  params TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL,
  created INTEGER NOT NULL,
  updated INTEGER NOT NULL,
  log TEXT NOT NULL DEFAULT '[]',
  result TEXT
);
CREATE INDEX IF NOT EXISTS tasks_host ON tasks(host, id);
CREATE TABLE IF NOT EXISTS inventory (
  host TEXT PRIMARY KEY,
  updated INTEGER NOT NULL,
  data TEXT NOT NULL
);
"""

# Spalten, die in Version 2 dazugekommen sind
SAMPLE_COLUMNS_V2 = {"cpu": "REAL", "mem_pct": "REAL", "net_rx": "INTEGER", "net_tx": "INTEGER"}


class Database:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)
            have = {r["name"] for r in self.conn.execute("PRAGMA table_info(samples)")}
            for col, typ in SAMPLE_COLUMNS_V2.items():
                if col not in have:
                    self.conn.execute(f"ALTER TABLE samples ADD COLUMN {col} {typ}")
            self.conn.commit()

    def query(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def run(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def kv_get(self, key, default=None):
        row = self.one("SELECT value FROM kv WHERE key=?", (key,))
        return row["value"] if row else default

    def kv_set(self, key, value):
        self.run("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value if isinstance(value, str) else json.dumps(value)))

    def close(self):
        with self.lock:
            self.conn.close()


_db = None


def get():
    global _db
    if _db is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _db = Database(config.DATA_DIR / "heimzentrale.db")
    return _db


def use(path):
    """Fuer Tests: eine andere Datenbankdatei verwenden."""
    global _db
    if _db is not None:
        _db.close()
    _db = Database(path)
    return _db
