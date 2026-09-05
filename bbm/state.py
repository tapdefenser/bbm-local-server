"""Persistent local accounts, sessions, and the first mutable gameplay state."""
import hashlib
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


WALLET_FIELDS = (
    "cash", "p_cash", "coin", "candy", "choco", "manaStone",
    "friendPoint", "mandoriSeed", "mandoriTonic", "soulStone",
)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class State:
    def __init__(self, path, starting_wallet=None):
        self.path = Path(path)
        supplied = starting_wallet or {}
        self.starting_wallet = {name: supplied.get(name, 0) for name in WALLET_FIELDS}
        if any(type(value) is not int or not (0 <= value < 2**63) for value in self.starting_wallet.values()):
            raise ValueError("Wallet defaults must be nonnegative int64 values")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    udid TEXT UNIQUE NOT NULL,
                    token_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wallets (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    cash INTEGER NOT NULL, p_cash INTEGER NOT NULL,
                    coin INTEGER NOT NULL, candy INTEGER NOT NULL, choco INTEGER NOT NULL,
                    manaStone INTEGER NOT NULL, friendPoint INTEGER NOT NULL,
                    mandoriSeed INTEGER NOT NULL, mandoriTonic INTEGER NOT NULL,
                    soulStone INTEGER NOT NULL
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
            if "last_login_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN last_login_at INTEGER NOT NULL DEFAULT 0")
            # Upgrade accounts created by the earlier bootstrap-only milestone.
            for row in db.execute("SELECT id FROM users WHERE id NOT IN (SELECT user_id FROM wallets)"):
                self._insert_wallet(db, row["id"])

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _insert_wallet(self, db, user_id):
        fields = ",".join(WALLET_FIELDS)
        placeholders = ",".join("?" for _ in WALLET_FIELDS)
        db.execute(f"INSERT INTO wallets (user_id,{fields}) VALUES (?,{placeholders})",
                   (user_id, *(self.starting_wallet[name] for name in WALLET_FIELDS)))

    def _create(self, db, udid, token):
        now = int(time.time())
        cur = db.execute(
            "INSERT INTO users (udid,token_hash,nickname,created_at,last_login_at) VALUES (?,?,?,?,?)",
            (udid, digest(token), "Local Mayor", now, now),
        )
        nickname = f"Mayor {cur.lastrowid}"
        db.execute("UPDATE users SET nickname=? WHERE id=?", (nickname, cur.lastrowid))
        self._insert_wallet(db, cur.lastrowid)
        return cur.lastrowid, nickname

    def create(self):
        udid, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        with self.connect() as db:
            self._create(db, udid, token)
        return {"udid": udid, "accessToken": token}

    def exists(self, udid):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM users WHERE udid=?", (udid,)).fetchone() is not None

    def login(self, udid, token):
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE udid=?", (udid,)).fetchone()
            if user is None or not secrets.compare_digest(user["token_hash"], digest(token)):
                return None
            return self._new_session(db, user)

    def login_dev(self, udid):
        """Local-only convenience flow used by this client's SendDevLogin path."""
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE udid=?", (udid,)).fetchone()
            if user is None:
                self._create(db, udid, secrets.token_urlsafe(32))
                user = db.execute("SELECT * FROM users WHERE udid=?", (udid,)).fetchone()
            return self._new_session(db, user)

    def _new_session(self, db, user):
        session_id = secrets.randbelow(2**63-1) + 1
        db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (session_id, user["id"], int(time.time()) + 86400))
        db.execute("UPDATE users SET last_login_at=? WHERE id=?", (int(time.time()), user["id"]))
        return {"userId": user["id"], "sessionId": session_id, "nickname": user["nickname"]}

    def valid_session(self, user_id, session_id):
        if type(user_id) is not int or type(session_id) is not int or not (0 < user_id < 2**63 and 0 < session_id < 2**63):
            return False
        with self.connect() as db:
            return db.execute("SELECT 1 FROM sessions WHERE id=? AND user_id=? AND expires_at>?",
                              (session_id, user_id, int(time.time()))).fetchone() is not None

    def profile(self, user_id):
        with self.connect() as db:
            row = db.execute("SELECT id,nickname,created_at,last_login_at FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                return None
            return dict(row)

    def wallet(self, user_id):
        with self.connect() as db:
            row = db.execute(f"SELECT {','.join(WALLET_FIELDS)} FROM wallets WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row is not None else None

    def set_wallet(self, user_id, changes):
        if not changes or any(name not in WALLET_FIELDS for name in changes):
            raise ValueError("Unknown or empty wallet change")
        if any(type(value) is not int or not (0 <= value < 2**63) for value in changes.values()):
            raise ValueError("Wallet values must be nonnegative int64 values")
        with self.connect() as db:
            values = list(changes.values())
            cur = db.execute(
                "UPDATE wallets SET " + ",".join(f"{name}=?" for name in changes) + " WHERE user_id=?",
                (*values, user_id),
            )
            if cur.rowcount != 1:
                raise ValueError("Unknown user id")
        return self.wallet(user_id)

    def users(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,nickname,created_at,last_login_at FROM users ORDER BY id"
            )]
