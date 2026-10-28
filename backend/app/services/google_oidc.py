"""Google OpenID Connect (authorization code flow + PKCE), validated entirely on the server.

The browser is only redirected to Google and back. The authorization code is exchanged here with the
client secret, and the returned ID token is verified (signature via Google's JWKS, issuer, audience,
expiry, nonce, verified email) before any account is created or any session is issued.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
FLOW_TTL_SECONDS = 600
JWKS_TTL_SECONDS = 3600

PROVIDER = "google"

# Tests inject an httpx.MockTransport so no real Google traffic happens.
_transport_override: Optional[httpx.BaseTransport] = None


def set_transport_override(transport: Optional[httpx.BaseTransport]) -> None:
    global _transport_override
    _transport_override = transport
    _jwks_cache.clear()


class GoogleAuthError(Exception):
    """Failure with a short machine code that is safe to show the user (no provider detail)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def is_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


# --------------------------------------------------------------------------------------
# Flow state (state -> PKCE verifier + nonce), single use, in memory
# --------------------------------------------------------------------------------------

_flows: dict[str, tuple[str, str, float]] = {}
_flows_lock = threading.Lock()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def begin_flow() -> tuple[str, str]:
    """Return (state, authorize_url). ``prompt=select_account`` forces Google's account chooser."""
    state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32)
    now = time.time()
    with _flows_lock:
        for k in [k for k, v in _flows.items() if v[2] < now]:
            _flows.pop(k, None)
        _flows[state] = (verifier, nonce, now + FLOW_TTL_SECONDS)
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return state, f"{AUTH_URL}?{query}"


def pop_flow(state: str) -> Optional[tuple[str, str]]:
    with _flows_lock:
        entry = _flows.pop(state or "", None)
    if not entry or entry[2] < time.time():
        return None
    return entry[0], entry[1]


def clear_flows() -> None:
    with _flows_lock:
        _flows.clear()


# --------------------------------------------------------------------------------------
# Token exchange and ID token verification
# --------------------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0), transport=_transport_override)


def exchange_code(code: str, verifier: str) -> str:
    """Exchange the authorization code (with PKCE verifier) for an ID token."""
    try:
        with _client() as client:
            resp = client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
    except httpx.HTTPError:
        raise GoogleAuthError("google_unavailable") from None
    if resp.status_code != 200:
        raise GoogleAuthError("google_exchange_failed")
    id_token = resp.json().get("id_token")
    if not id_token:
        raise GoogleAuthError("google_exchange_failed")
    return str(id_token)


_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _signing_keys(force: bool = False) -> dict[str, Any]:
    cached = _jwks_cache.get("jwks")
    if cached and not force and cached[0] > time.time():
        return cached[1]
    try:
        with _client() as client:
            resp = client.get(JWKS_URL)
        resp.raise_for_status()
        keys = {k["kid"]: k for k in resp.json()["keys"]}
    except (httpx.HTTPError, KeyError, ValueError):
        raise GoogleAuthError("google_unavailable") from None
    _jwks_cache["jwks"] = (time.time() + JWKS_TTL_SECONDS, keys)
    return keys


def verify_id_token(id_token: str, expected_nonce: str) -> dict[str, Any]:
    """Verify signature, issuer, audience, expiry, nonce and email; return the claims."""
    import jwt  # PyJWT[crypto]
    from jwt.algorithms import RSAAlgorithm

    try:
        header = jwt.get_unverified_header(id_token)
        if header.get("alg") != "RS256":
            raise GoogleAuthError("google_invalid_token")
        kid = header.get("kid")
        keys = _signing_keys()
        if kid not in keys:
            keys = _signing_keys(force=True)  # key rotation
        if kid not in keys:
            raise GoogleAuthError("google_invalid_token")
        claims = jwt.decode(
            id_token,
            RSAAlgorithm.from_jwk(keys[kid]),
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=60,
        )
    except GoogleAuthError:
        raise
    except jwt.ExpiredSignatureError:
        raise GoogleAuthError("google_token_expired") from None
    except jwt.PyJWTError:
        raise GoogleAuthError("google_invalid_token") from None

    if claims.get("iss") not in ISSUERS:
        raise GoogleAuthError("google_invalid_token")
    if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise GoogleAuthError("google_invalid_token")
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleAuthError("google_invalid_token")
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("google_email_unverified")
    return claims
