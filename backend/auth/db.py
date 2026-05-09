"""SQLite schema and helpers for users and sessions."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# api_server.py lives in backend/; keep DB under backend/data/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _BACKEND_ROOT / "data" / "intellimodel_users.db"


def db_path() -> Path:
    raw = os.environ.get("INTELLIMODEL_SQLITE_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_DB


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_connection() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_sub TEXT NOT NULL UNIQUE,
            email TEXT,
            email_verified INTEGER NOT NULL DEFAULT 0,
            name TEXT,
            picture_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        """
    )
    conn.commit()


@dataclass
class UserRecord:
    id: int
    google_sub: str
    email: Optional[str]
    email_verified: bool
    name: Optional[str]
    picture_url: Optional[str]
    created_at: str
    updated_at: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "email_verified": self.email_verified,
            "name": self.name,
            "picture_url": self.picture_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _row_to_user(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=row["id"],
        google_sub=row["google_sub"],
        email=row["email"],
        email_verified=bool(row["email_verified"]),
        name=row["name"],
        picture_url=row["picture_url"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def upsert_user_from_google(
    conn: sqlite3.Connection,
    *,
    google_sub: str,
    email: Optional[str],
    email_verified: bool,
    name: Optional[str],
    picture_url: Optional[str],
) -> UserRecord:
    now = _iso(_utc_now())
    cur = conn.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,))
    row = cur.fetchone()
    if row:
        uid = int(row["id"])
        conn.execute(
            """
            UPDATE users SET
                email = ?,
                email_verified = ?,
                name = ?,
                picture_url = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                email,
                1 if email_verified else 0,
                name,
                picture_url,
                now,
                uid,
            ),
        )
        conn.commit()
        cur2 = conn.execute("SELECT * FROM users WHERE id = ?", (uid,))
        row2 = cur2.fetchone()
        if row2 is None:
            raise RuntimeError(f"User id {uid} missing after update")
        return _row_to_user(row2)

    conn.execute(
        """
        INSERT INTO users (
            google_sub, email, email_verified, name, picture_url, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            google_sub,
            email,
            1 if email_verified else 0,
            name,
            picture_url,
            now,
            now,
        ),
    )
    conn.commit()
    cur3 = conn.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,))
    return _row_to_user(cur3.fetchone())


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_session(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    max_age_days: int = 30,
) -> str:
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)
    now = _utc_now()
    expires = now + timedelta(days=max_age_days)
    conn.execute(
        """
        INSERT INTO sessions (user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, token_hash, _iso(expires), _iso(now)),
    )
    conn.commit()
    return raw


def delete_session_by_raw_token(conn: sqlite3.Connection, raw_token: str) -> None:
    th = _hash_token(raw_token)
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (th,))
    conn.commit()


def get_user_for_session_token(
    conn: sqlite3.Connection, raw_token: str
) -> Optional[UserRecord]:
    th = _hash_token(raw_token)
    now_s = _iso(_utc_now())
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now_s,))
    conn.commit()

    cur = conn.execute(
        """
        SELECT u.* FROM users u
        INNER JOIN sessions s ON s.user_id = u.id
        WHERE s.token_hash = ? AND s.expires_at >= ?
        """,
        (th, now_s),
    )
    row = cur.fetchone()
    if not row:
        return None
    return _row_to_user(row)
