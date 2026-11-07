"""Independent SQLite transactions, append-only moves/events and versioned schema."""
from contextlib import contextmanager, closing
from pathlib import Path
import json
import sqlite3

SCHEMA_VERSION = 1


class Storage:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this application")
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS moves(game_id TEXT NOT NULL REFERENCES games(id),ply INTEGER NOT NULL,uci TEXT NOT NULL,san TEXT NOT NULL,fen TEXT NOT NULL,PRIMARY KEY(game_id,ply));
                CREATE TABLE IF NOT EXISTS game_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,game_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS game_operations(game_id TEXT NOT NULL,request_id TEXT NOT NULL,payload_hash TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(game_id,request_id));
                CREATE TABLE IF NOT EXISTS positions(id TEXT PRIMARY KEY,fen TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS variations(id TEXT PRIMARY KEY,owner TEXT NOT NULL,parent_id TEXT NOT NULL,state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_runs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_evaluations(cache_key TEXT PRIMARY KEY,result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS analysis_jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,cache_key TEXT NOT NULL,state TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS analysis_owner_key ON analysis_jobs(owner,cache_key);
                CREATE TABLE IF NOT EXISTS bridge_nonces(nonce TEXT PRIMARY KEY,expires REAL NOT NULL);
                PRAGMA user_version=1;
            ''')
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def read(self, query, params=()):
        with closing(self.connect()) as db:
            return db.execute(query, params).fetchall()

    @staticmethod
    def encode(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
