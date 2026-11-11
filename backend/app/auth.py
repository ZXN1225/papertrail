"""Account credential and opaque session helpers."""

import re
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash

from app.storage.repository import PaperStore

SESSION_COOKIE = "papertrail_session"
SESSION_TTL = timedelta(days=14)
_PASSWORD_HASHER = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password, encoded)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


_DUMMY_PASSWORD_HASH = hash_password("constant dummy password")


def create_account(store: PaperStore, username: str, password: str) -> str | None:
    store.migrate()
    normalized = username.strip()
    if not 3 <= len(normalized) <= 40 or re.fullmatch(r"[A-Za-z0-9_]+", normalized) is None:
        raise ValueError("invalid_username")
    if not 12 <= len(password) <= 256:
        raise ValueError("invalid_password")
    import uuid

    user_id = str(uuid.uuid4())
    try:
        with store._connection() as db:
            db.execute(
                "INSERT INTO users(id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, normalized, hash_password(password), datetime.now(UTC).isoformat()),
            )
    except sqlite3.IntegrityError as exc:
        if "users.username" in str(exc):
            return None
        raise
    return user_id


def login(store: PaperStore, username: str, password: str) -> tuple[str, str] | None:
    store.migrate()
    with store._connection() as db:
        user = db.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    created = datetime.now(UTC)
    with store._connection() as db:
        db.execute(
            "INSERT INTO user_sessions(token_sha256,user_id,created_at,expires_at) VALUES(?,?,?,?)",
            (
                token_digest(token),
                user["id"],
                created.isoformat(),
                (created + SESSION_TTL).isoformat(),
            ),
        )
    return user["id"], token


def session_user(store: PaperStore, token: str | None) -> str | None:
    if not token:
        return None
    with store._connection() as db:
        row = db.execute(
            "SELECT user_id FROM user_sessions WHERE token_sha256=? "
            "AND revoked_at IS NULL AND expires_at>?",
            (token_digest(token), datetime.now(UTC).isoformat()),
        ).fetchone()
    return row["user_id"] if row else None
