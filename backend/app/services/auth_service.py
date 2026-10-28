"""Password hashing, input validation, session tokens and login rate limiting."""

from __future__ import annotations

import base64
from collections import defaultdict, deque
import hashlib
import hmac
import re
import secrets
import threading
import time
from typing import Deque, Optional
import unicodedata

from app.config import settings
from app.storage import user_store

# Existing product policy (signup form: "min. 6 chars"); the maximum bounds hashing cost.
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
MIN_NAME_LENGTH = 2

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# scrypt (memory-hard, OWASP-accepted, in the standard library): N=2^15, r=8, p=1 (~32 MiB).
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _SCRYPT_MAXMEM = 2**15, 8, 1, 128 * 1024 * 1024
_DUMMY_HASH: Optional[str] = None


class ValidationError(ValueError):
    """User-presentable input error."""


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", (email or "")).strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or len(normalized) > 254 or not _EMAIL_RE.match(normalized):
        raise ValidationError("Please enter a valid email address.")
    return normalized


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    return password


def validate_name(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if len(cleaned) < MIN_NAME_LENGTH:
        raise ValidationError(f"Please enter your full name (at least {MIN_NAME_LENGTH} characters).")
    if len(cleaned) > 100:
        raise ValidationError("Name is too long.")
    return cleaned


# --------------------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32
    )
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Constant-time check. A missing hash (Google-only account) never verifies, even for ''."""
    global _DUMMY_HASH
    if not stored:
        # Burn the same CPU as a real check so response time does not reveal the account state.
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password("dummy-password-for-timing")
        stored, ok_if_match = _DUMMY_HASH, False
    else:
        ok_if_match = True
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected) and ok_if_match


# --------------------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------------------

SESSION_COOKIE = "astral_session"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(user_id: str) -> tuple[str, int]:
    """Create a server-side session; returns (cookie token, max_age seconds)."""
    token = secrets.token_urlsafe(32)
    max_age = settings.session_days * 86400
    user_store.create_session(_digest(token), user_id, time.time() + max_age)
    return token, max_age


def user_for_token(token: Optional[str]) -> Optional[user_store.UserRecord]:
    return user_store.get_session_user(_digest(token)) if token else None


def end_session(token: Optional[str]) -> None:
    if token:
        user_store.delete_session(_digest(token))


# --------------------------------------------------------------------------------------
# Rate limiting (in memory, single process)
# --------------------------------------------------------------------------------------

class RateLimiter:
    """Sliding-window failure counter keyed by arbitrary strings."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit, self.window = limit, window_seconds
        self._events: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self._events[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if not q:
            self._events.pop(key, None)
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until another attempt is allowed (0 = allowed)."""
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            if len(q) < self.limit:
                return 0
            return max(1, int(q[0] + self.window - now) + 1)

    def record(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


# Per-account (credential stuffing against one email) and per-IP (spraying across emails).
login_by_email = RateLimiter(limit=5, window_seconds=15 * 60)
login_by_ip = RateLimiter(limit=30, window_seconds=15 * 60)
signup_by_ip = RateLimiter(limit=10, window_seconds=15 * 60)


def clear_rate_limits() -> None:
    for limiter in (login_by_email, login_by_ip, signup_by_ip):
        limiter.clear()
