"""User, OAuth identity and login-session persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import Optional
import uuid

from app.storage.database import get_db
from app.storage.repository_store import current_utc_iso


class DuplicateEmailError(Exception):
    """Raised when the unique email index rejects an insert (also under concurrent signups)."""


@dataclass
class UserRecord:
    id: str
    email: str
    name: str
    password_hash: Optional[str]
    picture: Optional[str]
    is_active: bool
    created_at: str
    last_login_at: Optional[str]


def _user(row: sqlite3.Row) -> UserRecord:
    d = dict(row)
    d["is_active"] = bool(d["is_active"])
    return UserRecord(**d)


def create_user(
    email: str,
    name: str,
    password_hash: Optional[str],
    picture: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> UserRecord:
    user_id = f"usr_{uuid.uuid4().hex[:16]}"
    try:
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO users (id, email, name, password_hash, picture, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (user_id, email, name, password_hash, picture, current_utc_iso()),
            )
    except sqlite3.IntegrityError as err:
        raise DuplicateEmailError(email) from err
    return get_user_by_id(user_id, db_path)  # type: ignore[return-value]


def get_user_by_email(email: str, db_path: Optional[Path] = None) -> Optional[UserRecord]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return _user(row) if row else None


def get_user_by_id(user_id: str, db_path: Optional[Path] = None) -> Optional[UserRecord]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user(row) if row else None


def touch_login(user_id: str, db_path: Optional[Path] = None) -> None:
    with get_db(db_path) as conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (current_utc_iso(), user_id))


def get_user_by_identity(provider: str, subject: str, db_path: Optional[Path] = None) -> Optional[UserRecord]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT u.* FROM users u JOIN oauth_identities i ON i.user_id = u.id "
            "WHERE i.provider = ? AND i.subject = ?",
            (provider, subject),
        ).fetchone()
    return _user(row) if row else None


def create_user_with_identity(
    email: str,
    name: str,
    picture: Optional[str],
    provider: str,
    subject: str,
    db_path: Optional[Path] = None,
) -> UserRecord:
    """Atomically create a password-less user and link its provider identity."""
    user_id = f"usr_{uuid.uuid4().hex[:16]}"
    now = current_utc_iso()
    try:
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO users (id, email, name, password_hash, picture, is_active, created_at) "
                "VALUES (?, ?, ?, NULL, ?, 1, ?)",
                (user_id, email, name, picture, now),
            )
            conn.execute(
                "INSERT INTO oauth_identities (provider, subject, user_id, email, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (provider, subject, user_id, email, now),
            )
    except sqlite3.IntegrityError as err:
        raise DuplicateEmailError(email) from err
    return get_user_by_id(user_id, db_path)  # type: ignore[return-value]


def list_identity_providers(user_id: str, db_path: Optional[Path] = None) -> list[str]:
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT provider FROM oauth_identities WHERE user_id = ?", (user_id,)).fetchall()
    return [r["provider"] for r in rows]


# --- Sessions (only a SHA-256 of the cookie token is stored) ---

def create_session(token_hash: str, user_id: str, expires_at: float, db_path: Optional[Path] = None) -> None:
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (time.time(),))
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, current_utc_iso(), expires_at),
        )


def get_session_user(token_hash: str, db_path: Optional[Path] = None) -> Optional[UserRecord]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT u.* FROM auth_sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1",
            (token_hash, time.time()),
        ).fetchone()
    return _user(row) if row else None


def delete_session(token_hash: str, db_path: Optional[Path] = None) -> None:
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
