"""GitHub App integration: OAuth user authorization, installation tokens, and private archive download.

Security model
- The App private key, the OAuth client secret, GitHub user tokens and installation tokens live only
  in this process. The browser receives an opaque Astral session token (never a GitHub credential).
- A repository is importable only if (1) the signed-in GitHub user can read it (checked with the user's
  own token) and (2) the GitHub App is installed on it (checked with the App JWT). The installation
  token used to download it is minted per job, scoped to that single repository with read-only
  ``contents`` + ``metadata`` permissions, and discarded afterwards.
- Nothing here ever logs or returns a token; error messages are fixed strings.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import logging
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Optional
from urllib.parse import quote, urlencode, urlparse

import httpx

from app.config import settings
from app.services.downloader import ALLOWED_ARCHIVE_HOSTS

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"

STATE_TTL_SECONDS = 600
TICKET_TTL_SECONDS = 60
MAX_LISTED_REPOS = 300
MAX_BRANCHES = 300

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
REF_PATTERN = re.compile(r"^[A-Za-z0-9._/\-]{1,100}$")


class GitHubError(Exception):
    """A user-presentable GitHub integration failure. ``message`` never contains secrets."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

# Tests inject an httpx.MockTransport here so no real GitHub traffic happens.
_transport_override: Optional[httpx.BaseTransport] = None


def set_transport_override(transport: Optional[httpx.BaseTransport]) -> None:
    global _transport_override
    _transport_override = transport


def _private_key_pem() -> str:
    if settings.github_app_private_key:
        return settings.github_app_private_key
    if settings.github_app_private_key_path:
        try:
            return Path(settings.github_app_private_key_path).read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def is_configured() -> bool:
    return bool(
        settings.github_app_id
        and settings.github_app_client_id
        and settings.github_app_client_secret
        and _private_key_pem()
    )


def require_configured() -> None:
    if not is_configured():
        raise GitHubError(
            "github_not_configured",
            "GitHub App integration is not configured on this server.",
            503,
        )


def install_url() -> Optional[str]:
    if not settings.github_app_slug:
        return None
    return f"https://github.com/apps/{quote(settings.github_app_slug, safe='')}/installations/new"


def callback_url() -> str:
    return f"{settings.public_backend_url}/api/github/callback"


# --------------------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------------------

def _client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=False,
        transport=_transport_override,
    )


def _headers(token: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "astrograph-github-app",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _raise_for_status(resp: httpx.Response) -> None:
    status = resp.status_code
    if status < 400:
        return
    remaining = resp.headers.get("x-ratelimit-remaining")
    if status == 429 or (status == 403 and (remaining == "0" or resp.headers.get("retry-after"))):
        reset = resp.headers.get("x-ratelimit-reset")
        when = ""
        if reset and reset.isdigit():
            when = " Try again after " + time.strftime("%H:%M UTC", time.gmtime(int(reset))) + "."
        raise GitHubError("github_rate_limited", "GitHub API rate limit reached." + when, 429)
    if status == 401:
        raise GitHubError("github_auth_expired", "GitHub authorization expired. Reconnect GitHub.", 401)
    if status == 403:
        raise GitHubError("github_forbidden", "GitHub denied access to this resource.", 403)
    if status in (404, 410):
        raise GitHubError("github_not_found", "Not found, or not accessible with the granted permissions.", 404)
    if status == 422:
        raise GitHubError("github_rejected", "GitHub rejected the request.", 400)
    raise GitHubError("github_unavailable", f"GitHub returned HTTP {status}.", 502)


def _api(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    auth: Optional[tuple[str, str]] = None,
) -> Any:
    try:
        with _client() as client:
            resp = client.request(
                method,
                f"{API_BASE}{path}",
                headers=_headers(token),
                params=params,
                json=json_body,
                auth=auth,
            )
    except httpx.HTTPError as err:
        logger.warning("GitHub API network failure (%s)", type(err).__name__)
        raise GitHubError("github_unavailable", "Could not reach GitHub. Try again shortly.", 502) from None
    _raise_for_status(resp)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


# --------------------------------------------------------------------------------------
# GitHub App authentication (JWT -> installation token)
# --------------------------------------------------------------------------------------

def app_jwt() -> str:
    require_configured()
    try:
        import jwt  # PyJWT[crypto]; imported lazily so public imports never need it
    except ImportError:
        raise GitHubError(
            "github_not_configured", "Server is missing the PyJWT[crypto] dependency.", 503
        ) from None
    now = int(time.time())
    try:
        return jwt.encode(
            {"iat": now - 60, "exp": now + 9 * 60, "iss": settings.github_app_id},
            _private_key_pem(),
            algorithm="RS256",
        )
    except Exception:
        raise GitHubError(
            "github_not_configured", "The configured GitHub App private key is invalid.", 503
        ) from None


def get_repo_installation_id(owner: str, repo: str) -> int:
    try:
        data = _api("GET", f"/repos/{quote(owner)}/{quote(repo)}/installation", token=app_jwt())
    except GitHubError as err:
        if err.code == "github_not_found":
            raise GitHubError(
                "github_not_installed",
                "The Astrograph GitHub App is not installed on this repository. Install it and grant access first.",
                404,
            ) from None
        raise
    return int(data["id"])


def create_installation_token(installation_id: int, repo_name: str) -> str:
    """Mint a short-lived token limited to one repository with read-only permissions."""
    data = _api(
        "POST",
        f"/app/installations/{int(installation_id)}/access_tokens",
        token=app_jwt(),
        json_body={
            "repositories": [repo_name],
            "permissions": {"contents": "read", "metadata": "read"},
        },
    )
    return str(data["token"])


# --------------------------------------------------------------------------------------
# OAuth user authorization
# --------------------------------------------------------------------------------------

def build_authorize_url(state: str) -> str:
    require_configured()
    query = urlencode(
        {"client_id": settings.github_app_client_id, "redirect_uri": callback_url(), "state": state}
    )
    return f"{OAUTH_AUTHORIZE_URL}?{query}"


def exchange_code_for_user_token(code: str) -> str:
    require_configured()
    try:
        with _client() as client:
            resp = client.post(
                OAUTH_TOKEN_URL,
                headers={"Accept": "application/json", "User-Agent": "astrograph-github-app"},
                data={
                    "client_id": settings.github_app_client_id,
                    "client_secret": settings.github_app_client_secret,
                    "code": code,
                    "redirect_uri": callback_url(),
                },
            )
    except httpx.HTTPError:
        raise GitHubError("github_unavailable", "Could not reach GitHub. Try again shortly.", 502) from None
    if resp.status_code != 200:
        raise GitHubError("github_oauth_failed", "GitHub sign-in failed.", 400)
    token = resp.json().get("access_token")
    if not token:
        raise GitHubError("github_oauth_failed", "GitHub sign-in failed.", 400)
    return str(token)


def get_authenticated_user(user_token: str) -> dict[str, Any]:
    data = _api("GET", "/user", token=user_token)
    return {"id": int(data["id"]), "login": str(data["login"]), "avatar_url": data.get("avatar_url")}


def revoke_user_token(user_token: str) -> None:
    """Best effort: invalidate the user's GitHub token on sign-out."""
    if not is_configured():
        return
    try:
        _api(
            "DELETE",
            f"/applications/{quote(settings.github_app_client_id)}/token",
            json_body={"access_token": user_token},
            auth=(settings.github_app_client_id, settings.github_app_client_secret),
        )
    except GitHubError:
        pass


# --------------------------------------------------------------------------------------
# Repository discovery and permission checks
# --------------------------------------------------------------------------------------

def _paginate(path: str, token: str, key: str, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while len(items) < limit:
        data = _api("GET", path, token=token, params={"per_page": 100, "page": page})
        batch = data.get(key, []) if isinstance(data, dict) else data
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items[:limit]


def list_user_repositories(user_token: str) -> list[dict[str, Any]]:
    """Repositories the user can access AND the App is installed on (GitHub intersects both)."""
    repos: list[dict[str, Any]] = []
    for inst in _paginate("/user/installations", user_token, "installations", 100):
        remaining = MAX_LISTED_REPOS - len(repos)
        if remaining <= 0:
            break
        inst_id = int(inst["id"])
        for r in _paginate(f"/user/installations/{inst_id}/repositories", user_token, "repositories", remaining):
            repos.append(
                {
                    "id": int(r["id"]),
                    "installation_id": inst_id,
                    "full_name": r["full_name"],
                    "owner": r["owner"]["login"],
                    "name": r["name"],
                    "private": bool(r.get("private")),
                    "default_branch": r.get("default_branch") or "main",
                    "description": r.get("description"),
                }
            )
    return repos


def validate_repo_coordinates(owner: str, repo: str, ref: str) -> None:
    if not NAME_PATTERN.match(owner or "") or not NAME_PATTERN.match(repo or ""):
        raise GitHubError("invalid_repository", "Invalid repository owner or name.", 400)
    if (
        not REF_PATTERN.match(ref or "")
        or ".." in ref
        or ref.startswith(("-", "/"))
        or ref.endswith(("/", ".lock"))
    ):
        raise GitHubError("invalid_ref", "Invalid branch or commit reference.", 400)


def authorize_repository_access(user_token: str, owner: str, repo: str) -> dict[str, Any]:
    """Backend-side permission check: the user must be able to read the repo and the App must be installed."""
    validate_repo_coordinates(owner, repo, "main")
    try:
        data = _api("GET", f"/repos/{quote(owner)}/{quote(repo)}", token=user_token)
    except GitHubError as err:
        if err.code in ("github_not_found", "github_forbidden"):
            raise GitHubError(
                "github_access_denied",
                "You do not have access to this repository through the Astrograph GitHub App.",
                403,
            ) from None
        raise
    perms = data.get("permissions") or {}
    if perms and not (perms.get("pull") or perms.get("admin") or perms.get("push")):
        raise GitHubError("github_access_denied", "You do not have read access to this repository.", 403)
    installation_id = get_repo_installation_id(data["owner"]["login"], data["name"])
    return {
        "id": int(data["id"]),
        "owner": data["owner"]["login"],
        "name": data["name"],
        "full_name": data["full_name"],
        "private": bool(data.get("private")),
        "default_branch": data.get("default_branch") or "main",
        "installation_id": installation_id,
    }


def list_branches(installation_id: int, owner: str, repo: str) -> list[dict[str, Any]]:
    token = create_installation_token(installation_id, repo)
    branches = _paginate(f"/repos/{quote(owner)}/{quote(repo)}/branches", token, "", MAX_BRANCHES)
    return [{"name": b["name"], "sha": (b.get("commit") or {}).get("sha")} for b in branches]


# --------------------------------------------------------------------------------------
# Private archive download (feeds the shared extraction + analysis pipeline)
# --------------------------------------------------------------------------------------

def download_private_archive(
    installation_id: int,
    owner: str,
    repo: str,
    ref: str,
    dest_path: Path,
    max_bytes: Optional[int] = None,
) -> None:
    """Stream ``owner/repo@ref`` as a zip to ``dest_path`` using a freshly minted, repo-scoped token."""
    validate_repo_coordinates(owner, repo, ref)
    limit = max_bytes or settings.max_archive_mb * 1024 * 1024
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    token = create_installation_token(installation_id, repo)
    url = f"{API_BASE}/repos/{quote(owner)}/{quote(repo)}/zipball/{quote(ref, safe='/')}"
    auth_header: Optional[dict[str, str]] = _headers(token)

    try:
        with _client(timeout=60.0) as client:
            for _ in range(4):  # initial request + at most 3 redirects
                host = urlparse(url).netloc.lower()
                if urlparse(url).scheme != "https" or (
                    host != "api.github.com" and host not in ALLOWED_ARCHIVE_HOSTS
                ):
                    raise GitHubError("github_unavailable", "Refused unexpected archive redirect.", 502)
                # The token is only ever sent to api.github.com; the signed codeload URL needs none.
                headers = auth_header if host == "api.github.com" else {"User-Agent": "astrograph-github-app"}
                with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code in (301, 302, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise GitHubError("github_unavailable", "GitHub redirect was malformed.", 502)
                        url = location
                        continue
                    if resp.status_code == 404:
                        raise GitHubError(
                            "github_ref_not_found", "Branch or commit not found, or access was revoked.", 404
                        )
                    if resp.status_code != 200:
                        resp.read()
                        _raise_for_status(resp)
                    total = 0
                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            total += len(chunk)
                            if total > limit:
                                raise ValueError(
                                    f"Archive exceeded maximum allowed size of {limit // (1024 * 1024)} MB"
                                )
                            f.write(chunk)
                    return
            raise GitHubError("github_unavailable", "Too many redirects downloading archive.", 502)
    except httpx.HTTPError:
        dest_path.unlink(missing_ok=True)
        raise GitHubError("github_unavailable", "Network error downloading repository archive.", 502) from None
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------------------
# Server-side session, OAuth state, and one-time login tickets (in memory, single process)
# --------------------------------------------------------------------------------------

def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class GitHubSession:
    user_id: int
    login: str
    avatar_url: Optional[str]
    user_token: str
    expires_at: float


class _Stores:
    """Holds sessions, OAuth states and login tickets. Everything is keyed by a hash of the secret."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, GitHubSession] = {}
        self._states: dict[str, tuple[str, float]] = {}  # state hash -> (nonce hash, expiry)
        self._tickets: dict[str, tuple[str, str, float]] = {}  # ticket hash -> (session token, nonce hash, expiry)

    def _purge(self, now: float) -> None:
        self._sessions = {k: v for k, v in self._sessions.items() if v.expires_at > now}
        self._states = {k: v for k, v in self._states.items() if v[1] > now}
        self._tickets = {k: v for k, v in self._tickets.items() if v[2] > now}

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._states.clear()
            self._tickets.clear()

    # --- OAuth state, bound to the initiating browser through a client-held nonce
    def begin_flow(self) -> tuple[str, str]:
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._purge(now)
            self._states[_digest(state)] = (_digest(nonce), now + STATE_TTL_SECONDS)
        return state, nonce

    def consume_state(self, state: str) -> Optional[str]:
        with self._lock:
            entry = self._states.pop(_digest(state or ""), None)
        if not entry or entry[1] < time.time():
            return None
        return entry[0]

    # --- Sessions
    def create_session(self, sess: GitHubSession) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge(time.time())
            self._sessions[_digest(token)] = sess
        return token

    def get_session(self, token: str) -> Optional[GitHubSession]:
        if not token:
            return None
        with self._lock:
            sess = self._sessions.get(_digest(token))
            if sess and sess.expires_at <= time.time():
                self._sessions.pop(_digest(token), None)
                return None
            return sess

    def delete_session(self, token: str) -> Optional[GitHubSession]:
        with self._lock:
            return self._sessions.pop(_digest(token or ""), None)

    # --- One-time tickets: callback -> browser hand-off of the session token
    def create_ticket(self, session_token: str, nonce_hash: str) -> str:
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._tickets[_digest(ticket)] = (session_token, nonce_hash, time.time() + TICKET_TTL_SECONDS)
        return ticket

    def redeem_ticket(self, ticket: str, nonce: str) -> Optional[str]:
        with self._lock:
            entry = self._tickets.pop(_digest(ticket or ""), None)
        if not entry or entry[2] < time.time():
            return None
        if not hmac.compare_digest(entry[1], _digest(nonce or "")):
            return None
        return entry[0]


stores = _Stores()


def new_session_expiry() -> float:
    return time.time() + settings.github_session_ttl_minutes * 60


def bearer_token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def session_from_authorization(authorization: Optional[str]) -> Optional[GitHubSession]:
    token = bearer_token_from_header(authorization)
    return stores.get_session(token) if token else None
